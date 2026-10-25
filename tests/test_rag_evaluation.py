"""V1.2 story 15 (CAP-11): the Evaluate tab, the judges against the reference annotation, the
aggregates with their n, the family rule, the cloud key and cap, the judge's output and the
four traps.

Real code throughout. The doubles stand at the boundary only: a fake judge, a scripted cloud
transport (`httpx.MockTransport`), the engines' libraries (a stub `llama_cpp`) and the disk and
loopback discovery of local models. No model is loaded and nothing leaves the machine.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import yaml
from fake_engine import FakeEngine
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from test_bricks import HEADERS
from test_cloud import GROQ_TEXT, SENTINEL, Provider, delta, sse
from test_rag import build
from test_rag_lab import _client, run, wait_idle
from test_rag_lab_generation import cloud_session, ready

from wavestack import config
from wavestack.models import servers
from wavestack.models.cloud_base import CallCost, record_spend
from wavestack.models.engine import CancelToken, LlamaCppEngine
from wavestack.rag import evaluation as ev
from wavestack.rag import lab as rag_lab
from wavestack.rag.corpus import RagPassage, RagQuestion, load_rag_questions
from wavestack.rag.diagnosis import Listed
from wavestack.session.app_session import SendRefused

LANGS = ("fr", "en", "de")
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "src" / "wavestack" / "web" / "static"
VERDICT_JSON = '{"verdict": "yes", "why": "La réponse suit le contexte."}'


@pytest.fixture(autouse=True)
def _fresh_content_caches():
    config.clear_content_caches()
    yield
    config.clear_content_caches()


@pytest.fixture
def index(tmp_path: Path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


class FakeJudge:
    """A scripted judge: one output per call, the prompts kept."""

    label = "fake"

    def __init__(self, *outputs: str) -> None:
        self.outputs = list(outputs)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.outputs[min(len(self.prompts) - 1, len(self.outputs) - 1)]


# ---------- the measures without a model (values written by hand) ----------


def test_recall_at_k_on_hand_written_ranks():
    assert ev.recall_at_k([1, 2], 3) == 1.0
    assert ev.recall_at_k([2, None], 3) == 0.5  # two expected passages, one found
    assert ev.recall_at_k([None], 3) == 0.0  # an absent rank
    assert ev.recall_at_k([5, 1], 3) == 0.5  # a passage beyond k does not count
    assert ev.recall_at_k([4], 3) == 0.0
    assert ev.recall_at_k([], 3) is None  # a question with no expected passage


def test_the_mrr_is_the_inverse_of_the_first_expected_passage_found():
    assert ev.reciprocal_rank([2]) == 0.5
    assert ev.reciprocal_rank([None, 4, 2]) == 0.5  # the best of the found ones
    assert ev.reciprocal_rank([None]) == 0.0  # absent: 0
    assert ev.reciprocal_rank([]) is None
    questions = [[1], [2], [None], [4]]  # mean over questions: (1 + 1/2 + 0 + 1/4) / 4
    assert ev.mean(ev.reciprocal_rank(r) for r in questions) == pytest.approx(0.4375)


def test_a_session_run_reads_the_last_ordered_list_before_the_context():
    question = RagQuestion(
        id="q",
        type="multi_hop",
        question_text="?",
        expected_answer_text="!",
        expected_passages=[
            RagPassage(doc_id="a", anchor_text="alpha"),
            RagPassage(doc_id="b", anchor_text="beta"),
        ],
    )
    a, b, other = Listed("a", "x alpha y"), Listed("b", "x beta y"), Listed("c", "gamma")
    searches = {"vector_search": [other, a], "lexical_search": [b, other]}
    assert ev.run_ranks(question, searches) == [2, 1]  # the best rank of either search
    fused = searches | {"fusion": [other, b, a]}
    assert ev.run_ranks(question, fused) == [3, 2]
    reranked = fused | {"rerank": [a, other], "context": [other]}
    assert ev.run_ranks(question, reranked) == [1, None]  # the reranking wins; the context never


def test_the_refusal_rule_reads_the_formulas_of_the_content_in_each_language():
    for lang in LANGS:
        markers = ev.load_evaluation(lang).refusal_markers
        assert ev.refused(f"Alors… {markers[0].upper()}, désolé.", markers)
        assert not ev.refused("Le stationnement est remboursé à 50 %.", markers)


# ---------- the table, the aggregates, the threshold ----------


def row(question_id: str = "q_fact_pwd", preset: str = "dense", **verdicts):
    return {
        "question_id": question_id,
        "preset": preset,
        "recall_at_k": 1.0,
        "reciprocal_rank": 1.0,
        "cells": {
            c: {
                "applicable": True,
                "reference": r,
                "judges": {
                    role: None if v is None else {"verdict": v, "agreement": ev.agreement(v, r)}
                    for role, v in (("local", lo), ("cloud", cl))
                },
            }
            for c, (r, lo, cl) in verdicts.items()
        }
        | {c: {"applicable": False} for c in ev.CRITERIA if c not in verdicts},
    }


def agg(rows, measure, who="local"):
    return next(a for a in ev.aggregates(rows) if a["measure"] == measure and a["who"] == who)


def test_an_aggregate_carries_its_n_and_says_when_too_few():
    four = [row(f"q{n}", faithfulness=("yes", "yes", "no")) for n in range(4)]
    five = [*four, row("q4", faithfulness=("yes", "partly", "no"))]
    assert (agg(four, "faithfulness")["n"], agg(four, "faithfulness")["too_few"]) == (4, True)
    found = agg(five, "faithfulness")
    assert (found["n"], found["too_few"]) == (5, False)
    assert ev.MIN_SAMPLE == 5 and found["value"] == pytest.approx(0.9)  # (4 * 1 + 0.5) / 5
    assert agg(five, "faithfulness", "cloud")["value"] == 0.0
    assert agg(five, "faithfulness", "reference")["value"] == 1.0


def test_unreadable_verdicts_are_counted_apart_and_left_out_of_the_mean():
    rows = [
        row("q1", relevance=("yes", "yes", "yes")),
        row("q2", relevance=("yes", "unreadable", "yes")),
        row("q3", relevance=("yes", "no", "yes")),
    ]
    found = agg(rows, "relevance")
    assert (found["n"], found["unreadable"], found["value"]) == (2, 1, 0.5)
    assert agg(rows, "relevance", "agreement_local")["n"] == 2  # unreadable: not an agreement


def test_an_unannotated_cell_is_out_of_the_agreement_rates():
    rows = [row("q1", accuracy=(None, "yes", "no")), row("q2", accuracy=("yes", "yes", "no"))]
    assert agg(rows, "accuracy", "agreement_local")["n"] == 1
    assert ev.agreement("yes", None) == "unannotated" and ev.agreement(None, "yes") == "none"
    assert ev.agreement("no", "yes") == "disagree" and ev.agreement("yes", "yes") == "agree"


def test_the_recorded_set_is_a_table_with_n_architectures_and_judges():
    for lang in LANGS:
        content = ev.load_evaluation(lang)
        table = ev.build_table(content, lang)
        assert table["n"] == 10 and table["architectures"] == ["dense", "hybrid"]
        assert table["judges_n"] == 2 and len(table["rows"]) == 20
        types = {r["type"] for r in table["rows"]}
        assert types >= {"factual", "multi_hop", "temporal", "no_answer"}


def test_the_table_has_a_cell_per_criterion_and_a_disagreement_is_written_out():
    table = ev.build_table(ev.load_evaluation("fr"), "fr")
    badge = next(
        r for r in table["rows"] if r["question_id"] == "q_fact_badge" and r["preset"] == "dense"
    )
    faith = badge["cells"]["faithfulness"]
    assert faith["reference"] == "no" and faith["judges"]["local"]["verdict"] == "yes"
    assert faith["judges"]["local"]["agreement"] == "disagree"
    assert faith["judges"]["cloud"]["agreement"] == "agree"
    assert not any(k in badge for k in ("score", "global", "overall"))  # no score per question
    # Ranks (dense: [4], k = 3): beyond k, so recall@3 = 0, and MRR = 1/4.
    assert (badge["recall_at_k"], badge["reciprocal_rank"]) == (0.0, 0.25)


def test_a_no_answer_question_evaluates_only_the_correct_refusal():
    table = ev.build_table(ev.load_evaluation("fr"), "fr")
    parking = next(r for r in table["rows"] if r["question_id"] == "q_noanswer_parking")
    assert parking["recall_at_k"] is None and parking["reciprocal_rank"] is None
    applicable = {c for c, cell in parking["cells"].items() if cell["applicable"]}
    assert applicable == {"correct_refusal"}
    dense = next(
        r
        for r in table["rows"]
        if r["question_id"] == "q_noanswer_parking" and r["preset"] == "dense"
    )
    hybrid = next(
        r
        for r in table["rows"]
        if r["question_id"] == "q_noanswer_parking" and r["preset"] == "hybrid"
    )
    assert dense["cells"]["correct_refusal"]["rule"] == "yes"  # "Je ne sais pas…"
    assert hybrid["cells"]["correct_refusal"]["rule"] == "no"  # it made something up
    # The other criteria stay out of the aggregates.
    measures = {a["measure"] for a in table["aggregates"] if a["preset"] == "dense"}
    assert "correct_refusal" in measures and "faithfulness" in measures  # from the other questions
    only = ev.aggregates([parking])
    assert {a["measure"] for a in only if a["who"] != "metric"} == {"correct_refusal"}


def test_a_free_question_is_left_out_of_n_and_a_session_run_adds_its_row():
    content = ev.load_evaluation("fr")
    free = ev.LiveRun(run_id="lab1", question_id="q_libre", preset="dense", stages=[])
    assert ev.build_table(content, "fr", [free])["n"] == 10
    stages = [
        diag_stage(
            "vector_search", [("mots_de_passe", "Le mot de passe compte au minimum 14 caractères")]
        ),
        diag_stage(
            "context", [("mots_de_passe", "Le mot de passe compte au minimum 14 caractères")]
        ),
    ]
    live = ev.LiveRun(
        run_id="lab2",
        question_id="q_fact_pwd",
        preset="custom",
        top_k=3,
        stages=stages,
        answer_text="14 caractères.",
    )
    table = ev.build_table(content, "fr", [live])
    assert table["n"] == 10 and "custom" in table["architectures"]  # a known question
    added = next(r for r in table["rows"] if r["source"] == "session")
    assert added["run_id"] == "lab2" and (added["recall_at_k"], added["reciprocal_rank"]) == (
        1.0,
        1.0,
    )
    assert added["cells"]["faithfulness"]["judges"] == {"local": None, "cloud": None}
    assert added["cells"]["faithfulness"]["reference"] is None  # « non annoté »


def diag_stage(kind, items):
    from wavestack.rag import diagnosis

    return diagnosis.LiveStage(
        kind=kind, items=[diagnosis.LiveItem(doc_id=d, text=t) for d, t in items]
    )


# ---------- the families ----------


def candidate(name, *, ref=None, engine=None, architecture=None, size=1):
    return SimpleNamespace(
        status="found",
        ref=ref or name,
        path=None,
        name=name,
        architecture=architecture,
        publisher_hint=None,
        engine=engine,
        size_bytes=size,
    )


def test_a_judge_never_judges_its_own_family():
    texts = ev.load_evaluation("fr").texts
    qwen = ev.family_of([], ["qwen3-0.6b"], "fr")
    assert qwen == "qwen"
    assert ev.refusal_reason("qwen", qwen, texts)  # a Qwen judge, a Qwen generator
    for family in ("mistral", "gemini", "claude", "granite"):
        assert ev.refusal_reason(family, qwen, texts) is None
    assert ev.refusal_reason("mistral", "mistral", texts)  # a cloud Mistral, a Mistral generator
    assert ev.refusal_reason("other", qwen, texts)  # unknown judge: set aside
    assert ev.refusal_reason("granite", "other", texts)  # unknown generator: no judge


def test_the_local_panel_admits_one_family_apart_and_gives_each_reason():
    texts = ev.load_evaluation("fr").texts
    found = [
        candidate("Qwen3-1.7B-Q4.gguf", size=3),
        candidate("granite-4.0-micro.gguf", size=2),
        candidate("mystery-model.gguf", size=1),
        candidate("granite-4.0-h:latest", engine="ollama", size=1),
        candidate("gemma-3-1b.gguf", engine="llama_server", size=4),
    ]
    options = {o.label: o for o in ev.local_options(found, "qwen", texts, "fr")}
    assert (
        options["Qwen3-1.7B-Q4.gguf"].reason and "famille" in options["Qwen3-1.7B-Q4.gguf"].reason
    )
    assert (
        options["mystery-model.gguf"].reason and "inconnue" in options["mystery-model.gguf"].reason
    )
    assert "GBNF" in options["granite-4.0-h:latest"].reason  # Ollama: no grammar
    assert options["granite-4.0-micro.gguf"].reason is None
    assert options["gemma-3-1b.gguf"].reason is None  # llama-server accepts a grammar
    ordered = ev.local_options(found, "qwen", texts, "fr")
    assert [o.label for o in ordered][:2] == [
        "granite-4.0-micro.gguf",
        "gemma-3-1b.gguf",
    ]  # admitted first, smallest first
    assert ev.local_options([], "qwen", texts, "fr") == []


def test_the_cloud_panel_sets_the_generators_family_aside():
    texts = ev.load_evaluation("fr").texts
    entries = config.load_config().cloud_models[0]
    options = {o.id: o for o in ev.cloud_options(entries, "mistral", lambda e: False, texts, "fr")}
    assert options["mistral"].reason and options["gemini"].reason is None
    assert not options["gemini"].has_key


# ---------- the judge's output ----------


def test_a_judge_output_that_follows_the_grammar_is_read():
    read = ev.read_verdict(VERDICT_JSON)
    assert (read.verdict, read.why_text) == ("yes", "La réponse suit le contexte.")
    padded = ev.read_verdict('Voici : {"verdict": "partly", "why": "incomplet"} fin')
    assert padded.verdict == "partly"


@pytest.mark.parametrize(
    "output",
    ["", "oui", "{", '{"verdict": "oui", "why": "x"}', '{"verdict": 3}', '["yes"]', '{"why": "x"}'],
)
def test_a_judge_output_off_the_grammar_is_unreadable_and_not_retried(output):
    judge = FakeJudge(output, VERDICT_JSON)
    case = ev.Case("Q ?", "R.", ["c1"], "attendue")
    texts = ev.load_evaluation("fr").texts
    assert ev.judge_case(judge, "relevance", case, texts).verdict == ev.UNREADABLE
    assert len(judge.prompts) == 1  # no silent retry


def test_the_prompt_of_each_criterion_holds_what_it_reads_and_nothing_more():
    case = ev.Case("LA-QUESTION", "LA-REPONSE", ["LE-CONTEXTE"], "L-ATTENDUE")
    texts = ev.load_evaluation("fr").texts
    prompt = {c: ev.judge_prompt(c, case, texts) for c in ev.CRITERIA}
    assert (
        "LE-CONTEXTE" in prompt["context_precision"]
        and "LA-REPONSE" not in prompt["context_precision"]
    )
    assert "LE-CONTEXTE" in prompt["faithfulness"] and "L-ATTENDUE" not in prompt["faithfulness"]
    assert "LE-CONTEXTE" not in prompt["relevance"] and "LA-REPONSE" in prompt["relevance"]
    assert "L-ATTENDUE" in prompt["accuracy"] and "LA-QUESTION" in prompt["correct_refusal"]


def test_the_shipped_grammar_is_accepted_by_llama_cpp_without_a_model():
    llama_cpp = pytest.importorskip("llama_cpp")
    assert llama_cpp.LlamaGrammar.from_string(ev.GRAMMAR, verbose=False) is not None


# ---------- the engines take a grammar ----------


def stub_llama(received: list):
    class Vocab:
        def is_eog(self, token):
            return token == 1

        def token_pieces(self, ids):
            return [b"{}" if i == 0 else b"" for i in ids]

    def generate(prompt_ids, **kwargs):
        received.append(kwargs)
        yield 0
        yield 1

    engine = LlamaCppEngine.__new__(LlamaCppEngine)
    engine._lib = SimpleNamespace(
        llama_perf_context_reset=lambda ctx: None,
        llama_perf_context=lambda ctx: SimpleNamespace(n_p_eval=0),
        LlamaGrammar=SimpleNamespace(from_string=lambda text, verbose: ("grammar", text)),
    )
    engine._llm = SimpleNamespace(ctx=None, generate=generate)
    engine._tokenizer = Vocab()
    engine._last_evaluated = None
    return engine


def test_the_in_process_engine_passes_the_grammar_to_llama_cpp():
    received: list = []
    engine = stub_llama(received)
    out = list(engine.complete([5], [], 8, CancelToken(), grammar='root ::= "{}"'))
    assert "".join(f.text for f in out) == "{}"
    assert received[-1]["grammar"] == ("grammar", 'root ::= "{}"')
    list(engine.complete([5], [], 8, CancelToken()))  # without: free sampling, as before
    assert "grammar" not in received[-1]


def load_fake_server():
    path = ROOT / "tools" / "e2e" / "fake_local_server.py"
    spec = importlib.util.spec_from_file_location("fake_local_server_s15", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["fake_local_server_s15"] = module
    spec.loader.exec_module(module)
    return module


def test_llama_server_gets_the_grammar_in_the_body_of_the_completion():
    client = TestClient(load_fake_server().create_app("llama_server"))
    bodies: list[dict] = []

    def bridge(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/completion":
            bodies.append(json.loads(request.content))
        answer = client.request(request.method, request.url.path, content=request.content)
        return httpx.Response(answer.status_code, content=answer.content)

    engine = servers.LlamaServerEngine(
        "http://127.0.0.1:8080", transport=httpx.MockTransport(bridge)
    )
    ids = engine.tokenize("<|im_start|>user\nBonjour<|im_end|>\n<|im_start|>assistant\n")
    list(engine.complete(ids, [], 20, CancelToken(), grammar="root ::= [a-z]+"))
    list(engine.complete(ids, [], 20, CancelToken()))
    assert bodies[0]["grammar"] == "root ::= [a-z]+" and "grammar" not in bodies[1]
    engine.close()


def test_an_engine_without_the_argument_stays_callable():
    engine = FakeEngine(output="ok")
    assert "".join(f.text for f in engine.complete([1], [], 8, CancelToken())) == "ok"
    assert engine.grammars == []


# ---------- the traps ----------


def test_the_two_definitions_of_faithfulness_differ_on_the_shipped_claims():
    content = ev.load_evaluation("en")
    claims = next(t for t in content.traps if t.kind == "two_tools").claims
    assert [c.label for c in claims] == [
        "supported",
        "supported",
        "supported",
        "unsupported",
        "contradicted",
    ]
    assert ev.faithfulness_ragas(claims) == 0.6  # 3 supported of 5, written by hand
    assert ev.faithfulness_deepeval(claims) == 0.8  # 4 not contradicted of 5
    shown = ev.replay_trap("two_tools", "en")
    assert (shown["ragas"], shown["deepeval"]) == (0.6, 0.8) and shown["recorded"] is True


def test_the_judge_changes_the_ranking_recomputed_from_the_recorded_verdicts():
    content = ev.load_evaluation("fr")
    order = ev.ranking(content)
    assert [r["preset"] for r in order["local"]] == ["dense", "hybrid"]
    assert [r["preset"] for r in order["cloud"]] == ["hybrid", "dense"]
    # Recomputed by hand from the YAML: the mean of the local judge's verdicts on dense.
    value = {"yes": 1.0, "partly": 0.5, "no": 0.0}
    mine = [
        value[v.local]
        for r in content.recorded.runs
        if r.preset == "dense"
        for v in r.verdicts.values()
        if v.local in value
    ]
    assert order["local"][0]["value"] == sum(mine) / len(mine)
    assert ev.replay_trap("ranking", "fr")["ranking"] == order


def test_two_judges_two_verdicts_and_the_variance_of_one_judge():
    two = ev.replay_trap("two_judges", "fr")
    assert two["verdicts"]["local"]["verdict"] != two["verdicts"]["cloud"]["verdict"]
    assert two["verdicts"]["local"]["why_text"] != two["verdicts"]["cloud"]["why_text"]
    assert two["question_text"] and two["answer_text"]
    variance = ev.replay_trap("variance", "fr")
    assert len(variance["passes"]) == 2
    assert variance["passes"][0]["verdict"] != variance["passes"][1]["verdict"]
    assert variance["causes"] == ["temperature", "passage_order"]
    assert ev.replay_trap("nope", "fr") is None


# ---------- the shipped data ----------


def test_the_data_is_the_same_in_the_three_languages():
    docs = {
        lang: yaml.safe_load((config.content_file(ev.FILE, lang)).read_text(encoding="utf-8"))
        for lang in LANGS
    }

    def keys(node):
        if isinstance(node, dict):
            return {k: keys(v) for k, v in node.items()}
        return [keys(v) for v in node][:1] if isinstance(node, list) else None

    for lang in ("en", "de"):
        assert keys(docs[lang]["texts"]) == keys(docs["fr"]["texts"])
        fr, other = docs["fr"]["recorded"], docs[lang]["recorded"]
        for a, b in zip(fr["runs"], other["runs"], strict=True):
            assert {k: v for k, v in a.items() if k != "answer_text"} == {
                k: v for k, v in b.items() if k != "answer_text"
            }
        assert fr["judges"] == other["judges"] and fr["provenance"] == other["provenance"]
        for a, b in zip(docs["fr"]["traps"], docs[lang]["traps"], strict=True):
            assert (
                a["id"] == b["id"] and a.get("verdicts", {}).keys() == b.get("verdicts", {}).keys()
            )
            assert [p["verdict"] for p in a.get("passes", [])] == [
                p["verdict"] for p in b.get("passes", [])
            ]
            assert [c["label"] for c in a.get("claims", [])] == [
                c["label"] for c in b.get("claims", [])
            ]
            for role, v in a.get("verdicts", {}).items():
                assert v["verdict"] == b["verdicts"][role]["verdict"]
        # The placeholders stay the same, text by text.
        for path in ("banner_text", "provenance_constructed_text", "annotation_human_text"):
            assert set(re.findall(r"\{\w+\}", docs["fr"]["texts"][path])) == set(
                re.findall(r"\{\w+\}", docs[lang]["texts"][path])
            )


@pytest.mark.parametrize("lang", LANGS)
def test_every_question_and_preset_cited_exists_and_the_provenance_is_honest(lang):
    content = ev.load_evaluation(lang)
    known = {q.id: q for q in load_rag_questions(lang)}
    for run_ in content.recorded.runs:
        assert run_.question_id in known and run_.preset in rag_lab.PRESETS
        question = known[run_.question_id]
        assert len(run_.ranks) == len(question.expected_passages)
        wanted = {"correct_refusal"} if question.type == "no_answer" else set(ev.CRITERIA[:4])
        assert set(run_.verdicts) == wanted
    for trap in content.traps:
        assert trap.question_id is None or trap.question_id in known
    provenance = content.recorded.provenance
    assert provenance.kind in ("constructed", "recorded")
    assert provenance.kind == "constructed" or provenance.recorded_on
    assert all(j.model for j in content.recorded.judges.values())
    # The reference is a draft until Anaël validates it: never presented as human.
    assert content.recorded.annotation.annotated_by == "draft"
    with pytest.raises(ValidationError):
        ev.Provenance(kind="recorded")


def test_the_recorded_judges_are_of_two_other_families_than_the_generator():
    content = ev.load_evaluation("fr")
    generator = ev.family_of([], [content.recorded.generator], "fr")
    local = ev.family_of([], [content.recorded.judges["local"].model], "fr")
    cloud = ev.family_of([], [content.recorded.judges["cloud"].model], "fr")
    assert generator == "qwen" and len({generator, local, cloud}) == 3
    assert "other" not in (local, cloud)


# ---------- the endpoints ----------


def test_the_state_and_the_traps_over_http(index):
    session = ready(index)
    session._rag_judge_discover = lambda: []
    client = _client(session)
    body = client.get("/api/rag_lab/evaluation").json()
    assert body["min_sample"] == 5 and body["table"]["n"] == 10
    assert body["panel"]["local"] == [] and body["finops"]["max_session_usd"] == 5.0
    assert [t["id"] for t in body["traps"]] == ["two_judges", "variance", "two_tools", "ranking"]
    assert body["provenance"]["kind"] == "constructed" and body["lang"] == "fr"
    posted = client.post("/api/rag_lab/evaluation", json={"runs": []}, headers=HEADERS).json()
    assert posted["table"] == body["table"] and posted["panel"] is None
    for trap in body["traps"]:
        got = client.get(f"/api/rag_lab/evaluation/traps/{trap['id']}")
        assert got.status_code == 200 and got.json()["recorded"] is True
    assert client.get("/api/rag_lab/evaluation/traps/nope").status_code == 404


def test_the_post_body_is_bounded(index):
    session = ready(index)
    client = _client(session)
    many = [
        {"run_id": f"lab{n}", "question_id": "q_fact_pwd", "preset": "dense", "stages": []}
        for n in range(41)
    ]
    assert (
        client.post("/api/rag_lab/evaluation", json={"runs": many}, headers=HEADERS).status_code
        == 422
    )
    huge = {
        "run_id": "lab1",
        "question_id": "q_fact_pwd",
        "preset": "dense",
        "stages": [],
        "answer_text": "x" * 20001,
    }
    assert (
        client.post("/api/rag_lab/evaluation", json={"runs": [huge]}, headers=HEADERS).status_code
        == 422
    )
    odd = {"run_id": "lab1", "question_id": "q_fact_pwd", "preset": "Dense!", "stages": []}
    assert (
        client.post("/api/rag_lab/evaluation", json={"runs": [odd]}, headers=HEADERS).status_code
        == 422
    )


def test_a_session_run_posted_by_the_page_is_added_to_n_and_a_free_question_is_not(index):
    session = ready(index)
    client = _client(session)
    runs = [
        {
            "run_id": "lab1",
            "question_id": "q_libre",
            "preset": "dense",
            "stages": [],
            "answer_text": "x",
        },
        {
            "run_id": "lab2",
            "question_id": "q_fact_pwd",
            "preset": "custom",
            "stages": [],
            "answer_text": "x",
        },
    ]
    table = client.post("/api/rag_lab/evaluation", json={"runs": runs}, headers=HEADERS).json()[
        "table"
    ]
    assert table["n"] == 10 and sum(r["source"] == "session" for r in table["rows"]) == 1


JUDGE_URL = "/api/intentions/rag_lab_judge"


def judge_body(**changes):
    run_ = {
        "run_id": "lab1",
        "question_id": "q_fact_pwd",
        "preset": "dense",
        "top_k": 3,
        "stages": [
            {
                "kind": "context",
                "items": [
                    {
                        "doc_id": "mots_de_passe",
                        "text": "Le mot de passe compte au minimum 14 caractères.",
                    }
                ],
            }
        ],
        "answer_text": "14 caractères.",
    }
    return {"run": run_, "role": "cloud", "judge": "mistral", "criterion": "faithfulness"} | changes


def test_the_intention_is_refused_without_a_known_generator_or_an_admitted_judge(index):
    session = ready(index)
    session._rag_judge_discover = lambda: []
    client = _client(session)
    refused = client.post(JUDGE_URL, json=judge_body(), headers=HEADERS)
    assert refused.status_code == 409 and "inconnu" in refused.json()["detail"]
    session._rag_generators["lab1"] = ("Qwen3 0.6B", "qwen")
    no_local = client.post(JUDGE_URL, json=judge_body(role="local", judge="x"), headers=HEADERS)
    assert no_local.status_code == 409
    unknown = client.post(JUDGE_URL, json=judge_body(judge="nope"), headers=HEADERS)
    assert unknown.status_code == 409
    assert (
        client.post(JUDGE_URL, json=judge_body(criterion="bogus"), headers=HEADERS).status_code
        == 422
    )
    # A criterion that does not apply to the question.
    wrong = client.post(JUDGE_URL, json=judge_body(criterion="correct_refusal"), headers=HEADERS)
    assert wrong.status_code == 409
    free = judge_body()
    free["run"]["question_id"] = "q_libre"
    assert client.post(JUDGE_URL, json=free, headers=HEADERS).status_code == 409


def test_the_intention_is_accepted_in_idle_only(index):
    session = ready(index)
    session._rag_generators["lab1"] = ("Qwen3 0.6B", "qwen")
    config.write_api_key(
        "mistral", config.load_config().cloud_model("mistral").host, SecretStr(SENTINEL)
    )
    session.state, session.reason_text = "turn", None
    refused = _client(session).post(JUDGE_URL, json=judge_body(), headers=HEADERS)
    assert refused.status_code == 409


# ---------- the cloud judge: key, cap, spend ----------


def judged_session(index, provider):
    session = cloud_session(index, provider)
    run(session)  # lab1 is generated by the active model: its generator is kept
    return session


def reply(text: str) -> bytes:
    return sse(
        delta(content=text),
        {**delta("stop"), "usage": {"prompt_tokens": 90, "completion_tokens": 12}},
    )


def test_the_generator_of_a_finished_run_is_kept_and_bounded(index):
    session = judged_session(index, Provider(GROQ_TEXT))
    label, family = session._rag_generators["lab1"]
    assert label == "openai/gpt-oss-120b" and family == "gpt_oss"
    for n in range(session.MAX_RAG_JUDGED + 5):
        session._rag_generators[f"x{n}"] = ("m", "f")
        session._remember_generator(f"y{n}")
    assert len(session._rag_generators) <= session.MAX_RAG_JUDGED
    assert "lab1" not in session._rag_generators  # the oldest left


def live_run(**changes):
    from wavestack.web.app import RagLabJudgeIntention

    return RagLabJudgeIntention.model_validate(judge_body(**changes)).run


def test_a_cloud_judge_without_a_key_sends_nothing(index):
    provider = Provider(GROQ_TEXT)
    session = judged_session(index, provider)
    sent = len(provider.requests)
    with pytest.raises(SendRefused) as refused:
        session.judge_rag_lab_run(
            live_run(), role="cloud", judge_id="gemini", criterion="faithfulness"
        )
    assert "clé" in refused.value.reason_text
    assert len(provider.requests) == sent and session.state == "idle"
    assert config.cloud_key(config.load_config().cloud_model("gemini")) is None


def test_a_cloud_judge_with_a_key_gives_a_verdict_and_the_session_pays_it(index):
    provider = Provider(GROQ_TEXT, reply(VERDICT_JSON))
    session = judged_session(index, provider)
    entry = config.load_config().cloud_model("mistral")
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    sent = len(provider.requests)
    session.judge_rag_lab_run(
        live_run(), role="cloud", judge_id="mistral", criterion="faithfulness"
    )
    wait_idle(session)
    assert len(provider.requests) == sent + 1
    kept = session._rag_verdicts["lab1"]["faithfulness"]["cloud"]
    assert (kept.verdict, kept.judge_label) == ("yes", entry.model)
    body = session.rag_lab_evaluation([live_run().model_copy()])
    row = next(r for r in body["table"]["rows"] if r["source"] == "session")
    judged = row["cells"]["faithfulness"]["judges"]["cloud"]
    assert judged["verdict"] == "yes" and judged["agreement"] == "unannotated"
    assert body["judging"] is False and body["judge_error"] is None


def test_an_unreadable_cloud_answer_is_kept_as_unreadable(index):
    session = judged_session(index, Provider(GROQ_TEXT, reply("Je ne sais pas noter.")))
    entry = config.load_config().cloud_model("mistral")
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    session.judge_rag_lab_run(live_run(), role="cloud", judge_id="mistral", criterion="relevance")
    wait_idle(session)
    assert session._rag_verdicts["lab1"]["relevance"]["cloud"].verdict == "unreadable"


def test_the_session_cap_refuses_the_judgment_before_anything_is_sent(index):
    provider = Provider(GROQ_TEXT)
    session = judged_session(index, provider)
    entry = config.load_config().cloud_model("mistral")
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    record_spend(CallCost(3.0, 2.5, "api"), 0.86)  # 5.50 $ spent, the cap is 5 $
    sent = len(provider.requests)
    with pytest.raises(SendRefused) as refused:
        session.judge_rag_lab_run(
            live_run(), role="cloud", judge_id="mistral", criterion="faithfulness"
        )
    assert "Plafond" in refused.value.reason_text or "plafond" in refused.value.reason_text
    assert len(provider.requests) == sent and session.state == "idle"
    finops = session.rag_lab_evaluation()["finops"]
    assert finops["capped"] is True and finops["max_session_usd"] == 5.0


def test_a_provider_failure_is_said_in_the_tab_not_retried(index):
    failing = httpx.Response(500, json={"error": {"message": "Internal error"}})
    provider = Provider(GROQ_TEXT, failing)
    session = judged_session(index, provider)
    entry = config.load_config().cloud_model("mistral")
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    sent = len(provider.requests)
    session.judge_rag_lab_run(
        live_run(), role="cloud", judge_id="mistral", criterion="faithfulness"
    )
    wait_idle(session)
    assert len(provider.requests) == sent + 1
    assert "Internal error" in session.rag_lab_evaluation()["judge_error"]
    assert "lab1" not in session._rag_verdicts and session.state == "idle"


# ---------- the local judge ----------


def test_a_local_judge_loads_for_the_call_under_a_grammar_and_leaves(index):
    session = ready(index)
    judge_engine = FakeEngine(output=VERDICT_JSON)
    session._engine_factory = lambda path, n_ctx: judge_engine
    session._rag_generators["lab1"] = ("Qwen3 0.6B", "qwen")
    found = candidate("granite-4.0-micro.gguf", ref="fake.gguf")
    found.path = "fake.gguf"
    session._rag_judge_discover = lambda: [found]
    panel = session.rag_lab_evaluation(with_panel=True)["panel"]
    # The panel follows the model that generates now (a fake of unknown family): set aside by
    # prudence. The judgment below is for the run's own generator, a Qwen.
    assert "inconnue" in panel["local"][0]["reason"]
    session.judge_rag_lab_run(
        live_run(), role="local", judge_id="fake.gguf", criterion="faithfulness"
    )
    wait_idle(session)
    kept = session._rag_verdicts["lab1"]["faithfulness"]["local"]
    assert (kept.verdict, kept.judge_label) == ("yes", "granite-4.0-micro.gguf")
    assert judge_engine.grammars == [ev.GRAMMAR]
    assert session._load_registry.holder("rag_lab.judge") is None  # it left the registry
    assert session.state == "idle"


def test_a_local_judge_whose_grant_fails_still_closes_its_engine(index, monkeypatch):
    session = ready(index)
    judge_engine = FakeEngine(output=VERDICT_JSON)
    closed: list[bool] = []
    judge_engine.close = lambda: closed.append(True)
    session._engine_factory = lambda path, n_ctx: judge_engine
    session._rag_generators["lab1"] = ("Qwen3 0.6B", "qwen")
    found = candidate("granite-4.0-micro.gguf", ref="fake.gguf")
    found.path = "fake.gguf"
    session._rag_judge_discover = lambda: [found]

    def refuse(*args, **kwargs):
        raise RuntimeError("grant failed")

    monkeypatch.setattr(session._load_registry, "grant", refuse)
    session.judge_rag_lab_run(
        live_run(), role="local", judge_id="fake.gguf", criterion="faithfulness"
    )
    wait_idle(session)
    assert closed == [True] and judge_engine.grammars == []
    assert "grant failed" in session.rag_lab_evaluation()["judge_error"]
    assert session.state == "idle"


def test_a_local_judge_of_the_generators_family_is_refused(index):
    session = ready(index)
    session._rag_generators["lab1"] = ("Qwen3 0.6B", "qwen")
    found = candidate("Qwen3-1.7B.gguf", ref="q.gguf")
    session._rag_judge_discover = lambda: [found]
    with pytest.raises(SendRefused) as refused:
        session.judge_rag_lab_run(
            live_run(), role="local", judge_id="q.gguf", criterion="faithfulness"
        )
    assert "famille" in refused.value.reason_text


def test_the_verdicts_the_session_keeps_stay_bounded(index):
    session = ready(index)
    for n in range(session.MAX_RAG_JUDGED + 3):
        session._keep_verdict(f"lab{n}", "relevance", ev.SessionVerdict("local", "j", "yes", ""))
    assert len(session._rag_verdicts) == session.MAX_RAG_JUDGED
    assert "lab0" not in session._rag_verdicts and "lab52" in session._rag_verdicts


# ---------- no extra dependency, no average elsewhere ----------


def test_ragas_and_deepeval_are_neither_imported_nor_declared(index):
    session = ready(index)
    session._rag_judge_discover = lambda: []
    client = _client(session)
    client.get("/api/rag_lab/evaluation")
    for trap in ("two_judges", "variance", "two_tools", "ranking"):
        client.get(f"/api/rag_lab/evaluation/traps/{trap}")
    ev.listing("fr")
    assert not any(m.split(".")[0] in ("ragas", "deepeval") for m in sys.modules)
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "ragas" not in pyproject.lower() and "deepeval" not in pyproject.lower()


AVERAGE = re.compile(r"\b(mean|average|avg|mrr|recall_at_k|aggregates?)\b", re.IGNORECASE)
OTHER_TABS = (
    "rag.js",
    "rag-build.js",
    "rag-compare.js",
    "rag-diagnosis.js",
    "rag-attack.js",
    "rag-sheets.js",
)


def strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"(^|[^:\"'`])//.*", r"\1", source)


@pytest.mark.parametrize("name", OTHER_TABS)
def test_no_average_in_the_other_tabs_of_the_page(name):
    code = strip_comments((STATIC / name).read_text(encoding="utf-8"))
    assert not AVERAGE.search(code), AVERAGE.search(code)


def keys_of(node) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in keys_of(v)}
    if isinstance(node, list):
        return {k for v in node for k in keys_of(v)}
    return set()


def test_no_average_in_the_json_of_the_workshop_and_of_the_diagnosis(index):
    session = ready(index)
    client = _client(session)
    shown = [client.get("/api/rag_lab").json(), client.get("/api/rag_lab/diagnosis").json()]
    shown.append(client.get("/api/rag_lab/diagnosis/cases/not_indexed").json())
    for body in shown:
        assert not [k for k in keys_of(body) if AVERAGE.search(k)]


def test_the_evaluate_tab_leaves_the_banner_outside_any_folding_section():
    html = (STATIC / "rag.html").read_text(encoding="utf-8")
    panel = html.split('id="rag-panel-evaluate"')[1].split('id="rag-panel-attack"')[0]
    assert 'id="rag-eval-banner"' in panel and "<details" not in panel
    js = (STATIC / "rag-evaluate.js").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(", js)
