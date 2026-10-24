"""V1.3 story 4 (CAP-3): the bilan's two columns, « Cette conversation » and « Depuis le
lancement », and the cache cells, the ring and the write signal's inputs they carry.

The totals are the sum of the calls: the sums are checked against the `model_call_ended` of
each call, from real sessions (a fake Anthropic, a fake OpenAI-compatible provider, the fake
local engine).
"""

from __future__ import annotations

import pytest
from fake_engine import FakeEngine, booted_session
from test_anthropic_messages import Provider as AnthropicProvider
from test_anthropic_messages import _session as anthropic_session
from test_anthropic_messages import end, start, text
from test_anthropic_messages import sse as anthropic_sse
from test_cache_per_call import _compatible, _usage
from test_cloud import GEMINI_TEXT, GeminiProvider, _cloud_session, _of, _turn
from test_tools import QWEN
from test_turn import _run

from wavestack import config
from wavestack.models.cloud_base import (
    CallCost,
    cost_ring,
    record_spend,
    reset_conversation_spend,
    reset_spend,
    session_spend,
)
from wavestack.models.engine import Sampling
from wavestack.trace.catalog import ConsumptionUpdatedPayload, SpendColumn
from wavestack.trace.journal import get_journal

CELLS = ("read", "write", "write_1h", "uncached")


def _stream(read: int, write: int, fresh: int, one_hour: int | None = None) -> bytes:
    usage: dict = {"cache_read_input_tokens": read, "cache_creation_input_tokens": write}
    if one_hour is not None:
        usage["cache_creation"] = {
            "ephemeral_5m_input_tokens": write - one_hour,
            "ephemeral_1h_input_tokens": one_hour,
        }
    return anthropic_sse(start(fresh, **usage), *text(0, "Oui."), *end("end_turn", 10))


def _call_cells(events) -> list[dict]:
    return [e.payload for e in _of(events, "model_call_ended")]


def _total(calls: list[dict], key: str) -> int:
    return sum(c[key] for c in calls if c[key] is not None)


def _cache(column: dict, name: str) -> dict:
    return column["cache"][name]


# ---------- the totals are the sum of the calls ----------


def test_the_totals_equal_the_sum_of_the_anthropic_calls():
    provider = AnthropicProvider(
        _stream(0, 1000, 20), _stream(1000, 100, 30, one_hour=40), _stream(1100, 0, 50)
    )
    session = anthropic_session(provider)
    try:
        calls: list[dict] = []
        for question in ("Un", "Deux", "Trois"):
            calls += _call_cells(_turn(session, question))
        spend = session.consumption()
    finally:
        session.close()
    assert len(calls) == 3
    for column in (spend, spend["conversation"]):
        for name, key in zip(
            CELLS,
            (
                "cache_read_tokens",
                "cache_write_tokens",
                "cache_write_1h_tokens",
                "cache_uncached_tokens",
            ),
            strict=True,
        ):
            assert _cache(column, name)["tokens"] == _total(calls, key)
        assert column["cache_calls"] == 3
    read, write, fresh = (_cache(spend, n)["tokens"] for n in ("read", "write", "uncached"))
    assert read + write + fresh == sum(c["prompt_tokens"] for c in calls)
    # the 1 h write is declared by one call only: partial, never summed as 0 for the others
    one_hour = _cache(spend, "write_1h")
    assert (one_hour["declared"], one_hour["undeclared"], one_hour["tokens"]) == (1, 2, 40)
    # the money: the ring is the cost, the cache saving is the sum of the calls'
    assert sum(spend["ring"].values()) == pytest.approx(spend["total_usd"])
    assert spend["ring_calls"] == 3
    assert spend["cache_saved_usd"] == pytest.approx(sum(c["cache_saved_usd"] for c in calls))
    assert spend["cache_priced_calls"] == 3
    assert spend["cold_write_tokens"] == 1000
    assert spend["conversation"] == {k: spend[k] for k in spend["conversation"]}
    ConsumptionUpdatedPayload.model_validate(spend)


def test_a_compatible_call_without_detail_is_undeclared_not_zero():
    reset_spend()
    unpriced = _compatible("gemma", _usage(1000))
    assert unpriced["cache_read_tokens"] is None
    spend = session_spend(0.86)
    assert spend is not None
    for name in ("read", "write", "uncached"):
        cell = _cache(spend, name)
        assert (cell["tokens"], cell["declared"], cell["undeclared"]) == (0, 0, 1)
    assert spend["calls"] == 0 and spend["unpriced_calls"] == 1 and spend["ring_calls"] == 0
    _compatible("gemma", _usage(500, cached_tokens=300))
    spend = session_spend(0.86)
    read = _cache(spend, "read")  # a mix: a partial total
    assert (read["tokens"], read["declared"], read["undeclared"]) == (300, 1, 1)
    assert _cache(spend, "write")["declared"] == 0 and _cache(spend, "write")["undeclared"] == 2


