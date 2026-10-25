"""V1.2 story 2 benchmark: System One decision models for the passage filter (CAP-6) and the
grounding check, and the 16,384-token window of Qwen3.5-2B in 4 GB (CAP-7).

Spec: `_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/stories/
2-banc-prealable-system-one.md` (section "Décisions du point de contrôle"). Modelled on
`v2s6_decision_bench.py`, whose helpers it reuses (`_snapshot`, NLI helpers, RAM watchdog,
machine info); it adds no dependency to the project: measurement packages come from
`uv run --with ...`. Only the standard library is imported at module level (project modules
and `httpx` are imported where used), so `tests/test_v12s2_system_one_bench.py` tests the
pure logic without network or model.

Commands (from the repository root; the real ones need `--confirm-idle`, never run in CI):

    uv run python tools/bench/v12s2_system_one_bench.py list
    uv run python tools/bench/v12s2_system_one_bench.py dry-run [--results-dir D]
    uv run python tools/bench/v12s2_system_one_bench.py online --confirm-idle
    uv run --with onnxruntime --with tokenizers --with huggingface-hub \\
        python tools/bench/v12s2_system_one_bench.py local --confirm-idle --download
    uv run python tools/bench/v12s2_system_one_bench.py memory --confirm-idle

The key (`OPENROUTER_API_KEY`, else `HKCU\\Environment`) is never printed, logged or written.
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
import subprocess
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPT = "tools/bench/v12s2_system_one_bench.py"
SPEC_DIR = ROOT / "_bmad-output" / "specs" / "spec-wavestack-v1-2-atelier-recherche-documentaire"
REPORT_PATH = SPEC_DIR / "rapport-banc-system-one.md"
MEMLOG_PATH = SPEC_DIR / ".memlog.md"
CLAIMS_PATH = HERE / "data" / "v12s2_claims.yaml"
RESULTS_DIR = HERE / "results"

# --------------------------------------------------------------------------------------
# Constants: endpoint, key, budget, thresholds (spec, decisions 1, 3, 4, 8).
# --------------------------------------------------------------------------------------

ENDPOINT_URL = "https://openrouter.ai/api/alpha/decisions"
ALLOWED_HOSTS = ("openrouter.ai",)
KEY_ENV = "OPENROUTER_API_KEY"
QUESTION_KEY = "decision"
LANGS = ("fr", "en", "de")
CHUNK_MAX_CHARS = 700  # [rag] chunk_max_chars of wavestack.toml: what the filter will see
SEED = 12002
PREMISE_SEP = "\n\n---\n\n"
REPETITIONS_ONLINE = 2
DETERMINISM_ITEMS = 20
DETERMINISM_EPS = 1e-4
CAP_USD = 2.00
CAP_CALLS = 6000
CAP_MODEL_USD = 0.33
FREE_RATE_PER_MIN = 20
RETRY_AFTER_MAX_S = 60
RATE_LIMIT_TRIES = 3
REQUEST_TIMEOUT_S = 60
BOOTSTRAP_DRAWS = 300

FILTER_RECALL_MIN = 0.95
FILTER_REJECT_MIN = 0.60
GROUNDING_RECALL_MIN = 0.80
H7_MAX = 0.13
H7_LITERATURE_JEV = 0.23
ERROR_RATE_WATCH = 0.05
LOCAL_LATENCY_MEDIAN_MS = 1000
LOCAL_LATENCY_MAX_MS = 3000
RAM_BUDGET_MB = 4096
TOP_K = 3
RERANK_CANDIDATES = 8
BASCULE_THRESHOLDS = (0.3, 0.5, 0.7)

MEMORY_N_CTX = 16384
MEMORY_MARGIN_TOKENS = 256
MEMORY_CONFIRMED_MB = 3072
MEMORY_LIMIT_MB = 4096
RAG_V1_MB = 1170  # V2 measure: the embedding and the reranker of the RAG brick

INSTRUCTIONS = {
    "filter": {
        "fr": (
            "Ce passage contient-il l'information qui permet de répondre à la question ? "
            "Réponds oui seulement si le passage suffit à répondre."
        ),
        "en": (
            "Does this passage contain the information needed to answer the question? "
            "Answer yes only if the passage is enough to answer."
        ),
        "de": (
            "Enthält dieser Abschnitt die Information, die zur Beantwortung der Frage nötig "
            "ist? Antworte nur dann mit ja, wenn der Abschnitt zur Antwort ausreicht."
        ),
    },
    "grounding": {
        "fr": (
            "L'affirmation est-elle entièrement étayée par les passages ? Réponds non si elle "
            "ajoute ou change un fait, un chiffre ou une condition."
        ),
        "en": (
            "Is the claim fully supported by the passages? Answer no if it adds or changes a "
            "fact, a number or a condition."
        ),
        "de": (
            "Wird die Aussage von den Abschnitten vollständig gestützt? Antworte mit nein, "
            "wenn sie eine Tatsache, eine Zahl oder eine Bedingung hinzufügt oder ändert."
        ),
    },
}
NLI_HYPOTHESIS = {
    "fr": "Ce passage répond à la question : {q}",
    "en": "This passage answers the question: {q}",
    "de": "Dieser Abschnitt beantwortet die Frage: {q}",
}
YES_NO = {"fr": ("oui", "non"), "en": ("yes", "no"), "de": ("ja", "nein")}
KINDS_NEGATIVE = ("same_doc", "hard", "random")


# --------------------------------------------------------------------------------------
# Candidates.
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    id: str
    kind: str  # "online" | "local"
    label: str
    tasks: tuple[str, ...] = ("filter", "grounding")
    published: str = ""  # figures published, kept when the endpoint does not know the model
    v2s6_id: str = ""  # the candidate of `v2s6` whose loader the bench reuses
    packages: tuple[str, ...] = ()  # `uv run --with` of its command
    office: str = ""  # "écarté" verdict without measure
    office_reason: str = ""
    free: bool = False
    # Pinned weights (decision 1 criteria: pinning). `revision` overrides the `v2s6` candidate's,
    # which follows `main`; `repo`, `files` and `onnx_file` describe a candidate of its own.
    revision: str = ""
    repo: str = ""
    files: tuple[str, ...] = ()
    onnx_file: str = ""


_NO_FIGURE = "aucun chiffre publié connu"
ONLINE = (
    Candidate(
        "typesafe/jev-1.14",
        "online",
        "Jev 1.14 (TypeSafe)",
        published="23 % d'affirmations non étayées acceptées (H7, un article Towards AI)",
    ),
    Candidate(
        "microsoft/microsoft-decision-1", "online", "Microsoft Decision 1", published=_NO_FIGURE
    ),
    Candidate(
        "openai/gpt-6-luna-decisions", "online", "GPT-6 Luna Decisions", published=_NO_FIGURE
    ),
    Candidate(
        "perplexity/pplx-decider-flash-v1.2",
        "online",
        "PPLX Decider Flash 1.2",
        published=_NO_FIGURE,
    ),
    Candidate("liquid/d1", "online", "Liquid D1", published=_NO_FIGURE),
    Candidate(
        "inception/mercury-decide:free",
        "online",
        "Mercury Decide (gratuit)",
        published=_NO_FIGURE,
        free=True,
    ),
)
# Model cards read on 2026-10-25 (Hugging Face API and GitHub, card files only, no weight).
DEBERTA_XSMALL_REVISION = "262ae02f29173eec1c250f90804dc7edc677dcff"
MDEBERTA_REVISION = "b5113eb38ab63efdd7f280f8c144ea8b13f978ce"
# Strands Decider 2B: the official checkpoints (StrandsAgents/strands-decider-2B-*) are a PEFT
# adapter + head that need torch (`strands-decider` requires torch, transformers, peft); the
# GGUF port needs a patched llama.cpp. The ONNX port of hobson v19 (onnx-community) runs on
# ONNX Runtime's CPU provider: one fused graph, input_ids, attention_mask, answer_pos,
# option_pos -> logits; prompt rendering of `strands_decider.prompting` (commit b81d443).
STRANDS_REPO = "onnx-community/strands-decider-2B-hobson-v19-ONNX"
STRANDS_REVISION = "31a83e0244b26d939ae33f87189d6c8204003e53"
STRANDS_ONNX = "onnx/model_quantized.onnx"  # q8, the card's default (1.80 GB)
STRANDS_FILES = ("config.json", "tokenizer.json", STRANDS_ONNX, STRANDS_ONNX + "_data")
STRANDS_MAX_LENGTH = 4096
# AnyJev (Nokia, Apache-2.0): a training-free readout of any causal LM, numpy only, with a
# llama-cpp-python backend; run here on the application's own SLM (no second model).
# The PyPI wheel 0.3.0 has no llama.cpp backend (added after it): the archive of the read
# commit, a pure-Python build (setuptools, no compiler).
ANYJEV_COMMIT = "35311c58955716cb8955ce1368a665988bc63735"
ANYJEV_PACKAGE = (
    f"anyjev @ https://github.com/nokia-applied-research/AnyJev/archive/{ANYJEV_COMMIT}.tar.gz"
)
ANYJEV_N_CTX = 4096
LOCAL = (
    Candidate(
        "deberta_xsmall",
        "local",
        "deberta-v3-xsmall zero-shot NLI (ONNX)",
        v2s6_id="deberta_xsmall",
        packages=("onnxruntime", "tokenizers", "huggingface-hub"),
        revision=DEBERTA_XSMALL_REVISION,
    ),
    Candidate(
        "nli_mdeberta",
        "local",
        "mDeBERTa-v3 xnli (petit NLI ONNX multilingue)",
        v2s6_id="mdeberta",
        packages=("onnxruntime", "tokenizers", "huggingface-hub"),
        revision=MDEBERTA_REVISION,
    ),
    Candidate(
        "reranker_livre",
        "local",
        "bge-reranker-v2-m3 Q4_K_M de la brique (seuil sur le score)",
        tasks=("filter",),
    ),
    Candidate("slm_juge", "local", "SLM juge Qwen3.5-2B + GBNF (référence et repli)"),
    Candidate(
        "strands_decider_2b",
        "local",
        "Strands Decider 2B hobson v19 (port ONNX q8)",
        packages=("onnxruntime", "tokenizers", "huggingface-hub", "numpy"),
        revision=STRANDS_REVISION,
        repo=STRANDS_REPO,
        files=STRANDS_FILES,
        onnx_file=STRANDS_ONNX,
    ),
    Candidate(
        "anyjev",
        "local",
        "AnyJev 0.3.0 (commit 35311c5), lecture L0 du SLM Qwen3.5-2B (llama-cpp-python)",
        packages=(ANYJEV_PACKAGE,),
    ),
)
CANDIDATES = ONLINE + LOCAL
BY_ID = {c.id: c for c in CANDIDATES}


def slug(candidate_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", candidate_id)


# --------------------------------------------------------------------------------------
# The item set, built from the corpus and the questions (decision 2).
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    id: str
    task: str  # "filter" | "grounding"
    lang: str
    kind: str  # pos, same_doc, hard, random, stale | supported, number, invented, inversion
    label: bool  # filter: the passage answers; grounding: the claim is supported
    query: str  # filter: the question; grounding: the claim
    text: str  # filter: the passage; grounding: the premise (passages joined)
    group: str = "main"  # "stale": outdated passage, counted apart
    question_id: str = ""


@dataclass
class Built:
    items: list[Item] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)  # anchors across two chunks, counted


def _norm(text: str) -> str:
    return " ".join(text.split())


def load_claims(path: Path = CLAIMS_PATH) -> dict[str, dict[str, list[dict]]]:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))["claims"]


def _passage_text(chunk) -> str:
    from wavestack.rag.index import passage_text

    return passage_text(chunk)


def build_items(lang: str, claims: dict | None = None) -> Built:
    """The items of one language: filter pairs (question, chunk) and grounding pairs
    (premise, claim), labelled by construction. Chunks are those of the brick's default
    chunking over the active corpus (the trapped and sentinel documents are inactive)."""
    from wavestack.rag.corpus import chunk_corpus, load_rag_content, load_rag_questions
    from wavestack.rag.lab import bm25

    claims = load_claims() if claims is None else claims
    content = load_rag_content(lang)
    chunks = chunk_corpus(content, CHUNK_MAX_CHARS, lang)
    questions = load_rag_questions(lang)
    texts = [_passage_text(c) for c in chunks]
    norm_chunks = [_norm(c.text) for c in chunks]
    doc_order = list(dict.fromkeys(c.doc_id for c in chunks))
    built = Built()

    def containing(doc_id: str, anchor: str) -> list[int]:
        a = _norm(anchor)
        return [i for i, c in enumerate(chunks) if c.doc_id == doc_id and a in norm_chunks[i]]

    for q in questions:
        rng = random.Random(f"{SEED}:{lang}:{q.id}")
        query = q.question_text if not q.history else f"{q.history[-1]} {q.question_text}"
        bm = bm25(query, texts, lang)
        ranking = sorted(range(len(chunks)), key=lambda i: (-bm[i], i))
        positives: list[tuple[int, int]] = []  # (anchor rank, chunk index)
        dropped = False
        for n, passage in enumerate(q.expected_passages, start=1):
            found = containing(passage.doc_id, passage.anchor_text)
            if found:
                positives.append((n, found[0]))
            else:
                dropped = True
                built.dropped.append(f"{lang}.{q.id}.pos{n}")
        stale = []
        for n, passage in enumerate(q.trap_passages, start=1):
            found = containing(passage.doc_id, passage.anchor_text)
            if found:
                stale.append((n, found[0]))
            else:
                built.dropped.append(f"{lang}.{q.id}.stale{n}")
        expected_docs = {p.doc_id for p in q.expected_passages}
        trap_docs = {p.doc_id for p in q.trap_passages}
        used = {i for _, i in positives} | {i for _, i in stale}
        away = expected_docs | trap_docs
        # hard: the best BM25 chunk of a document that is not expected
        hard = next((i for i in ranking if chunks[i].doc_id not in away and i not in used), None)
        used_neg = {hard} if hard is not None else set()
        anchor_doc = (
            q.expected_passages[0].doc_id
            if q.expected_passages
            else chunks[hard].doc_id
            if hard is not None
            else doc_order[0]
        )
        same = [
            i
            for i, c in enumerate(chunks)
            if c.doc_id == anchor_doc and i not in used and i not in used_neg
        ]
        if same:
            same_doc = rng.choice(same)
        else:  # a one-chunk document: the next document in the corpus order
            nxt = doc_order[(doc_order.index(anchor_doc) + 1) % len(doc_order)]
            same_doc = next(i for i, c in enumerate(chunks) if c.doc_id == nxt)
        used_neg.add(same_doc)
        pool = [
            i
            for i, c in enumerate(chunks)
            if c.doc_id not in away and i not in used and i not in used_neg
        ]
        rand = rng.choice(pool)
        used_neg.add(rand)

        def add_filter(
            q, suffix: str, kind: str, index: int, label: bool, group: str = "main"
        ) -> None:
            built.items.append(
                Item(
                    f"filter.{lang}.{q.id}.{suffix}",
                    "filter",
                    lang,
                    kind,
                    label,
                    q.question_text,
                    texts[index],
                    group,
                    q.id,
                )
            )

        for n, index in positives:
            add_filter(q, f"pos{n}", "pos", index, True)
        add_filter(q, "same_doc", "same_doc", same_doc, False)
        if hard is not None:
            add_filter(q, "hard", "hard", hard, False)
        add_filter(q, "random", "random", rand, False)
        for n, index in stale:
            add_filter(q, f"stale{n}", "stale", index, False, "stale")

        # grounding: the premise is the expected chunks plus the hard negative
        if dropped:
            continue
        premise_idx = [i for _, i in positives]
        if not premise_idx:  # no_answer: the two best chunks of two different documents
            first = ranking[0]
            second = next(i for i in ranking if chunks[i].doc_id != chunks[first].doc_id)
            premise_idx = [first, second]
        elif hard is not None:
            premise_idx.append(hard)
        premise_idx = list(dict.fromkeys(premise_idx))
        random.Random(f"{SEED}:{lang}:{q.id}:premise").shuffle(premise_idx)
        premise = PREMISE_SEP.join(texts[i] for i in premise_idx)
        mine = claims.get(lang, {}).get(q.id, [])
        if q.type != "no_answer":
            built.items.append(
                Item(
                    f"grounding.{lang}.{q.id}.supported",
                    "grounding",
                    lang,
                    "supported",
                    True,
                    q.expected_answer_text,
                    premise,
                    question_id=q.id,
                )
            )
        for n, claim in enumerate(mine, start=1):
            built.items.append(
                Item(
                    f"grounding.{lang}.{q.id}.unsupported{n}",
                    "grounding",
                    lang,
                    claim["kind"],
                    False,
                    claim["text"],
                    premise,
                    question_id=q.id,
                )
            )
    return built


def build_all(langs: Iterable[str] = LANGS) -> Built:
    claims = load_claims()
    total = Built()
    for lang in langs:
        part = build_items(lang, claims)
        total.items += part.items
        total.dropped += part.dropped
    return total


class ProvenanceError(ValueError):
    """A text that does not come from the fictitious Exemplia corpus or the question set."""


def allowed_texts(lang: str, claims: dict | None = None) -> tuple[set[str], set[str]]:
    """(passages, queries) that may leave the machine in `lang`."""
    from wavestack.rag.corpus import chunk_corpus, load_rag_content, load_rag_questions

    claims = load_claims() if claims is None else claims
    chunks = chunk_corpus(load_rag_content(lang), CHUNK_MAX_CHARS, lang)
    passages = {_passage_text(c) for c in chunks}
    questions = load_rag_questions(lang)
    queries = {q.question_text for q in questions} | {q.expected_answer_text for q in questions}
    queries |= {c["text"] for per_q in claims.get(lang, {}).values() for c in per_q}
    return passages, queries


def assert_provenance(items: Iterable[Item]) -> None:
    """Refuses any item whose text is not the active Exemplia corpus or the question set."""
    cache: dict[str, tuple[set[str], set[str]]] = {}
    for item in items:
        passages, queries = cache.setdefault(item.lang, allowed_texts(item.lang))
        if item.query not in queries:
            raise ProvenanceError(f"{item.id}: texte hors du jeu de questions et des affirmations")
        parts = item.text.split(PREMISE_SEP) if item.task == "grounding" else [item.text]
        for part in parts:
            if part not in passages:
                raise ProvenanceError(f"{item.id}: passage hors du corpus Exemplia actif")


# --------------------------------------------------------------------------------------
# Request, key, transport (spec: format of T9, whitelist of the host, no leak of the key).
# --------------------------------------------------------------------------------------


def state_for(item: Item) -> dict:
    if item.task == "filter":
        return {"question": item.query, "passage": item.text}
    return {"premise": item.text, "claim": item.query}


def request_body(model: str, item: Item) -> dict:
    return {
        "model": model,
        "state": state_for(item),
        "questions": {
            QUESTION_KEY: {"type": "noul", "instructions": INSTRUCTIONS[item.task][item.lang]}
        },
    }


def body_bytes(body: dict) -> bytes:
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def request_sha256(model: str, item: Item) -> str:
    return hashlib.sha256(body_bytes(request_body(model, item))).hexdigest()


class ForbiddenHost(RuntimeError):
    pass


def check_host(url: str) -> None:
    if urlsplit(url).hostname not in ALLOWED_HOSTS:
        raise ForbiddenHost(f"hôte non autorisé : {urlsplit(url).hostname!r}")


def read_registry_key(name: str = KEY_ENV) -> str | None:  # pragma: no cover - Windows only
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            value, _ = winreg.QueryValueEx(k, name)
        return value or None
    except OSError:
        return None


def read_key(environ=None, registry=None) -> str | None:
    """The key from the variable, else the user's registry; never printed anywhere."""
    environ = os.environ if environ is None else environ
    registry = registry or read_registry_key
    return environ.get(KEY_ENV) or registry(KEY_ENV) or None


