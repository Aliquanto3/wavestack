"""V1.2 story 7 (CAP-5, CAP-17): the context options of the document search workshop.

`budget`, `order` and `compress` are run by the real workshop with the suite's fakes
(`FakeEmbedder`, `FakeEngine`, `FakeCompressor`): nothing touches the network, no real model and
no Headroom load. The real Headroom path is skipped when the extra is absent.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest
from fake_engine import FakeEngine
from test_compression import FakeCompressor
from test_rag import build, place_model
from test_rag_lab import QUESTION, ended, run, run_status, stage
from test_rag_lab_generation import own_chain
from test_rag_rerank import place_reranker, rerank_config, session_for

from wavestack import config
from wavestack.compression.port import Compressed
from wavestack.messages import msg, render
from wavestack.rag import lab as rag_lab
from wavestack.rag.corpus import load_rag_content
from wavestack.session.app_session import AppSession

LANGS = ("fr", "en", "de")
# The context text `excerpts` built before the story (top_k 3, chunks of 700 characters).
EXCERPTS_BEFORE_SHA256 = "dadd9b461eddd4a7f27d422a9ebcd568d19ab08c36aa90e6e9fdb27ee80efae6"


@pytest.fixture
def index(tmp_path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


def ready(
    index: Path,
    *,
    min_chars: int | None = None,
    bricks: tuple[str, ...] = (),
    extra: dict | None = None,
):
    place_reranker()
    place_model()
    values = rerank_config(index) | (extra or {})
    if min_chars is not None:
        values = values | {"compression": {"min_chars": min_chars}}
    session, _ = session_for(
        values, rerank=False, bricks=bricks, engine=FakeEngine(output="Réponse.")
    )
    return session


def chain_with(session: AppSession, option: str, *, top_k: int = 5, budget: int | None = 4000):
    chain = own_chain(session)
    stage(chain, "chunking").params["chunk_max_chars"] = 700
    context = stage(chain, "context")
    context.option = option
    context.params["top_k"] = top_k
    if option != "excerpts":
        context.params["budget_tokens"] = budget if budget is not None else 450
    return chain


def estimator(session: AppSession):
    return lambda text: config.estimate_tokens(text, session.cfg.chars_per_token)


def facts(payload: dict) -> dict[str, str]:
    return {f["label_text"]: f["value_text"] for f in payload["facts"]}


def context_of(session: AppSession, option: str, **kwargs) -> dict:
    events = run(session, QUESTION, chain_with(session, option, **kwargs))
    assert run_status(events) == "ok"
    payload = ended(events, "context")
    assert payload["status"] == "ok", payload["error_text"]
    return payload


class FlakyCompressor(FakeCompressor):
    """Shortens every extract (as `FakeCompressor(prose=True)`) but raises on the `bad`-th."""

    def __init__(self, bad: int) -> None:
        super().__init__(prose=True)
        self.bad = bad

    def compress(self, text: str) -> Compressed:
        if len(self.seen) + 1 == self.bad:
            self.seen.append(text)
            raise ValueError("format inattendu")
        return super().compress(text)


# ---------- criterion 1 and 15: the options, the settings, the catalog ----------


def test_the_options_the_sequence_and_the_settings():
    assert rag_lab.OPTIONS["context"][:4] == ("excerpts", "budget", "order", "compress")
    context = rag_lab.STEPS["context"]
    assert (context.reads, context.writes) == (("chunks", "question"), ("augmented_prompt",))
    assert rag_lab.PARAMS[("context", "excerpts")] == ("top_k",)
    for option in ("budget", "order", "compress"):
        assert rag_lab.PARAMS[("context", option)] == ("top_k", "budget_tokens")
    assert rag_lab.BOUNDS["budget_tokens"] == (100, 4000)
    assert "context" in rag_lab.SHEETED_KINDS


def test_the_catalog_gives_the_budget_its_bounds_and_default(index):
    session = ready(index)
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    options = {
        o["id"]: o
        for s in catalog.payload()["stages"]
        if s["kind"] == "context"
        for o in s["options"]
    }
    assert [p["name"] for p in options["excerpts"]["params"]] == ["top_k"]
    for option in ("budget", "order", "compress"):
        budget = next(p for p in options[option]["params"] if p["name"] == "budget_tokens")
        assert (budget["min"], budget["max"], budget["default"]) == (100, 4000, 450)
        assert budget["unit_text"] == "tokens (estimés)"
    # An out-of-bounds value is refused as the other settings are.
    chain = chain_with(session, "budget", budget=99)
    refusal = rag_lab.validate_pipeline(chain, catalog)
    assert refusal is not None and "entre 100 et 4 000" in refusal
    chain = chain_with(session, "budget", budget=4001)
    assert rag_lab.validate_pipeline(chain, catalog) is not None
    # `excerpts` knows no budget.
    chain = chain_with(session, "excerpts")
    stage(chain, "context").params["budget_tokens"] = 450
    assert "réglage inconnu" in (rag_lab.validate_pipeline(chain, catalog) or "")


def test_a_chain_without_a_budget_setting_reads_the_default(index):
    session = ready(index)
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    probe = rag_lab.Stage(id="x", kind="context", option="budget")
    assert rag_lab.param(probe, "budget_tokens", catalog) == 450
    assert rag_lab.param(probe, "top_k", catalog) == catalog.default.find("context").params["top_k"]


# ---------- criterion 1: excerpts as before ----------


def test_excerpts_keeps_its_items_text_and_facts(index):
    session = ready(index)
    payload = context_of(session, "excerpts", top_k=3)
    content = load_rag_content()
    items = payload["items"]
    assert [i["rank"] for i in items] == [1, 2, 3]
    for item in items:
        assert item["text"].startswith(f"Extrait {item['rank']} — {item['title_text']} :\n")
        assert item["state"] == "whole" and item["placed"] == item["rank"]
    assert payload["output_text"] == "\n\n".join([content.intro_text, *(i["text"] for i in items)])
    assert list(facts(payload)) == ["Extraits gardés", "Caractères", "Placement"]
    assert facts(payload)["Extraits gardés"].startswith("3 sur ")
    assert payload["dropped"] == [] and payload["budget"] is None
    assert payload["warning_text"] is None
    # Frozen from the workshop before the story (origin/integration/v1-2-atelier at 15 commits
    # past #99, same fixture and chain): the chunks, the context text and the facts, unchanged.
    assert [i["chunk_id"] for i in items] == [5, 7, 34]
    text = payload["output_text"].replace("\r\n", "\n")
    assert len(text) == 1992
    assert hashlib.sha256(text.encode()).hexdigest() == EXCERPTS_BEFORE_SHA256
    assert facts(payload) == {
        "Extraits gardés": "3 sur 8",
        "Caractères": "1 992",
        "Placement": "Dans le message de l'utilisateur de ce tour, avant la question",
    }


def test_excerpts_shows_the_final_prompt_too(index):
    session = ready(index)
    payload = context_of(session, "excerpts", top_k=3)
    parts = payload["prompt_parts"]
    assert [p["kind"] for p in parts] == ["context", "question"]
    assert parts[0]["text"] == payload["output_text"] and parts[1]["text"] == QUESTION
    estimate = estimator(session)
    assert [p["tokens"] for p in parts] == [estimate(p["text"]) for p in parts]
    assert payload["prompt_tokens"] == sum(p["tokens"] for p in parts)


# ---------- criteria 2 to 4: the budget ----------


def test_a_budget_that_lets_everything_through_keeps_every_passage_whole(index):
    session = ready(index)
    payload = context_of(session, "budget", top_k=5, budget=4000)
    assert [i["state"] for i in payload["items"]] == ["whole"] * 5
    assert payload["dropped"] == []
    assert payload["budget"]["budget"] == 4000
    assert estimator(session)(payload["output_text"]) == payload["budget"]["used"] <= 4000
    assert payload["warning_text"] is None
    said = facts(payload)
    assert said["Passages entiers"] == "5" and said["Passage coupé"] == "aucun"
    assert said["Passages écartés"] == "0"
    assert said["Tokens du contexte (estimés)"].startswith(f"{payload['budget']['used']} sur 4")


def test_a_tight_budget_cuts_the_third_passage_and_drops_the_others(index):
    session = ready(index)
    estimate = estimator(session)
    full = context_of(session, "excerpts", top_k=5)["items"]
    intro = load_rag_content().intro_text
    budget = estimate("\n\n".join([intro, full[0]["text"], full[1]["text"]])) + (
        estimate(full[2]["text"]) // 2
    )
    payload = context_of(session, "budget", top_k=5, budget=budget)
    items = payload["items"]
    assert [i["state"] for i in items] == ["whole", "whole", "cut"]
    assert items[0]["text"] == full[0]["text"] and items[1]["text"] == full[1]["text"]
    assert items[2]["text"].endswith(" " + rag_lab.CUT_MARK)
    kept = items[2]["text"][: -len(rag_lab.CUT_MARK)].rstrip()
    assert full[2]["text"].startswith(kept)
    assert len(items[2]["text"]) < len(full[2]["text"])
    assert [d["rank"] for d in payload["dropped"]] == [4, 5]
    assert {d["chunk_id"] for d in payload["dropped"]}.isdisjoint(i["chunk_id"] for i in items)
    assert estimate(payload["output_text"]) <= budget
    assert payload["budget"] == {
        "used": estimate(payload["output_text"]),
        "budget": budget,
        "before": None,
    }
    said = facts(payload)
    removed = estimate(full[2]["text"]) - items[2]["tokens"]
    assert said["Passages entiers"] == "2" and said["Passages écartés"] == "2"
    assert said["Passage coupé"] == f"1 (−{removed} tokens estimés)"
    assert "écartés 2" in payload["warning_text"]
    assert payload["prompt_parts"][0]["text"] == payload["output_text"]


def test_a_budget_smaller_than_the_introduction_and_the_first_passage_cuts_the_first(index):
    session = ready(index)
    payload = context_of(session, "budget", top_k=5, budget=100)
    items = payload["items"]
    assert [i["state"] for i in items] == ["cut"] and items[0]["rank"] == 1
    assert items[0]["text"].endswith(rag_lab.CUT_MARK)
    assert estimator(session)(payload["output_text"]) <= 100
    assert [d["rank"] for d in payload["dropped"]] == [2, 3, 4, 5]
    assert "plus petit que l'introduction" in payload["warning_text"]
    assert "dépasse le budget" not in payload["warning_text"]


def test_a_budget_not_even_the_first_sentence_fits_in_says_it_goes_over(index):
    # One character a token: the introduction alone is over 100 tokens, so the best passage
    # keeps its first sentence and the context goes over the budget, which the warning says.
    session = ready(index, extra={"cloud": {"chars_per_token": 1.0}})
    payload = context_of(session, "budget", top_k=5, budget=100)
    items = payload["items"]
    assert [i["state"] for i in items] == ["cut"] and items[0]["text"].endswith(rag_lab.CUT_MARK)
    used = estimator(session)(payload["output_text"])
    assert used > 100 and payload["budget"]["used"] == used
    assert "plus petit que l'introduction" in payload["warning_text"]
    assert f"dépasse le budget : {used} tokens estimés sur 100" in payload["warning_text"]


def test_the_cuts_end_at_a_sentence_else_at_a_word():
    cut_at, smallest = rag_lab.LabRun._cut_at, rag_lab.LabRun._smallest_cut
    mark = rag_lab.CUT_MARK
    assert cut_at("Une phrase. Une autre phrase longue.", 20) == f"Une phrase. {mark}"
    assert cut_at("abcdefghij", 5) == f"abcde {mark}"  # no word boundary: a hard cut
    assert cut_at("", 5) == ""
    kept = smallest(object.__new__(rag_lab.LabRun), "Courte. Longue suite.")
    assert kept == f"Courte. {mark}"
    assert smallest(object.__new__(rag_lab.LabRun), "Mot " * 60).endswith(mark)


# ---------- criteria 5 and 6: the order ----------


def positions_in(payload: dict) -> list[int]:
    """The relevance ranks in the order of the context text."""
    text = payload["output_text"]
    found = sorted((text.index(i["text"]), i["rank"]) for i in payload["items"])
    return [rank for _, rank in found]


def test_order_places_the_extremities_first(index):
    session = ready(index)
    payload = context_of(session, "order", top_k=5, budget=4000)
    items = payload["items"]
    assert [i["rank"] for i in items] == [1, 2, 3, 4, 5]  # still the relevance order
    assert [i["placed"] for i in items] == [1, 5, 2, 4, 3]
    assert positions_in(payload) == [1, 3, 5, 4, 2]
    for item in items:  # the numbering follows the position in the context
        assert item["text"].startswith(f"Extrait {item['placed']} — ")
    assert "1, 3, 5, 4, 2" in facts(payload)["Ordre"]


def test_order_with_two_passages_keeps_the_relevance_order_and_says_so(index):
    session = ready(index)
    payload = context_of(session, "order", top_k=2, budget=4000)
    assert [i["placed"] for i in payload["items"]] == [1, 2]
    assert "moins de trois" in facts(payload)["Ordre"]


def test_order_is_applied_after_the_budget(index):
    session = ready(index)
    estimate = estimator(session)
    three = context_of(session, "order", top_k=3, budget=4000)
    payload = context_of(session, "order", top_k=5, budget=estimate(three["output_text"]))
    assert [i["rank"] for i in payload["items"]] == [1, 2, 3]
    assert [i["placed"] for i in payload["items"]] == [1, 3, 2]
    assert positions_in(payload) == [1, 3, 2]
    assert [d["rank"] for d in payload["dropped"]] == [4, 5]
    assert estimate(payload["output_text"]) <= estimate(three["output_text"])


# ---------- criteria 7 to 9: the compression ----------


def test_compress_counts_the_tokens_before_and_after_each_extract(index):
    session = ready(index)
    base = context_of(session, "order", top_k=5, budget=4000)
    lengths = sorted(len(i["text"]) for i in base["items"])
    threshold = lengths[2]  # three extracts reach it, two stay under
    session = ready(index, min_chars=threshold)
    compressor = FakeCompressor(prose=True)
    session._compressor = compressor
    payload = context_of(session, "compress", top_k=5, budget=4000)
    estimate = estimator(session)
    intro = load_rag_content().intro_text
    assert all(not seen.startswith(intro[:30]) for seen in compressor.seen)
    by_chunk = {i["chunk_id"]: i for i in base["items"]}
    for item in payload["items"]:
        before = by_chunk[item["chunk_id"]]
        assert item["tokens"] == before["tokens"]
        if len(before["text"].strip()) >= threshold:
            assert item["tokens_after"] < item["tokens"] and item["transforms"] == ["prose"]
            assert item["text"].startswith(before["text"][:120])
        else:
            assert item["tokens_after"] == item["tokens"] and item["transforms"] == []
            assert item["text"] == before["text"]
    assert len(compressor.seen) == 3
    assert payload["output_text"] == "\n\n".join(
        [intro, *(i["text"] for i in sorted(payload["items"], key=lambda i: i["placed"]))]
    )
    total_before = sum(i["tokens"] for i in payload["items"])
    total_after = sum(i["tokens_after"] for i in payload["items"])
    assert total_after < total_before
    assert f"{total_before} → {total_after} tokens estimés" in facts(payload)["Compression"]
    assert payload["budget"]["used"] == estimate(payload["output_text"])
    assert payload["budget"]["before"] == estimate(base["output_text"])
    assert facts(payload)["Extraits compressés"] == "3 sur 5"
    assert payload["prompt_parts"][0]["text"] == payload["output_text"]
    assert not compressor.closed  # borrowed: the workshop never closes it


def test_a_failing_extract_is_kept_as_it_was_and_counted(index):
    session = ready(index, min_chars=0)
    session._compressor = FlakyCompressor(bad=2)
    payload = context_of(session, "compress", top_k=4, budget=4000)
    failed = [i for i in payload["items"] if i["error_text"]]
    assert len(failed) == 1 and failed[0]["tokens_after"] == failed[0]["tokens"]
    assert failed[0]["error_text"].startswith("ValueError")
    others = [i for i in payload["items"] if not i["error_text"]]
    assert len(others) == 3 and all(i["tokens_after"] < i["tokens"] for i in others)
    assert facts(payload)["Échecs de compression"] == "1"
    assert "1 extrait(s) non compressé(s)" in payload["warning_text"]


def test_without_a_compressor_the_context_is_built_as_order_does(index, monkeypatch):
    session = ready(index)
    monkeypatch.setattr(session, "_compression_missing", None)  # the extra is installed
    order = context_of(session, "order", top_k=5, budget=4000)
    payload = context_of(session, "compress", top_k=5, budget=4000)
    assert payload["output_text"] == order["output_text"]
    assert [i["placed"] for i in payload["items"]] == [i["placed"] for i in order["items"]]
    assert all(i["tokens_after"] == i["tokens"] for i in payload["items"])
    assert "Compression indisponible" in payload["warning_text"]
    assert "carte Compression n'est pas activée" in payload["warning_text"]
    assert "indisponible" in facts(payload)["Compression"]


def test_the_catalog_gives_the_reason_next_to_the_option(index, monkeypatch):
    session = ready(index)
    monkeypatch.setattr(session, "_compression_missing", None)  # the extra is installed
    texts = rag_lab.load_lab_content()
    note = session._rag_lab_catalog(texts).options[("context", "compress")].note_text
    for lang in LANGS:
        said = render(note, lang)
        assert said == msg("session.rag_lab.compress_not_wanted", lang) and said
    assert "Compression" in render(note, "fr") and "Compression" in render(note, "en")
    # Headroom missing: the card's own reason, the option stays choosable.
    monkeypatch.setattr(session, "_compression_missing", "Headroom n'est pas installé.")
    state = session._rag_lab_catalog(texts).options[("context", "compress")]
    assert state.note_text == "Headroom n'est pas installé." and state.available
    # A compressor loaded: nothing to say.
    monkeypatch.setattr(session, "_compression_missing", None)
    session._compressor = FakeCompressor()
    assert session._rag_lab_catalog(texts).options[("context", "compress")].note_text is None


@pytest.mark.skipif(
    importlib.util.find_spec("headroom") is None, reason="headroom-ai (extra) absent"
)
def test_the_real_headroom_compresses_an_extract_of_the_corpus(index):
    from wavestack.compression import headroom_adapter

    session = ready(index, min_chars=0)
    compressor = headroom_adapter.HeadroomCompressor()
    session._compressor = compressor
    try:
        payload = context_of(session, "compress", top_k=2, budget=4000)
    finally:
        compressor.close()
    estimate = estimator(session)
    said = facts(payload)
    assert payload["warning_text"] is None  # no extract failed with the real adapter
    assert headroom_adapter.HeadroomCompressor.label_text in said["Compression"]
    assert said["Extraits compressés"].endswith(" sur 2")
    for item in payload["items"]:
        assert isinstance(item["tokens"], int) and isinstance(item["tokens_after"], int)
        assert item["error_text"] is None
        assert item["tokens_after"] <= item["tokens"]  # kept only when it shrinks
        assert item["tokens_after"] == estimate(item["text"])  # the text sent, counted after
    after = sum(i["tokens_after"] for i in payload["items"])
    before = sum(i["tokens"] for i in payload["items"])
    assert f"{before} → {after} tokens estimés" in said["Compression"]
    assert payload["budget"]["used"] == estimate(payload["output_text"])
    assert payload["prompt_parts"][0]["text"] == payload["output_text"]


# ---------- criterion 11: the final prompt, one function ----------


def test_the_parts_of_the_prompt_are_those_the_generation_sends(index):
    session = ready(index, bricks=("system_prompt",))
    events = run(session, QUESTION, chain_with(session, "order", top_k=3))
    payload = ended(events, "context")
    assert [p["kind"] for p in payload["prompt_parts"]] == ["system", "context", "question"]
    state = session.build_turn_state()
    assert payload["prompt_parts"][0]["text"] == state.system_prompt
    messages, system = session._rag_lab_messages(state, payload["output_text"], QUESTION)
    assert system
    sent = [part.text for message in messages for part in message["content"]]
    assert sent == [p["text"] for p in payload["prompt_parts"]]
    assert payload["prompt_tokens"] == sum(p["tokens"] for p in payload["prompt_parts"])
    prompt = ended(events, "generation")["prompt_text"]
    for part in payload["prompt_parts"]:
        assert part["text"] in prompt


def test_the_preview_is_shown_without_a_model_and_without_a_system_prompt(index):
    session = ready(index)
    chain = chain_with(session, "budget", top_k=3)
    stage(chain, "generation").option = "not_run"
    events = run(session, QUESTION, chain)
    assert ended(events, "generation")["status"] == "not_run"
    payload = ended(events, "context")
    assert [p["kind"] for p in payload["prompt_parts"]] == ["context", "question"]
    assert payload["prompt_parts"][0]["text"] == payload["output_text"]
    state = session.build_turn_state()
    messages, system = session._rag_lab_messages(state, "", QUESTION)
    assert not system and [p.text for m in messages for p in m["content"]] == [QUESTION]


# ---------- criterion 12: parent-child ----------


def test_parent_child_budget_and_order_work_on_distinct_parents(index):
    session = ready(index)
    chain = chain_with(session, "order", top_k=4, budget=4000)
    stage(chain, "chunking").option = "parent_child"
    events = run(session, QUESTION, chain)
    assert run_status(events) == "ok"
    payload = ended(events, "context")
    items = payload["items"]
    texts = [i["text"].split(":\n", 1)[1] for i in items]
    assert len(set(texts)) == len(texts) and 1 <= len(items) <= 4
    if len(items) >= 3:
        assert sorted(i["placed"] for i in items) == list(range(1, len(items) + 1))
    assert "Enfants lus" in facts(payload)
    tight = chain_with(session, "budget", top_k=4, budget=200)
    stage(tight, "chunking").option = "parent_child"
    squeezed = ended(run(session, QUESTION, tight), "context")
    assert squeezed["items"][0]["state"] == "cut" and squeezed["dropped"]


# ---------- criterion 14: the sheets ----------


@pytest.mark.parametrize("lang", LANGS)
def test_every_context_option_has_a_sheet_with_a_source(lang):
    sheets = rag_lab.load_lab_content(lang).sheets
    for option in rag_lab.OPTIONS["context"]:
        sheet = sheets[f"context.{option}"]
        assert sheet.sources and sheet.bench_text == ""
        for block in (sheet.purpose_text, sheet.when_text, sheet.cost_text, sheet.literature_text):
            assert block.strip()
    assert "Lost in the Middle" in sheets["context.order"].literature_text
    assert any("Lost in the Middle" in s.label_text for s in sheets["context.order"].sources)
    assert "Headroom" in sheets["context.compress"].when_text
    assert "4" in sheets["context.budget"].when_text and "096" in sheets["context.budget"].when_text


def test_the_compress_sheet_says_prose_barely_shrinks():
    when = rag_lab.load_lab_content("fr").sheets["context.compress"].when_text
    assert "sorties structurées" in when and "prose" in when


# ---------- criterion 16: nothing is lost on the way to the journal ----------


def test_the_journal_keeps_the_new_fields_of_a_compress_run(index):
    session = ready(index, min_chars=0)
    session._compressor = FakeCompressor(prose=True)
    payload = context_of(session, "compress", top_k=4, budget=300)
    for item in payload["items"]:
        for key in ("placed", "state", "tokens", "tokens_after", "transforms", "error_text"):
            assert key in item
        assert item["placed"] and item["state"] in ("whole", "cut") and item["tokens"]
    assert payload["dropped"] and payload["dropped"][0]["tokens"]
    assert set(payload["budget"]) == {"used", "budget", "before"}
    assert payload["budget"]["before"] > payload["budget"]["used"]
    assert {"kind", "label_text", "text", "tokens"} <= set(payload["prompt_parts"][0])
    assert payload["prompt_tokens"] > 0


def test_with_the_extra_missing_the_warning_gives_its_reason(index, monkeypatch):
    session = ready(index)
    monkeypatch.setattr(session, "_compression_missing", "Headroom n'est pas installé.")
    payload = context_of(session, "compress", top_k=3, budget=4000)
    assert "Headroom n'est pas installé." in payload["warning_text"]
    assert all(i["tokens_after"] == i["tokens"] for i in payload["items"])


class SwitchingOffCompressor(FakeCompressor):
    """Switches the Compression card off from inside the run, at its first extract, and
    records whether it was closed while the workshop still compressed."""

    def __init__(self, session: AppSession) -> None:
        super().__init__(prose=True)
        self.session = session
        self.closed_while_used = False

    def compress(self, text: str) -> Compressed:
        if not self.seen:
            self.session.set_brick("compression", False)
        self.closed_while_used = self.closed_while_used or self.closed
        return super().compress(text)


def test_the_card_switched_off_during_a_run_releases_the_compressor_after_it(index):
    # The release runs on the session's single worker, as the run does: it waits for the run's
    # end, so the borrowed compressor is never closed nor its slot freed while it compresses.
    session = ready(index, min_chars=0)
    compressor = SwitchingOffCompressor(session)
    with session._lock:
        session._wanted.add("compression")
    session._compressor = compressor
    payload = context_of(session, "compress", top_k=3, budget=4000)
    session.join()
    assert len(compressor.seen) == 3 and not compressor.closed_while_used
    assert facts(payload)["Extraits compressés"] == "3 sur 3"
    assert compressor.closed and session._compressor is None  # released once the run ended
