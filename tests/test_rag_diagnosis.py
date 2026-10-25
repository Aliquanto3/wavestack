"""V1.2 story 9 (CAP-10): the rank of the expected passage at each stage, the stage at fault,
and the three recorded failure cases of « Où naît l'erreur », replayed without the model.

Real code throughout: the rules read real chunks of the corpus; the live test runs the
workshop's real chain (fake embedder and reranker at the boundary) and asks the endpoint.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_bricks import HEADERS
from test_rag import build
from test_rag_lab import _client, ready, run

from wavestack import config
from wavestack.rag import diagnosis
from wavestack.rag.corpus import (
    Chunk,
    RagPassage,
    RagQuestion,
    chunk_corpus,
    load_rag_content,
    load_rag_questions,
)
from wavestack.rag.diagnosis import Listed, StageList, diagnose_passage

LANGS = ("fr", "en", "de")
STATIC = Path(__file__).resolve().parent.parent / "src" / "wavestack" / "web" / "static"
PASSAGE = RagPassage(doc_id="d", anchor_text="la règle  trois\nest simple")


@pytest.fixture(autouse=True)
def _fresh_content_caches():
    config.clear_content_caches()
    yield
    config.clear_content_caches()


@pytest.fixture
def index(tmp_path: Path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


def listed(*texts: str | None, doc: str = "d") -> list[Listed]:
    """A ranked list: `None` is the passage, a text another excerpt of the same document."""
    return [Listed(doc, PASSAGE.anchor_text if t is None else t) for t in texts]


def verdict(stages: list[StageList], *, whole: bool = True, **kw) -> dict:
    chunks = [Chunk("d", "D", 1, PASSAGE.anchor_text if whole else "autre chose")]
    return diagnose_passage(PASSAGE, chunks, stages, **kw)


def fault_of(result: dict) -> tuple[str, str] | None:
    return (result["fault"]["kind"], result["fault"]["reason"]) if result["fault"] else None


def ranks(result: dict) -> dict[str, int | None]:
    return {s["kind"]: s["rank"] for s in result["steps"] if s["kind"] != "chunking"}


# ---------- the rules ----------


def test_a_passage_whole_and_on_top_has_no_fault():
    stages = [
        StageList("vector_search", listed(None, "x", "y")),
        StageList("rerank", listed(None, "x", "y")),
        StageList("context", listed(None, "x", "y")),
    ]
    result = verdict(stages)
    assert fault_of(result) is None and result["rescued_by"] is None
    assert ranks(result) == {"vector_search": 1, "rerank": 1, "context": 1}


def test_the_anchor_is_found_across_spaces_and_case():
    # Looked for folded: a line break or a capital does not hide the passage.
    item = Listed("d", "La RÈGLE trois est simple, dit le texte.")
    assert (
        diagnosis.rank_in([item], RagPassage(doc_id="d", anchor_text="la règle  trois\nest simple"))
        == 1
    )
    assert (
        diagnosis.rank_in([item], RagPassage(doc_id="other", anchor_text="la règle trois")) is None
    )


def test_a_cut_anchor_is_not_indexed_and_the_chunking_is_the_first_fault():
    result = verdict([StageList("vector_search", listed("x", "y"))], whole=False)
    assert fault_of(result) == ("chunking", "not_indexed")
    assert result["steps"][0] == {"kind": "chunking", "intact": False, "rank": None, "of": None}


def test_a_passage_retrieved_whole_is_indexed_whatever_the_shipped_cut():
    # The list holds a chunk the chain indexed (a working copy, another cut): no chunking fault.
    result = verdict([StageList("vector_search", listed(None, "x"))], whole=False)
    assert fault_of(result) is None and result["steps"][0]["intact"] is True


def test_empty_lists_and_no_list_at_all_are_missing():
    empty = [StageList("vector_search", []), StageList("context", [])]
    assert fault_of(verdict(empty)) == ("vector_search", "missing")
    assert fault_of(verdict([])) == ("context", "missing")


def test_a_budget_up_to_the_labs_bound_is_accepted():
    assert (
        diagnosis.LiveRequest(question_id="q", chunk_max_chars=700, top_k=20, stages=[]).top_k == 20
    )


def test_absent_from_every_search_list_is_missing_at_the_first_search():
    stages = [
        StageList("vector_search", listed("x", "y")),
        StageList("lexical_search", listed("y", "x")),
    ]
    assert fault_of(verdict(stages)) == ("vector_search", "missing")


def test_found_by_one_search_only_is_no_fault():
    stages = [
        StageList("vector_search", listed("x", "y")),
        StageList("lexical_search", listed("x", None)),
        StageList("fusion", listed("x", None, "y")),
    ]
    assert fault_of(verdict(stages)) is None


def test_ranked_beyond_the_budget_then_rescued_by_the_reranking():
    stages = [
        StageList("vector_search", listed("a", "b", "c", "d", None)),
        StageList("rerank", listed(None, "a", "b", "c", "d")),
        StageList("context", listed(None, "a", "b")),
    ]
    result = verdict(stages)
    assert fault_of(result) == ("vector_search", "ranked_low")
    assert result["rescued_by"] == "rerank" and ranks(result)["vector_search"] == 5


def test_a_fall_of_more_than_the_tolerance_blames_the_step_that_dropped_it():
    stages = [
        StageList("vector_search", listed(None, "a", "b")),
        StageList("rerank", listed("a", "b", "c", "d", None)),
        StageList("context", listed("a", "b", "c")),
    ]
    assert fault_of(verdict(stages)) == ("rerank", "fell")
    # The tolerance is the caller's: with 4, the same fall is no fault of the reranking.
    assert fault_of(verdict(stages, tolerance=4)) == ("context", "cut")


def test_absent_from_the_reranked_list_is_missing_there():
    stages = [
        StageList("vector_search", listed(None, "a")),
        StageList("rerank", listed("a", "b")),
        StageList("context", listed("a", "b")),
    ]
    assert fault_of(verdict(stages)) == ("rerank", "missing")


def test_in_the_list_but_beyond_the_budget_is_cut_by_the_context():
    stages = [
        StageList("vector_search", listed("a", "b", None, "c")),
        StageList("rerank", listed("a", "b", "c", None)),
        StageList("context", listed("a", "b", "c")),
    ]
    result = verdict(stages)
    assert fault_of(result) == ("context", "cut") and result["rescued_by"] is None


def test_the_budget_is_the_callers():
    stages = [
        StageList("vector_search", listed("a", "b", "c", None)),
        StageList("context", listed("a", "b", "c", None)),
    ]
    assert fault_of(verdict(stages, budget=3)) == ("vector_search", "ranked_low")
    assert fault_of(verdict(stages, budget=4)) is None


def test_a_passage_in_the_middle_of_the_context_is_only_noted():
    stages = [StageList("context", listed("a", None, "b"))]
    result = verdict(stages)
    assert fault_of(result) is None and result["note"] == "middle"
    assert verdict([StageList("context", listed(None, "a", "b"))])["note"] is None
    assert verdict([StageList("context", listed("a", None))])["note"] is None


# ---------- the questions ----------


@pytest.mark.parametrize("lang", LANGS)
def test_a_question_without_expected_passage_has_no_diagnosis(lang):
    no_answer = next(q for q in load_rag_questions(lang) if q.type == "no_answer")
    assert diagnosis.diagnose(no_answer, [], [])["passages"] == []


def test_a_question_with_two_passages_has_one_verdict_each():
    question = next(q for q in load_rag_questions("fr") if len(q.expected_passages) == 2)
    chunks = chunk_corpus(load_rag_content("fr"), 700, "fr")
    first = next(
        c
        for c in chunks
        if diagnosis.holds(Listed(c.doc_id, c.text), question.expected_passages[0])
    )
    stages = [StageList("rerank", [Listed(first.doc_id, first.text)])]
    result = diagnosis.diagnose(question, chunks, stages)
    assert [fault_of(p) for p in result["passages"]] == [None, ("rerank", "missing")]


def test_there_is_no_average_anywhere_in_the_result():
    stages = [StageList("rerank", listed(None))]
    flat = repr(verdict(stages)).lower()
    assert not any(word in flat for word in ("mean", "average", "mrr", "avg"))
    question = RagQuestion(
        id="q_x",
        type="factual",
        question_text="?",
        expected_answer_text="!",
        expected_passages=[PASSAGE],
    )
    assert set(diagnosis.diagnose(question, [], [])) == {
        "question_id",
        "question_text",
        "budget",
        "tolerance",
        "passages",
    }


# ---------- the recorded failure cases ----------


@pytest.mark.parametrize("lang", LANGS)
def test_each_recorded_case_is_born_at_its_own_stage_in_every_language(lang):
    content = diagnosis.load_diagnosis(lang)
    born = []
    for case in content.cases:
        result = diagnosis.replay(case.id, lang)
        first = result["passages"][0]
        assert f"{first['fault']['kind']}:{first['fault']['reason']}" == case.expected_fault
        born.append(first["fault"]["kind"])
    assert len(content.cases) == 3 and len(set(born)) == 3


def test_the_ranked_low_case_is_rescued_and_the_cut_case_is_not():
    low = diagnosis.replay("ranked_low")["passages"][0]
    assert low["rescued_by"] == "rerank"
    assert ranks(low) == {"vector_search": 6, "rerank": 1, "context": 1}
    cut = diagnosis.replay("cut_by_budget")["passages"][0]
    assert cut["rescued_by"] is None
    assert ranks(cut) == {"vector_search": 3, "rerank": 4, "context": None}
    gone = diagnosis.replay("not_indexed")["passages"][0]
    assert gone["steps"][0]["intact"] is False


def test_the_replay_hands_back_the_lists_it_read_and_an_unknown_case_is_none():
    result = diagnosis.replay("ranked_low")
    assert result["recorded"] is True and result["case_id"] == "ranked_low"
    assert [s["kind"] for s in result["stages"]] == ["vector_search", "rerank", "context"]
    assert len(result["stages"][0]["items"]) == 8
    assert diagnosis.replay("nope") is None


@pytest.mark.parametrize("lang", LANGS)
def test_the_overlays_keep_the_same_cases_and_references(lang):
    french, other = diagnosis.load_diagnosis("fr"), diagnosis.load_diagnosis(lang)

    def shape(content):
        return [
            (c.id, c.question_id, c.chunk_max_chars, c.top_k, c.expected_fault, c.stages)
            for c in content.cases
        ]

    assert shape(other) == shape(french)
    assert diagnosis.listing(lang)["texts"]["stages"]["context_text"]


def test_the_recorded_cases_name_prepared_questions_with_an_expected_passage():
    questions = {q.id: q for q in load_rag_questions("fr")}
    for case in diagnosis.load_diagnosis("fr").cases:
        assert questions[case.question_id].expected_passages, case.id


# ---------- the endpoints ----------


def test_the_endpoints_hand_the_texts_and_replay_a_case_without_a_model(index):
    session, _ = ready(index)
    client = _client(session)
    listing = client.get("/api/rag_lab/diagnosis").json()
    assert [c["id"] for c in listing["cases"]] == ["not_indexed", "ranked_low", "cut_by_budget"]
    assert listing["texts"]["replay_badge_text"] and listing["cases"][0]["question_text"]
    played = client.get("/api/rag_lab/diagnosis/cases/cut_by_budget")
    assert played.status_code == 200 and played.json()["passages"][0]["fault"]["kind"] == "context"
    assert client.get("/api/rag_lab/diagnosis/cases/nope").status_code == 404
    assert session.state == "idle"  # nothing was run, no model loaded


def test_a_finished_run_is_diagnosed_from_the_lists_the_page_holds(index):
    session, _ = ready(index)
    question = next(q for q in load_rag_questions("fr") if q.id == "q_fact_pwd")
    events = run(session, question.question_text)
    lists = [
        {
            "kind": e.payload["kind"],
            "items": [{"doc_id": i["doc_id"], "text": i["text"]} for i in e.payload["items"]],
        }
        for e in events
        if e.kind == "rag_lab_stage_ended" and e.payload["items"]
    ]
    body = {"question_id": "q_fact_pwd", "chunk_max_chars": 700, "top_k": 3, "stages": lists}
    client = _client(session)
    got = client.post("/api/rag_lab/diagnosis", json=body, headers=HEADERS).json()
    steps = got["passages"][0]["steps"]
    assert [s["kind"] for s in steps] == ["chunking", "vector_search", "rerank", "context"]
    expected = question.expected_passages[0]
    for stage in lists:
        step = next(s for s in steps if s["kind"] == stage["kind"])
        want = next(
            (n for n, i in enumerate(stage["items"], 1) if diagnosis.holds(Listed(**i), expected)),
            None,
        )
        assert step["rank"] == want
    url = "/api/rag_lab/diagnosis"
    assert client.post(url, json=body | {"question_id": "free"}, headers=HEADERS).status_code == 404
    assert client.post(url, json=body | {"chunk_max_chars": 5}, headers=HEADERS).status_code == 422


def test_the_page_section_and_file_are_wired():
    html = (STATIC / "rag.html").read_text(encoding="utf-8")
    script = '<script type="module" src="/static/rag-diagnosis.js"></script>'
    assert html.index(script) > html.index('src="/static/rag.js"')
    for element in ("rag-diag", "rag-diag-run", "rag-cases", "rag-case"):
        assert f'id="{element}"' in html
    source = (STATIC / "rag-diagnosis.js").read_text(encoding="utf-8")
    assert 'registerTab("diagnosis"' in source
