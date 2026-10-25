"""V1.4 story 4 (CAP-5): compaction and sliding window of the main chat's short memory.

On `FakeEngine` (one token per byte, ChatML, a simulated cache): the plan's rules alone, the
overflow card's choices, both strategies with and without the refused message sent again,
their failures and refusals, and « Compacter ▾ »'s state.
"""

from __future__ import annotations

import threading

import pytest
from fake_engine import FakeEngine, booted_session
from test_cloud import GEMINI_TEXT, GeminiProvider, _cloud_session
from test_cloud_cap import _settings, _spent_already

from wavestack import config
from wavestack.session import compaction
from wavestack.session.app_session import Exchange, SendRefused
from wavestack.trace.catalog import PAYLOAD_MODELS
from wavestack.trace.journal import get_journal

# Window 2048, reserve 512: 1536 usable; three exchanges of ~450 bytes, then a message of
# 700 overflows; one exchange kept still holds, two do not.
LONG = "a" * 400
REFUSED = "b" * 700
VALUES = {"context": {"compaction_max_tokens": 64}}


def settle(session) -> None:
    """The worker's queue drained twice: a strategy submits the resent turn from the worker."""
    session.join()
    session.join()


def events_of(mark: int, kind: str, context: str | None = "main") -> list:
    return [
        e
        for e in get_journal().events_since(mark)
        if e.kind == kind and (context is None or e.context_id == context)
    ]


def payloads(mark: int, kind: str, context: str | None = "main") -> list[dict]:
    return [e.payload for e in events_of(mark, kind, context)]


def session_with_history(outputs: list[str] | None = None, *, exchanges: int = 3, **engine_kw):
    engine = FakeEngine(outputs=outputs or ["ok"], **engine_kw)
    session = booted_session(engine, window=2048, values=VALUES)
    session.set_brick("short_memory", True)
    session.join()
    for i in range(exchanges):
        session.send(f"{i}{LONG}")
        session.join()
    return engine, session


def overflow(session, message: str = REFUSED) -> tuple[str, dict]:
    """Send the refused message; its turn id and its `context_overflow`."""
    mark = get_journal().last_seq()
    session.send(message)
    session.join()
    (card,) = events_of(mark, "context_overflow")
    return card.turn_id, card.payload


# ---------- the plan, alone ----------


def test_the_plan_searches_by_dichotomy():
    calls = []

    def fits(k: int, compacted: bool) -> bool:
        calls.append((k, compacted))
        return k <= 37

    plans = compaction.compaction_plan(100, fits, 2, True)

    assert plans["compaction"].kept == 37 and plans["compaction"].removed == 63
    assert plans["sliding_window"].kept == 37
    assert len(calls) <= 2 * (1 + 8)  # O(log n) renders per strategy, not n


def test_the_sliding_window_keeps_one_exchange_at_least():
    plans = compaction.compaction_plan(4, lambda k, c: k == 0 if c else k <= 1, 2, True)
    assert plans["sliding_window"] == compaction.Plan("sliding_window", True, 1, 3)
    assert plans["compaction"] == compaction.Plan("compaction", True, 0, 4)


def test_a_single_exchange_leaves_nothing_to_slide():
    plans = compaction.compaction_plan(1, lambda k, c: True, 2, True)
    assert plans["sliding_window"].reason == "single" and not plans["sliding_window"].available
    assert plans["compaction"] == compaction.Plan("compaction", True, 0, 1)


def test_a_minimum_that_still_does_not_hold_is_unavailable():
    plans = compaction.compaction_plan(3, lambda k, c: False, 2, True)
    assert {p.reason for p in plans.values()} == {"still_too_long"}
    assert not any(p.available for p in plans.values())


def test_outside_an_overflow_both_keep_compaction_keep():
    plans = compaction.compaction_plan(5, None, 2, False)
    assert all(p.available and p.kept == 2 and p.removed == 3 for p in plans.values())
    few = compaction.compaction_plan(2, None, 2, False)
    assert all(not p.available and p.reason == "too_few" for p in few.values())


def test_a_summary_counts_as_an_exchange_and_the_transcript_is_masked_history():
    summary = Exchange("t1", "Résume.", "Résumé d'avant.", "", summary=True)
    plain = Exchange(
        "t2",
        "[masqué]",
        "Réponse.",
        "",
        steps=({"role": "tool", "name": "read_file", "content": "x" * 42},),
    )
    labels = {
        "previous": "Résumé précédent :",
        "user": "Utilisateur :",
        "assistant": "Assistant :",
        "tool": "[outil {name} : {chars} caractères]",
    }

    entries = compaction.transcript_entries([summary, plain], labels)

    assert entries[0] == "Résumé précédent : Résumé d'avant."
    assert entries[1].splitlines() == [
        "Utilisateur : [masqué]",
        "[outil read_file : 42 caractères]",
        "Assistant : Réponse.",
    ]
    assert compaction.compaction_plan(3, None, 2, False)["compaction"].removed == 1