def redact(text: object, key: str | None) -> str:
    out = str(text)
    if key:
        out = out.replace(key, "***")
    return out


@dataclass
class Raw:
    status: int | None
    payload: dict | None
    error: str
    latency_ms: int
    retry_after: float = 0.0


class DecisionClient:
    """One POST to the decisions endpoint. `transport` is an `httpx` transport (a fake in
    tests); the key only ever lives in the Authorization header of the live request."""

    def __init__(self, key: str, transport=None, url: str = ENDPOINT_URL, clock=time.perf_counter):
        check_host(url)
        self._key = key
        self._url = url
        self._clock = clock
        import httpx

        self._http = httpx.Client(
            transport=transport, timeout=REQUEST_TIMEOUT_S, follow_redirects=False, trust_env=True
        )

    def post(self, raw_body: bytes) -> Raw:
        check_host(self._url)
        t0 = self._clock()
        try:
            r = self._http.post(
                self._url,
                content=raw_body,
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
            )
        except Exception as exc:  # noqa: BLE001 - network failure: counted, never raised
            ms = int((self._clock() - t0) * 1000)
            return Raw(None, None, redact(f"{type(exc).__name__}: {exc}", self._key)[:200], ms)
        ms = int((self._clock() - t0) * 1000)
        try:
            payload = r.json()
            if not isinstance(payload, dict):
                payload = None
        except ValueError:
            payload = None
        err = ""
        if r.status_code >= 400 or payload is None:
            err = redact(error_summary(r.status_code, payload), self._key)
        try:
            wait = float(r.headers.get("Retry-After", 0) or 0)
        except ValueError:
            wait = 0.0
        return Raw(r.status_code, payload, err, ms, wait)

    def close(self) -> None:
        self._http.close()


def error_summary(status: int, payload: dict | None) -> str:
    """Status and the `error.code` / `error.message` of the body, nothing else: the raw body
    may carry a generation id or an account id (decision 6, white list)."""
    out = f"HTTP {status}"
    err = (payload or {}).get("error")
    if isinstance(err, dict):
        code, message = err.get("code"), err.get("message")
        if isinstance(code, int | str) and not isinstance(code, bool):
            out += f" {code}"
        if isinstance(message, str):
            out += f" : {message}"
    elif isinstance(err, str):
        out += f" : {err}"
    elif payload is None and 200 <= status < 300:
        out += " : réponse non JSON"
    return " ".join(out.split())[:200]


