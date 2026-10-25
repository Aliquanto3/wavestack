"""V1.2 story 2: the System One bench, pure logic and replay. No network, no key, no model."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import httpx
import pytest

PATH = Path(__file__).resolve().parents[1] / "tools" / "bench" / "v12s2_system_one_bench.py"
FIXTURE = Path(__file__).parent / "fixtures" / "v12s2"
FAKE_KEY = "sk-or-FAKE-KEY-0123456789"
JEV = "typesafe/jev-1.14"


def _load():
    spec = importlib.util.spec_from_file_location("v12s2_bench_under_test", PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


b = _load()


@pytest.fixture(scope="module")
def built():
    return b.build_all()


@pytest.fixture
def fixture_dir(tmp_path):
    target = tmp_path / "fx"
    shutil.copytree(FIXTURE, target)
    return target


def _digits(text: str) -> set[str]:
    return set(re.findall(r"\d+", text))


# ---------- item set ----------


def test_counts_per_language(built):
    assert built.dropped == []
    for lang in b.LANGS:
        mine = [i for i in built.items if i.lang == lang]
        assert sum(i.task == "filter" for i in mine) == 93  # 27 + 21 x 3 + 3 stale
        assert sum(i.task == "grounding" for i in mine) == 57  # 18 + 36 + 3
    assert len(built.items) == 450
    assert len({i.id for i in built.items}) == 450


def test_filter_labels_by_construction(built):
    from wavestack.rag.corpus import load_rag_questions

    for lang in b.LANGS:
        for q in load_rag_questions(lang):
            mine = [
                i
                for i in built.items
                if i.task == "filter" and i.question_id == q.id and i.lang == lang
            ]
            pos = sorted((i for i in mine if i.label), key=lambda i: i.id)
            assert len(pos) == len(q.expected_passages)
            for item, passage in zip(pos, q.expected_passages, strict=True):
                assert b._norm(passage.anchor_text) in b._norm(item.text)
            negatives = [i for i in mine if i.group == "main" and not i.label]
            assert sorted(i.kind for i in negatives) == ["hard", "random", "same_doc"]
            anchors = [b._norm(p.anchor_text) for p in (*q.expected_passages, *q.trap_passages)]
            for item in negatives:
                assert not any(a in b._norm(item.text) for a in anchors)
            assert len([i for i in mine if i.group == "stale"]) == len(q.trap_passages)


def test_inactive_documents_never_in_items(built):
    from wavestack.rag.corpus import load_rag_content

    texts = " ".join(i.text for i in built.items)
    inactive = [d.title_text for d in load_rag_content("fr").documents if not d.active]
    assert inactive
    for title in inactive:
        assert title not in texts


def test_claims_checks(built):
    groups: dict[tuple[str, str], list] = {}
    for i in built.items:
        if i.task == "grounding":
            groups.setdefault((i.lang, i.question_id), []).append(i)
    for group in groups.values():
        supported = next((i for i in group if i.label), None)
        for item in group:
            if item.label:
                assert _digits(item.query) <= _digits(item.text), item.id
            else:
                assert b._norm(item.query) not in b._norm(item.text), item.id
                if item.kind == "number":
                    assert supported
                    assert _digits(item.query) != _digits(supported.query), item.id


def test_hand_written_claims_per_language():
    claims = b.load_claims()
    for lang in b.LANGS:
        assert sum(len(v) for v in claims[lang].values()) == 39
    assert set(claims["fr"]) == set(claims["en"]) == set(claims["de"])


def test_provenance_refuses_foreign_text(built):
    item = built.items[0]
    b.assert_provenance([item])
    args = (item.id, item.task, item.lang, item.kind, item.label)
    with pytest.raises(b.ProvenanceError):
        b.assert_provenance([b.Item(*args, item.query, "texte étranger")])
    with pytest.raises(b.ProvenanceError):
        b.assert_provenance([b.Item(*args, "question libre", item.text)])


# ---------- metrics ----------


def test_auc_and_ties():
    assert b.auc([0.9, 0.8, 0.2, 0.1], [True, True, False, False]) == 1.0
    assert b.auc([0.5, 0.5, 0.5, 0.5], [True, True, False, False]) == 0.5
    assert b.auc([0.1, 0.2], [True, True]) is None
    lo, hi = b.auc_ci([0.9, 0.8, 0.7, 0.2, 0.1, 0.3], [True] * 3 + [False] * 3, draws=50)
    assert lo <= 1.0 and hi == 1.0


def test_threshold_and_operating_point():
    pos = [0.9, 0.8, 0.7, 0.6, 0.5]
    assert b.threshold_for_recall(pos, 0.8) == 0.6
    rows = [{"score": s, "label": True, "group": "main", "lang": "fr"} for s in pos]
    rows += [
        {"score": s, "label": False, "group": "main", "lang": "fr"} for s in (0.65, 0.2, 0.1, 0.05)
    ]
    rows += [{"score": 0.3, "label": False, "group": "stale", "lang": "fr"}]
    m = b.evaluate_at("filter", rows, 0.6)
    assert m["recall"] == 0.8 and m["reject_share"] == 0.75 and m["stale_reject_share"] == 1.0
    g = b.evaluate_at("grounding", rows, 0.6)
    assert g["h7"] == 0.25 and g["h7_ci"][0] < 0.25 < g["h7_ci"][1]


def test_wilson_calibration_histogram():
    assert b.wilson(0, 0) is None
    lo, hi = b.wilson(1, 4)
    assert 0 < lo < 0.25 < hi < 1
    cal = b.calibration([0.1, 0.1, 0.9, 1.0], [False, True, True, True])
    assert cal[0]["observed"] == 0.5 and cal[-1]["n"] == 2
    assert sum(b.histogram([0.0, 0.5, 1.0])) == 3


# ---------- replay ----------


def test_dry_run_fixture_is_byte_identical(fixture_dir, built):
    report, agg = b.dry_run(fixture_dir, built.items)
    assert report == (FIXTURE / "expected_report.md").read_text("utf-8")
    again, _ = b.dry_run(fixture_dir, built.items)
    assert again == report
    assert "DONNÉES SYNTHÉTIQUES" in report
    assert "publié, non mesuré" in report
    assert agg["candidates"][JEV]["status"] == "measured"


def test_missing_case_names_model_and_item(fixture_dir, built):
    path = b.recorded_path(fixture_dir, JEV)
    lines = path.read_text("utf-8").splitlines()
    missing = json.loads(lines[0])
    path.write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")
    with pytest.raises(b.ReplayError) as err:
        b.dry_run(fixture_dir, built.items)
    assert JEV in str(err.value) and missing["item_id"] in str(err.value)


def test_stale_case_refused(fixture_dir, built):
    path = b.recorded_path(fixture_dir, JEV)
    rows = [json.loads(x) for x in path.read_text("utf-8").splitlines()]
    rows[0]["request_sha256"] = "0" * 64
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    with pytest.raises(b.ReplayError, match="périmé"):
        b.dry_run(fixture_dir, built.items)


def test_template_report_says_not_measured(tmp_path, built):
    report, _ = b.dry_run(tmp_path / "none", built.items)
    assert "pas encore mesuré" in report
    assert "Aucun choix" in report
    assert "écarté" in report  # Strands Decider 2B and AnyJev, with the reason
    assert "450" in report


def test_committed_report_is_the_template_until_measured(built):
    report, _ = b.dry_run(None, built.items)
    committed = b.REPORT_PATH.read_text("utf-8")
    if "enregistrée du" not in committed:
        assert committed == report


# ---------- request, key, host ----------


def _item(built, task="filter"):
    return next(i for i in built.items if i.task == task and i.lang == "fr")


def test_request_shape_with_fake_transport(built):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = json.loads(request.content)
        assert set(body) == {"model", "state", "questions"}
        assert body["model"] == JEV
        (q,) = body["questions"].values()
        assert q["type"] == "noul" and q["instructions"]
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
        assert str(request.url) == b.ENDPOINT_URL
        return httpx.Response(
            200,
            json={
                "model": "typesafe/jev-1.14-20261014",
                "answers": {"decision": {"noul": 0.8, "debug": "x"}},
                "usage": {"input_tokens": 10, "output_tokens": 1, "cost": 0.0001, "secret": "z"},
                "id": "gen-123",
            },
        )

    client = b.DecisionClient(FAKE_KEY, transport=httpx.MockTransport(handler))
    raw = client.post(b.body_bytes(b.request_body(JEV, _item(built))))
    assert raw.status == 200 and len(seen) == 1
    assert b.retained(JEV, raw) == {
        "model_returned": "typesafe/jev-1.14-20261014",
        "noul": 0.8,
        "input_tokens": 10,
        "output_tokens": 1,
        "cost": 0.0001,
    }


def test_host_allow_list():
    with pytest.raises(b.ForbiddenHost):
        b.DecisionClient(FAKE_KEY, url="https://example.com/api/alpha/decisions")
    b.check_host(b.ENDPOINT_URL)
    with pytest.raises(b.ForbiddenHost):
        b.check_host("http://openrouter.ai.evil.example/x")


def test_read_key_order():
    assert b.read_key({b.KEY_ENV: "a"}, registry=lambda n: "b") == "a"
    assert b.read_key({}, registry=lambda n: "b") == "b"
    assert b.read_key({}, registry=lambda n: None) is None
    assert FAKE_KEY not in b.redact(f"boom {FAKE_KEY}", FAKE_KEY)


def _ok_handler(cost=0.0001, noul=0.7):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "m-1",
                "answers": {"decision": {"noul": noul}},
                "usage": {"input_tokens": 5, "output_tokens": 1, "cost": cost},
            },
        )

    return handler


def _run(built, path, handler, models, budget=None, reps=2, n=4, sleep=None):
    items = b.fixture_items(built.items)[:n]
    client = b.DecisionClient(FAKE_KEY, transport=httpx.MockTransport(handler))
    budget = budget or b.Budget()
    state = b.run_online(
        items,
        models,
        path,
        client,
        budget,
        reps=reps,
        today=lambda: "2000-01-01",
        sleep=sleep or (lambda s: None),
        clock=lambda: 0.0,
        log=lambda m: None,
    )
    return items, state


def test_key_never_written_or_printed(built, tmp_path, capsys):
    counter = {"n": 0}

    def handler(request):
        counter["n"] += 1
        if counter["n"] in (3, 4):
            return httpx.Response(500, text=f"upstream said {FAKE_KEY} is wrong")
        return httpx.Response(
            200,
            json={
                "model": "m-1",
                "answers": {"decision": {"noul": 0.6}},
                "usage": {"cost": 0.0},
                "echo_key": FAKE_KEY,
                "id": "gen-1",
            },
        )

    _run(built, tmp_path, handler, [JEV], n=6)
    out = capsys.readouterr()
    assert FAKE_KEY not in out.out + out.err
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert FAKE_KEY not in path.read_text("utf-8"), path
    rows = b.read_records(b.recorded_path(tmp_path, JEV))
    assert any(r["error"] for r in rows)
    allowed = {
        "item_id", "candidate", "rep", "request_sha256", "status", "model_returned", "noul",
        "input_tokens", "output_tokens", "cost", "calls", "latency_ms", "date", "error",
    }  # fmt: skip
    assert all(set(r) == allowed for r in rows)


def test_unknown_model_single_attempt(built, tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(404, json={"error": "unknown model"})

    _, state = _run(built, tmp_path, handler, ["liquid/d1"])
    assert len(calls) == 1
    probes = json.loads((tmp_path / "probes.json").read_text("utf-8"))
    assert probes["liquid/d1"]["status"] == "unknown_model"
    assert state["incomplete"] == {}


def test_server_error_one_retry_then_error(built, tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, text="down")

    _run(built, tmp_path, handler, [JEV], reps=1, n=1)
    assert len(calls) == 2
    (row,) = b.read_records(b.recorded_path(tmp_path, JEV))
    assert row["noul"] is None and row["error"] and row["calls"] == 2


def test_rate_limit_waits_and_is_not_an_error(built, tmp_path):
    state = {"n": 0}
    waits = []

    def handler(request):
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "300"}, text="slow")
        return _ok_handler()(request)

    _run(built, tmp_path, handler, [JEV], reps=1, n=1, sleep=waits.append)
    assert waits == [b.RETRY_AFTER_MAX_S]
    (row,) = b.read_records(b.recorded_path(tmp_path, JEV))
    assert row["noul"] == 0.7 and row["error"] is None


def test_total_cap_stops_run_and_marks_incomplete(built, tmp_path):
    budget = b.Budget(cap_usd=0.00035, cap_model_usd=1.0)
    _, state = _run(built, tmp_path, _ok_handler(cost=0.0001), [JEV], budget, n=6)
    rows = b.read_records(b.recorded_path(tmp_path, JEV))
    assert state["stopped"] == "usd" and state["incomplete"][JEV] == "usd"
    assert len(rows) == 3 and budget.spent <= 0.00035 + 1e-12


def test_call_cap_and_model_cap(built, tmp_path):
    budget = b.Budget(cap_calls=2)
    _, state = _run(built, tmp_path / "a", _ok_handler(), [JEV], budget, n=5)
    assert state["stopped"] == "calls" and budget.calls == 2
    budget = b.Budget(cap_model_usd=0.00025)
    other = "microsoft/microsoft-decision-1"
    _, state = _run(
        built, tmp_path / "b", _ok_handler(cost=0.0001), [JEV, other], budget, n=5, reps=1
    )
    assert state["incomplete"][JEV] == "usd"
    assert state["stopped"] is None  # the other model is not starved by the first one's cap
    assert len(b.read_records(b.recorded_path(tmp_path / "b", other))) > 0


def test_resume_does_not_call_again(built, tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return _ok_handler()(request)

    _run(built, tmp_path, handler, [JEV], n=3)
    first = len(calls)
    assert first == 6
    budget = b.Budget()
    _run(built, tmp_path, handler, [JEV], budget, n=3)
    assert len(calls) == first
    assert budget.calls == first  # costs of the recorded cases still count


def test_run_refuses_foreign_item(built, tmp_path):
    item = built.items[0]
    bad = b.Item(item.id, item.task, item.lang, item.kind, item.label, item.query, "étranger")
    client = b.DecisionClient(FAKE_KEY, transport=httpx.MockTransport(_ok_handler()))
    with pytest.raises(b.ProvenanceError):
        b.run_online([bad], [JEV], tmp_path, client, b.Budget())


# ---------- choice, memory, command line ----------


def _cand(cid, kind, task, reject=None, h7=None, err=0.0, lat=100, ram=2000):
    tuned = {"reject_share": reject} if task == "filter" else {"h7": h7, "recall": 0.9}
    return {
        "id": cid,
        "kind": kind,
        "label": cid,
        "status": "measured",
        "counters": {"error_rate": err, "latency": {"median_ms": lat, "max_ms": lat}},
        "local": {"rss_with_slm_mb": ram},
        "tasks": {task: {"tuned": tuned}},
    }


def test_choose_is_local_by_default_and_reranker_is_reference():
    agg = {
        "stopped": None,
        "candidates": {
            "reranker_livre": _cand("reranker_livre", "local", "filter", reject=0.7),
            "deberta_xsmall": _cand("deberta_xsmall", "local", "filter", reject=0.65),
            JEV: _cand(JEV, "online", "filter", reject=0.9),
        },
    }
    ch = b.choose(agg)
    assert ch["filter"]["default"] == "reranker_livre"
    assert ch["filter"]["fallback"] == "deberta_xsmall"
    assert ch["filter"]["cloud"] == JEV
    agg["candidates"]["deberta_xsmall"] = _cand("deberta_xsmall", "local", "filter", reject=0.8)
    assert b.choose(agg)["filter"]["default"] == "deberta_xsmall"


def test_grounding_needs_h7_and_error_rate():
    agg = {
        "stopped": None,
        "candidates": {
            "slm_juge": _cand("slm_juge", "local", "grounding", h7=0.2),
            "nli_mdeberta": _cand("nli_mdeberta", "local", "grounding", h7=0.1, err=0.06),
        },
    }
    assert b.choose(agg)["grounding"]["default"] is None  # none passes
    agg["candidates"]["slm_juge"] = _cand("slm_juge", "local", "grounding", h7=0.1)
    assert b.choose(agg)["grounding"]["default"] == "slm_juge"
    agg["stopped"] = "usd"
    assert b.choose(agg)["state"] == "incomplete"


def test_memory_verdict_slices():
    assert b.memory_verdict(3000) == "confirmé"
    assert "PC cible" in b.memory_verdict(3500)
    assert b.memory_verdict(4200) == "infirmé"
    assert b.memory_verdict(None) == "pas encore mesuré"
    assert "pas encore mesuré" in b.memlog_block(None)
    mem = {
        "peak_working_set_mb": 3500,
        "peak_private_mb": 3400,
        "n_ctx": 16384,
        "prompt_tokens_full": 16000,
        "ram_total_mb": 32000,
    }
    assert "3500" in b.memlog_block(mem) and "16 Go" in b.memlog_block(mem)


def test_real_commands_need_confirmation():
    for cmd in ("online", "local", "memory"):
        with pytest.raises(SystemExit) as err:
            b.main([cmd])
        assert "--confirm-idle" in str(err.value)


def test_online_without_key_refuses_before_any_call(monkeypatch):
    monkeypatch.delenv(b.KEY_ENV, raising=False)
    monkeypatch.setattr(b, "read_registry_key", lambda name=b.KEY_ENV: None)
    with pytest.raises(SystemExit) as err:
        b.main(["online", "--confirm-idle"])
    assert b.KEY_ENV in str(err.value)