def test_kept_docs_are_those_still_read_in_a_kept_exchange():
    call = {"name": "load_tool_doc", "arguments": {"tool": "read_file"}}
    kept = [Exchange("t2", "u", "a", "", steps=({"role": "assistant", "tool_calls": [call]},))]
    assert compaction.kept_docs(kept, {"read_file", "web_search"}) == {"read_file"}
    assert compaction.kept_docs([], {"read_file"}) == set()


# ---------- the overflow card ----------


def test_an_overflow_with_history_offers_both_choices():
    _, session = session_with_history()

    _, card = overflow(session)

    PAYLOAD_MODELS["context_overflow"].model_validate(card)
    choices = {c["strategy"]: c for c in card["choices"]}
    assert set(choices) == {"compaction", "sliding_window"}
    assert choices["sliding_window"]["available"] and choices["sliding_window"]["count"] == 2
    assert "les 2 plus anciens sont retirés" in choices["sliding_window"]["detail_text"]
    assert choices["compaction"]["available"] and choices["compaction"]["count"] >= 2
    assert "≈" not in choices["compaction"]["detail_text"]  # no generation rate measured yet
    assert len(card["other_strategies_text"]) == 2 and len(card["strategies_text"]) == 4
    session.close()


def test_without_history_or_short_memory_the_card_has_no_choice():
    engine = FakeEngine()
    session = booted_session(engine, window=2048, values=VALUES)
    session.set_brick("short_memory", True)
    session.join()
    _, card = overflow(session, "c" * 1600)  # the first turn: no exchange
    assert card.get("choices", []) == [] and card["strategies_text"]

    session.send(LONG)
    session.join()
    session.set_brick("short_memory", False)
    session.join()
    _, card = overflow(session, "c" * 1600)
    assert card.get("choices", []) == []
    with pytest.raises(SendRefused):
        session.compact("sliding_window")
    session.close()


def test_a_message_too_long_even_alone_makes_both_choices_unavailable():
    _, session = session_with_history()
    mark = get_journal().last_seq()
    session.send("c" * 1600)
    session.join()
    (card,) = payloads(mark, "context_overflow")
    assert card["choices"] and not any(c["available"] for c in card["choices"])
    assert all("ne tiendraient pas" in c["reason_text"] for c in card["choices"])
    (turn,) = events_of(mark, "turn_started")
    with pytest.raises(SendRefused, match="tiendraient"):
        session.compact("compaction", turn.turn_id)
    session.close()


# ---------- the sliding window ----------


def test_the_sliding_window_sends_the_refused_message_again_alone():
    engine, session = session_with_history()
    first_ids = [ex.turn_id for ex in session._history]
    turn_id, _ = overflow(session)
    calls = len(engine.calls)
    mark = get_journal().last_seq()

    session.compact("sliding_window", turn_id)
    settle(session)

    (compacted,) = payloads(mark, "history_compacted", None)
    assert compacted["strategy"] == "sliding_window"
    assert compacted["removed_turn_ids"] == first_ids[:2]
    assert compacted["message_text"] == "2 échanges retirés (fenêtre glissante)"
    assert compacted["after_tokens"] < compacted["before_tokens"]
    (started,) = payloads(mark, "turn_started")
    assert started["replay_of"] is None and started["message"] == REFUSED
    assert len(engine.calls) == calls + 1  # no call before the resent turn's
    (reread,) = payloads(mark, "prefix_not_reused")
    assert reread["cause"] == "sliding_window"
    history = session._history
    assert [ex.turn_id for ex in history[:1]] == first_ids[2:] and history[-1].user == REFUSED
    assert [ex.turn_id for ex in session._last[2]] == first_ids[2:]

    mark = get_journal().last_seq()
    session.replay()  # « Rejouer » keeps the history the strategy left
    session.join()
    ctx = payloads(mark, "context_rendered")[0]
    texts = " ".join(s["text"] for s in ctx["segments"])
    assert f"0{LONG}" not in texts and f"2{LONG}" in texts
    session.close()


