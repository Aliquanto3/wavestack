"""Builds the shipped LLM Wiki (V1.2 story 14, CAP-7): `content/rag_wiki.yaml` and its
translations `content/i18n/{en,de}/rag_wiki.yaml`.

The wiki of the active documents of the corpus, compiled by a deterministic rule with no model
(method `heuristic`): the index, a page per document (its first two sentences, its sentences with
a figure, its concepts), a page per concept (a word among the two best of a document by tf-idf,
named by two documents or more: the first sentence of each one that names it). The file carries
no duration: running it again gives the same files, byte for byte. No network, no model.

    uv run python tools/build_wiki.py [--lang fr|en|de ...] [--check]

`--check` writes nothing and exits 1 when a file differs from what the rule gives.

Pages written by a real model are not made here: « Reconstruire » in the RAG workshop writes
their syntheses with the active model into the workshop's data folder.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wavestack import config
from wavestack.rag import wiki
from wavestack.rag.corpus import load_rag_content, read_documents

LANGUAGES = ("fr", "en", "de")
COMMENT = (
    "# The LLM Wiki (V1.2 story 14). Built by tools/build_wiki.py, not by hand: compiled by a\n"
    "# rule, without a model; a page belongs to what it is compiled from by its sha256.\n"
)


def target(lang: str) -> Path:
    """Where the shipped file of `lang` lives."""
    root = config.content_dir()
    if lang == config.DEFAULT_LANGUAGE:
        return root / wiki.WIKI_FILE
    return root / "i18n" / lang / wiki.WIKI_FILE


def build(lang: str) -> str:
    """The text of the shipped file of `lang`."""
    content = load_rag_content(lang)
    documents = read_documents(content, lang)
    audiences = {d.id: d.audience for d in content.documents}
    concepts = wiki.select_concepts(documents, lang)
    pages = wiki.build_wiki(documents, lang, concepts, audiences)
    return wiki.dump(wiki.shipped_file(pages, concepts), COMMENT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--lang", nargs="+", choices=LANGUAGES, default=list(LANGUAGES))
    parser.add_argument("--check", action="store_true", help="write nothing, report differences")
    args = parser.parse_args(argv)
    differs = False
    for lang in args.lang:
        text, path = build(lang), target(lang)
        if args.check:
            current = path.read_text(encoding="utf-8") if path.is_file() else ""
            if current.replace("\r\n", "\n") != text:
                differs = True
                print(f"{path}: differs", file=sys.stderr)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"{path}: {text.count('- id:')} pages, {len(text.encode())} bytes")
    return 1 if differs else 0


if __name__ == "__main__":
    raise SystemExit(main())
