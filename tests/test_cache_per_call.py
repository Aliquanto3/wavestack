"""V1.3 story 1 (CAP-1): the cache cells of every call, local or cloud, priced or not.

A fake local engine (with and without a server's `cache_n`), a fake Anthropic response (read,
write, 1 h detail) and a fake OpenAI-compatible response (read only).
"""

from __future__ import annotations

import json

import pytest
from fake_engine import FakeEngine, booted_session
from test_anthropic_messages import PLAIN_TEXT, end, start, text
from test_anthropic_messages import Provider as AnthropicProvider
from test_anthropic_messages import _session as anthropic_session
from test_anthropic_messages import sse as anthropic_sse
from test_cloud import Provider, _cloud_session, _of, _turn, delta, sse
from test_reasoning import RecordingEngine
from test_tools import QWEN
from test_turn import _run

from wavestack import config
from wavestack.models.cloud_base import cache_tokens
from wavestack.session.app_session import AppSession
from wavestack.trace.journal import get_journal

CELLS = (
    "cache_origin",
    "cache_read_tokens",
    "cache_write_tokens",
    "cache_write_1h_tokens",
    "cache_uncached_tokens",
)
NONE_CELLS = {
    "cache_origin": "provider",
    "cache_read_tokens": None,
    "cache_write_tokens": None,
    "cache_write_1h_tokens": None,
    "cache_uncached_tokens": None,
}


def _cells(ended: dict) -> dict:
    return {k: ended.get(k) for k in CELLS}


def _ended(events) -> dict:
    (ended,) = (e.payload for e in _of(events, "model_call_ended"))
    return ended


# ---------- the pure rule ----------


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        (  # OpenAI-compatible: read only, the write is not declared
            {"prompt_tokens": 1000, "prompt_tokens_details": {"cached_tokens": 600}},
            ("provider", 600, None, None, 400),
        ),
        (  # no detail at all (Mistral, Groq…): nothing declared, never a 0
            {"prompt_tokens": 1000},
            ("provider", None, None, None, None),
        ),
        (  # details without a read count: the same
            {"prompt_tokens": 1000, "prompt_tokens_details": None},
            ("provider", None, None, None, None),
        ),
        (  # a read of 0 the provider declares stays a measured 0
            {"prompt_tokens": 1000, "prompt_tokens_details": {"cached_tokens": 0}},
            ("provider", 0, None, None, 1000),
        ),
        (  # the pivot carries the write (Anthropic): all three declared
            {
                "prompt_tokens": 1000,
                "prompt_tokens_details": {"cached_tokens": 800, "cache_write_tokens": 150},
            },
            ("provider", 800, 150, None, 50),
        ),
        (  # out-of-range values: bounded, never an exception
            {
                "prompt_tokens": 1000,
                "prompt_tokens_details": {"cached_tokens": 5000, "cache_write_tokens": -3},
            },
            ("provider", 1000, 0, None, 0),
        ),
        (  # an unreadable read is not a declared one
            {"prompt_tokens": 1000, "prompt_tokens_details": {"cached_tokens": float("nan")}},
            ("provider", None, None, None, None),
        ),
        (  # usage without a prompt count: nothing is invented
            {"prompt_tokens_details": {"cached_tokens": 5}},
            ("provider", None, None, None, None),
        ),
    ],
)
def test_cache_tokens_rule(usage, expected):
    fields = cache_tokens(usage, usage.get("prompt_tokens", 1000), "api")
    assert tuple(fields[k] for k in CELLS) == expected


def test_cache_tokens_of_an_estimate_are_all_none():
    assert cache_tokens({}, 1000, "estimate") == NONE_CELLS


# ---------- Anthropic ----------


def _anthropic_ended(stream: bytes) -> dict:
    session = anthropic_session(AnthropicProvider(stream))
    try:
        return _ended(_turn(session, "Bonjour"))
    finally:
        session.close()


def test_anthropic_declares_read_write_and_uncached():
    stream = anthropic_sse(
        start(50, cache_read_input_tokens=800, cache_creation_input_tokens=150),
        *text(0, "Bonjour."),
        *end("end_turn", 10),
    )
    ended = _anthropic_ended(stream)
    assert _cells(ended) == {
        "cache_origin": "provider",
        "cache_read_tokens": 800,
        "cache_write_tokens": 150,
        "cache_write_1h_tokens": None,
        "cache_uncached_tokens": 50,
    }
    assert 800 + 150 + 50 == ended["prompt_tokens"]
    assert "cache_saved_usd" in ended  # the priced line is still there


def test_anthropic_details_the_one_hour_write():
    stream = anthropic_sse(
        start(
            50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=150,
            cache_creation={"ephemeral_5m_input_tokens": 100, "ephemeral_1h_input_tokens": 50},
        ),
        *text(0, "Bonjour."),
        *end("end_turn", 10),
    )
    cells = _cells(_anthropic_ended(stream))
    assert cells["cache_write_tokens"] == 150 and cells["cache_write_1h_tokens"] == 50
    assert cells["cache_read_tokens"] == 0


def test_anthropic_declares_zeros_when_nothing_is_cached():
    stream = anthropic_sse(
        start(800, cache_read_input_tokens=0, cache_creation_input_tokens=0),
        *text(0, "Bonjour."),
        *end("end_turn", 5),
    )
    cells = _cells(_anthropic_ended(stream))
    assert cells["cache_read_tokens"] == 0 and cells["cache_write_tokens"] == 0
    assert cells["cache_uncached_tokens"] == 800


