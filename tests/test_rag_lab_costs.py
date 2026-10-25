"""V1.2 story 3 (CAP-8): the costs in three times (build, update, query) of the RAG workshop,
and the work copy of the corpus the update buttons act on.

Real code throughout; the doubles stand at the boundary: `FakeEmbedder`, `FakeReranker`, the
active `FakeEngine`, and a fake CodeCarbon tracker (no real model, no network).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient
from test_bricks import HEADERS
from test_rag import build
from test_rag_lab import (
    _client,
    add,
    chains,
    ended,
    ready,
    remove,
    run,
    run_status,
    stage,
    wait_idle,
)

from wavestack import config, greenops
from wavestack.greenops import Impact, Measure, Probe, StageCost
from wavestack.messages import render
from wavestack.rag import lab as rag_lab
from wavestack.rag import workcopy
from wavestack.rag.corpus import chunk_corpus, load_rag_content
from wavestack.session.app_session import SendRefused
from wavestack.trace.catalog import PAYLOAD_MODELS
from wavestack.trace.journal import get_journal


@pytest.fixture
def index(tmp_path: Path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


# ---------- greenops: the cost of a part, its sum, its record ----------


class FakeTracker:
    """CodeCarbon's tracker, as far as `Measure` reads it: 2 Wh consumed."""

    def __init__(self) -> None:
        self.final_emissions_data = SimpleNamespace(energy_consumed=0.002, gpu_energy=0)

    def stop(self) -> None:
        pass


class FakeOfflineTracker:
    """CodeCarbon's `OfflineEmissionsTracker`, the boundary the session's `LocalMeter`
    reaches: every part it tracks read 2 Wh."""

    made: list[FakeOfflineTracker] = []

    def __init__(self, **kwargs) -> None:
        FakeOfflineTracker.made.append(self)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        self.final_emissions_data = SimpleNamespace(energy_consumed=0.002, gpu_energy=0.0)


@pytest.fixture
def codecarbon(monkeypatch) -> list[FakeOfflineTracker]:
    """CodeCarbon installed, as a double (the real `LocalMeter` runs): the trackers made."""
    FakeOfflineTracker.made = []
    module = SimpleNamespace(
        OfflineEmissionsTracker=FakeOfflineTracker, count_physical_cpus=lambda: 1
    )
    monkeypatch.setattr(greenops, "_find_spec", lambda name: object())
    monkeypatch.setattr(greenops, "_load_codecarbon", lambda: module)
    return FakeOfflineTracker.made


def test_a_probe_without_a_meter_gives_a_duration_and_no_footprint():
    duration, impact = Probe(None).stop()
    assert duration >= 0 and impact is None


def test_a_probe_with_a_meter_gives_the_energy_and_the_emissions():
    _, impact = Probe(lambda: Measure(FakeTracker(), False, 41.4)).stop()
    assert impact is not None and impact.estimated
    assert impact.energy_wh_min == pytest.approx(2.0)
    assert impact.gco2e_min == pytest.approx(0.002 * 41.4)


def test_a_probe_whose_meter_fails_still_gives_the_duration():
    def broken() -> Measure:
        raise RuntimeError("no tracker")

    duration, impact = Probe(broken).stop()
    assert duration >= 0 and impact is None


def test_the_sum_of_a_phase_keeps_what_is_known_and_says_when_it_is_partial():
    impact = Impact("codecarbon", None, 1.0, 1.0, 0.04, 0.04)
    costs = [
        StageCost("build", "embedding", 100, 50, 0.0, impact),
        StageCost("build", "vector_store", None, 10, 0.0, None),  # no footprint
        StageCost("query", "generation", 30, 200, 0.001, impact),
    ]
    build = greenops.summarize(costs, "build")
    assert (build["tokens"], build["duration_ms"], build["usd"]) == (100, 60, 0.0)
    assert build["gco2e_min"] == pytest.approx(0.04) and build["partial"] is True
    assert build["measured_at_build"] is False and build["parts"] == 2
    query = greenops.summarize(costs, "query")
    assert query["partial"] is False and query["usd"] == pytest.approx(0.001)
    assert greenops.summarize(costs, "update")["parts"] == 0


