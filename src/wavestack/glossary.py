"""The harness glossary (V1.5 story 6, CAP-6): `content/glossary.yaml` (French) and its
translations `content/i18n/{en,de}/glossary.yaml`, served by `GET /api/glossary` to `glossary.js`.

`terms` maps a key (`snake_case`, English) to `{term, definition}`. A text of a brick or of a
scenario cites a term with `[[g:key]]` or `[[g:key|displayed text]]` (`CITATION`; the `g:`
prefix keeps clear of the `[[page]]` wiki links some texts already contain). The interface
turns it into a link that opens the glossary on that term. Distinct from
`content/mcp_local/glossary.yaml`, a demonstration datum of the local MCP server."""

from __future__ import annotations

import re
from typing import Any

import yaml

from wavestack import config

# `[[g:key]]` or `[[g:key|displayed text]]`; glossary.js uses the same pattern.
CITATION = re.compile(r"\[\[g:([a-z][a-z0-9_]*)(?:\|([^\]]*))?\]\]")
KEY = re.compile(r"[a-z][a-z0-9_]*")


class GlossaryError(ValueError):
    """`glossary.yaml` does not have the expected shape."""


def load_terms(lang: str | None = None) -> dict[str, dict[str, str]]:
    """The terms in `lang` (the setting's language when `None`), `{key: {term, definition}}`."""
    path = config.content_file("glossary.yaml", lang)
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise GlossaryError(f"{path.name} : YAML invalide ({exc})") from exc
    terms = data.get("terms") if isinstance(data, dict) else None
    if not isinstance(terms, dict) or not terms:
        raise GlossaryError(f"{path.name} : une section « terms » non vide est attendue")
    for key, entry in terms.items():
        if not isinstance(key, str) or not KEY.fullmatch(key):
            raise GlossaryError(f"{key} : clé invalide")
        for field in ("term", "definition"):
            value = entry.get(field) if isinstance(entry, dict) else None
            if not isinstance(value, str) or not value.strip():
                raise GlossaryError(f"{key}.{field} : un texte non vide est attendu")
    return {k: {"term": v["term"], "definition": v["definition"]} for k, v in terms.items()}


def cited_keys(text: str) -> set[str]:
    """The keys a text cites with `[[g:key]]` or `[[g:key|displayed text]]`."""
    return {m.group(1) for m in CITATION.finditer(text)}
