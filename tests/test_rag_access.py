"""V1.2 story 18 (CAP-15): the « Droits d'accès » card of the Attack tab.

No model, no network. The ranks, the leaks and the numbers returned are written by hand,
measured at the spec's checkpoint on the real corpus (`q_global_rh`, k = 3).
"""

from __future__ import annotations

import ast
import re

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_bricks import HEADERS

from wavestack import config
from wavestack.rag import access
from wavestack.rag.corpus import load_rag_content, load_rag_questions
from wavestack.session.app_session import AppSession
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.web.app import create_app

LANGS = ("fr", "en", "de")
AVERAGE = re.compile(r"\b(mean|average|avg|mrr|recall_at_k|aggregates?)\b", re.IGNORECASE)
# lang: (read before the filter, leaked, number returned, read in mode before)
AFTER = {
    "fr": (["formation_securite", "entretiens_annuels", "grille_remunerations"], 1),
    "en": (["formation_securite", "entretiens_annuels", "grille_remunerations"], 1),
    "de": (["prestataires", "entretiens_annuels", "deplacements"], 2),
}
LEAKED = {
    "fr": ["entretiens_annuels", "grille_remunerations"],
    "en": ["entretiens_annuels", "grille_remunerations"],
    "de": ["entretiens_annuels"],
}
BEFORE = {
    "fr": ["formation_securite", "ia_generative", "teletravail"],
    "en": ["formation_securite", "ia_generative", "teletravail"],
    "de": ["prestataires", "deplacements", "registre_sous_traitants"],
}


@pytest.fixture(autouse=True)
def _fresh_content_caches():
    config.clear_content_caches()
    yield
    config.clear_content_caches()


def make_session(lang: str = "fr") -> AppSession:
    session = AppSession(config.Config(values={"language": lang}))

    def boom(*args, **kwargs):
        raise AssertionError("a model was opened")

    session._engine_factory = boom  # type: ignore[assignment]
    session._embedder_factory = boom  # type: ignore[assignment]
    session._reranker_factory = boom  # type: ignore[assignment]
    return session


def ask(session: AppSession, **fields):
    return session.rag_lab_access(access.AccessRequest(**fields))


def docs(passages: list[dict]) -> list[str]:
    return [p["doc_id"] for p in passages]


@pytest.mark.parametrize("lang", LANGS)
def test_all_after_the_search_leaks_what_the_pipeline_read(lang):
    body = ask(make_session(lang), profile="all", mode="after")
    read, count = AFTER[lang]
    assert docs(body["seen_before_filter"]) == read
    assert docs(body["leaked"]) == LEAKED[lang]
    assert [p["rank"] for p in body["leaked"]] == ([2, 3] if lang != "de" else [2])
    assert body["returned_count"] == count < body["k"] == 3
    assert not set(docs(body["returned"])) & set(LEAKED[lang])
    assert body["shortfall"] and "trahit" in (body["shortfall_text"] or "") or lang != "fr"
    assert all(p["kept"] is False for p in body["leaked"])
    assert body["leaked"] and body["note_text"]


@pytest.mark.parametrize("lang", LANGS)
def test_the_constructed_rewriting_cites_a_leaked_document(lang):
    body = ask(make_session(lang), profile="all", mode="after")
    titles = {d.id: d.title_text for d in load_rag_content(lang).documents}
    leaked_titles = [titles[d] for d in docs(body["leaked"])]
    assert any(title in body["rewrite"]["text"] for title in leaked_titles)
    assert "entretiens_annuels" in docs(body["leaked"])
    assert (
        next(p for p in body["seen_before_filter"] if p["doc_id"] == "entretiens_annuels")["rank"]
        == 2
    )
    assert body["rewrite"]["provenance"]["kind"] == "constructed"


@pytest.mark.parametrize("lang", LANGS)
def test_all_before_the_search_never_reads_an_hr_passage(lang):
    body = ask(make_session(lang), profile="all", mode="before")
    assert docs(body["seen_before_filter"]) == BEFORE[lang]
    assert body["leaked"] == [] and body["rewrite"] is None
    assert body["returned_count"] == body["k"] == 3 and not body["shortfall"]
    assert body["seen_before_filter"] == [{**p} for p in body["seen_before_filter"]]
    assert {p["audience"] for p in body["seen_before_filter"]} == {"all"}
    assert docs(body["returned"]) == docs(body["seen_before_filter"])


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("mode", ("after", "before"))
def test_hr_is_an_authorization_not_a_leak(lang, mode):
    body = ask(make_session(lang), profile="hr", mode=mode)
    assert body["leaked"] == [] and body["rewrite"] is None
    assert body["returned_count"] == 3
    assert "entretiens_annuels" in docs(body["returned"])
    assert any(p["audience"] == "hr" for p in body["returned"])


@pytest.mark.parametrize("lang", LANGS)
def test_before_the_search_never_reads_an_hr_passage_for_any_question(lang):
    content = access.load_access(lang)
    original = access._question_text
    try:
        for question in load_rag_questions(lang):
            access._question_text = lambda c, lg, q=question: q.question_text  # type: ignore[assignment]
            body = access.run(access.AccessRequest(profile="all", mode="before"), lang)
            assert not [p for p in body["seen_before_filter"] if p["audience"] == "hr"], question.id
            assert body["leaked"] == []
    finally:
        access._question_text = original
    assert content.top_k == 3


