"""V1.4 story 2: the harness map. Every brick declares its subsystem and roles in the
registry; the labels of the 7 subsystems and of the roles exist in fr, en and de."""

from __future__ import annotations

import pytest
from fake_engine import FakeEngine, booted_session
from pydantic import ValidationError

from wavestack import ui_texts
from wavestack.bricks.contract import SUBSYSTEMS, BrickDeclaration, Component
from wavestack.bricks.registry import BRICKS
from wavestack.trace.catalog import BrickState
from wavestack.trace.journal import get_journal

LANGS = ["fr", "en", "de"]
ROLE_KEYS = ["guide", "sensor_computed", "sensor_inferred", "capability"]


def _component(brick_id: str) -> Component:
    return Component(id=f"{brick_id}.x", kind="fake", hosting="local_process")


def _declare(**kwargs) -> BrickDeclaration:
    return BrickDeclaration(
        id="b", category="harness", group="acts", components=[_component("b")], **kwargs
    )


@pytest.mark.parametrize("brick", BRICKS, ids=lambda b: b.id)
def test_every_brick_has_a_valid_subsystem_and_roles(brick):
    assert brick.subsystem in SUBSYSTEMS
    assert set(brick.roles) <= {"guide", "sensor"}
    assert ("sensor" in brick.roles) == (brick.sensor_kind in {"computed", "inferred"})


def test_the_placement_follows_the_map_of_the_harness():
    placed = {b.id: (b.subsystem, tuple(b.roles), b.sensor_kind) for b in BRICKS}
    assert placed["hooks"] == ("extensibility", ("guide", "sensor"), "computed")
    assert placed["guardrails"] == ("security", ("sensor",), "inferred")
    assert placed["system_prompt"] == ("memory", ("guide",), None)
    assert placed["reasoning"][0] == "llm" and placed["subagent"][0] == "orchestration"
    assert placed["tools"][0] == "tools" and placed["skills"][0] == "extensibility"


def test_a_sensor_needs_its_kind_and_a_kind_needs_the_sensor_role():
    with pytest.raises(ValidationError, match="sensor_kind"):
        _declare(subsystem="security", roles=["sensor"])
    with pytest.raises(ValidationError, match="sensor_kind"):
        _declare(subsystem="security", roles=["guide"], sensor_kind="computed")
    with pytest.raises(ValidationError):
        _declare(subsystem="nowhere")
    assert _declare(subsystem="security", roles=["sensor"], sensor_kind="inferred")


@pytest.mark.parametrize("lang", LANGS)
def test_every_subsystem_and_role_has_a_label_in_each_language(lang):
    texts = ui_texts.load_ui_texts(lang)["main"]["harness_map"]
    for subsystem in SUBSYSTEMS:
        assert texts["subsystems"][subsystem].strip(), (lang, subsystem)
    for role in ROLE_KEYS:
        assert texts["roles"][role].strip(), (lang, role)
    for subsystem in ("loop", "llm", "orchestration"):  # filled by the harness core
        assert texts["core"][subsystem].strip(), (lang, subsystem)
    assert "2609.00006" in texts["source_arxiv"] and "Böckeler" in texts["source_fowler"]


def test_the_paper_labels_are_the_translations_of_the_subsystems():
    en = ui_texts.load_ui_texts("en")["main"]["harness_map"]["subsystems"]
    assert en["tools"] == "Tools & actions" and en["security"] == "Safety & permissions"
    fr = ui_texts.load_ui_texts("fr")["main"]["harness_map"]["subsystems"]
    assert fr["tools"] == "Outils et actions" and fr["security"] == "Sécurité et permissions"
    de = ui_texts.load_ui_texts("de")["main"]["harness_map"]["subsystems"]
    assert de["tools"] == "Werkzeuge und Aktionen"
    assert de["security"] == "Sicherheit und Berechtigungen"


def test_bricks_changed_carries_the_placement_of_every_brick():
    session = booted_session(FakeEngine())
    mark = get_journal().last_seq()
    session.set_brick("short_memory", True)
    payload = [e.payload for e in get_journal().events_since(mark) if e.kind == "bricks_changed"][
        -1
    ]
    states = [BrickState(**b) for b in payload["bricks"]]
    assert {s.id for s in states} == {b.id for b in BRICKS}
    by_id = {s.id: s for s in states}
    assert by_id["hooks"].roles == ["guide", "sensor"] and by_id["hooks"].sensor_kind == "computed"
    assert all(s.subsystem in SUBSYSTEMS for s in states)