def test_an_anthropic_usage_without_cache_counts_declares_nothing():
    cells = _cells(_anthropic_ended(PLAIN_TEXT))
    assert cells == NONE_CELLS


def test_a_compatible_response_without_cache_details_declares_nothing():
    """CAP-1: Mistral or Groq without `prompt_tokens_details`: « not declared », not 0."""
    ended = _compatible("gemma", _usage(1000))
    assert _cells(ended) == NONE_CELLS
    assert ended["prompt_tokens"] == 1000


# ---------- OpenAI-compatible ----------


def _usage(prompt: int, **details: int) -> dict:
    usage = {"prompt_tokens": prompt, "completion_tokens": 10, "total_tokens": prompt + 10}
    if details:
        usage["prompt_tokens_details"] = details
    return usage


def _compatible(model_id: str, usage: dict | None) -> dict:
    last = {**delta("stop"), **({"usage": usage} if usage else {})}
    session = _cloud_session(model_id, Provider(sse(delta(content="Oui."), last)))
    try:
        return _ended(_turn(session, "Bonjour"))
    finally:
        session.close()


def test_a_compatible_response_without_a_declared_price_still_carries_the_cells():
    assert config.load_config().cloud_model("gemma").pricing is None
    ended = _compatible("gemma", _usage(1000, cached_tokens=600))
    assert _cells(ended) == {
        "cache_origin": "provider",
        "cache_read_tokens": 600,
        "cache_write_tokens": None,
        "cache_write_1h_tokens": None,
        "cache_uncached_tokens": 400,
    }
    assert "cache_saved_usd" not in ended and "cost_in_usd" not in ended


def test_a_priced_compatible_response_keeps_its_cost_fields_and_an_undeclared_write():
    pricing = {
        "input_usd_per_mtok": 1,
        "output_usd_per_mtok": 5,
        "cache_read_usd_per_mtok": 0.10,
        "cache_write_usd_per_mtok": 1.25,
        "checked": "2026-10-03",
    }
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    settings = {"cloud": {"models": [{"id": "gemini", "pricing": pricing}]}}
    config.settings_path().write_text(json.dumps(settings), encoding="utf-8")
    ended = _compatible("gemini", _usage(1000, cached_tokens=800))
    assert ended["cache_read_tokens"] == 800 and ended["cache_write_tokens"] is None
    assert ended["cache_uncached_tokens"] == 200
    assert ended["cache_saved_usd"] > 0 and "cost_in_usd" in ended


def test_an_estimated_usage_has_no_cells():
    assert _cells(_compatible("gemma", None)) == NONE_CELLS


# ---------- local ----------


class _Server(RecordingEngine):
    """As `llama-server`: its prompt cache says how many tokens it reused."""

    def __init__(self, reuse: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self.reuse = reuse

    @property
    def last_cache_reuse(self):
        return (self.reuse, None)


def _ended_calls(mark: int) -> list[dict]:
    events = get_journal().events_since(mark)
    return [e.payload for e in events if e.kind == "model_call_ended"]


def test_two_questions_in_a_row_read_the_context_memory_of_the_local_engine():
    engine = FakeEngine(
        outputs=["Oui.", "Non."], template=QWEN.decode("utf-8"), architecture="qwen35"
    )
    session = booted_session(engine, window=16384)
    session.set_brick("short_memory", True)
    session.join()
    mark = get_journal().last_seq()
    _run(session, "Bonjour, comment ça va ?")
    _run(session, "Bonjour, comment ça va ?")
    first, second = _ended_calls(mark)
    session.close()
    assert first["cache_origin"] == second["cache_origin"] == "local"
    assert first["cache_read_tokens"] == 0
    assert first["cache_write_tokens"] == first["prompt_tokens"]
    assert second["cache_read_tokens"] > 0
    assert second["cache_read_tokens"] + second["cache_write_tokens"] == second["prompt_tokens"]
    assert second["cache_uncached_tokens"] is None and second["cache_write_1h_tokens"] is None


def test_a_server_that_says_its_cache_reuse_is_read_as_it_says_it():
    engine = _Server(40, outputs=["Oui."], template=QWEN.decode("utf-8"))
    session = booted_session(engine, window=16384)
    session.join()
    mark = get_journal().last_seq()
    _run(session, "Bonjour")
    (ended,) = _ended_calls(mark)
    session.close()
    assert ended["cache_read_tokens"] == ended["kv_cache_tokens"] == 40
    assert ended["cache_write_tokens"] == ended["prompt_tokens"] - 40


def test_an_engine_that_says_nothing_leaves_the_local_cells_unmeasured():
    cells = AppSession._local_cache_cells(None, None, 500)
    assert cells == {**NONE_CELLS, "cache_origin": "local"}


def test_the_pivots_leave_out_a_cache_count_the_response_does_not_carry():
    """CAP-1: an absent count stays absent in the pivot, a declared 0 stays a 0."""
    from wavestack.models import anthropic_messages, openai_responses

    assert openai_responses.pivot_usage({"input_tokens": 10})["prompt_tokens_details"] == {}
    declared = {"input_tokens": 10, "input_tokens_details": {"cached_tokens": 0}}
    assert openai_responses.pivot_usage(declared)["prompt_tokens_details"] == {"cached_tokens": 0}
    assert anthropic_messages.pivot_usage({"input_tokens": 10})["prompt_tokens_details"] == {}
