"""The texts of the `subagent` brick (story 19, AD-11, AD-19): `content/subagent.yaml` for the
harness's words, `content/prompts/subagent.md` for the sub-agent's system prompt."""

from __future__ import annotations

import yaml
from pydantic import BaseModel, Field

from wavestack import config


class DelegateText(BaseModel):
    """The harness meta-tool `delegate` (AD-25): what the model reads."""

    description: str = Field(min_length=1)
    task: str = Field(min_length=1)  # the `task` parameter's description


class SubagentContent(BaseModel):
    delegate: DelegateText
    phase_label_text: str = Field(min_length=1)  # « Appel au sous-agent »
    overflow_cause_text: str = Field(min_length=1)
    prompt: str = Field(min_length=1)  # content/prompts/subagent.md


def load_subagent_content(lang: str | None = None) -> SubagentContent:
    """Raises on a missing or invalid file (the session traces it)."""
    data = yaml.safe_load(config.content_file("subagent.yaml", lang).read_text("utf-8")) or {}
    path = config.content_file("prompts/subagent.md", lang)
    prompt = path.read_text(encoding="utf-8-sig").strip()
    return SubagentContent.model_validate({**data, "prompt": prompt})