def retained(model: str, raw: Raw) -> dict:
    """White list of the response: nothing else is ever recorded (no header, no id)."""
    p = raw.payload or {}
    usage = p.get("usage") if isinstance(p.get("usage"), dict) else {}
    answers = p.get("answers") if isinstance(p.get("answers"), dict) else {}
    answer = answers.get(QUESTION_KEY) if isinstance(answers.get(QUESTION_KEY), dict) else {}
    noul = answer.get("noul")
    ok = isinstance(noul, int | float) and not isinstance(noul, bool) and 0 <= noul <= 1
    return {
        "model_returned": p.get("model") if isinstance(p.get("model"), str) else None,
        "noul": float(noul) if ok else None,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cost": usage.get("cost") if isinstance(usage.get("cost"), int | float) else None,
    }


# --------------------------------------------------------------------------------------
# Recording, budget, resumable online run.
# --------------------------------------------------------------------------------------


def recorded_path(results_dir: Path, candidate_id: str) -> Path:
    return results_dir / "recorded" / f"{slug(candidate_id)}.jsonl"


def read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def append_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


class Budget:
    """Hard caps, in dollars and calls, overall and per model. Checked before every call:
    spent + the highest cost seen for this model must stay within the cap."""

    def __init__(self, cap_usd=CAP_USD, cap_calls=CAP_CALLS, cap_model_usd=CAP_MODEL_USD):
        self.cap_usd, self.cap_calls, self.cap_model_usd = cap_usd, cap_calls, cap_model_usd
        self.spent = 0.0
        self.calls = 0
        self.model_spent: dict[str, float] = {}
        self.model_calls: dict[str, int] = {}
        self.model_max: dict[str, float] = {}

    def add(self, model: str, cost: float | None, calls: int = 1) -> None:
        c = float(cost or 0.0)
        self.spent += c
        self.calls += calls
        self.model_spent[model] = self.model_spent.get(model, 0.0) + c
        self.model_calls[model] = self.model_calls.get(model, 0) + calls
        self.model_max[model] = max(self.model_max.get(model, 0.0), c)

    def stop_reason(self, model: str) -> str | None:
        """`global:...` stops the whole run, `model:...` only this model."""
        worst = self.model_max.get(model, 0.0)
        if self.calls >= self.cap_calls:
            return "global:calls"
        if self.spent + worst > self.cap_usd + 1e-12:
            return "global:usd"
        if self.model_spent.get(model, 0.0) + worst > self.cap_model_usd + 1e-12:
            return "model:usd"
        return None

    def snapshot(self) -> dict:
        return {
            "cap_usd": self.cap_usd,
            "cap_calls": self.cap_calls,
            "cap_model_usd": self.cap_model_usd,
            "spent_usd": round(self.spent, 6),
            "calls": self.calls,
            "model_spent_usd": {k: round(v, 6) for k, v in sorted(self.model_spent.items())},
            "model_calls": dict(sorted(self.model_calls.items())),
        }


AUTH_STATUSES = (401, 402, 403)  # key refused, credit exhausted, forbidden: the whole run
RETRYABLE_4XX = (408, 429)


def is_auth_error(raw: Raw) -> bool:
    return raw.status in AUTH_STATUSES


def is_unknown_model(raw: Raw) -> bool:
    return (
        raw.status is not None
        and 400 <= raw.status < 500
        and raw.status not in AUTH_STATUSES + RETRYABLE_4XX
    )


class StopRun(Exception):
    pass


def call_one(
    client: DecisionClient,
    model: str,
    item: Item,
    budget: Budget,
    sleep: Callable[[float], None],
    *,
    retry_server: bool = True,
) -> tuple[Raw, int, str]:
    """One decision, with the retries of the spec: 429 waits `Retry-After` (at most 60 s) up
    to three tries and is not an error; 5xx, timeout or invalid JSON: one retry then error.
    The budget is checked again before every retry. Returns (last raw, number of HTTP calls,
    outcome in ok | error | rate_limit | refused | auth | budget)."""
    raw_body = body_bytes(request_body(model, item))
    calls = 0
    tries_429 = 0
    retried = False
    raw = None
    while True:
        if calls and budget.stop_reason(model):
            return raw, calls, "budget"
        raw = client.post(raw_body)
        calls += 1
        budget.add(model, retained(model, raw)["cost"])
        if raw.status == 429:
            tries_429 += 1
            if tries_429 >= RATE_LIMIT_TRIES:
                return raw, calls, "rate_limit"
            sleep(min(raw.retry_after or 1.0, RETRY_AFTER_MAX_S))
            continue
        if (
            raw.status is not None
            and 200 <= raw.status < 300
            and retained(model, raw)["noul"] is not None
        ):
            return raw, calls, "ok"
        if is_auth_error(raw):
            return raw, calls, "auth"
        if is_unknown_model(raw):
            return raw, calls, "refused"
        if retry_server and not retried:
            retried = True
            continue
        return raw, calls, "error"


def run_online(
    items: list[Item],
    models: list[str],
    results_dir: Path,
    client: DecisionClient,
    budget: Budget,
    *,
    reps: int = REPETITIONS_ONLINE,
    today: Callable[[], str] = lambda: date.today().isoformat(),
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    log: Callable[[str], None] = print,
) -> dict:
    """The real online series, resumable: records already written are not called again and
    their costs count in the budget. Returns the state written to `run_state.json`."""
    assert_provenance(items)
    probes_path = results_dir / "probes.json"
    probes = json.loads(probes_path.read_text("utf-8")) if probes_path.exists() else {}
    state: dict = {"incomplete": {}, "stopped": None}
    last_call = 0.0
    done_by_model: dict[str, set] = {}
    # every recorded cost counts before the first call, whatever the order of the models
    for c in ONLINE:
        records = read_records(recorded_path(results_dir, c.id))
        done_by_model[c.id] = {(r["item_id"], r["rep"]) for r in records}
        for r in records:
            budget.add(c.id, r.get("cost"), calls=r.get("calls", 1))

    def stop(model: str, reason: str) -> None:
        scope, why = reason.split(":")
        state["incomplete"][model] = why
        if scope == "global":
            state["stopped"] = why

    for model in models:
        path = recorded_path(results_dir, model)
        done = done_by_model.get(model, set())
        if probes.get(model, {}).get("status") == "unknown_model":
            continue
        for rep in range(1, reps + 1):
            for item in items:
                if (item.id, rep) in done:
                    continue
                reason = budget.stop_reason(model)
                if reason:
                    stop(model, reason)
                    break
                if BY_ID[model].free:  # 20 requests per minute at most
                    wait = 60.0 / FREE_RATE_PER_MIN - (clock() - last_call)
                    if wait > 0:
                        sleep(wait)
                    last_call = clock()
                raw, calls, outcome = call_one(client, model, item, budget, sleep)
                if outcome == "auth":  # never a verdict on the model: the whole run stops
                    state["stopped"] = f"auth:{raw.status}"
                    state["incomplete"][model] = "auth"
                    log(f"{model}: accès refusé (HTTP {raw.status}), banc arrêté : clé ou crédit")
                    break
                if outcome == "budget":  # cap reached between two tries: the item is not kept
                    stop(model, budget.stop_reason(model) or "model:usd")
                    break
                if outcome == "refused" and model not in probes:
                    probes[model] = {"status": "unknown_model", "http": raw.status}
                    write_json(probes_path, probes)
                    log(f"{model}: modèle refusé par le point d'accès (publié, non mesuré)")
                    break
                if model not in probes and outcome == "ok":
                    probes[model] = {"status": "ok"}
                    write_json(probes_path, probes)
                if outcome == "rate_limit":
                    state["incomplete"][model] = "rate_limit"
                    break
                r = retained(model, raw)
                if outcome == "ok" and r["cost"] is None and not BY_ID[model].free:
                    missing = state.setdefault("cost_missing", {})
                    missing[model] = missing.get(model, 0) + 1
                    if missing[model] == 1:
                        log(f"{model}: coût absent de la réponse, compté 0 (budget sous-estimé)")
                append_record(
                    path,
                    {
                        "item_id": item.id,
                        "candidate": model,
                        "rep": rep,
                        "request_sha256": request_sha256(model, item),
                        "status": raw.status,
                        **r,
                        "calls": calls,
                        "latency_ms": raw.latency_ms,
                        "date": today(),
                        "error": None
                        if outcome == "ok"
                        else (raw.error or "réponse invalide")[:200],
                    },
                )
            if model in state["incomplete"] or probes.get(model, {}).get("status") != "ok":
                break
            if state["stopped"]:
                break
        if state["stopped"]:
            break
    state["budget"] = budget.snapshot()
    return state


# --------------------------------------------------------------------------------------
# Metrics (pure).
# --------------------------------------------------------------------------------------


def auc(scores: list[float], labels: list[bool]) -> float | None:
    """Area under the ROC curve by ranks; ties count one half."""
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    sum_pos = sum(r for r, lab in zip(ranks, labels, strict=True) if lab)
    return (sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def auc_ci(scores: list[float], labels: list[bool], draws: int = BOOTSTRAP_DRAWS) -> list | None:
    """95 % interval by stratified bootstrap (fixed seed)."""
    pos = [s for s, lab in zip(scores, labels, strict=True) if lab]
    neg = [s for s, lab in zip(scores, labels, strict=True) if not lab]
    if not pos or not neg:
        return None
    rng = random.Random(SEED)
    values = []
    for _ in range(draws):
        p = [rng.choice(pos) for _ in pos]
        n = [rng.choice(neg) for _ in neg]
        a = auc(p + n, [True] * len(p) + [False] * len(n))
        values.append(a)
    values.sort()
    return [
        round(values[int(0.025 * draws)], 4),
        round(values[min(draws - 1, int(0.975 * draws))], 4),
    ]


def wilson(k: int, n: int) -> list | None:
    if n == 0:
        return None
    z = 1.96
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def threshold_for_recall(pos_scores: list[float], min_recall: float) -> float | None:
    """The highest threshold (accept when score >= it) that keeps `min_recall` of positives."""
    if not pos_scores:
        return None
    desc = sorted(pos_scores, reverse=True)
    k = max(1, math.ceil(min_recall * len(desc) - 1e-9))
    return desc[k - 1]


def calibration(scores: list[float], labels: list[bool], bins: int = 5) -> list[dict]:
    out = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, s in enumerate(scores) if lo <= s < hi or (b == bins - 1 and s == 1.0)]
        if idx:
            out.append(
                {
                    "bin": f"{lo:.1f}-{hi:.1f}",
                    "n": len(idx),
                    "mean_prob": round(sum(scores[i] for i in idx) / len(idx), 4),
                    "observed": round(sum(labels[i] for i in idx) / len(idx), 4),
                }
            )
    return out


def histogram(scores: list[float], bins: int = 10) -> list[int]:
    h = [0] * bins
    for s in scores:
        h[min(bins - 1, max(0, int(s * bins)))] += 1
    return h


def evaluate_at(task: str, rows: list[dict], thr: float | None) -> dict:
    """Metrics at one threshold. Rows: score, label, group ('main' | 'stale'). A row whose
    every try failed (score None) counts against the candidate: a positive is missed, a
    negative is accepted (never a gain from an error)."""
    if thr is None:
        return {}

    def keeps(r: dict) -> bool:
        return r["score"] is None or r["score"] >= thr

    pos = [r for r in rows if r["label"]]
    neg = [r for r in rows if not r["label"] and r["group"] == "main"]
    stale = [r for r in rows if r["group"] == "stale"]
    recall = (
        sum(r["score"] is not None and r["score"] >= thr for r in pos) / len(pos) if pos else None
    )
    accepted = sum(keeps(r) for r in neg)
    out = {"threshold": round(thr, 4), "recall": _r(recall), "n_pos": len(pos), "n_neg": len(neg)}
    failed = sum(r["score"] is None for r in rows)
    if failed:
        out["n_failed"] = failed
    if task == "filter":
        out["reject_share"] = _r(1 - accepted / len(neg)) if neg else None
        out["stale_reject_share"] = (
            _r(sum(not keeps(r) for r in stale) / len(stale)) if stale else None
        )
        out["n_stale"] = len(stale)
    else:
        out["h7"] = _r(accepted / len(neg)) if neg else None
        out["h7_ci"] = wilson(accepted, len(neg))
    return out


