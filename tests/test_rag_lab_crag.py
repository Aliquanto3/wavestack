"""V1.2 story 12 (CAP-7): Corrective RAG in the RAG workshop, the `crag` preset.

Hybrid RAG, System One's passage filter (the brick's reranker, story 8), then the fallback: when
the filter kept nothing, the active model rewrites the question, the searches and the filter run
once more; still nothing, or `abstain`, or no model: the workshop answers « je ne sais pas »
itself, no generation, no web. The models are fakes: the reranker of the tests (one whose first
scoring rejects everything stands for a first search gone wrong), `FakeEngine` for the rewrite.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_reranker import FakeReranker
from test_rag import build
from test_rag_lab import QUESTION, ended, run, run_status, stage
from test_rag_lab_decision import ready
from test_rag_lab_no_index import lab

from wavestack.models.reranker import RerankScore
from wavestack.rag import exposed
from wavestack.rag import lab as rag_lab

LANGS = ("fr", "en", "de")


@pytest.fixture
def index(tmp_path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


def crag(session, *, option: str = "retry") -> rag_lab.Pipeline:  # noqa: ANN001
    """The preset on its own index (chunks of 300 characters, the memory store), as the other
    workshop tests run the shipped chain."""
    chain = session._rag_lab_catalog(rag_lab.load_lab_content()).preset_pipeline("crag")
    stage(chain, "chunking").params["chunk_max_chars"] = 300
    stage(chain, "vector_store").option = "memory"
    stage(chain, "fallback").option = option
    return chain


class Scripted(FakeReranker):
    """Each scoring gives every passage the next score of `scores` (shared by the instances the
    session opens): `[0.0, 1.0]`, the first search gone wrong and the second right."""

    def __init__(self, scores: list[float], **kwargs) -> None:  # noqa: ANN003
        super().__init__(**kwargs)
        self.scores = scores

    def score(self, query, passages, cancelled=None, progress=None):  # noqa: ANN001, ANN201
        found = super().score(query, passages, cancelled, progress)
        value = self.scores.pop(0) if len(self.scores) > 1 else self.scores[0]
        return [RerankScore(value, s.truncated) for s in found]


def scripted(session, *scores: float) -> None:  # noqa: ANN001
    shared = list(scores)
    session._reranker_factory = lambda model: Scripted(shared, model_id=model.id)


def facts(payload: dict) -> dict:
    return {f["label_text"]: f["value_text"] for f in payload["facts"]}


# ---------- criterion 1: the preset, its family, its exposure ----------


def test_the_preset_is_hybrid_then_the_filter_then_the_fallback(index):
    session, _ = ready(index)
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    chain = catalog.preset_pipeline("crag")
    segment = [(s.kind, s.option) for s in chain.stages[3:-2]]
    assert segment == [
        ("vector_search", "cosine"),
        ("lexical_search", "bm25"),
        ("fusion", "rrf"),
        ("passage_filter", "local"),
        ("fallback", "retry"),
    ]
    assert rag_lab.check_pipeline(chain, catalog) is None
    assert rag_lab.PRESET_FAMILIES["search"][-1] == "crag"
    shown = {p["id"]: p for p in session.rag_lab_state()["catalog"]["presets"]}
    assert shown["crag"]["family"] == "search" and shown["crag"]["available"]
    refused = exposed.refusal(chain, catalog, 700, exposed.load_texts("fr"))
    assert refused is not None and refused.reason == "model_stage"
    kinds = {s["kind"]: s for s in catalog.payload()["stages"]}
    assert kinds["fallback"]["insert_after"] == "passage_filter" and kinds["fallback"]["movable"]
    session.close()


@pytest.mark.parametrize(
    ("lang", "said"),
    [("fr", "Corrective fallback"), ("en", "passage filter"), ("de", "Passagenfilter")],
)
def test_the_fallback_needs_a_filter_before_it(index, lang, said):
    session, _ = ready(index)
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content(lang))
    chain = catalog.preset_pipeline("hybrid")
    at = next(i for i, s in enumerate(chain.stages) if s.kind == "context")
    chain.stages.insert(at, rag_lab.Stage(id="f1", kind="fallback", option="retry"))
    reason, where = rag_lab.check_pipeline(chain, catalog, lang=lang)
    assert where == "f1" and said in reason
    misplaced = catalog.preset_pipeline("crag")
    stages = misplaced.stages
    i, j = (
        next(k for k, s in enumerate(stages) if s.kind == kind)
        for kind in ("passage_filter", "fallback")
    )
    stages[i], stages[j] = stages[j], stages[i]
    assert rag_lab.check_pipeline(misplaced, catalog, lang=lang)[1] == stages[i].id
    session.close()


# ---------- criterion 7: correct, then retry, then « je ne sais pas » ----------


def test_passages_kept_need_no_fallback(index):
    session, _ = ready(index, judge="Réponse.")
    events = run(session, QUESTION, crag(session))
    assert run_status(events) == "ok"
    fallback = ended(events, "fallback")
    assert fallback["status"] == "ok" and fallback["fallback"]["verdict"] == "correct"
    assert fallback["items"] and not fallback["fallback"]["abstained"]
    assert ended(events, "generation")["output_text"] == "Réponse."
    session.close()


def test_nothing_kept_rewrites_once_then_answers_it_does_not_know(index):
    session, _ = ready(index, judge="télétravail jours semaine")
    scripted(session, 0.0)
    fake = session._engine
    events = run(session, QUESTION, crag(session))
    assert ended(events, "passage_filter")["items"] == []
    fallback = ended(events, "fallback")
    payload = fallback["fallback"]
    assert payload["verdict"] == "incorrect" and payload["abstained"] and not payload["web"]
    assert payload["rewritten"] and fallback["queries"] == [payload["rewritten"]]
    assert payload["kept_after"] == 0
    kinds = [c["kind"] for c in fallback["costs"]]
    assert kinds[0] == "query" and "passage_filter" in kinds and "vector_search" in kinds
    assert len(fake.calls) == 1  # the rewrite only: no generation
    generation = ended(events, "generation")
    assert generation["status"] == "ok" and "Je ne sais pas" in generation["output_text"]
    assert all(c["tokens"] == 0 for c in generation["costs"])
    assert ended(events, "context")["items"] == []
    session.close()


def test_a_second_attempt_that_keeps_passages_feeds_the_context(index):
    session, _ = ready(index, judge="Réponse.")
    scripted(session, 0.0, 1.0)
    events = run(session, QUESTION, crag(session))
    fallback = ended(events, "fallback")
    assert fallback["fallback"]["verdict"] == "corrected" and fallback["items"]
    assert fallback["fallback"]["kept_after"] == len(fallback["items"])
    context = ended(events, "context")
    assert {i["chunk_id"] for i in context["items"]} <= {i["chunk_id"] for i in fallback["items"]}
    assert ended(events, "generation")["output_text"] == "Réponse."
    session.close()


def test_abstain_answers_without_any_model_call(index):
    session, _ = ready(index, judge="x")
    scripted(session, 0.0)
    fake = session._engine
    events = run(session, QUESTION, crag(session, option="abstain"))
    fallback = ended(events, "fallback")
    assert fallback["fallback"]["abstained"] and fallback["fallback"]["rewritten"] is None
    assert len(fake.calls) == 0
    assert "Je ne sais pas" in ended(events, "generation")["output_text"]
    session.close()


def test_without_a_model_the_fallback_does_not_rewrite_and_abstains(index):
    bare = lab(index, model=None, small=False)
    state = bare._rag_lab_catalog(rag_lab.load_lab_content()).options[("fallback", "retry")]
    assert state.available and state.note_text is not None
    bare.close()
    session, _ = ready(index)
    scripted(session, 0.0)
    session._engine = None
    events = run(session, QUESTION, crag(session))
    fallback = ended(events, "fallback")
    assert fallback["fallback"]["abstained"] and fallback["warning_text"]
    assert "Je ne sais pas" in ended(events, "generation")["output_text"]
    session.close()


def test_a_fallback_after_a_filter_that_did_not_run_is_skipped(index):
    session, _ = ready(index)
    session._reranker_factory = lambda model: FakeReranker(model_id=model.id, fail=True)
    events = run(session, QUESTION, crag(session))
    assert ended(events, "passage_filter")["status"] == "error"
    assert ended(events, "fallback")["status"] == "skipped"
    session.close()


@pytest.mark.parametrize("lang", LANGS)
def test_the_sheets_and_texts_in_each_language(lang):
    content = rag_lab.load_lab_content(lang)
    for key in ("fallback.retry", "fallback.abstain"):
        sheet = content.sheets[key]
        assert any(s.url == "https://arxiv.org/abs/2401.15884" for s in sheet.sources)
    assert content.presets["crag"].explain_text and content.stages["fallback"].explain_text
    if lang != "fr":
        assert "«" not in content.options["fallback"]["retry"].label_text
