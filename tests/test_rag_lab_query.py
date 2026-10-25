"""V1.2 story 5 (CAP-3, CAP-17): the query understanding of the document search workshop.

The options `rewrite`, `decompose`, `follow_up` and `hyde` ask the workshop's active model for
the queries to search. The model is `FakeEngine` (scripted outputs, one per call); the
embedding and the reranking are the suite's fakes. Nothing touches the network.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_engine import FakeEngine
from test_rag import build, place_model
from test_rag_lab import QUESTION, ended, run, run_status, stage
from test_rag_lab_generation import own_chain
from test_rag_rerank import place_reranker, rerank_config, session_for

from wavestack.rag import lab as rag_lab

HOPS = "Combien de jours de télétravail ?\n- Quel est le délai de préavis ?\n"
ANSWER = "Quatorze caractères."


@pytest.fixture
def index(tmp_path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


def ready(index: Path, *outputs: str):
    """A booted session whose model says `outputs` in turn (the last one repeated)."""
    place_model()
    place_reranker()
    engine = FakeEngine(outputs=list(outputs), output=ANSWER)
    session, _ = session_for(rerank_config(index), rerank=False, bricks=(), engine=engine)
    return session


def chain_with(session, option: str, *, hybrid: bool = False) -> rag_lab.Pipeline:
    """The workshop's own chain (memory store), the query understanding after the store."""
    chain = own_chain(session)
    chain.stages.insert(3, rag_lab.Stage(id="q1", kind="query", option=option))
    if hybrid:
        position = next(i for i, s in enumerate(chain.stages) if s.kind == "vector_search")
        chain.stages[position + 1 : position + 1] = [
            rag_lab.Stage(id="b1", kind="lexical_search", option="bm25"),
            rag_lab.Stage(id="f1", kind="fusion", option="rrf"),
        ]
    return chain


# ---------- the parsing of the model's answer ----------


@pytest.mark.parametrize(
    ("option", "answer", "expected"),
    [
        (
            "rewrite",
            "  « télétravail jours par semaine »\nautre ligne",
            ["télétravail jours par semaine"],
        ),
        ("follow_up", "1. Et pour les stagiaires ?", ["Et pour les stagiaires ?"]),
        ("decompose", "- a\n2) b\n* a\n\n« c »\nd\ne", ["a", "b", "c", "d"]),
        ("hyde", "Le télétravail\n est de deux jours.", ["Le télétravail est de deux jours."]),
        ("rewrite", " \n ", []),
        ("hyde", "", []),
    ],
)
def test_the_models_answer_is_read_as_queries(option, answer, expected):
    assert rag_lab.parse_queries(option, answer) == expected


def test_a_query_is_cut_at_its_bound():
    long = "mot " * 500
    assert len(rag_lab.parse_queries("rewrite", long)[0]) <= rag_lab.QUERY_MAX_CHARS
    assert len(rag_lab.parse_queries("hyde", long)[0]) <= rag_lab.HYDE_MAX_CHARS


# ---------- the options, run with the fake model ----------


def test_decompose_searches_each_sub_question_and_shows_them(index):
    session = ready(index, HOPS, ANSWER)
    events = run(session, QUESTION, chain_with(session, "decompose"))
    assert run_status(events) == "ok"

    query = ended(events, "query")
    assert query["status"] == "ok", query["error_text"]
    assert query["queries"] == [
        "Combien de jours de télétravail ?",
        "Quel est le délai de préavis ?",
    ]
    assert query["output_text"].splitlines()[0].startswith("1. Combien")
    assert "Question : « Combien de jours" in query["input_text"]
    assert query["costs"][0]["kind"] == "query" and query["costs"][0]["phase"] == "query"
    # the prompt sent carries the task's instruction, not the brick's system prompt
    assert "sous-questions simples" in query["prompt_text"]

    search = ended(events, "vector_search")
    assert ("Requêtes cherchées", "2") in [
        (f["label_text"], f["value_text"]) for f in search["facts"]
    ]
    sources = [i["sources"] for i in search["items"]]
    assert all(len(s) == 2 for s in sources)  # where each query ranked each excerpt
    assert [i["rank"] for i in search["items"]] == list(range(1, len(sources) + 1))
    assert ended(events, "generation")["output_text"] == ANSWER


def test_rewrite_searches_the_one_rewritten_query(index):
    session = ready(index, "préavis de démission", ANSWER)
    events = run(session, QUESTION, chain_with(session, "rewrite", hybrid=True))
    assert run_status(events) == "ok"
    query = ended(events, "query")
    assert query["queries"] == ["préavis de démission"]
    assert query["output_text"] == "préavis de démission"
    lexical = ended(events, "lexical_search")  # its words are the rewritten query's, folded
    assert "preavis" in lexical["input_text"] and "teletravail" not in lexical["input_text"]
    assert lexical["items"] and ended(events, "fusion")["status"] == "ok"


