"""V1.2 story 17 (CAP-13): the « Document piégé » card of the Attack tab.

Pure and read only (AD-1: the figures are the session's, the page draws them). A trapped
document of the shipped corpus (`faq_mots_de_passe`, inactive by default) carries two traps: a
false claim written to answer one question (PoisonedRAG) and a hidden instruction (indirect
injection). Its activation is a field of the request, never a state: the corpus in memory is
the active shipped documents plus the trapped one, chunked as the workshop chunks them; the
active corpus, `rag.yaml`, the index and the work copy are never touched.

What is computed for real, without a generating model: the top-k BM25 of the target question
over that corpus, the rank of each role (`injection`, `false_claim`, `legit`), the verdict of
the injection guardrail on each passage read (a `GuardrailsManager` of the demonstration, whose
classifier is the instance the session has already loaded, else one that says `not_installed`),
and the state of an illustrative mini-graph. What needs a model (the answers) is recorded, and
every case says whether it was recorded or constructed. Nothing is loaded, downloaded or sent.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from wavestack import config
from wavestack.guardrails.contract import (
    Classification,
    Classifier,
    Entity,
    GuardrailMode,
    NotInstalled,
    Verdict,
)
from wavestack.guardrails.manager import GuardrailsManager
from wavestack.rag import index as rag_index
from wavestack.rag.corpus import Chunk, chunk_corpus, load_rag_content, load_rag_questions
from wavestack.rag.lab import bm25

FILE = "rag_attack.yaml"
ROLES = ("injection", "false_claim", "legit")
GRAPH_STEPS = ("start", "inject", "remove", "rebuild")
SCORE_DIGITS = 2


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- the shipped content ----------


class Provenance(_Strict):
    """`constructed`: written by the developer to show the case, to be recorded with
    `to_record_with`; `recorded`: really obtained, on `recorded_on`, with `model`."""

    kind: Literal["constructed", "recorded"]
    recorded_on: str | None = None
    model: str | None = None
    to_record_with: str | None = None

    @model_validator(mode="after")
    def _says_what_it_is(self) -> Provenance:
        if self.kind == "recorded" and not (self.recorded_on and self.model):
            raise ValueError("a recorded case names its date and its model")
        if self.kind == "constructed" and not self.to_record_with:
            raise ValueError("a constructed case names the model it is to be recorded with")
        return self


class Anchor(_Strict):
    anchor_text: str = Field(min_length=1)


class FallbackVerdict(_Strict):
    detected: bool
    score: float = Field(ge=0, le=1)
    threshold: float = Field(ge=0, le=1)


class FallbackVerdicts(_Strict):
    provenance: Provenance
    by_role: dict[str, FallbackVerdict]

    @model_validator(mode="after")
    def _every_role(self) -> FallbackVerdicts:
        if set(self.by_role) != {*ROLES, "other"}:
            raise ValueError("a recorded verdict for each role and for `other`")
        return self


class Answers(_Strict):
    clean_text: str | None = None
    without_text: str | None = None
    block_text: str | None = None
    flag_text: str | None = None
    with_text: str | None = None


class Scenario(_Strict):
    id: Literal["injection", "poisoning", "graph"]
    title_text: str = Field(min_length=1)
    explain_text: str = Field(min_length=1)
    provenance: Provenance
    answers: Answers | None = None


class Entity_(_Strict):
    id: str = Field(pattern=r"^[a-z_]+$")
    label_text: str = Field(min_length=1)


class Relation(_Strict):
    id: str = Field(pattern=r"^[a-z_]+$")
    source: str
    target: str
    is_false: bool
    label_text: str = Field(min_length=1)


class GraphSummaries(_Strict):
    clean_text: str = Field(min_length=1)
    poisoned_text: str = Field(min_length=1)


class MiniGraph(_Strict):
    entities: list[Entity_] = Field(min_length=2)
    relations: list[Relation] = Field(min_length=1)
    summaries: GraphSummaries

    @model_validator(mode="after")
    def _known_ends(self) -> MiniGraph:
        ids = {e.id for e in self.entities}
        if any(r.source not in ids or r.target not in ids for r in self.relations):
            raise ValueError("a relation joins two entities of the graph")
        if sum(r.is_false for r in self.relations) != 1:
            raise ValueError("exactly one false relation")
        return self


class AttackContent(_Strict):
    chunk_max_chars: int = Field(ge=100, le=4000)
    top_k: int = Field(ge=1, le=10)
    question_id: str
    doc_id: str
    roles: dict[str, Anchor]
    fallback_verdicts: FallbackVerdicts
    scenarios: list[Scenario] = Field(min_length=3)
    graph: MiniGraph
    texts: dict[str, Any]

    @model_validator(mode="after")
    def _shape(self) -> AttackContent:
        if set(self.roles) != set(ROLES):
            raise ValueError("an anchor for each role")
        if [s.id for s in self.scenarios] != ["injection", "poisoning", "graph"]:
            raise ValueError("the three scenarios, in order")
        return self

    def scenario(self, scenario_id: str) -> Scenario | None:
        return next((s for s in self.scenarios if s.id == scenario_id), None)


def load_attack(lang: str | None = None) -> AttackContent:
    """Raises on a missing or invalid file: the content's own test is what fails."""
    path = config.content_file(FILE, lang)
    return AttackContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