def test_a_groq_like_call_without_footprint_is_counted():
    """No price and no footprint: the call still reaches the registry through its cells."""
    settings = {"cloud": {"models": [{"id": "groq", "pricing": None, "impacts": None}]}}
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    import json

    config.settings_path().write_text(json.dumps(settings), encoding="utf-8")
    from test_cloud import GROQ_TEXT, Provider

    session = _cloud_session("groq", Provider(GROQ_TEXT))
    try:
        events = _turn(session, "Bonjour")
    finally:
        session.close()
    (spend,) = (e.payload for e in _of(events, "consumption_updated"))
    assert spend["cache_calls"] == 1 and spend["conversation"]["cache_calls"] == 1
    assert spend["total_usd"] == 0 and spend["ring_calls"] == 0


def test_a_call_with_no_origin_is_not_counted():
    reset_spend()
    cells = {"cache_origin": None, "cache_read_tokens": None}
    record_spend(None, 0.86, cache=cells, in_conversation=True)
    spend = record_spend(None, 0.86, kv_time_saved_s=0.0)
    assert spend["cache_calls"] == 0 and spend["conversation"]["cache_calls"] == 0


def test_a_local_call_has_no_uncached_cell_to_count():
    reset_spend()
    local = {
        "cache_origin": "local",
        "cache_read_tokens": 900,
        "cache_write_tokens": 100,
        "cache_write_1h_tokens": None,
        "cache_uncached_tokens": None,
    }
    spend = record_spend(None, 0.86, cache=local, in_conversation=True)
    assert _cache(spend, "uncached") == {"tokens": 0, "declared": 0, "undeclared": 0}
    assert _cache(spend, "write_1h")["undeclared"] == 1  # the 1 h detail is the provider's
    assert spend["local_read_calls"] == 1 and spend["kv_time_saved_s"] == 0


def test_local_calls_of_the_fake_engine_sum_to_their_prompts():
    engine = FakeEngine(
        outputs=["Oui.", "Non."], template=QWEN.decode("utf-8"), architecture="qwen35"
    )
    session = booted_session(engine, window=16384)
    session.set_brick("short_memory", True)
    session.join()
    mark = get_journal().last_seq()
    _run(session, "Bonjour, comment ça va ?")
    _run(session, "Bonjour, comment ça va ?")
    calls = [e.payload for e in get_journal().events_since(mark) if e.kind == "model_call_ended"]
    spend = session.consumption()
    session.close()
    assert spend is not None
    for column in (spend, spend["conversation"]):
        assert _cache(column, "read")["tokens"] == _total(calls, "cache_read_tokens") > 0
        assert _cache(column, "write")["tokens"] == _total(calls, "cache_write_tokens")
        assert _cache(column, "read")["tokens"] + _cache(column, "write")["tokens"] == sum(
            c["prompt_tokens"] for c in calls
        )
        assert column["local_read_calls"] == 1
    assert spend["ring_calls"] == 0 and spend["unpriced_calls"] == 2


# ---------- the ring ----------


@pytest.mark.parametrize(
    ("cached_read", "cached_write", "prompt", "one_hour"),
    [
        (800, 150, 1000, 0),
        (0, 0, 500, 0),
        (5000, 70, 1000, 0),
        (100, 9999, 1000, 0),
        (0, 150, 1000, 50),
    ],
)
@pytest.mark.parametrize("model_id", ["claude_haiku", "openai_luna", "gemini"])
def test_the_ring_posts_sum_to_the_cost(model_id, cached_read, cached_write, prompt, one_hour):
    from wavestack.models.cloud_base import call_cost

    pricing = config.load_config().cloud_model(model_id).pricing
    assert pricing is not None
    cost = call_cost(pricing, prompt, 40, "api", cached_read=cached_read, cached_write=cached_write)
    ring = cost_ring(pricing, cached_read, cached_write, prompt, cost, one_hour)
    assert sum(ring.values()) == pytest.approx(cost.input_usd + cost.output_usd)
    assert ring["out"] == cost.output_usd and ring["fresh"] >= -1e-12


def test_the_ring_puts_the_whole_write_in_the_5_minute_post_without_a_1h_count():
    from wavestack.models.cloud_base import call_cost

    pricing = config.load_config().cloud_model("claude_haiku").pricing
    cost = call_cost(pricing, 1000, 10, "api", cached_read=0, cached_write=150)
    ring = cost_ring(pricing, 0, 150, 1000, cost)
    assert ring["write_1h"] == 0 and ring["write_5m"] == pytest.approx(
        150 * pricing.cache_write_usd_per_mtok / 1_000_000
    )


# ---------- who counts where, and the resets ----------


