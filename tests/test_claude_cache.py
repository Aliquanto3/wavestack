"""V1.3 story 5: Claude's prompt cache (`off`, `5m`, `1h`), one test per row of the I/O
matrix. A fake Anthropic (`httpx.MockTransport`) captures the bodies sent: no real call."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import SecretStr
from test_anthropic_messages import (
    PLAIN_TEXT,
    Provider,
    _entry,
    _session,
    end,
    sse,
    start,
    text,
)
from test_cloud import _of, _turn

from wavestack import config
from wavestack.cloud import chat_fields
from wavestack.context.render import render_chat_body
from wavestack.context.segments import Part, SegmentKind
from wavestack.models.cloud_base import (
    CACHE_WRITE_1H_FACTOR,
    cache_savings,
    call_cost,
    reset_spend,
    session_cap_error,
    write_1h_price,
)
from wavestack.session.app_session import SendRefused
from wavestack.trace.journal import get_journal

FIVE = {"type": "ephemeral"}
HOUR = {"type": "ephemeral", "ttl": "1h"}
TOOLS = [
    {"type": "function", "function": {"name": "a", "description": "A", "parameters": {}}},
    {"type": "function", "function": {"name": "b", "description": "B", "parameters": {}}},
]


def _body(
    messages: list[dict[str, Any]],
    tools: Any = None,
    ttl: str | None = None,
    api: str = "anthropic_messages",
) -> tuple[dict[str, Any], str, list]:
    cfg = config.load_config()
    rendered = render_chat_body(
        messages,
        tools,
        call_id="t1.c1",
        fields=chat_fields(_entry(), 512),
        markers=cfg.cloud_markers,
        estimate=lambda t: config.estimate_tokens(t, cfg.chars_per_token),
        provider_label_text="chez le fournisseur",
        api=api,
        cache_ttl=ttl,
    )
    return json.loads(rendered.body), rendered.body, rendered.segments


def _chat(system: str = "Système.", user: str = "Bonjour.") -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, user)]}
    ]
    if system:
        messages.insert(0, {"role": "system", "content": [Part(SegmentKind.SYSTEM_PROMPT, system)]})
    return messages


def _strip(value: Any) -> Any:
    """The same body without its cache points."""
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k != "cache_control"}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def _points(body: dict[str, Any]) -> list[str]:
    found = []
    if any("cache_control" in tool for tool in body.get("tools", [])):
        found.append("tools")
    if isinstance(body.get("system"), list) and "cache_control" in body["system"][-1]:
        found.append("system")
    last = body["messages"][-1]["content"] if body.get("messages") else None
    if isinstance(last, list) and "cache_control" in last[-1]:
        found.append("message")
    return found


# ---------- the translator ----------


def test_off_sends_the_body_as_before():
    body, raw, _ = _body(_chat(), TOOLS)
    assert "cache_control" not in raw
    assert body["system"] == "Système."
    assert body["messages"] == [{"role": "user", "content": "Bonjour."}]


@pytest.mark.parametrize(("ttl", "point"), [("5m", FIVE), ("1h", HOUR)])
def test_the_three_points_carry_the_duration(ttl, point):
    body, raw, segments = _body(_chat(), TOOLS, ttl)
    assert body["system"] == [{"type": "text", "text": "Système.", "cache_control": point}]
    assert [("cache_control" in t) for t in body["tools"]] == [False, True]
    assert body["tools"][-1]["cache_control"] == point
    assert body["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "Bonjour.", "cache_control": point}]}
    ]
    assert "".join(s.text for s in segments) == raw  # the segments are the bytes sent
    assert raw.count("cache_control") == 3


def test_without_tools_the_points_are_system_and_last_message():
    body, _, _ = _body(_chat(), None, "5m")
    assert "tools" not in body and _points(body) == ["system", "message"]


def test_without_system_the_points_are_tools_and_last_message():
    body, _, _ = _body(_chat(system=""), TOOLS, "5m")
    assert "system" not in body and _points(body) == ["tools", "message"]


def test_the_other_apis_never_get_a_cache_control():
    _, raw, _ = _body(_chat(), TOOLS, "1h", api="openai_chat")
    assert "cache_control" not in raw
    _, raw, _ = _body(_chat(), TOOLS, "1h", api="openai_responses")
    assert "cache_control" not in raw


def test_the_last_message_point_follows_the_last_block():
    model = (SegmentKind.ASSISTANT_TURN, None, "core.model")
    call = {
        "id": "abc",
        "type": "function",
        "function": {
            "name": Part(*model[:1], "a", *model[1:], "g"),
            "arguments": Part(*model[:1], "{}", *model[1:], "g"),
        },
    }
    tooled = [
        *_chat(),
        {"role": "assistant", "content": [], "tool_calls": [call]},
        {"role": "tool", "tool_call_id": "abc", "content": [Part(SegmentKind.TOOL_RESULT, "2")]},
    ]
    body, _, _ = _body(tooled, TOOLS, "5m")
    assert body["messages"][-1]["content"][-1]["cache_control"] == FIVE
    assert "cache_control" not in body["messages"][1]["content"][-1]  # the tool_use: not last
    ending_on_call = [*_chat(), {"role": "assistant", "content": [], "tool_calls": [call]}]
    body, _, _ = _body(ending_on_call, TOOLS, "5m")
    assert body["messages"][-1]["content"][-1]["type"] == "tool_use"
    assert body["messages"][-1]["content"][-1]["cache_control"] == FIVE
    # An empty string stays a string, with no point.
    body, _, _ = _body(_chat(user=""), None, "5m")
    assert body["messages"][-1]["content"] == "" and _points(body) == ["system"]


def test_a_reasoning_block_last_takes_no_point():
    # `thinking_blocks` come first, a message left with nothing else is left out: a block of
    # reasoning is never the last one of a sent message, the guard stays for the API's sake.
    model = (SegmentKind.ASSISTANT_TURN, None, "core.model")
    messages = [
        *_chat(),
        {
            "role": "assistant",
            "content": [Part(*model[:1], "ok", *model[1:])],
            "thinking_blocks": [{"type": "thinking", "thinking": "x", "signature": "s"}],
        },
    ]
    body, _, _ = _body(messages, None, "5m")
    blocks = body["messages"][-1]["content"]
    assert [b["type"] for b in blocks] == ["thinking", "text"]
    assert "cache_control" not in blocks[0] and blocks[1]["cache_control"] == FIVE


# ---------- through the session, on a fake API ----------


def _cached(read: int = 0, write: int = 0, one_hour: int | None = None, inp: int = 100) -> bytes:
    usage: dict[str, Any] = {
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": write,
    }
    if one_hour is not None:
        usage["cache_creation"] = {
            "ephemeral_5m_input_tokens": write - one_hour,
            "ephemeral_1h_input_tokens": one_hour,
        }
    return sse(start(inp, **usage), *text(0, "Bonjour."), *end("end_turn", 10))


def _run(provider: Provider, *messages: str, setting: str | None = None):
    session = _session(provider, bricks=("system_prompt", "short_memory"))
    try:
        if setting:
            session.set_claude_cache(setting)
        return [_turn(session, message) for message in messages]
    finally:
        session.close()


def test_the_default_setting_sends_the_body_of_before():
    provider = Provider(PLAIN_TEXT)
    _run(provider, "Bonjour")
    body = provider.body(0)
    assert (
        isinstance(body["system"], str)
        and "cache_control" not in provider.requests[0].content.decode()
    )
    assert isinstance(body["messages"][0]["content"], str)


@pytest.mark.parametrize(("setting", "point"), [("5m", FIVE), ("1h", HOUR)])
def test_a_turn_sends_the_points_and_the_next_one_extends_the_same_prefix(setting, point):
    provider = Provider(PLAIN_TEXT)
    first, second = _run(provider, "Bonjour", "Et ensuite ?", setting=setting)
    one, two = provider.body(0), provider.body(1)
    assert _points(one) == _points(two) == ["system", "message"]
    assert one["system"][0]["cache_control"] == point
    assert two["messages"][-1]["content"][-1]["cache_control"] == point
    # The past messages carry no point, and the second body starts with the first, byte for
    # byte once the points are left out.
    assert "cache_control" not in json.dumps(two["messages"][:-1])
    assert _strip(one["system"]) == _strip(two["system"])
    assert _strip(two["messages"])[: len(one["messages"])] == _strip(one["messages"])
    # What is traced is what is sent.
    for events in (first, second):
        ctx = _of(events, "context_rendered")[0].payload
        assert "".join(s["text"] for s in ctx["segments"]) == ctx["body"]


def test_the_request_shown_is_the_one_sent():
    provider = Provider(PLAIN_TEXT)
    (events,) = _run(provider, "Bonjour", setting="1h")
    shown = _of(events, "context_rendered")[0].payload["body"].encode()
    assert provider.requests[0].content == shown


def test_setting_back_to_off_sends_no_point():
    provider = Provider(PLAIN_TEXT)
    session = _session(provider, bricks=("system_prompt",))
    try:
        session.set_claude_cache("1h")
        _turn(session, "Un")
        session.set_claude_cache("off")
        _turn(session, "Deux")
    finally:
        session.close()
    assert "cache_control" in provider.requests[0].content.decode()
    assert "cache_control" not in provider.requests[1].content.decode()


def _ended(events) -> dict[str, Any]:
    return _of(events, "model_call_ended")[0].payload


def test_a_one_hour_write_is_paid_twice_the_input_price_then_a_read_costs_its_price():
    provider = Provider(_cached(write=800, one_hour=800, inp=200), _cached(read=800, inp=200))
    first, second = _run(provider, "Un", "Deux", setting="1h")
    a, b = _ended(first), _ended(second)
    assert a["cache_write_tokens"] == a["cache_write_1h_tokens"] == 800
    # claude_haiku: input 1 $, read 0,10 $, 1 h write 2 $ per million.
    assert a["cost_in_usd"] == pytest.approx((200 * 1.0 + 800 * 2.0) / 1e6)
    assert a["cache_write_usd"] == pytest.approx(800 * 2.0 / 1e6)
    assert b["cache_read_tokens"] == 800
    assert b["cost_in_usd"] == pytest.approx((200 * 1.0 + 800 * 0.10) / 1e6)


def test_a_five_minutes_write_is_paid_one_quarter_more():
    provider = Provider(_cached(write=800, one_hour=0, inp=200))
    (first,) = _run(provider, "Un", setting="5m")
    ended = _ended(first)
    assert ended["cache_write_1h_tokens"] == 0
    assert ended["cost_in_usd"] == pytest.approx((200 * 1.0 + 800 * 1.25) / 1e6)


def test_a_mixed_write_is_paid_by_part_and_without_detail_all_at_five_minutes():
    mixed = Provider(_cached(write=150, one_hour=50, inp=50))
    (first,) = _run(mixed, "Un", setting="1h")
    assert _ended(first)["cache_write_usd"] == pytest.approx((100 * 1.25 + 50 * 2.0) / 1e6)
    bare = Provider(_cached(write=150, inp=50))
    (first,) = _run(bare, "Un", setting="1h")
    ended = _ended(first)
    assert ended["cache_write_1h_tokens"] is None  # never deduced from the setting
    assert ended["cache_write_usd"] == pytest.approx(150 * 1.25 / 1e6)


def test_under_the_threshold_nothing_is_written_and_it_is_no_error():
    provider = Provider(_cached(write=0, one_hour=0, inp=1000))
    (first,) = _run(provider, "Un", setting="5m")
    ended = _ended(first)
    assert ended["cache_write_tokens"] == ended["cache_read_tokens"] == 0
    assert ended["cache_uncached_tokens"] == 1000
    assert _of(first, "turn_ended")[0].payload["status"] == "completed"


def test_the_write_premium_counts_in_the_session_total_the_cap_reads():
    reset_spend()
    provider = Provider(_cached(write=100_000, one_hour=100_000, inp=10))
    _run(provider, "Un", setting="1h")
    entry = _entry()
    # 100 000 tokens at 2 $ per million: 0,20 $ of premium alone, paid by the call.
    assert session_cap_error(entry, 0.1) is not None
    assert session_cap_error(entry, 1.0) is None  # the check itself is unchanged


# ---------- the price ----------


def test_the_one_hour_price_is_declared_or_twice_the_input_price():
    declared = _entry("claude_sonnet").pricing
    assert declared is not None and write_1h_price(declared) == 4.0
    bare = declared.model_copy(update={"cache_write_1h_usd_per_mtok": None})
    assert write_1h_price(bare) == CACHE_WRITE_1H_FACTOR * 2.0 == 4.0
    odd = declared.model_copy(update={"cache_write_1h_usd_per_mtok": 3.0})
    assert write_1h_price(odd) == 3.0


def test_call_cost_and_savings_split_the_write_by_duration():
    pricing = _entry().pricing  # 1 / 0,10 / 1,25 / 2
    assert pricing is not None
    cost = call_cost(
        pricing, 1000, 0, "api", cached_read=100, cached_write=300, cached_write_1h=100
    )
    assert cost.input_usd == pytest.approx((600 + 10 + 200 * 1.25 + 100 * 2.0) / 1e6)
    saved = cache_savings(pricing, 1000, 100, 300, cost.input_usd, "anthropic_messages", 100)
    assert saved is not None and saved["cache_priced"] is True
    assert saved["cache_write_usd"] == pytest.approx((200 * 1.25 + 100 * 2.0) / 1e6)
    # An absent 5 min price stays the input price (CAP-4), never derived at 1,25.
    bare = pricing.model_copy(update={"cache_write_usd_per_mtok": None})
    cost = call_cost(bare, 1000, 0, "api", cached_write=200, cached_write_1h=0)
    assert cost.input_usd == pytest.approx(1000 * 1.0 / 1e6)
    unpriced = cache_savings(bare, 1000, 0, 200, cost.input_usd, "anthropic_messages", 0)
    assert unpriced is not None and unpriced["cache_priced"] is False
    only_hour = cache_savings(bare, 1000, 0, 200, cost.input_usd, "anthropic_messages", 200)
    assert only_hour is not None and only_hour["cache_priced"] is True


def test_the_shipped_claude_entries_declare_1_25_and_2_times_the_input_price():
    entries = [e for e in config.load_config().cloud_models[0] if e.api == "anthropic_messages"]
    assert entries
    for entry in entries:
        pricing = entry.pricing
        assert pricing is not None
        assert pricing.cache_write_usd_per_mtok == pytest.approx(1.25 * pricing.input_usd_per_mtok)
        assert write_1h_price(pricing) == pytest.approx(2.0 * pricing.input_usd_per_mtok)


# ---------- the setting ----------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("off", "off"),
        ("5m", "5m"),
        ("1h", "1h"),
        ("2h", "off"),
        (True, "off"),
        (5, "off"),
        ("1H", "off"),
    ],
)
def test_an_unreadable_setting_is_off(value, expected):
    cfg = config.Config(values={"cloud": {"claude_cache": value}})
    assert cfg.claude_cache == expected
    assert config.Config(values={}).claude_cache == "off"
    assert config.load_config().claude_cache == "off"  # shipped default


def test_the_intention_is_saved_in_settings_and_read_at_the_next_launch():
    session = _session(Provider(PLAIN_TEXT))
    try:
        session.set_claude_cache("1h")
        assert config.read_settings()["cloud"]["claude_cache"] == "1h"
        assert config.load_config().claude_cache == "1h"
    finally:
        session.close()


def test_the_panel_state_carries_the_setting_and_no_reason_with_a_key():
    session = _session(Provider(PLAIN_TEXT))
    try:
        session.set_claude_cache("5m")
        state = session._window_state()
        assert state["claude_cache"] == "5m" and state["claude_cache_locked_text"] is None
    finally:
        session.close()


def _last_window_state() -> dict[str, Any]:
    events = get_journal().all_events()
    return [e for e in events if e.kind == "context_window_state"][-1].payload


def test_without_a_claude_key_the_setting_is_greyed_and_refused(monkeypatch):
    session = _session(Provider(PLAIN_TEXT))
    try:
        # No key at all: the keys file of the temporary data dir emptied, no variable.
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config.api_keys_path().write_text("{}", encoding="utf-8")
        session._emit_window_state()  # the panel's state as `/api/state` gives it
        assert _last_window_state()["claude_cache_locked_text"]
        with pytest.raises(SendRefused):
            session.set_claude_cache("1h")
        assert session._claude_cache == "off"
        # A key typed during the session enables the setting, without relaunching.
        entry = _entry()
        config.write_api_key(entry.id, entry.host, SecretStr("sk-test"))
        session.use_api_key(entry.id)  # what `POST /api/intentions/set_api_key` calls
        assert _last_window_state()["claude_cache_locked_text"] is None
        session.set_claude_cache("1h")
        assert session._claude_cache == "1h"
    finally:
        session.close()


def test_the_intention_is_refused_outside_idle():
    session = _session(Provider(PLAIN_TEXT))
    try:
        session.state = "streaming"
        with pytest.raises(SendRefused):
            session.set_claude_cache("1h")
        assert session._claude_cache == "off"
        session.state = "idle"
    finally:
        session.close()
