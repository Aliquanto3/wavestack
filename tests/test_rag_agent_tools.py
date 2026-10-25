"""V1.2 story 11 (CAP-7): the agentic search's three tools, confined to the work copy.

The tools read a list of `DocText` (the chain's documents), never the disk: the model's argument
is only compared with the virtual names `corpus/<doc_id>.md`. A small corpus is written in a real
temporary folder (`tmp_path`) so that a hostile action can be shown to read and write nothing.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath

import pytest

from wavestack import config
from wavestack.rag import agent_tools, workcopy
from wavestack.rag.agent_tools import Action, Workspace, parse_action
from wavestack.rag.corpus import DocText, load_rag_content
from wavestack.tools import native
from wavestack.tools.registry import ToolError

DOCS = {
    "teletravail": (
        "Accord de télétravail",
        "# Télétravail\n\nOn télétravaille 3 jours par semaine.\n\nLe matériel est fourni.",
    ),
    "astreinte": ("Astreinte", "# Astreinte\n\nLe numéro d'astreinte sécurité est le 4242."),
}


def estimate(text: str) -> int:
    return config.estimate_tokens(text, 4.0)


def corpus(tmp_path: Path) -> tuple[Path, list[DocText]]:
    """The small corpus, written in a folder, then read as the chain reads it."""
    folder = tmp_path / "corpus"
    folder.mkdir()
    docs = []
    for doc_id, (title, text) in DOCS.items():
        (folder / f"{doc_id}.md").write_text(text, encoding="utf-8")
        docs.append(DocText(doc_id, title, (folder / f"{doc_id}.md").read_text(encoding="utf-8")))
    (tmp_path / "secret.env").write_text("TOKEN=abc", encoding="utf-8")
    return folder, docs


def snapshot(*roots: Path) -> dict[str, str]:
    found = {}
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            found[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


@pytest.mark.parametrize(
    "name",
    [
        "../x",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "corpus/../rag.yaml",
        "../secret.env",
        "corpus/inconnu.md",
        "inconnu",
    ],
)
def test_read_file_refuses_anything_but_an_active_document(tmp_path, name):
    folder, docs = corpus(tmp_path)
    before = snapshot(tmp_path, config.data_dir())
    out = Workspace(docs, "fr", estimate).read_file(name)
    assert not out.ok and out.doc is None
    assert out.text.startswith("Fichier absent")
    assert "corpus/teletravail.md" in out.text and "corpus/astreinte.md" in out.text
    assert "TOKEN" not in out.text
    assert snapshot(tmp_path, config.data_dir()) == before


def test_a_symbolic_link_in_the_corpus_folder_is_refused(tmp_path):
    folder, docs = corpus(tmp_path)
    link = folder / "lien.md"
    try:
        os.symlink(tmp_path / "secret.env", link)
    except (OSError, NotImplementedError):
        pytest.skip("the OS refuses to create a symbolic link (Windows without developer mode)")
    before = snapshot(tmp_path)
    tools = Workspace(docs, "fr", estimate)
    for name in ("corpus/lien.md", "lien.md", "lien"):
        out = tools.read_file(name)
        assert not out.ok and "TOKEN" not in out.text
    assert snapshot(tmp_path) == before


def test_read_file_by_its_virtual_name_or_its_name_alone(tmp_path):
    _, docs = corpus(tmp_path)
    tools = Workspace(docs, "fr", estimate)
    for name in (
        "corpus/teletravail.md",
        " corpus/teletravail.md ",
        "teletravail.md",
        "teletravail",
    ):
        out = tools.read_file(name)
        assert out.ok and out.doc is not None and out.doc.doc_id == "teletravail"
        assert "3 jours" in out.text


def test_list_files_lists_only_the_documents_given(tmp_path):
    _, docs = corpus(tmp_path)
    out = Workspace(docs[:1], "fr", estimate).list_files()
    assert out.ok and out.files == ("corpus/teletravail.md",)
    assert "Accord de télétravail" in out.text and "astreinte" not in out.text


def test_grep_is_the_rule_of_search_documents_on_the_same_texts():
    """On the shipped corpus read as `search_documents` reads it, the same lines, the same
    header: one function, `native.match_lines`."""
    content = load_rag_content("fr")
    docs = [
        DocText(PurePosixPath(d.file).stem, d.title_text, native._corpus_text(d.file, "fr"))
        for d in sorted(content.documents, key=lambda d: d.file)  # `corpus_files`' order
        if d.active
    ]
    tools = Workspace(docs, "fr", lambda _: 0)
    for query in ("télétravail jours", "mot de passe", "astreinte sécurité"):
        assert tools.grep(query).text == native.search_documents(query, "fr")
    pairs = [(f"corpus/{d.doc_id}.md", d.text) for d in docs]
    assert native.match_lines("Coffrix", pairs, "fr") == native.search_documents("Coffrix", "fr")
    with pytest.raises(ToolError):
        native.match_lines("de la", pairs, "fr")


def test_grep_without_a_word_or_a_hit_is_a_sentence_not_an_exception(tmp_path):
    _, docs = corpus(tmp_path)
    tools = Workspace(docs, "fr", estimate)
    empty, none = tools.grep("de la"), tools.grep("zzzinconnu")
    assert not empty.ok and "au moins un mot" in empty.text
    assert not none.ok and "Aucun résultat" in none.text
    hit = tools.grep("astreinte")
    assert hit.ok and hit.files == ("corpus/astreinte.md",)


def test_a_long_argument_and_a_long_result_are_cut(tmp_path):
    action = parse_action("ACTION: grep " + "a" * 500)
    assert action is not None and action.cut
    assert len(action.argument) == agent_tools.ACTION_ARG_MAX_CHARS
    long = DocText("long", "Long", "mot " * 3000)
    out = Workspace([long], "fr", estimate).read_file("corpus/long.md")
    assert out.ok and out.cut and out.text.endswith(agent_tools.CUT_MARK)
    assert estimate(out.text) <= agent_tools.AGENT_RESULT_MAX_TOKENS


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("ACTION: list_files", Action("list_files")),
        ("Je cherche.\naction : GREP télétravail jours", Action("grep", "télétravail jours")),
        (
            "**ACTION:** read_file `corpus/x.md`",
            Action("read_file", "corpus/x.md"),
        ),
        ("ACTION: ANSWER", Action("answer")),
        ("ACTION: grep a\nACTION: read_file corpus/x.md", Action("grep", "a")),
        ("ACTION: rm -rf /", Action("rm", "-rf /")),
    ],
)
def test_the_first_action_line_counts_whatever_its_case(answer, expected):
    assert parse_action(answer) == expected


def test_an_answer_without_an_action_line_is_unreadable():
    assert parse_action("Je pense que la réponse est 3 jours.") is None
    assert parse_action("") is None


def test_an_unknown_action_is_refused_by_a_sentence(tmp_path):
    _, docs = corpus(tmp_path)
    out = Workspace(docs, "fr", estimate).run(Action("rm", "-rf /"))
    assert not out.ok and "Action inconnue" in out.text


def test_the_work_copy_is_what_the_tools_see(tmp_path):
    """Criterion 4: a document added, one modified and one deleted in the work copy: the tools
    see the copy, never the shipped files; back to the shipped corpus, they see it again."""
    content = load_rag_content("fr")
    copy = workcopy.WorkCopy()
    copy = workcopy.apply(
        content, copy, "add", "note_flash", "Note flash", "Le code Zéphyr vaut 77."
    )
    copy = workcopy.apply(
        content, copy, "modify", "teletravail", "", "Ajout : le vendredi est libre."
    )
    copy = workcopy.apply(content, copy, "delete", "astreinte")
    tools = Workspace(workcopy.documents(content, "fr", copy), "fr", estimate)
    names = tools.list_files().files
    assert "corpus/note_flash.md" in names and "corpus/astreinte.md" not in names
    assert tools.grep("Zéphyr").ok and "corpus/teletravail.md" in tools.grep("vendredi").text
    assert tools.read_file("teletravail").text.startswith("# Accord de télétravail")
    assert not tools.read_file("corpus/astreinte.md").ok
    shipped = Workspace(workcopy.documents(content, "fr", None), "fr", estimate)
    assert shipped.read_file("corpus/astreinte.md").ok
    assert not shipped.read_file("corpus/note_flash.md").ok
    assert "est libre" not in shipped.grep("vendredi libre").text
