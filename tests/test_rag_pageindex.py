"""V1.2 story 11 (CAP-7): PageIndex's tree of sections, the shipped file and the rebuilt one.

The shipped tree is built by a deterministic rule without a model: a test builds it again from the
shipped corpus and asks for the same file, byte for byte (no stale file). The structure always
comes from the documents; each summary from the rebuilt file, else the shipped one, at equal
fingerprint, else from the rule (a node « stale » when it had a rebuilt summary).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

from wavestack import config
from wavestack.rag import pageindex
from wavestack.rag.corpus import DocText, load_rag_content, read_documents

ROOT = Path(__file__).resolve().parents[1]
DOCS = [
    DocText(
        "alpha", "Alpha", "# Alpha\n\nPremière phrase d'alpha. Suite.\n\nDeuxième bloc, court."
    ),
    DocText(
        "beta", "Beta", "# Beta\n\nUn seul bloc pour beta, avec un mot de plus que huit mots ici."
    ),
]


def builder():
    spec = importlib.util.spec_from_file_location(
        "build_pageindex", ROOT / "tools" / "build_pageindex.py"
    )
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.mark.parametrize("lang", ["fr", "en", "de"])
def test_the_shipped_file_is_the_rule_on_the_shipped_corpus(lang):
    """Criterion 9: the root, a node per document and per section, stable ids, fingerprints,
    the rule's summaries; the header says `shipped`, `heuristic`, and no measure."""
    tool = builder()
    path = tool.target(lang)
    assert path.read_text(encoding="utf-8").replace("\r\n", "\n") == tool.build(lang)
    shipped = pageindex.TreeFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    assert (shipped.author, shipped.method, shipped.model) == ("shipped", "heuristic", "heuristic")
    assert shipped.tokens is None and shipped.duration_ms is None
    documents = read_documents(load_rag_content(lang), lang)
    kinds = [n.kind for n in shipped.nodes]
    assert kinds[0] == "root" and kinds.count("document") == len(documents) == 25  # the active ones
    ids = [n.id for n in shipped.nodes]
    assert len(set(ids)) == len(ids)
    assert all(len(n.summary_text) <= pageindex.TREE_SUMMARY_MAX_CHARS for n in shipped.nodes)
    tree = pageindex.assemble(documents, shipped, None)
    assert tree.depth() == 2 and tree.stale == 0
    assert {n.source for n in tree.nodes.values()} == {"shipped"}


def test_the_rule_titles_summaries_and_ids():
    nodes = pageindex.build_tree(DOCS)
    assert list(nodes) == ["corpus", "alpha", "alpha#1", "alpha#2", "beta", "beta#1"]
    assert nodes["alpha"].summary_text == "Première phrase d'alpha."
    assert nodes["alpha#2"].title_text == "Deuxième bloc, court."
    assert nodes["beta#1"].title_text == "Un seul bloc pour beta, avec un mot…"
    assert nodes["alpha#1"].parent == "alpha" and nodes["alpha"].parent == "corpus"
    assert nodes["corpus"].children == ["alpha", "beta"]
    assert pageindex.build_tree(DOCS) == nodes  # deterministic


def test_a_subtitle_opens_an_intermediate_level():
    doc = DocText(
        "gamma",
        "Gamma",
        "# Gamma\n\n## Partie A\n\nTexte A1.\n\nTexte A2.\n\n## Partie B\nTexte B.",
    )
    nodes = pageindex.build_tree([doc])
    assert nodes["gamma"].children == ["gamma#1", "gamma#4"]
    assert nodes["gamma#1"].kind == "heading" and nodes["gamma#1"].title_text == "Partie A"
    assert nodes["gamma#1"].children == ["gamma#2", "gamma#3"]
    assert nodes["gamma#4"].summary_text == "Texte B."
    tree = pageindex.Tree(nodes)
    assert tree.depth() == 3