def test_a_cost_read_back_from_its_record_is_marked_measured_at_build():
    cost = StageCost("build", "embedding", 12, 345, 0.0, Impact("codecarbon", None, 1, 1, 2, 2))
    back = StageCost.from_record("build", "embedding", cost.record())
    assert back is not None and back.measured_at_build
    assert (back.tokens, back.duration_ms, back.usd) == (12, 345, 0.0)
    assert back.impact is not None and back.impact.gco2e_min == 2
    assert StageCost.from_record("build", "embedding", "damaged") is None
    assert StageCost.from_record("build", "embedding", {"tokens": "x"}).tokens is None  # type: ignore[union-attr]


# ---------- a run: the costs of each part, by time ----------


def lexical_only(pipeline: rag_lab.Pipeline) -> None:
    """A chain with BM25 as its only search (no fusion needed)."""
    remove(pipeline, "vector_search")
    remove(pipeline, "rerank")
    add(pipeline, "lexical_search", "bm25", candidates=5)


def costs_of(events: list, kind: str) -> list[dict]:
    return ended(events, kind)["costs"]


def test_a_run_costs_the_embedding_the_reranking_and_the_generation_by_time(index, codecarbon):
    session, _ = ready(index)
    events = run(session)
    assert run_status(events) == "ok"
    embedding = costs_of(events, "embedding")
    assert [c["phase"] for c in embedding] == ["build", "query"]
    build, query = embedding
    # The brick's index is precomputed and has no record of its build: said, never invented.
    assert build["measured_at_build"] and build["tokens"] is None and build["note_text"]
    assert (
        query["tokens"] > 0 and query["usd"] == 0.0 and query["energy_wh_min"] == pytest.approx(2)
    )
    (rerank,) = costs_of(events, "rerank")
    assert rerank["phase"] == "query" and rerank["tokens"] > 0 and rerank["gco2e_min"] > 0
    (generation,) = costs_of(events, "generation")
    assert generation["phase"] == "query" and generation["tokens"] > 0 and generation["usd"] == 0.0
    assert len(codecarbon) >= 3
    # A part with no cost of its own counts its duration in its time.
    assert [c["phase"] for c in costs_of(events, "chunking")] == ["build"]
    assert [c["phase"] for c in costs_of(events, "context")] == ["query"]
    summary = {
        s["phase"]: s
        for s in next(e.payload["cost_summary"] for e in events if e.kind == "rag_lab_run_ended")
    }
    assert set(summary) == {"build", "query"}
    assert summary["build"]["measured_at_build"] is True and summary["build"]["partial"] is True
    assert summary["query"]["tokens"] >= query["tokens"] + rerank["tokens"]
    assert summary["query"]["gco2e_min"] > 0
    for e in events:  # the payloads stay valid for the journal's schema
        PAYLOAD_MODELS[e.kind].model_validate(e.payload)


def test_a_precomputed_index_shows_the_cost_measured_when_it_was_built(index):
    record = StageCost(
        "build", "embedding", 4321, 9876, 0.0, Impact("codecarbon", None, 5, 5, 0.2, 0.2)
    )
    rag_lab.write_build_cost(rag_lab.brick_costs_path(index), "embedding", record)
    session, _ = ready(index)
    events = run(session)
    build = costs_of(events, "embedding")[0]
    assert build["measured_at_build"] is True and build["note_text"] is None
    assert (build["tokens"], build["duration_ms"]) == (4321, 9876)
    assert build["gco2e_min"] == pytest.approx(0.2)
    # `vector_store` over the brick's index adds nothing: its build is the Embedding's record.
    assert costs_of(events, "vector_store") == []


def test_a_cache_built_by_a_run_gives_its_cost_back_the_next_time(index, codecarbon):
    session, _ = ready(index)
    _, _, b = chains(session)
    stage(b, "chunking").params["chunk_max_chars"] = 300
    stage(b, "vector_store").option = "memory"
    first = run(session, pipeline=b)
    built = costs_of(first, "embedding")[0]
    assert built["phase"] == "build" and not built["measured_at_build"]
    assert built["tokens"] > 0 and built["energy_wh_min"] == pytest.approx(2)
    second = run(session, pipeline=b)
    again = costs_of(second, "embedding")[0]
    assert again["measured_at_build"] is True and again["tokens"] == built["tokens"]
    assert again["duration_ms"] == built["duration_ms"]
    summary = next(
        s
        for e in second
        if e.kind == "rag_lab_run_ended"
        for s in e.payload["cost_summary"]
        if s["phase"] == "build"
    )
    assert summary["measured_at_build"] is True