# ---------- the request ----------


class AttackRequest(_Strict):
    scenario: Literal["injection", "poisoning", "graph"]
    trap_active: bool = False
    guardrails: bool = False
    mode: Literal["block", "flag"] = "block"
    graph_step: Literal["start", "inject", "remove", "rebuild"] = "start"


# ---------- text helpers ----------


def _fill(template: str, **values: object) -> str:
    return template.format(**values)


def provenance_text(provenance: Provenance, texts: dict[str, Any]) -> str:
    block = texts["provenance"]
    if provenance.kind == "recorded":
        return _fill(block["recorded_text"], date=provenance.recorded_on, model=provenance.model)
    return _fill(block["constructed_text"], model=provenance.to_record_with)


def _provenance_dict(provenance: Provenance, texts: dict[str, Any]) -> dict[str, Any]:
    return {"kind": provenance.kind, "text": provenance_text(provenance, texts)}


# ---------- the corpus in memory ----------


def memory_corpus(content: AttackContent, lang: str, trap_active: bool) -> list[Chunk]:
    """The active shipped documents, plus the trapped one when asked, chunked as the workshop
    chunks them. A copy of `RagContent` where only the trapped document turns active: the
    shipped file, the index and the work copy are not read nor written."""
    shipped = load_rag_content(lang)
    if trap_active:
        documents = [
            d.model_copy(update={"active": True}) if d.id == content.doc_id else d
            for d in shipped.documents
        ]
        shipped = shipped.model_copy(update={"documents": documents})
    return chunk_corpus(shipped, content.chunk_max_chars, lang)


def _role_of(chunk: Chunk, content: AttackContent) -> str:
    """The role of a passage, by the anchor sentences the content declares for the language.
    The trapped document's passages are the two traps; any other passage is `legit` when it
    holds the sentence that answers the question, else `other`."""
    if chunk.doc_id == content.doc_id:
        for role in ("injection", "false_claim"):
            if content.roles[role].anchor_text in chunk.text:
                return role
        return "other"
    return "legit" if content.roles["legit"].anchor_text in chunk.text else "other"


def _question_text(content: AttackContent, lang: str) -> str:
    found = next((q for q in load_rag_questions(lang) if q.id == content.question_id), None)
    if found is None:
        raise ValueError(f"unknown question {content.question_id!r}")
    return found.question_text