def test_the_shipped_corpus_is_untouched_and_no_trap_or_sentinel_is_read():
    session = make_session()
    before = (config.repo_root() / "content" / "rag.yaml").read_bytes()
    body = ask(session, profile="all", mode="after")
    assert (config.repo_root() / "content" / "rag.yaml").read_bytes() == before
    read = {p["doc_id"] for p in body["seen_before_filter"]}
    assert not read & {"projet_talvane", "faq_mots_de_passe"}
    active = [d for d in load_rag_content("fr").documents if d.active]
    assert body["corpus"]["documents"] == len(active)


# ---------- the data ----------


def load(lang: str) -> dict:
    return yaml.safe_load(config.content_file(access.FILE, lang).read_text(encoding="utf-8"))


def holes(value):
    if isinstance(value, dict):
        return {k: holes(v) for k, v in value.items()}
    if isinstance(value, list):
        return [holes(v) for v in value]
    return sorted(re.findall(r"\{(\w+)\}", str(value)))


@pytest.mark.parametrize("lang", ("en", "de"))
def test_the_three_languages_mirror_each_other(lang):
    fr, tr = load("fr"), load(lang)
    assert holes(tr["texts"]) == holes(fr["texts"])
    for key in ("chunk_max_chars", "top_k", "question_id"):
        assert tr[key] == fr[key]
    assert tr["rewrite"]["doc_id"] == fr["rewrite"]["doc_id"]
    assert tr["rewrite"]["provenance"]["kind"] == fr["rewrite"]["provenance"]["kind"]
    assert tr["texts"]["title_text"] != fr["texts"]["title_text"]


def test_invalid_data_is_refused_at_the_load():
    data = load("fr")
    bad = {**data, "rewrite": {**data["rewrite"], "text": "sans titre"}}
    with pytest.raises(ValidationError):
        access.AccessContent.model_validate(bad)
    with pytest.raises(ValidationError):
        access.AccessContent.model_validate({**data, "unknown": 1})
    notes = {k: v for k, v in data["texts"]["notes"].items() if k != "leak_text"}
    with pytest.raises(ValidationError, match="notes.leak_text"):
        access.AccessContent.model_validate({**data, "texts": {**data["texts"], "notes": notes}})


def test_an_unknown_question_is_refused_at_the_load(tmp_path, monkeypatch):
    data = load("fr")
    data["question_id"] = "q_absente"
    path = tmp_path / access.FILE
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(config, "content_file", lambda name, lang=None: path)
    with pytest.raises(ValueError, match="q_absente"):
        access.load_access("fr")


def test_the_module_imports_only_the_permitted_names():
    tree = ast.parse((config.repo_root() / "src/wavestack/rag/access.py").read_text("utf-8"))
    found = {
        (node.module, alias.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("wavestack")
        for alias in node.names
    }
    assert found == {
        ("wavestack", "config"),
        ("wavestack.rag.attack", "Provenance"),
        ("wavestack.rag.attack", "provenance_text"),
        ("wavestack.rag.corpus", "Chunk"),
        ("wavestack.rag.corpus", "chunk_corpus"),
        ("wavestack.rag.corpus", "load_rag_content"),
        ("wavestack.rag.corpus", "load_rag_questions"),
        ("wavestack.rag.index", "passage_text"),
        ("wavestack.rag.lab", "bm25"),
    }


# ---------- the endpoints ----------


def client_for(session: AppSession) -> TestClient:
    app = create_app(
        DiagnosticSession(session.cfg, port=8421), port=8421, version="t", app_session=session
    )
    return TestClient(app, base_url="http://127.0.0.1:8421")


def keys_of(node) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in keys_of(v)}
    if isinstance(node, list):
        return {k for v in node for k in keys_of(v)}
    return set()


def test_endpoints_shapes_and_422():
    client = client_for(make_session())
    got = client.get("/api/rag_lab/access")
    assert got.status_code == 200
    body = got.json()
    assert body["defaults"] == {"profile": "all", "mode": "after"}
    assert body["question"]["id"] == "q_global_rh" and "seen_before_filter" not in body
    posted = client.post(
        "/api/rag_lab/access", headers=HEADERS, json={"profile": "all", "mode": "after"}
    )
    assert posted.status_code == 200
    answer = posted.json()
    assert set(answer) >= {"seen_before_filter", "returned", "leaked", "returned_count", "rewrite"}
    for wrong in ({"extra": 1}, {"profile": "boss"}, {"mode": "during"}, {"profile": None}):
        assert client.post("/api/rag_lab/access", json=wrong, headers=HEADERS).status_code == 422, (
            wrong
        )
    for shown in (body, answer):
        assert not [k for k in keys_of(shown) if AVERAGE.search(k)]


def test_the_page_script_has_no_colour_and_no_inner_html():
    code = (config.repo_root() / "src/wavestack/web/static/rag-attack-access.js").read_text("utf-8")
    assert "innerHTML" not in code and "insertAdjacentHTML" not in code
    assert 'registerTab("attack_access"' in code and 'registerTab("attack"' not in code
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(", code)
