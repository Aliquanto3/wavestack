"""The RAG workshop's agentic search (V1.2 story 11, CAP-7): three tools on the corpus.

The agent of the `agent_loop` Context searches the corpus itself, without an index: it lists the
documents (`list_files`), searches words in them (`grep`, the rule of the V1.4 tool
`search_documents`, `native.match_lines`) and reads one (`read_file`). The tools read the work
copy in memory (a list of `DocText`: the documents added, modified or deleted in the Build tab
included), never the disk: the model's argument is never joined to a path nor opened, it is only
compared with the virtual names `corpus/<doc_id>.md` of the active documents. They write nothing,
reach no network and run no command; they are not in `NATIVE_TOOLS` (the chat never sees them).
A refusal is a sentence for the model (the messages of `tools.read_file.*` and
`tools.search_documents.*`), never an exception out of the loop.

The protocol is plain text, the same for the local engine and the cloud: the model answers with a
line `ACTION: list_files`, `ACTION: grep <words>`, `ACTION: read_file <name>` or `ACTION: ANSWER`.
Only the model's lines are read for an action: a document's text is data, never an action.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from wavestack.messages import msg
from wavestack.rag.corpus import DocText
from wavestack.tools import native
from wavestack.tools.registry import ToolError

CORPUS_PREFIX = "corpus/"
ACTIONS = ("list_files", "grep", "read_file", "answer")
ACTION_ARG_MAX_CHARS = 200  # the characters of an action's argument kept
AGENT_RESULT_MAX_TOKENS = 400  # the estimated tokens of a tool's result kept
CUT_MARK = "[…]"
# The first line `ACTION: name argument` of an answer, whatever its case, a bullet or bold
# marks around it tolerated.
_ACTION = re.compile(r"^[\s>*_`-]*action[\s*_`]*:[\s*_`]*([a-z_]+)[\s*_`]*(.*)$", re.I)
_QUOTES = " \t\"'`«»“”*"


@dataclass(frozen=True)
class Action:
    """An action the model asked for: its name (lower case, `answer` for `ANSWER`, or what the
    model wrote when it is none of `ACTIONS`) and its argument, cut at `ACTION_ARG_MAX_CHARS`."""

    name: str
    argument: str = ""
    cut: bool = False

    @property
    def known(self) -> bool:
        return self.name in ACTIONS


@dataclass(frozen=True)
class AgentResult:
    """What a tool gave back: `ok` (else a refusal, `text` says why to the model), the text,
    the document it read (`read_file`), the files a `grep` matched, and whether it was cut."""

    ok: bool
    text: str
    doc: DocText | None = None
    files: tuple[str, ...] = ()
    cut: bool = False


def parse_action(answer: str) -> Action | None:
    """The first `ACTION:` line of a model's answer, or `None` when it has none (unreadable)."""
    for line in answer.splitlines():
        found = _ACTION.match(line.strip())
        if found is None:
            continue
        name = found.group(1).casefold()
        argument = found.group(2).strip().strip(_QUOTES).strip()
        cut = len(argument) > ACTION_ARG_MAX_CHARS
        return Action(name, argument[:ACTION_ARG_MAX_CHARS], cut)
    return None


def virtual_name(doc_id: str) -> str:
    return f"{CORPUS_PREFIX}{doc_id}.md"


def cut_to_tokens(text: str, max_tokens: int, estimate: Callable[[str], int]) -> tuple[str, bool]:
    """`text` cut so that its estimated tokens, `CUT_MARK` included, stay within `max_tokens`
    (`(text, False)` when it already fits)."""
    if estimate(text) <= max_tokens:
        return text, False
    low, high = 0, len(text)
    while low < high:  # the longest prefix that fits with the mark
        middle = (low + high + 1) // 2
        if estimate(f"{text[:middle].rstrip()} {CUT_MARK}") <= max_tokens:
            low = middle
        else:
            high = middle - 1
    return f"{text[:low].rstrip()} {CUT_MARK}".lstrip(), True


class Workspace:
    """The tools on one list of documents (the chain's: the work copy while it differs), in a
    language. Nothing here touches a file."""

    def __init__(self, docs: Sequence[DocText], lang: str, estimate: Callable[[str], int]) -> None:
        self.docs = list(docs)
        self.lang = lang
        self.estimate = estimate
        self.names = {virtual_name(d.doc_id): d for d in self.docs}

    def _said(self, error: ToolError) -> str:
        return error.render(self.lang)

    def _bounded(self, result: AgentResult) -> AgentResult:
        text, cut = cut_to_tokens(result.text, AGENT_RESULT_MAX_TOKENS, self.estimate)
        if not cut:
            return result
        return AgentResult(result.ok, text, result.doc, result.files, True)

    def resolve(self, name: str) -> DocText | None:
        """The active document `name` designates: its virtual name exactly, or the name without
        its folder (`teletravail.md`, `teletravail`) when one document only has it. Anything
        else (a path that leaves the corpus, an absolute path, a link, an unknown name): `None`."""
        wanted = name.strip()
        if wanted in self.names:
            return self.names[wanted]
        if "/" in wanted or "\\" in wanted or ".." in wanted:
            return None
        found = [d for d in self.docs if wanted in (d.doc_id, f"{d.doc_id}.md")]
        return found[0] if len(found) == 1 else None

    def list_files(self) -> AgentResult:
        lines = [f"{name} — {doc.title_text}" for name, doc in self.names.items()]
        text = msg("tools.read_file.listing", self.lang, files="\n".join(lines))
        return self._bounded(AgentResult(True, text, files=tuple(self.names)))

    def grep(self, terms: str) -> AgentResult:
        pairs = [(name, doc.text) for name, doc in self.names.items()]
        try:
            text = native.match_lines(terms, pairs, self.lang)
        except ToolError as error:
            return AgentResult(False, self._said(error))
        files = tuple(n for n in self.names if f"\n{n}:" in f"\n{text}")
        return self._bounded(AgentResult(True, text, files=files))

    def read_file(self, name: str) -> AgentResult:
        doc = self.resolve(name)
        if doc is None:
            refused = ToolError("tools.read_file.missing", path=name, files=", ".join(self.names))
            return AgentResult(False, self._said(refused))
        return self._bounded(
            AgentResult(True, doc.text, doc=doc, files=(virtual_name(doc.doc_id),))
        )

    def run(self, action: Action) -> AgentResult:
        """An action other than `answer`, run; an unknown one is refused (said to the model)."""
        if action.name == "list_files":
            return self.list_files()
        if action.name == "grep":
            return self.grep(action.argument)
        if action.name == "read_file":
            return self.read_file(action.argument)
        return AgentResult(
            False, msg("rag_lab.agent.unknown_action", self.lang, action=action.name)
        )


__all__ = [
    "ACTIONS",
    "ACTION_ARG_MAX_CHARS",
    "AGENT_RESULT_MAX_TOKENS",
    "Action",
    "AgentResult",
    "Workspace",
    "cut_to_tokens",
    "parse_action",
    "virtual_name",
]