def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(x, nd)


def task_metrics(
    task: str, rows: list[dict], probabilistic: bool = True, calibrated: bool = True
) -> dict:
    """All metrics of one candidate on one task, from scored rows (failed rows: only in the
    metrics at a threshold, see `evaluate_at`)."""
    all_rows = rows
    rows = [r for r in rows if r["score"] is not None]
    scores = [r["score"] for r in rows]
    labels = [r["label"] for r in rows]
    main = [r for r in rows if r["group"] == "main"]
    min_recall = FILTER_RECALL_MIN if task == "filter" else GROUNDING_RECALL_MIN
    thr = threshold_for_recall([r["score"] for r in rows if r["label"]], min_recall)
    out: dict = {
        "n_scored": len(rows),
        "auc": _r(auc([r["score"] for r in main], [r["label"] for r in main]))
        if probabilistic
        else None,
        "auc_ci": auc_ci([r["score"] for r in main], [r["label"] for r in main])
        if probabilistic
        else None,
        "tuned": evaluate_at(task, all_rows, thr),
        "fixed_05": evaluate_at(task, all_rows, 0.5),
        "calibration": calibration(scores, labels) if probabilistic and calibrated else None,
        "histogram": histogram(scores),
        "switch_to_judge": {
            f"{t:.1f}": _r(sum(s < t for s in scores) / len(scores)) if scores else None
            for t in BASCULE_THRESHOLDS
        },
        "by_lang": {},
    }
    for lang in LANGS:
        sub = [r for r in all_rows if r["lang"] == lang]
        if sub:
            out["by_lang"][lang] = evaluate_at(task, sub, thr)
    return out


def latency_stats(values: list[int]) -> dict:
    if not values:
        return {"median_ms": None, "max_ms": None}
    return {"median_ms": round(statistics.median(values), 1), "max_ms": max(values)}


# --------------------------------------------------------------------------------------
# Aggregation and replay (dry run), shared with the real run.
# --------------------------------------------------------------------------------------


class ReplayError(RuntimeError):
    pass


def candidate_tasks(c: Candidate) -> tuple[str, ...]:
    return c.tasks


def score_rows(
    c: Candidate, items: dict[str, Item], records: list[dict], reps: int, incomplete: bool
) -> tuple[dict[str, list[dict]], dict]:
    """Rows per task from the recorded cases, plus counters. A missing case raises an error
    naming the candidate and the item, unless the series stopped at a cap."""
    by_key: dict[tuple[str, int], dict] = {}
    for r in records:
        by_key[(r["item_id"], r["rep"])] = r
    rows: dict[str, list[dict]] = {t: [] for t in c.tasks}
    errors = total = 0
    gaps: list[float] = []
    latencies: list[int] = []
    cost = 0.0
    calls = 0
    versions: set[str] = set()
    dates: list[str] = []
    for item in items.values():
        if item.task not in c.tasks:
            continue
        probs: list[float] = []
        tried = False
        for rep in range(1, reps + 1):
            rec = by_key.get((item.id, rep))
            if rec is None:
                if incomplete:
                    continue
                raise ReplayError(f"cas manquant : {c.id} / {item.id} (répétition {rep})")
            if c.kind == "online" and rec["request_sha256"] != request_sha256(c.id, item):
                raise ReplayError(f"cas périmé (texte changé) : {c.id} / {item.id}")
            total += 1
            tried = True
            cost += float(rec.get("cost") or 0.0)
            calls += rec.get("calls", 1)
            latencies.append(int(rec["latency_ms"]))
            dates.append(rec["date"])
            if rec.get("model_returned"):
                versions.add(rec["model_returned"])
            value = rec.get("noul") if c.kind == "online" else rec.get("prob")
            if value is None:
                errors += 1
            else:
                probs.append(float(value))
        if len(probs) >= 2:
            gaps.append(max(probs) - min(probs))
        if probs or tried:  # every try in error: kept, counted against (`evaluate_at`)
            rows[item.task].append(
                {
                    "id": item.id,
                    "score": sum(probs) / len(probs) if probs else None,
                    "label": item.label,
                    "group": item.group,
                    "lang": item.lang,
                }
            )
    counters = {
        "attempts": total,
        "errors": errors,
        "error_rate": _r(errors / total) if total else None,
        "repro_max_gap": _r(max(gaps)) if gaps else None,
        "latency": latency_stats(latencies),
        "cost_usd": round(cost, 6),
        "calls": calls,
        "versions": sorted(versions),
        "dates": [min(dates), max(dates)] if dates else [],
    }
    return rows, counters


def aggregate(results_dir: Path, all_items: list[Item]) -> dict:
    """Metrics of every candidate from the recorded cases of `results_dir`."""
    run_path = results_dir / "run.json"
    run = json.loads(run_path.read_text("utf-8"))
    wanted = set(run["item_ids"])
    by_id = {i.id: i for i in all_items}
    missing = sorted(wanted - set(by_id))
    if missing:
        raise ReplayError(f"item inconnu du jeu actuel : {missing[0]}")
    items = {i: by_id[i] for i in sorted(wanted)}
    probes_path = results_dir / "probes.json"
    probes = json.loads(probes_path.read_text("utf-8")) if probes_path.exists() else {}
    state_path = results_dir / "run_state.json"
    state = json.loads(state_path.read_text("utf-8")) if state_path.exists() else {}
    incomplete = state.get("incomplete", {})
    out_c: dict[str, dict] = {}
    for cid in run["candidates"]:
        c = BY_ID[cid]
        entry: dict = {"id": cid, "kind": c.kind, "label": c.label, "published": c.published}
        if c.kind == "online":
            probe = probes.get(cid, {})
            if probe.get("status") != "ok":
                entry.update(
                    status="published",
                    reason="modèle refusé par le point d'accès"
                    if probe.get("status") == "unknown_model"
                    else "pas encore appelé",
                )
                out_c[cid] = entry
                continue
            probabilistic = True
            local_meta = {}
        else:
            meta_path = results_dir / "local" / f"{slug(cid)}.json"
            local_meta = json.loads(meta_path.read_text("utf-8")) if meta_path.exists() else {}
            if c.office or local_meta.get("status") == "discarded":
                entry.update(
                    status="discarded", reason=c.office_reason or local_meta.get("reason", "")
                )
                out_c[cid] = entry
                continue
            if not local_meta:
                entry.update(status="unmeasured", reason="pas encore mesuré")
                out_c[cid] = entry
                continue
            probabilistic = bool(local_meta.get("probabilistic", True))
        records = read_records(recorded_path(results_dir, cid))
        reps = REPETITIONS_ONLINE if c.kind == "online" else 1
        rows, counters = score_rows(c, items, records, reps, cid in incomplete)
        if c.kind == "local" and "determinism" in local_meta:
            counters["repro_max_gap"] = local_meta["determinism"].get("max_gap")
        entry.update(status="measured", counters=counters, local=local_meta, tasks={})
        if cid in incomplete:
            entry["incomplete"] = incomplete[cid]
        for task, task_rows in rows.items():
            if task_rows:
                entry["tasks"][task] = task_metrics(
                    task, task_rows, probabilistic, cid != "reranker_livre"
                )
        out_c[cid] = entry
    memory_path = results_dir / "memory.json"
    return {
        "synthetic": (results_dir / "fixture.json").exists(),
        "n_items": len(items),
        "langs": sorted({i.lang for i in items.values()}),
        "items_by_task": {
            t: sum(1 for i in items.values() if i.task == t) for t in ("filter", "grounding")
        },
        "stopped": state.get("stopped"),
        "budget": state.get("budget"),
        "candidates": out_c,
        "memory": json.loads(memory_path.read_text("utf-8")) if memory_path.exists() else None,
        "commit": run.get("commit"),
        "machine": run.get("machine"),
    }


# --------------------------------------------------------------------------------------
# Choice (decision 1): local by default, cloud apart; no choice without an H7 measure.
# --------------------------------------------------------------------------------------


def _passes(c: dict, task: str) -> bool:
    if c.get("status") != "measured" or c.get("incomplete"):
        return False
    m = c.get("tasks", {}).get(task)
    if not m or (c["counters"]["error_rate"] or 0) > ERROR_RATE_WATCH:
        return False
    t = m["tuned"]
    if task == "filter":
        ok = (t.get("reject_share") or 0) >= FILTER_REJECT_MIN
    else:
        ok = t.get("h7") is not None and t["h7"] <= H7_MAX
    if c["kind"] == "local":
        lat = c["counters"]["latency"]
        ram = c.get("local", {}).get("rss_with_slm_mb")
        ok = ok and (lat["median_ms"] or 0) <= LOCAL_LATENCY_MEDIAN_MS
        ok = ok and (lat["max_ms"] or 0) <= LOCAL_LATENCY_MAX_MS
        ok = ok and (ram is None or ram <= RAM_BUDGET_MB)
    return ok


def choose(agg: dict) -> dict:
    """The filter and the grounding check: default (local), fallback, cloud option."""
    cands = agg["candidates"]
    measured = [c for c in cands.values() if c["status"] == "measured"]
    out: dict = {"state": "unmeasured"}
    if not measured:
        return out
    if agg.get("stopped") or any(c.get("incomplete") for c in measured):
        out["state"] = "incomplete"
        return out
    out["state"] = "chosen"
    local = [c for c in measured if c["kind"] == "local"]
    cloud = [c for c in measured if c["kind"] == "online"]

    def key_filter(c):
        return -(c["tasks"]["filter"]["tuned"].get("reject_share") or 0)

    def key_ground(c):
        t = c["tasks"]["grounding"]["tuned"]
        return (t["h7"], -(t.get("recall") or 0))

    reranker = cands.get("reranker_livre")
    pass_f = sorted((c for c in local if _passes(c, "filter")), key=key_filter)
    ref_reject = None
    if reranker and reranker["status"] == "measured" and "filter" in reranker.get("tasks", {}):
        ref_reject = reranker["tasks"]["filter"]["tuned"].get("reject_share")
    default_f = None
    for c in pass_f:  # without the reference measured, no decision model is the filter
        if c["id"] == "reranker_livre" or ref_reject is None:
            continue
        if (c["tasks"]["filter"]["tuned"].get("reject_share") or 0) > ref_reject:
            default_f = c
        break
    if default_f is None and ref_reject is not None:
        default_f = reranker
    fallback_f = next((c for c in pass_f if default_f is None or c["id"] != default_f["id"]), None)
    out["filter"] = {
        "default": default_f["id"] if default_f else None,
        "fallback": fallback_f["id"] if fallback_f else None,
        "cloud": next(
            (c["id"] for c in sorted((c for c in cloud if _passes(c, "filter")), key=key_filter)),
            None,
        ),
    }
    pass_g = sorted(
        (c for c in measured if c["kind"] == "local" and _passes(c, "grounding")), key=key_ground
    )
    out["grounding"] = {
        "default": pass_g[0]["id"] if pass_g else None,
        "fallback": pass_g[1]["id"] if len(pass_g) > 1 else None,
        "cloud": next(
            (
                c["id"]
                for c in sorted((c for c in cloud if _passes(c, "grounding")), key=key_ground)
            ),
            None,
        ),
    }
    return out


