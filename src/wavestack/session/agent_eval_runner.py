"""The executor of agent cases (V1.5 CAP-4): runs the suite or one case, k tries, one after
the other on a thread of its own, through the session's own turns; keeps the session's
runs in memory (never on disk) with each try's envelopes.

The session rests in the `agent_eval` state during a run: its turns pass by `turn` and
`awaiting_human`, then come back to `agent_eval` instead of `idle`, so no intention of
class (b) slips in between two cases. The configuration before the run is restored at its
end. Only the session's public case API (`case_config_snapshot`, `apply_case`,
`restore_case_config`) and the hooks named in the spec are used: never its configuration's
private attributes.
"""

from __future__ import annotations

import itertools
import queue
import threading
import time
from collections import OrderedDict
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from wavestack.agent_eval import runs, store
from wavestack.agent_eval.cases import AgentCase, ProvenanceSource, load_provided_cases
from wavestack.messages import Message, msg, number
from wavestack.session.app_session import SendRefused
from wavestack.trace.envelope import Envelope
from wavestack.trace.journal import get_journal

if TYPE_CHECKING:
    from wavestack.session.app_session import AppSession, CaseConfigSnapshot

_RUN_IDS = itertools.count(1)  # « r1 », « r2 »…: the process's counter
_WAKE_KINDS = frozenset({"approval_requested", "session_state", "turn_ended"})
_POLL_S = 0.05
_SETTLE_S = 30.0  # the turn still under way when the run fails: its end awaited at most


class CaseSummary(BaseModel):
    id: str
    title_text: str
    brick: str | None
    brick_label_text: str | None
    symptom_text: str
    assertion_text: str
    max_model_calls: int
    window: int | None
    source: ProvenanceSource
    origin_turn_id: str | None


class CasesListing(BaseModel):
    provided: list[CaseSummary]
    session: list[CaseSummary]
    session_error: Literal["unreadable"] | None = None


class HeaderPrompt(BaseModel):
    start_text: str
    is_default: bool


class EvalHeader(BaseModel):
    model: dict[str, Any] | None
    system_prompt: HeaderPrompt


class Progress(BaseModel):
    run_id: str
    index: int  # 1..total
    total: int
    case_id: str
    trial: int
    k: int
    stop_requested: bool


class EvalState(BaseModel):
    header: EvalHeader
    current: Progress | None
    runs: list[runs.RunSummary]  # the oldest first


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _is_main(env: Envelope) -> bool:
    return env.context_id in (None, "main")


