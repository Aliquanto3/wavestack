"""Measures the provided agent cases on the local model and proposes their `max_model_calls`.

    uv run python tools/eval/measure_cases.py [--runs 3] [--cases id1 id2] [--model x.gguf]
                                              [--json out.json]

Each case is played `--runs` times in a row on the local model; the proposed cap is the
largest number of model calls seen on the passed tries, plus one (none when no try passed: a
loop to the step limit must not become the cap). An error on one try is recorded and the
measure goes on. The tool never writes `content/agent_cases.yaml`
(the choice of a cap is human) and never changes H5's contract cap (2). It runs on a
temporary data directory, so the trainer's memory and settings are not touched. Never run in
the CI, and never on a real model by a test.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from case_player import play_case  # noqa: E402

CONTRACT_CAPPED = {"h5_refuse_sans_rappel": 2}  # the cap that forbids the call again (contract)
DEFAULT_RUNS = 3


@dataclass
class CaseMeasure:
    case_id: str
    file_cap: int
    calls: list[int] = field(default_factory=list)  # model calls of each try
    passed: list[bool] = field(default_factory=list)
    seconds: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # tries that raised (timeout, refusal)
    skipped: str | None = None  # why the case was not measured here

    @property
    def observed_max(self) -> int | None:
        return max(self.calls) if self.calls else None

    @property
    def proposed_cap(self) -> int | None:
        """Largest count of the passed tries + 1; none for a case skipped, held by the
        contract, or without any passed try."""
        ok = [n for n, passed in zip(self.calls, self.passed, strict=True) if passed]
        if self.skipped or self.case_id in CONTRACT_CAPPED or not ok:
            return None
        return max(ok) + 1


def measure(session, cases, runs: int = DEFAULT_RUNS, lang: str = "fr") -> list[CaseMeasure]:  # noqa: ANN001
    """Plays each case `runs` times, one after the other, and checks it each time."""
    from wavestack.agent_eval.checks import verify

    results = []
    for case in cases:
        measure_ = CaseMeasure(case.id, case.max_model_calls)
        results.append(measure_)
        window = session.configured_window
        if case.window is not None and case.window != window:
            measure_.skipped = f"non mesurable ici (fenêtre {case.window}, courante {window})"
            continue
        for _ in range(runs):
            started = time.monotonic()
            try:
                verdict = verify(case, play_case(session, case), lang)
            except Exception as exc:  # noqa: BLE001 - one try's error must not stop the measure
                measure_.errors.append(f"{type(exc).__name__}: {exc}")
                continue
            measure_.seconds.append(round(time.monotonic() - started, 1))
            measure_.calls.append(verdict.model_calls)
            measure_.passed.append(verdict.passed)
    return results


def render(results: list[CaseMeasure], runs: int) -> str:
    """The table, then the `max_model_calls` lines to copy by hand."""
    rows = [
        (
            "cas",
            "appels par essai",
            "max",
            "plafond proposé",
            "plafond du fichier",
            f"réussites/{runs}",
        )
    ]
    lines = []
    for r in results:
        if r.skipped:
            rows.append((r.case_id, r.skipped, "-", "-", str(r.file_cap), "-"))
            continue
        if r.case_id in CONTRACT_CAPPED:
            proposed = "contrat (2)"
        else:
            proposed = str(r.proposed_cap) if r.proposed_cap else "aucun essai réussi"
        rows.append(
            (
                r.case_id,
                " ".join(map(str, r.calls)) + (f" ({len(r.errors)} erreur(s))" if r.errors else ""),
                str(r.observed_max),
                proposed,
                str(r.file_cap),
                f"{sum(r.passed)}/{len(r.passed) + len(r.errors)}",
            )
        )
        if r.case_id in CONTRACT_CAPPED:
            lines.append(
                f"{r.case_id}: plafond du contrat ({CONTRACT_CAPPED[r.case_id]}), non relevé"
            )
        elif r.proposed_cap:
            lines.append(f"{r.case_id}: max_model_calls: {r.proposed_cap}")
        else:
            lines.append(f"{r.case_id}: aucun essai réussi, plafond à choisir à la main")
        lines.extend(f"{r.case_id}: erreur : {e}" for e in r.errors)
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    table = "\n".join(
        "  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)).rstrip() for row in rows
    )
    return (
        table
        + "\n\nÀ copier à la main dans content/agent_cases.yaml (et en, de) :\n"
        + "\n".join(lines)
    )


def _model_path(arg: str | None) -> Path:
    """Resolved before the data directory changes: the real models folder."""
    from wavestack import config

    return Path(arg) if arg else config.models_dir() / config.DEFAULT_MODEL_FILE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--cases", nargs="*", help="ids of the cases to play (default: all)")
    parser.add_argument("--model", help="path of the .gguf (default: the local model)")
    parser.add_argument("--json", dest="json_path", help="writes the measures to this file")
    args = parser.parse_args(argv)

    model = _model_path(args.model)
    if not model.is_file():
        print(f"Modèle introuvable : {model}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="wavestack-eval-") as tmp:
        os.environ["WAVESTACK_DATA_DIR"] = tmp  # before the session: the real data stays as is
        from wavestack import config
        from wavestack.agent_eval.cases import load_provided_cases
        from wavestack.session.app_session import AppSession

        cases = load_provided_cases("fr")
        if args.cases:
            unknown = sorted(set(args.cases) - {c.id for c in cases})
            if unknown:
                print(f"Cas inconnus : {unknown}", file=sys.stderr)
                return 2
            cases = [c for c in cases if c.id in args.cases]
        session = AppSession(config.load_config())
        try:
            session.boot(str(model)).result()
            results = measure(session, cases, args.runs)
        finally:
            session.close()
    print(render(results, args.runs))
    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
