"""V1.2 story 19 (CAP-16, CAP-17): the component sheets and the architecture sheets, with the
seven-axis compliance sheet, of the « Fiches » tab.

Declared content, read only (AD-1): nothing is computed, no model, no network. One source per
datum: the label of an architecture, its erasure places and its update cost in words are read from
`rag_erasure.yaml` (story 18, `erasure.load_erasure`), `available` from `lab.PRESETS`, the levels
share the vocabulary of the Security page's risk matrix (`mcp.policy.RISKS`). A level states an
exposure, never a verdict of compliance; the regulatory axis has none.
"""

from __future__ import annotations

from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from wavestack import config
from wavestack.mcp.policy import RISKS
from wavestack.rag import erasure, lab

FILE = "rag_sheets.yaml"
# The families of `lab.OPTIONS` whose component sheets are still to come: empty since story 19b
# (end of CAP-17). A family added to `OPTIONS` goes here until its sheets are written, or in
# `lab.SHEETED_KINDS` with them; `missing_sheets()` fails otherwise.
PENDING_SHEET_KINDS: tuple[str, ...] = ()
AXES = ("location", "copies", "erasure", "rights", "injection", "traceability", "regulatory")
DEMO_OF_AXIS = {
    "erasure": "rag-erasure-card",
    "rights": "rag-access-card",
    "injection": "rag-atk-title",
}
LocationClass = Literal["local", "cloud_eu", "secnumcloud", "outside_eu", "depends_on_provider"]


class UnknownSheet(KeyError):
    """No such sheet: the endpoint answers 404."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class LocatedComponent(_Strict):
    id: Literal["documents", "index", "derived", "cache", "generation", "judge", "trace_export"]
    cls: LocationClass = Field(alias="class")


class Axis(_Strict):
    level: str | None = None
    text: str = Field(min_length=1)
    demo: str | None = None
    components: list[LocatedComponent] | None = None
    before_search: bool | None = None  # rights axis only: a check before the search is possible


class ArchitectureSheet(_Strict):
    id: erasure.Architecture
    story: int | None = None
    hypotheses: list[str] = Field(min_length=1)
    purpose_text: str = Field(min_length=1)
    when_text: str = Field(min_length=1)
    cost_text: str = Field(min_length=1)
    literature_text: str = Field(min_length=1)
    bench_text: str = ""
    no_source_text: str | None = None
    sources: list[lab.SourceText] = Field(min_length=1)
    axes: dict[str, Axis]

    @model_validator(mode="after")
    def _shape(self) -> ArchitectureSheet:
        if tuple(self.axes) != AXES:
            raise ValueError(f"{self.id}: exactly the axes {', '.join(AXES)}, in order")
        for name, axis in self.axes.items():
            if name == "regulatory":
                if axis.level is not None:
                    raise ValueError("the regulatory axis has no level")
            elif axis.level not in RISKS:
                raise ValueError(f"{self.id}.{name}: a level among {', '.join(RISKS)}")
            if axis.demo != DEMO_OF_AXIS.get(name):
                raise ValueError(f"{self.id}.{name}: demo {DEMO_OF_AXIS.get(name)!r}")
            if name == "location":
                if not axis.components:
                    raise ValueError(f"{self.id}.location: components are required")
            elif axis.components is not None:
                raise ValueError(f"{self.id}.{name}: components belong to the location axis")
            if (axis.before_search is not None) != (name == "rights"):
                raise ValueError(f"{self.id}.{name}: before_search belongs to the rights axis")
        if (self.id in lab.PRESETS) == (self.story is not None):
            raise ValueError(f"{self.id}: a story if and only if it is not a workshop preset")
        return self


class SheetsContent(_Strict):
    texts: dict[str, Any]
    architectures: list[ArchitectureSheet]

    @model_validator(mode="after")
    def _shape(self) -> SheetsContent:
        if [a.id for a in self.architectures] != list(erasure.ARCHITECTURES):
            raise ValueError("one sheet per architecture of the erasure card, in order")
        return self


def load_sheets(lang: str | None = None) -> SheetsContent:
    """Raises on a missing or invalid file: the content's own test is what fails."""
    path = config.content_file(FILE, lang)
    return SheetsContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def missing_sheets() -> list[str]:
    """What has no sheet: a preset without an architecture sheet, a family of options neither
    sheeted nor pending (or both). Empty when the partition holds."""
    problems = [
        f"family {k!r}: neither sheeted nor pending"
        for k in lab.OPTIONS
        if k not in lab.SHEETED_KINDS and k not in PENDING_SHEET_KINDS
    ]
    problems += [
        f"family {k!r}: both sheeted and pending"
        for k in lab.SHEETED_KINDS
        if k in PENDING_SHEET_KINDS
    ]
    problems += [
        f"family {k!r}: pending but not in OPTIONS"
        for k in PENDING_SHEET_KINDS
        if k not in lab.OPTIONS
    ]
    have = {a.id for a in load_sheets().architectures}
    problems += [f"preset {p!r}: no architecture sheet" for p in lab.PRESETS if p not in have]
    return problems


