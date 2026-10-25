"""V1.2 story 12 (CAP-7): RAPTOR's tree of summaries, the pure part (`rag/raptor.py`).

The shipped tree is computed by a rule (passages clustered by the cosine of their words, summaries
by the closest sentences); these tests read the shipped corpus of the three languages, a planted
set of vectors, and a rebuilt file in a real temporary folder. No model, no session.
"""

from __future__ import annotations

import importlib.util

import pytest

from wavestack import config
from wavestack.rag import raptor as r
from wavestack.rag.contexts import fingerprint
from wavestack.rag.corpus import DocText, chunk_documents, load_rag_content, read_documents

LANGS = ("fr", "en", "de")
SIZE = 700
CODE = "TLV-7731-QZ"
# Measured on the shipped corpus with the rule as written (story 12).
LEAVES = {"fr": 73, "en": 65, "de": 78}
NODES = {"fr": 27, "en": 27, "de": 37}
# Summaries citing the sentinel's code once it is active (a sentence with a code first, D3).
SENTINEL_SUMMARIES = {"fr": 3, "en": 3, "de": 2}


def shipped_docs(lang: str):  # noqa: ANN201
    content = load_rag_content(lang)
    return content, read_documents(content, lang)


def audiences(content) -> dict[str, str]:  # noqa: ANN001
    return {d.id: d.audience for d in content.documents}


@pytest.fixture(scope="module")
def trees() -> dict[str, r.Tree]:
    out = {}
    for lang in LANGS:
        content, docs = shipped_docs(lang)
        out[lang] = r.build_tree(docs, lang, SIZE, audiences(content))
    return out


def with_sentinel(lang: str) -> list[DocText]:
    content = load_rag_content(lang)
    docs = [
        d.model_copy(update={"active": True}) if d.id == "projet_talvane" else d
        for d in content.documents
    ]
    return read_documents(content.model_copy(update={"documents": docs}), lang)


# ---------- criterion 2: the shipped tree ----------


@pytest.mark.parametrize("lang", LANGS)
def test_the_shipped_file_is_the_rule_on_the_shipped_corpus(lang, trees):
    content, docs = shipped_docs(lang)
    again = r.build_tree(docs, lang, SIZE, audiences(content))
    first = r.dump(r.to_file(trees[lang]))
    assert first == r.dump(r.to_file(again))  # deterministic, byte for byte
    path = config.content_file(r.RAPTOR_FILE, lang)
    body = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert body.endswith(first) and body.startswith("# RAPTOR")
    shipped = r._read(path)
    assert (shipped.author, shipped.method, shipped.model) == ("shipped", "heuristic", "heuristic")
    assert shipped.duration_ms is None and shipped.calls is None and "duration" not in body


