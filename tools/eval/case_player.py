"""Plays one agent case on an `AppSession` and returns the envelopes of its turns (V1.5 story 2).

Minimal on purpose: one function, shared by `measure_cases.py` and the tests. No k tries,
cancellation, budget, configuration restore nor `not_run` status: the executor of story 4
takes this code over in the package and removes this file.
"""

from __future__ import annotations

import time

from wavestack.agent_eval.cases import AgentCase
from wavestack.session.app_session import Exchange, SendRefused
from wavestack.trace.envelope import Envelope
from wavestack.trace.journal import get_journal

TIMEOUT_SECONDS = 900.0


def _apply(session, case: AgentCase) -> None:  # noqa: ANN001
    """The case's configuration as a scenario's: explicit lists, a `None` keeps the launch
    values. What is enabled and not listed is switched off, what is listed is switched on."""
    session.reset()
    for brick_id in list(session._bricks):  # noqa: SLF001
        session.set_brick(brick_id, brick_id in case.bricks)
    for field, enabled, setter in (
        ("tools", session._tools_enabled, session.set_tool),  # noqa: SLF001
        ("skills", session._skills_enabled, session.set_skill),  # noqa: SLF001
        ("hooks", session._hooks_enabled, session.set_hook),  # noqa: SLF001
        ("mcp_servers", session._mcp_enabled, session.set_mcp_server),  # noqa: SLF001
    ):
        wanted = getattr(case, field)
        if wanted is not None:
            for name in sorted(set(enabled) | set(wanted)):
                setter(name, name in wanted)
    session.join()
    session._history[:] = [  # noqa: SLF001
        Exchange(f"h{n}", ex.user, ex.assistant, "") for n, ex in enumerate(case.history, 1)
    ]


def _wait(session, mark: int, answered: set[str], case: AgentCase) -> None:  # noqa: ANN001
    """Until the session is idle again; H5's validation is answered as `case.approval`."""
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if session.state == "awaiting_human":
            for env in get_journal().events_since(mark):
                approval_id = env.payload.get("approval_id")
                if env.kind == "approval_requested" and approval_id not in answered:
                    answered.add(approval_id)
                    try:
                        session.answer_approval(approval_id, case.approval == "approve", False)
                    except SendRefused:
                        pass  # answered meanwhile
        elif session.state == "idle":
            session.join()
            return
        time.sleep(0.01)
    raise TimeoutError(f"case {case.id}: the session did not come back to idle")


def play_case(session, case: AgentCase) -> list[Envelope]:  # noqa: ANN001
    """Applies the configuration and the history, sends the prompt, answers H5, and applies
    `on_overflow` when the turn is refused for an overflow (the message is sent again).
    Returns the envelopes of the case's turns, every context, in `seq` order."""
    _apply(session, case)
    mark = get_journal().last_seq()
    answered: set[str] = set()
    turn_id = session.send(case.prompt)
    _wait(session, mark, answered, case)
    ended = {
        e.turn_id: e.payload.get("status")
        for e in get_journal().events_since(mark)
        if e.kind == "turn_ended" and e.context_id in (None, "main")
    }
    if ended.get(turn_id) == "overflow" and case.on_overflow != "none":
        try:
            session.compact(case.on_overflow, resend_turn_id=turn_id)
        except SendRefused:
            pass  # the verdict reads the overflow
        else:
            _wait(session, mark, answered, case)
    return [e for e in get_journal().events_since(mark) if e.turn_id is not None]
