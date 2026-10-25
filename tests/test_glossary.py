"""V1.5 story 6 (CAP-6): the harness glossary, `content/glossary.yaml` and its translations,
its route, its citations from the texts of the bricks and the scenarios, its button in the
shared navigation."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from test_bricks import _client
from test_i18n import _session

from wavestack import config, glossary

CONTENT = config.content_dir()
STATIC = config.repo_root() / "src" / "wavestack" / "web" / "static"
TRANSLATED = ("en", "de")
PAGES = ("index", "llm", "rag", "mcp", "security", "diagnostic")
# The glossaries themselves (and the MCP demo's) are not citing texts.
NOT_CITING = ("glossary.yaml", "mcp_local/glossary.yaml")


@pytest.fixture(autouse=True)
def _fresh_caches():
    config.clear_content_caches()
    yield
    config.clear_content_caches()


def _raw(lang: str) -> dict:
    return yaml.safe_load(config.content_file("glossary.yaml", lang).read_text(encoding="utf-8"))


def test_the_french_glossary_has_40_to_60_valid_terms():
    terms = glossary.load_terms("fr")
    assert 40 <= len(terms) <= 60
    for key, entry in terms.items():
        assert glossary.KEY.fullmatch(key)
        assert entry["term"].strip() and entry["definition"].strip()
    # The terms the evaluation module needs.
    needed = {
        "call_ceiling", "pass_at_k", "pass_hat_k", "benchmark", "regression", "llm_judge",
        "agent_case", "check", "replay", "witness_replay", "journal", "context_window",
        "compaction", "prompt_cache", "kv_cache", "reasoning", "memory", "system_prompt",
        "tool", "rag", "mcp", "skill", "hook", "subagent",
    }  # fmt: skip
    assert needed <= terms.keys(), sorted(needed - terms.keys())


@pytest.mark.parametrize("lang", TRANSLATED)
def test_the_translation_mirrors_the_french_glossary(lang):
    path = config.content_file("glossary.yaml", lang)
    assert path == CONTENT / "i18n" / lang / "glossary.yaml"
    french, translated = glossary.load_terms("fr"), glossary.load_terms(lang)
    assert list(translated) == list(french), "mêmes clés, dans le même ordre"
    assert set(_raw(lang)) == {"terms"}
    for key, entry in french.items():
        assert set(translated[key]) == {"term", "definition"}
        assert translated[key]["definition"] != entry["definition"], key


def test_citation_syntax():
    text = "Voir [[g:tool]], [[g:pass_at_k|le pass@k]], [[page]], [[g:Pas une clé]], [[g:x]]."
    assert glossary.cited_keys(text) == {"tool", "pass_at_k", "x"}
    match = glossary.CITATION.search("[[g:pass_at_k|le pass@k]]")
    assert match and match.groups() == ("pass_at_k", "le pass@k")
    assert glossary.cited_keys("aucune") == set()


def test_glossary_js_uses_the_same_citation_pattern():
    script = (STATIC / "glossary.js").read_text(encoding="utf-8")
    assert glossary.CITATION.pattern in script


def _citing_files() -> list[Path]:
    skipped = {CONTENT / name for name in NOT_CITING}
    skipped |= {CONTENT / "i18n" / lang / name for lang in TRANSLATED for name in NOT_CITING}
    return sorted(
        p
        for p in CONTENT.rglob("*")
        if p.is_file() and p.suffix in {".yaml", ".md"} and p not in skipped
    )


def _unknown_citations(paths: list[Path], root: Path) -> list[str]:
    """The citations of `paths` whose key is missing from a language of the glossary."""
    known = [set(glossary.load_terms(lang)) for lang in ("fr", *TRANSLATED)]
    unknown = []
    for path in paths:
        for key in sorted(glossary.cited_keys(path.read_text(encoding="utf-8-sig"))):
            if not all(key in keys for keys in known):
                unknown.append(f"{path.relative_to(root).as_posix()} : [[g:{key}]]")
    return unknown


def test_every_term_cited_by_a_content_text_exists_in_every_language():
    """The texts of the bricks and of the scenarios (and every other text of `content/`)
    cite only terms of the glossary, in French and in its translations."""
    unknown = _unknown_citations(_citing_files(), CONTENT)
    assert not unknown, unknown


def test_a_citation_of_an_unknown_term_would_be_found(tmp_path):
    """The check above looks at the `.yaml` and `.md` texts under `content/` (bricks included)
    and reports a key the glossary does not know, not a known one."""
    files = _citing_files()
    assert CONTENT / "bricks" / "guardrails.yaml" in files
    assert CONTENT / "glossary.yaml" not in files
    text = tmp_path / "brick.yaml"
    text.write_text("explanation_text:\n  - Un [[g:inconnu]] et un [[g:tool|outil]].\n", "utf-8")
    assert _unknown_citations([text], tmp_path) == ["brick.yaml : [[g:inconnu]]"]


@pytest.mark.parametrize("lang", ["fr", *TRANSLATED])
def test_the_route_serves_the_terms_in_the_settings_language(lang):
    _, session = _session(language=lang)
    body = _client(session).get("/api/glossary").json()
    expected = glossary.load_terms(lang)
    assert body["language"] == lang
    assert [t["key"] for t in body["terms"]] == list(expected)
    first = body["terms"][0]
    assert first == {"key": first["key"], **expected[first["key"]]}
    session.close()


def test_the_route_falls_back_to_french_on_a_broken_translation(tmp_path, monkeypatch):
    broken = tmp_path / "i18n" / "de" / "glossary.yaml"
    broken.parent.mkdir(parents=True)
    broken.write_text("terms: {tool: {term: ''}}\n", encoding="utf-8")
    _, session = _session(language="de")
    real = config.content_file
    monkeypatch.setattr(
        config,
        "content_file",
        lambda rel, lang=None: (
            broken if (rel, lang) == ("glossary.yaml", "de") else real(rel, lang)
        ),
    )
    body = _client(session).get("/api/glossary").json()
    assert body["language"] == "fr"
    assert len(body["terms"]) == len(glossary.load_terms("fr"))
    session.close()


def test_the_route_falls_back_to_french_on_a_malformed_yaml_translation(tmp_path, monkeypatch):
    broken = tmp_path / "glossary.yaml"
    broken.write_text("terms: {tool: {term: Outil, definition: x\n", encoding="utf-8")
    _, session = _session(language="en")
    real = config.content_file
    monkeypatch.setattr(
        config,
        "content_file",
        lambda rel, lang=None: (
            broken if (rel, lang) == ("glossary.yaml", "en") else real(rel, lang)
        ),
    )
    response = _client(session).get("/api/glossary")
    assert response.status_code == 200
    assert response.json()["language"] == "fr"
    session.close()


def test_an_invalid_glossary_is_refused(tmp_path, monkeypatch):
    bad = tmp_path / "glossary.yaml"
    for text in ("terms: {}\n", "terms: {Bad-Key: {term: a, definition: b}}\n",
                 "terms: {ok: {term: a, definition: ' '}}\n",
                 "terms: {ok: {term: 404, definition: b}}\n",
                 "terms: {ok: {term: a, definition: [b]}}\n",
                 "terms: {ok: {term: a, definition: b\n"):  # fmt: skip
        bad.write_text(text, encoding="utf-8")
        monkeypatch.setattr(config, "content_file", lambda rel, lang=None: bad)
        with pytest.raises(glossary.GlossaryError):
            glossary.load_terms("fr")


@pytest.mark.parametrize("page", PAGES)
def test_every_page_has_the_glossary_button_in_its_navigation_and_loads_the_script(page):
    html = (STATIC / f"{page}.html").read_text(encoding="utf-8")
    nav = html[html.index('<nav class="site-nav"') : html.index("</nav>")]
    assert re.search(r'<button[^>]*id="glossary-toggle"[^>]*>Glossaire</button>', nav)
    assert html.count('src="/static/glossary.js"') == 1
