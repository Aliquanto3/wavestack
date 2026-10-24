"""MiniCPM5-2B: template recognition, `minicpm5` call reader, channels, full cycle."""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_engine import FakeEngine, booted_session
from test_turn import _run

from wavestack.context.render import render_template
from wavestack.models.capabilities import ChannelSplitter, capabilities_for, tool_call_tags
from wavestack.models.engine import EngineMetadata
from wavestack.tools.parser import ToolCall, parse_tool_calls

FIXTURES = Path(__file__).parent / "fixtures"
MINICPM5 = (FIXTURES / "minicpm5_chat_template.jinja").read_bytes().decode("utf-8")
QWEN = (FIXTURES / "qwen3_5_chat_template.jinja").read_bytes().decode("utf-8")


def fn(name: str, **params: str) -> str:
    body = "".join(f'<param name="{k}">{v}</param>' for k, v in params.items())
    return f'<function name="{name}">{body}</function>'


def parse(raw: str, schemas: dict | None = None):
    return parse_tool_calls(raw, "minicpm5", schemas or {})


def test_simple_call():
    calls, bad = parse(fn("calculator", expression="12*37"))
    assert bad is None
    assert calls == [ToolCall("calculator", {"expression": "12*37"})]
    assert calls[0].source == fn("calculator", expression="12*37")


def test_cdata_value_loses_its_envelope():
    raw = '<function name="x"><param name="code"><![CDATA[a < b && c\nd]]></param></function>'
    calls, bad = parse(raw)
    assert bad is None and calls[0].arguments == {"code": "a < b && c\nd"}


def test_entities_are_undone_outside_cdata():
    calls, _ = parse(fn("x", s="a &lt; b &amp;&amp; &quot;c&quot; &apos;d&apos; &gt;"))
    assert calls[0].arguments == {"s": "a < b && \"c\" 'd' >"}


def test_typing_follows_the_schema_and_keeps_text_on_failure():
    schemas = {"x": {"n": "integer", "m": "integer"}}
    calls, _ = parse(fn("x", n="42", m="abc"), schemas)
    assert calls[0].arguments == {"n": 42, "m": "abc"}


def test_several_calls_with_text_around():
    a, b = fn("a", p="1"), fn("b", q="2")
    calls, bad = parse(f"Avant {a} milieu {b} après")
    assert bad is None
    assert [(c.name, c.source) for c in calls] == [("a", a), ("b", b)]


def test_close_tag_inside_cdata_is_not_the_end():
    raw = '<function name="x"><param name="s"><![CDATA[x</function>y]]></param></function>'
    calls, bad = parse(raw)
    assert bad is None and len(calls) == 1 and calls[0].arguments == {"s": "x</function>y"}


def test_never_closed():
    calls, bad = parse('<function name="x"><param name="a">1</param>')
    assert calls == [] and bad is not None
    assert "jamais fermée" in str(bad.detail_text)


def test_a_new_call_before_the_close_means_never_closed():
    calls, bad = parse(fn_open := '<function name="a"><param name="x">1</param>' + fn("b", y="2"))
    assert calls == [] and bad is not None and bad.fragment == fn_open
    assert "jamais fermée" in str(bad.detail_text)
    raw = '<function name="a"><param name="s"><![CDATA[<function name="b">]]></param></function>'
    calls, bad = parse(raw)
    assert bad is None and calls[0].arguments == {"s": '<function name="b">'}


def test_output_cut_inside_a_call_takes_the_malformed_path():
    engine = FakeEngine(
        outputs=['<function name="calculator"><param name="expression">' + "1+" * 300, "Pardon."],
        template=MINICPM5,
        architecture="llama",
    )
    session = booted_session(engine)
    session.set_brick("tools", True)

    events = _run(session, "Calcule")

    assert events["output_truncated"][0]["channel"] == "tool_call"
    assert "coupée" in events["tool_call_malformed"][0]["detail_text"]


def test_param_not_closed():
    calls, bad = parse('<function name="x"><param name="a">1</function>')
    assert calls == [] and bad is not None
    assert "<param" in str(bad.detail_text) and "fermée" in str(bad.detail_text)


@pytest.mark.parametrize("raw", ['<function name=""></function>', '<function name="x'])
def test_missing_name_or_truncated_open_tag(raw):
    calls, bad = parse(raw)
    assert calls == [] and bad is not None
    assert "absente ou mal fermée" in str(bad.detail_text)


def test_no_call_no_error():
    assert parse("Juste du texte.") == ([], None)


def test_qwen_and_minicpm_tags():
    assert tool_call_tags("minicpm5") == ('<function name="', "</function>")
    assert tool_call_tags("qwen3_coder") == tool_call_tags("hermes") == tool_call_tags(None)


# ---------- capabilities ----------


@pytest.mark.parametrize("architecture", ["llama", None])
def test_capabilities_from_the_template(architecture):
    caps = capabilities_for(EngineMetadata(architecture, MINICPM5, None, "", "", ()))
    assert (caps.family, caps.tool_call_parser) == ("minicpm5", "minicpm5")
    assert caps.stop_sequences == ("<|im_end|>",)
    assert caps.reasoning is True and caps.reasoning_variable == "enable_thinking"
    assert caps.reasoning_tags == ("<think>", "</think>")


def test_qwen_template_is_unchanged():
    caps = capabilities_for(EngineMetadata("qwen35", QWEN, None, "", "", ()))
    assert (caps.family, caps.tool_call_parser) == ("qwen3", "qwen3_coder")


def test_call_in_reasoning_does_not_count():
    splitter = ChannelSplitter(
        ("<think>", "</think>"), in_reasoning=True, tool_tags=tool_call_tags("minicpm5")
    )
    splitter.feed(f"{fn('x', a='1')}</think>Fin")
    splitter.flush()
    assert parse(splitter.outside) == ([], None)


def test_splitter_sends_a_call_to_the_tool_call_channel():
    splitter = ChannelSplitter(("<think>", "</think>"), tool_tags=tool_call_tags("minicpm5"))
    out = splitter.feed("Je calcule." + fn("calculator", expression="1+1") + "Fin")
    out += splitter.flush()
    assert [c for c, _ in out] == ["text", "tool_call", "text"]
    assert "1+1" in out[1][1]
    assert parse(splitter.outside)[0][0].name == "calculator"


# ---------- render and full cycle ----------


def test_template_renders_tools_and_a_past_call():
    messages = [
        {"role": "user", "content": "12 * 37 ?"},
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
    text = render_template(MINICPM5, messages, tools=tools, add_generation_prompt=True)
    assert '<function name="calculator">' in text
    assert '<param name="expression">12*37</param>' in text
    assert "<tool_response>\n444\n</tool_response>" in text


def test_full_cycle_calculator():
    engine = FakeEngine(
        outputs=[
            "<think>\n\n</think>\n\n" + fn("calculator", expression="12*37"),
            "Cela fait 444.",
        ],
        template=MINICPM5,
        architecture="llama",
    )
    session = booted_session(engine)
    session.set_brick("tools", True)

    events = _run(session, "Combien font 12 × 37 ?")

    assert events["model_call_ended"][0]["tool_calls"] == [
        {"name": "calculator", "arguments": {"expression": "12*37"}}
    ]
    assert events["tool_ended"][0]["result"] == "444"
    second = "".join(s["text"] for s in events["context_rendered"][1]["segments"])
    assert "<tool_response>" in second
    assert events["turn_ended"][0]["status"] == "completed"