# --------------------------------------------------------------------------------------
# Memory (decision 8).
# --------------------------------------------------------------------------------------


def memory_verdict(peak_mb: float | None) -> str:
    if peak_mb is None:
        return "pas encore mesuré"
    if peak_mb <= MEMORY_CONFIRMED_MB:
        return "confirmé"
    if peak_mb <= MEMORY_LIMIT_MB:
        return "confirmé sur le poste de développement, confirmation sur le PC cible demandée"
    return "infirmé"


def memory_peak(mem: dict | None) -> float | None:
    if not mem:
        return None
    values = [mem.get(k) for k in ("peak_working_set_mb", "peak_private_mb")]
    values = [v for v in values if v is not None]
    return max(values) if values else None


def memlog_block(mem: dict | None) -> str:
    """The `.memlog.md` line for the 16,384 tokens / 4 GB hypothesis."""
    peak = memory_peak(mem)
    if peak is None:
        return (
            "- (event) Banc V1.2 story 2, hypothèse « 16 384 tokens avec Qwen3.5-2B dans 4 Go » : "
            "pas encore mesuré (pic de RSS à relever par `v12s2_system_one_bench.py memory`, "
            "lancement réel sur ordre d'Anaël, poste libre)."
        )
    return (
        f"- (event) Banc V1.2 story 2, hypothèse « 16 384 tokens avec Qwen3.5-2B dans 4 Go » : "
        f"{memory_verdict(peak)}. Pic {peak:.0f} Mo (n_ctx {mem['n_ctx']}, prompt de "
        f"{mem['prompt_tokens_full']} tokens), RAM du poste {mem['ram_total_mb']} Mo ; "
        "mesure sur un poste de 32 Go, majorant pour le PC cible de 16 Go."
    )


# --------------------------------------------------------------------------------------
# Report (deterministic: no generation date, no local path).
# --------------------------------------------------------------------------------------

NOT_MEASURED = "pas encore mesuré"


def f2(x: float | None, nd: int = 2) -> str:
    return "—" if x is None else f"{x:.{nd}f}".replace(".", ",")


def pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.0f} %".replace(".", ",")


def ci(x: list | None) -> str:
    return "" if not x else f" [{f2(x[0])} ; {f2(x[1])}]"


def status_label(c: dict) -> str:
    if c["status"] == "measured":
        return "mesuré (incomplet : " + c["incomplete"] + ")" if c.get("incomplete") else "mesuré"
    if c["status"] == "published":
        return "publié, non mesuré"
    if c["status"] == "discarded":
        return "écarté"
    return NOT_MEASURED


def render_report(agg: dict, choice: dict) -> str:
    L: list[str] = []
    cands = agg["candidates"]
    L += [
        "# Rapport du banc préalable System One et fenêtre de 16 384 tokens",
        "",
        "V1.2, story 2. Généré par `tools/bench/v12s2_system_one_bench.py` ; le rejeu à sec "
        "régénère ce fichier à l'identique (aucune date de génération).",
        "",
    ]
    if agg["synthetic"]:
        L += [
            "> **DONNÉES SYNTHÉTIQUES DE FIXTURE : ce ne sont pas des mesures.** Réponses "
            "fabriquées pour tester le rejeu en CI.",
            "",
        ]
    dates = sorted({d for c in cands.values() for d in c.get("counters", {}).get("dates", [])})
    L += [
        "## 1. Statut",
        "",
        f"- Mesure : {'enregistrée du ' + dates[0] + ' au ' + dates[-1] if dates else NOT_MEASURED}.",  # noqa: E501
        f"- Items : {agg['n_items']} (filtre {agg['items_by_task']['filter']}, ancrage "
        f"{agg['items_by_task']['grounding']}), en {', '.join(agg['langs'])}.",
        f"- Commit du lancement : {agg.get('commit') or NOT_MEASURED}.",
        f"- Verdict : {_state_text(choice['state'])}.",
        "",
        "## 2. Choix",
        "",
    ]
    if choice["state"] != "chosen":
        L += [
            f"Aucun choix : {_state_text(choice['state'])}. "
            "Le défaut reste local ; un modèle en ligne n'est jamais un prérequis.",
            "",
        ]
    else:
        for role, title in (("filter", "Filtre de passages"), ("grounding", "Contrôle d'ancrage")):
            ch = choice[role]
            L += [
                f"**{title}**",
                f"- Défaut local : {_name(ch['default'], cands) or 'aucun candidat ne passe'}.",
                f"- Repli : {_name(ch['fallback'], cands) or 'aucun'} (SLM juge si mesuré).",
                f"- Option cloud (à part, CAP-6) : {_name(ch['cloud'], cands) or 'aucune'}.",
                "",
            ]
    L += [
        "Règles : le défaut est local. Filtre : au seuil de probabilité le plus haut qui garde "
        f"un rappel du passage attendu >= {f2(FILTER_RECALL_MIN)}, part des négatifs écartés "
        f">= {f2(FILTER_REJECT_MIN)} ; le reranker livré est la référence (un modèle de décision "
        "n'est choisi que s'il écarte plus de négatifs que lui au même rappel). Ancrage : au "
        f"seuil qui garde un rappel des étayées >= {f2(GROUNDING_RECALL_MIN)}, part des non "
        f"étayées acceptées (H7) <= {f2(H7_MAX)}. Un candidat sans mesure H7 n'est jamais choisi "
        f"pour l'ancrage ; un taux d'erreur > {pct(ERROR_RATE_WATCH)} le met « à surveiller », "
        "jamais choisi. Seuils ajustés sur le jeu lui-même, donc optimistes : les chiffres au "
        "seuil fixe 0,5 sont donnés aussi. Les seuils du filtre sont une proposition du "
        "développement, sans source ; l'origine de H7 est un seul article (Towards AI : Jev "
        "23 %, LLM 13 %).",
        "",
        "## 3. Candidats",
        "",
        "| Candidat | Type | État | H7 (non étayées acceptées) | Version rendue / motif |",
        "|---|---|---|---|---|",
    ]
    for c in cands.values():
        h7 = c.get("tasks", {}).get("grounding", {}).get("tuned", {})
        if c["status"] == "measured" and h7:
            h7s = f"{pct(h7.get('h7'))}{ci(h7.get('h7_ci'))}"
        elif c["status"] == "published":
            h7s = c["published"]
        else:
            h7s = "—"
        extra = ", ".join(c.get("counters", {}).get("versions", [])) or c.get("reason", "")
        L.append(
            f"| {c['label']} (`{c['id']}`) | {'en ligne' if c['kind'] == 'online' else 'local'} | "
            f"{status_label(c)} | {h7s} | {extra} |"
        )
    L.append("")
    for task, title, _n in (
        ("filter", "4. Filtre de passages", 4),
        ("grounding", "5. Contrôle d'ancrage", 5),
    ):
        L += [f"## {title}", ""]
        measured = [c for c in cands.values() if task in c.get("tasks", {})]
        if not measured:
            L += [NOT_MEASURED, ""]
            continue
        if task == "filter":
            L += [
                "| Candidat | n | AUC [IC 95 %] | Seuil | Rappel | Écartés | Périmés écartés | "
                "Écartés à 0,5 | Latence méd./max (ms) | k=3 / k=8 (ms) | Erreurs | Écart répét. |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|",
            ]
        else:
            L += [
                "| Candidat | n | AUC [IC 95 %] | Seuil | Rappel étayées | H7 [IC 95 %] | "
                "H7 à 0,5 | Latence méd./max (ms) | Erreurs | Écart répét. |",
                "|---|---|---|---|---|---|---|---|---|---|",
            ]
        for c in measured:
            m = c["tasks"][task]
            t, f = m["tuned"], m["fixed_05"]
            lat = c["counters"]["latency"]
            auc_s = f"{f2(m['auc'])}{ci(m['auc_ci'])}" if m["auc"] is not None else "non calculable"
            err = pct(c["counters"]["error_rate"])
            if (c["counters"]["error_rate"] or 0) > ERROR_RATE_WATCH:
                err += " (à surveiller)"
            gap = f2(c["counters"]["repro_max_gap"])
            lat_s = f"{f2(lat['median_ms'], 0)} / {f2(lat['max_ms'], 0)}"
            if task == "filter":
                k3 = f2((lat["median_ms"] or 0) * TOP_K, 0)
                k8 = f2((lat["median_ms"] or 0) * RERANK_CANDIDATES, 0)
                L.append(
                    f"| {c['label']} | {m['n_scored']} | {auc_s} | {f2(t.get('threshold'))} | "
                    f"{f2(t.get('recall'))} | {pct(t.get('reject_share'))} | "
                    f"{pct(t.get('stale_reject_share'))} | {pct(f.get('reject_share'))} | "
                    f"{lat_s} | {k3} / {k8} | {err} | {gap} |"
                )
            else:
                L.append(
                    f"| {c['label']} | {m['n_scored']} | {auc_s} | {f2(t.get('threshold'))} | "
                    f"{f2(t.get('recall'))} | {pct(t.get('h7'))}{ci(t.get('h7_ci'))} | "
                    f"{pct(f.get('h7'))} | {lat_s} | {err} | {gap} |"
                )
        L += [
            "",
            "Par langue (au seuil retenu) : "
            + (
                " ; ".join(
                    f"{c['label']} {lang} "
                    + (
                        f"écartés {pct(v.get('reject_share'))}"
                        if task == "filter"
                        else f"H7 {pct(v.get('h7'))}"
                    )
                    for c in measured
                    for lang, v in c["tasks"][task]["by_lang"].items()
                )
                or NOT_MEASURED
            )
            + ".",
            "",
        ]
        if task == "grounding":
            L += [
                "H7 est décidé sur les trois langues regroupées. Les items sont des traductions "
                "les uns des autres, donc non indépendants : les intervalles sont optimistes.",
                "",
            ]
    L += ["## 6. Calibration, distribution et bascule vers le SLM juge", ""]
    shown = False
    for c in cands.values():
        for task, m in c.get("tasks", {}).items():
            shown = True
            cal = (
                "sans objet"
                if m["calibration"] is None
                else "; ".join(
                    f"{b['bin']} : prob. {f2(b['mean_prob'])} / observé {f2(b['observed'])} (n={b['n']})"  # noqa: E501
                    for b in m["calibration"]
                )
            )
            sw = ", ".join(f"seuil {k} : {pct(v)}" for k, v in m["switch_to_judge"].items())
            L += [
                f"- {c['label']}, {task} : calibration {cal}. Distribution (10 classes) : "
                f"{m['histogram']}. Part des items sous le seuil (bascule vers le SLM juge) : {sw}."
            ]
    L += [""] if shown else [NOT_MEASURED, ""]
    L += ["## 7. Formulations exactes des `instructions`", ""]
    for task in ("filter", "grounding"):
        for lang in LANGS:
            L.append(f"- {task}, {lang} : « {INSTRUCTIONS[task][lang]} »")
    L += [
        "",
        'Requête : `{model, state, questions: {decision: {type: "noul", instructions}}}` ; '
        "état du filtre `{question, passage}`, de l'ancrage `{premise, claim}`.",
        "",
        "## 8. Candidats locaux",
        "",
    ]
    local = [c for c in cands.values() if c["kind"] == "local"]
    for c in local:
        meta = c.get("local") or {}
        if c["status"] == "measured":
            L.append(
                f"- {c['label']} : RAM avec le SLM chargé {meta.get('rss_with_slm_mb', '—')} Mo "
                f"(budget {RAM_BUDGET_MB}), ajoutée {meta.get('rss_added_mb', '—')} Mo ; "
                f"versions {meta.get('versions', {})} ; révisions {meta.get('revisions', {})} ; "
                f"sha256 {meta.get('sha256', '—')} ; déterministe : "
                f"{meta.get('determinism', {}).get('deterministic', '—')} ; probabilité : "
                f"{'oui' if meta.get('probabilistic', True) else 'non (étiquette seule)'} ; "
                f"troncature à 512 tokens : {meta.get('truncated_items', 0)} items."
            )
        else:
            L.append(
                f"- {c['label']} : {status_label(c)}"
                + (f" ({c['reason']})" if c.get("reason") else "")
                + "."
            )
    L += ["", "## 9. Budget", ""]
    b = agg.get("budget")
    if b:
        L += [
            f"- Dépensé {b['spent_usd']:.4f} $ sur un plafond de {f2(b['cap_usd'])} $ ; "
            f"{b['calls']} appels sur {b['cap_calls']} ; plafond par modèle {f2(b['cap_model_usd'])} $.",  # noqa: E501
            *(
                f"- {k} : {v:.4f} $, {b['model_calls'].get(k, 0)} appels."
                for k, v in b["model_spent_usd"].items()
            ),
        ]
        if agg.get("stopped"):
            L.append(f"- Arrêt au plafond ({agg['stopped']}) : rapport incomplet, aucun choix.")
    else:
        L.append(NOT_MEASURED)
    L += ["", "## 10. Mémoire de la fenêtre de 16 384 tokens (Qwen3.5-2B)", ""]
    mem = agg.get("memory")
    if mem:
        L += [
            f"- Pic de l'ensemble de travail {mem['peak_working_set_mb']} Mo, pic de mémoire privée "  # noqa: E501
            f"{mem['peak_private_mb']} Mo ; n_ctx {mem['n_ctx']}, prompt de "
            f"{mem['prompt_tokens_full']} tokens ; RAM du poste {mem['ram_total_mb']} Mo.",
            f"- Estimation `_kv_per_token` x 16 384 : {mem.get('kv_estimate_mb', '—')} Mo.",
            f"- Verdict : {memory_verdict(memory_peak(mem))}. Le pic mesuré sur un poste de 32 Go "
            "est un majorant pour le PC cible de 16 Go (cache KV alloué pour tout n_ctx, mmap).",
            f"- Avec le RAG V1 (+{RAG_V1_MB} Mo, mesure V2), informatif : "
            f"{memory_peak(mem) + RAG_V1_MB:.0f} Mo.",
        ]
    else:
        L.append(
            f"{NOT_MEASURED}. Seuils : <= {MEMORY_CONFIRMED_MB} Mo confirmé ; "
            f"{MEMORY_CONFIRMED_MB} à {MEMORY_LIMIT_MB} Mo confirmé sur le poste de "
            "développement, confirmation sur le PC cible demandée ; au-delà, infirmé."
        )
    L += [
        "",
        "## 11. Limites",
        "",
        "- Jeu fictif Exemplia (corpus et questions du dépôt), affirmations non étayées écrites à "
        "la main : petites tailles, IC larges, items traduits non indépendants.",
        "- Seuils ajustés sur le jeu : optimistes. Probabilités des modèles en ligne rendues au "
        "centième (ex æquo fréquents).",
        "- Mesure mémoire sur 32 Go : majorant pour le PC cible 16 Go (point 8 de la spec).",
        "- Un modèle en ligne n'est jamais un prérequis (SPEC.md) ; données envoyées : corpus "
        "fictif et jeu de questions seulement.",
        "",
        "## 12. Commandes",
        "",
        f"- Rejeu à sec (sans réseau) : `uv run python {SCRIPT} dry-run`.",
        f"- Réel en ligne : `uv run python {SCRIPT} online --confirm-idle`.",
        f"- Réel local : `uv run --with onnxruntime --with tokenizers --with huggingface-hub "
        f"python {SCRIPT} local --confirm-idle --download`.",
        f"- Mémoire : `uv run python {SCRIPT} memory --confirm-idle`.",
        "",
    ]
    return "\n".join(L)


