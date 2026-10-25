"""The session's agent cases (V1.5 CAP-3, D4): `data_dir()/agent_cases.json`, user data out
of the repository, `{"version": 1, "cases": [...]}`, written atomically as the global memory
(`memory.write_memory`). The session's reset never touches it; « Effacer mes cas » is
`clear_session_cases`. An unreadable file raises `SessionCasesUnreadable`: the view says it
and offers to clear; the provided cases stay playable.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path

from wavestack import config
from wavestack.agent_eval.cases import AgentCase, check_unique_ids, validate_cases

VERSION = 1


class SessionCasesUnreadable(Exception):
    """The session file exists but cannot be read, parsed or validated."""


def _path(path: Path | None) -> Path:
    return path if path is not None else config.agent_cases_path()


def read_session_cases(path: Path | None = None) -> list[AgentCase]:
    """The session cases; none when the file does not exist. Raises
    `SessionCasesUnreadable` on an unreadable or invalid file, another version, or an id
    twice."""
    path = _path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError) as exc:
        raise SessionCasesUnreadable(f"{path}: {exc}") from exc
    try:
        data = json.loads(text)
        if not isinstance(data, dict) or data.get("version") != VERSION:
            raise ValueError(f"expected an object of version {VERSION}")
        if set(data) - {"version", "cases"}:
            raise ValueError(f"unexpected keys {sorted(set(data) - {'version', 'cases'})}")
        cases = validate_cases(data.get("cases", []))
        check_unique_ids(cases)
    except ValueError as exc:  # JSONDecodeError and ValidationError included
        raise SessionCasesUnreadable(f"{path}: {exc}") from exc
    if any(c.provenance.source != "séance" for c in cases):
        raise SessionCasesUnreadable(f"{path}: a session case has another provenance")
    return cases


def write_session_cases(cases: Iterable[AgentCase], path: Path | None = None) -> None:
    """An atomic replace (temporary file, then `os.replace`). Raises OSError on failure,
    `ValueError` on an id twice."""
    cases = list(cases)
    check_unique_ids(cases)
    path = _path(path)
    data = {"version": VERSION, "cases": [c.model_dump(mode="json") for c in cases]}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def add_session_case(
    case: AgentCase, provided: Iterable[AgentCase] = (), path: Path | None = None
) -> list[AgentCase]:
    """Appends a session case and returns the session cases. Raises `ValueError` when it is
    not a `séance` case or its id is already used (provided or session), and
    `SessionCasesUnreadable` on an unreadable file (clear it first)."""
    if case.provenance.source != "séance":
        raise ValueError("a session case has the `séance` provenance")
    cases = [*read_session_cases(path), case]
    check_unique_ids([*provided, *cases])
    write_session_cases(cases, path)
    return cases


def delete_session_case(case_id: str, path: Path | None = None) -> bool:
    """Deletes a session case; `False` when there is none of that id (a provided case is
    never deleted)."""
    cases = read_session_cases(path)
    kept = [c for c in cases if c.id != case_id]
    if len(kept) == len(cases):
        return False
    write_session_cases(kept, path)
    return True


def clear_session_cases(path: Path | None = None) -> None:
    """« Effacer mes cas »: an empty file, whatever the previous one held (readable or not)."""
    write_session_cases([], path)
