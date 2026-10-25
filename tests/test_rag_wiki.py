"""V1.2 story 14 (CAP-7): the LLM Wiki, compiled by a rule, linted, rebuilt, forgotten.

The shipped wiki is compiled by a deterministic rule without a model: a test compiles it again
from the shipped corpus and asks for the same file, byte for byte (no stale file). The pages
always come from the documents, the vocabulary (the concepts that have a page) from the file read,
each synthesis from the rebuilt file, else the shipped one, at equal fingerprint, else from the
rule. Pure functions: no session, no model; files in `tmp_path`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

from wavestack.rag import wiki
from wavestack.rag.corpus import DocText, load_rag_content, read_documents

ROOT = Path(__file__).resolve().parents[1]
LANGS = ("fr", "en", "de")
DOCS = [
    DocText(
        "alpha",
        "Alpha",
        "# Alpha\n\nLa cellule gère les pannes. La cellule se réunit le lundi avec le support.\n\n"
        "Le budget vaut 40 euros par mois.",
    ),
    DocText(
        "beta",
        "Beta",
        "# Beta\n\nLa cellule appelle le support. Le support répond vite.\n\n"
        "Le support ferme à 18 heures.",
    ),
    DocText("gamma", "Gamma", "# Gamma\n\nUn texte isolé. Rien de commun ici, pas même un mot."),
]


def builder():
    spec = importlib.util.spec_from_file_location("build_wiki", ROOT / "tools" / "build_wiki.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def shipped(lang: str) -> wiki.WikiFile:
    path = builder().target(lang)
    return wiki.WikiFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


# ---------- the shipped wiki ----------


@pytest.mark.parametrize("lang", LANGS)
def test_the_shipped_file_is_the_rule_on_the_shipped_corpus(lang):
    tool = builder()
    text = tool.target(lang).read_text(encoding="utf-8").replace("\r\n", "\n")
    assert text == tool.build(lang) == tool.build(lang)  # deterministic, not stale
    file = shipped(lang)
    assert (file.author, file.method, file.model) == ("shipped", "heuristic", "heuristic")
    assert file.tokens is None and file.duration_ms is None


@pytest.mark.parametrize("lang", LANGS)
def test_the_shipped_wiki_measured_on_the_corpus(lang):
    """Measured when the story was written (fr 67 pages, en 66, de 67; 320 to 368 links; about
    100 KB per file): the bounds below leave room for a corpus that grows a little."""
    content = load_rag_content(lang)
    docs = read_documents(content, lang)
    book = wiki.load_wiki(docs, lang, audiences={d.id: d.audience for d in content.documents})
    assert book.count("source") == len(docs) == 25 and book.count("index") == 1
    assert 30 <= book.count("concept") <= 60
    assert book.links() >= 250 and book.size() < 100_000
    assert len(builder().target(lang).read_bytes()) < 150_000
    assert all(len(p.sources) >= 2 for p in book.listed() if p.kind == "concept")
    # Every page keeps its sources; an HR document makes its pages HR (shown, never filtered).
    hr = {d.id for d in content.documents if d.audience == "hr" and d.active}
    for page in book.listed():
        assert page.audience == ("hr" if hr & set(page.sources) else "all")
    assert any(p.audience == "hr" for p in book.listed())
    # The lint of the shipped wiki: an orphan page at most (a document that names no concept).
    findings = wiki.lint(book, docs, lang)
    assert len(findings) <= 2 and {f.code for f in findings} <= {"orphan_page"}
    # The trapped document and the sentinel, inactive, are in no page.
    assert not [p for p in book.listed() if {"faq_mots_de_passe", "projet_orion"} & set(p.sources)]


def test_the_french_wiki_has_the_concepts_of_the_crisis_questions():
    file = shipped("fr")
    assert {"astreinte", "crise"} <= set(file.concepts)
    page = next(p for p in file.pages if p.id == "concept/astreinte")
    assert {"astreinte", "gestion_crise"} <= set(
        page.sources
    ) and "[[source/astreinte]]" in page.text


def test_the_shipped_file_carries_no_measure():
    with pytest.raises(ValueError, match="no measure"):
        wiki.WikiFile(
            author="shipped", method="heuristic", model="heuristic", tokens=1, concepts=[], pages=[]
        )
    with pytest.raises(ValueError, match="tokens and its duration"):
        wiki.WikiFile(author="rebuilt", method="llm", model="m", concepts=[], pages=[])


# ---------- the rule ----------


def test_the_rule_compiles_a_page_per_source_per_concept_and_an_index():
    pages = wiki.build_wiki(DOCS, "fr")
    assert list(pages)[0] == "index"
    assert set(pages) == {
        "index",
        "source/alpha",
        "source/beta",
        "source/gamma",
        "concept/cellule",
        "concept/support",
    }
    alpha = pages["source/alpha"]
    assert alpha.synthesis_text.startswith("La cellule gère les pannes.")
    assert "- Le budget vaut 40 euros par mois." in alpha.text  # a key fact: a figure
    assert "[[concept/cellule]]" in alpha.text and "corpus/alpha.md" in alpha.text
    cell = pages["concept/cellule"]
    assert cell.sources == ["alpha", "beta"] and "([[source/beta]])" in cell.text
    assert all(f"[[{p}]]" in pages["index"].text for p in pages if p != "index")
    assert wiki.build_wiki(DOCS, "fr") == pages  # deterministic


def test_the_lint_finds_orphans_thin_empty_missing_and_broken():
    book = wiki.assemble(DOCS, "fr", None, None)
    found = {(f.code, f.page_id) for f in wiki.lint(book, DOCS, "fr")}
    assert found == {("orphan_page", "source/gamma")}
    # A frozen vocabulary with a word no document names, and without one the corpus calls for.
    file = wiki.shipped_file(wiki.build_wiki(DOCS, "fr"), ["cellule", "zeppelin"])
    book = wiki.assemble(DOCS, "fr", file, None)
    codes = {(f.code, f.page_id) for f in wiki.lint(book, DOCS, "fr")}
    assert ("empty_concept", "concept/zeppelin") in codes
    assert ("missing_concept", "concept/support") in codes
    # A concept page that lost a source; a link a model wrote to no page.
    book = wiki.assemble(DOCS[::2], "fr", file, None)
    assert ("thin_concept", "concept/cellule") in {
        (f.code, f.page_id) for f in wiki.lint(book, DOCS[::2], "fr")
    }
    book.pages["source/alpha"].synthesis_text = "Voir [[concept/nulle_part]]."
    assert ("broken_link", "source/alpha") in {
        (f.code, f.page_id) for f in wiki.lint(book, DOCS[::2], "fr")
    }


def test_an_update_touches_the_document_s_pages_and_its_concepts_only():
    concepts = wiki.select_concepts(DOCS, "fr")
    added = DocText("delta", "Delta", "# Delta\n\nLe support aide. Le support conseille.")
    touched, gone = wiki.touched_pages(DOCS, [*DOCS, added], "fr", concepts)
    assert touched == {"source/delta", "concept/support"} and gone == set()
    touched, gone = wiki.touched_pages(DOCS, [DOCS[0], DOCS[2]], "fr", concepts)
    assert touched == {"concept/cellule", "concept/support"} and gone == {"source/beta"}
    gamma = DocText("gamma", "Gamma", "Plus rien.")
    touched, gone = wiki.touched_pages(DOCS, [DOCS[0], gamma], "fr", concepts)
    assert "source/gamma" in touched and "source/beta" in gone


def test_parse_pages_reads_the_first_line_in_range_at_most_three():
    assert wiki.parse_pages("Je pense.\nPAGES: 2, 9, 2, 1, 3, 4", 5) == [2, 1, 3]
    assert wiki.parse_pages("**Pages**: none", 5) == []
    assert wiki.parse_pages("PAGES: 99", 5) == []
    assert wiki.parse_pages("La deuxième page.", 5) is None


# ---------- the rebuilt file ----------


def test_rebuilt_syntheses_are_read_by_fingerprint_and_forgotten_with_their_document(tmp_path):
    pages = wiki.build_wiki(DOCS, "fr")
    concepts = wiki.select_concepts(DOCS, "fr")
    entries = []
    for page in pages.values():
        if page.id != "index":
            page.synthesis_text = f"Synthèse du modèle pour {page.id}."
            entries.append(page.entry())
    wiki.write_rebuilt(
        "fr",
        entries,
        concepts=concepts,
        model="m",
        tokens=10,
        duration_ms=5,
        merge=False,
        folder=tmp_path,
    )
    book = wiki.load_wiki(DOCS, "fr", tmp_path)
    assert book.rebuilt is not None and book.pages["source/alpha"].source == "rebuilt"
    assert "Synthèse du modèle pour concept/cellule." in book.pages["index"].text
    # A modified document: its page is stale, the rule's synthesis, the rest kept.
    changed = [DocText("alpha", "Alpha", DOCS[0].text + "\n\nUn ajout."), *DOCS[1:]]
    book = wiki.load_wiki(changed, "fr", tmp_path)
    assert book.pages["source/alpha"].stale and book.stale == 1
    assert book.pages["source/beta"].source == "rebuilt"
    # A deleted document leaves none of its text in the rebuilt file.
    assert wiki.forget("fr", ["alpha"], tmp_path) == 3  # its page and the concepts citing it
    kept = wiki.load_files("fr", tmp_path)[1]
    assert kept is not None and "alpha" not in wiki.rebuilt_path("fr", tmp_path).read_text(
        encoding="utf-8"
    ).replace("Alpha", "")
    assert {p.id for p in kept.pages} == {"source/beta", "source/gamma"}
    # An update merges over it and adds its measure.
    wiki.write_rebuilt(
        "fr",
        [entries[0]],
        concepts=["autre"],
        model="n",
        tokens=4,
        duration_ms=1,
        merge=True,
        folder=tmp_path,
    )
    merged = wiki.load_files("fr", tmp_path)[1]
    assert merged is not None and (merged.tokens, merged.model) == (14, "m + n")
    assert merged.concepts == concepts  # the vocabulary of the full compilation stays
    assert wiki.reset("fr", tmp_path) and not wiki.reset("fr", tmp_path)
