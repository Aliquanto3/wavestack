"""V1.2 story 8 (CAP-6): System One's decision layer of the document search workshop.

The router, the passage filter and the grounding check are run by the real workshop with the
suite's fakes (`FakeEmbedder`, `FakeReranker`, `FakeEngine` as the SLM judge, a fake NLI
classifier) and the decision API behind an `httpx.MockTransport`: nothing touches the network,
no real model is loaded. The real ONNX classifier is tested only when the extra `decision` and
its files are on the workstation (skipped otherwise).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fake_engine import FakeEngine
from test_rag import build, place_model
from test_rag_lab import QUESTION, ended, run, run_status, stage
from test_rag_lab_generation import own_chain
from test_rag_rerank import place_reranker, rerank_config, session_for

from wavestack import config
from wavestack.rag import decision as rag_decision
from wavestack.rag import exposed, sheets
from wavestack.rag import lab as rag_lab
from wavestack.trace.journal import get_journal

LANGS = ("fr", "en", "de")
KEY = "sk-or-test-not-a-real-key"
CLASSIFIER_FILES = {
    "decision/fake/config.json": 8,
    "decision/fake/tokenizer.json": 8,
    "decision/fake/model.onnx": 16,
}


@pytest.fixture
def index(tmp_path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


class FakeClassifier:
    """The NLI classifier's port: `noul` reads « 1 » as the claim's support when it shares a
    word of four letters or more with the premise; `choice` prefers « rerank » at 0.7."""

    def __init__(self, choice: dict[str, float] | None = None) -> None:
        self.calls: list[tuple] = []
        self.closed = False
        self._choice = choice

    def noul(self, task: str, lang: str, state: dict) -> tuple[float, bool]:
        self.calls.append((task, lang, dict(state)))
        premise = state.get("premise", state.get("passage", "")).lower()
        claim = state.get("claim", state.get("question", "")).lower()
        words = [w for w in claim.replace(".", " ").split() if len(w) >= 4]
        shared = sum(1 for w in words if w in premise)
        return (0.9 if shared else 0.1), False

    def choice(self, question: str, options: dict[str, str]) -> tuple[dict[str, float], bool]:
        self.calls.append(("choice", question, dict(options)))
        if self._choice is not None:
            return {k: self._choice.get(k, 0.0) for k in options}, False
        rest = (1 - 0.7) / max(1, len(options) - 1)
        return {k: (0.7 if k == "rerank" else rest) for k in options}, False

    def close(self) -> None:
        self.closed = True


def classifier_config() -> dict:
    files = [
        {"url": f"https://huggingface.co/demo/resolve/main/{p}", "path": p, "size": size}
        for p, size in CLASSIFIER_FILES.items()
    ]
    return {
        "id": "fake-nli",
        "backend": "onnx",
        "label_text": "Faux NLI",
        "license": "MIT",
        "max_tokens": 512,
        "load_path": "decision/fake/model.onnx",
        "tokenizer_path": "decision/fake/tokenizer.json",
        "config_path": "decision/fake/config.json",
        "files": files,
    }


def place_classifier() -> None:
    for path, size in CLASSIFIER_FILES.items():
        target = config.models_dir() / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\0" * size)


def ready(index: Path, *, judge: str = "oui", key: str | None = None, classifier=None):
    """A session with the fake reranker and NLI classifier, the fake engine as the judge."""
    place_reranker()
    place_model()
    place_classifier()
    values = rerank_config(index) | {
        "rag_lab": {"decision": {"classifier": classifier_config()}},
        "finops": {"max_session_usd": 1.0},
    }
    session, _ = session_for(values, rerank=False, bricks=(), engine=FakeEngine(output=judge))
    fake = classifier or FakeClassifier()
    session._decision_classifier_factory = lambda model: fake
    session._decision_installed = lambda: True
    session._decision_key = lambda: key
    return session, fake


def with_stage(chain: rag_lab.Pipeline, kind: str, option: str = "local", **params):
    stages = chain.stages
    used = {s.id for s in stages}
    new_id = next(f"d{i}" for i in range(1, 20) if f"d{i}" not in used)
    added = rag_lab.Stage(id=new_id, kind=kind, option=option, params=params)
    if kind == "router":
        at = next(i for i, s in enumerate(stages) if s.kind == "vector_store") + 1
    elif kind == "passage_filter":
        at = next(i for i, s in enumerate(stages) if s.kind == "context")
    else:
        at = len(stages)
    stages.insert(at, added)
    return chain


def decisions_of(events: list, kind: str) -> list[dict]:
    payload = ended(events, kind)
    assert payload["status"] == "ok", payload["error_text"]
    return payload["decisions"]


def catalog_of(session) -> dict:
    payload = session._rag_lab_catalog(rag_lab.load_lab_content()).payload()
    return {s["kind"]: {o["id"]: o for o in s["options"]} | {"_": s} for s in payload["stages"]}


# ---------- the registries, the catalog, the rules of the chain ----------


def test_the_kinds_options_settings_and_sheets():
    for kind in rag_lab.DECISION_KINDS:
        assert rag_lab.OPTIONS[kind] == ("local", "cloud")
        assert kind in rag_lab.SHEETED_KINDS and kind in rag_lab.STEPS
        for option in ("local", "cloud"):
            assert rag_lab.PARAMS[(kind, option)] == ("decision_threshold", "judge_cascade")
    assert {"router", "passage_filter"} <= set(rag_lab.RETRIEVAL)
    assert rag_lab.CHECKS == ("grounding_check",)
    assert rag_lab.BOUNDS["decision_threshold"] == (1, 99)
    assert rag_lab.BOUNDS["judge_cascade"] == (0, 1)
    assert "decision_model" in rag_lab.COMPONENTS
    assert sheets.missing_sheets() == []


@pytest.mark.parametrize("lang", LANGS)
def test_each_option_has_its_sheet_with_the_literature(lang):
    content = rag_lab.load_lab_content(lang)
    for kind in rag_lab.DECISION_KINDS:
        for option in rag_lab.OPTIONS[kind]:
            sheet = content.sheets[f"{kind}.{option}"]
            assert sheet.sources and sheet.bench_text
            hypothesis = "H6" if kind == "router" else "H7"
            assert hypothesis in sheet.literature_text
    assert "64" in content.sheets["grounding_check.local"].bench_text  # the judge's H7


def test_the_catalog_gives_the_bench_thresholds_and_the_cascade_off(index):
    session, _ = ready(index)
    catalog = catalog_of(session)
    expected = {
        ("router", "local"): 50,
        ("router", "cloud"): 50,
        ("passage_filter", "local"): 2,
        ("passage_filter", "cloud"): 13,
        ("grounding_check", "local"): 20,
        ("grounding_check", "cloud"): 59,
    }
    for (kind, option), threshold in expected.items():
        params = {p["name"]: p for p in catalog[kind][option]["params"]}
        assert params["decision_threshold"]["default"] == threshold
        assert (params["decision_threshold"]["min"], params["decision_threshold"]["max"]) == (
            1,
            99,
        )
        assert params["judge_cascade"]["default"] == 0
    assert catalog["grounding_check"]["_"]["check"] is True
    assert catalog["grounding_check"]["_"]["insert_after"] == "generation"
    assert catalog["router"]["_"]["insert_after"] == "vector_store"
    assert catalog["passage_filter"]["local"]["label_text"].endswith("(Faux reranker)")
    assert catalog["router"]["local"]["label_text"] == "Faux NLI"


@pytest.mark.parametrize("lang", LANGS)
def test_without_a_key_the_cloud_options_are_greyed_with_their_reason(index, lang):
    session, _ = ready(index)
    session._language = lang
    catalog = catalog_of(session)
    for kind in rag_lab.DECISION_KINDS:
        cloud = catalog[kind]["cloud"]
        assert cloud["available"] is False
        assert rag_decision.KEY_ENV in cloud["reason_text"]
    assert catalog["router"]["local"]["available"] is True


def test_with_a_key_the_cloud_options_are_offered_and_the_key_never_shown(index):
    session, _ = ready(index, key=KEY)
    state = session.rag_lab_state()
    assert KEY not in json.dumps(state, ensure_ascii=False)
    catalog = catalog_of(session)
    for kind in rag_lab.DECISION_KINDS:
        assert catalog[kind]["cloud"]["available"] is True
    assert "typesafe/jev-1.14" in catalog["grounding_check"]["cloud"]["label_text"]
    assert "pplx-decider-flash" in catalog["passage_filter"]["cloud"]["label_text"]


def test_the_local_classifier_without_its_extra_or_files_says_why(index):
    session, _ = ready(index)
    session._decision_installed = lambda: False
    local = catalog_of(session)["router"]["local"]
    assert local["available"] is False and "--extra decision" in local["reason_text"]
    session._decision_installed = lambda: True
    (config.models_dir() / "decision/fake/model.onnx").unlink()
    local = catalog_of(session)["grounding_check"]["local"]
    assert local["available"] is False and "model.onnx" in local["reason_text"]
    assert local["download"]["target"] == "rag_lab_decision:fake-nli"


def test_the_download_target_of_the_classifier(index):
    session, _ = ready(index)
    model, _, scope = session._download_target("rag_lab_decision:fake-nli")
    assert model.id == "fake-nli" and scope["component"] == "rag_lab.decision"
    with pytest.raises(KeyError):
        session._download_target("rag_lab_decision:other")


def test_the_shipped_declaration_pins_the_bench_revision():
    model, why = config.load_config().rag_lab_decision_classifier
    assert why is None and model is not None
    assert all("262ae02f29173eec1c250f90804dc7edc677dcff" in f.url for f in model.files)
    assert all(len(f.sha256) == 64 and f.size > 0 for f in model.files)
    assert model.load_file.size == 87246195


def test_the_chain_rules_of_the_three_decisions(index):
    session, _ = ready(index)
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    good = with_stage(
        with_stage(with_stage(own_chain(session), "router"), "passage_filter"), "grounding_check"
    )
    assert rag_lab.check_pipeline(good, catalog) is None
    # The grounding check closes the chain.
    bad = own_chain(session)
    bad.stages.insert(-1, rag_lab.Stage(id="g1", kind="grounding_check", option="local"))
    refusal = rag_lab.check_pipeline(bad, catalog)
    assert refusal is not None and refusal[1] == "g1" and "Generation" in refusal[0]
    # The router before the searches, the filter after one.
    late = own_chain(session)
    late.stages.insert(4, rag_lab.Stage(id="r1", kind="router", option="local"))
    assert rag_lab.check_pipeline(late, catalog)[1] == "r1"
    early = own_chain(session)
    early.stages.insert(3, rag_lab.Stage(id="f1", kind="passage_filter", option="local"))
    assert rag_lab.check_pipeline(early, catalog)[1] == "f1"
    # A setting out of bounds is refused like the others.
    wrong = with_stage(own_chain(session), "passage_filter", decision_threshold=100)
    assert "entre 1 et 99" in rag_lab.check_pipeline(wrong, catalog)[0]


def test_a_chain_with_a_decision_is_never_exposed_as_mcp(index):
    session, _ = ready(index)
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    texts = exposed.load_texts()
    shipped = session.cfg.rag_chunk_max_chars
    base = catalog.default.model_copy(deep=True)
    assert exposed.refusal(base, catalog, shipped, texts) is None
    for kind in rag_lab.DECISION_KINDS:
        chain = with_stage(catalog.default.model_copy(deep=True), kind)
        refused = exposed.refusal(chain, catalog, shipped, texts)
        assert refused is not None and refused.reason == "model_stage"


# ---------- the cascade rule, the judge's answers ----------


def test_the_classifier_decides_alone_at_or_above_the_threshold():
    called = []

    def judge():
        called.append(1)
        return True, "oui"

    d = rag_decision.decide_binary("p", 0.5, 0.5, True, judge, "keep", "drop")
    assert (d.author, d.verdict, d.below, called) == ("classifier", "keep", False, [])
    d = rag_decision.decide_binary("p", 0.4, 0.5, False, judge, "keep", "drop")
    assert (d.author, d.verdict, d.below, d.note) == ("classifier", "drop", True, "cascade_off")
    d = rag_decision.decide_binary("p", 0.4, 0.5, True, judge, "keep", "drop")
    assert (d.author, d.verdict, d.judge_text) == ("judge", "keep", "oui")
    d = rag_decision.decide_binary("p", 0.4, 0.5, True, lambda: (None, "peut-être"), "k", "d")
    assert (d.author, d.verdict, d.note) == ("classifier", "d", "judge_unreadable")
    d = rag_decision.decide_binary("p", 0.4, 0.5, True, lambda: (None, None), "k", "d")
    assert d.note == "judge_unavailable"


def test_the_router_keeps_its_choice_under_the_threshold_without_cascade():
    probs = {"dense": 0.45, "rerank": 0.55}
    d = rag_decision.decide_choice("q", probs, 0.5, False, None)
    assert (d.verdict, d.author, d.below) == ("rerank", "classifier", False)
    d = rag_decision.decide_choice("q", probs, 0.6, False, None)
    assert (d.verdict, d.author, d.below, d.note) == ("rerank", "classifier", True, "cascade_off")
    d = rag_decision.decide_choice("q", probs, 0.6, True, lambda: ("dense", "dense"))
    assert (d.verdict, d.author) == ("dense", "judge")


def test_the_judges_words_and_the_answers_sentences():
    assert rag_decision.judge_word("Oui.", "fr") is True
    assert rag_decision.judge_word("nein", "de") is False
    assert rag_decision.judge_word("yes", "fr") is True  # English understood everywhere
    assert rag_decision.judge_word("Je pense que oui", "fr") is None
    assert rag_decision.judge_label("Stratégie : dense.", ("dense", "rerank")) == "dense"
    assert rag_decision.judge_label("aucune", ("dense",)) is None
    found, total = rag_decision.sentences("Un. Deux ! Trois ?\nQuatre", 3)
    assert found == ["Un.", "Deux !", "Trois ?"] and total == 4


# ---------- the decision API, behind a fake transport ----------


def api_transport(answers: list[dict], seen: list[httpx.Request], status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = answers[min(len(seen), len(answers)) - 1]
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def test_the_api_reads_noul_choice_and_score_and_sends_the_bench_body():
    seen: list[httpx.Request] = []
    answers = [
        {"model": "m-1", "answers": {"decision": {"noul": 0.83}}, "usage": {"cost": 2e-05}},
        {
            "answers": {
                "decision": {
                    "choice": "rerank",
                    "confidence": 0.7,
                    "probabilities": {"rerank": 0.7, "dense": 0.3, "other": 0.5},
                }
            }
        },
        {"answers": {"decision": {"score": 3, "probabilities": {"3": 0.6}}}},
    ]
    api = rag_decision.DecisionApi(KEY, transport=api_transport(answers, seen))
    got = api.noul("m", {"question": "q", "passage": "p"}, "instr")
    assert (got.value, got.cost_usd, got.model_returned) == (0.83, 2e-05, "m-1")
    body = json.loads(seen[0].content)
    assert body == {
        "model": "m",
        "state": {"question": "q", "passage": "p"},
        "questions": {"decision": {"type": "noul", "instructions": "instr"}},
    }
    assert seen[0].headers["Authorization"] == f"Bearer {KEY}"
    assert seen[0].url.host == "openrouter.ai"
    choice = api.choice("m", {"question": "q"}, "i", {"dense": "a", "rerank": "b"})
    assert choice.value == "rerank" and choice.probabilities == {"rerank": 0.7, "dense": 0.3}
    assert json.loads(seen[1].content)["questions"]["decision"]["options"] == {
        "dense": "a",
        "rerank": "b",
    }
    assert api.score("m", {"x": 1}, "i", 5).value == 3
    with pytest.raises(ValueError):
        api.score("m", {}, "i", 11)


def test_the_api_errors_never_carry_the_key_and_other_hosts_are_refused():
    seen: list[httpx.Request] = []
    error = {"error": {"code": 401, "message": f"bad key {KEY}"}}
    api = rag_decision.DecisionApi(KEY, transport=api_transport([error], seen, status=401))
    with pytest.raises(rag_decision.DecisionError) as raised:
        api.noul("m", {}, "i")
    assert KEY not in str(raised.value.text) and "401" in str(raised.value.text)
    with pytest.raises(rag_decision.DecisionError):
        rag_decision.DecisionApi(KEY, url="https://example.com/api/alpha/decisions")
    unreadable = rag_decision.DecisionApi(
        KEY, transport=api_transport([{"answers": {"decision": {"noul": 2}}}], [])
    )
    with pytest.raises(rag_decision.DecisionError):
        unreadable.noul("m", {}, "i")


def test_the_key_is_read_from_the_variable_then_the_registry():
    assert rag_decision.read_key({"OPENROUTER_API_KEY": "a"}, lambda name: "b") == "a"
    assert rag_decision.read_key({}, lambda name: "b") == "b"
    assert rag_decision.read_key({"OPENROUTER_API_KEY": ""}, lambda name: None) is None


def test_the_capped_api_refuses_before_sending_and_records_each_cost():
    seen: list[httpx.Request] = []
    answer = {"answers": {"decision": {"noul": 0.5}}, "usage": {"cost": 0.001}}
    api = rag_decision.DecisionApi(KEY, transport=api_transport([answer], seen))
    spent: list[float] = []
    capped = rag_decision.CappedApi(api, lambda: None, lambda a: spent.append(a.cost_usd))
    capped.noul("m", {}, "i")
    assert spent == [0.001] and len(seen) == 1
    refused = rag_decision.CappedApi(api, lambda: "plafond", lambda a: spent.append(1))
    with pytest.raises(rag_decision.DecisionError):
        refused.noul("m", {}, "i")
    assert len(seen) == 1


# ---------- the runs: the filter, the router, the grounding ----------


def test_the_filter_keeps_or_rejects_each_passage_with_author_probability_and_threshold(index):
    session, _ = ready(index)
    chain = with_stage(own_chain(session), "passage_filter", decision_threshold=30)
    events = run(session, QUESTION, chain)
    assert run_status(events) == "ok"
    payload = ended(events, "passage_filter")
    decisions = payload["decisions"]
    assert decisions and all(d["author"] == "classifier" for d in decisions)
    assert all(d["threshold"] == 0.3 and d["threshold_text"] == "0,300" for d in decisions)
    for d in decisions:
        assert (d["verdict"] == "keep") == (d["probability"] >= 0.3)
        assert d["below"] == (d["probability"] < 0.3)
    kept = [d["chunk_id"] for d in decisions if d["verdict"] == "keep"]
    assert [i["chunk_id"] for i in payload["items"]] == kept
    assert [i["chunk_id"] for i in payload["dropped"]] == [
        d["chunk_id"] for d in decisions if d["verdict"] == "drop"
    ]
    context = ended(events, "context")
    assert {i["chunk_id"] for i in context["items"]} <= set(kept)


def test_lowering_the_threshold_changes_the_author_of_a_decision(index):
    """CAP-6: with the cascade on, the passages under the threshold go to the SLM judge; at a
    lower threshold the classifier decides some of them alone."""
    session, _ = ready(index, judge="oui")
    authors = {}
    for threshold in (99, 1):
        chain = with_stage(
            own_chain(session), "passage_filter", decision_threshold=threshold, judge_cascade=1
        )
        events = run(session, QUESTION, chain)
        payload = ended(events, "passage_filter")
        assert payload["status"] == "ok"
        authors[threshold] = [d["author"] for d in payload["decisions"]]
        assert "non validée" in payload["warning_text"]
    assert "judge" in authors[99]
    assert authors[1] != authors[99]
    assert authors[1].count("classifier") > authors[99].count("classifier")


def test_the_judge_without_a_readable_answer_leaves_the_classifiers_refusal(index):
    session, _ = ready(index, judge="Je ne sais pas.")
    chain = with_stage(own_chain(session), "passage_filter", decision_threshold=99, judge_cascade=1)
    decisions = decisions_of(run(session, QUESTION, chain), "passage_filter")
    below = [d for d in decisions if d["below"]]
    assert below and all(d["author"] == "classifier" and d["verdict"] == "drop" for d in below)
    assert all("illisible" in d["note_text"] for d in below)


def test_the_router_chooses_a_strategy_and_skips_the_stages_it_does_not_use(index):
    session, fake = ready(index)
    chain = with_stage(own_chain(session), "router", decision_threshold=50)
    events = run(session, QUESTION, chain)
    assert run_status(events) == "ok"
    (decision,) = decisions_of(events, "router")
    assert decision["verdict"] == "rerank" and decision["author"] == "classifier"
    assert set(decision["probabilities"]) == {"dense", "rerank"}
    assert ended(events, "rerank")["status"] == "ok"
    # A classifier that prefers the dense RAG: the reranking is left out, with the reason.
    session, _ = ready(index, classifier=FakeClassifier({"dense": 0.8, "rerank": 0.2}))
    events = run(session, QUESTION, with_stage(own_chain(session), "router"))
    assert decisions_of(events, "router")[0]["verdict"] == "dense"
    rerank = ended(events, "rerank")
    assert rerank["status"] == "skipped" and "routeur" in rerank["error_text"]
    assert run_status(events) == "ok"


def test_the_router_needs_two_strategies(index):
    session, _ = ready(index)
    chain = own_chain(session)
    chain.stages = [s for s in chain.stages if s.kind != "rerank"]
    events = run(session, QUESTION, with_stage(chain, "router"))
    router = ended(events, "router")
    assert router["status"] == "skipped" and "au moins deux" in router["error_text"]
    assert run_status(events) == "ok"


def test_the_grounding_checks_each_sentence_of_the_answer(index):
    answer = "Le télétravail est possible deux jours par semaine. Les licornes votent."
    session, fake = ready(index, judge=answer)
    chain = with_stage(own_chain(session), "grounding_check", decision_threshold=50)
    events = run(session, QUESTION, chain)
    assert run_status(events) == "ok"
    decisions = decisions_of(events, "grounding_check")
    assert [d["subject_text"] for d in decisions] == [
        "Le télétravail est possible deux jours par semaine.",
        "Les licornes votent.",
    ]
    assert [d["verdict"] for d in decisions] == ["grounded", "not_grounded"]
    premise = next(c[2]["premise"] for c in fake.calls if c[0] == "grounding")
    assert rag_decision.PREMISE_SEP in premise or "\n" in premise
    assert fake.closed  # loaded for the run, closed at its end


def test_the_grounding_without_an_answer_is_skipped(index):
    session, _ = ready(index)
    chain = own_chain(session)
    stage(chain, "generation").option = "not_run"
    events = run(session, QUESTION, with_stage(chain, "grounding_check"))
    grounding = ended(events, "grounding_check")
    assert grounding["status"] == "skipped" and "réponse" in grounding["error_text"]


def test_the_cloud_filter_calls_the_api_records_the_spend_and_never_leaks_the_key(index):
    session, _ = ready(index, key=KEY)
    seen: list[httpx.Request] = []
    answer = {"answers": {"decision": {"noul": 0.4}}, "usage": {"cost": 1e-05}}
    session._decision_transport = api_transport([answer], seen)
    mark = get_journal().last_seq()
    chain = with_stage(own_chain(session), "passage_filter", "cloud", decision_threshold=13)
    events = run(session, QUESTION, chain)
    assert run_status(events) == "ok"
    decisions = decisions_of(events, "passage_filter")
    assert seen and len(seen) == len(decisions)
    assert all(d["verdict"] == "keep" and d["probability"] == 0.4 for d in decisions)
    body = json.loads(seen[0].content)
    assert body["model"] == "perplexity/pplx-decider-flash-v1.2"
    assert (
        body["questions"]["decision"]["instructions"] == rag_decision.INSTRUCTIONS["filter"]["fr"]
    )
    costs = ended(events, "passage_filter")["costs"]
    assert costs[0]["usd"] == pytest.approx(1e-05 * len(seen))
    everything = [e for e in get_journal().events_since(mark)]
    assert any(e.kind == "consumption_updated" for e in everything)
    assert KEY not in json.dumps([e.payload for e in everything], ensure_ascii=False, default=str)


def test_the_cloud_api_failure_lets_the_chain_go_on_unfiltered(index):
    session, _ = ready(index, key=KEY)
    error = {"error": {"code": 503, "message": "indisponible"}}
    session._decision_transport = api_transport([error], [], status=503)
    chain = with_stage(own_chain(session), "passage_filter", "cloud")
    events = run(session, QUESTION, chain)
    payload = ended(events, "passage_filter")
    assert payload["status"] == "error" and "503" in payload["error_text"]
    assert ended(events, "context")["status"] == "ok"
    assert run_status(events) == "ok"


def test_the_cap_reached_refuses_the_cloud_call(index, monkeypatch):
    session, _ = ready(index, key=KEY)
    seen: list[httpx.Request] = []
    session._decision_transport = api_transport([{"answers": {"decision": {"noul": 1}}}], seen)
    monkeypatch.setattr(session, "_decision_cap_refusal", lambda: "plafond atteint")
    events = run(session, QUESTION, with_stage(own_chain(session), "grounding_check", "cloud"))
    grounding = ended(events, "grounding_check")
    assert grounding["status"] == "error" and "plafond" in grounding["error_text"]
    assert seen == []


# ---------- the real classifier (extra `decision` and its files) ----------


def test_the_real_classifier_when_installed():
    pytest.importorskip("onnxruntime")
    pytest.importorskip("tokenizers")
    model, _ = config.load_config().rag_lab_decision_classifier
    dest = config.models_dir()
    if model is None or any(not (dest / f.path).exists() for f in model.files):
        pytest.skip("fichiers de deberta_xsmall absents (Télécharger dans l'atelier)")
    nli = rag_decision.NliClassifier(
        dest / model.config_path, dest / model.tokenizer_path, dest / model.load_path
    )
    yes, _ = nli.noul(
        "grounding", "en", {"premise": "The sky is blue.", "claim": "The sky is blue."}
    )
    no, _ = nli.noul("grounding", "en", {"premise": "The sky is blue.", "claim": "Cats can fly."})
    assert yes > no
    probs, _ = nli.choice("Who wrote it?", rag_decision.ROUTER_HYPOTHESES["en"])
    assert abs(sum(probs.values()) - 1) < 1e-6
