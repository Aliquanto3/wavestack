"""Builds the shipped tree of summaries of RAPTOR (V1.2 story 12, CAP-7): `content/rag_raptor.yaml`
and its translations `content/i18n/{en,de}/rag_raptor.yaml`.

The tree of the active documents of the corpus, by a deterministic rule with no model (method
`heuristic`, `rag/raptor.py`): the passages of the paragraphs chunking (`doc_id#rank` and their
sha256) clustered level by level (average linkage on the cosine of their words), each summary
node summarized by the rule (its children's closest sentences). The file carries no duration:
running it again gives the same files, byte for byte. No network, no model.

    uv run python tools/build_raptor.py [--lang fr|en|de ...] [--check]

`--check` writes nothing and exits 1 when a file differs from what the rule gives.

A tree summarized by a real model is not made here: « Reconstruire l'arbre » in the RAG workshop
writes it with the active model into the workshop's data folder.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wavestack import config
from wavestack.rag import raptor
from wavestack.rag.corpus import load_rag_content, read_documents

LANGUAGES = ("fr", "en", "de")
COMMENT = (
    "# RAPTOR's tree of summaries (V1.2 story 12). Built by tools/build_raptor.py, not by hand:\n"
    "# computed by a rule, without a model; each leaf names a passage and its sha256.\n"
)


def target(lang: str) -> Path:
    """Where the shipped file of `lang` lives."""
    root = config.content_dir()
    if lang == config.DEFAULT_LANGUAGE:
        return root / raptor.RAPTOR_FILE
    return root / "i18n" / lang / raptor.RAPTOR_FILE


def build(lang: str, chunk_max_chars: int | None = None) -> str:
    """The text of the shipped file of `lang`."""
    content = load_rag_content(lang)
    audiences = {d.id: d.audience for d in content.documents}
    size = chunk_max_chars or config.Config(values={}).rag_chunk_max_chars  # the default: 700
    built = raptor.build_tree(read_documents(content, lang), lang, size, audiences)
    return raptor.dump(raptor.to_file(built), COMMENT)


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
        print(f"{path}: {len(text.encode()) // 1024} Ko")
    return 1 if differs else 0


if __name__ == "__main__":
    raise SystemExit(main())