def _state_text(state: str) -> str:
    return {
        "unmeasured": NOT_MEASURED,
        "incomplete": "incomplet (plafond atteint ou série interrompue)",
        "chosen": "mesuré",
    }[state]


def _name(cid: str | None, cands: dict) -> str | None:
    return f"{cands[cid]['label']} (`{cid}`)" if cid else None


def empty_aggregate() -> dict:
    """The template: every candidate listed, nothing measured."""
    cands = {}
    for c in CANDIDATES:
        entry = {"id": c.id, "kind": c.kind, "label": c.label, "published": c.published}
        if c.office:
            entry.update(status="discarded", reason=c.office_reason)
        else:
            entry.update(status="unmeasured", reason=NOT_MEASURED)
        cands[c.id] = entry
    return {
        "synthetic": False,
        "n_items": 0,
        "langs": list(LANGS),
        "items_by_task": {"filter": 0, "grounding": 0},
        "stopped": None,
        "budget": None,
        "candidates": cands,
        "memory": None,
        "commit": None,
        "machine": None,
    }


def dry_run(results_dir: Path | None, all_items: list[Item] | None = None) -> tuple[str, dict]:
    """The report and the aggregates, without network, key or model."""
    if results_dir is None or not (results_dir / "run.json").exists():
        agg = empty_aggregate()
        if all_items is not None:
            agg["n_items"] = len(all_items)
            for t in ("filter", "grounding"):
                agg["items_by_task"][t] = sum(1 for i in all_items if i.task == t)
    else:
        agg = aggregate(results_dir, build_all().items if all_items is None else all_items)
    return render_report(agg, choose(agg)), agg


def latest_results_dir() -> Path | None:
    dirs = (
        sorted(p for p in RESULTS_DIR.glob("*-v12s2") if p.is_dir()) if RESULTS_DIR.exists() else []
    )
    return dirs[-1] if dirs else None


# --------------------------------------------------------------------------------------
# Local candidates and memory: children measured under the network guard (real run only).
# --------------------------------------------------------------------------------------


def _load_v2s6():  # pragma: no cover - needs the sibling bench only
    path = HERE / "v2s6_decision_bench.py"
    name = "_v12s2_v2s6_helpers"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def softmax_pair(a: float, b: float) -> float:
    m = max(a, b)
    ea, eb = math.exp(a - m), math.exp(b - m)
    return ea / (ea + eb)


def yes_probability(top: list[dict], lang: str) -> float | None:  # pragma: no cover - model
    """P(yes) from the top logprobs of the first permitted token, None when absent."""
    yes, no = YES_NO[lang]
    ly = ln = None
    for entry in top:
        tok = str(entry.get("token", "")).strip().lower()
        lp = entry.get("logprob")
        if lp is None:
            continue
        if tok.startswith(yes) and ly is None:
            ly = lp
        elif tok.startswith(no) and ln is None:
            ln = lp
    if ly is None or ln is None:
        return None
    return softmax_pair(ly, ln)


def v2_candidate(c: Candidate, v2):
    """The `v2s6` candidate that downloads and opens `c`'s files, pinned to `c.revision`."""
    import dataclasses

    if c.v2s6_id:
        v = v2.candidate(c.v2s6_id)
        return dataclasses.replace(v, revision=c.revision) if c.revision else v
    if not c.repo:
        return None
    return v2.Candidate(
        id=c.id,
        doc_name=c.label,
        tier="-",
        backend="onnx",
        repos=((c.repo, c.files),),
        onnx_file=c.onnx_file,
        revision=c.revision,
    )


def pinned_snapshot(c: Candidate, models_dir: Path, v2) -> Path:  # pragma: no cover - model
    """The local snapshot of `c` at its pinned commit; another commit is refused."""
    v = v2_candidate(c, v2)
    repo, files = v.repos[0]
    root = v2._snapshot(models_dir, repo, files, v)
    if v.revision and root.name != v.revision:
        raise RuntimeError(f"{repo} : snapshot {root.name}, commit épinglé {v.revision}")
    return root


# Strands Decider prompt (port of `strands_decider.prompting`, commit b81d443, noul only).
_STRANDS_NOUL_HEADER = "Decide whether the statement is true of the state."
_STRANDS_NOUL_OPTIONS = (
    ("false", "the statement does not hold for this state"),
    ("true", "the statement holds for this state"),
)


def strands_render(state: object, instructions: str) -> tuple[str, str, list[tuple[int, int]]]:
    """(state text, question text, character span of each option line in the question)."""
    if isinstance(state, str):
        content = state.strip()
    else:
        content = json.dumps(state, indent=2, ensure_ascii=False)
    state_text = "<state>\n" + content + "\n</state>\n"
    prefix = (
        '<question type="noul">\n'
        + _STRANDS_NOUL_HEADER
        + "\n"
        + instructions.strip()
        + "\n<options>\n"
    )
    lines, spans, cursor = [], [], len(prefix)
    for i, (name, desc) in enumerate(_STRANDS_NOUL_OPTIONS):
        line = f"{i + 1}. {name} \u2014 {desc}"
        lines.append(line)
        spans.append((cursor, cursor + len(line)))
        cursor += len(line) + 1
    question = prefix + "\n".join(lines) + "\n</options>\n</question>\n<answer>"
    return state_text, question, spans


def strands_positions(
    n_state: int, n_question: int, offsets: list[tuple[int, int]], spans: list[tuple[int, int]]
) -> tuple[int, list[int]]:
    """answer_pos (the last token, `<answer>`) and option_pos (last token of each option
    line), in the whole prompt (state tokens then question tokens)."""
    option_pos = []
    for a, b in spans:
        last = -1
        for j, (lo, hi) in enumerate(offsets):
            if hi > lo and lo >= a and hi <= b:
                last = j
        if last < 0:
            raise ValueError(f"option ({a},{b}) sans jeton")
        option_pos.append(n_state + last)
    return n_state + n_question - 1, option_pos


def strands_p_true(logits: list[float], temperature: float) -> float:
    """Softmax of the two slots (false, true) after the noul temperature: P(true)."""
    a, b = (x / temperature for x in logits[:2])
    return 1.0 - softmax_pair(a, b)