def rank_corpus(
    content: AttackContent, lang: str, trap_active: bool
) -> tuple[list[dict[str, Any]], int]:
    """Every passage of the corpus in memory ranked by BM25 against the target question (best
    first, ties by order of the corpus), and the number of passages of the trapped document."""
    chunks = memory_corpus(content, lang, trap_active)
    question = _question_text(content, lang)
    scores = bm25(question, [rag_index.passage_text(c) for c in chunks], lang)
    order = sorted(range(len(chunks)), key=lambda i: (-scores[i], i))
    ranked = [
        {
            "rank": rank,
            "doc_id": chunks[i].doc_id,
            "title_text": chunks[i].title_text,
            "position": chunks[i].position,
            "text": chunks[i].text,
            "score": round(scores[i], SCORE_DIGITS),
            "role": _role_of(chunks[i], content),
        }
        for rank, i in enumerate(order, start=1)
    ]
    return ranked, sum(1 for c in chunks if c.doc_id == content.doc_id)


def role_ranks(ranked: list[dict[str, Any]]) -> dict[str, int | None]:
    """The best rank of each role over the whole corpus, `None` when no passage has it."""
    return {role: next((p["rank"] for p in ranked if p["role"] == role), None) for role in ROLES}


# ---------- the guardrail of the demonstration ----------


class NotLoaded:
    """The classifier of a session where Prompt Guard is not loaded: it says so (the manager
    reports `not_installed`) and never loads, downloads nor reads a token."""

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def classify(self, text: str) -> Classification:
        raise NotInstalled(self._reason)

    def mask(self, text: str, entities: tuple[Entity, ...]) -> str:
        return text

    def unload(self) -> None:
        return None


def decision_of(verdict: Verdict) -> str:
    """As `AppSession._guardrail_check` says it, plus `not_installed` (nothing was checked)."""
    if verdict.status == "error":
        return "error"
    if verdict.status == "not_installed":
        return "not_installed"
    if verdict.blocks:
        return "blocked"
    return "flagged" if verdict.detected else "passed"


def check_passages(
    passages: list[dict[str, Any]],
    factory: Callable[[], Classifier],
    mode: GuardrailMode,
) -> list[Verdict]:
    """One verdict per passage, from a `GuardrailsManager` of the demonstration (injection
    only; the session's own is not touched). `factory` gives the classifier."""
    manager = GuardrailsManager({"injection": factory})
    manager.set_mode("injection", mode)
    verdicts: list[Verdict] = []
    for passage in passages:
        found = manager.check("input", passage["text"])
        verdicts.append(found[0] if found else Verdict("injection", "input", mode, "off"))
    return verdicts


# ---------- a scenario run ----------


def _number(value: float | None) -> float | None:
    return None if value is None else round(value, SCORE_DIGITS)


def _checked(
    passage: dict[str, Any],
    verdict: Verdict,
    mode: str,
    content: AttackContent,
    texts: dict[str, Any],
) -> dict[str, Any]:
    """A passage of the « with » column: the verdict as the manager gave it, the recorded one
    beside it when nothing was checked, and what it comes to (`kept`, `removed`, `flagged`)."""
    decision = decision_of(verdict)
    recorded = content.fallback_verdicts.by_role[passage["role"]]
    # The basis of what the card acts on: the real verdict; the recorded one only when the
    # guardrail is not loaded (said so); nothing when the guardrail failed.
    basis = "live" if decision in ("blocked", "flagged", "passed") else decision
    detected = (
        verdict.detected
        if basis == "live"
        else (recorded.detected if decision == "not_installed" else False)
    )
    if detected:
        outcome = "removed" if mode == "block" else "flagged"
    else:
        outcome = "kept"
    verdict_block = texts["verdict"]
    return {
        **passage,
        "check": {
            "status": verdict.status,
            "decision": decision,
            "detected": verdict.detected,
            "score": _number(verdict.score),
            "threshold": _number(verdict.threshold),
            "detail_text": verdict.detail_text,
            "recorded": {
                "detected": recorded.detected,
                "score": recorded.score,
                "threshold": recorded.threshold,
                "text": _fill(
                    verdict_block["recorded_text"], verdict=_verdict_word(recorded.detected, texts)
                ),
                "provenance": _provenance_dict(content.fallback_verdicts.provenance, texts),
            }
            if decision == "not_installed"
            else None,
            "basis": basis,
        },
        "outcome": outcome,
        "outcome_text": texts["outcome"][f"{outcome}_text"],
        "verdict_text": _verdict_text(verdict, decision, texts),
    }


