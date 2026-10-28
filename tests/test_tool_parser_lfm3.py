"""LFM3-1.7B: ChatML with Qwen3's `<function=` call format, whatever the architecture.

Fixture: `tokenizer.chat_template` read from the GGUF header of
`LiquidAI/LFM3-1.7B-GGUF`'s `LFM3-1.7B-QAD-Q4_0.gguf` (Hugging Face), licence `lfm1.0`.
"""

from __future__ import annotations

from pathlib import Path

from wavestack.context.render import render_template
from wavestack.models.capabilities import capabilities_for
from wavestack.models.engine import EngineMetadata
from wavestack.tools.parser import ToolCall, parse_tool_calls

FIXTURES = Path(__file__).parent / "fixtures"
LFM3 = (FIXTURES / "lfm3_chat_template.jinja").read_bytes().decode("utf-8")


def meta(architecture: str | None, template: str) -> EngineMetadata:
    return EngineMetadata(architecture, template, None, "", "", ())


def test_lfm3_in_direct_gets_its_own_family():
    caps = capabilities_for(meta("lfm3", LFM3))
    assert (caps.family, caps.tool_call_parser) == ("lfm3", "qwen3_coder")
    assert caps.stop_sequences == ("<|im_end|>",)
    assert caps.reasoning_variable == "enable_thinking"
    assert caps.reasoning_tags == ("<think>", "</think>")
    assert caps.reasoning is True
    assert caps.incompatible_reason is None


def test_lfm3_served_by_llama_server_gets_qwen3():
    caps = capabilities_for(meta(None, LFM3))
    assert (caps.family, caps.tool_call_parser) == ("qwen3", "qwen3_coder")
    assert caps.stop_sequences == ("<|im_end|>",)
    assert caps.reasoning_variable == "enable_thinking"
    assert caps.reasoning_tags == ("<think>", "</think>")
    assert caps.reasoning is True


def test_round_trip_calculator_call():
    messages = [
        {"role": "user", "content": "Combien font 12 x 37 ?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "calculator", "arguments": {"expression": "12*37"}}}
            ],
        },
    ]
    tools = [{"type": "function", "function": {"name": "calculator", "parameters": {}}}]
    text = render_template(LFM3, messages, tools=tools, add_generation_prompt=False)
    calls, bad = parse_tool_calls(text, "qwen3_coder", {})
    assert bad is None
    assert calls == [ToolCall("calculator", {"expression": "12*37"})]


def test_generation_prompt_opens_think_tags_per_enable_thinking():
    messages = [{"role": "user", "content": "bonjour"}]
    thinking = render_template(LFM3, messages, add_generation_prompt=True, enable_thinking=True)
    assert thinking.endswith("<think>")
    no_thinking = render_template(LFM3, messages, add_generation_prompt=True, enable_thinking=False)
    assert no_thinking.endswith("<think></think>")
