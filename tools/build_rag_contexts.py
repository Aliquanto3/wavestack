"""Builds the shipped contexts of the contextual chunking (V1.2 story 6, CAP-4):
`content/rag_contexts.yaml` and its translations `content/i18n/{en,de}/rag_contexts.yaml`.

Each chunk of the corpus (cut by `paragraphs` at the shipped size) gets a short context, tied to
the chunk by the sha256 of its text. With no model, the context is written by a deterministic
rule (method `heuristic`, model `heuristic`): the chunk's rank among its document's chunks, the
document's title and how the document opens. Running it again gives the same files, byte for
byte. No network, no model.

    uv run python tools/build_rag_contexts.py [--lang fr|en|de ...] [--size N] [--check]

`--check` writes nothing and exits 1 when a file differs from what the rule gives.

A context written by a real model is not made here: « Reconstruire » in the RAG workshop makes
it with the active model into the workshop's data folder; copy that file over the shipped one
(its header then says `author: rebuilt`, `method: llm`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wavestack import config
from wavestack.messages import msg
from wavestack.rag import contexts
from wavestack.rag.corpus import chunk_documents, load_rag_content, read_documents

LANGUAGES = ("fr", "en", "de")
COMMENT = (
    "# Contexts of the contextual chunking (V1.2 story 6). Built by tools/build_rag_contexts.py,\n"
    "# not by hand: a context belongs to a chunk by the sha256 of its text.\n"
)


def target(lang: str) -> Path:
    """Where the shipped file of `lang` lives."""
    root = config.content_dir()
    if lang == config.DEFAULT_LANGUAGE:
        return root / contexts.CONTEXTS_FILE
    return root / "i18n" / lang / contexts.CONTEXTS_FILE


def build(lang: str, size: int) -> str:
    """The text of the shipped file of `lang` at chunk size `size`."""
    content = load_rag_content(lang)
    documents = read_documents(content, lang)
    chunks = chunk_documents(documents, size)

    def say(**kw: object) -> str:
        return msg("rag_lab.contexts.heuristic", lang, **kw)

    entries = contexts.heuristic_entries(documents, chunks, say)
    estimate = lambda text: config.estimate_tokens(text, 4.0)  # noqa: E731 - a fixed rule
    return contexts.dump(contexts.shipped_file(entries, size, estimate), COMMENT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--lang", nargs="+", choices=LANGUAGES, default=list(LANGUAGES))
    parser.add_argument("--size", type=int, default=config.load_config().rag_chunk_max_chars)
    parser.add_argument("--check", action="store_true", help="write nothing, report differences")
    args = parser.parse_args(argv)
    differs = False
    for lang in args.lang:
        text, path = build(lang, args.size), target(lang)
        if args.check:
            current = path.read_text(encoding="utf-8") if path.is_file() else ""
            if current.replace("\r\n", "\n") != text:
                differs = True
                print(f"{path}: differs", file=sys.stderr)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"{path}: {text.count('doc_id:')} contexts")
    return 1 if differs else 0


if __name__ == "__main__":
    raise SystemExit(main())
