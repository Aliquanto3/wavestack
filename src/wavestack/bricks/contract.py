"""The brick contract (AD-12) and its content loaders (AD-19)."""

from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from wavestack import config

Category = Literal["prompt", "context", "harness"]
# Story 33: the bricks panel's two groups, « Ce que le modèle lit » / « Ce que le harnais fait ».
PanelGroup = Literal["reads", "acts"]
Hosting = Literal["local_process", "local_file", "network_service"]
# V1.4-2: the harness map. The paper's seven subsystems (arXiv 2609.00006), and Böckeler's
# roles: a brick guides the model before it acts and/or senses what happens, by a computed
# rule or an inferred (model) judgement; no role at all = a capability given to the model.
Subsystem = Literal["loop", "llm", "tools", "memory", "security", "orchestration", "extensibility"]
SUBSYSTEMS: tuple[str, ...] = (
    "loop",
    "llm",
    "tools",
    "memory",
    "security",
    "orchestration",
    "extensibility",
)
HarnessRole = Literal["guide", "sensor"]
SensorKind = Literal["computed", "inferred"]


class Component(BaseModel):
    id: str  # "{brick}.{component}"
    kind: str
    hosting: Hosting
    edges_to: list[str] = []


class BrickDeclaration(BaseModel):
    id: str
    category: Category
    group: PanelGroup  # story 33: its group in the bricks panel, distinct from the category
    subsystem: Subsystem  # V1.4-2: its place on the harness map
    roles: list[HarnessRole] = []  # empty: a capability, neither guide nor sensor
    sensor_kind: SensorKind | None = None  # required with the `sensor` role, forbidden without
    requires: list[str] = []  # brick ids that must be effective
    capabilities: list[str] = []  # truthy `Capabilities` fields the model must offer (AD-6)
    network: bool = False
    contributes_to: list[str] = ["main"]
    components: list[Component]

    @model_validator(mode="after")
    def _sensor_kind_goes_with_the_sensor_role(self) -> BrickDeclaration:
        if ("sensor" in self.roles) != (self.sensor_kind is not None):
            raise ValueError(f"brick {self.id!r}: `sensor_kind` goes with the `sensor` role, only.")
        return self

    @model_validator(mode="after")
    def _component_ids_are_prefixed(self) -> BrickDeclaration:
        for component in self.components:
            if not component.id.startswith(f"{self.id}."):
                raise ValueError(f"component {component.id!r} must start with {self.id!r}.")
        return self


class BrickContent(BaseModel):
    """`content/bricks/{id}.yaml`: what the brick card says, in French."""

    label_text: str = Field(min_length=1)
    category_text: str = Field(min_length=1)
    hosting_text: str = Field(min_length=1)
    # Each item is a paragraph (`str`, rendered `<p>`) or a bullet list (`list[str]`, `<ul><li>`).
    explanation_text: list[str | list[str]] = Field(min_length=1)
    # Story 23, `tools` and `mcp`: what leaves the workstation and where to read it, a
    # template the session fills with `{tools}` and `{servers}` (network labels).
    outbound_text: str | None = None


class SystemPromptContent(BaseModel):
    text: str = Field(min_length=1)


def load_brick_content(brick_id: str, lang: str | None = None) -> BrickContent:
    """Raises on a missing or invalid file (the session traces it)."""
    path = config.content_file(f"bricks/{brick_id}.yaml", lang)
    return BrickContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_default_system_prompt(lang: str | None = None) -> str:
    """Raises on a missing or blank `content/prompts/system.md` (or its translation)."""
    path = config.content_file("prompts/system.md", lang)
    return SystemPromptContent(text=path.read_text(encoding="utf-8-sig").strip()).text