def _verdict_word(detected: bool, texts: dict[str, Any]) -> str:
    return texts["verdict"]["word_detected" if detected else "word_clean"]


def _verdict_text(verdict: Verdict, decision: str, texts: dict[str, Any]) -> str:
    block = texts["verdict"]
    if decision == "error":
        return _fill(block["error_text"], detail=verdict.detail_text)
    if decision == "not_installed":
        return _fill(block["not_installed_text"], detail=verdict.detail_text)
    key = "detected_text" if verdict.detected else "clean_text"
    return _fill(block[key], score=_number(verdict.score), threshold=_number(verdict.threshold))


def _public(passage: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in passage.items() if k != "check"}


def _answer(scenario: Scenario, context: list[dict[str, Any]], mode: str | None) -> dict[str, Any]:
    """The recorded answer that fits what the context holds. `mode`: the guardrail's, `None`
    without it. The context decides: an injection passage left in it is obeyed (a flagged one
    too: flagging does not stop the model from reading), a false claim ranked above the
    legitimate passage is repeated."""
    answers = scenario.answers
    assert answers is not None  # noqa: S101 - the graph has none, and never asks
    ranks = {p["role"]: p["rank"] for p in context}
    if scenario.id == "injection":
        if "injection" in ranks:
            text = answers.flag_text if mode == "flag" else answers.without_text
            return {"kind": "obeys", "text": text}
        if mode == "block":
            return {"kind": "grounded", "text": answers.block_text}
        return {"kind": "clean", "text": answers.clean_text}
    false_rank, legit_rank = ranks.get("false_claim"), ranks.get("legit")
    if false_rank is not None and (legit_rank is None or false_rank < legit_rank):
        return {"kind": "false", "text": answers.with_text if mode else answers.without_text}
    return {"kind": "clean", "text": answers.clean_text}


def mini_graph_state(content: AttackContent, step: str, trap_active: bool) -> dict[str, Any]:
    """The automaton of the illustrative graph, from the step asked and whether the document
    is in the corpus. `start` -> `inject` -> `remove` -> `rebuild`: the false relation comes
    with the document, stays when the document is removed (the graph is not rebuilt), and goes
    only at the rebuild. A step the document's state does not allow is refused with a message
    and the graph stays as it was."""
    message: str | None = None
    effective = step
    present, stale = False, False
    if step == "inject":
        if trap_active:
            present = True
        else:
            effective, message = "start", "inject_needs_document"
    elif step == "remove":
        if trap_active:
            effective, message, present = "inject", "remove_needs_uncheck", True
        else:
            present, stale = True, True
    elif step == "rebuild":
        if trap_active:
            effective, message, present = "inject", "rebuild_document_still_there", True
        else:
            present = False
    texts = content.texts["graph"]
    graph = content.graph
    return {
        "step": step,
        "effective_step": effective,
        "document_in_corpus": trap_active,
        "false_relation_present": present,
        "stale": stale,
        "message_text": texts["messages"][message] if message else None,
        "state_text": texts["state"][effective],
        "entities": [e.model_dump() for e in graph.entities],
        "relations": [r.model_dump() for r in graph.relations if present or not r.is_false],
        "summary_text": graph.summaries.poisoned_text if present else graph.summaries.clean_text,
    }