def test_a_send_during_a_strategy_is_refused():
    gate = threading.Event()
    engine, session = session_with_history()
    turn_id, _ = overflow(session)
    engine.gate = gate

    session.compact("sliding_window", turn_id)
    with pytest.raises(SendRefused):
        session.send("Encore")
    gate.set()
    settle(session)
    assert session.state == "idle"
    session.close()


def test_a_stale_card_is_refused():
    _, session = session_with_history()
    turn_id, _ = overflow(session)
    session.send("Autre chose")
    session.join()
    with pytest.raises(SendRefused, match="périmée"):
        session.compact("sliding_window", turn_id)

    turn_id, _ = overflow(session)
    session.clear_conversation()
    with pytest.raises(SendRefused):
        session.compact("sliding_window", turn_id)
    session.close()


# ---------- the compaction ----------


def test_the_compaction_summarizes_then_sends_again():
    engine, session = session_with_history(["ok", "ok", "ok", "Résumé des échanges.", "Fini."])
    first_ids = [ex.turn_id for ex in session._history]
    turn_id, card = overflow(session)
    count = {c["strategy"]: c for c in card["choices"]}["compaction"]["count"]
    mark = get_journal().last_seq()

    session.compact("compaction", turn_id)
    settle(session)

    turns = events_of(mark, "turn_started")
    assert [t.payload.get("kind", "message") for t in turns] == ["compaction", "message"]
    assert turns[0].actor == "harness" and turns[1].payload["replay_of"] is None
    summary_turn = turns[0].turn_id
    calls = [e for e in events_of(mark, "model_call_started") if e.turn_id == summary_turn]
    assert len(calls) == 1 and calls[0].component == compaction.COMPONENT
    ended = [e.payload for e in events_of(mark, "model_call_ended") if e.turn_id == summary_turn]
    assert ended[0]["text"] == "Résumé des échanges."
    (compacted,) = payloads(mark, "history_compacted")
    assert compacted["removed_turn_ids"] == first_ids[:count]
    assert compacted["summary_text"] == "Résumé des échanges."
    statuses = [e.payload["status"] for e in events_of(mark, "turn_ended")]
    assert statuses == ["completed", "completed"]

    history = session._history
    assert history[0].summary and history[0].turn_id == summary_turn
    assert [ex.turn_id for ex in history[1:-1]] == first_ids[count:]
    (reread,) = [
        e.payload for e in events_of(mark, "prefix_not_reused") if e.turn_id != summary_turn
    ]
    assert reread["cause"] == "compaction"
    rendered = [e.payload for e in events_of(mark, "context_rendered") if e.turn_id != summary_turn]
    summary = [s for s in rendered[0]["segments"] if s["text"] == "Résumé des échanges."]
    assert summary[0]["component"] == compaction.COMPONENT
    assert summary[0]["label_text"] == "Résumé (compaction)"
    session.close()


def test_the_summary_call_reads_only_the_masked_history_without_tools():
    engine, session = session_with_history(["ok", "ok", "ok", "Résumé.", "Fini."])
    turn_id, _ = overflow(session)
    mark = get_journal().last_seq()
    session.compact("compaction", turn_id)
    settle(session)
    summary_turn = events_of(mark, "turn_started")[0].turn_id
    (ctx,) = [e.payload for e in events_of(mark, "context_rendered") if e.turn_id == summary_turn]
    text = "".join(s["text"] for s in ctx["segments"])
    assert "Utilisateur : 0" in text and REFUSED not in text
    assert "<tools>" not in text
    assert ctx["usable"] == 2048 - 64  # its output bounded by `compaction_max_tokens`
    session.close()


def test_the_compact_menu_compacts_without_sending_and_forgets_the_replay():
    engine, session = session_with_history(["ok", "ok", "ok", "Résumé."])
    mark = get_journal().last_seq()

    session.compact("compaction")
    settle(session)

    assert [p.get("kind") for p in payloads(mark, "turn_started")] == ["compaction"]
    assert len(session._history) == 3 and session._history[0].summary  # summary + 2 kept
    assert session._last is None and session.state == "idle"
    (state,) = payloads(mark, "compaction_state", None)[-1:]
    assert all(c["available"] for c in state["choices"])  # the summary counts: 3 > keep 2
    with pytest.raises(SendRefused):
        session.replay()
    session.close()