def test_a_rebuilt_summary_wins_until_its_text_changes(tmp_path):
    """Criterion 12: a node whose text changed has the rule's summary and is stale; the rest of
    the rebuilt tree is kept."""
    nodes = pageindex.build_tree(DOCS)
    entries = [
        n.entry().model_copy(update={"summary_text": f"Résumé du modèle {n.id}"})
        for n in nodes.values()
        if n.id != "corpus"
    ]
    pageindex.write_rebuilt("fr", entries, model="fake", tokens=40, duration_ms=12, folder=tmp_path)
    shipped = pageindex.shipped_file(nodes)
    rebuilt = pageindex.load_files("fr", tmp_path)[1]
    assert rebuilt is not None and (rebuilt.author, rebuilt.method) == ("rebuilt", "llm")
    tree = pageindex.assemble(DOCS, shipped, rebuilt)
    assert tree.nodes["alpha#1"].summary_text == "Résumé du modèle alpha#1" and tree.stale == 0
    changed = [
        DOCS[0]._replace(text=DOCS[0].text.replace("Deuxième bloc", "Bloc modifié")),
        DOCS[1],
    ]
    tree = pageindex.assemble(changed, shipped, rebuilt)
    assert tree.nodes["alpha#2"].stale and tree.nodes["alpha#2"].source == "heuristic"
    assert tree.nodes["alpha#2"].summary_text == "Bloc modifié, court."
    assert tree.nodes["alpha"].stale  # the document's own text changed too
    assert tree.nodes["beta#1"].summary_text == "Résumé du modèle beta#1"
    assert tree.stale == 2


def test_rebuilds_add_up_and_reset_deletes_the_file(tmp_path):
    nodes = pageindex.build_tree(DOCS)
    one = [nodes["alpha"].entry().model_copy(update={"summary_text": "A."})]
    two = [nodes["beta"].entry().model_copy(update={"summary_text": "B."})]
    pageindex.write_rebuilt("fr", one, model="m1", tokens=10, duration_ms=5, folder=tmp_path)
    pageindex.write_rebuilt("fr", two, model="m2", tokens=20, duration_ms=7, folder=tmp_path)
    rebuilt = pageindex.load_files("fr", tmp_path)[1]
    assert rebuilt is not None
    assert (rebuilt.model, rebuilt.tokens, rebuilt.duration_ms) == ("m1 + m2", 30, 12)
    assert {n.id for n in rebuilt.nodes} == {"alpha", "beta"}
    assert pageindex.reset("fr", tmp_path) and not pageindex.rebuilt_path("fr", tmp_path).exists()
    assert not pageindex.reset("fr", tmp_path)


def test_an_unreadable_rebuilt_file_is_ignored(tmp_path):
    path = pageindex.rebuilt_path("fr", tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("author: rebuilt\nnodes: 3\n", encoding="utf-8")
    shipped, rebuilt, error = pageindex.load_files("fr", tmp_path)
    assert shipped is not None and rebuilt is None and error is None


def test_the_shipped_file_carries_no_measure():
    nodes = pageindex.build_tree(DOCS)
    with pytest.raises(ValueError, match="no measure"):
        pageindex.TreeFile(
            author="shipped", method="heuristic", model="heuristic", tokens=3, nodes=[]
        )
    with pytest.raises(ValueError, match="tokens and its duration"):
        pageindex.TreeFile(author="rebuilt", method="llm", model="m", nodes=[])
    assert "duration_ms" not in pageindex.dump(pageindex.shipped_file(nodes))


@pytest.mark.parametrize(
    ("answer", "count", "expected"),
    [
        ("CHOICE: 4", 27, [4]),
        ("Je choisis.\nchoice : 1, 2, 3", 5, [1, 2]),
        ("CHOICE: 99", 27, []),
        ("CHOICE: 4, 99", 27, [4]),
        ("CHOICE: 2, 2", 3, [2]),
        ("CHOICE: NONE", 27, []),
        ("**CHOICE:** none", 27, []),
        ("Le document 4.", 27, None),
    ],
)
def test_parse_choice(answer, count, expected):
    assert pageindex.parse_choice(answer, count) == expected


def test_the_level_list_shows_titles_and_summaries_only():
    nodes = pageindex.build_tree(DOCS)
    listed = pageindex.level_list([nodes["alpha"], nodes["beta"]])
    assert listed.splitlines()[0] == "1. Alpha — Première phrase d'alpha."
    assert "Suite" not in listed and "Deuxième bloc" not in listed


def test_the_shipped_level_of_documents_fits_the_default_window():
    """25 active documents, 120 characters of summary each: the first level's list holds in the
    default window minus a short call's reserve."""
    for lang in ("fr", "en", "de"):
        nodes = pageindex.build_tree(read_documents(load_rag_content(lang), lang))
        listed = pageindex.level_list([nodes[c] for c in nodes["corpus"].children])
        tokens = config.estimate_tokens(listed, config.Config().chars_per_token)
        assert tokens < config.Config().context_window - 1024, tokens
