"""Builds the shipped tree of PageIndex (V1.2 story 11, CAP-7): `content/rag_pageindex.yaml`
and its translations `content/i18n/{en,de}/rag_pageindex.yaml`.

The tree of the active documents of the corpus: the root, a node per document, a node per
section (the blocks between blank lines, the `# title` line left out), each with a title and a
summary written by a deterministic rule with no model (method `heuristic`): a section's title is
its first eight words, a summary the first sentence cut at 120 characters. The file carries no
duration: running it again gives the same files, byte for byte. No network, no model.

    uv run python tools/build_pageindex.py [--lang fr|en|de ...] [--check]

`--check` writes nothing and exits 1 when a file differs from what the rule gives.

Summaries written by a real model are not made here: « Reconstruire » in the RAG workshop writes
them with the active model into the workshop's data folder.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wavestack import config
from wavestack.rag import pageindex
from wavestack.rag.corpus import load_rag_content, read_documents

LANGUAGES = ("fr", "en", "de")
COMMENT = (
    "# PageIndex's tree of sections (V1.2 story 11). Built by tools/build_pageindex.py, not by\n"
    "# hand: computed by a rule, without a model; a node belongs to a text by its sha256.\n"
)


def target(lang: str) -> Path:
    """Where the shipped file of `lang` lives."""
    root = config.content_dir()
    if lang == config.DEFAULT_LANGUAGE:
        return root / pageindex.PAGEINDEX_FILE
    return root / "i18n" / lang / pageindex.PAGEINDEX_FILE


def build(lang: str) -> str:
    """The text of the shipped file of `lang`."""
    documents = read_documents(load_rag_content(lang), lang)
    return pageindex.dump(pageindex.shipped_file(pageindex.build_tree(documents)), COMMENT)


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
        print(f"{path}: {text.count('- id:')} nodes")
    return 1 if differs else 0


if __name__ == "__main__":
    raise SystemExit(main())
