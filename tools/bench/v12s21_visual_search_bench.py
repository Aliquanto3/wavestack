"""V1.2 story 21 benchmark: does a visual document retriever (ColPali, ColQwen, ColSmol) fit the
CPU budget of WaveStack (CAP-19)? Pages of the fictitious Exemplia corpus are drawn as images
(no OCR), indexed page by page, then searched with the prepared questions (MaxSim).

Spec: `_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/stories/
21-recherche-visuelle-sans-ocr.md`. Modelled on `v12s2_system_one_bench.py` and `v2s6`, whose
helpers it reuses (network guard, peak working set, RAM watchdog). It adds no dependency to the
project and no torch: the measurement packages come from `uv run --with fastembed==0.9.1`
(onnxruntime, tokenizers, numpy, pillow). Only the standard library is imported at module level,
so `tests/test_v12s21_visual_search_bench.py` tests the pure logic with a fake model.

Commands (from the repository root; `download` and `measure` are never run in CI):

    uv run python tools/bench/v12s21_visual_search_bench.py list
    uv run --with fastembed==0.9.1 python tools/bench/v12s21_visual_search_bench.py download
    uv run --with fastembed==0.9.1 python tools/bench/v12s21_visual_search_bench.py measure \\
        --confirm-idle
    uv run python tools/bench/v12s21_visual_search_bench.py report [--results-dir D] [--write]

`download` is the only command that touches the network (huggingface.co and *.hf.co, revisions
pinned); `measure` runs each candidate in a child process under the project network guard with
no allowed host. `report` replays the recorded results without any model.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import statistics
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPT = "tools/bench/v12s21_visual_search_bench.py"
SPEC_DIR = ROOT / "_bmad-output" / "specs" / "spec-wavestack-v1-2-atelier-recherche-documentaire"
REPORT_PATH = SPEC_DIR / "rapport-recherche-visuelle.md"
RESULTS_DIR = HERE / "results"
DEFAULT_MODELS_DIR = Path.home() / ".cache" / "wavestack-bench"
DEFAULT_WORK_DIR = Path.home() / ".cache" / "wavestack-bench" / "v12s21-pages"
FASTEMBED_PIN = "fastembed==0.9.1"
DOWNLOAD_HOSTS = ["huggingface.co", "*.hf.co"]

# --------------------------------------------------------------------------------------
# Constants: page layout, sample, thresholds (spec, "Protocole" and "Seuils").
# --------------------------------------------------------------------------------------

SEED = 12021
LANG_DEFAULT = "fr"
N_PAGES = 12
N_QUERIES = 8
INDEX_CAP_MIN = 12  # per candidate: indexing stops there, the result is marked partial
QUERY_CAP_MIN = 5
CHILD_TIMEOUT_MIN = 40
RAM_CEILING_MB = 16384  # safety stop of the child on the 32 GB dev PC (not the verdict)

PAGE_W, PAGE_H, MARGIN = 1240, 1754, 90  # A4 at 150 dpi
FONT_SIZE, LINE_H = 26, 34
CHARS_PER_LINE, LINES_PER_PAGE = 70, 44

RAM_BUDGET_MB = 4096  # SPEC.md: 4 GB for the whole process
RAM_COMFORT_MB = 3072  # above it: "just fits"
INDEX_MEDIAN_MAX_S = 15.0  # per page; ~30 pages of Exemplia then index in under 8 minutes
INDEX_MAX_S = 45.0
QUERY_MEDIAN_MAX_MS = 3000
RECALL3_MIN = 0.75
MIN_QUERIES = 6
VECTOR_DIM = 128
VECTOR_BYTES = 2  # fp16 storage of the multivectors

QUERY_TYPES = ("factual", "temporal", "cross_lingual")

# --------------------------------------------------------------------------------------
# Candidates (cards read over the network on 2026-10-25, revisions from the HF API).
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    id: str
    label: str
    repo: str
    revision: str
    files: tuple[str, ...]
    download_mb: int
    license: str
    params: str
    engine: str  # "fastembed" | "onnx_idefics3"
    roots: tuple[str, ...]  # distributions whose closure is the install
    vectors_note: str
    languages: str
    source: str


CANDIDATES: dict[str, Candidate] = {
    "colpali_v13_fp16": Candidate(
        id="colpali_v13_fp16",
        label="ColPali v1.3, ONNX fp16 (Qdrant, fastembed)",
        repo="Qdrant/colpali-v1.3-fp16",
        revision="e69c27e8e2e50f62a2f76d8c6f693d21d53804a7",
        files=(
            "model.onnx",
            "model.onnx_data",
            "config.json",
            "preprocessor_config.json",
            "special_tokens_map.json",
            "tokenizer.json",
            "tokenizer_config.json",
        ),
        download_mb=5890,
        license="Gemma Terms of Use (modèle dérivé de Gemma ; adaptateur ColPali MIT)",
        params="~2,9 Md (PaliGemma 3B)",
        engine="fastembed",
        roots=("fastembed",),
        vectors_note="1 030 vecteurs de 128 par page (image 448x448) ; requête : 50 jetons au plus",
        languages="anglais (entraînement 100 % anglais, généralisation non anglaise non garantie)",
        source="https://huggingface.co/Qdrant/colpali-v1.3-fp16 (carte, fastembed 0.9.1)",
    ),
    "colsmol_256m_onnx": Candidate(
        id="colsmol_256m_onnx",
        label="ColSmol-256M, ONNX fp32 (onnx-community)",
        repo="onnx-community/colSmol-256M-ONNX",
        revision="12022f0630b795c229e85cd4af33e288fef124f0",
        files=(
            "onnx/model.onnx",
            "added_tokens.json",
            "merges.txt",
            "preprocessor_config.json",
            "special_tokens_map.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.json",
        ),
        download_mb=960,
        license="MIT (carte onnx-community ; modèle d'origine vidore/colSmol-256M, MIT)",
        params="~256 M (SmolVLM-256M)",
        engine="onnx_idefics3",
        roots=("onnxruntime", "tokenizers", "numpy", "pillow"),
        vectors_note="832 vecteurs image + 2 (13 tuiles de 64) de 128 par page",
        languages="anglais (entraînement 100 % anglais, généralisation non anglaise non garantie)",
        source="https://huggingface.co/onnx-community/colSmol-256M-ONNX (carte : licence seule)",
    ),
}

# Not measured: the reason is written, never a figure made up (spec, "Candidats").
EXCLUDED: dict[str, dict[str, str]] = {
    "colqwen2.5-v0.2": {
        "label": "ColQwen2.5 v0.2 (vidore, 3B)",
        "repo": "vidore/colqwen2.5-v0.2 @ dcbe8d9cede518bce830488364ba0e40c873645b",
        "reason": (
            "adaptateur PEFT (240 Mo) sur Qwen2.5-VL-3B : `colpali-engine` exige torch ; aucun "
            "port ONNX ou GGUF trouvé sur le Hub (recherche du 2026-10-25) ; licence MIT"
        ),
    },
    "colqwen2_gguf": {
        "label": "ColQwen2 v1.0, GGUF f16 (odellus)",
        "repo": "odellus/colqwen2-v1.0-gguf @ 8b4ff3b7acf948c88bb4226b6e788cdab49afbf4",
        "reason": (
            "f16 de 3 094 Mo (LLM) + 1 332 Mo (mmproj) = 4,4 Go, au-delà du budget de 4 Go à lui "
            "seul ; exige le fork crow-cli/llama.cpp (branche crow-colqwen2-mv, sorties "
            "multivecteurs), qui n'est ni llama-cpp-python ni le llama-server épinglé b11378 ; "
            "licence Apache-2.0"
        ),
    },
    "ops_colqwen3_4b_gguf": {
        "label": "Ops-Colqwen3-4B, GGUF Q4_K_M (takenoko-gohan)",
        "repo": "takenoko-gohan/Ops-Colqwen3-4B-GGUF @ 463a43c16232d445546eb72880ed6e3baf3e692f",
        "reason": (
            "3 311 Mo de poids seuls (4B), exécutable seulement par l'exemple Rust Candle "
            "(`cargo run`, compilation) ; hors des moteurs du projet ; licence Apache-2.0"
        ),
    },
    "colsmol_500m": {
        "label": "ColSmol-500M (vidore)",
        "repo": "vidore/colSmol-500M @ 0aaa9726104ce485884c7b8faa8a58a72d5fdbe7",
        "reason": "adaptateur PEFT (70 Mo) : torch et colpali-engine ; aucun port ONNX trouvé",
    },
    "colpali_torch": {
        "label": "ColPali v1.3 (vidore, safetensors)",
        "repo": "vidore/colpali-v1.3 @ b5c6dd62125326e6f0b540c1f7b36e901cdc0a11",
        "reason": "adaptateur PEFT : torch ; le port ONNX de Qdrant ci-dessus est la voie sans torch",  # noqa: E501
    },
    "colnomic_3b": {
        "label": "ColNomic Embed Multimodal 3B (nomic-ai)",
        "repo": "nomic-ai/colnomic-embed-multimodal-3b",
        "reason": "adaptateur PEFT sur Qwen2.5-VL-3B : torch ; seuls des ports MLX (Apple) trouvés",
    },
    "colsmol_256m_dynamic": {
        "label": "ColSmol-256M, ONNX à nombre de tuiles dynamique (guyettinger)",
        "repo": "guyettinger/colSmol-256M-dynamic-onnx @ 93956db0e440eebd497bc776e7bf34a06830b0c6",
        "reason": (
            "réserve, non mesuré : sortie de `n*64+2` vecteurs, donc une disposition des "
            "`input_ids` différente de l'invite Idefics3 complète, non vérifiable sans télécharger ; "  # noqa: E501
            "l'auteur annonce ~5,0 s par image à 7 tuiles en fp32 sur CPU (publié, non vérifié) ; MIT"  # noqa: E501
        ),
    },
}

# --------------------------------------------------------------------------------------
# Pages: pagination of the corpus, selection of pages and questions.
# --------------------------------------------------------------------------------------


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


@dataclass
class Page:
    id: str
    doc_id: str
    number: int
    lines: list[str]

    @property
    def text(self) -> str:
        return " ".join(line for line in self.lines if line.strip())

    @property
    def norm_text(self) -> str:
        return norm(self.text)


def wrap_lines(text: str, width: int = CHARS_PER_LINE) -> list[str]:
    """Plain text to display lines: headings lose their `#`, paragraphs wrap at `width`."""
    import textwrap

    lines: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"^#+\s*", "", raw.rstrip())
        if not line.strip():
            lines.append("")
            continue
        lines.extend(textwrap.wrap(line, width=width, break_long_words=True) or [""])
    while lines and not lines[0]:
        lines.pop(0)
    return lines


def paginate(
    doc_id: str, lines: Sequence[str], per_page: int = LINES_PER_PAGE, prefix: str = ""
) -> list[Page]:
    pages: list[Page] = []
    for start in range(0, len(lines), per_page):
        chunk = list(lines[start : start + per_page])
        if not any(line.strip() for line in chunk):
            continue
        number = len(pages) + 1
        pages.append(Page(f"{prefix}{doc_id}.p{number}", doc_id, number, chunk))
    return pages


def build_pages(lang: str = LANG_DEFAULT) -> list[Page]:  # needs the project modules
    from wavestack.rag.corpus import load_rag_content, read_documents

    pages: list[Page] = []
    for doc in read_documents(load_rag_content(lang), lang):
        full = f"{doc.title_text}\n\n{doc.text}"
        pages.extend(paginate(doc.doc_id, wrap_lines(full), prefix=f"{lang}."))
    return pages


@dataclass
class Selection:
    lang: str
    pages: list[Page]
    queries: list[dict]  # {id, text, gold} (gold: page id)
    skipped: list[str] = field(default_factory=list)
    corpus_pages: int = 0


def select(
    pages: list[Page],
    questions: Sequence,
    lang: str = LANG_DEFAULT,
    n_pages: int = N_PAGES,
    n_queries: int = N_QUERIES,
    seed: int = SEED,
) -> Selection:
    """Questions (factual, temporal, cross-lingual) with one expected passage lying wholly on
    one page (otherwise skipped and listed), their gold pages, then seeded filler pages up to
    `n_pages`."""
    eligible: list[tuple[object, int]] = []
    skipped: list[str] = []
    for q in sorted(questions, key=lambda q: q.id):
        if q.type not in QUERY_TYPES or len(q.expected_passages) != 1:
            continue
        passage = q.expected_passages[0]
        anchor = norm(passage.anchor_text)
        found = [
            i
            for i, pg in enumerate(pages)
            if pg.doc_id == passage.doc_id and anchor in pg.norm_text
        ]
        if len(found) == 1:
            eligible.append((q, found[0]))
        else:
            skipped.append(q.id)
    rng = random.Random(f"{seed}:{lang}")
    rng.shuffle(eligible)
    chosen = eligible[:n_queries]  # several questions may share a gold page
    used = {i for _, i in chosen}
    if n_pages < len(used):
        raise ValueError(f"{n_pages} pages for {len(used)} gold pages: raise --pages")
    fillers = [i for i in range(len(pages)) if i not in used]
    rng.shuffle(fillers)
    indexes = sorted(used | set(fillers[: n_pages - len(used)]))
    return Selection(
        lang=lang,
        pages=[pages[i] for i in indexes],
        queries=[{"id": q.id, "text": q.question_text, "gold": pages[i].id} for q, i in chosen],
        skipped=skipped,
        corpus_pages=len(pages),
    )


def font_candidates() -> list[str]:
    return [
        "C:/Windows/Fonts/consola.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ]


def render_page(page: Page, path: Path) -> str:  # pragma: no cover - needs pillow
    """Draw a page as a white A4 image at 150 dpi; returns the font used."""
    from PIL import Image, ImageDraw, ImageFont

    font, name = None, "PIL default"
    for candidate in font_candidates():
        if Path(candidate).is_file():
            font, name = ImageFont.truetype(candidate, FONT_SIZE), Path(candidate).name
            break
    if font is None:
        font = ImageFont.load_default(size=FONT_SIZE)
    image = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    draw = ImageDraw.Draw(image)
    for n, line in enumerate(page.lines):
        draw.text((MARGIN, MARGIN + n * LINE_H), line, fill="black", font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return name


# --------------------------------------------------------------------------------------
# Scores and metrics (pure).
# --------------------------------------------------------------------------------------


def maxsim(query, page) -> float:
    """ColBERT late interaction: sum over query vectors of the best dot product on the page."""
    import numpy as np

    sims = np.asarray(query, dtype=np.float32) @ np.asarray(page, dtype=np.float32).T
    return float(sims.max(axis=1).sum())


def l2_normalize(vectors):
    import numpy as np

    v = np.asarray(vectors, dtype=np.float32)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


def rank_of(scores: Sequence[float], gold_index: int) -> int:
    """1-based rank of the gold page; ties count against the model (the gold is last)."""
    better = sum(1 for i, s in enumerate(scores) if i != gold_index and s >= scores[gold_index])
    return better + 1


def retrieval_metrics(
    scores: Sequence[Sequence[float]], page_ids: Sequence[str], gold: Sequence[str]
) -> dict:
    ranks = [rank_of(row, page_ids.index(g)) for row, g in zip(scores, gold, strict=True)]
    n = len(ranks)
    if not n:
        return {"n_queries": 0, "recall_1": None, "recall_3": None, "mrr": None}
    return {
        "n_queries": n,
        "recall_1": round(sum(r <= 1 for r in ranks) / n, 4),
        "recall_3": round(sum(r <= 3 for r in ranks) / n, 4),
        "mrr": round(sum(1 / r for r in ranks) / n, 4),
        "ranks": ranks,
    }


def latency_stats(values: Sequence[float]) -> dict:
    if not values:
        return {"n": 0, "median": None, "max": None}
    return {
        "n": len(values),
        "median": round(statistics.median(values), 1),
        "max": round(max(values), 1),
    }


def index_size_mb(vectors_per_page: float, pages: int) -> float:
    return round(vectors_per_page * pages * VECTOR_DIM * VECTOR_BYTES / (1 << 20), 2)


class AdapterError(RuntimeError):
    """The model cannot run as the bench feeds it (inputs, shapes): recorded, not hidden."""


def measure_candidate(
    embedder,
    selection: Selection,
    images: dict[str, str],
    clock: Callable[[], float] = time.perf_counter,
    index_cap_s: float = INDEX_CAP_MIN * 60,
    query_cap_s: float = QUERY_CAP_MIN * 60,
    probe: Callable[[str], dict] | None = None,
) -> dict:
    """Load, index every page one by one, search every query. `embedder` has `load()`,
    `embed_page(image_path)` and `embed_query(text)`, vectors in a (n, 128) array.
    `probe(phase)` returns a memory snapshot after `load`, `index` and `search`."""
    snapshots: dict[str, dict] = {}

    def snap(phase: str) -> None:
        if probe is not None:
            snapshots[phase] = probe(phase)

    t0 = clock()
    embedder.load()
    load_s = clock() - t0
    snap("load")
    vectors: dict[str, object] = {}
    page_rows: list[dict] = []
    start = clock()
    partial = False
    for page in selection.pages:
        if clock() - start > index_cap_s:
            partial = True
            break
        t = clock()
        vec = embedder.embed_page(images[page.id])
        page_rows.append(
            {"id": page.id, "ms": round((clock() - t) * 1000, 1), "vectors": int(len(vec))}
        )
        vectors[page.id] = vec
    snap("index")
    indexed = [p.id for p in selection.pages if p.id in vectors]
    query_rows: list[dict] = []
    scores: list[list[float]] = []
    gold: list[str] = []
    start = clock()
    query_error = None
    for q in selection.queries:
        if q["gold"] not in vectors:
            continue  # its gold page was not indexed (cap reached): not counted
        if clock() - start > query_cap_s:
            partial = True
            break
        try:
            t = clock()
            qv = embedder.embed_query(q["text"])
            embed_ms = (clock() - t) * 1000
        except AdapterError as exc:
            query_error = str(exc)[:300]
            break
        t = clock()
        row = [maxsim(qv, vectors[pid]) for pid in indexed]
        score_ms = (clock() - t) * 1000
        scores.append([round(s, 4) for s in row])
        gold.append(q["gold"])
        query_rows.append(
            {
                "id": q["id"],
                "embed_ms": round(embed_ms, 1),
                "score_ms": round(score_ms, 2),
                "vectors": int(len(qv)),
            }
        )
    snap("search")
    return {
        "status": "measured",
        "load_s": round(load_s, 2),
        "pages": page_rows,
        "queries": query_rows,
        "page_ids": indexed,
        "gold": gold,
        "scores": scores,
        "partial": partial,
        "query_error": query_error,
        "memory_phases": snapshots,
    }


# --------------------------------------------------------------------------------------
# Adapters (real models; excluded from coverage, never run in CI).
# --------------------------------------------------------------------------------------


def snapshot_dir(models_dir: Path, c: Candidate) -> Path:
    return (
        Path(models_dir)
        / "hf-v12s21"
        / f"models--{c.repo.replace('/', '--')}"
        / "snapshots"
        / c.revision
    )


def missing_files(models_dir: Path, c: Candidate) -> list[str]:
    root = snapshot_dir(models_dir, c)
    return [f for f in c.files if not (root / f).is_file()]


def numpy_dtype_name(ort_type: str) -> str:
    """`tensor(int64)` -> `int64`, `tensor(bool)` -> `bool`, `tensor(float)` -> `float32`."""
    inner = re.fullmatch(r"tensor\((\w+)\)", ort_type)
    if not inner:
        raise AdapterError(f"type d'entrée ONNX inconnu : {ort_type}")
    return {"float": "float32", "double": "float64"}.get(inner.group(1), inner.group(1))


IMAGE_TOKEN = "<image>"
TILE = 512
TILE_TOKENS = 64
PAGE_PREFIX = "<|im_start|>user\n"
PAGE_SUFFIX = "Describe the image.<end_of_utterance>"
QUERY_PREFIX = "Query: "
QUERY_AUGMENTATION = "<end_of_utterance>"


def idefics3_image_prompt(rows: int, cols: int, seq_len: int = TILE_TOKENS) -> str:
    """Idefics3 prompt of a split image: one `<row_r_col_c>` block per tile, then the global."""
    out = ""
    for r in range(1, rows + 1):
        for c in range(1, cols + 1):
            out += f"<fake_token_around_image><row_{r}_col_{c}>" + IMAGE_TOKEN * seq_len
        out += "\n"
    out += "\n<fake_token_around_image><global-img>" + IMAGE_TOKEN * seq_len
    return out + "<fake_token_around_image>"


def colsmol_page_text(rows: int, cols: int) -> str:
    return PAGE_PREFIX + idefics3_image_prompt(rows, cols) + PAGE_SUFFIX


def colsmol_query_text(query: str) -> str:
    return QUERY_PREFIX + query + QUERY_AUGMENTATION * 10 + "\n"


def tile_grid(width: int, height: int, longest: int = 4 * TILE) -> tuple[int, int, int, int]:
    """Idefics3 split: longest edge scaled to `longest`, sides rounded up to multiples of 512.
    Returns (rows, cols, resized width, resized height)."""
    scale = longest / max(width, height)
    w, h = max(1, round(width * scale)), max(1, round(height * scale))
    cols, rows = math.ceil(w / TILE), math.ceil(h / TILE)
    return rows, cols, cols * TILE, rows * TILE


class FastEmbedColPali:  # pragma: no cover - needs the model
    def __init__(self, c: Candidate, models_dir: Path):
        self.c, self.models_dir = c, models_dir
        self.model = None

    def load(self) -> None:
        from fastembed import LateInteractionMultimodalEmbedding

        self.model = LateInteractionMultimodalEmbedding(
            model_name=self.c.repo,
            cache_dir=str(Path(self.models_dir) / "fastembed-v12s21"),
            specific_model_path=str(snapshot_dir(self.models_dir, self.c)),
            local_files_only=True,
        )

    def embed_page(self, image_path: str):
        return l2_normalize(list(self.model.embed_image([image_path], batch_size=1))[0])

    def embed_query(self, text: str):
        return l2_normalize(list(self.model.embed_text([text], batch_size=1))[0])


class OnnxColSmol:  # pragma: no cover - needs the model
    """ColSmol-256M ONNX graph traced at 13 tiles: input_ids, attention_mask, pixel_values,
    pixel_attention_mask. Inputs are built by hand (no transformers, no torch); the first run
    checks the names and the shape of the output and fails with a clear message otherwise."""

    def __init__(self, c: Candidate, models_dir: Path):
        self.c, self.models_dir = c, models_dir
        self.session = None
        self.tok = None
        self.input_types: dict[str, str] = {}

    def load(self) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        root = snapshot_dir(self.models_dir, self.c)
        self.tok = Tokenizer.from_file(str(root / "tokenizer.json"))
        self.session = ort.InferenceSession(
            str(root / "onnx" / "model.onnx"), providers=["CPUExecutionProvider"]
        )
        self.input_types = {i.name: i.type for i in self.session.get_inputs()}
        known = {"input_ids", "attention_mask", "pixel_values", "pixel_attention_mask"}
        if set(self.input_types) - known:
            raise AdapterError(
                f"entrées ONNX inattendues : {sorted(set(self.input_types) - known)}"
            )

    def _run(self, ids, pixel_values, pixel_mask):
        import numpy as np

        arrays = {
            "input_ids": np.asarray([ids], dtype=np.int64),
            "attention_mask": np.ones((1, len(ids)), dtype=np.int64),
            "pixel_values": pixel_values[None].astype(np.float32),
            "pixel_attention_mask": pixel_mask[None],
        }
        feeds = {
            name: arrays[name].astype(numpy_dtype_name(typ))
            for name, typ in self.input_types.items()
        }
        try:
            out = self.session.run(None, feeds)[0]
        except Exception as exc:  # noqa: BLE001 - the graph refuses the input: recorded
            raise AdapterError(f"le graphe refuse l'entrée : {exc!r}"[:300]) from exc
        return l2_normalize(out[0])

    def embed_page(self, image_path: str):
        import numpy as np
        from PIL import Image

        with Image.open(image_path) as img:
            img = img.convert("RGB")
            rows, cols, w, h = tile_grid(*img.size)
            if rows * cols + 1 != 13:
                raise AdapterError(f"{rows * cols + 1} tuiles : le graphe est tracé à 13")
            big = np.asarray(img.resize((w, h), Image.LANCZOS), dtype=np.float32)
            glob = np.asarray(img.resize((TILE, TILE), Image.LANCZOS), dtype=np.float32)
        tiles = [
            big[r * TILE : (r + 1) * TILE, c * TILE : (c + 1) * TILE]
            for r in range(rows)
            for c in range(cols)
        ] + [glob]
        pixels = (np.stack(tiles) / 255.0 - 0.5) / 0.5  # (13, 512, 512, 3)
        pixels = pixels.transpose(0, 3, 1, 2)
        ids = self.tok.encode(colsmol_page_text(rows, cols), add_special_tokens=False).ids
        image_id = self.tok.token_to_id(IMAGE_TOKEN)
        if sum(i == image_id for i in ids) != 13 * TILE_TOKENS:
            raise AdapterError("le nombre de jetons <image> n'est pas 13 x 64")
        return self._run(ids, pixels, np.ones((13, TILE, TILE), dtype=bool))

    def embed_query(self, text: str):
        import numpy as np

        ids = self.tok.encode(colsmol_query_text(text), add_special_tokens=False).ids
        zeros = np.zeros((13, 3, TILE, TILE), dtype=np.float32)
        return self._run(ids, zeros, np.ones((13, TILE, TILE), dtype=bool))


def make_embedder(c: Candidate, models_dir: Path):  # pragma: no cover - needs the model
    return {"fastembed": FastEmbedColPali, "onnx_idefics3": OnnxColSmol}[c.engine](c, models_dir)


# --------------------------------------------------------------------------------------
# Child process: one candidate, under the network guard, with memory and install size.
# --------------------------------------------------------------------------------------


def install_size_mb(roots: Sequence[str]) -> dict:  # pragma: no cover - installed env
    from importlib.metadata import PackageNotFoundError, distribution

    v2 = load_sibling("v2s6_decision_bench.py", "_v12s21_v2s6")
    closure = {}
    for root in roots:
        for d in v2.s12.dependency_closure(root):
            closure[d["name"].lower()] = d
    total, rows = 0, []
    for name, d in sorted(closure.items()):
        try:
            dist = distribution(name)
        except PackageNotFoundError:
            continue
        size = sum(
            p.stat().st_size for f in dist.files or [] if (p := Path(dist.locate_file(f))).is_file()
        )
        total += size
        rows.append(
            {"name": d["name"], "version": d["version"], "license": d["license"], "mb": size >> 20}
        )
    return {"total_mb": total >> 20, "packages": rows}


def has_torch() -> bool:  # pragma: no cover - installed env
    from importlib.metadata import PackageNotFoundError, distribution

    for name in ("torch", "torchvision", "transformers"):
        try:
            distribution(name)
            return True
        except PackageNotFoundError:
            pass
    return any(m in sys.modules for m in ("torch", "transformers"))


def load_sibling(filename: str, name: str):  # pragma: no cover - needs the sibling bench only
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def child_measure(
    candidate_id: str, models_dir: Path, selection_path: Path, ceiling_mb: int
) -> dict:  # pragma: no cover - needs the model
    import threading

    import psutil

    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    v2 = load_sibling("v2s6_decision_bench.py", "_v12s21_v2s6")
    s12 = v2.s12
    attempts, guard = s12._record_and_guard(allowed_hosts=[])
    _, stop_watch, watch_state = v2.start_ram_watchdog(attempts, budget_mb=ceiling_mb)
    c = CANDIDATES[candidate_id]
    spec = json.loads(selection_path.read_text("utf-8"))
    selection = Selection(
        lang=spec["lang"],
        pages=[Page(p["id"], p["doc_id"], p["number"], p["lines"]) for p in spec["pages"]],
        queries=spec["queries"],
        corpus_pages=spec["corpus_pages"],
    )
    proc = psutil.Process()
    private = {"peak": 0}
    stop = threading.Event()

    def poll() -> None:
        while not stop.is_set():
            info = proc.memory_info()
            value = getattr(info, "private", None) or info.rss
            private["peak"] = max(private["peak"], value)
            stop.wait(0.25)

    threading.Thread(target=poll, daemon=True).start()

    def probe(phase: str) -> dict:
        info = proc.memory_info()
        return {
            "rss_mb": info.rss >> 20,
            "peak_wset_mb": s12._peak_rss_mb(),
            "peak_private_mb": private["peak"] >> 20,
            "peak_pagefile_mb": (getattr(info, "peak_pagefile", 0) or 0) >> 20,
        }

    base = probe("base")
    out: dict = {"base": base, "guard": guard}
    try:
        result = measure_candidate(
            make_embedder(c, models_dir),
            selection,
            spec["images"],
            index_cap_s=spec["index_cap_s"],
            query_cap_s=spec["query_cap_s"],
            probe=probe,
        )
        out.update(result)
    except AdapterError as exc:
        out.update(status="failed", error=str(exc)[:400])
    except Exception as exc:  # noqa: BLE001 - recorded, the next candidate goes on
        out.update(status="failed", error=repr(exc)[:400])
    stop.set()
    stop_watch.set()
    final = probe("end")
    out["memory"] = final
    out["peak_mb"] = max(
        final["peak_wset_mb"] or 0, final["peak_private_mb"], final["peak_pagefile_mb"]
    )
    out["watchdog"] = watch_state
    out["attempts"] = s12.summarize_attempts(attempts)
    out["deps"] = install_size_mb(c.roots)
    out["torch"] = has_torch()
    out["ram_total_mb"] = psutil.virtual_memory().total >> 20
    return out


# --------------------------------------------------------------------------------------
# Results, aggregation, verdict, report (pure; the replay).
# --------------------------------------------------------------------------------------


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def candidate_metrics(raw: dict, run: dict | None = None) -> dict:
    """Everything the report prints about one candidate, recomputed from the recording."""
    out: dict = {"status": raw.get("status", "failed"), "error": raw.get("error")}
    if raw.get("status") != "measured":
        out["peak_mb"] = raw.get("peak_mb")
        return out
    pages, queries = raw["pages"], raw["queries"]
    idx = latency_stats([p["ms"] / 1000 for p in pages])
    qms = latency_stats([q["embed_ms"] + q["score_ms"] for q in queries])
    mean_vec = statistics.mean(p["vectors"] for p in pages) if pages else 0
    retr = retrieval_metrics(raw["scores"], raw["page_ids"], raw["gold"])
    total = (run or {}).get("corpus_pages") or len(pages)
    out.update(
        peak_mb=raw.get("peak_mb"),
        memory=raw.get("memory"),
        load_s=raw.get("load_s"),
        index_s=idx,
        query_ms=qms,
        vectors_per_page=round(mean_vec, 1),
        index_mb_corpus=index_size_mb(mean_vec, total),
        corpus_pages=total,
        corpus_minutes=round(idx["median"] * total / 60, 1) if idx["median"] else None,
        retrieval=retr,
        n_pages=len(pages),
        partial=bool(raw.get("partial")),
        query_error=raw.get("query_error"),
        deps_mb=(raw.get("deps") or {}).get("total_mb"),
        torch=raw.get("torch"),
        network=raw.get("attempts"),
    )
    return out


def verdict(m: dict) -> dict:
    """Thresholds of the spec: memory, indexing, query, quality, no torch."""
    if m.get("status") != "measured":
        return {"label": "non exécutable", "reasons": [m.get("error") or "mesure en échec"]}
    reasons = []
    peak = m.get("peak_mb")
    if peak is None or peak > RAM_BUDGET_MB:
        reasons.append(f"mémoire : pic {peak} Mo > {RAM_BUDGET_MB} Mo")
    if m["index_s"]["median"] is None or m["index_s"]["median"] > INDEX_MEDIAN_MAX_S:
        reasons.append(
            f"indexation : médiane {m['index_s']['median']} s/page > {INDEX_MEDIAN_MAX_S:g} s"
        )
    if m["query_error"]:
        reasons.append("requêtes non exécutables : " + m["query_error"])
    elif m["query_ms"]["median"] is None or m["query_ms"]["median"] > QUERY_MEDIAN_MAX_MS:
        reasons.append(f"requête : médiane {m['query_ms']['median']} ms > {QUERY_MEDIAN_MAX_MS} ms")
    r = m["retrieval"]
    if r["n_queries"] < MIN_QUERIES:
        reasons.append(f"qualité non jugeable : {r['n_queries']} requêtes < {MIN_QUERIES}")
    elif r["recall_3"] < RECALL3_MIN:
        reasons.append(f"qualité : rappel@3 {r['recall_3']} < {RECALL3_MIN}")
    if m.get("torch"):
        reasons.append("torch présent dans l'environnement de mesure")
    if reasons:
        return {"label": "ne tient pas", "reasons": reasons}
    label = "tient de justesse" if peak > RAM_COMFORT_MB else "tient"
    return {"label": label, "reasons": []}


def aggregate(results_dir: Path | None) -> dict:
    agg: dict = {"run": None, "candidates": {}}
    if results_dir is None or not (results_dir / "run.json").is_file():
        return agg
    run = json.loads((results_dir / "run.json").read_text("utf-8"))
    agg["run"] = run
    for cid in CANDIDATES:
        path = results_dir / f"{cid}.json"
        if not path.is_file():
            continue
        m = candidate_metrics(json.loads(path.read_text("utf-8")), run)
        m["verdict"] = verdict(m)
        agg["candidates"][cid] = m
    return agg


def conclusion(agg: dict) -> tuple[str, str]:
    """(short label, sentence) of the lot."""
    cands = agg["candidates"]
    if not cands:
        return (
            "pas encore mesuré",
            "Aucune mesure enregistrée : le lancement est une ressource d'Anaël.",
        )
    fits = [c for c, m in cands.items() if m["verdict"]["label"] in ("tient", "tient de justesse")]
    if fits:
        names = ", ".join(CANDIDATES[c].label for c in fits)
        return "tient", f"Tient dans le budget du CPU : {names}. Sous les réserves de la section 6."
    why = "; ".join(
        f"{CANDIDATES[c].label} : {' ; '.join(m['verdict']['reasons'])}" for c, m in cands.items()
    )
    return "ne tient pas", f"Aucun candidat mesuré ne tient. {why}."


def fr(x: float | None, nd: int = 1) -> str:
    return "n/d" if x is None else f"{x:.{nd}f}".replace(".", ",")


def render_report(agg: dict) -> str:
    run = agg["run"] or {}
    label, sentence = conclusion(agg)
    L: list[str] = [
        "# Rapport de la recherche visuelle sans OCR (ColPali, ColQwen)",
        "",
        "V1.2, story 21, CAP-19. Généré par `tools/bench/v12s21_visual_search_bench.py report` ; "
        "il se régénère à l'identique depuis `tools/bench/results/<date>-v12s21/` (aucune date de "
        "génération).",
        "",
        "## 1. Statut",
        "",
    ]
    if not agg["candidates"]:
        L += [
            "- **Pas encore mesuré.** Le script et la spec sont livrés ; la mesure demande un "
            "poste libre de tout agent (ordre d'Anaël). Les tableaux 3 à 5 sont vides.",
            "- Notice de lancement : section 7.",
        ]
    else:
        L += [
            f"- Mesure enregistrée le {run.get('measured_on', '?')} sur {run.get('machine', {}).get('platform', '?')} "  # noqa: E501
            f"({run.get('machine', {}).get('cpu_count', '?')} CPU, {run.get('machine', {}).get('ram_total_mb', '?')} Mo de RAM).",  # noqa: E501
            f"- Corpus : {run.get('lang', '?')}, {run.get('n_pages', '?')} pages tirées de {run.get('corpus_pages', '?')} "  # noqa: E501
            f"(rendu A4 150 dpi, police {run.get('font', '?')}), {run.get('n_queries', '?')} requêtes ; commit {run.get('commit', '?')}.",  # noqa: E501
            "- La mesure vaut pour le poste de développement (32 Go) : la mémoire est un pic de "
            "processus, indépendant de la RAM libre, mais les durées ne valent pas pour le PC "
            "cible (16 Go, i5) sans confirmation.",
        ]
    L += ["", f"**Conclusion : {label}.** {sentence}", "", "## 2. Candidats", ""]
    L += [
        "| Candidat | Dépôt @ révision | Poids | Licence | Voie d'exécution | Langue | État |",
        "|---|---|---|---|---|---|---|",
    ]
    for cid, c in CANDIDATES.items():
        m = agg["candidates"].get(cid)
        state = "pas encore mesuré" if m is None else f"mesuré : {m['verdict']['label']}"
        way = (
            "fastembed 0.9.1 (onnxruntime), sans torch"
            if c.engine == "fastembed"
            else ("onnxruntime + tokenizers + pillow, entrées construites à la main, sans torch")
        )
        L.append(
            f"| {c.label} | `{c.repo}` @ `{c.revision[:8]}` | {c.download_mb} Mo, {c.params} | "
            f"{c.license} | {way} | {c.languages} | {state} |"
        )
    L += [
        "",
        "Écartés ou en réserve, avec le motif (cartes lues le 2026-10-25, aucun poids téléchargé) :",  # noqa: E501
        "",
    ]
    L += [f"- {e['label']} (`{e['repo']}`) : {e['reason']}." for e in EXCLUDED.values()]
    L += ["", "## 3. Mémoire et latence", ""]
    L += [
        "| Candidat | Pic (Mo) | Budget 4 096 Mo | Chargement (s) | Indexation médiane / max (s par page) | "  # noqa: E501
        "Requête médiane / max (ms) | Pages indexées | Vecteurs par page |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for cid, c in CANDIDATES.items():
        m = agg["candidates"].get(cid)
        if m is None or m["status"] != "measured":
            err = "" if m is None else f" ({m.get('error')})"
            L.append(f"| {c.label} | pas encore mesuré{err} | | | | | | |")
            continue
        fit = "oui" if m["peak_mb"] is not None and m["peak_mb"] <= RAM_BUDGET_MB else "non"
        L.append(
            f"| {c.label} | {m['peak_mb']} | {fit} | {fr(m['load_s'])} | "
            f"{fr(m['index_s']['median'])} / {fr(m['index_s']['max'])} | "
            f"{fr(m['query_ms']['median'], 0)} / {fr(m['query_ms']['max'], 0)} | "
            f"{m['n_pages']}{' (partiel)' if m['partial'] else ''} | {fr(m['vectors_per_page'], 0)} |"  # noqa: E501
        )
    L += ["", "## 4. Qualité de la recherche et taille de l'index", ""]
    L += [
        "| Candidat | Requêtes | Rappel@1 | Rappel@3 | MRR | Index du corpus entier (Mo, fp16) | "
        "Indexation du corpus entier (min) |",
        "|---|---|---|---|---|---|---|",
    ]
    for cid, c in CANDIDATES.items():
        m = agg["candidates"].get(cid)
        if m is None or m["status"] != "measured":
            L.append(f"| {c.label} | pas encore mesuré | | | | | |")
            continue
        r = m["retrieval"]
        L.append(
            f"| {c.label} | {r['n_queries']} | {fr(r['recall_1'], 2)} | {fr(r['recall_3'], 2)} | "
            f"{fr(r['mrr'], 2)} | {fr(m['index_mb_corpus'])} ({m['corpus_pages']} pages) | "
            f"{fr(m['corpus_minutes'])} |"
        )
    L += ["", "## 5. Dépendances", ""]
    L += [
        "| Candidat | Paquets à installer (Mo sur disque) | Torch | Réseau pendant la mesure |",
        "|---|---|---|---|",
    ]
    for cid, c in CANDIDATES.items():
        m = agg["candidates"].get(cid)
        if m is None or m["status"] != "measured":
            L.append(f"| {c.label} | pas encore mesuré | | |")
            continue
        L.append(
            f"| {c.label} | {m['deps_mb']} Mo ({', '.join(c.roots)}) | "
            f"{'présent' if m['torch'] else 'absent'} | {m['network'] or 'aucune tentative'} |"
        )
    L += [
        "",
        "Aucune dépendance n'est ajoutée au projet : `pyproject.toml` et `uv.lock` ne changent "
        f"pas ; la mesure vient de `uv run --with {FASTEMBED_PIN}`. Une fonction de l'application "
        "ajouterait onnxruntime (déjà employé par le banc des modèles de décision), numpy, "
        "pillow et fastembed, plus un modèle de 0,96 à 5,9 Go à télécharger.",
        "",
        "## 6. Seuils, réserves et décisions",
        "",
        f"- Seuils : pic <= {RAM_BUDGET_MB} Mo (<= {RAM_COMFORT_MB} Mo : « tient », au-dessus : « tient de justesse ») ; "  # noqa: E501
        f"indexation médiane <= {INDEX_MEDIAN_MAX_S:g} s par page ; requête médiane <= {QUERY_MEDIAN_MAX_MS} ms ; "  # noqa: E501
        f"rappel@3 >= {RECALL3_MIN} sur au moins {MIN_QUERIES} requêtes ; pas de torch.",
        "- Les deux modèles sont entraînés sur des données anglaises : le corpus Exemplia est "
        "français, la qualité mesurée vaut pour ce corpus et cette langue, pas pour le multilingue.",  # noqa: E501
        "- ColPali v1.3 ONNX est sous les conditions d'utilisation de Gemma (restrictions "
        "d'usage, à transmettre en cas de redistribution) : à faire valider avant tout "
        "téléchargement par l'application.",
        "- Les requêtes de ColPali (fastembed) font passer une image vide dans tout le graphe : "
        "leur latence est celle d'un passage complet du modèle, pas d'un encodeur de texte seul.",
        "- Les entrées du graphe ColSmol sont construites à la main d'après la carte d'Idefics3 / "
        "ColIdefics3 ; si le graphe les refuse, la mesure l'enregistre (« non exécutable ») sans "
        "chiffre inventé.",
        "- Pages de test : rendu de texte sur fond blanc, sans mise en page riche : une borne "
        "optimiste pour la lecture, pessimiste pour l'intérêt du visuel (pas de schémas ni de scans).",  # noqa: E501
        "",
    ]
    L += deferred_block(agg)
    L += ["## 7. Commandes", ""]
    L += command_lines()
    return "\n".join(L).rstrip() + "\n"


def deferred_block(agg: dict) -> list[str]:
    label, sentence = conclusion(agg)
    L = ["### Écart à consigner dans `deferred-work.md`", ""]
    if not agg["candidates"]:
        L += [
            "Pas encore mesuré : l'entrée de report est déjà en place, à clore après la mesure.",
            "",
        ]
        return L
    L += [
        "```yaml",
        "- source_spec: `_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/stories/21-recherche-visuelle-sans-ocr.md`",  # noqa: E501
        f"  summary: CAP-19, recherche visuelle sans OCR : {label}. {sentence}",
        "  evidence: rapport-recherche-visuelle.md ; décision d'intégration (ou non) à prendre par Anaël.",  # noqa: E501
        "```",
        "",
    ]
    return L


def command_lines() -> list[str]:
    return [
        "```bash",
        "# 1. téléchargement unique, seule étape réseau (huggingface.co, révisions épinglées) : ~6,9 Go",  # noqa: E501
        f"uv run --with {FASTEMBED_PIN} python {SCRIPT} download",
        "# 2. mesure, poste libre de tout agent, hors ligne : ~20 min",
        f"uv run --with {FASTEMBED_PIN} python {SCRIPT} measure --confirm-idle",
        "# 3. rapport (rejeu sans modèle)",
        f"uv run python {SCRIPT} report --write",
        "```",
        "",
    ]


# --------------------------------------------------------------------------------------
# Commands.
# --------------------------------------------------------------------------------------


def results_dir_for(args) -> Path:
    return (
        Path(args.results_dir)
        if args.results_dir
        else RESULTS_DIR / f"{date.today().isoformat()}-v12s21"
    )


def latest_results_dir() -> Path | None:
    found = sorted(RESULTS_DIR.glob("*-v12s21/run.json")) if RESULTS_DIR.is_dir() else []
    return found[-1].parent if found else None


def cmd_list(_args) -> int:
    print("Candidats mesurables (sans torch) :")
    for c in CANDIDATES.values():
        print(
            f"  {c.id}: {c.repo} @ {c.revision[:8]}  {c.download_mb} Mo  {c.license}\n"
            f"      {c.vectors_note} ; {c.languages}"
        )
    print("Écartés ou en réserve :")
    for e in EXCLUDED.values():
        print(f"  {e['label']}: {e['reason']}")
    print(
        "\nTéléchargement (réseau) :\n  "
        + f"uv run --with {FASTEMBED_PIN} python {SCRIPT} download"
    )
    print(
        "Mesure (hors ligne) :\n  "
        + f"uv run --with {FASTEMBED_PIN} python {SCRIPT} measure --confirm-idle"
    )
    return 0


def selected(only: list[str] | None) -> list[Candidate]:
    if not only:
        return list(CANDIDATES.values())
    unknown = [o for o in only if o not in CANDIDATES]
    if unknown:
        sys.exit(f"candidat inconnu : {unknown} (voir `list`)")
    return [CANDIDATES[o] for o in only]


def cmd_download(args) -> int:  # pragma: no cover - network
    v2 = load_sibling("v2s6_decision_bench.py", "_v12s21_v2s6")
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    _attempts, guard = v2.s12._record_and_guard(allowed_hosts=DOWNLOAD_HOSTS, strip_proxy=False)
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass
    from huggingface_hub import snapshot_download

    status = 0
    for c in selected(args.only):
        target = Path(args.models_dir) / "hf-v12s21"
        try:
            snapshot_download(
                repo_id=c.repo,
                revision=c.revision,
                cache_dir=str(target),
                allow_patterns=list(c.files),
            )
        except Exception as exc:  # noqa: BLE001 - one failure does not stop the other
            print(f"{c.id}: échec {exc!r}"[:300])
            status = 2
            continue
        missing = missing_files(Path(args.models_dir), c)
        print(
            f"{c.id}: {'incomplet, manque ' + str(missing) if missing else 'ok'} (garde : {guard})"
        )
        status = status or (2 if missing else 0)
    return status


def cmd_measure(args) -> int:  # pragma: no cover - real run
    if not args.confirm_idle:
        sys.exit("Lancement réel refusé : passez --confirm-idle quand aucun autre agent ne tourne.")
    from wavestack.rag.corpus import load_rag_questions

    models_dir = Path(args.models_dir)
    cands = selected(args.only)
    for c in cands:
        missing = missing_files(models_dir, c)
        if missing:
            sys.exit(f"{c.id}: fichiers absents {missing} : lancer `download` d'abord.")
    pages = build_pages(args.lang)
    sel = select(pages, load_rag_questions(args.lang), args.lang, args.pages, args.queries)
    work = Path(args.work_dir)
    images, font = {}, ""
    for p in sel.pages:
        path = work / f"{p.id}.png"
        font = render_page(p, path)
        images[p.id] = str(path)
    v2 = load_sibling("v2s6_decision_bench.py", "_v12s21_v2s6")
    spec = {
        "lang": sel.lang,
        "corpus_pages": sel.corpus_pages,
        "pages": [
            {"id": p.id, "doc_id": p.doc_id, "number": p.number, "lines": p.lines}
            for p in sel.pages
        ],
        "queries": sel.queries,
        "images": images,
        "index_cap_s": args.index_cap_min * 60,
        "query_cap_s": args.query_cap_min * 60,
    }
    work.mkdir(parents=True, exist_ok=True)
    selection_path = work / "selection.json"
    write_json(selection_path, spec)
    results = results_dir_for(args)
    machine = {
        k: v for k, v in v2.machine_info().items() if k in ("platform", "cpu_count", "ram_total_mb")
    }
    write_json(
        results / "run.json",
        {
            "measured_on": date.today().isoformat(),
            "lang": sel.lang,
            "corpus_pages": sel.corpus_pages,
            "n_pages": len(sel.pages),
            "n_queries": len(sel.queries),
            "page_ids": [p.id for p in sel.pages],
            "query_ids": [q["id"] for q in sel.queries],
            "skipped_questions": sel.skipped,
            "font": font,
            "seed": SEED,
            "commit": v2._repo_commit(),
            "bench_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "machine": machine,
        },
    )
    status = 0
    for c in cands:
        print(
            f"{c.id}: mesure ({len(sel.pages)} pages, {len(sel.queries)} requêtes)...", flush=True
        )
        cmd = [
            sys.executable,
            str(HERE / Path(SCRIPT).name),
            "child",
            c.id,
            "--models-dir",
            str(models_dir),
            "--selection",
            str(selection_path),
            "--ceiling-mb",
            str(args.ceiling_mb),
        ]
        out = v2.s12._run_child(cmd, dict(os.environ), timeout=args.timeout_min * 60)
        if out.get("error") == "ram_ceiling":
            out = {
                "status": "failed",
                "error": f"arrêté au plafond de sécurité ({out['rss_at_stop_mb']} Mo)",
                "peak_mb": out["rss_at_stop_mb"],
            }
        elif "fatal" in out:
            out = {"status": "failed", "error": out["fatal"]}
        write_json(results / f"{c.id}.json", out)
        if out.get("status") != "measured":
            status = 2
        print(f"{c.id}: {out.get('status')} {out.get('error') or ''}")
    text = render_report(aggregate(results))
    print(text)
    return status


def cmd_report(args) -> int:
    results = Path(args.results_dir) if args.results_dir else latest_results_dir()
    text = render_report(aggregate(results))
    if args.write:
        REPORT_PATH.write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    rp = sub.add_parser("report")
    rp.add_argument("--results-dir")
    rp.add_argument("--write", action="store_true")
    for name in ("download", "measure", "child"):
        s = sub.add_parser(name)
        s.add_argument("--models-dir", default=str(DEFAULT_MODELS_DIR))
        s.add_argument("--only", nargs="*")
        if name == "download":
            continue
        if name == "child":
            s.add_argument("candidate")
            s.add_argument("--selection", required=True)
            s.add_argument("--ceiling-mb", type=int, default=RAM_CEILING_MB)
            continue
        s.add_argument("--confirm-idle", action="store_true")
        s.add_argument("--results-dir")
        s.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR))
        s.add_argument("--lang", default=LANG_DEFAULT, choices=("fr", "en", "de"))
        s.add_argument("--pages", type=int, default=N_PAGES)
        s.add_argument("--queries", type=int, default=N_QUERIES)
        s.add_argument("--index-cap-min", type=float, default=INDEX_CAP_MIN)
        s.add_argument("--query-cap-min", type=float, default=QUERY_CAP_MIN)
        s.add_argument("--timeout-min", type=int, default=CHILD_TIMEOUT_MIN)
        s.add_argument("--ceiling-mb", type=int, default=RAM_CEILING_MB)
    args = p.parse_args(argv)
    if args.cmd == "child":  # pragma: no cover
        out = child_measure(
            args.candidate, Path(args.models_dir), Path(args.selection), args.ceiling_mb
        )
        print(json.dumps(out, ensure_ascii=False))
        return 0
    return {
        "list": cmd_list,
        "report": cmd_report,
        "download": cmd_download,
        "measure": cmd_measure,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