def test_hyde_searches_the_hypothetical_answer_as_a_passage(index):
    session = ready(index, "Le télétravail est de deux jours par semaine.", ANSWER)
    events = run(session, QUESTION, chain_with(session, "hyde"))
    query = ended(events, "query")
    assert query["queries"] == ["Le télétravail est de deux jours par semaine."]
    assert ("Vectorisée", "comme un passage du corpus, non comme une question") in [
        (f["label_text"], f["value_text"]) for f in query["facts"]
    ]
    assert ended(events, "vector_search")["items"]


def test_follow_up_reads_the_questions_asked_before(index):
    standalone = "Combien de jours de télétravail par semaine pour les stagiaires ?"
    # the model speaks at each call: the first run's answer, then the rewriting, then the answer
    session = ready(index, ANSWER, standalone, ANSWER)
    chain = chain_with(session, "follow_up")
    first = run(session, QUESTION, chain)
    # nothing asked before: the stage is skipped, the question is searched as typed
    skipped = ended(first, "query")
    assert skipped["status"] == "skipped" and skipped["queries"] == []
    assert "Aucune question précédente" in skipped["error_text"]
    assert run_status(first) == "ok" and ended(first, "vector_search")["items"]

    second = run(session, "Et pour les stagiaires ?", chain)
    query = ended(second, "query")
    assert query["status"] == "ok", query["error_text"]
    assert QUESTION in query["input_text"]
    assert QUESTION in query["prompt_text"]
    assert query["queries"] == [standalone]


def test_a_model_that_says_nothing_leaves_the_question_as_typed(index):
    session = ready(index, " ", ANSWER)
    events = run(session, QUESTION, chain_with(session, "rewrite"))
    query = ended(events, "query")
    assert query["status"] == "ok" and query["queries"] == []
    assert "rien donné d'exploitable" in query["warning_text"]
    assert ended(events, "vector_search")["items"]
    assert run_status(events) == "ok"


def test_without_the_stage_the_searches_are_unchanged(index):
    session = ready(index, ANSWER)
    events = run(session, QUESTION, own_chain(session))
    assert all(
        e.payload.get("queries", []) == [] for e in events if e.kind == "rag_lab_stage_ended"
    )
    assert "Requêtes cherchées" not in [
        f["label_text"] for f in ended(events, "vector_search")["facts"]
    ]


# ---------- the chain's rules and the catalog ----------


def test_the_query_understanding_must_come_before_the_searches(index):
    session = ready(index, ANSWER)
    chain = chain_with(session, "rewrite")
    query = stage(chain, "query")
    chain.stages.remove(query)
    chain.stages.insert(next(i for i, s in enumerate(chain.stages) if s.kind == "context"), query)
    verdict = session.validate_rag_lab(chain)
    assert verdict["valid"] is False
    assert verdict["refusals"][0]["stage_id"] == "q1"
    assert "avant elles" in verdict["refusals"][0]["reason_text"]
    assert session.validate_rag_lab(chain_with(session, "decompose"))["valid"] is True


def test_the_catalog_offers_the_four_options_after_the_store(index):
    session = ready(index, ANSWER)
    stages = session.rag_lab_state()["catalog"]["stages"]
    assert [s["kind"] for s in stages][:4] == ["chunking", "embedding", "vector_store", "query"]
    query = next(s for s in stages if s["kind"] == "query")
    assert [o["id"] for o in query["options"]] == ["rewrite", "decompose", "follow_up", "hyde"]
    assert query["movable"] and query["insert_after"] == "vector_store"
    assert all(o["available"] for o in query["options"])


# ---------- the component sheets (CAP-17) ----------


@pytest.mark.parametrize("lang", ["fr", "en", "de"])
def test_every_option_of_a_sheeted_kind_has_a_sheet_with_a_source(lang):
    content = rag_lab.load_lab_content(lang)
    wanted = {
        f"{kind}.{option}" for kind in rag_lab.SHEETED_KINDS for option in rag_lab.OPTIONS[kind]
    }
    assert set(content.sheets) == wanted
    assert {"query.rewrite", "query.decompose", "query.follow_up", "query.hyde"} <= wanted
    for key, sheet in content.sheets.items():
        assert sheet.sources, key
        assert all(s.url.startswith("https://") for s in sheet.sources), key
        assert sheet.bench_text == "", key  # nothing published by the bench yet


def test_a_missing_sheet_is_refused():
    import yaml

    from wavestack import config

    raw = yaml.safe_load(config.content_file("rag_lab.yaml", "fr").read_text(encoding="utf-8"))
    del raw["sheets"]["query.hyde"]
    with pytest.raises(ValueError, match="sheets"):
        rag_lab.RagLabContent.model_validate(raw)
