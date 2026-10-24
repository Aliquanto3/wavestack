"""Granite 4.0 Nano: `<tool_call>` JSON calls, template recognition, full cycle."""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_engine import FakeEngine, booted_session
from test_turn import _run

from wavestack.context.render import render_template
from wavestack.models.capabilities import capabilities_for
from wavestack.models.engine import EngineMetadata
from wavestack.tools.parser import ToolCall, parse_tool_calls

FIXTURES = Path(__file__).parent / "fixtures"
GRANITE = (FIXTURES / "granite4_chat_template.jinja").read_bytes().decode("utf-8")
QWEN = (FIXTURES / "qwen3_5_chat_template.jinja").read_bytes().decode("utf-8")
MINICPM5 = (FIXTURES / "minicpm5_chat_template.jinja").read_bytes().decode("utf-8")
CHATML_TOOLS = (
    "{% for m in messages %}<|im_start|>{{ m.role }}\n{{ m.content }}<|im_end|>\n{% endfor %}"
    "{% if tools %}<tool_call>\n{}\n</tool_call>{% endif %}"
)
GEMMA = (
    "{% for m in messages %}<start_of_turn>{{ m.role }}\n{{ m.content }}<end_of_turn>\n{% endfor %}"
)


def meta(arch: str | None, template: str) -> EngineMetadata:
    return EngineMetadata(arch, template, None, "", "", ())


def test_call():
    raw = '<tool_call>\n{"name": "calculator", "arguments": {"expression": "12*37"}}\n</tool_call>'
    calls, bad = parse_tool_calls(raw, "hermes", {})
    assert bad is None
    assert calls == [ToolCall("calculator", {"expression": "12*37"})]


def test_unreadable_json():
    calls, bad = parse_tool_calls("<tool_call>{name: x</tool_call>", "hermes", {})
    assert calls == [] and bad is not None


@pytest.mark.parametrize("architecture", ["granite", None])
def test_granite_capabilities(architecture):
    caps = capabilities_for(meta(architecture, GRANITE))
    assert (caps.family, caps.tool_call_parser) == (architecture or "unknown", "hermes")
    assert caps.stop_sequences == ("<|end_of_text|>",)
    assert caps.reasoning is False and caps.reasoning_variable is None


def test_chatml_with_tool_call_gets_hermes():
    caps = capabilities_for(meta("qwen2", CHATML_TOOLS))
    assert caps.tool_call_parser == "hermes" and caps.stop_sequences == ("<|im_end|>",)


def test_other_families_unchanged():
    qwen = capabilities_for(meta("qwen35", QWEN))
    assert (qwen.family, qwen.tool_call_parser) == ("qwen3", "qwen3_coder")
    mini = capabilities_for(meta("llama", MINICPM5))
    assert (mini.family, mini.tool_call_parser) == ("minicpm5", "minicpm5")
    assert capabilities_for(meta("gemma3", GEMMA)).tool_call_parser is None


def test_render_with_tool_and_past_call():
    messages = [
        {"role": "user", "content": "Combien font 12 × 37 ?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "calculator", "arguments": {"expression": "12*37"}}}
            ],
        },
        {"role": "tool", "content": "444"},
    ]
    tools = [{"type": "function", "function": {"name": "calculator", "parameters": {}}}]
    text = render_template(GRANITE, messages, tools=tools, add_generation_prompt=True)
    assert '<tool_call>\n{"name": "calculator"' in text
    assert "444" in text


def test_full_cycle_calculator():
    engine = FakeEngine(
        outputs=[
            "<tool_call>\n"
            '{"name": "calculator", "arguments": {"expression": "12*37"}}\n'
            "</tool_call>",
            "Cela fait 444.",
        ],
        template=GRANITE,
        architecture="granite",
    )
    session = booted_session(engine)
    session.set_brick("tools", True)

    events = _run(session, "Combien font 12 × 37 ?")

    assert events["model_call_ended"][0]["tool_calls"] == [
        {"name": "calculator", "arguments": {"expression": "12*37"}}
    ]
    assert events["tool_ended"][0]["result"] == "444"
    second = "".join(s["text"] for s in events["context_rendered"][1]["segments"])
    assert "444" in second and '"name": "calculator"' in second
    assert "harness_error" not in events
    assert events["turn_ended"][0]["status"] == "completed"