def test_the_lexical_index_counts_the_tokens_it_indexed(index):
    session, _ = ready(index)
    _, _, b = chains(session)
    lexical_only(b)
    events = run(session, pipeline=b)
    part = next(
        e.payload
        for e in events
        if e.kind == "rag_lab_stage_ended" and e.payload["kind"] == "lexical_index"
    )
    (cost,) = part["costs"]
    assert cost["phase"] == "build" and cost["tokens"] > 0


# ---------- the work copy ----------


def test_the_work_copy_applies_each_operation_without_touching_the_shipped_corpus():
    content = load_rag_content("fr")
    shipped = chunk_corpus(content, 600, "fr")
    copy = workcopy.WorkCopy()
    added = workcopy.apply(content, copy, "add", "nouveau_doc", "Titre", "Un texte neuf.")
    appended = workcopy.apply(content, added, "modify", "teletravail", text="Paragraphe ajouté.")
    deleted = workcopy.apply(content, appended, "delete", "nouveau_doc")
    assert copy.empty  # the copy given is left as it is
    assert [c.doc_id for c in workcopy.chunks(content, 600, "fr", added)][-1] == "nouveau_doc"
    changed = workcopy.chunks(content, 600, "fr", appended)
    assert any("Paragraphe ajouté." in c.text for c in changed if c.doc_id == "teletravail")
    assert "nouveau_doc" not in {c.doc_id for c in workcopy.chunks(content, 600, "fr", deleted)}
    gone = workcopy.apply(content, workcopy.WorkCopy(), "delete", "teletravail")
    assert "teletravail" not in {c.doc_id for c in workcopy.chunks(content, 600, "fr", gone)}
    assert chunk_corpus(content, 600, "fr") == shipped  # the shipped corpus, as it was


@pytest.mark.parametrize(
    ("args", "key"),
    [
        (("add", "Mauvais Id", "t", "x"), "update_bad_id"),
        (("add", "teletravail", "t", "x"), "update_id_taken"),
        (("add", "ok_id", "", "x"), "update_empty"),
        (("modify", "absent", "", "x"), "update_unknown_doc"),
        (("modify", "teletravail", "", "  "), "update_empty"),
        (("delete", "absent"), "update_unknown_doc"),
        (("rename", "teletravail"), "update_unknown_operation"),
    ],
)
def test_the_work_copy_refuses_what_it_cannot_take(args, key):
    with pytest.raises(workcopy.UpdateRefused) as refused:
        workcopy.apply(load_rag_content("fr"), workcopy.WorkCopy(), *args)
    assert refused.value.reason.key.endswith(key)
    assert render(refused.value.reason, "en") != render(refused.value.reason, "de")


def test_the_work_copy_is_a_file_of_the_data_folder_that_reset_deletes():
    content = load_rag_content("fr")
    copy = workcopy.apply(content, workcopy.WorkCopy(), "delete", "teletravail")
    workcopy.save(copy, "fr")
    assert workcopy.path("fr").is_relative_to(config.rag_lab_dir())
    assert workcopy.load("fr").deleted == ["teletravail"]
    assert workcopy.load("en").empty  # one copy per language
    assert workcopy.reset("fr") is True and workcopy.reset("fr") is False
    assert workcopy.load("fr").empty


# ---------- an update: its cost, measured on the copy ----------


def update(session, *args, **kwargs):  # noqa: ANN001, ANN201
    mark = get_journal().last_seq()
    run_id = session.update_rag_lab(*args, **kwargs)
    wait_idle(session)
    return run_id, [e for e in get_journal().events_since(mark) if e.context_id == "rag_lab"]


def summary_of(events: list) -> dict:
    (found,) = next(e.payload["cost_summary"] for e in events if e.kind == "rag_lab_run_ended")
    return found