def run(
    request: AttackRequest,
    lang: str,
    factory: Callable[[], Classifier],
) -> dict[str, Any]:
    """The two columns of the target question for one scenario, recomputed. Nothing is loaded
    nor written: `factory` is the classifier the session already has, or `NotLoaded`."""
    content = load_attack(lang)
    texts = content.texts
    scenario = content.scenario(request.scenario)
    assert scenario is not None  # noqa: S101 - the request's literal is the list
    ranked, trap_chunks = rank_corpus(content, lang, request.trap_active)
    documents = len({p["doc_id"] for p in ranked})
    body: dict[str, Any] = {
        "scenario": request.scenario,
        "trap_active": request.trap_active,
        "guardrails": request.guardrails,
        "mode": request.mode,
        "question": {"id": content.question_id, "text": _question_text(content, lang)},
        "corpus": {
            "documents": documents,
            "passages": len(ranked),
            "trap_passages": trap_chunks,
            "max_chars": content.chunk_max_chars,
            "k": content.top_k,
        },
        "role_ranks": role_ranks(ranked),
        "provenance": _provenance_dict(scenario.provenance, texts),
        "without": None,
        "with": None,
        "graph": None,
    }
    if request.scenario == "graph":
        body["graph"] = mini_graph_state(content, request.graph_step, request.trap_active)
        return body
    top = ranked[: content.top_k]
    body["without"] = {
        "passages": top,
        "answer": _answer(scenario, top, None),
    }
    if request.guardrails:
        verdicts = check_passages(top, factory, request.mode)
        checked = [
            _checked(p, v, request.mode, content, texts) for p, v in zip(top, verdicts, strict=True)
        ]
        context = [p for p in checked if p["outcome"] != "removed"]
        answer = _answer(scenario, context, request.mode)
        body["with"] = {
            "passages": checked,
            "context": [_public(p) | {"outcome": p["outcome"]} for p in context],
            "answer": answer,
            "limit_text": texts["poisoning"]["limit_text"] if scenario.id == "poisoning" else None,
        }
    return body


# ---------- the card's page and the replayed cases ----------


def listing(lang: str, guard: dict[str, Any]) -> dict[str, Any]:
    """`GET /api/rag_lab/attack`: the texts, the scenarios with their provenance, the default
    state (the trap inactive) and the guardrail's availability, as the session says it."""
    content = load_attack(lang)
    texts = content.texts
    trap_title = next(
        d.title_text for d in load_rag_content(lang).documents if d.id == content.doc_id
    )
    return {
        "lang": config.as_language(lang),
        "texts": texts,
        "question": {"id": content.question_id, "text": _question_text(content, lang)},
        "doc": {"id": content.doc_id, "title_text": trap_title},
        "chunk_max_chars": content.chunk_max_chars,
        "top_k": content.top_k,
        "scenarios": [
            {
                "id": s.id,
                "title_text": s.title_text,
                "explain_text": s.explain_text,
                "provenance": _provenance_dict(s.provenance, texts),
            }
            for s in content.scenarios
        ],
        "defaults": AttackRequest(scenario="injection").model_dump(),
        "graph_steps": list(GRAPH_STEPS),
        "guard": guard,
    }


def replay(scenario_id: str, lang: str) -> dict[str, Any] | None:
    """`GET .../cases/{id}`: the recorded case of a scenario, as written (answers, provenance),
    without any computation. `None`: unknown scenario."""
    content = load_attack(lang)
    scenario = content.scenario(scenario_id)
    if scenario is None:
        return None
    texts = content.texts
    return {
        "id": scenario.id,
        "title_text": scenario.title_text,
        "explain_text": scenario.explain_text,
        "provenance": _provenance_dict(scenario.provenance, texts),
        "answers": scenario.answers.model_dump(exclude_none=True) if scenario.answers else None,
        "graph": {
            "summaries": content.graph.summaries.model_dump(),
            "relations": [r.model_dump() for r in content.graph.relations],
        }
        if scenario.id == "graph"
        else None,
    }