def _loader_strands(c: Candidate, models_dir: Path, v2):  # pragma: no cover - model
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    root = pinned_snapshot(c, models_dir, v2)
    cfg = json.loads((root / "config.json").read_text("utf-8"))["decider"]
    temperature = float(cfg["temperature_by_kind"]["noul"])
    tok = Tokenizer.from_file(str(root / "tokenizer.json"))
    session = ort.InferenceSession(str(root / c.onnx_file), providers=["CPUExecutionProvider"])

    def score(item: Item) -> tuple[float, bool]:
        state_text, question, spans = strands_render(
            state_for(item), INSTRUCTIONS[item.task][item.lang]
        )
        s_ids = tok.encode(state_text, add_special_tokens=True).ids
        q = tok.encode(question, add_special_tokens=False)
        if len(s_ids) + len(q.ids) > STRANDS_MAX_LENGTH:
            raise ValueError(f"invite de {len(s_ids) + len(q.ids)} jetons > {STRANDS_MAX_LENGTH}")
        answer_pos, option_pos = strands_positions(len(s_ids), len(q.ids), q.offsets, spans)
        ids = s_ids + q.ids
        feeds = {
            "input_ids": np.array([ids], dtype=np.int64),
            "attention_mask": np.ones((1, len(ids)), dtype=np.int64),
            "answer_pos": np.array([answer_pos], dtype=np.int64),
            "option_pos": np.array([option_pos], dtype=np.int64),
        }
        logits = session.run(None, feeds)[0][0].tolist()
        return strands_p_true(logits, temperature), False

    return score, {"revisions": {c.repo: root.name}, "onnx_file": c.onnx_file}


def _loader_anyjev(c: Candidate, slm: Path):  # pragma: no cover - model
    from anyjev import Decider, Question
    from anyjev.backends.llamacpp import LlamaCppBackend

    backend = LlamaCppBackend(str(slm), n_ctx=ANYJEV_N_CTX)
    # content-free prior: one correction per question, independent of the order of the items
    decider = Decider(backend, level="L0", prior="content_free")
    questions = {
        (t, lang): Question.noul(INSTRUCTIONS[t][lang], name=QUESTION_KEY)
        for t in ("filter", "grounding")
        for lang in LANGS
    }

    def score(item: Item) -> tuple[float, bool]:
        d = decider.decide(state_for(item), [questions[(item.task, item.lang)]])[QUESTION_KEY]
        return float(d.p_true), False

    return score, {"revisions": {"anyjev": ANYJEV_COMMIT, "slm": slm.name}}


def _loader_nli(c: Candidate, models_dir: Path, v2):  # pragma: no cover - model
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    v = v2_candidate(c, v2)
    repo, files = v.repos[0]
    root = pinned_snapshot(c, models_dir, v2)
    cfg = json.loads((root / "config.json").read_text("utf-8"))
    entail = v2.entailment_index(cfg["id2label"])
    tok = Tokenizer.from_file(str(root / "config.json").replace("config.json", "tokenizer.json"))
    tok.enable_truncation(max_length=512)
    tok.enable_padding(pad_id=int(cfg.get("pad_token_id", 0)))
    session = ort.InferenceSession(str(root / v.onnx_file), providers=["CPUExecutionProvider"])
    names = {i.name for i in session.get_inputs()}

    def score(item: Item) -> tuple[float, bool]:
        hyp = (
            NLI_HYPOTHESIS[item.lang].format(q=item.query) if item.task == "filter" else item.query
        )
        enc = tok.encode(item.text, hyp)
        feeds = {k: np.array(x, dtype=np.int64) for k, x in v2.onnx_feeds([enc], names).items()}
        logits = session.run(None, feeds)[0].tolist()[0]
        return v2.softmax(logits)[entail], bool(enc.overflowing)

    return score, {"revisions": {repo: root.name}, "onnx_inputs": sorted(names)}


def _loader_reranker(c: Candidate, models_dir: Path, v2):  # pragma: no cover - model
    from wavestack import config
    from wavestack.models.reranker import open_reranker

    model, why = config.load_config().rag_reranker
    if model is None:
        raise RuntimeError(why)
    reranker = open_reranker(model)

    def score(item: Item) -> tuple[float, bool]:
        r = reranker.score(item.query, [item.text])[0]
        return r.score, r.truncated

    return score, {"revisions": {model.id: model.load_path}}


def _loader_judge(c: Candidate, models_dir: Path, v2, slm_llm):  # pragma: no cover - model
    from llama_cpp import LlamaGrammar

    grammars = {
        lang: LlamaGrammar.from_string(
            f'root ::= "{YES_NO[lang][0]}" | "{YES_NO[lang][1]}"', verbose=False
        )
        for lang in LANGS
    }
    state = {"probabilistic": True}

    def score(item: Item) -> tuple[float, bool]:
        user = (
            f"Question : {item.query}\nPassage : {item.text}"
            if item.task == "filter"
            else f"Passages :\n{item.text}\n\nAffirmation : {item.query}"
        )
        out = slm_llm.create_chat_completion(
            messages=[
                {"role": "system", "content": INSTRUCTIONS[item.task][item.lang]},
                {"role": "user", "content": user},
            ],
            grammar=grammars[item.lang],
            max_tokens=1,
            temperature=0.0,
            logprobs=True,
            top_logprobs=10,
        )
        choice = out["choices"][0]
        top = ((choice.get("logprobs") or {}).get("content") or [{}])[0].get("top_logprobs") or []
        p = yes_probability(top, item.lang)
        if p is None:  # no logprobs under the grammar: the label only
            state["probabilistic"] = False
            text = (choice["message"].get("content") or "").strip().lower()
            p = 1.0 if text.startswith(YES_NO[item.lang][0]) else 0.0
        return p, False

    return score, {"revisions": {}, "judge_state": state}


