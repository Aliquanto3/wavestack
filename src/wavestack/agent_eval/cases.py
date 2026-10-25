"""An agent case (V1.5 CAP-1): a prompt, a configuration, an optional history, one to three
checks read in the turn's journal, and its provenance. The contract is
`_bmad-output/specs/spec-wavestack-evaluer-l-agent/contrat-des-cas.md`; its names are kept
as they are (fields, `kind`, statuses).

A provided case comes from `content/agent_cases.yaml` (and its translations under
`content/i18n/{en,de}/`), a session case from `data_dir()/agent_cases.json` (`store.py`):
the same model for both.
"""

from __future__ import annotations

import secrets
from datetime import date, datetime
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from wavestack import config
from wavestack.trace.catalog import ActiveModel

PROVIDED_FILE = "agent_cases.yaml"

# The closed catalogue (contrat-des-cas.md); extending it is a change of spec.
CheckKind = Literal[
    "tool_called",
    "tool_not_called",
    "argument_never",
    "model_calls_max",
    "answer_contains",
    "hook_decided",
    "subagent_called",
    "turn_completed",
]
# CAP-4: a case's outcome in a run, and why it was not run.
RunStatus = Literal["passed", "failed", "not_run"]
NotRunReason = Literal["window", "cancelled", "budget"]
ProvenanceSource = Literal["fourni", "séance", "recette"]


class _Check(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolCalledCheck(_Check):
    kind: Literal["tool_called"]
    tool: str = Field(min_length=1)
    # The first `tool` precedes the first `before` (`before` never called: passes).
    before: str | None = Field(default=None, min_length=1)


class ToolNotCalledCheck(_Check):
    kind: Literal["tool_not_called"]
    tool: str = Field(min_length=1)


class ArgumentNeverCheck(_Check):
    kind: Literal["argument_never"]
    tool: str = Field(min_length=1)
    argument: str = Field(min_length=1)
    contains: str = Field(min_length=1)


class AnswerContainsCheck(_Check):
    kind: Literal["answer_contains"]
    text: str = Field(min_length=1)


class HookDecidedCheck(_Check):
    kind: Literal["hook_decided"]
    hook: str = Field(min_length=1)
    decision: Literal["block", "ask_human"]


class SubagentCalledCheck(_Check):
    kind: Literal["subagent_called"]


class TurnCompletedCheck(_Check):
    kind: Literal["turn_completed"]


# `model_calls_max` is never written in `checks`: it comes from `max_model_calls`.
Check = Annotated[
    ToolCalledCheck
    | ToolNotCalledCheck
    | ArgumentNeverCheck
    | AnswerContainsCheck
    | HookDecidedCheck
    | SubagentCalledCheck
    | TurnCompletedCheck,
    Field(discriminator="kind"),
]


class HistoryExchange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: str
    assistant: str


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: ProvenanceSource
    date: str = Field(min_length=1)  # ISO
    model: ActiveModel | None = None  # the original turn's model
    turn_id: str | None = None  # the original turn
    # The original turn's system prompt, kept even when the case does not fix it.
    system_prompt_text: str | None = None
    fixed_in: str | None = None  # « corrigé dans »

    @field_validator("date")
    @classmethod
    def _iso_date(cls, value: str) -> str:
        try:
            (date if len(value) == 10 else datetime).fromisoformat(value)
        except ValueError:
            raise ValueError(f"provenance date is not ISO: {value!r}") from None
        return value


# A check that only an event present satisfies (SPEC Constraints): an idle fake engine never
# passes it. `turn_completed` and the negatives pass on an idle turn.
POSITIVE_KINDS = frozenset({"tool_called", "answer_contains", "hook_decided", "subagent_called"})


class AgentCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title_text: str = Field(min_length=1)
    brick: str | None = None  # required for a provided case
    symptom_text: str = Field(min_length=1)
    assertion_text: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    history: list[HistoryExchange] = []
    # The whole configuration, applied as a scenario's; `None` keeps the launch values.
    bricks: list[str] = []
    tools: list[str] | None = None
    hooks: list[str] | None = None
    skills: list[str] | None = None
    mcp_servers: list[str] | None = None
    window: int | None = Field(default=None, ge=1)  # another than the current: `not_run`
    system_prompt: str | None = None  # `None`: the session's
    approval: Literal["refuse", "approve"] = "refuse"  # the harness's answer to H5
    on_overflow: Literal["none", "compaction", "sliding_window"] = "none"
    max_model_calls: int = Field(ge=1)  # always checked (`model_calls_max`)
    checks: list[Check] = Field(min_length=1, max_length=3)
    provenance: Provenance

    @model_validator(mode="after")
    def _id_matches_its_source(self) -> AgentCase:
        if self.provenance.source == "séance" and not self.id.startswith("u"):
            raise ValueError("a session case's id starts with `u`.")
        return self


class ProvidedCases(BaseModel):
    """`content/agent_cases.yaml`: `cases`, a list of cases."""

    model_config = ConfigDict(extra="forbid")

    cases: list[AgentCase] = []


_CASES = TypeAdapter(list[AgentCase])


def new_case_id() -> str:
    """A session case's id: `u` and a generated identifier."""
    return f"u{secrets.token_hex(4)}"


def check_unique_ids(cases: list[AgentCase]) -> None:
    """Raises `ValueError` when an id is used twice (provided and session together)."""
    seen: set[str] = set()
    twice: set[str] = set()
    for case in cases:
        (twice if case.id in seen else seen).add(case.id)
    if twice:
        raise ValueError(f"agent case ids used twice: {sorted(twice)}")


_CONFIG_FIELDS = ("bricks", "tools", "hooks", "skills", "mcp_servers")


def check_known_ids(cases: list[AgentCase], known: dict[str, set[str]]) -> None:
    """`known` maps `bricks`, `tools`, `mcp_servers`, `skills` and `hooks` to their ids, as
    for `load_scenarios`. Raises `ValueError` on any unknown id of a case's configuration."""
    unknown = [
        f"{case.id}.{field}: {i}"
        for case in cases
        for field in _CONFIG_FIELDS
        if field in known
        for i in getattr(case, field) or []
        if i not in known[field]
    ]
    if unknown:
        raise ValueError(f"agent cases: unknown ids {unknown}")


def load_provided_cases(
    lang: str | None = None, known: dict[str, set[str]] | None = None
) -> list[AgentCase]:
    """The provided cases in `lang` (the setting's language when `None`): the translated file
    when it exists, else the French one. No file: no case. Raises on an invalid file, an id
    twice, a case without `brick`, with a `system_prompt` or a `séance` provenance, without a
    check of `POSITIVE_KINDS`, or (with `known`) an unknown id."""
    path = config.content_file(PROVIDED_FILE, lang)
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases = ProvidedCases.model_validate(data).cases
    wrong = [
        c.id
        for c in cases
        if c.brick is None
        or c.system_prompt is not None
        or c.provenance.source == "séance"
        or not any(k.kind in POSITIVE_KINDS for k in c.checks)
    ]
    if wrong:
        raise ValueError(
            f"{path}: provided cases need a brick, no system prompt, no session provenance and"
            f" a check on an event present ({sorted(POSITIVE_KINDS)}): {wrong}"
        )
    check_unique_ids(cases)
    if known is not None:
        check_known_ids(cases, known)
    return cases


def validate_cases(data: object) -> list[AgentCase]:
    """A list of cases from JSON-like data (the session file's `cases`)."""
    return _CASES.validate_python(data)