def listing(lang: str) -> dict[str, Any]:
    """`GET /api/rag_lab/sheets`: components sheeted, architectures, families pending."""
    lang = config.as_language(lang)
    content = load_sheets(lang)
    texts = content.texts
    lab_content = lab.load_lab_content(lang)
    info = erasure.load_erasure(lang)
    components = [
        {
            "key": f"{kind}.{option}",
            "kind": kind,
            "kind_label_text": lab_content.stages[kind].label_text,
            "label_text": lab_content.options[kind][option].label_text,
        }
        for kind in lab.SHEETED_KINDS
        for option in lab.OPTIONS[kind]
    ]
    pending = [
        {"kind": k, "label_text": lab_content.stages[k].label_text} for k in PENDING_SHEET_KINDS
    ]
    return {
        "lang": lang,
        "texts": texts,
        "components": components,
        "architectures": [
            {
                "id": a.id,
                "label_text": info.architecture(a.id).label_text,
                "available": a.id in lab.PRESETS,
                "story": a.story,
            }
            for a in content.architectures
        ],
        "pending": pending,
        "pending_text": (
            texts["pending_text"].format(kinds=", ".join(p["label_text"] for p in pending))
            if pending
            else ""
        ),
    }


def component(lang: str, key: str) -> dict[str, Any]:
    """`GET /api/rag_lab/sheets/component/{kind}.{option}`: five blocks and the sources."""
    lang = config.as_language(lang)
    lab_content = lab.load_lab_content(lang)
    kind, _, option = key.partition(".")
    if kind not in lab.SHEETED_KINDS or option not in lab.OPTIONS.get(kind, ()):
        raise UnknownSheet(key)
    return {
        "key": key,
        "kind": kind,
        "kind_label_text": lab_content.stages[kind].label_text,
        "label_text": lab_content.options[kind][option].label_text,
        **lab_content.sheets[key].model_dump(),
    }


def architecture(lang: str, arch_id: str) -> dict[str, Any]:
    """`GET /api/rag_lab/sheets/architecture/{id}`: five blocks, the sources, the seven axes, the
    erasure places and the update cost of the story 18 joined."""
    lang = config.as_language(lang)
    content = load_sheets(lang)
    sheet = next((a for a in content.architectures if a.id == arch_id), None)
    if sheet is None:
        raise UnknownSheet(arch_id)
    info = erasure.load_erasure(lang)
    base = info.architecture(arch_id)
    axes = []
    for name, axis in sheet.axes.items():
        row: dict[str, Any] = {
            "id": name,
            "level": axis.level,
            "text": axis.text,
            "demo": axis.demo,
        }
        if axis.components is not None:
            row["components"] = [{"id": c.id, "class": c.cls} for c in axis.components]
        if axis.before_search is not None:
            row["before_search"] = axis.before_search
        if name == "erasure":
            row["places"] = [
                {"id": p.id, "label_text": p.label_text}
                for p in info.places
                if arch_id in p.architectures
            ]
            row["update_text"] = base.update_text
        axes.append(row)
    return {
        "id": arch_id,
        "label_text": base.label_text,
        "available": arch_id in lab.PRESETS,
        "story": sheet.story,
        "hypotheses": sheet.hypotheses,
        "purpose_text": sheet.purpose_text,
        "when_text": sheet.when_text,
        "cost_text": sheet.cost_text,
        "literature_text": sheet.literature_text,
        "bench_text": sheet.bench_text,
        "no_source_text": sheet.no_source_text,
        "sources": [s.model_dump() for s in sheet.sources],
        "axes": axes,
        "banner_text": content.texts["banner_text"],
    }
