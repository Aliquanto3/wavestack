"""V1.2 story 19 (CAP-16, CAP-17): the component and architecture sheets of the « Fiches » tab.

Declared content: no model, no index, no network (the guard of `conftest.py` stays on).
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from wavestack import config
from wavestack.mcp.policy import RISKS
from wavestack.rag import erasure, lab, sheets
from wavestack.session.app_session import AppSession
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.web.app import create_app

LANGS = ("fr", "en", "de")
CONTENT = config.repo_root() / "content"
STATIC = config.repo_root() / "src" / "wavestack" / "web" / "static"
SPEC = (
    config.repo_root()
    / "_bmad-output"
    / "specs"
    / "spec-wavestack-v1-2-atelier-recherche-documentaire"
)
LITERATURE = SPEC / "litterature.md"
AVERAGE = re.compile(r"\b(mean|average|avg|mrr|recall_at_k|aggregates?)\b", re.IGNORECASE)
GLOBAL_SCORE = {"score", "total", "overall"}
STORY_OF = {
    "long_context": 10,
    "cag": 10,
    "agentic": 11,
    "pageindex": 11,
    "raptor": 12,
    "crag": 12,
    "graphrag": 13,
    "llm_wiki": 14,
}
FORBIDDEN = {
    "fr": ["est conforme", "conforme au RGPD", "garantit la conformité", "assure la conformité"],
    "en": ["is compliant", "compliant with", "ensures compliance", "guarantees compliance"],
    "de": [
        "ist konform",
        "DSGVO-konform",
        "gewährleistet die Konformität",
        "garantiert die Konformität",
    ],
}
LEGAL = {"fr": "pas un avis juridique", "en": "not legal advice", "de": "keine rechtsberatung"}
UNMEASURED = {"fr": "Pas encore mesuré", "en": "Not measured yet", "de": "Noch nicht gemessen"}
NAME_TO_ID = {
    "dense": "dense",
    "hybride": "hybrid",
    "reranking": "rerank",
    "GraphRAG": "graphrag",
    "LLM Wiki": "llm_wiki",
    "PageIndex": "pageindex",
    "recherche agentique": "agentic",
    "Corrective RAG": "crag",
    "contexte long": "long_context",
    "CAG": "cag",
}
STATES_FR = ("non démontrée", "non étudiée", "partiellement soutenue", "soutenue", "contredite")
STATES = {
    "fr": dict(zip(STATES_FR, STATES_FR, strict=True)),
    "en": {
        "non démontrée": "not demonstrated",
        "non étudiée": "not studied",
        "partiellement soutenue": "partially supported",
        "soutenue": "supported",
        "contredite": "contradicted",
    },
    "de": {
        "non démontrée": "nicht belegt",
        "non étudiée": "nicht untersucht",
        "partiellement soutenue": "teilweise gestützt",
        "soutenue": "gestützt",
        "contredite": "widerlegt",
    },
}


@pytest.fixture(autouse=True)
def _fresh_content_caches():
    config.clear_content_caches()
    yield
    config.clear_content_caches()


def raw(lang: str) -> dict:
    path = (
        CONTENT / "rag_sheets.yaml" if lang == "fr" else CONTENT / "i18n" / lang / "rag_sheets.yaml"
    )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def literature_rows() -> dict[str, list[str]]:
    rows = {}
    for line in LITERATURE.read_text(encoding="utf-8").splitlines():
        found = re.match(r"\| (H\d+) \|", line)
        if found:
            rows[found.group(1)] = [c.strip() for c in line.strip().strip("|").split(" | ")]
    return rows


needs_literature = pytest.mark.skipif(not LITERATURE.exists(), reason="dossier de specs absent")


# ---------- exhaustiveness (criteria 1, 2, 17) ----------


def test_the_families_of_options_are_split_between_sheeted_and_pending():
    sheeted, pending = set(lab.SHEETED_KINDS), set(sheets.PENDING_SHEET_KINDS)
    assert not sheeted & pending
    missing = set(lab.OPTIONS) - sheeted - pending
    assert not missing, f"family without a sheet or a pending mark: {sorted(missing)}"
    assert sheeted | pending == set(lab.OPTIONS)
    assert sheets.missing_sheets() == []


def test_a_new_family_or_a_new_preset_fails_the_check(monkeypatch):
    monkeypatch.setitem(lab.OPTIONS, "newfamily", ("a",))
    assert any("newfamily" in p for p in sheets.missing_sheets())
    monkeypatch.delitem(lab.OPTIONS, "newfamily")
    monkeypatch.setitem(lab.PRESETS, "newpreset", (("vector_search", "cosine"),))
    assert any("newpreset" in p for p in sheets.missing_sheets())


@pytest.mark.parametrize("lang", LANGS)
def test_one_sheet_per_architecture_of_the_erasure_card(lang):
    ids = [a["id"] for a in raw(lang)["architectures"]]
    assert ids == [a.id for a in erasure.load_erasure(lang).architectures]
    assert set(lab.PRESETS) <= set(ids)
    assert len(ids) == 11


@pytest.mark.parametrize("lang", LANGS)
def test_the_listing_serves_a_sheet_for_each_component(lang):
    body = sheets.listing(lang)
    expected = [f"{k}.{o}" for k in lab.SHEETED_KINDS for o in lab.OPTIONS[k]]
    assert [c["key"] for c in body["components"]] == expected
    assert len(expected) == 8
    assert {p["kind"] for p in body["pending"]} == set(sheets.PENDING_SHEET_KINDS)
    assert "19b" in body["pending_text"]
    for key in expected:
        assert sheets.component(lang, key)["bench_text"] == ""


# ---------- structure and validation (criteria 3 to 5) ----------


def forged(mutate) -> None:
    data = copy.deepcopy(raw("fr"))
    mutate(data["architectures"][0])
    sheets.SheetsContent.model_validate(data)


def test_the_delivered_content_validates_and_has_five_blocks_and_seven_axes():
    for lang in LANGS:
        for arch in sheets.load_sheets(lang).architectures:
            assert tuple(arch.axes) == sheets.AXES
            for block in ("purpose_text", "when_text", "cost_text", "literature_text"):
                assert getattr(arch, block)
            assert arch.bench_text == "" and arch.sources


def test_levels_are_those_of_the_risk_matrix_of_the_security_page():
    for arch in sheets.load_sheets("fr").architectures:
        for name, axis in arch.axes.items():
            if name == "regulatory":
                assert axis.level is None
            else:
                assert axis.level in RISKS


def test_the_levels_proposed_by_the_spec():
    mid5 = "mid mid mid mid low"
    table = {
        "dense": mid5,
        "hybrid": mid5,
        "rerank": mid5,
        "crag": mid5,
        "pageindex": mid5,
        "long_context": "low low high high mid",
        "cag": "mid high high high mid",
        "agentic": "low low mid high low",
        "raptor": "high high high mid mid",
        "graphrag": "high high high high mid",
        "llm_wiki": "high high high high mid",
    }
    axes = ("copies", "erasure", "rights", "injection", "traceability")
    for arch in sheets.load_sheets("fr").architectures:
        got = [arch.axes[a].level for a in axes]
        assert got == table[arch.id].split(), arch.id


@pytest.mark.parametrize(
    "mutate",
    [
        lambda a: a["axes"].pop("copies"),
        lambda a: a["axes"].update(extra={"level": "low", "text": "x"}),
        lambda a: a["axes"]["copies"].update(level="critical"),
        lambda a: a["axes"]["regulatory"].update(level="low"),
        lambda a: a["axes"]["location"]["components"][0].update({"class": "mars"}),
        lambda a: a.update(sources=[]),
        lambda a: a["axes"]["erasure"].update(demo="rag-unknown"),
        lambda a: a["axes"]["copies"].update(demo="rag-erasure-card"),
        lambda a: a.update(story=10),
        lambda a: a["axes"]["rights"].pop("before_search"),
    ],
)
def test_invalid_sheets_are_refused_at_load(mutate):
    with pytest.raises(ValidationError):
        forged(mutate)


def test_a_story_is_required_outside_the_presets():
    data = copy.deepcopy(raw("fr"))
    next(a for a in data["architectures"] if a["id"] == "cag").pop("story")
    with pytest.raises(ValidationError):
        sheets.SheetsContent.model_validate(data)


def test_location_classes_are_local_or_depend_on_the_provider():
    for arch in sheets.load_sheets("fr").architectures:
        classes = {c.id: c.cls for c in arch.axes["location"].components}
        assert set(classes.values()) <= {"local", "depends_on_provider"}
        assert classes["generation"] == "depends_on_provider"


def test_the_crag_sheet_says_jev_is_proprietary_without_local_hosting():
    text = sheets.architecture("fr", "crag")["axes"][0]["text"]
    assert "Jev" in text and "propriétaire" in text and "sans hébergement local" in text
    classes = {
        c["id"]: c["class"] for c in sheets.architecture("fr", "crag")["axes"][0]["components"]
    }
    assert classes["judge"] == "depends_on_provider"


# ---------- links and coherence with the story 18 (criteria 6, 7) ----------


def test_the_demo_ids_are_elements_of_the_page():
    html = (STATIC / "rag.html").read_text(encoding="utf-8")
    assert set(sheets.DEMO_OF_AXIS.values()) == {
        "rag-erasure-card",
        "rag-access-card",
        "rag-atk-title",
    }
    for element in sheets.DEMO_OF_AXIS.values():
        assert f'id="{element}"' in html
    for arch in sheets.load_sheets("fr").architectures:
        with_demo = {n for n, a in arch.axes.items() if a.demo}
        assert with_demo == set(sheets.DEMO_OF_AXIS)


@pytest.mark.parametrize("lang", LANGS)
def test_places_and_update_cost_are_those_of_the_erasure_card(lang):
    info = erasure.load_erasure(lang)
    for a in info.architectures:
        body = sheets.architecture(lang, a.id)
        axis = next(x for x in body["axes"] if x["id"] == "erasure")
        assert axis["places"] == [
            {"id": p.id, "label_text": p.label_text} for p in info.places if a.id in p.architectures
        ]
        assert axis["update_text"] == a.update_text
        assert body["label_text"] == a.label_text
        assert body["available"] == a.available == (a.id in lab.PRESETS)
        assert body["story"] == a.story


def test_the_architectures_outside_the_presets_have_their_story():
    for arch_id, story in STORY_OF.items():
        body = sheets.architecture("fr", arch_id)
        assert body["available"] is False and body["story"] == story
        assert len(body["axes"]) == 7 and body["sources"]
    for arch_id in lab.PRESETS:
        body = sheets.architecture("fr", arch_id)
        assert body["available"] is True and body["story"] is None


# ---------- sources (criterion 9) ----------


@needs_literature
def test_literature_hypotheses_sources_and_states():
    rows = literature_rows()
    link = re.compile(r"\[([^\]]+)\]\((https://[^)]+)\)")
    all_urls = set(re.findall(r"\((https://[^)]+)\)", LITERATURE.read_text(encoding="utf-8")))
    content = {lang: sheets.load_sheets(lang) for lang in LANGS}
    for arch in content["fr"].architectures:
        assert arch.sources and all(s.url.startswith("https://") for s in arch.sources)
        assert set(arch.hypotheses) <= set(rows) - {"H8", "H16", "H17"}
        cited = {(s.label_text, s.url) for s in arch.sources}
        for h in arch.hypotheses:
            assert set(link.findall(rows[h][2])) <= cited, (arch.id, h)
    for hyp, cells in rows.items():
        if hyp in ("H8", "H16", "H17"):
            continue
        named = {NAME_TO_ID[n] for n in re.split(r", ", cells[3]) if n in NAME_TO_ID}
        if "fiches conformité" in cells[3]:
            named = set(erasure.ARCHITECTURES)
        for arch in content["fr"].architectures:
            if arch.id in named:
                assert hyp in arch.hypotheses, (arch.id, hyp)
    for lang in LANGS:
        for arch in content[lang].architectures:
            assert {s.url for s in arch.sources} <= all_urls
            for h in arch.hypotheses:
                state = next(s for s in STATES_FR if rows[h][2].lower().startswith(s))
                assert STATES[lang][state].lower() in arch.literature_text.lower(), (
                    lang,
                    arch.id,
                    h,
                )
    raptor = next(a for a in content["fr"].architectures if a.id == "raptor")
    assert raptor.no_source_text
    assert not any("raptor" in s.label_text.lower() for s in raptor.sources)


# ---------- compliance wording (criterion 10) ----------


@pytest.mark.parametrize("lang", LANGS)
def test_no_text_asserts_compliance_and_the_banner_is_everywhere(lang):
    blob = yaml.safe_dump(raw(lang), allow_unicode=True).lower()
    for pattern in FORBIDDEN[lang]:
        assert pattern.lower() not in blob, pattern
    assert LEGAL[lang] in raw(lang)["texts"]["banner_text"].lower()
    assert sheets.listing(lang)["texts"]["banner_text"] == raw(lang)["texts"]["banner_text"]
    for arch_id in erasure.ARCHITECTURES:
        assert (
            sheets.architecture(lang, arch_id)["banner_text"] == raw(lang)["texts"]["banner_text"]
        )
    assert UNMEASURED[lang] == raw(lang)["texts"]["bench_empty_text"]


# ---------- parity (criterion 11) ----------


def skeleton(node):
    """The data that do not depend on the language: texts are blanked."""
    if isinstance(node, dict):
        return {k: skeleton(v) for k, v in node.items()}
    if isinstance(node, list):
        return [skeleton(v) for v in node]
    if isinstance(node, str):
        return "<text>" if len(node.split()) > 3 else node
    return node


def test_the_three_languages_mirror_each_other():
    fr = raw("fr")
    for lang in ("en", "de"):
        other = raw(lang)
        assert set(other["texts"]) == set(fr["texts"])
        for key, value in fr["texts"].items():
            if isinstance(value, dict):
                assert set(other["texts"][key]) == set(value), key
            for placeholder in re.findall(r"\{\w+\}", str(value)):
                assert placeholder in str(other["texts"][key]), key
        for a, b in zip(fr["architectures"], other["architectures"], strict=True):
            assert a["id"] == b["id"] and a.get("story") == b.get("story")
            assert a["hypotheses"] == b["hypotheses"] and a["sources"] == b["sources"]
            for name, axis in a["axes"].items():
                twin = b["axes"][name]
                assert {k: v for k, v in axis.items() if k != "text"} == {
                    k: v for k, v in twin.items() if k != "text"
                }
            assert bool(a.get("no_source_text")) == bool(b.get("no_source_text"))
        assert other["texts"]["banner_text"] != fr["texts"]["banner_text"]


# ---------- the endpoints (criterion 12) ----------


def keys_of(node) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in keys_of(v)}
    if isinstance(node, list):
        return {k for v in node for k in keys_of(v)}
    return set()


def client_for(lang: str = "fr") -> TestClient:
    session = AppSession(config.Config(values={"language": lang}))
    app = create_app(
        DiagnosticSession(session.cfg, port=8421), port=8421, version="t", app_session=session
    )
    return TestClient(app, base_url="http://127.0.0.1:8421")


def test_endpoints_and_404():
    client = client_for()
    listing = client.get("/api/rag_lab/sheets")
    assert listing.status_code == 200
    assert len(listing.json()["components"]) == 8 and len(listing.json()["architectures"]) == 11
    comp = client.get("/api/rag_lab/sheets/component/chunking.semantic")
    assert comp.status_code == 200 and comp.json()["bench_text"] == ""
    arch = client.get("/api/rag_lab/sheets/architecture/graphrag")
    assert arch.status_code == 200
    assert [a["id"] for a in arch.json()["axes"]] == list(sheets.AXES)
    for url in (
        "/api/rag_lab/sheets/component/embedding.declared",  # a pending family
        "/api/rag_lab/sheets/component/query.unknown",
        "/api/rag_lab/sheets/component/nothing",
        "/api/rag_lab/sheets/architecture/unknown",
    ):
        assert client.get(url).status_code == 404, url
    shown = [listing.json(), comp.json(), arch.json()]
    for body in shown:
        keys = keys_of(body)
        assert not [k for k in keys if AVERAGE.search(k)]
        assert not keys & GLOBAL_SCORE


def test_the_endpoints_follow_the_language():
    for lang in ("en", "de"):
        body = client_for(lang).get("/api/rag_lab/sheets/architecture/hybrid").json()
        assert body["banner_text"] == raw(lang)["texts"]["banner_text"]


def test_no_model_is_opened():
    def boom(*args, **kwargs):
        raise AssertionError("a model was opened")

    session = AppSession(config.Config(values={"language": "fr"}))
    session._engine_factory = boom  # type: ignore[assignment]
    session._embedder_factory = boom  # type: ignore[assignment]
    session._reranker_factory = boom  # type: ignore[assignment]
    session.rag_lab_sheets()
    session.rag_lab_sheet_architecture("cag")
    session.rag_lab_sheet_component("query.hyde")


def test_the_page_keeps_a_hidden_soon_note_in_the_sheets_panel():
    html = (STATIC / "rag.html").read_text(encoding="utf-8")
    panel = html.split('id="rag-panel-sheets"')[1].split("</main>")[0]
    assert re.search(r'<p class="rag-note rag-soon" hidden>', panel)
    assert Path(STATIC / "rag-sheets.js").read_text(encoding="utf-8")