@pytest.mark.parametrize("failure", ["cancel", "error"])
def test_a_failed_summary_leaves_the_history_unchanged(failure):
    engine, session = session_with_history()
    turn_id, _ = overflow(session)
    before = list(session._history)
    mark = get_journal().last_seq()
    gate = threading.Event()
    if failure == "cancel":
        engine.gate = gate
    else:
        engine.fail = True

    session.compact("compaction", turn_id)
    if failure == "cancel":
        session.stop()
        gate.set()
    settle(session)

    assert session._history == before and session.state == "idle"
    assert payloads(mark, "history_compacted", None) == []
    assert [p.get("kind") for p in payloads(mark, "turn_started")] == ["compaction"]
    status = payloads(mark, "turn_ended")[-1]["status"]
    assert status == ("cancelled" if failure == "cancel" else "error")
    session.close()


# ---------- refusals and « Compacter ▾ »'s state ----------


def test_refused_without_exchange_and_outside_idle():
    engine = FakeEngine()
    session = booted_session(engine, window=2048, values=VALUES)
    session.set_brick("short_memory", True)
    session.join()
    with pytest.raises(SendRefused, match="vide"):
        session.compact("compaction")

    gate = threading.Event()
    engine.gate = gate
    session.send("Bonjour")
    with pytest.raises(SendRefused):
        session.compact("compaction")
    gate.set()
    session.join()
    with pytest.raises(SendRefused, match="Pas assez"):
        session.compact("sliding_window")  # one exchange, keep 2
    session.close()


def test_compaction_state_follows_turns_strategies_and_clearing():
    mark = get_journal().last_seq()
    _, session = session_with_history()
    states = payloads(mark, "compaction_state", None)
    assert len(states) >= 3  # after each turn at least
    last = {c["strategy"]: c for c in states[-1]["choices"]}
    assert last["sliding_window"]["available"] and last["sliding_window"]["kept"] == 2

    mark = get_journal().last_seq()
    session.compact("sliding_window")
    settle(session)
    assert len(session._history) == 2
    assert not any(c["available"] for c in payloads(mark, "compaction_state", None)[-1]["choices"])

    mark = get_journal().last_seq()
    session.clear_conversation()
    session.join()
    (cleared,) = payloads(mark, "compaction_state", None)[-1:]
    assert all(c["reason_text"] for c in cleared["choices"])
    session.close()


def test_the_estimated_duration_needs_both_measured_rates():
    _, session = session_with_history()
    history = list(session._history)
    assert session._compaction_duration(history) == ""
    session._read_tps[session._model_name] = 100.0
    assert session._compaction_duration(history) == ""
    session._gen_tps[session._model_name] = 8.0
    assert session._compaction_duration(history).startswith(", ≈ ")
    session.close()


# ---------- cloud: the summary call's cost and the FinOps cap ----------


def test_in_cloud_the_summary_cost_enters_its_turn_and_the_cap_applies():
    provider = GeminiProvider(GEMINI_TEXT)
    session = _cloud_session("gemini", provider, bricks=("short_memory",))
    try:
        for message in ("Un", "Deux", "Trois"):
            session.send(message)
            session.join()
        mark = get_journal().last_seq()
        session.compact("compaction")
        settle(session)
        (ended,) = payloads(mark, "turn_ended")
        assert ended["status"] == "completed" and ended["cost_in_usd"] > 0
        assert session._history[0].summary and session._history[0].text == "Il est 9 h."

    finally:
        session.close()


def test_in_cloud_the_cap_refuses_the_summary_and_keeps_the_history():
    _settings(max_session_usd=0.01)
    _spent_already(0.01)
    provider = GeminiProvider(GEMINI_TEXT)
    session = _cloud_session("gemini", provider, bricks=("short_memory",))
    try:
        # The cap refuses every call: the history as earlier turns would have left it.
        session._history[:] = [Exchange(f"t{i}", f"Message {i}", "Réponse.", "") for i in (1, 2, 3)]
        before = list(session._history)
        mark = get_journal().last_seq()
        session.compact("compaction")
        settle(session)
        assert provider.requests == [] and session._history == before
        assert payloads(mark, "turn_ended")[-1]["status"] != "completed"
        assert payloads(mark, "history_compacted", None) == []
        assert session.state == "idle"
    finally:
        session.close()


@pytest.mark.parametrize(
    ("values", "bound", "keep"),
    [
        ({}, 256, 2),
        ({"compaction_max_tokens": 9, "compaction_keep": 0}, 64, 1),
        ({"compaction_max_tokens": 4000, "compaction_keep": 9}, 512, 5),
    ],
)
def test_the_two_settings_are_bounded(values, bound, keep):
    cfg = config.Config(values={"context": values})
    assert (cfg.compaction_max_tokens, cfg.compaction_keep) == (bound, keep)