def test_the_build_tool_finds_no_difference():
    path = config.repo_root() / "tools" / "build_raptor.py"
    spec = importlib.util.spec_from_file_location("build_raptor", path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    assert module.main(["--check"]) == 0


@pytest.mark.parametrize("lang", LANGS)
def test_the_measured_shape_of_the_tree(lang, trees):
    tree = trees[lang]
    assert len(tree.leaves) == LEAVES[lang] and len(tree.nodes) == NODES[lang]
    assert len(tree.nodes) >= 15 and tree.levels >= 2
    assert all(2 <= len(n.children) <= r.MAX_CLUSTER for n in tree.nodes.values())
    assert all(len(n.summary_text) <= r.SUMMARY_MAX_CHARS for n in tree.nodes.values())
    _, docs = shipped_docs(lang)
    chunks = {f"{c.doc_id}#{c.position}": c.text for c in chunk_documents(docs, SIZE)}
    shipped = r._read(config.content_file(r.RAPTOR_FILE, lang))
    assert {pid: fingerprint(chunks[pid]) for pid in chunks} == shipped.leaves


def test_the_audience_is_the_most_restrictive_of_the_passages(trees):
    tree = trees["fr"]
    for node in tree.nodes.values():
        held = {p.audience for p in tree.leaves if p.id in tree.leaves_under(node.id)}
        assert node.audience == ("hr" if "hr" in held else "all")
    assert any(n.audience == "hr" for n in tree.nodes.values())


def test_inactive_documents_are_absent_and_the_sentinel_reaches_the_summaries():
    shipped = r.build_tree(shipped_docs("fr")[1], "fr", SIZE)
    assert not any(p.doc_id in ("projet_talvane", "faq_mots_de_passe") for p in shipped.leaves)
    for lang in LANGS:
        tree = r.build_tree(with_sentinel(lang), lang, SIZE)
        held = [n for n in tree.nodes.values() if CODE in n.summary_text]
        assert len(held) == SENTINEL_SUMMARIES[lang]


# ---------- the clustering ----------


def test_the_clustering_is_deterministic_bounded_and_keeps_far_vectors_apart():
    near = [{"a": 1.0}, {"a": 0.9, "b": 0.1}, {"a": 0.8, "b": 0.2}]
    far = [{"z": 1.0}, {"z": 0.95, "y": 0.05}]
    alone = [{"q": 1.0}]
    vectors = [r._unit(v) for v in near + far + alone]
    groups = r.cluster(vectors)
    assert groups == r.cluster(vectors)
    assert [0, 1, 2] in groups and [3, 4] in groups and [5] in groups
    many = [r._unit({"a": 1.0, f"x{i}": 0.01}) for i in range(10)]
    assert all(len(g) <= r.MAX_CLUSTER for g in r.cluster(many))


# ---------- the reading: structure kept, placement, summaries by fingerprint ----------


def small() -> list[DocText]:
    return [
        d for d in shipped_docs("fr")[1] if d.doc_id in ("incidents", "gestion_crise", "astreinte")
    ]


def test_a_new_passage_joins_a_first_level_node_and_only_its_branch_is_redone():
    docs = small()
    tree = r.build_tree(docs, "fr", SIZE)
    shipped = r.to_file(tree)
    extra = DocText(
        "crise_bis",
        "Crise bis",
        "La cellule de crise se réunit dans les deux heures ; l'astreinte prévient le directeur.",
    )
    again = r.assemble([*docs, extra], "fr", SIZE, shipped=shipped)
    assert again.placed == 1 and any("crise_bis#1" in n.children for n in again.nodes.values())
    before = {(n.id, n.sha256) for n in tree.nodes.values()}
    redone = [n for n in again.nodes.values() if (n.id, n.sha256) not in before]
    assert 1 <= len(redone) < len(again.nodes)
    kept = [n for n in again.nodes.values() if (n.id, n.sha256) in before]
    assert all(n.source == "shipped" for n in kept)


def test_a_rebuilt_summary_is_read_at_equal_fingerprint_and_stale_otherwise(tmp_path):
    docs = small()
    tree = r.build_tree(docs, "fr", SIZE)
    first = next(iter(tree.nodes.values()))
    first.summary_text, first.source = "Résumé du modèle.", "rebuilt"
    file = r.to_file(tree, author="rebuilt", model="fake", only_model=True, measure=MEASURE)
    assert [n.summary_text for n in file.nodes if n.summary_text] == ["Résumé du modèle."]
    r.write_rebuilt("fr", file, tmp_path)
    read = r.load_tree(docs, "fr", SIZE, folder=tmp_path)
    assert read.rebuilt is not None and read.nodes[first.id].source == "rebuilt"
    assert read.by_model == 1
    leaf = tree.leaf(first.children[0])
    assert leaf is not None
    head = leaf.text[:40]
    changed = [
        DocText(d.doc_id, d.title_text, d.text.replace(head, head + " modifié", 1))
        if d.doc_id == leaf.doc_id
        else d
        for d in docs
    ]
    stale = r.load_tree(changed, "fr", SIZE, folder=tmp_path)
    assert stale.nodes[first.id].stale and stale.nodes[first.id].source == "rule"
    assert r.reset("fr", tmp_path) and not r.reset("fr", tmp_path)


MEASURE = {"duration_ms": 5, "input_tokens": 10, "output_tokens": 3, "calls": 2}


def test_forget_removes_a_document_from_the_rebuilt_file(tmp_path):
    docs = small()
    tree = r.build_tree(docs, "fr", SIZE)
    for node in tree.nodes.values():
        node.summary_text, node.source = f"Résumé {node.id} : texte du modèle.", "rebuilt"
    r.write_rebuilt(
        "fr",
        r.to_file(tree, author="rebuilt", model="fake", only_model=True, measure=MEASURE),
        tmp_path,
    )
    gone = "gestion_crise"
    assert r.forget("fr", [gone], tmp_path) > 0
    body = r.rebuilt_path("fr", tmp_path).read_text(encoding="utf-8")
    assert f"{gone}#" not in body and f"- {gone}" not in body
    file = r._read(r.rebuilt_path("fr", tmp_path))
    touched = [n for n in file.nodes if n.summary_text == ""]
    assert touched  # the summaries that read it, emptied
    assert r.forget("fr", [gone], tmp_path) == 0  # nothing left to remove: not written again


def test_the_file_refuses_a_measure_on_the_shipped_tree_and_an_unknown_child(trees):
    data = r.to_file(trees["fr"]).model_dump()
    with pytest.raises(ValueError, match="measure"):
        r.RaptorFile.model_validate(data | {"calls": 1})
    data["nodes"][0]["children"] = ["inconnu#9"]
    with pytest.raises(ValueError, match="unknown"):
        r.RaptorFile.model_validate(data)


# ---------- criterion 3: the search on every level, pure ----------


def test_the_search_reads_every_level_without_a_model(trees):
    from wavestack.rag.corpus import load_rag_questions  # noqa: PLC0415

    questions = {q.id: q for q in load_rag_questions("fr")}
    picks = r.select(trees["fr"], questions["q_global_rh"].question_text, "fr")
    assert 1 <= len(picks) <= r.TOP_NODES
    assert any(p.level >= 1 for p in picks)  # a summary among them
    assert [p.score for p in picks] == sorted((p.score for p in picks), reverse=True)
    fact = r.select(trees["fr"], questions["q_fact_pwd"].question_text, "fr")
    assert fact[0].doc_id == "mots_de_passe"
    assert r.select(trees["fr"], "zzzz qqqq", "fr") == []