def test_modifying_a_document_embeds_only_its_changed_passages(index, codecarbon):
    session, _ = ready(index)
    run_id, events = update(
        session, "modify", "teletravail", "", "Une règle de plus sur le télétravail."
    )
    assert run_id.startswith("upd") and run_status(events) == "ok"
    kinds = [e.payload["kind"] for e in events if e.kind == "rag_lab_stage_ended"]
    assert kinds == ["chunking", "embedding", "vector_store"]
    embedded = ended(events, "embedding")
    assert embedded["status"] == "ok"
    (embed_cost,) = embedded["costs"]
    assert embed_cost["phase"] == "update" and embed_cost["tokens"] > 0
    assert embed_cost["energy_wh_min"] == pytest.approx(2)
    total = summary_of(events)
    assert total["phase"] == "update" and total["tokens"] == embed_cost["tokens"]
    assert total["parts"] == 3 and total["usd"] == 0.0
    # Kept on the work copy, never on `content/`.
    assert workcopy.load("fr").appended["teletravail"] == ["Une règle de plus sur le télétravail."]
    assert load_rag_content("fr").documents  # the shipped corpus is read as before
    # A later question is still run on the shipped corpus, and the update is not "the last run".
    again = run(session)
    assert "73 extraits" in ended(again, "chunking")["output_text"]
    state = session.rag_lab_state()
    assert state["last_run"][0]["payload"]["run_id"].startswith("lab")
    assert state["last_update"][0]["payload"]["run_id"] == run_id
    assert state["work_copy"]["appended"] == ["teletravail"]
    assert state["work_copy"]["path"].startswith(str(config.rag_lab_dir()))


def test_deleting_a_document_embeds_nothing_and_rebuilds_the_indexes(index):
    session, _ = ready(index)
    _, _, b = chains(session)
    lexical_only(b)
    _, events = update(session, "delete", "teletravail", pipeline=b)
    assert run_status(events) == "ok"
    (embed_cost,) = ended(events, "embedding")["costs"]
    assert embed_cost["tokens"] == 0 and embed_cost["usd"] == 0.0
    lexical_cost = ended(events, "lexical_index")["costs"][0]
    assert lexical_cost["phase"] == "update" and lexical_cost["tokens"] > 0
    assert "teletravail" in workcopy.load("fr").deleted


def test_adding_a_document_then_going_back_to_the_shipped_state(index):
    session, _ = ready(index)
    _, events = update(session, "add", "doc_neuf", "Document neuf", "Texte du nouveau document.")
    assert run_status(events) == "ok"
    assert summary_of(events)["tokens"] > 0
    assert session.rag_lab_state()["work_copy"]["added"] == ["doc_neuf"]
    state = session.reset_rag_lab_copy()
    assert state is not None and state["empty"] is True
    assert not workcopy.path("fr").exists()
    with pytest.raises(SendRefused):  # gone with the copy
        session.update_rag_lab("delete", "doc_neuf")


def test_an_update_the_copy_refuses_emits_nothing_and_changes_nothing(index):
    session, _ = ready(index)
    mark = get_journal().last_seq()
    with pytest.raises(SendRefused):
        session.update_rag_lab("modify", "absent", "", "texte")
    with pytest.raises(SendRefused):
        session.update_rag_lab("add", "teletravail", "Titre", "texte")
    assert session.state == "idle" and workcopy.load("fr").empty
    assert not [e for e in get_journal().events_since(mark) if e.kind.startswith("rag_lab_")]


def test_the_copy_is_saved_before_the_update_says_it_ended(index, monkeypatch):
    # The page reloads the copy on `rag_lab_run_ended`: it must be on disk by then.
    session, _ = ready(index)
    seen = []
    end = rag_lab.UpdateRun.end

    def watched(self, status, duration_ms):  # noqa: ANN001, ANN202
        seen.append(workcopy.load("fr").appended.get("teletravail"))
        end(self, status, duration_ms)

    monkeypatch.setattr(rag_lab.UpdateRun, "end", watched)
    _, events = update(session, "modify", "teletravail", "", "Une règle de plus.")
    assert run_status(events) == "ok" and seen == [["Une règle de plus."]]


def test_an_update_whose_copy_cannot_be_saved_ends_in_error(index, monkeypatch):
    session, _ = ready(index)

    def unwritable(*_args):  # noqa: ANN002, ANN202
        raise OSError("disque plein")

    monkeypatch.setattr(workcopy, "save", unwritable)
    _, events = update(session, "modify", "teletravail", "", "Texte.")
    assert run_status(events) == "error" and workcopy.load("fr").empty
    assert session.state == "idle"


