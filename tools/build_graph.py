"""Builds the shipped knowledge graph of GraphRAG (V1.2 story 13, CAP-7): `content/rag_graph.yaml`
and its translations `content/i18n/{en,de}/rag_graph.yaml`.

The graph of the active documents of the corpus, by a deterministic rule with no model (method
`heuristic`, `rag/graph.py`): entities (key terms by tf-idf, acronyms, codes, proper names,
quoted terms), relations (two entities in one sentence), communities (local moves of
modularity) and their summaries (the main documents and the evidence's sentences). Each entity
and relation keeps its evidence, `doc_id#rank` of the paragraphs chunking with its sha256. The
file carries no duration: running it again gives the same files, byte for byte. No network, no
model.

    uv run python tools/build_graph.py [--lang fr|en|de ...] [--check]

`--check` writes nothing and exits 1 when a file differs from what the rule gives.

A graph extracted by a real model is not made here: « Reconstruire » in the RAG workshop writes
it with the active model into the workshop's data folder.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wavestack import config
from wavestack.rag import graph
from wavestack.rag.corpus import load_rag_content, read_documents

LANGUAGES = ("fr", "en", "de")
COMMENT = (
    "# GraphRAG's knowledge graph (V1.2 story 13). Built by tools/build_graph.py, not by hand:\n"
    "# computed by a rule, without a model; each evidence names a passage and its sha256.\n"
)


def target(lang: str) -> Path:
    """Where the shipped file of `lang` lives."""
    root = config.content_dir()
    if lang == config.DEFAULT_LANGUAGE:
        return root / graph.GRAPH_FILE
    return root / "i18n" / lang / graph.GRAPH_FILE


def build(lang: str, chunk_max_chars: int | None = None) -> str:
    """The text of the shipped file of `lang`."""
    content = load_rag_content(lang)
    audiences = {d.id: d.audience for d in content.documents}
    size = chunk_max_chars or config.Config(values={}).rag_chunk_max_chars  # the default: 700
    built = graph.build_graph(read_documents(content, lang), lang, size, audiences)
    return graph.dump(graph.shipped_file(built), COMMENT)


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
