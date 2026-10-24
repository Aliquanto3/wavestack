"""V1.4 story 3 (CAP-4): `search_documents`, and `read_file` opened to `corpus/<doc>.md`."""

from __future__ import annotations

import pytest
from test_tools import _segments, call, tool_session
from test_turn import _run

from wavestack.hooks import HookContext, guard
from wavestack.rag.corpus import load_rag_content
from wavestack.tools.native import (
    MAX_LINE,
    MAX_RESULTS,
    NATIVE_TOOLS,
    corpus_files,
    read_file,
    resolve_demo_path,
    search_documents,
)
from wavestack.tools.parser import ToolCall
from wavestack.tools.registry import ToolError

INACTIVE = [d.file for d in load_rag_content("fr").documents if not d.active]


def _result_lines(text: str) -> list[str]:
    return text.splitlines()[1:]  # the first line is the header


def test_the_search_ignores_case_and_accents():
    plain = search_documents("teletravail")
    assert plain == search_documents("TÉLÉTRAVAIL")
    assert any(line.startswith("corpus/teletravail.md:") for line in _result_lines(plain))


def test_results_are_bounded_and_shaped_file_line_text():
    lines = _result_lines(search_documents("mot de passe"))
    assert 0 < len(lines) <= MAX_RESULTS
    for line in lines:
        name, number, text = line.split(":", 2)
        assert name.startswith("corpus/") and number.isdigit() and len(text) <= MAX_LINE + 1


def test_the_lines_with_the_most_words_come_first():
    lines = _result_lines(search_documents("mot de passe minimum"))
    assert "minimum" in lines[0].casefold() and "mot de passe" in lines[0].casefold()


def test_the_numbered_line_is_the_one_read_file_returns():
    first = _result_lines(search_documents("Coffrix"))[0]
    name, number, _ = first.split(":", 2)
    assert "Coffrix" in read_file(name).splitlines()[int(number) - 1]


def test_the_search_follows_the_language_of_the_session():
    assert search_documents("password", "en") and "mots de passe" not in search_documents(
        "password", "en"
    )
    with pytest.raises(ToolError):
        search_documents("password", "fr")


def test_a_query_without_a_word_or_without_a_result_is_refused():
    for query in ("", "de la", "Quelles sont les"):
        with pytest.raises(ToolError):
            search_documents(query)
    with pytest.raises(ToolError):
        search_documents("zzzqqqxxx")


@pytest.mark.parametrize("lang", ["fr", "en", "de"])
def test_an_inactive_document_is_neither_searched_nor_read(lang):
    assert INACTIVE  # the trapped document and the sentinel (rag.yaml)
    assert not set(INACTIVE) & set(corpus_files())
    for file in INACTIVE:
        with pytest.raises(ToolError):
            read_file(file, lang)
        assert file not in search_documents("Exemplia", lang)
        assert file not in read_file("corpus", lang)


def test_read_file_opens_an_active_document_and_lists_the_corpus():
    assert read_file("corpus/mots_de_passe.md").startswith("# Politique des mots de passe")
    assert read_file("CORPUS/mots_de_passe.md", "en").startswith("# Exemplia password policy")
    listing = read_file("corpus")
    assert "corpus/mots_de_passe.md" in listing and INACTIVE[0] not in listing
    assert "corpus/" in read_file(".").splitlines()[0]  # the prefix is announced


@pytest.mark.parametrize(
    "path", ["corpus/../confidentiel/budget_projet.txt", "../corpus/../README.md", "corpus/nope.md"]
)
def test_read_file_stays_confined(path):
    with pytest.raises(ToolError):
        read_file(path)


@pytest.mark.parametrize(
    ("path", "decision"),
    [("corpus/mots_de_passe.md", "allow"), ("corpus/../confidentiel/budget_projet.txt", None)],
)
def test_h1_judges_the_corpus_path_with_the_same_resolution(path, decision):
    spec = next(s for s in NATIVE_TOOLS if s.name == "read_file")
    ctx = HookContext("before_tool", "t1", call=ToolCall("read_file", {"path": path}), spec=spec)
    result = guard(ctx)
    assert (result.decision if result else None) == decision


def test_search_then_read_on_the_fake_engine():
    # The test engine counts about a token per character: a wider window holds the two results.
    _, session = tool_session(
        window=8192,
        outputs=[
            call("search_documents", query="astreinte"),
            call("read_file", path="corpus/astreinte.md"),
            "Voilà.",
        ],
    )
    assert "search_documents" not in session.build_turn_state().tools  # off at launch
    session.set_tool("search_documents", True)

    events = _run(session, "Qui est d'astreinte ?")

    assert [e["tool"] for e in events["tool_started"]] == ["search_documents", "read_file"]
    assert [e["status"] for e in events["tool_ended"]] == ["ok", "ok"]
    first, _, third = events["context_rendered"]
    catalog = _segments(first, "tool_catalog")
    assert "tools.search_documents" in [s["component"] for s in catalog]
    assert "read_file" in next(
        s["text"] for s in catalog if s["component"] == "tools.search_documents"
    )  # the description names « search, then read »
    results = _segments(third, "tool_result")
    assert results[0]["component"] == "tools.search_documents"
    assert "corpus/astreinte.md:" in results[0]["text"]
    assert results[1]["text"] == read_file("corpus/astreinte.md").strip()
    assert events["turn_ended"][0]["status"] == "completed"


def test_the_corpus_prefix_resolves_the_same_whatever_its_case_and_the_os():
    # Review: `CORPUS/…` must not depend on a case-insensitive filesystem (CI on Linux).
    assert resolve_demo_path("CORPUS/mots_de_passe.md") == resolve_demo_path(
        "corpus/mots_de_passe.md"
    )
    assert resolve_demo_path(r"Corpus\astreinte.md") == resolve_demo_path("corpus/astreinte.md")


def test_the_fictitious_notice_is_neither_read_nor_searched_but_keeps_the_numbering():
    text = read_file("corpus/mots_de_passe.md")
    assert "<!--" not in text and "Texte fictif" not in text
    assert "imaginaire" not in search_documents("organisation imaginaire Exemplia")
    first = _result_lines(search_documents("Coffrix"))[0]
    name, number, _ = first.split(":", 2)
    assert "Coffrix" in read_file(name).splitlines()[int(number) - 1]
