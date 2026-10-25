"""V1.2 story 12 (CAP-7): RAPTOR in the RAG workshop, the `raptor` preset.

The Context stage `raptor_search` scores every node of the tree of summaries of the chain's
documents at once (passages and summaries) by BM25, without any model call; « Reconstruire »
has the active model write each summary into the data folder, « Rétablir » deletes it; an update
places the touched document's passages and redoes the summaries of its branch only. The models are
fakes (`FakeEngine`, one token per byte); the runs read the whole shipped corpus.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_engine import FakeEngine
from test_bricks import HEADERS
from test_rag import build
from test_rag_erasure import client_for
from test_rag_lab import ended, stage, wait_idle
from test_rag_lab_graphrag import Stopping
from test_rag_lab_no_index import lab, preset, presets, summary, update

from wavestack import config
from wavestack.rag import exposed, workcopy
from wavestack.rag import lab as rag_lab
from wavestack.rag import raptor as rag_raptor
from wavestack.rag.corpus import load_rag_questions
from wavestack.session.app_session import SendRefused
from wavestack.trace.journal import get_journal

QUESTIONS = {q.id: q.question_text for q in load_rag_questions("fr")}
GLOBAL = QUESTIONS["q_global_rh"]


@pytest.fixture
def index(tmp_path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


def full(index: Path, fake: FakeEngine | None = None, **kwargs):  # noqa: ANN003, ANN201
    return lab(index, fake or FakeEngine(output="Réponse."), small=False, **kwargs)


def run(session, question: str, chain) -> list:  # noqa: ANN001
    mark = get_journal().last_seq()
    session.run_rag_lab(question, chain)
    wait_idle(session)
    return [e for e in get_journal().events_since(mark) if e.context_id == "rag_lab"]


def rebuild(session, fake: FakeEngine) -> list:  # noqa: ANN001
    session._engine = fake
    mark = get_journal().last_seq()
    session.rebuild_rag_lab_contexts(preset(session, "raptor"), "raptor")
    wait_idle(session)
    return [e for e in get_journal().events_since(mark) if e.context_id == "rag_lab"]


def docs(session):  # noqa: ANN001, ANN201
    return workcopy.documents(session._rag_content, "fr", workcopy.load("fr"))


def facts(payload: dict) -> dict:
    return {f["label_text"]: f["value_text"] for f in payload["facts"]}


# ---------- criterion 1: the preset, its family, its rules ----------


def test_the_preset_its_family_its_context_and_its_mcp_refusal(index):
    session = full(index)
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    chain = catalog.preset_pipeline("raptor")
    assert rag_lab.PRESETS["raptor"] == ()
    assert [s.kind for s in chain.stages] == [*rag_lab.FIXED_HEAD, *rag_lab.FIXED_TAIL]
    assert stage(chain, "context").option == "raptor_search"
    assert rag_lab.check_pipeline(chain, catalog) is None
    family = rag_lab.PRESET_FAMILIES["structure"]
    assert family.index("pageindex") < family.index("raptor") < family.index("graphrag")
    shown = presets(session)
    assert shown["raptor"]["family"] == "structure" and shown["raptor"]["available"]
    assert "raptor_search" in session.rag_lab_state()["catalog"]["searchless_options"]
    # Story 20's rule, unchanged: a Context that searches by itself is never exposed.
    refused = exposed.refusal(chain, catalog, 700, exposed.load_texts("fr"))
    assert refused is not None and refused.reason == "searches_itself"
    bad = catalog.preset_pipeline("raptor")
    bad.stages.insert(3, rag_lab.Stage(id="x1", kind="vector_search", option="cosine"))
    reason, at = rag_lab.check_pipeline(bad, catalog)
    assert at == "x1" and "cherche elle-même" in reason
    session.close()


def test_the_sequence_draws_the_tree_lines_and_no_question_embedding(index):
    session = full(index)
    steps = {s["key"]: s for s in session.rag_lab_state()["catalog"]["steps"]}
    assert steps["raptor_build"]["phase"] == "build" and steps["raptor_query"]["phase"] == "run"
    assert steps["raptor_build"]["options"] == steps["raptor_query"]["options"] == ["raptor_search"]
    assert "raptor_search" in steps["embed_query"]["hidden_with"]
    assert {"component": "summary_tree", "how": "writes"} in steps["raptor_build"]["uses"]
    for lang in ("fr", "en", "de"):
        texts = rag_lab.load_lab_content(lang)
        assert texts.steps["raptor_query"].explain_text and texts.components["summary_tree"]
        assert texts.sheets["context.raptor_search"].sources
    session.close()


# ---------- criteria 3 and 6: the search on every level, its costs ----------


def test_the_search_keeps_nodes_of_every_level_without_a_model_call(index):
    fake = FakeEngine(output="Réponse.")
    session = full(index, fake)
    events = run(session, GLOBAL, preset(session, "raptor"))
    context = ended(events, "context")
    assert context["status"] == "ok"
    picked = context["raptor"]["picked"]
    assert 1 <= len(picked) <= rag_raptor.TOP_NODES
    assert any(p["level"] >= 1 for p in picked)  # a summary among them
    assert context["raptor"]["author"] == "shipped" and context["raptor"]["rule_note_text"]
    assert context["raptor"]["estimate"]["calls"] == context["raptor"]["summaries"]
    assert len(context["items"]) == len(picked)
    assert len(fake.calls) == 1  # the generation only
    for kind in rag_lab.FIXED_HEAD:
        assert ended(events, kind)["status"] == "skipped"
    build_cost = summary(events, "build")
    assert build_cost["tokens"] == 0  # the rule's tree, measured; the estimate is in no sum
    session.close()


def test_without_a_model_the_context_runs_and_the_generation_is_skipped(index):
    session = full(index, model=None)
    assert presets(session)["raptor"]["available"]
    events = run(session, GLOBAL, preset(session, "raptor"))
    assert ended(events, "context")["status"] == "ok"
    assert ended(events, "generation")["status"] == "skipped"
    with pytest.raises(SendRefused):
        session.rebuild_rag_lab_contexts(preset(session, "raptor"), "raptor")
    client = client_for(session)
    answer = client.post(
        "/api/intentions/rag_lab_rebuild",
        json={"pipelines": [preset(session, "raptor").model_dump()], "target": "raptor"},
        headers=HEADERS,
    )
    assert answer.status_code == 409
    assert client.post("/api/rag_lab/raptor/reset", json={}, headers=HEADERS).status_code == 200
    session.close()


# ---------- criterion 4: « Reconstruire », « Rétablir » ----------


def test_rebuild_writes_one_summary_per_node_then_reset_gives_the_shipped_tree(index):
    fake = FakeEngine(output="Résumé écrit par le modèle.")
    session = full(index, fake)
    nodes = len(rag_raptor.build_tree(docs(session), "fr", 700).nodes)
    events = rebuild(session, fake)
    assert ended(events, "raptor_search")["status"] == "ok"
    path = rag_raptor.rebuilt_path("fr", config.rag_lab_dir())
    rebuilt = rag_raptor.load_files("fr", config.rag_lab_dir())[1]
    assert rebuilt is not None and (rebuilt.author, rebuilt.method) == ("rebuilt", "llm")
    assert rebuilt.calls == len(fake.calls) == nodes
    assert rebuilt.duration_ms is not None and rebuilt.input_tokens and rebuilt.output_tokens
    assert summary(events, "build")["tokens"] == rebuilt.tokens
    card = session.rag_lab_state()["contexts"]["raptor"]
    assert card["rebuilt"] and "reconstruit" in card["mark_text"] and card["measure_text"]
    assert card["estimate"] is None and card["rule_note_text"] is None
    events = run(session, GLOBAL, preset(session, "raptor"))
    build_cost = summary(events, "build")
    assert build_cost["measured_at_build"] and build_cost["tokens"] == rebuilt.tokens
    assert ended(events, "context")["raptor"]["author"] == "rebuilt"
    reset = session.reset_rag_lab_raptor()
    assert not path.exists() and not reset["raptor"]["rebuilt"]
    assert reset["raptor"]["estimate"]["calls"] == nodes
    session.close()


def test_a_stopped_or_failing_rebuild_writes_nothing(index):
    fake = Stopping(output="Résumé.")
    session = full(index, fake)
    fake.session = session
    rebuild(session, fake)
    path = rag_raptor.rebuilt_path("fr", config.rag_lab_dir())
    assert not path.exists()
    rebuild(session, FakeEngine(output="Résumé écrit par le modèle."))
    before = path.read_text(encoding="utf-8")
    broken = FakeEngine(output="Résumé.")
    broken.fail = True
    events = rebuild(session, broken)
    assert ended(events, "raptor_search")["status"] == "error"
    assert len(broken.calls) == 1 and path.read_text(encoding="utf-8") == before
    session.reset_rag_lab_raptor()
    rebuild(session, FakeEngine(output=""))  # nothing readable: nothing written
    assert not path.exists()
    session.close()


# ---------- criterion 5: the update in three parts, the erasure ----------


def test_an_update_of_the_shipped_tree_redoes_the_branch_touched_only(index):
    session = full(index)
    chain = preset(session, "raptor")
    text = "La cellule de crise se réunit vite.\n\nL'astreinte prévient la cellule de crise."
    events = update(session, "add", "note_flash", "Note flash", text, chain)
    part = ended(events, "raptor_search")
    assert part["status"] == "ok"
    kinds = [c["kind"] for c in part["costs"]]
    assert kinds == ["raptor_chunking", "raptor_placement", "raptor_summaries"]
    found = facts(part)
    assert int(found["Découpage (passages du document)"]) >= 1
    redone, _, total = found["Résumés"].partition(" refait(s) sur ")
    assert 1 <= int(redone) < int(total)
    assert summary(events, "update")["tokens"] == 0  # by the rule
    session.close()


def test_a_rebuilt_tree_updated_by_the_model_then_a_deletion_forgets(index):
    session = full(index, FakeEngine(output="Résumé écrit par le modèle."))
    rebuild(session, FakeEngine(output="Résumé écrit par le modèle."))
    chain = preset(session, "raptor")
    fake = FakeEngine(output="Résumé du Projet Zéphyr.")
    session._engine = fake
    text = "Le Projet Zéphyr dépend de la cellule de crise.\n\nLe Projet Zéphyr a son astreinte."
    events = update(session, "add", "note_zephyr", "Note Zéphyr", text, chain)
    part = ended(events, "raptor_search")
    redone = int(facts(part)["Résumés"].split(" ")[0])
    assert redone >= 1 and len(fake.calls) == redone
    assert summary(events, "update")["tokens"] > 0
    path = rag_raptor.rebuilt_path("fr", config.rag_lab_dir())
    assert "Zéphyr" in path.read_text(encoding="utf-8")
    session._engine = FakeEngine(output="Résumé sans le document.")
    update(session, "delete", "note_zephyr", pipeline=chain)
    body = path.read_text(encoding="utf-8")
    assert "note_zephyr" not in body and "Zéphyr" not in body
    session.close()


class FailsSecond(FakeEngine):
    """Its first call answers, the next ones fail (`status: error`)."""

    @property
    def fail(self) -> bool:  # type: ignore[override]
        return len(self.calls) >= 2

    @fail.setter
    def fail(self, value: bool) -> None:
        pass


def test_a_model_failing_during_an_update_writes_nothing_and_keeps_no_copy(index):
    # Review of V1.2 story 12: the summaries already written are not kept (as « Reconstruire »).
    session = full(index, FakeEngine(output="Résumé écrit par le modèle."))
    rebuild(session, FakeEngine(output="Résumé écrit par le modèle."))
    path = rag_raptor.rebuilt_path("fr", config.rag_lab_dir())
    before = path.read_text(encoding="utf-8")
    chain = preset(session, "raptor")
    fake = FailsSecond(output="Résumé du Projet Zéphyr.")
    session._engine = fake
    text = "Le Projet Zéphyr dépend de la cellule de crise.\n\nLe Projet Zéphyr a son astreinte."
    events = update(session, "add", "note_zephyr", "Note Zéphyr", text, chain)
    part = ended(events, "raptor_search")
    assert len(fake.calls) == 2 and part["status"] == "error"
    assert "rien n'est écrit" in part["error_text"]
    assert any(c["tokens"] for c in part["costs"])  # the calls made are said
    assert path.read_text(encoding="utf-8") == before
    assert "note_zephyr" not in {d.doc_id for d in docs(session)}
    session.close()


def test_the_payload_keeps_the_tree_in_the_journal(index):
    session = full(index)
    events = run(session, GLOBAL, preset(session, "raptor"))
    payload = ended(events, "context")["raptor"]
    assert payload["passages"] > 0 and payload["levels"] >= 2
    assert all(len(p["preview"]) <= rag_lab.PREVIEW_CHARS for p in payload["picked"])
    session.close()