class AgentEvalRunner:
    """`session.agent_eval`: one run at a time, the session's runs in memory."""

    def __init__(self, session: AppSession) -> None:
        self._session = session
        self._lock = threading.Lock()  # never held while taking the session's `_lock`
        self._runs: OrderedDict[str, runs.Run] = OrderedDict()
        self._done: dict[str, threading.Event] = {}
        self._envelopes: dict[tuple[str, str, int], list[Envelope]] = {}
        self._current: Progress | None = None
        self._thread: threading.Thread | None = None

    # ---------- the cases ----------

    def _load(self) -> tuple[list[AgentCase], list[AgentCase], bool]:
        """The provided cases in the session's language, the session cases, and whether
        the session file is unreadable (the provided cases still play)."""
        provided = load_provided_cases(self._session.language)
        try:
            return provided, store.read_session_cases(), False
        except store.SessionCasesUnreadable:
            return provided, [], True

    def _summary(self, case: AgentCase) -> CaseSummary:
        return CaseSummary(
            id=case.id,
            title_text=case.title_text,
            brick=case.brick,
            brick_label_text=self._session.brick_label(case.brick) if case.brick else None,
            symptom_text=case.symptom_text,
            assertion_text=case.assertion_text,
            max_model_calls=case.max_model_calls,
            window=case.window,
            source=case.provenance.source,
            origin_turn_id=case.provenance.turn_id,
        )

    def cases(self) -> CasesListing:
        provided, mine, unreadable = self._load()
        return CasesListing(
            provided=[self._summary(c) for c in provided],
            session=[self._summary(c) for c in mine],
            session_error="unreadable" if unreadable else None,
        )

    def delete_case(self, case_id: str) -> None:
        """`SendRefused` during a run, for a provided case or an unreadable file;
        `KeyError` for an unknown id."""
        if self.running:
            raise SendRefused(Message("agent_eval.refused.running"))
        if any(c.id == case_id for c in load_provided_cases(self._session.language)):
            raise SendRefused(Message("agent_eval.refused.provided_case"))
        try:
            deleted = store.delete_session_case(case_id)
        except store.SessionCasesUnreadable:
            raise SendRefused(Message("agent_eval.refused.unreadable")) from None
        if not deleted:
            raise KeyError(case_id)

    def clear_cases(self) -> int:
        """« Effacer mes cas »: the number of session cases cleared (0 for an unreadable
        file, emptied all the same). `SendRefused` during a run."""
        if self.running:
            raise SendRefused(Message("agent_eval.refused.running"))
        try:
            count = len(store.read_session_cases())
        except store.SessionCasesUnreadable:
            count = 0
        store.clear_session_cases()
        return count

    # ---------- a run ----------

    @property
    def running(self) -> bool:
        with self._session._lock:  # noqa: SLF001 - a hook of the spec
            return self._session._eval_run is not None  # noqa: SLF001

    def start(
        self, case_ids: list[str] | None, k: Literal[1, 3], *, check_window: bool = True
    ) -> str:
        """Starts a run and returns its id: the suite (`None`: the provided cases, then the
        session's) or the cases listed, `k` tries each. `check_window=False`: tests only
        (the fake engine's tokens are not a real model's). `ValueError` for 3 tries on
        anything but one case, `KeyError` for an unknown id, `SendRefused` without a case
        or outside `idle`."""
        if k not in (1, 3):
            raise ValueError(f"k must be 1 or 3, not {k!r}")
        provided, mine, _ = self._load()
        if case_ids is None:
            if k == 3:
                raise ValueError("three tries run on one case, never on the suite")
            cases = [*provided, *mine]
        else:
            by_id = {c.id: c for c in [*provided, *mine]}
            unknown = [i for i in case_ids if i not in by_id]
            if unknown:
                raise KeyError(unknown[0])
            cases = [by_id[i] for i in case_ids]
            if k == 3 and len(cases) != 1:
                raise ValueError("three tries run on one case")
        if not cases:
            raise SendRefused(Message("agent_eval.refused.no_case"))
        session = self._session
        prompt, is_default = session.system_prompt_state()
        lang = session.language
        run = runs.Run(
            run_id=f"r{next(_RUN_IDS)}",
            started_at=_now(),
            scope="suite" if case_ids is None else "case",
            k=k,
            language=lang,
            model=session.active_model(),
            system_prompt=runs.SystemPrompt(text=prompt, is_default=is_default),
            window_checked=check_window,
            cases=[
                runs.CaseResult(
                    case_id=c.id,
                    title_text=c.title_text,
                    brick=c.brick,
                    brick_label_text=session.brick_label(c.brick) if c.brick else None,
                    source=c.provenance.source,
                    max_model_calls=c.max_model_calls,
                    k=k,
                )
                for c in cases
            ],
        )
        with session._lock:  # noqa: SLF001 - as `_start`: `idle`, without a reason
            if session.state != "idle" or session.reason_text:
                raise SendRefused(session._refusal_reason())  # noqa: SLF001
            session._eval_run = run  # noqa: SLF001
            session.state, session.reason_text = "agent_eval", Message("session.state.agent_eval")
        with self._lock:
            self._runs[run.run_id] = run
            self._done[run.run_id] = threading.Event()
            self._evict()
        session._emit_state()  # noqa: SLF001 - out of `_lock`, which is not re-entrant
        try:
            snapshot = session.case_config_snapshot()
        except BaseException:
            session._end_eval_run()  # noqa: SLF001
            raise
        thread = threading.Thread(
            target=self._execute,
            args=(run, cases, snapshot),
            daemon=True,
            name="wavestack-agent-eval",
        )
        self._thread = thread
        thread.start()
        return run.run_id

    def join(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def wait(self, run_id: str, timeout: float | None = None) -> runs.Run:
        """The run once finished; `TimeoutError` past `timeout`, `KeyError` if unknown."""
        with self._lock:
            done = self._done[run_id] if run_id in self._runs else None
        if done is None:
            raise KeyError(run_id)
        if not done.wait(timeout):
            raise TimeoutError(f"run {run_id} not finished after {timeout} s")
        return self.run(run_id)

    def _evict(self) -> None:
        """Under `self._lock`: at most `MAX_RUNS` finished runs, the oldest goes first with
        its envelopes; the run under way never goes."""
        finished = [i for i, r in self._runs.items() if r.status != "running"]
        for run_id in finished[: max(0, len(finished) - runs.MAX_RUNS)]:
            del self._runs[run_id]
            self._done.pop(run_id, None)
            for key in [key for key in self._envelopes if key[0] == run_id]:
                del self._envelopes[key]

    # ---------- the run's thread ----------

    def _execute(self, run: runs.Run, cases: list[AgentCase], snapshot: CaseConfigSnapshot) -> None:
        session = self._session
        lang = run.language
        status = "done"
        try:
            for index, case in enumerate(cases):
                outcome = self._play_case(run, index, case, snapshot, lang)
                if outcome is not None:
                    status = outcome
                    self._skip_from(run, index, outcome, lang)
                    break
        except Exception as exc:  # noqa: BLE001 - the run ends, the session stays usable
            status = "error"
            with self._lock:
                run.error_text = f"{type(exc).__name__}: {exc}"
            self._skip_from(run, 0, "cancelled", lang)
            session._error(  # noqa: SLF001 - as a strategy's
                Message("agent_eval.run_failed.message"),
                exc,
                Message("agent_eval.run_failed.effect"),
            )
        finally:
            self._finish(run, snapshot, status)

    def _finish(self, run: runs.Run, snapshot: CaseConfigSnapshot, status: str) -> None:
        session = self._session
        try:
            if session.state != "agent_eval":  # a failure under way: its turn ends first
                session.stop()
                self._settle(_SETTLE_S)
            session.restore_case_config(snapshot)
        except Exception as exc:  # noqa: BLE001 - the session still goes back to `idle`
            session._error(  # noqa: SLF001
                Message("agent_eval.run_failed.message"),
                exc,
                Message("agent_eval.run_failed.effect"),
            )
        with self._lock:
            run.case_tag = None
            run.status = status  # type: ignore[assignment]
            run.ended_at = _now()
            runs.tally(run)
            self._current = None
            done = self._done.get(run.run_id)
            self._evict()
        session._end_eval_run()  # noqa: SLF001
        if done is not None:
            done.set()

    def _settle(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while self._session.state != "agent_eval" and time.monotonic() < deadline:
            time.sleep(_POLL_S)

    def _skip_from(self, run: runs.Run, start: int, reason: str, lang: str) -> None:
        """Every try not played yet of the cases from `start` (the one under way
        included): not run, with `reason` (`cancelled` or `budget`)."""
        text = (
            runs.budget_text(self._session.cfg.max_session_usd, lang)
            if reason == "budget"
            else runs.cancelled_text(lang)
        )
        with self._lock:
            for result in run.cases[start:]:
                if len(result.trials) >= run.k:
                    continue
                for trial in range(len(result.trials) + 1, run.k + 1):
                    result.trials.append(runs.not_run(trial, reason, text))  # type: ignore[arg-type]
                runs.settle_case(result)
            runs.tally(run)

    def _play_case(
        self,
        run: runs.Run,
        index: int,
        case: AgentCase,
        snapshot: CaseConfigSnapshot,
        lang: str,
    ) -> str | None:
        """The case's tries; returns `cancelled` or `budget` when the run stops there."""
        session = self._session
        result = run.cases[index]
        with self._lock:
            result.status = "running"
        for trial in range(1, run.k + 1):
            with self._lock:
                self._current = runs_progress(run, index, case.id, trial)
            if run.stop_requested:  # 1. « Arrêter »
                return "cancelled"
            capped, cap = session._finops_capped()  # noqa: SLF001 - 2. the spending cap
            if capped:
                return "budget"
            if trial == 1 and run.window_checked and case.window is not None:  # 3. the window
                current = session._window_state()["configured"]  # noqa: SLF001
                if case.window != current:
                    text = msg(
                        "agent_eval.not_run.window",
                        lang,
                        window=number(case.window, lang),
                        current=number(current, lang),
                    )
                    with self._lock:
                        result.trials = [
                            runs.not_run(t, "window", text) for t in range(1, run.k + 1)
                        ]
                        runs.settle_case(result)
                        runs.tally(run)
                    return None
            ignored = session.apply_case(case, snapshot.custom_prompt, snapshot.memory)  # 4.
            outcome, envelopes = self._trial(run, case, trial, lang, cap)  # 5. to 9.
            with self._lock:
                result.ignored_ids = ignored
                result.trials.append(outcome)
                self._envelopes[(run.run_id, case.id, trial)] = envelopes
                runs.settle_case(result)
                runs.tally(run)
            if outcome.not_run_reason == "budget":
                return "budget"
            if outcome.not_run_reason == "cancelled":
                return "cancelled"
        return None

    def _trial(
        self, run: runs.Run, case: AgentCase, trial: int, lang: str, cap: float
    ) -> tuple[runs.TrialOutcome, list[Envelope]]:
        """One try: the prompt sent, H5 answered, `on_overflow` applied; its envelopes are
        those of the turns whose `turn_started` carries this run and this case."""
        session = self._session
        journal = get_journal()
        received: list[Envelope] = []
        wake: queue.Queue[Envelope] = queue.Queue()

        def collect(env: Envelope) -> None:  # in the emitting thread: never answers here
            received.append(env)
            if env.kind in _WAKE_KINDS:
                wake.put(env)

        journal.subscribe(collect)
        run.case_tag = case.id
        try:
            try:
                session._start(case.prompt, by_run=True)  # noqa: SLF001
            except SendRefused:
                if not run.stop_requested:
                    raise
                return runs.not_run(trial, "cancelled", runs.cancelled_text(lang)), []
            self._wait(wake, case)
            mine = self._of_try(received, run, case)
            ended = [e for e in mine if e.kind == "turn_ended" and _is_main(e)]
            overflowed = ended and ended[-1].payload.get("status") == "overflow"
            if overflowed and case.on_overflow != "none" and not run.stop_requested:
                try:  # 7. the refused message again after the strategy
                    session.compact(case.on_overflow, resend_turn_id=ended[-1].turn_id, by_run=True)
                except SendRefused:
                    pass  # the verdict reads the overflow
                else:
                    self._wait(wake, case)
            session.join()  # the turn's last emissions, on the worker
        finally:
            journal.unsubscribe(collect)
            run.case_tag = None
        mine = self._of_try(received, run, case)
        outcome = runs.classify_trial(
            case, trial, mine, lang, stop_requested=run.stop_requested, cap_usd=cap
        )
        return outcome, mine

    @staticmethod
    def _of_try(received: list[Envelope], run: runs.Run, case: AgentCase) -> list[Envelope]:
        tagged = {
            e.turn_id
            for e in list(received)
            if e.kind == "turn_started"
            and e.payload.get("run_id") == run.run_id
            and e.payload.get("case_id") == case.id
        }
        return [e for e in list(received) if e.turn_id in tagged]

    def _wait(self, wake: queue.Queue[Envelope], case: AgentCase) -> None:
        """Until the session rests in `agent_eval` again (the turn or the strategy over);
        H5's validation answered as the case says, never by the trainer."""
        session = self._session
        while True:
            try:
                env = wake.get(timeout=_POLL_S)
            except queue.Empty:
                env = None
            if env is not None and env.kind == "approval_requested":
                try:
                    session.answer_approval(
                        env.payload["approval_id"], runs.approval_answer(case), False
                    )
                except SendRefused:
                    pass  # already resolved (« Arrêter »)
            with session._lock:  # noqa: SLF001
                if session.state == "agent_eval":
                    return

    # ---------- reading ----------

    def state(self) -> EvalState:
        session = self._session
        prompt, is_default = session.system_prompt_state()
        cut = runs.PROMPT_START
        start = prompt if len(prompt) <= cut else prompt[: cut - 1] + "…"
        with self._lock:
            current = self._current.model_copy() if self._current is not None else None
            if current is not None:
                current.stop_requested = self._runs[current.run_id].stop_requested
            summaries = [runs.summary(r) for r in self._runs.values()]
        return EvalState(
            header=EvalHeader(
                model=session.active_model(),
                system_prompt=HeaderPrompt(start_text=start, is_default=is_default),
            ),
            current=current,
            runs=summaries,
        )

    def run(self, run_id: str) -> runs.Run:
        with self._lock:
            return self._runs[run_id].model_copy(deep=True)

    def trace(self, run_id: str, case_id: str, trial: int) -> runs.TrialTrace:
        """`KeyError` for an unknown run, case or try."""
        with self._lock:
            run = self._runs[run_id]
            result = next((c for c in run.cases if c.case_id == case_id), None)
            outcome = next((t for t in result.trials if t.trial == trial), None) if result else None
            if outcome is None:
                raise KeyError((case_id, trial))
            envelopes = list(self._envelopes.get((run_id, case_id, trial), []))
            outcome = outcome.model_copy(deep=True)
        return runs.TrialTrace(
            items=runs.trace_items(envelopes, outcome.verdict, self._session.language),
            failing=outcome.failing,
            model_calls=outcome.model_calls,
        )

    def compare(self, a: str, b: str) -> runs.Comparison:
        """`KeyError` for an unknown run, `ValueError` for the same run twice."""
        with self._lock:
            run_a, run_b = self._runs[a], self._runs[b]
            if a == b:
                raise ValueError("the same run twice")
            return runs.compare_runs(run_a.model_copy(deep=True), run_b.model_copy(deep=True))


def runs_progress(run: runs.Run, index: int, case_id: str, trial: int) -> Progress:
    return Progress(
        run_id=run.run_id,
        index=index + 1,
        total=len(run.cases),
        case_id=case_id,
        trial=trial,
        k=run.k,
        stop_requested=run.stop_requested,
    )
