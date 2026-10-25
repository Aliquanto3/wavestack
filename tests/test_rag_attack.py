"""V1.2 story 17 (CAP-13): the « Document piégé » card of the Attack tab.

The classifier is faked at the model's frontier (a `Classifier`), never a real Prompt Guard:
no test loads, downloads or sends anything (the network guard of `conftest.py` stays on).
The ranks are written by hand, measured on the real corpus after the reformulation of the
injection paragraph (decision 4 of the spec's checkpoint).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_bricks import HEADERS

from wavestack import config
from wavestack.guardrails import injection
from wavestack.guardrails.contract import Classification, Entity, NotInstalled
from wavestack.guardrails.manager import GuardrailsManager
from wavestack.rag import attack, workcopy
from wavestack.rag import index as rag_index
from wavestack.rag.corpus import chunk_corpus, load_rag_content, load_rag_questions
from wavestack.session.app_session import AppSession
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.web.app import create_app

LANGS = ("fr", "en", "de")
CONTENT = config.repo_root() / "content"
# (false_claim, legit, injection): measured at 700 characters, k = 3, after decision 4.
RANKS = {"fr": (1, 2, 3), "en": (2, 3, 1), "de": (1, 2, 3)}
AVERAGE = re.compile(r"\b(mean|average|avg|mrr|recall_at_k|aggregates?)\b", re.IGNORECASE)


@pytest.fixture(autouse=True)
def _fresh_content_caches():
    config.clear_content_caches()
    yield
    config.clear_content_caches()


class FakeGuard:
    """Detects the hidden instruction by its anchor sentence; `loaded` as a real one."""

    loaded = True

    def __init__(self, lang: str, *, fails: bool = False) -> None:
        self.anchor = attack.load_attack(lang).roles["injection"].anchor_text
        self.fails = fails
        self.seen: list[str] = []

    def classify(self, text: str) -> Classification:
        self.seen.append(text)
        if self.fails:
            raise RuntimeError("boom")
        hit = self.anchor in text
        return Classification(hit, 0.97 if hit else 0.02, 0.5)

    def mask(self, text: str, entities: tuple[Entity, ...]) -> str:
        return text

    def unload(self) -> None:
        return None


def make_session(lang: str = "fr", guard: object | None = None) -> AppSession:
    session = AppSession(config.Config(values={"language": lang}))
    if guard is not None:
        session._guardrails._instances["injection"] = guard  # type: ignore[assignment]
    return session


def ask(session: AppSession, **fields):
    return session.rag_lab_attack(attack.AttackRequest(**fields))


def roles_of(passages: list[dict]) -> dict[str, dict]:
    return {p["role"]: p for p in passages}


def journal(session: AppSession) -> list:
    return [e for e in session._security_journal.entries() if e.source == "guardrail"]


# ---------- the corpus in memory and the ranks ----------


@pytest.mark.parametrize("lang", LANGS)
def test_ranks_of_the_target_question_are_the_measured_ones(lang):
    body = ask(make_session(lang), scenario="poisoning", trap_active=True)
    ranks = body["role_ranks"]
    assert (ranks["false_claim"], ranks["legit"], ranks["injection"]) == RANKS[lang]
    assert ranks["false_claim"] < ranks["legit"]  # the false passage is above the legitimate one
    assert body["corpus"]["max_chars"] == 700 and body["corpus"]["k"] == 3
    shown = body["without"]["passages"]
    assert sorted(p["role"] for p in shown) == ["false_claim", "injection", "legit"]
    assert [p["rank"] for p in shown] == [1, 2, 3]
    assert "8" in body["without"]["answer"]["text"] and body["without"]["answer"]["kind"] == "false"


@pytest.mark.parametrize("lang", LANGS)
def test_an_inactive_trap_changes_nothing_in_the_context(lang):
    body = ask(make_session(lang), scenario="injection", trap_active=False, guardrails=True)
    shown = {p["role"] for p in body["without"]["passages"]}
    assert not shown & {"injection", "false_claim"}
    assert body["without"]["answer"]["kind"] == "clean"
    assert body["corpus"]["trap_passages"] == 0
    assert body["role_ranks"]["injection"] is None and body["role_ranks"]["false_claim"] is None


def snapshot_bytes(*roots: Path) -> dict[str, str]:
    found = {}
    for root in roots:
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        for path in files:
            found[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


@pytest.mark.parametrize("lang", LANGS)
def test_the_trap_never_touches_the_active_corpus_the_files_or_the_work_copy(lang):
    session = make_session(lang)
    content = load_rag_content(lang)
    chunks = chunk_corpus(content, 700, lang)
    digest = rag_index.corpus_digest(chunks)
    work = workcopy.load(lang)

    def files() -> dict[str, str]:
        roots = [CONTENT / "rag.yaml", CONTENT / "corpus"]
        return snapshot_bytes(*roots, *([config.data_dir()] if config.data_dir().exists() else []))

    before = files()
    shipped = (CONTENT / "rag.yaml").read_text(encoding="utf-8")
    assert next(d for d in content.documents if d.id == "faq_mots_de_passe").active is False
    session.rag_lab_attack_texts()
    ask(session, scenario="injection")
    ask(session, scenario="injection", trap_active=True, guardrails=True)
    ask(session, scenario="injection", trap_active=False)
    assert files() == before
    assert (CONTENT / "rag.yaml").read_text(encoding="utf-8") == shipped
    reloaded = load_rag_content(lang)
    assert rag_index.corpus_digest(chunk_corpus(reloaded, 700, lang)) == digest
    assert workcopy.load(lang) == work


# ---------- the guardrail ----------


@pytest.mark.parametrize("lang", LANGS)
def test_injection_with_a_guard_that_detects_it_blocks_the_passage(lang):
    guard = FakeGuard(lang)
    session = make_session(lang, guard)
    body = ask(session, scenario="injection", trap_active=True, guardrails=True, mode="block")
    assert body["without"]["answer"]["kind"] == "obeys"
    assert (
        "[liste factice" in body["without"]["answer"]["text"]
        or "dummy list" in (body["without"]["answer"]["text"])
        or "Dummy-Liste" in body["without"]["answer"]["text"]
    )
    checked = roles_of(body["with"]["passages"])
    assert checked["injection"]["check"]["decision"] == "blocked"
    assert checked["injection"]["check"]["detected"] is True
    assert (
        checked["injection"]["check"]["score"] == 0.97
        and checked["injection"]["check"]["threshold"] == 0.5
    )
    assert checked["injection"]["outcome"] == "removed"
    assert checked["false_claim"]["check"]["decision"] == "passed"
    assert checked["legit"]["outcome"] == "kept"
    assert "injection" not in {p["role"] for p in body["with"]["context"]}
    assert body["with"]["answer"]["kind"] == "grounded"
    entries = journal(session)
    assert len(entries) == 3  # one per passage checked, the « with » column only
    assert {e.name for e in entries} == {"guardrails.injection"}
    assert sorted(e.decision for e in entries) == ["blocked", "passed", "passed"]
    assert all("Démonstration" in e.reason_text or lang != "fr" for e in entries)


@pytest.mark.parametrize("lang", LANGS)
def test_flag_mode_keeps_the_passage_and_the_answer_still_obeys(lang):
    session = make_session(lang, FakeGuard(lang))
    body = ask(session, scenario="injection", trap_active=True, guardrails=True, mode="flag")
    checked = roles_of(body["with"]["passages"])
    assert checked["injection"]["check"]["decision"] == "flagged"
    assert checked["injection"]["outcome"] == "flagged"
    assert "injection" in {p["role"] for p in body["with"]["context"]}
    assert body["with"]["answer"]["kind"] == "obeys"
    assert sorted(e.decision for e in journal(session)) == ["flagged", "passed", "passed"]


def test_without_the_guard_checkbox_nothing_is_checked_nor_journaled():
    guard = FakeGuard("fr")
    session = make_session("fr", guard)
    body = ask(session, scenario="injection", trap_active=True, guardrails=False)
    assert body["with"] is None and guard.seen == [] and journal(session) == []


@pytest.mark.parametrize("mode", ["block", "flag"])
def test_poisoned_rag_passes_every_guardrail_and_the_answer_stays_false(mode):
    session = make_session("fr", FakeGuard("fr"))
    body = ask(session, scenario="poisoning", trap_active=True, guardrails=True, mode=mode)
    checked = roles_of(body["with"]["passages"])
    assert checked["false_claim"]["check"]["decision"] == "passed"
    assert "false_claim" in {p["role"] for p in body["with"]["context"]}
    assert (
        body["with"]["answer"]["kind"] == "false"
        and "8 caractères" in body["with"]["answer"]["text"]
    )
    assert (
        "aucun garde-fou de contenu ne détecte cette affirmation"
        in body["with"]["limit_text"].lower()
    )
    texts = session.rag_lab_attack_texts()["texts"]["poisoning"]
    assert len(texts["helps"]) == 2
    assert "CAP-6" in texts["helps"][0] and "diversité" in texts["helps"][1].lower()


def test_a_guard_that_fails_reports_error_and_removes_nothing():
    session = make_session("fr", FakeGuard("fr", fails=True))
    body = ask(session, scenario="injection", trap_active=True, guardrails=True, mode="block")
    assert {p["check"]["decision"] for p in body["with"]["passages"]} == {"error"}
    assert all(p["outcome"] == "kept" for p in body["with"]["passages"])
    assert body["with"]["answer"]["kind"] == "obeys"
    assert {e.decision for e in journal(session)} == {"error"}


def test_no_loaded_instance_means_not_installed_and_nothing_is_loaded_or_downloaded(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_not_a_real_token")  # the riskiest case: a token, no files

    def fails(*args, **kwargs):
        raise AssertionError("the card must never load, check a licence or download")

    monkeypatch.setattr(injection.PromptGuardGuardrail, "ensure_loaded", fails)
    monkeypatch.setattr(injection.PromptGuardGuardrail, "classify", fails)
    monkeypatch.setattr(injection, "check_licence", fails)
    monkeypatch.setattr(injection, "download_files", fails)
    session = make_session("fr")
    body = ask(session, scenario="injection", trap_active=True, guardrails=True, mode="block")
    for passage in body["with"]["passages"]:
        check = passage["check"]
        assert check["decision"] == "not_installed" and check["basis"] == "not_installed"
        assert "Garde-fous" in check["detail_text"]
        assert check["recorded"]["provenance"]["kind"] == "constructed"
        assert "cas construit" in check["recorded"]["provenance"]["text"]
    by_role = roles_of(body["with"]["passages"])
    assert by_role["injection"]["check"]["recorded"]["detected"] is True
    assert body["guard"]["loaded"] is False and body["guard"]["reason_text"]
    assert {e.decision for e in journal(session)} == {"not_installed"}
    assert len(journal(session)) == 3
    assert session._guardrails.loaded_classifier("injection") is None
    assert body["with"]["answer"]["kind"] in {"grounded", "obeys"}


def test_the_session_guardrail_modes_and_instances_are_not_touched():
    guard = FakeGuard("fr")
    session = make_session("fr", guard)
    session._guardrails.set_mode("toxicity", "flag")
    modes = dict(session._guardrails.modes)
    instances = dict(session._guardrails._instances)
    for mode in ("block", "flag"):
        ask(session, scenario="injection", trap_active=True, guardrails=True, mode=mode)
    assert session._guardrails.modes == modes
    assert session._guardrails._instances == instances


def test_loaded_classifier_returns_only_an_already_loaded_instance():
    class Fake:
        def __init__(self, loaded: bool) -> None:
            self.loaded = loaded
            self.touched = 0

        def classify(self, text):  # pragma: no cover - never called here
            self.touched += 1
            raise AssertionError

        def mask(self, text, entities):  # pragma: no cover
            return text

        def unload(self):  # pragma: no cover
            return None

    made = []
    manager = GuardrailsManager({"injection": lambda: made.append(1) or Fake(False)})
    assert manager.loaded_classifier("injection") is None and made == []
    manager._instances["injection"] = Fake(False)  # type: ignore[assignment]
    assert manager.loaded_classifier("injection") is None
    ready = Fake(True)
    manager._instances["injection"] = ready  # type: ignore[assignment]
    assert manager.loaded_classifier("injection") is ready and ready.touched == 0 and made == []
    assert manager.loaded_classifier("pii") is None


def test_not_loaded_says_not_installed_through_the_manager():
    manager = GuardrailsManager({"injection": lambda: attack.NotLoaded("why")})
    manager.set_mode("injection", "block")
    verdict = manager.check("input", "anything")[0]
    assert verdict.status == "not_installed" and verdict.detail_text == "why"
    with pytest.raises(NotInstalled):
        attack.NotLoaded("x").classify("t")


# ---------- the graph ----------


def graph(step: str, trap: bool, lang: str = "fr") -> dict:
    return attack.mini_graph_state(attack.load_attack(lang), step, trap)


def test_graph_automaton_steps_on_the_written_out_values():
    start = graph("start", False)
    assert start["false_relation_present"] is False and start["stale"] is False
    assert "14 caractères" in start["summary_text"]
    assert [r["id"] for r in start["relations"]] == [
        "policy_length",
        "policy_manager",
        "policy_second_factor",
        "policy_lockout",
    ]
    injected = graph("inject", True)
    assert injected["false_relation_present"] is True and injected["stale"] is False
    assert "8 caractères" in injected["summary_text"]
    assert "policy_eight" in [r["id"] for r in injected["relations"]]
    removed = graph("remove", False)  # unticking is the removal: the effect stays
    assert removed["false_relation_present"] is True and removed["stale"] is True
    assert "8 caractères" in removed["summary_text"]
    again = graph("remove", False)  # a double removal changes nothing
    assert again == removed
    rebuilt = graph("rebuild", False)
    assert rebuilt["false_relation_present"] is False and rebuilt["stale"] is False
    assert "14 caractères" in rebuilt["summary_text"] and rebuilt["message_text"] is None
    kept = graph("rebuild", True)  # the document is still there
    assert kept["false_relation_present"] is True and kept["message_text"]
    assert graph("inject", False)["false_relation_present"] is False  # nothing to inject
    assert graph("inject", False)["message_text"]
    assert graph("remove", True)["message_text"]  # still ticked: not removed


def test_graph_scenario_through_the_session_is_illustrative_and_constructed():
    body = ask(make_session("fr"), scenario="graph", trap_active=True, graph_step="inject")
    assert body["graph"]["false_relation_present"] is True
    assert body["provenance"]["kind"] == "constructed"
    texts = make_session("fr").rag_lab_attack_texts()["texts"]["graph"]
    assert "illustratif" in texts["illustrative_text"] and "story 13" in texts["illustrative_text"]
    assert body["without"] is None and body["with"] is None


# ---------- the data ----------


def raw(lang: str) -> dict:
    return yaml.safe_load(config.content_file(attack.FILE, lang).read_text(encoding="utf-8"))


def holes(value):
    if isinstance(value, dict):
        return {k: holes(v) for k, v in value.items()}
    if isinstance(value, list):
        return [holes(v) for v in value]
    return sorted(re.findall(r"\{(\w+)\}", str(value)))


def test_the_three_languages_mirror_each_other():
    fr = attack.load_attack("fr")
    for lang in ("en", "de"):
        tr = attack.load_attack(lang)
        assert holes(tr.texts) == holes(fr.texts)
        text_fields = {"title_text", "explain_text", "answers", "provenance"}
        for a, b in zip(fr.scenarios, tr.scenarios, strict=True):
            assert a.model_dump(exclude=text_fields) == b.model_dump(exclude=text_fields)
            assert b.title_text and b.explain_text
            if a.answers:
                assert {k for k, v in a.answers.model_dump().items() if v} == {
                    k for k, v in b.answers.model_dump().items() if v
                }
                assert a.answers.clean_text != b.answers.clean_text
        assert fr.fallback_verdicts.by_role == tr.fallback_verdicts.by_role
        assert fr.fallback_verdicts.provenance.kind == tr.fallback_verdicts.provenance.kind
        assert [s.provenance.kind for s in fr.scenarios] == [
            s.provenance.kind for s in tr.scenarios
        ]
        keep = {"id", "source", "target", "is_false"}
        assert [r.model_dump(include=keep) for r in fr.graph.relations] == [
            r.model_dump(include=keep) for r in tr.graph.relations
        ]
        assert [e.id for e in fr.graph.entities] == [e.id for e in tr.graph.entities]
        assert (fr.chunk_max_chars, fr.top_k, fr.question_id, fr.doc_id) == (
            tr.chunk_max_chars,
            tr.top_k,
            tr.question_id,
            tr.doc_id,
        )
        assert tr.graph.summaries.clean_text != fr.graph.summaries.clean_text


@pytest.mark.parametrize("lang", LANGS)
def test_references_exist_and_anchors_are_in_the_language_files(lang):
    content = attack.load_attack(lang)
    rag = load_rag_content(lang)
    assert content.doc_id in {d.id for d in rag.documents}
    assert content.question_id in {q.id for q in load_rag_questions(lang)}
    trap = next(d for d in rag.documents if d.id == content.doc_id)
    trap_text = config.content_file(trap.file, lang).read_text(encoding="utf-8")
    legit = next(d for d in rag.documents if d.id == "mots_de_passe")
    legit_text = config.content_file(legit.file, lang).read_text(encoding="utf-8")
    assert content.roles["injection"].anchor_text in trap_text
    assert content.roles["false_claim"].anchor_text in trap_text
    assert content.roles["legit"].anchor_text in legit_text
    assert (content.chunk_max_chars, content.top_k) == (700, 3)


def test_the_three_trap_paragraphs_survive_the_reformulation():
    counts = {
        lang: len(
            [
                p
                for p in re.sub(
                    r"<!--.*?-->",
                    "",
                    config.content_file("corpus/faq_mots_de_passe.md", lang).read_text("utf-8"),
                    flags=re.S,
                ).split("\n\n")
                if p.strip()
            ]
        )
        for lang in LANGS
    }
    assert len(set(counts.values())) == 1
    for lang in LANGS:  # the hidden instruction is unchanged in substance
        text = config.content_file("corpus/faq_mots_de_passe.md", lang).read_text("utf-8")
        assert attack.load_attack(lang).roles["injection"].anchor_text in text


SECRET = re.compile(
    r"sk-|hf_|ghp_|AKIA|\b(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{12,}\b"
)


@pytest.mark.parametrize("lang", LANGS)
def test_no_secret_like_string_and_the_obeying_answer_is_a_dummy_list(lang):
    text = config.content_file(attack.FILE, lang).read_text(encoding="utf-8")
    assert not SECRET.search(text), SECRET.search(text)
    answers = attack.load_attack(lang).scenario("injection").answers
    assert any(
        mark in answers.without_text for mark in ("liste factice", "dummy list", "Dummy-Liste")
    )
    assert any(mark in answers.flag_text for mark in ("liste factice", "dummy list", "Dummy-Liste"))
    assert answers.block_text == answers.clean_text


def test_provenance_is_checked_at_load():
    with pytest.raises(ValidationError):
        attack.Provenance(kind="recorded", recorded_on="2026-10-25")  # no model
    with pytest.raises(ValidationError):
        attack.Provenance(kind="recorded", model="m")  # no date
    with pytest.raises(ValidationError):
        attack.Provenance(kind="constructed")  # nothing to record it with
    ok = attack.Provenance(kind="recorded", recorded_on="2026-10-25", model="m")
    texts = attack.load_attack("fr").texts
    assert attack.provenance_text(ok, texts) == "enregistré le 2026-10-25 avec m"
    built = attack.Provenance(kind="constructed", to_record_with="x")
    assert attack.provenance_text(built, texts).startswith("cas construit pour la démonstration")
    shipped = {s.provenance.kind for s in attack.load_attack("fr").scenarios}
    assert shipped == {"constructed"}


# ---------- the endpoints ----------


def client_for(session: AppSession) -> TestClient:
    app = create_app(
        DiagnosticSession(session.cfg, port=8421), port=8421, version="t", app_session=session
    )
    return TestClient(app, base_url="http://127.0.0.1:8421")


def keys_of(node) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in keys_of(v)}
    if isinstance(node, list):
        return {k for v in node for k in keys_of(v)}
    return set()


def test_endpoints_shapes_404_and_422():
    session = make_session("fr", FakeGuard("fr"))
    client = client_for(session)
    got = client.get("/api/rag_lab/attack")
    assert got.status_code == 200
    body = got.json()
    assert body["defaults"] == {
        "scenario": "injection",
        "trap_active": False,
        "guardrails": False,
        "mode": "block",
        "graph_step": "start",
    }
    assert [s["id"] for s in body["scenarios"]] == ["injection", "poisoning", "graph"]
    assert body["guard"]["loaded"] is True
    assert body["texts"]["banner_text"] == "Démonstration : aucune donnée réelle ne sort"
    posted = client.post(
        "/api/rag_lab/attack",
        headers=HEADERS,
        json={"scenario": "injection", "trap_active": True, "guardrails": True, "mode": "block"},
    )
    assert posted.status_code == 200
    posted_body = posted.json()
    assert set(posted_body) >= {"without", "with", "role_ranks", "corpus", "provenance", "guard"}
    assert client.get("/api/rag_lab/attack/cases/poisoning").json()["id"] == "poisoning"
    assert client.get("/api/rag_lab/attack/cases/nope").status_code == 404
    for wrong in (
        {"scenario": "injection", "extra": 1},
        {"scenario": "nope"},
        {"scenario": "injection", "mode": "off"},
        {"scenario": "injection", "trap_active": "maybe"},
        {"scenario": "graph", "graph_step": "explode"},
        {},
    ):
        assert client.post("/api/rag_lab/attack", json=wrong, headers=HEADERS).status_code == 422, (
            wrong
        )
    for shown in (body, posted_body, client.get("/api/rag_lab/attack/cases/graph").json()):
        assert not [k for k in keys_of(shown) if AVERAGE.search(k)]


def test_the_card_works_without_a_model_an_index_or_a_key():
    session = make_session("fr")
    client = client_for(session)
    for scenario in ("injection", "poisoning", "graph"):
        for guardrails in (False, True):
            response = client.post(
                "/api/rag_lab/attack",
                headers=HEADERS,
                json={"scenario": scenario, "trap_active": True, "guardrails": guardrails},
            )
            assert response.status_code == 200
    assert session.state == "idle" or session.state  # no intention was needed nor taken


def test_the_tab_script_has_no_colour_and_no_inner_html():
    code = (config.repo_root() / "src/wavestack/web/static/rag-attack.js").read_text("utf-8")
    assert "innerHTML" not in code and "insertAdjacentHTML" not in code
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(", code)
    css = (config.repo_root() / "src/wavestack/web/static/rag.css").read_text("utf-8")
    block = css.split("V1.2 story 17")[1]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(", block)
    html = (config.repo_root() / "src/wavestack/web/static/rag.html").read_text("utf-8")
    panel = html.split('id="rag-panel-attack"')[1].split('id="rag-panel-sheets"')[0]
    assert "rag-soon" in panel and "Démonstration" not in panel  # the text comes from the file