def test_an_update_that_ends_in_error_leaves_the_copy_as_it_was(index, monkeypatch):
    session, _ = ready(index)

    def broken(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
        raise rag_lab.StageFailed(rag_lab.Message("rag_lab.update.empty_corpus"))

    monkeypatch.setattr(rag_lab.UpdateRun, "_update_embedding", broken)
    _, events = update(session, "modify", "teletravail", "", "Texte.")
    assert run_status(events) == "error"
    assert workcopy.load("fr").empty
    states = {
        e.payload["kind"]: e.payload["status"] for e in events if e.kind == "rag_lab_stage_ended"
    }
    assert states["embedding"] == "error" and states["vector_store"] == "skipped"


# ---------- the web layer ----------


def test_the_update_and_reset_routes(index):
    session, _ = ready(index)
    client: TestClient = _client(session)
    refused = client.post(
        "/api/intentions/rag_lab_update",
        json={"operation": "delete", "doc_id": "absent"},
        headers=HEADERS,
    )
    assert refused.status_code == 409 and "absent" in refused.json()["detail"]
    invalid = client.post(
        "/api/intentions/rag_lab_update",
        json={"operation": "rename", "doc_id": "teletravail"},
        headers=HEADERS,
    )
    assert invalid.status_code == 422
    ok = client.post(
        "/api/intentions/rag_lab_update",
        json={"operation": "delete", "doc_id": "teletravail"},
        headers=HEADERS,
    )
    assert ok.status_code == 200 and ok.json()["run_id"].startswith("upd")
    wait_idle(session)
    copy = client.get("/api/rag_lab").json()["work_copy"]
    assert copy["deleted"] == ["teletravail"] and copy["empty"] is False
    reset = client.post("/api/rag_lab/copy/reset", json={}, headers=HEADERS)
    assert reset.status_code == 200 and reset.json()["work_copy"]["empty"] is True
    assert json.loads(client.get("/api/rag_lab").text)["last_update"]  # still told after a reload


def test_the_index_built_in_the_app_records_its_cost_for_the_workshop(index, codecarbon):
    session, _ = ready(index)
    index.unlink()  # absent: the app builds it
    session.build_rag_index()
    wait_idle(session)
    kept = rag_lab.read_build_costs(rag_lab.brick_costs_path(index))["embedding"]
    assert kept["tokens"] > 0 and kept["duration_ms"] >= 0 and kept["usd"] == 0.0
    assert kept["energy_wh_min"] == pytest.approx(2)
    build = costs_of(run(session), "embedding")[0]
    assert build["measured_at_build"] is True and build["tokens"] == kept["tokens"]


# ---------- review of the story (2026-10-25) ----------


def test_after_an_update_the_chain_reads_the_work_copy_and_says_so(index):
    session, _ = ready(index)
    _, events = update(session, "add", "doc_neuf", "Document neuf", "Texte du nouveau document.")
    assert run_status(events) == "ok"
    events = run(session)
    chunking = ended(events, "chunking")
    assert "copie de travail" in chunking["output_text"]
    built = costs_of(events, "embedding")[0]  # never the brick's index, built from the shipped
    assert built["measured_at_build"] is False and built["tokens"] > 0
    session.reset_rag_lab_copy()
    assert "copie de travail" not in ended(run(session), "chunking")["output_text"]


def test_a_deleted_document_can_come_back_and_a_damaged_copy_reads_empty(caplog):
    content = load_rag_content("fr")
    gone = workcopy.apply(content, workcopy.WorkCopy(), "delete", "teletravail")
    back = workcopy.apply(content, gone, "add", "teletravail", "Télétravail", "Texte revenu.")
    texts = [c.text for c in workcopy.chunks(content, 600, "fr", back) if c.doc_id == "teletravail"]
    assert texts == ["Texte revenu."]
    workcopy.path("fr").parent.mkdir(parents=True, exist_ok=True)
    workcopy.path("fr").write_text("{abîmé", encoding="utf-8")
    assert workcopy.load("fr").empty and "illisible" in caplog.text


def test_a_refused_build_starts_no_tracker(index, codecarbon, monkeypatch):
    session, _ = ready(index)
    refused = rag_lab.Message("session.build.embedder_failed", kind="X", cause="y")
    monkeypatch.setattr(session, "_build_embedder", lambda model: (None, refused))
    index.unlink()
    before = len(codecarbon)
    session.build_rag_index()
    wait_idle(session)
    assert len(codecarbon) == before