def child_local(
    candidate_id: str, models_dir: Path, slm: Path, langs: list[str]
) -> dict:  # pragma: no cover
    """Measures one local candidate in this fresh process, under the network guard."""
    v2 = _load_v2s6()
    s12 = v2.s12
    attempts, guard = s12._record_and_guard(allowed_hosts=[])
    _, stop_dog, dog = v2.start_ram_watchdog(attempts)
    c = BY_ID[candidate_id]
    out: dict = {"id": c.id, "guard": guard}
    try:
        import llama_cpp

        n_ctx = v2.slm_n_ctx(v2.wavestack_settings())
        slm_llm = llama_cpp.Llama(model_path=str(slm), n_ctx=n_ctx, verbose=False)
        slm_llm.create_completion("Bonjour", max_tokens=1)
        out["rss_with_slm_mb"] = s12._rss_mb()
        base = s12._baseline_rss()
        items = [i for i in build_all(langs).items if i.task in c.tasks]
        if c.id == "slm_juge":
            score, info = _loader_judge(c, models_dir, v2, slm_llm)
        elif c.id == "reranker_livre":
            score, info = _loader_reranker(c, models_dir, v2)
        elif c.id == "strands_decider_2b":
            score, info = _loader_strands(c, models_dir, v2)
        elif c.id == "anyjev":
            score, info = _loader_anyjev(c, slm)
        else:
            score, info = _loader_nli(c, models_dir, v2)
        state = info.pop("judge_state", None)
        out.update(info)

        def run(item: Item) -> dict:
            t0 = time.perf_counter()
            try:
                p, truncated = score(item)
                err = None
            except Exception as exc:  # noqa: BLE001 - an error is a finding
                p, truncated, err = None, False, repr(exc)[:200]
            return {
                "item_id": item.id,
                "candidate": c.id,
                "rep": 1,
                "prob": p,
                "truncated": truncated,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "date": date.today().isoformat(),
                "error": err,
            }

        records = [run(i) for i in items]
        # determinism: 20 items replayed; a gap > 1e-4 -> three more passes, "not deterministic"
        step = max(1, len(items) // DETERMINISM_ITEMS)
        sample = items[::step][:DETERMINISM_ITEMS]
        first = {r["item_id"]: r["prob"] for r in records}
        replay = [run(i) for i in sample]
        gap = max(
            (abs(r["prob"] - first[r["item_id"]]) for r in replay if r["prob"] is not None),
            default=0.0,
        )
        determinism = {
            "checked": len(sample),
            "max_gap": round(gap, 6),
            "deterministic": gap <= DETERMINISM_EPS,
        }
        for r in replay:
            r["rep"] = 2
        records += replay
        if gap > DETERMINISM_EPS:
            for rep in (3, 4):
                again = [run(i) for i in sample]
                for r in again:
                    r["rep"] = rep
                records += again
        out["determinism"] = determinism
        out["truncated_items"] = sum(1 for r in records if r["truncated"] and r["rep"] == 1)
        out["probabilistic"] = state["probabilistic"] if state else c.id != "reranker_livre"
        out.update(base)
        out.update(s12._loaded_rss())
        out["rss_added_mb"] = s12.added_rss_mb(
            base["rss_before_load_mb"],
            base["peak_before_load_mb"],
            out["rss_peak_mb"],
            (out["rss_loaded_mb"],),
        )
        names = tuple(re.split(r"[ =<>@\[]", pkg, maxsplit=1)[0] for pkg in c.packages)
        out["versions"] = v2._versions(names + ("llama-cpp-python",))
        out["records"] = records
        out["status"] = "measured"
    except Exception as exc:  # noqa: BLE001 - a candidate that does not run is "écarté"
        out.update(status="discarded", reason=repr(exc)[:300], attempts=attempts)
    finally:
        stop_dog.set()
    return out


def child_memory(slm: Path) -> dict:  # pragma: no cover - needs the real GGUF
    """Peak memory of the application's engine class at n_ctx 16,384: the `long_context`
    corpus (de, the longest) plus a question, then filled up to 16,384 - 256 tokens."""
    import threading

    import psutil

    v2 = _load_v2s6()
    s12 = v2.s12
    s12._record_and_guard(allowed_hosts=[])
    proc = psutil.Process()
    peaks = {"private": 0}
    stop = threading.Event()

    def watch() -> None:
        while not stop.is_set():
            info = proc.memory_info()
            private = getattr(info, "private", None) or getattr(info, "uss", None) or info.rss
            peaks["private"] = max(peaks["private"], private)
            stop.wait(0.25)

    threading.Thread(target=watch, daemon=True).start()
    from wavestack.models.engine import CancelToken, LlamaCppEngine
    from wavestack.rag.corpus import load_rag_content, read_documents

    docs = read_documents(load_rag_content("de"), "de")
    corpus = "\n\n".join(f"{d.title_text}\n{d.text}" for d in docs)
    engine = LlamaCppEngine(str(slm), MEMORY_N_CTX)
    question = "\n\nFrage: Wie lang muss ein Passwort mindestens sein?\nAntwort:"
    short_ids = engine.tokenize(corpus + question)
    target = MEMORY_N_CTX - MEMORY_MARGIN_TOKENS
    full = corpus
    while len(engine.tokenize(full + question)) < target:
        full += "\n\n" + corpus
    ids = engine.tokenize(full + question)[:target]
    for prompt in (short_ids[:target], ids):
        for _ in engine.complete(prompt, [], 16, CancelToken()):
            pass
    stop.set()
    kv = None
    try:
        from wavestack.models import probe

        per = probe.gguf_kv_bytes_per_token(str(slm))
        kv = round(per * MEMORY_N_CTX / (1 << 20)) if per else None
    except Exception:  # noqa: BLE001 - an estimate only
        pass
    return {
        "n_ctx": MEMORY_N_CTX,
        "prompt_tokens_short": min(len(short_ids), target),
        "prompt_tokens_full": len(ids),
        "peak_working_set_mb": s12._peak_rss_mb(),
        "peak_private_mb": peaks["private"] >> 20,
        "ram_total_mb": psutil.virtual_memory().total >> 20,
        "kv_estimate_mb": kv,
        "mmap": getattr(getattr(engine._llm, "model_params", None), "use_mmap", None),
        "n_batch": getattr(engine._llm, "n_batch", None),
    }


# --------------------------------------------------------------------------------------
# Synthetic fixture for CI (fake answers, never presented as measures).
# --------------------------------------------------------------------------------------

FIXTURE_DATE = "2000-01-01"


def fixture_items(all_items: list[Item]) -> list[Item]:
    fr = [i for i in all_items if i.lang == "fr"]

    def take(task: str, label: bool, n: int, kind: str | None = None) -> list[Item]:
        return [
            i
            for i in fr
            if i.task == task
            and i.label is label
            and i.group == "main"
            and (kind is None or i.kind == kind)
        ][:n]

    return (
        take("filter", True, 3)
        + take("filter", False, 3)
        + take("grounding", True, 2)
        + take("grounding", False, 2)
    )


def _synthetic(candidate_id: str, item: Item) -> float:
    h = int(hashlib.sha256(f"{candidate_id}|{item.id}".encode()).hexdigest()[:8], 16)
    u = (h % 1000) / 1000
    flip = (h >> 12) % 5 == 0  # one answer in five is wrong, so that the metrics are not trivial
    good = item.label != flip
    return round(0.55 + 0.4 * u if good else 0.05 + 0.4 * u, 2)


def make_fixture(out_dir: Path, all_items: list[Item]) -> None:
    """Writes ~10 synthetic cases in the layout of a results folder."""
    items = fixture_items(all_items)
    write_json(out_dir / "fixture.json", {"synthetic": True, "note": "fausses réponses de test"})
    write_json(
        out_dir / "run.json",
        {
            "item_ids": sorted(i.id for i in items),
            "candidates": ["typesafe/jev-1.14", "liquid/d1", "deberta_xsmall", "reranker_livre"],
            "commit": "fixture",
            "machine": None,
        },
    )
    write_json(
        out_dir / "probes.json",
        {
            "typesafe/jev-1.14": {"status": "ok"},
            "liquid/d1": {"status": "unknown_model", "http": 404},
        },
    )
    budget = Budget()
    for _ in range(2):
        for _ in items:
            budget.add("typesafe/jev-1.14", 0.00006)
    write_json(
        out_dir / "run_state.json", {"incomplete": {}, "stopped": None, "budget": budget.snapshot()}
    )
    jev = "typesafe/jev-1.14"
    for rep in (1, 2):
        for i in items:
            append_record(
                recorded_path(out_dir, jev),
                {
                    "item_id": i.id,
                    "candidate": jev,
                    "rep": rep,
                    "request_sha256": request_sha256(jev, i),
                    "status": 200,
                    "model_returned": "synthetic-fixture-20000101",
                    "noul": _synthetic(jev, i),
                    "input_tokens": 300,
                    "output_tokens": 4,
                    "cost": 0.00006,
                    "calls": 1,
                    "latency_ms": 250 + rep,
                    "date": FIXTURE_DATE,
                    "error": None,
                },
            )
    for cid in ("deberta_xsmall", "reranker_livre"):
        task_items = [i for i in items if i.task in BY_ID[cid].tasks]
        for i in task_items:
            append_record(
                recorded_path(out_dir, cid),
                {
                    "item_id": i.id,
                    "candidate": cid,
                    "rep": 1,
                    "prob": _synthetic(cid, i),
                    "truncated": False,
                    "latency_ms": 120,
                    "date": FIXTURE_DATE,
                    "error": None,
                },
            )
        write_json(
            out_dir / "local" / f"{slug(cid)}.json",
            {
                "status": "measured",
                "rss_with_slm_mb": 2300,
                "rss_added_mb": 90,
                "probabilistic": True,
                "versions": {"onnxruntime": "synthetic"},
                "revisions": {},
                "determinism": {"checked": 5, "max_gap": 0.0, "deterministic": True},
                "truncated_items": 0,
            },
        )
    write_json(
        out_dir / "memory.json",
        {
            "n_ctx": MEMORY_N_CTX,
            "prompt_tokens_short": 11000,
            "prompt_tokens_full": 16128,
            "peak_working_set_mb": 2900,
            "peak_private_mb": 2800,
            "ram_total_mb": 32000,
            "kv_estimate_mb": 700,
            "mmap": True,
            "n_batch": 512,
        },
    )


# --------------------------------------------------------------------------------------
# Command line.
# --------------------------------------------------------------------------------------


def _default_slm() -> str | None:
    """The application's default SLM in its models folder, when present."""
    from wavestack import config

    path = config.models_dir() / config.DEFAULT_MODEL_FILE
    return str(path) if path.is_file() else None


def _need_idle(args) -> None:
    if not args.confirm_idle:
        sys.exit("Lancement réel refusé : passez --confirm-idle quand aucun autre agent ne tourne.")


def _new_results_dir(args) -> Path:
    return (
        Path(args.results_dir)
        if args.results_dir
        else RESULTS_DIR / f"{date.today().isoformat()}-v12s2"
    )


def _init_run(
    results_dir: Path, items: list[Item], candidates: list[str], langs: list[str]
) -> None:
    path = results_dir / "run.json"
    run = json.loads(path.read_text("utf-8")) if path.exists() else {}
    ids = sorted(set(run.get("item_ids", [])) | {i.id for i in items})
    cands = list(dict.fromkeys([*run.get("candidates", []), *candidates]))
    v2 = _load_v2s6()
    run.update(
        item_ids=ids,
        candidates=cands,
        langs=langs,
        commit=v2._repo_commit(),
        machine={
            k: v
            for k, v in v2.machine_info().items()
            if k in ("platform", "cpu_count", "ram_total_mb")
        },
    )
    write_json(path, run)


def cmd_list(_args) -> int:
    built = build_all()
    for t in ("filter", "grounding"):
        for lang in LANGS:
            n = sum(1 for i in built.items if i.task == t and i.lang == lang)
            print(f"{t} {lang}: {n}")
    print(f"ancres à cheval sur deux chunks (écartées) : {len(built.dropped)}")
    for c in CANDIDATES:
        print(f"{c.kind:6} {c.id}  {c.office or ''}")
    return 0


def cmd_dry_run(args) -> int:
    results_dir = Path(args.results_dir) if args.results_dir else latest_results_dir()
    built = build_all()
    report, agg = dry_run(results_dir, built.items)
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")
    if results_dir and (results_dir / "run.json").exists():
        write_json(results_dir / "aggregates.json", agg)
    print(f"rapport écrit : {REPORT_PATH.relative_to(ROOT)}")
    return 0


def cmd_online(args) -> int:  # pragma: no cover - real run
    _need_idle(args)
    key = read_key()
    if not key:
        sys.exit(f"Clé absente : définissez {KEY_ENV} (variable ou registre utilisateur).")
    models = args.only or [c.id for c in ONLINE]
    langs = args.langs.split(",")
    items = build_all(langs).items
    results_dir = _new_results_dir(args)
    _init_run(results_dir, items, models, langs)
    v2 = _load_v2s6()
    v2.s12._record_and_guard(allowed_hosts=list(ALLOWED_HOSTS), strip_proxy=False)
    client = DecisionClient(key)
    try:
        state = run_online(items, models, results_dir, client, Budget())
    finally:
        client.close()
    write_json(results_dir / "run_state.json", state)
    print(json.dumps(state["budget"], ensure_ascii=False))
    return 0 if not state["stopped"] else 3


def cmd_local(args) -> int:  # pragma: no cover - real run
    _need_idle(args)
    v2 = _load_v2s6()
    langs = args.langs.split(",")
    results_dir = _new_results_dir(args)
    ids = args.only or [c.id for c in LOCAL]
    _init_run(results_dir, build_all(langs).items, ids, langs)
    slm, why = v2.resolve_slm(args.slm or _default_slm(), v2._slm_search_dir())
    if slm is None:
        sys.exit(why)
    for cid in ids:
        c = BY_ID[cid]
        meta_path = results_dir / "local" / f"{slug(cid)}.json"
        if c.office:
            write_json(meta_path, {"status": "discarded", "reason": c.office_reason})
            continue
        if meta_path.exists():
            continue  # resumable: a candidate already measured is not run again
        cmd = ["uv", "run"]
        for p in (*c.packages, "psutil"):
            cmd += ["--with", p]
        cmd += [
            "python",
            "-I" if False else "-u",
            str(HERE / Path(SCRIPT).name),
            "child-local",
            cid,
            "--models-dir",
            args.models_dir,
            "--slm",
            str(slm),
            "--langs",
            args.langs,
        ]
        if args.download and v2_candidate(c, v2) is not None:
            got = v2.download_candidate(v2_candidate(c, v2), Path(args.models_dir))
            if got["errors"]:
                print(f"{cid}: téléchargement en échec {got['errors']}")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=7200, cwd=ROOT)
        last = next((ln for ln in reversed(proc.stdout.splitlines()) if ln.startswith("{")), "{}")
        out = json.loads(last)
        for r in out.pop("records", []):
            append_record(recorded_path(results_dir, cid), r)
        write_json(meta_path, out)
        print(f"{cid}: {out.get('status', 'écarté')}")
    return 0


def cmd_memory(args) -> int:  # pragma: no cover - real run
    _need_idle(args)
    v2 = _load_v2s6()
    slm, why = v2.resolve_slm(args.slm or _default_slm(), v2._slm_search_dir())
    if slm is None:
        sys.exit(why)
    results_dir = _new_results_dir(args)
    proc = subprocess.run(
        [sys.executable, str(HERE / Path(SCRIPT).name), "child-memory", "--slm", str(slm)],
        capture_output=True,
        text=True,
        timeout=3600,
        cwd=ROOT,
    )
    last = next((ln for ln in reversed(proc.stdout.splitlines()) if ln.startswith("{")), None)
    if last is None:
        sys.exit("mesure mémoire en échec : " + proc.stderr[-300:])
    mem = json.loads(last)
    write_json(results_dir / "memory.json", mem)
    block = memlog_block(mem)
    print(block)
    if args.append_memlog:
        with MEMLOG_PATH.open("a", encoding="utf-8", newline="\n") as f:
            f.write(block + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    mf = sub.add_parser("make-fixture")
    mf.add_argument("out_dir")
    d = sub.add_parser("dry-run")
    d.add_argument("--results-dir")
    for name in ("online", "local", "memory", "child-local", "child-memory"):
        s = sub.add_parser(name)
        s.add_argument("--confirm-idle", action="store_true")
        s.add_argument("--results-dir")
        s.add_argument("--langs", default=",".join(LANGS))
        s.add_argument("--only", nargs="*")
        s.add_argument("--slm")
        s.add_argument("--models-dir", default=str(Path.home() / ".cache" / "wavestack-bench"))
        s.add_argument("--download", action="store_true")
        s.add_argument("--append-memlog", action="store_true")
        if name == "child-local":
            s.add_argument("candidate")
    args = p.parse_args(argv)
    if args.cmd == "make-fixture":
        make_fixture(Path(args.out_dir), build_all().items)
        return 0
    if args.cmd == "child-local":  # pragma: no cover
        out = child_local(
            args.candidate, Path(args.models_dir), Path(args.slm), args.langs.split(",")
        )
        print(json.dumps(out, ensure_ascii=False))
        return 0
    if args.cmd == "child-memory":  # pragma: no cover
        print(json.dumps(child_memory(Path(args.slm)), ensure_ascii=False))
        return 0
    return {
        "list": cmd_list,
        "dry-run": cmd_dry_run,
        "online": cmd_online,
        "local": cmd_local,
        "memory": cmd_memory,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
