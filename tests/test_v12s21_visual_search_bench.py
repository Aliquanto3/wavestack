"""V1.2 story 21: the visual search bench, pure logic and replay. No network, no model, no
Pillow: a fake embedder stands in for the model (the only external boundary)."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[1] / "tools" / "bench" / "v12s21_visual_search_bench.py"


def _load():
    spec = importlib.util.spec_from_file_location("v12s21_bench_under_test", PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


b = _load()
np = pytest.importorskip("numpy")

WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]


def _doc_text(word: str, n: int = 90) -> str:
    return "\n".join(f"Ligne {i} sur le sujet {word} et rien d'autre." for i in range(n))


class FakeEmbedder:
    """One-hot keyword vectors: a page about `alpha` matches the query `alpha`."""

    def __init__(self, fail_query: bool = False):
        self.loaded = False
        self.fail_query = fail_query

    def load(self) -> None:
        self.loaded = True

    def _vec(self, text: str):
        rows = [np.eye(len(WORDS))[i] for i, w in enumerate(WORDS) if w in text.lower()]
        return b.l2_normalize(rows or [np.zeros(len(WORDS))])

    def embed_page(self, image_path: str):
        return self._vec(Path(image_path).read_text("utf-8"))

    def embed_query(self, text: str):
        if self.fail_query:
            raise b.AdapterError("le graphe refuse la requête")
        return self._vec(text)


def _selection(tmp_path: Path):
    pages = []
    for w in WORDS:
        pages.extend(b.paginate(w, b.wrap_lines(_doc_text(w, 20)), per_page=20, prefix="fr."))
    q = [
        SimpleNamespace(
            id=f"q_{w}",
            type="factual",
            question_text=f"Que dit {w} ?",
            expected_passages=[SimpleNamespace(doc_id=w, anchor_text=f"Ligne 3 sur le sujet {w}")],
        )
        for w in WORDS
    ]
    sel = b.select(pages, q, "fr", n_pages=len(pages), n_queries=len(WORDS))
    images = {}
    for p in sel.pages:  # the "image" of the fake model is the page text
        f = tmp_path / f"{p.id}.txt"
        f.write_text(p.text, "utf-8")
        images[p.id] = str(f)
    return sel, images


class Clock:
    def __init__(self, step: float):
        self.t, self.step = 0.0, step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


# ---------- pages and selection ----------


def test_wrap_and_paginate():
    lines = b.wrap_lines("# Titre\n\n" + "mot " * 100)
    assert lines[0] == "Titre"
    assert all(len(line) <= b.CHARS_PER_LINE for line in lines)
    pages = b.paginate("doc", lines * 10, per_page=20, prefix="fr.")
    assert [p.id for p in pages][:2] == ["fr.doc.p1", "fr.doc.p2"]
    assert all(len(p.lines) <= 20 for p in pages)


def test_select_is_deterministic_and_keeps_gold_pages(tmp_path):
    sel, _ = _selection(tmp_path)
    again, _ = _selection(tmp_path)
    assert [q["gold"] for q in sel.queries] == [q["gold"] for q in again.queries]
    ids = {p.id for p in sel.pages}
    assert all(q["gold"] in ids for q in sel.queries)
    assert len(sel.queries) == len(WORDS)


def test_select_skips_an_anchor_that_is_on_no_single_page():
    pages = b.paginate("d", ["x", "y", "end1", "start2", "z", "w"], per_page=3, prefix="fr.")
    q = SimpleNamespace(
        id="q1",
        type="factual",
        question_text="?",
        expected_passages=[SimpleNamespace(doc_id="d", anchor_text="end1 start2")],  # spans pages
    )
    sel = b.select(pages, [q], "fr", n_pages=2, n_queries=1)
    assert sel.skipped == ["q1"] and sel.queries == []


def test_select_refuses_fewer_pages_than_gold_pages(tmp_path):
    sel, _ = _selection(tmp_path)
    pages = sel.pages
    q = [
        SimpleNamespace(
            id=f"q{i}",
            type="factual",
            question_text="?",
            expected_passages=[SimpleNamespace(doc_id=p.doc_id, anchor_text="Ligne 3")],
        )
        for i, p in enumerate(pages[:3])
    ]
    with pytest.raises(ValueError, match="raise --pages"):
        b.select(pages, q, "fr", n_pages=1, n_queries=3)


def test_real_corpus_gives_the_default_sample():
    pages = b.build_pages("fr")
    from wavestack.rag.corpus import load_rag_questions

    sel = b.select(pages, load_rag_questions("fr"), "fr")
    assert len(sel.pages) == b.N_PAGES and len(sel.queries) == b.N_QUERIES
    assert {q["gold"] for q in sel.queries} <= {p.id for p in sel.pages}
    assert sel.corpus_pages == len(pages) > b.N_PAGES
    assert {p.doc_id for p in sel.pages}  # fictitious Exemplia documents only


# ---------- scores ----------


def test_maxsim_and_rank_with_ties_against_the_model():
    q = np.array([[1.0, 0.0], [0.0, 1.0]])
    assert b.maxsim(q, np.array([[1.0, 0.0], [0.0, 1.0]])) == pytest.approx(2.0)
    assert b.maxsim(q, np.array([[1.0, 0.0]])) == pytest.approx(1.0)
    assert b.rank_of([0.5, 0.5, 0.1], 1) == 2  # tie: the gold counts last


def test_retrieval_metrics():
    scores = [[0.9, 0.1, 0.2], [0.1, 0.2, 0.9]]
    m = b.retrieval_metrics(scores, ["p0", "p1", "p2"], ["p0", "p1"])
    assert m["recall_1"] == 0.5 and m["recall_3"] == 1.0
    assert m["mrr"] == pytest.approx(0.75)
    assert b.retrieval_metrics([], [], [])["recall_3"] is None


def test_index_size_and_latency_stats():
    assert b.index_size_mb(1030, 30) == pytest.approx(1030 * 30 * 128 * 2 / 2**20, abs=0.01)
    assert b.latency_stats([1, 2, 9]) == {"n": 3, "median": 2, "max": 9}
    assert b.latency_stats([])["median"] is None


# ---------- measure with a fake model ----------


def test_measure_candidate_finds_every_page(tmp_path):
    sel, images = _selection(tmp_path)
    phases = []
    raw = b.measure_candidate(
        FakeEmbedder(),
        sel,
        images,
        clock=Clock(0.5),
        probe=lambda ph: phases.append(ph) or {"ph": ph},
    )
    assert raw["status"] == "measured" and not raw["partial"]
    assert phases == ["load", "index", "search"]
    m = b.candidate_metrics({**raw, "peak_mb": 900, "torch": False, "deps": {"total_mb": 80}})
    assert m["retrieval"]["recall_1"] == 1.0 and m["n_pages"] == len(sel.pages)
    assert m["index_s"]["median"] == pytest.approx(0.5, abs=0.1)


def test_index_cap_marks_the_result_partial(tmp_path):
    sel, images = _selection(tmp_path)
    raw = b.measure_candidate(FakeEmbedder(), sel, images, clock=Clock(10), index_cap_s=25)
    assert raw["partial"] and len(raw["page_ids"]) < len(sel.pages)
    assert all(g in raw["page_ids"] for g in raw["gold"])  # unindexed gold pages are not asked


def test_query_error_is_recorded_not_hidden(tmp_path):
    sel, images = _selection(tmp_path)
    raw = b.measure_candidate(FakeEmbedder(fail_query=True), sel, images, clock=Clock(0.1))
    m = b.candidate_metrics({**raw, "peak_mb": 500, "torch": False})
    assert "refuse la requête" in m["query_error"]
    verdict = b.verdict(m)
    assert verdict["label"] == "ne tient pas"
    assert any("requêtes non exécutables" in r for r in verdict["reasons"])


# ---------- verdict ----------


def _metrics(**over) -> dict:
    m = {
        "status": "measured",
        "error": None,
        "peak_mb": 2000,
        "index_s": {"median": 5.0, "max": 8.0},
        "query_ms": {"median": 900.0, "max": 1500.0},
        "retrieval": {"n_queries": 8, "recall_3": 0.9},
        "query_error": None,
        "torch": False,
    }
    m.update(over)
    return m


def test_verdict_thresholds():
    assert b.verdict(_metrics())["label"] == "tient"
    assert b.verdict(_metrics(peak_mb=3500))["label"] == "tient de justesse"
    over = b.verdict(_metrics(peak_mb=7000))
    assert over["label"] == "ne tient pas" and "mémoire" in over["reasons"][0]
    assert b.verdict(_metrics(index_s={"median": 40.0, "max": 60.0}))["label"] == "ne tient pas"
    assert (
        b.verdict(_metrics(query_ms={"median": 9000.0, "max": 9000.0}))["label"] == "ne tient pas"
    )
    assert (
        b.verdict(_metrics(retrieval={"n_queries": 8, "recall_3": 0.4}))["label"] == "ne tient pas"
    )
    few = b.verdict(_metrics(retrieval={"n_queries": 2, "recall_3": 1.0}))
    assert "non jugeable" in few["reasons"][0]
    assert b.verdict(_metrics(torch=True))["label"] == "ne tient pas"
    assert b.verdict({"status": "failed", "error": "boom"})["label"] == "non exécutable"


# ---------- results, replay, report ----------


def _record(results: Path, tmp_path: Path) -> None:
    sel, images = _selection(tmp_path)
    raw = b.measure_candidate(FakeEmbedder(), sel, images, clock=Clock(0.5))
    raw.update(peak_mb=1234, torch=False, deps={"total_mb": 77}, attempts=[], memory={})
    b.write_json(results / "colsmol_256m_onnx.json", raw)
    b.write_json(
        results / "colpali_v13_fp16.json",
        {"status": "failed", "error": "arrêté au plafond de sécurité (16400 Mo)", "peak_mb": 16400},
    )
    b.write_json(
        results / "run.json",
        {
            "measured_on": "2026-10-26",
            "lang": "fr",
            "corpus_pages": 30,
            "n_pages": len(sel.pages),
            "n_queries": len(sel.queries),
            "font": "consola.ttf",
            "commit": "abc",
            "machine": {"platform": "Windows", "cpu_count": 8, "ram_total_mb": 32000},
        },
    )


def test_replay_gives_the_same_report_and_conclusion(tmp_path):
    results = tmp_path / "res"
    _record(results, tmp_path)
    first = b.render_report(b.aggregate(results))
    assert first == b.render_report(b.aggregate(results))
    assert "**Conclusion : tient.**" in first
    assert "mesuré : tient" in first and "non exécutable" in first
    assert "1234" in first and "arrêté au plafond" in first
    assert "Pas encore mesuré" not in first.split("## 2.")[0]


def test_an_all_failed_run_concludes_no(tmp_path):
    results = tmp_path / "res"
    b.write_json(results / "run.json", {"corpus_pages": 30})
    b.write_json(results / "colpali_v13_fp16.json", {"status": "failed", "error": "mémoire"})
    agg = b.aggregate(results)
    assert b.conclusion(agg)[0] == "ne tient pas"
    assert "deferred-work.md" in b.render_report(agg)


def test_template_report_is_the_committed_one():
    text = b.render_report(b.aggregate(None))
    assert "Pas encore mesuré" in text and "pas encore mesuré" in text
    committed = b.REPORT_PATH.read_text("utf-8")
    assert committed == text, "regenerate with `report --write` (no results recorded yet)"


# ---------- candidates, adapters' pure parts ----------


def test_candidates_are_pinned_and_torch_free():
    for c in b.CANDIDATES.values():
        assert re.fullmatch(r"[0-9a-f]{40}", c.revision)
        assert c.download_mb > 0 and c.license
        assert not {"torch", "transformers", "colpali-engine"} & set(c.roots)
    assert b.EXCLUDED and all(e["reason"] and e["repo"] for e in b.EXCLUDED.values())


def test_idefics3_prompt_and_tiles():
    assert b.tile_grid(b.PAGE_W, b.PAGE_H) == (4, 3, 1536, 2048)
    text = b.colsmol_page_text(4, 3)
    assert text.count(b.IMAGE_TOKEN) == 13 * b.TILE_TOKENS
    assert "<row_4_col_3>" in text and "<global-img>" in text
    assert b.colsmol_query_text("q").startswith("Query: q<end_of_utterance>")


def test_numpy_dtype_name():
    assert b.numpy_dtype_name("tensor(int64)") == "int64"
    assert b.numpy_dtype_name("tensor(float)") == "float32"
    assert b.numpy_dtype_name("tensor(bool)") == "bool"
    with pytest.raises(b.AdapterError):
        b.numpy_dtype_name("seq(tensor(float))")


def test_missing_files_lists_what_download_must_fetch(tmp_path):
    c = b.CANDIDATES["colsmol_256m_onnx"]
    assert set(b.missing_files(tmp_path, c)) == set(c.files)
    root = b.snapshot_dir(tmp_path, c)
    for f in c.files:
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        (root / f).write_text("x")
    assert b.missing_files(tmp_path, c) == []


def test_render_page_draws_an_a4_image(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    page = b.Page("fr.d.p1", "d", 1, ["Bonjour", "monde"])
    b.render_page(page, tmp_path / "p.png")
    with Image.open(tmp_path / "p.png") as img:
        assert img.size == (b.PAGE_W, b.PAGE_H)


# ---------- commands ----------


def test_measure_refuses_without_confirm_idle():
    with pytest.raises(SystemExit, match="confirm-idle"):
        b.main(["measure"])


def test_unknown_candidate_is_refused():
    with pytest.raises(SystemExit, match="inconnu"):
        b.selected(["nope"])


def test_list_and_report_commands(tmp_path, capsys):
    assert b.main(["list"]) == 0
    assert "colpali_v13_fp16" in capsys.readouterr().out
    results = tmp_path / "res"
    _record(results, tmp_path)
    assert b.main(["report", "--results-dir", str(results)]) == 0
    assert "Rapport de la recherche visuelle" in capsys.readouterr().out
    json.loads((results / "run.json").read_text("utf-8"))