def test_a_call_out_of_a_turn_counts_for_the_launch_only():
    reset_spend()
    record_spend(CallCost(0.01, 0.02, "api"), 0.86, in_conversation=True)
    spend = record_spend(CallCost(0.10, 0.20, "api"), 0.86)  # « Tester », « LLM nu », a lab
    assert spend["calls"] == 2 and spend["conversation"]["calls"] == 1
    assert spend["conversation"]["total_usd"] == pytest.approx(0.03)


def test_the_llm_screen_stays_out_of_the_conversation():
    session = _cloud_session("gemini", GeminiProvider(GEMINI_TEXT))
    try:
        session.llm_generate("Bonjour", Sampling(temperature=0.2, top_k=5, top_p=0.9, min_p=0.05))
        session.join()
        spend = session.consumption()
    finally:
        session.close()
    assert spend["calls"] == 1 and spend["conversation"]["calls"] == 0
    assert spend["conversation"]["cache_calls"] == 0 and spend["cache_calls"] == 1


def test_the_sub_agent_counts_once_in_each_column():
    from test_cloud import gemini_call

    provider = GeminiProvider(
        gemini_call("delegate", '{"task": "Lis notes_reunion.txt."}', "p1", "sig-principal"),
        gemini_call("read_file", '{"path": "notes_reunion.txt"}', "p2", "sig-sous-agent"),
        GEMINI_TEXT,
        GEMINI_TEXT,
    )
    session = _cloud_session("gemini", provider, bricks=("tools", "subagent"))
    try:
        events = _turn(session, "Quelles décisions ?")
        spend = session.consumption()
    finally:
        session.close()
    calls = _of(events, "model_call_ended")
    assert len(calls) == 4
    assert spend["calls"] == spend["conversation"]["calls"] == 4
    assert spend["cache_calls"] == spend["conversation"]["cache_calls"] == 4


def _local_session():
    engine = FakeEngine(outputs=["Oui."], template=QWEN.decode("utf-8"), architecture="qwen35")
    return booted_session(engine, window=16384)


@pytest.mark.parametrize("how", ["clear", "reset"])
def test_clearing_or_resetting_restarts_only_the_conversation_column(how):
    reset_spend()
    session = _local_session()
    try:
        _run(session, "Bonjour")
        before = session.consumption()
        assert before["conversation"]["cache_calls"] == 1
        mark = get_journal().last_seq()
        if how == "clear":
            session.clear_conversation()
        else:
            session.reset()
        session.join()
        after = session.consumption()
        emitted = [
            e.payload for e in get_journal().events_since(mark) if e.kind == "consumption_updated"
        ]
    finally:
        session.close()
    assert after["conversation"]["cache_calls"] == 0
    assert after["conversation"] == SpendColumn().model_dump()
    assert {k: v for k, v in after.items() if k != "conversation"} == {
        k: v for k, v in before.items() if k != "conversation"
    }
    assert emitted and emitted[-1] == after  # the page learns the new column at once


def test_resetting_an_empty_conversation_emits_nothing():
    reset_spend()
    seen: list[dict] = []
    reset_conversation_spend(0.86, seen.append)
    assert seen == []


def test_the_scenario_change_restarts_the_conversation_column():
    from wavestack import scenarios

    reset_spend()
    session = _local_session()
    try:
        _run(session, "Bonjour")
        assert session.consumption()["conversation"]["cache_calls"] == 1
        session.reset()  # a scenario goes through the same `_reconfigure` as the reset
        session.join()
        spend = session.consumption()
    finally:
        session.close()
    assert scenarios and spend["cache_calls"] == 1
    assert spend["conversation"]["cache_calls"] == 0


# ---------- the write signal's inputs ----------


def test_the_cold_write_is_the_first_declared_write_of_each_column():
    reset_spend()

    def cells(write: int | None) -> dict:
        return {
            "cache_origin": "provider",
            "cache_read_tokens": 0 if write is not None else None,
            "cache_write_tokens": write,
            "cache_write_1h_tokens": None,
            "cache_uncached_tokens": None,
        }

    record_spend(None, 0.86, cache=cells(None), in_conversation=True)  # undeclared: not it
    record_spend(None, 0.86, cache=cells(1000), in_conversation=True)
    record_spend(None, 0.86, cache=cells(50), in_conversation=True)
    spend = record_spend(None, 0.86, cache=cells(7))  # out of the conversation
    assert spend["conversation"]["cold_write_tokens"] == 1000
    assert spend["cold_write_tokens"] == 1000
    reset_conversation_spend(0.86)
    spend = record_spend(None, 0.86, cache=cells(300), in_conversation=True)
    assert spend["conversation"]["cold_write_tokens"] == 300  # a new priming
    assert spend["cold_write_tokens"] == 1000  # the launch keeps its own
