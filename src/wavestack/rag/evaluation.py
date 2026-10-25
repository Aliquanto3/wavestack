"""V1.2 story 15 (CAP-11): the Evaluate tab, judges against the reference annotation, the
aggregates with their n, and the four traps of the judges.

The one place that averages (SPEC, constraints): everywhere else a figure is one question, one
run. The session computes, the page draws (AD-1). Nothing here loads a model or opens a
connection: a judge is a `Judge` the caller gives (a local GGUF with a GBNF grammar, a cloud
model, a fake one in the tests), and the shipped recorded set is replayed from
`content/rag_evaluation.yaml`.

Measures (`evaluation.md`), recomputed here:

- recall@k and MRR, without a model, from the rank of each expected passage in the list the run
  read (`diagnosis.rank_in`, the anchor rule of the diagnosis);
- context precision, faithfulness, relevance, accuracy: one verdict (`yes`, `partly`, `no`) of a
  judge, set against the reference annotation;
- correct refusal, on a `no_answer` question: a rule (the answer holds a refusal formula of the
  content file) and the judges. The other criteria are then « not applicable ».

A verdict a judge's output does not give legibly is `unreadable`: counted apart, out of every
aggregate, never retried. Below `MIN_SAMPLE` questions an aggregate says it is too few.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from wavestack import config
from wavestack.models import catalog
from wavestack.rag import diagnosis
from wavestack.rag.corpus import RagQuestion, load_rag_questions
from wavestack.rag.diagnosis import Listed, folded, rank_in

FILE = "rag_evaluation.yaml"
MIN_SAMPLE = 5  # an aggregate over fewer questions says « too few to conclude »
CRITERIA = ("context_precision", "faithfulness", "relevance", "accuracy", "correct_refusal")
VERDICTS = ("yes", "partly", "no")
UNREADABLE = "unreadable"
VALUE = {"yes": 1.0, "partly": 0.5, "no": 0.0}
ROLES = ("local", "cloud")  # the two judges of the panel
REFERENCE = "reference"
MAX_RUNS = 40  # the runs a page may send
MAX_WHY = 400  # the characters of a justification kept
JUDGE_MAX_TOKENS = 256  # 300 characters of justification (~100 tokens in French) fit
# The GBNF grammar of a judge's output (V1.2 story 15): one JSON object, a verdict on the scale
# and a short justification, no escape, no line break.
GRAMMAR = r"""root ::= "{" ws vkey ":" ws verdict ws "," ws wkey ":" ws why ws "}"
vkey ::= "\"verdict\"" ws
wkey ::= "\"why\"" ws
verdict ::= "\"yes\"" | "\"partly\"" | "\"no\""
why ::= "\"" [^"\\\n]{1,300} "\""
ws ::= [ \n]{0,2}
"""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- the shipped content ----------


class JudgeInfo(_Strict):
    label: str = Field(min_length=1)
    model: str = Field(min_length=1)


class Provenance(_Strict):
    """`constructed`: written by the developer to show the vue, to be recorded with the judges
    of `judges`; `recorded`: really obtained, on `recorded_on`, with their models."""

    kind: Literal["constructed", "recorded"]
    recorded_on: str | None = None
    source_lang: str = "fr"

    @model_validator(mode="after")
    def _recorded_has_a_date(self) -> Provenance:
        if self.kind == "recorded" and not self.recorded_on:
            raise ValueError("a recorded set names its date")
        return self


class Annotation(_Strict):
    """`draft`: proposed by the developer, to be validated; else the name of who annotated."""

    annotated_by: str = Field(min_length=1)
    annotated_on: str | None = None


class CellVerdicts(_Strict):
    reference: Literal["yes", "partly", "no"] | None = None
    local: Literal["yes", "partly", "no", "unreadable"] | None = None
    cloud: Literal["yes", "partly", "no", "unreadable"] | None = None


class RecordedRun(_Strict):
    question_id: str
    preset: str = Field(pattern=r"^[a-z0-9_]+$")
    top_k: int = Field(ge=1, le=20)
    ranks: list[int | None]  # one per expected passage, `None`: not in the list
    answer_text: str = Field(min_length=1)
    verdicts: dict[str, CellVerdicts]

    @model_validator(mode="after")
    def _known_criteria(self) -> RecordedRun:
        unknown = set(self.verdicts) - set(CRITERIA)
        if unknown:
            raise ValueError(f"unknown criteria {sorted(unknown)}")
        return self


class RecordedSet(_Strict):
    provenance: Provenance
    annotation: Annotation
    generator: str = Field(min_length=1)  # the model that wrote the answers
    judges: dict[str, JudgeInfo]
    runs: list[RecordedRun] = Field(min_length=1)

    @model_validator(mode="after")
    def _both_judges(self) -> RecordedSet:
        if set(self.judges) != set(ROLES):
            raise ValueError("a recorded set names its local and its cloud judge")
        return self


class Claim(_Strict):
    text: str = Field(min_length=1)
    label: Literal["supported", "unsupported", "contradicted"]


class TrapVerdict(_Strict):
    verdict: Literal["yes", "partly", "no"]
    why_text: str = Field(min_length=1)


class Trap(_Strict):
    """One of the four traps. `two_judges`: `verdicts` by role; `variance`: `passes` of one
    judge and the `causes` (keys of the texts); `two_tools`: the labelled `claims`; `ranking`:
    nothing more (the order is recomputed from the recorded set)."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    kind: Literal["two_judges", "variance", "two_tools", "ranking"]
    title_text: str = Field(min_length=1)
    explain_text: str = Field(min_length=1)
    question_id: str | None = None
    criterion: str | None = None
    answer_text: str | None = None
    verdicts: dict[str, TrapVerdict] = {}
    passes: list[TrapVerdict] = []
    causes: list[str] = []
    claims: list[Claim] = []


class EvaluationContent(_Strict):
    texts: dict[str, Any]
    refusal_markers: list[str] = Field(min_length=1)
    recorded: RecordedSet
    traps: list[Trap] = Field(min_length=4, max_length=4)


def load_evaluation(lang: str | None = None) -> EvaluationContent:
    """Raises on a missing or invalid file: the content's own test is what fails."""
    path = config.content_file(FILE, lang)
    return EvaluationContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


# ---------- the measures without a model ----------


def recall_at_k(ranks: Sequence[int | None], k: int) -> float | None:
    """The share of the expected passages ranked `k` or better; `None`: none expected."""
    if not ranks:
        return None
    return sum(1 for r in ranks if r is not None and r <= k) / len(ranks)


def reciprocal_rank(ranks: Sequence[int | None]) -> float | None:
    """1 / rank of the first expected passage found, 0 when none is; `None`: none expected."""
    if not ranks:
        return None
    found = [r for r in ranks if r is not None]
    return 1 / min(found) if found else 0.0


def mean(values: Iterable[float]) -> float | None:
    found = list(values)
    return sum(found) / len(found) if found else None


def refused(answer: str, markers: Sequence[str]) -> bool:
    """The answer holds one of the refusal formulas of the content file."""
    text = folded(answer)
    return any(folded(m) in text for m in markers)


def run_ranks(question: RagQuestion, stages: Mapping[str, Sequence[Listed]]) -> list[int | None]:
    """The rank of each expected passage in the last ordered list before the context: the
    reranking's, else the fusion's, else the best of the searches' (as `diagnosis.py`)."""
    for kind in ("rerank", "fusion"):
        if kind in stages:
            return [rank_in(stages[kind], p) for p in question.expected_passages]
    searched = [stages[k] for k in diagnosis.SEARCHES if k in stages]
    ranks: list[int | None] = []
    for passage in question.expected_passages:
        found = [r for items in searched if (r := rank_in(items, passage)) is not None]
        ranks.append(min(found) if found else None)
    return ranks


# ---------- the families: which judge may judge which model ----------


def family_of(architectures: Iterable[str | None], names: Iterable[str | None], lang: str) -> str:
    """The publisher's id of a model (`catalog.publisher_for`); `other` when unknown."""
    return catalog.publisher_for(architectures, names, lang).id


def refusal_reason(
    judge_family: str, generator_family: str, texts: Mapping[str, Any]
) -> str | None:
    """Why a judge may not judge this generator, else `None`: the family rule, with the
    prudence of an unknown family."""
    reasons = texts["panel"]
    if judge_family == catalog.OTHER_ID:
        return str(reasons["unknown_judge_text"])
    if generator_family == catalog.OTHER_ID:
        return str(reasons["unknown_generator_text"])
    if judge_family == generator_family:
        return str(reasons["same_family_text"])
    return None


@dataclass(frozen=True)
class LocalOption:
    id: str  # `ref` of the candidate
    label: str
    family: str
    size_bytes: int | None
    reason: str | None  # why it is not admitted


@dataclass(frozen=True)
class CloudOption:
    id: str
    label: str
    family: str
    has_key: bool
    reason: str | None


def local_options(
    candidates: Iterable[Any], generator_family: str, texts: Mapping[str, Any], lang: str
) -> list[LocalOption]:
    """The local models a judge may be taken from: a GGUF file or a llama-server model (both
    accept a GBNF grammar); an Ollama model is refused with its reason. Smallest first."""
    options: list[LocalOption] = []
    for c in candidates:
        if getattr(c, "status", "found") == "incompatible":
            continue
        ref = c.ref or c.path
        if not ref:
            continue
        name = c.name or ref
        header = catalog.header_metadata(c.path) if c.path else None
        raw = header[1] if header else {}
        family = family_of(
            [raw.get("general.architecture"), c.architecture, c.publisher_hint],
            [raw.get("general.basename"), raw.get("general.name"), name],
            lang,
        )
        reason: str | None = None
        if getattr(c, "engine", None) == "ollama":
            reason = str(texts["panel"]["no_grammar_text"])
        else:
            reason = refusal_reason(family, generator_family, texts)
        options.append(LocalOption(ref, name, family, c.size_bytes, reason))
    options.sort(key=lambda o: (o.reason is not None, o.size_bytes or 0, o.label))
    return options


def cloud_options(
    entries: Iterable[Any],
    generator_family: str,
    has_key: Callable[[Any], bool],
    texts: Mapping[str, Any],
    lang: str,
) -> list[CloudOption]:
    options = []
    for entry in entries:
        if not getattr(entry, "enabled", True):
            continue
        family = family_of([], [entry.model], lang)
        options.append(
            CloudOption(
                entry.id,
                entry.model,
                family,
                has_key(entry),
                refusal_reason(family, generator_family, texts),
            )
        )
    return options


# ---------- the judge: prompts, grammar, reading ----------


class Judge(Protocol):
    """What the evaluation needs of a judge: its label and one completion of a prompt. The
    session's are a local engine under `GRAMMAR` and a cloud call; the tests' are fakes."""

    label: str

    def complete(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class Verdict:
    verdict: str  # `yes` | `partly` | `no` | `unreadable`
    why_text: str = ""


def read_verdict(output: str) -> Verdict:
    """A judge's output, read: a JSON object with a verdict on the scale. Anything else
    (invalid JSON, a verdict off the scale) is `unreadable`: no retry, no guess."""
    text = output.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return Verdict(UNREADABLE)
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return Verdict(UNREADABLE)
    if not isinstance(data, dict) or data.get("verdict") not in VERDICTS:
        return Verdict(UNREADABLE)
    why = data.get("why")
    return Verdict(str(data["verdict"]), why.strip()[:MAX_WHY] if isinstance(why, str) else "")


@dataclass(frozen=True)
class Case:
    """What a judge is shown for one run."""

    question: str
    answer: str
    context: Sequence[str]
    expected_answer: str


def judge_prompt(criterion: str, case: Case, texts: Mapping[str, Any]) -> str:
    """The instruction of the criterion, in the session's language, then the material it
    needs (the context only where the criterion reads it)."""
    prompts = texts["prompts"]
    parts = [str(prompts[criterion]), ""]
    labels = prompts["labels"]
    parts.append(f"{labels['question']}\n{case.question}")
    if criterion in ("context_precision", "faithfulness"):
        numbered = "\n".join(f"[{n}] {c}" for n, c in enumerate(case.context, start=1))
        parts.append(f"{labels['context']}\n{numbered}")
    if criterion == "accuracy":
        parts.append(f"{labels['expected']}\n{case.expected_answer}")
    if criterion != "context_precision":
        parts.append(f"{labels['answer']}\n{case.answer}")
    parts.append(str(prompts["format"]))
    return "\n\n".join(parts)


def judge_case(judge: Judge, criterion: str, case: Case, texts: Mapping[str, Any]) -> Verdict:
    """One criterion, one judge, one try."""
    return read_verdict(judge.complete(judge_prompt(criterion, case, texts)))


# ---------- the table and its aggregates ----------


def agreement(judge: str | None, reference: str | None) -> str:
    """`agree` | `disagree` | `unannotated` | `unreadable` | `none` (the judge gave nothing)."""
    if judge is None:
        return "none"
    if judge == UNREADABLE:
        return UNREADABLE
    if reference is None:
        return "unannotated"
    return "agree" if judge == reference else "disagree"


class LiveRun(_Strict):
    """A finished run of the workshop, as the page holds it: the lists (as the journal gave
    them) and the answer."""

    run_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=40)
    question_id: str = Field(max_length=100)
    preset: str = Field(pattern=r"^[a-z0-9_]+$", max_length=40)
    top_k: int = Field(default=diagnosis.DEFAULT_BUDGET, ge=1, le=20)
    stages: list[diagnosis.LiveStage] = Field(max_length=12)
    answer_text: str = Field(default="", max_length=20000)


class EvaluationRequest(_Strict):
    runs: list[LiveRun] = Field(default_factory=list, max_length=MAX_RUNS)


@dataclass(frozen=True)
class SessionVerdict:
    """A verdict the session obtained from a judge of the panel, kept by run."""

    role: str  # `local` | `cloud`
    judge_label: str
    verdict: str
    why_text: str


def _row(
    question: RagQuestion,
    *,
    source: str,
    run_id: str | None,
    preset: str,
    top_k: int,
    ranks: Sequence[int | None],
    answer: str,
    cells_in: Mapping[str, CellVerdicts],
    markers: Sequence[str],
) -> dict[str, Any]:
    no_answer = question.type == "no_answer"
    cells: dict[str, Any] = {}
    for criterion in CRITERIA:
        applicable = (criterion == "correct_refusal") == no_answer
        verdicts = cells_in.get(criterion) or CellVerdicts()
        cell: dict[str, Any] = {"applicable": applicable}
        if applicable:
            cell["reference"] = verdicts.reference
            cell["judges"] = {
                role: (
                    None
                    if (v := getattr(verdicts, role)) is None
                    else {"verdict": v, "agreement": agreement(v, verdicts.reference)}
                )
                for role in ROLES
            }
            if no_answer:
                given = refused(answer, markers)
                cell["rule"] = "yes" if given else "no"
        cells[criterion] = cell
    return {
        "question_id": question.id,
        "question_text": question.question_text,
        "type": question.type,
        "source": source,
        "run_id": run_id,
        "preset": preset,
        "top_k": top_k,
        "answer_text": answer,
        "recall_at_k": None if no_answer else recall_at_k(ranks, top_k),
        "reciprocal_rank": None if no_answer else reciprocal_rank(ranks),
        "cells": cells,
    }


def aggregates(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Per architecture (preset), per measure: the mean, its n, the unreadable verdicts counted
    apart, and « too few » under `MIN_SAMPLE`. Per judge and for the reference: the mean of
    its verdicts, and the rate of agreement with the reference where there is one."""
    out: list[dict[str, Any]] = []
    presets = list(dict.fromkeys(r["preset"] for r in rows))
    for preset in presets:
        mine = [r for r in rows if r["preset"] == preset]
        for measure in ("recall_at_k", "reciprocal_rank"):
            values = [r[measure] for r in mine if r[measure] is not None]
            out.append(_aggregate(preset, measure, "metric", values, 0, len(values)))
        for criterion in CRITERIA:
            cells = [r["cells"][criterion] for r in mine if r["cells"][criterion]["applicable"]]
            for who in (REFERENCE, "rule", *ROLES):
                values, unreadable = [], 0
                for cell in cells:
                    v = _verdict(cell, who)
                    if v == UNREADABLE:
                        unreadable += 1
                    elif v in VALUE:
                        values.append(VALUE[v])
                if values or unreadable:
                    out.append(_aggregate(preset, criterion, who, values, unreadable, len(values)))
            for who in ROLES:
                pairs = [
                    c["judges"][who]["agreement"]
                    for c in cells
                    if c["judges"].get(who)
                    and c["judges"][who]["agreement"] in ("agree", "disagree")
                ]
                if pairs:
                    rate = pairs.count("agree") / len(pairs)
                    item = _aggregate(preset, criterion, f"agreement_{who}", [rate], 0, len(pairs))
                    item["value"] = rate
                    out.append(item)
    return out


def _verdict(cell: Mapping[str, Any], role: str) -> str | None:
    if role in (REFERENCE, "rule"):
        return cell.get(role)
    judged = cell["judges"].get(role)
    return judged["verdict"] if judged else None


def _aggregate(
    preset: str, measure: str, who: str, values: Sequence[float], unreadable: int, n: int
) -> dict[str, Any]:
    return {
        "preset": preset,
        "measure": measure,
        "who": who,
        "value": mean(values),
        "n": n,
        "unreadable": unreadable,
        "too_few": n < MIN_SAMPLE,
    }


def build_table(
    content: EvaluationContent,
    lang: str,
    live: Sequence[LiveRun] = (),
    session_criteria: Mapping[str, Mapping[str, Mapping[str, SessionVerdict]]] | None = None,
) -> dict[str, Any]:
    """The shipped recorded set plus the session's runs (a free question is left out: it does
    not count in n). `session_criteria`: run id -> criterion -> role -> verdict."""
    questions = {q.id: q for q in load_rag_questions(lang)}
    markers = content.refusal_markers
    rows: list[dict[str, Any]] = []
    for run in content.recorded.runs:
        rows.append(
            _row(
                questions[run.question_id],
                source="recorded",
                run_id=None,
                preset=run.preset,
                top_k=run.top_k,
                ranks=run.ranks,
                answer=run.answer_text,
                cells_in=run.verdicts,
                markers=markers,
            )
        )
    latest: OrderedDict[tuple[str, str], LiveRun] = OrderedDict()
    for run in live:
        if run.question_id in questions:
            latest.pop((run.question_id, run.preset), None)
            latest[(run.question_id, run.preset)] = run
    for run in latest.values():
        question = questions[run.question_id]
        stages = {s.kind: [Listed(i.doc_id, i.text) for i in s.items] for s in run.stages}
        cells_in: dict[str, CellVerdicts] = {}
        for criterion, by_role in (session_criteria or {}).get(run.run_id, {}).items():
            cells_in[criterion] = CellVerdicts(**{r: v.verdict for r, v in by_role.items()})
        row = _row(
            question,
            source="session",
            run_id=run.run_id,
            preset=run.preset,
            top_k=run.top_k,
            ranks=run_ranks(question, stages),
            answer=run.answer_text,
            cells_in=cells_in,
            markers=markers,
        )
        for criterion, by_role in (session_criteria or {}).get(run.run_id, {}).items():
            for role, v in by_role.items():
                judged = row["cells"][criterion].get("judges", {}).get(role)
                if judged is not None:
                    judged["why_text"] = v.why_text
                    judged["judge_label"] = v.judge_label
        rows.append(row)
    seen_judges = {
        role
        for r in rows
        for cell in r["cells"].values()
        for role, v in (cell.get("judges") or {}).items()
        if v
    }
    return {
        "n": len({r["question_id"] for r in rows}),
        "architectures": list(dict.fromkeys(r["preset"] for r in rows)),
        "judges_n": len(seen_judges),
        "rows": rows,
        "aggregates": aggregates(rows),
    }


# ---------- the four traps ----------


def faithfulness_ragas(claims: Sequence[Claim]) -> float:
    """Ragas' definition: the claims the context supports over all the claims."""
    return sum(1 for c in claims if c.label == "supported") / len(claims)


def faithfulness_deepeval(claims: Sequence[Claim]) -> float:
    """DeepEval's definition: the claims the context does not contradict over all of them."""
    return sum(1 for c in claims if c.label != "contradicted") / len(claims)


def ranking(content: EvaluationContent) -> dict[str, list[dict[str, Any]]]:
    """The architectures ranked by each judge, from the recorded verdicts (the mean of every
    verdict the judge gave on the architecture), best first."""
    out: dict[str, list[dict[str, Any]]] = {}
    for role in ROLES:
        scores: dict[str, list[float]] = {}
        for run in content.recorded.runs:
            for cell in run.verdicts.values():
                v = getattr(cell, role)
                if v in VALUE:
                    scores.setdefault(run.preset, []).append(VALUE[v])
        ordered = sorted(
            ((p, sum(v) / len(v), len(v)) for p, v in scores.items()), key=lambda t: -t[1]
        )
        out[role] = [{"preset": p, "value": s, "n": n} for p, s, n in ordered]
    return out


def replay_trap(trap_id: str, lang: str | None = None) -> dict[str, Any] | None:
    """A trap replayed from its recording, nothing run: `None` when unknown."""
    lang = lang or config.DEFAULT_LANGUAGE
    content = load_evaluation(lang)
    trap = next((t for t in content.traps if t.id == trap_id), None)
    if trap is None:
        return None
    out: dict[str, Any] = {
        "id": trap.id,
        "kind": trap.kind,
        "title_text": trap.title_text,
        "explain_text": trap.explain_text,
        "provenance": content.recorded.provenance.model_dump(),
        "judges": {r: j.model_dump() for r, j in content.recorded.judges.items()},
        "recorded": True,
    }
    if trap.question_id:
        asked = {q.id: q.question_text for q in load_rag_questions(lang)}
        out["question_text"] = asked.get(trap.question_id, "")
    if trap.kind == "two_judges":
        out |= {
            "criterion": trap.criterion,
            "answer_text": trap.answer_text,
            "verdicts": {r: v.model_dump() for r, v in trap.verdicts.items()},
        }
    elif trap.kind == "variance":
        out |= {
            "criterion": trap.criterion,
            "answer_text": trap.answer_text,
            "passes": [p.model_dump() for p in trap.passes],
            "causes": trap.causes,
        }
    elif trap.kind == "two_tools":
        out |= {
            "claims": [c.model_dump() for c in trap.claims],
            "ragas": faithfulness_ragas(trap.claims),
            "deepeval": faithfulness_deepeval(trap.claims),
        }
    else:
        out |= {"ranking": ranking(content)}
    return out


# ---------- the endpoints' payloads ----------


def listing(
    lang: str | None = None,
    *,
    panel: Mapping[str, Any] | None = None,
    finops: Mapping[str, Any] | None = None,
    live: Sequence[LiveRun] = (),
    session_criteria: Mapping[str, Mapping[str, Mapping[str, SessionVerdict]]] | None = None,
) -> dict[str, Any]:
    """`GET /api/rag_lab/evaluation` (and `POST`, with the page's `live` runs): the texts, the
    panel, the spend, the recorded set (plus the session's runs) with its aggregates, and the
    traps. No model."""
    lang = lang or config.DEFAULT_LANGUAGE
    content = load_evaluation(lang)
    recorded = content.recorded
    return {
        "lang": lang,
        "texts": content.texts,
        "min_sample": MIN_SAMPLE,
        "criteria": list(CRITERIA),
        "panel": panel,
        "finops": finops,
        "provenance": recorded.provenance.model_dump(),
        "annotation": recorded.annotation.model_dump(),
        "judges": {r: j.model_dump() for r, j in recorded.judges.items()},
        "table": build_table(content, lang, live, session_criteria=session_criteria),
        "traps": [{"id": t.id, "kind": t.kind, "title_text": t.title_text} for t in content.traps],
    }


__all__ = [
    "CRITERIA",
    "GRAMMAR",
    "MIN_SAMPLE",
    "Case",
    "EvaluationRequest",
    "Judge",
    "LiveRun",
    "SessionVerdict",
    "Verdict",
    "build_table",
    "cloud_options",
    "judge_case",
    "judge_prompt",
    "listing",
    "load_evaluation",
    "local_options",
    "read_verdict",
    "recall_at_k",
    "reciprocal_rank",
    "replay_trap",
]
