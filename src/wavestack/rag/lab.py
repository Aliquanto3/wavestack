"""The RAG workshop (story 30, CAP-45): a RAG chain drawn and run apart from the RAG brick.

A chain (`Pipeline`) is an ordered list of stages (`Stage`: a kind, an option, its settings).
`LabRun` runs one chain on one question (lot 5c-1: the A/B comparison is gone), with what it
is given: the models lent by the brick or loaded for the run (`Lent`), the brick's index, a
stop test and an emitter. It knows no session. Every figure the page shows is computed here
(AD-1): ranks, scores, sizes, durations, the context built. The workshop is a sandbox: it
only reads the brick's index and never changes the brick's state.
"""

from __future__ import annotations

import gc
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import time
import unicodedata
from array import array
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from wavestack import config, greenops
from wavestack.compression.port import Compressor
from wavestack.greenops import Measure, Probe, StageCost
from wavestack.messages import KeyedError, Lazy, Message, join, msg, number, render
from wavestack.models.embedding import Embedder
from wavestack.models.load_registry import LoadRegistry
from wavestack.models.reranker import RerankCancelled, Reranker
from wavestack.rag import agent_tools, pageindex, workcopy
from wavestack.rag import contexts as rag_contexts
from wavestack.rag import graph as rag_graph
from wavestack.rag import index as rag_index
from wavestack.rag.corpus import (
    Chunk,
    DocText,
    RagContent,
    chunk_corpus,
    chunk_documents,
    chunk_parent_child,
    chunk_semantic,
)
from wavestack.rag.index import exception_text
from wavestack.rag.retriever import SqliteVecRetriever

# The kinds of stage, in the order a chain draws them.
KINDS = (
    "chunking",
    "embedding",
    "vector_store",
    "query",
    "vector_search",
    "lexical_search",
    "fusion",
    "rerank",
    "context",
    "generation",
)
# Increment 4: the retrieval segment, between the vector store and the context, in any order
# (the chain's other stages are fixed); a stage of it is added before the context.
# V1.2 story 5 (CAP-3): the query understanding opens the segment, before the searches.
RETRIEVAL = ("query", "vector_search", "lexical_search", "fusion", "rerank")
SEARCHES = ("vector_search", "lexical_search")
FIXED_HEAD = ("chunking", "embedding", "vector_store")
FIXED_TAIL = ("context", "generation")
BM25_K1, BM25_B = 1.5, 0.75
RRF_K = 60
_WORD = re.compile(r"\w+")
# Each kind's options, the shipped one first.
OPTIONS: dict[str, tuple[str, ...]] = {
    # V1.2 story 6 (CAP-4): by the meaning of the sentences, small children indexed for a
    # large parent returned, a short context added to each chunk.
    "chunking": ("paragraphs", "semantic", "parent_child", "contextual"),
    "embedding": ("declared", "fastembed"),
    "vector_store": ("sqlite_vec", "memory", "faiss", "lancedb"),
    # V1.2 story 5 (CAP-3): what is searched is no longer the question as typed. Each option
    # asks the workshop's active model for the queries to search.
    "query": ("rewrite", "decompose", "follow_up", "hyde"),
    "vector_search": ("cosine",),
    "lexical_search": ("bm25",),
    "fusion": ("rrf",),
    "rerank": ("declared",),
    # V1.2 story 7 (CAP-5): cumulative options, each adds to the one before: the context fits a
    # budget of tokens, then the passages are ordered « extremities first », then compressed.
    # V1.2 story 10: the architectures without an index read the whole corpus instead, in the
    # prompt at each question (`full_corpus`) or once in the model's cache (`cached_corpus`).
    # V1.2 story 11 (CAP-7): searching without vectors, the model searches by itself: with
    # tools on the corpus (`agent_loop`), or going down a tree of sections (`section_tree`).
    "context": (
        "excerpts",
        "budget",
        "order",
        "compress",
        "full_corpus",
        "cached_corpus",
        "agent_loop",
        "section_tree",
        # V1.2 story 13 (CAP-7): GraphRAG, a knowledge graph's entities, relations, communities.
        "graph_search",
    ),
    # Lot 5c-3: the workshop's active model generates (the shipped one), or nothing is sent.
    "generation": ("active", "not_run"),
}
# The settings of an option, by name.
PARAMS: dict[tuple[str, str], tuple[str, ...]] = {
    ("chunking", "paragraphs"): ("chunk_max_chars",),
    ("chunking", "semantic"): ("chunk_max_chars",),
    ("chunking", "parent_child"): ("chunk_max_chars",),
    ("chunking", "contextual"): ("chunk_max_chars",),
    ("vector_search", "cosine"): ("candidates",),
    ("lexical_search", "bm25"): ("candidates",),
    ("context", "excerpts"): ("top_k",),
    ("context", "budget"): ("top_k", "budget_tokens"),
    ("context", "order"): ("top_k", "budget_tokens"),
    ("context", "compress"): ("top_k", "budget_tokens"),
}
BOUNDS: dict[str, tuple[int, int]] = {
    "chunk_max_chars": (200, 1500),
    "candidates": (1, 20),
    "top_k": (1, 20),
    "budget_tokens": (100, 4000),
}
# V1.2 story 7: the value of a setting the shipped chain does not carry (`param()` reads it
# before falling back on the lower bound); three excerpts of the shipped corpus take about 505
# estimated tokens, so the third one is cut at this default.
PARAM_DEFAULTS: dict[str, int] = {"budget_tokens": 450}
# V1.2 story 5: the query understanding's bounds (characters of a query, queries of a
# decomposition, previous questions read by `follow_up`, tokens the model may write).
QUERY_MAX_CHARS = 300
HYDE_MAX_CHARS = 800
SUBQUERIES_MAX = 4
HISTORY_MAX = 3
QUERY_RESERVE = 256
# The kinds whose every option has a component sheet (CAP-17) in `rag_lab.yaml`; each story
# that adds options adds its kind here. Story 19b: every family of `OPTIONS` (end of CAP-17).
SHEETED_KINDS = (
    "query",
    "chunking",
    "embedding",
    "vector_store",
    "vector_search",
    "lexical_search",
    "fusion",
    "rerank",
    "context",
    "generation",
)
# V1.2 story 6 (CAP-4): constants, not settings. `parent_child`: the characters of a child (the
# parent is a `paragraphs` chunk); `semantic`: a chunk ends where the distance between two
# neighbouring sentences passes this percentile of the corpus's; `contextual`: the tokens a
# rebuilt context may take; the chunks the focus lists, and the characters of each it shows.
CHILD_MAX_CHARS = 300
SEMANTIC_PERCENTILE = 80
CONTEXT_MAX_TOKENS = 128
FOCUS_CHUNKS_MAX = 20
FOCUS_CHUNK_CHARS = 300
# V1.2 story 7 (CAP-5): the mark of a passage the budget cut, and where it may be cut.
CUT_MARK = "[…]"
_SENTENCE_END = re.compile(r"[.!?\u2026\u00bb](?=\s)")
QUESTION_MAX = 500  # the characters of a question the workshop accepts
# V1.2 story 10: the Context options that read the whole corpus, without any search, and the
# effective window they need (the largest of `config.WINDOW_CHOICES`).
CORPUS_OPTIONS = ("full_corpus", "cached_corpus")
NO_INDEX_WINDOW = 16384
# V1.2 story 11: the Context options that have no retrieval segment (they search by themselves
# or read everything), and the bounds of the agentic search and of PageIndex's descent
# (constants, no setting: the loop's rounds, the tokens a model's action may write).
SEARCHLESS_OPTIONS = (*CORPUS_OPTIONS, "agent_loop", "section_tree", "graph_search")
# V1.2 story 13: GraphRAG's two modes (a choice of the page, `graph_mode` of the request).
GRAPH_MODES = ("local", "global")
MAX_AGENT_ROUNDS = 6
UNREADABLE_MAX = 2  # unreadable answers in a row that stop the loop
AGENT_RESERVE = 128
ACTION_ARG_MAX_CHARS = agent_tools.ACTION_ARG_MAX_CHARS
AGENT_RESULT_MAX_TOKENS = agent_tools.AGENT_RESULT_MAX_TOKENS
PAGEINDEX_BREADTH = pageindex.PAGEINDEX_BREADTH
TREE_SUMMARY_MAX_CHARS = pageindex.TREE_SUMMARY_MAX_CHARS
TREE_SOURCE_MAX_TOKENS = 1500  # what a summary's rewrite reads of a node's text
GRAPH_RESERVE = 256  # V1.2 story 13: the tokens a graph's call may write (lines, points)
PREVIEW_CHARS = 200  # the characters of a tool's result or a model's answer the event keeps
STATUSES = ("ok", "error", "skipped", "cancelled", "not_run")
EMBED_BATCH = 8  # passages embedded at a time: « Arrêter » and the progress between batches
PROGRESS_INTERVAL_S = 0.1  # `rag_lab_stage_progress` at most ten times a second

_MIB = 1024**2

# ---------- lot 5a: the sequence the page draws (vues-atelier-rag.md §2 to §4) ----------

# The two times of a RAG, its sequence's two bands: the indexing, then each question.
PHASES = ("build", "run")
# The architecture's groups, and their components in the order drawn: the group, an icon,
# and the kind of the stage whose option names it (the tile's subtitle), if any.
GROUPS = ("data", "models", "exchange")
COMPONENTS: dict[str, tuple[str, str, str | None]] = {
    "documents": ("data", "📄", None),
    "chunks": ("data", "🧩", None),
    "vector_store": ("data", "🗄️", "vector_store"),
    # B2 (2026-10-05): BM25's inverted index, built at BUILD when the chain has BM25.
    "lexical_index": ("data", "📇", None),
    "embedding_model": ("models", "🔢", "embedding"),
    "reranker": ("models", "⚖️", "rerank"),
    "llm": ("models", "🧠", "generation"),
    "question": ("exchange", "💬", None),
    "augmented_prompt": ("exchange", "📝", None),
    "answer": ("exchange", "💡", None),
    # V1.2 story 10: the prefix the CAG keeps in the model's memory.
    "model_cache": ("models", "🗃️", None),
    # V1.2 story 11: the agent's tools on the corpus files, and PageIndex's tree of sections.
    "file_tools": ("models", "🛠️", None),
    "section_tree": ("data", "🌳", None),
    # V1.2 story 13: GraphRAG's knowledge graph (entities, relations, communities).
    "knowledge_graph": ("data", "🕸️", None),
}


@dataclass(frozen=True)
class SequenceStep:
    """A line of the sequence. `stage`: the kind of the chain's stage it shows (its status,
    its figures; the line is drawn only when the chain has it, `None`: always); `own`: the
    line is that stage's own (it carries its editor), else it reads it (Documents reads the
    Chunking's input, the question's Embedding is the Embedding stage's second half). The
    components it reads, writes and calls. B2 (2026-10-05): `part`, the part of its stage the
    line shows with its own events, figures and duration (BM25's index, built at BUILD)."""

    phase: str
    stage: str | None
    own: bool = True
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    calls: tuple[str, ...] = ()
    part: str | None = None
    # V1.2 story 10: the line is drawn only when its stage's option is one of `options`
    # (empty: any), and never when the chain's Context is one of `hidden_with`.
    options: tuple[str, ...] = ()
    hidden_with: tuple[str, ...] = ()


# In the order drawn: BUILD, then RUN (whose retrieval segment follows the chain's order).
STEPS: dict[str, SequenceStep] = {
    "documents": SequenceStep("build", "chunking", own=False, reads=("documents",)),
    "chunking": SequenceStep("build", "chunking", reads=("documents",), writes=("chunks",)),
    "embed_passages": SequenceStep(
        "build", "embedding", reads=("chunks",), calls=("embedding_model",)
    ),
    "vector_store": SequenceStep(
        "build", "vector_store", reads=("embedding_model",), writes=("vector_store",)
    ),
    # B2: BM25's first part, its inverted index, built once the vectors are stored.
    "lexical_index": SequenceStep(
        "build",
        "lexical_search",
        own=False,
        reads=("chunks",),
        writes=("lexical_index",),
        part="index",
    ),
    "question": SequenceStep("run", None, own=False, reads=("question",)),
    "embed_query": SequenceStep(
        "run",
        "embedding",
        own=False,
        reads=("question",),
        calls=("embedding_model",),
        # V1.2 stories 10, 11: no vector search, no question embedded
        hidden_with=SEARCHLESS_OPTIONS,
    ),
    # V1.2 story 5: the queries the searches will run (the question, rewritten or split).
    "query": SequenceStep("run", "query", reads=("question",), calls=("llm",)),
    "vector_search": SequenceStep("run", "vector_search", reads=("vector_store",)),
    "lexical_search": SequenceStep("run", "lexical_search", reads=("lexical_index", "question")),
    "fusion": SequenceStep("run", "fusion"),
    "rerank": SequenceStep("run", "rerank", reads=("question",), calls=("reranker",)),
    "context": SequenceStep(
        "run", "context", reads=("chunks", "question"), writes=("augmented_prompt",)
    ),
    "generation": SequenceStep(
        "run", "generation", reads=("augmented_prompt",), writes=("answer",), calls=("llm",)
    ),
    # V1.2 story 10: the CAG's prefix (the instruction and the whole corpus), evaluated once
    # into the model's memory, drawn only for `cached_corpus`.
    "cache_prefix": SequenceStep(
        "build",
        "context",
        own=False,
        reads=("documents",),
        writes=("model_cache",),
        calls=("llm",),
        part="prefix",
        options=("cached_corpus",),
    ),
    # V1.2 story 11: PageIndex's tree, built once from the documents (its cost: `build`), then
    # gone down at each question; the agent's calls, each a model's action on the files.
    "tree_build": SequenceStep(
        "build",
        "context",
        own=False,
        reads=("documents",),
        writes=("section_tree",),
        options=("section_tree",),
    ),
    "agent_calls": SequenceStep(
        "run",
        "context",
        own=False,
        reads=("documents", "question"),
        calls=("llm", "file_tools"),
        options=("agent_loop",),
    ),
    "tree_levels": SequenceStep(
        "run",
        "context",
        own=False,
        reads=("section_tree", "question"),
        calls=("llm",),
        options=("section_tree",),
    ),
    # V1.2 story 13: GraphRAG's graph, built once from the documents (its cost: `build`), then
    # queried at each question (the question's entities, or the communities' « map »).
    "graph_build": SequenceStep(
        "build",
        "context",
        own=False,
        reads=("documents",),
        writes=("knowledge_graph",),
        options=("graph_search",),
    ),
    "graph_query": SequenceStep(
        "run",
        "context",
        own=False,
        reads=("knowledge_graph", "question"),
        calls=("llm",),
        options=("graph_search",),
    ),
}

# ---------- lot 5b: the ready-made architectures (vues-atelier-rag.md §8) ----------

# Each preset's retrieval segment, (kind, option) in order: applying one replaces the chain's
# segment only, its stages at their shipped settings. No « hybride + reranking »: it is
# composed by hand.
PRESETS: dict[str, tuple[tuple[str, str], ...]] = {
    "dense": (("vector_search", "cosine"),),
    "hybrid": (("vector_search", "cosine"), ("lexical_search", "bm25"), ("fusion", "rrf")),
    "rerank": (("vector_search", "cosine"), ("rerank", "declared")),  # the shipped chain's
    # V1.2 story 10: no search at all, the Context reads the whole corpus (`PRESET_CONTEXT`).
    "long_context": (),
    "cag": (),
    # V1.2 story 11: no search segment either, the Context searches by itself.
    "agentic": (),
    "pageindex": (),
    "graphrag": (),  # V1.2 story 13
}
# V1.2 story 10: the Context option a preset sets (the others keep the chain's Context).
PRESET_CONTEXT: dict[str, str] = {
    "long_context": "full_corpus",
    "cag": "cached_corpus",
    "agentic": "agent_loop",  # V1.2 story 11
    "pageindex": "section_tree",
    "graphrag": "graph_search",  # V1.2 story 13
}
# V1.2 story 10 (vues.md): the presets' families, drawn in this order; each preset is in one.
# V1.2 story 11: « Structure » between « Recherche » and « Sans index » (the mock-up's order).
PRESET_FAMILIES: dict[str, tuple[str, ...]] = {
    "search": ("dense", "hybrid", "rerank"),
    "structure": ("pageindex", "graphrag"),  # V1.2 story 13: GraphRAG after PageIndex
    "no_index": ("long_context", "cag", "agentic"),
}


# ---------- the page's texts (content/rag_lab.yaml, AD-19) ----------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StageText(_Strict):
    label_text: str = Field(min_length=1)
    explain_text: str = Field(min_length=1)


class OptionText(_Strict):
    label_text: str = Field(min_length=1)


class ParamText(_Strict):
    label_text: str = Field(min_length=1)
    unit_text: str = ""


class StatusTexts(_Strict):
    waiting_text: str
    running_text: str
    ok_text: str
    error_text: str
    skipped_text: str
    cancelled_text: str
    not_run_text: str


class ColumnTexts(_Strict):
    rank_text: str
    before_text: str
    document_text: str
    score_text: str


class StepText(_Strict):
    """A line of the sequence: its technical name (English, the same in every language), its
    action, its explanation (else its stage's) and an optional note."""

    label_text: str = Field(min_length=1)
    action_text: str = Field(min_length=1)
    explain_text: str | None = Field(default=None, min_length=1)
    note_text: str | None = Field(default=None, min_length=1)


class ComponentText(_Strict):
    """A tile of the architecture: its name, and its subtitle when no option names it."""

    label_text: str = Field(min_length=1)
    note_text: str = Field(min_length=1)


class GroupText(_Strict):
    label_text: str = Field(min_length=1)


class PresetText(_Strict):
    """A ready-made architecture: its button's name and its explanation (the tooltip)."""

    label_text: str = Field(min_length=1)
    explain_text: str = Field(min_length=1)


class PresetFamilyText(_Strict):
    """V1.2 story 10: a family of ready-made architectures (« Recherche », « Sans index »)."""

    label_text: str = Field(min_length=1)


class PhaseText(_Strict):
    """A band of the sequence: « BUILD · Indexing », « une fois pour toutes… »."""

    tag_text: str = Field(min_length=1)
    label_text: str = Field(min_length=1)
    help_text: str = Field(min_length=1)


class CostTexts(_Strict):
    """V1.2 story 3 (CAP-8): the page's texts of the costs in three times and the work copy."""

    title_text: str = Field(min_length=1)
    hint_text: str = Field(min_length=1)
    perimeters_text: str = Field(min_length=1)
    build_text: str = Field(min_length=1)
    build_help_text: str = Field(min_length=1)
    update_text: str = Field(min_length=1)
    update_help_text: str = Field(min_length=1)
    query_text: str = Field(min_length=1)
    query_help_text: str = Field(min_length=1)
    tokens_text: str = Field(min_length=1)
    duration_text: str = Field(min_length=1)
    usd_text: str = Field(min_length=1)
    gco2e_text: str = Field(min_length=1)
    energy_text: str = Field(min_length=1)
    measured_at_build_text: str = Field(min_length=1)
    not_measured_text: str = Field(min_length=1)
    partial_text: str = Field(min_length=1)
    local_free_text: str = Field(min_length=1)
    build_empty_text: str = Field(min_length=1)
    query_empty_text: str = Field(min_length=1)
    update_empty_text: str = Field(min_length=1)
    update_running_text: str = Field(min_length=1)
    copy_title_text: str = Field(min_length=1)
    copy_help_text: str = Field(min_length=1)
    copy_clean_text: str = Field(min_length=1)
    copy_changed_text: str = Field(min_length=1)
    add_doc_text: str = Field(min_length=1)
    modify_doc_text: str = Field(min_length=1)
    delete_doc_text: str = Field(min_length=1)
    reset_copy_text: str = Field(min_length=1)
    doc_label_text: str = Field(min_length=1)
    id_label_text: str = Field(min_length=1)
    doc_title_label_text: str = Field(min_length=1)
    doc_body_label_text: str = Field(min_length=1)
    modify_hint_text: str = Field(min_length=1)
    apply_text: str = Field(min_length=1)
    cancel_text: str = Field(min_length=1)
    update_of_text: str = Field(min_length=1)


class TabTexts(_Strict):
    """V1.2 story 4 (vues.md): the view tabs of the page."""

    label_text: str = Field(min_length=1)
    build_text: str = Field(min_length=1)
    compare_text: str = Field(min_length=1)
    evaluate_text: str = Field(min_length=1)
    attack_text: str = Field(min_length=1)
    sheets_text: str = Field(min_length=1)
    soon_text: str = Field(min_length=1)  # `{name}`: the tab, not yet built


class SourceText(_Strict):
    label_text: str = Field(min_length=1)
    url: str = Field(pattern=r"^https://")


class SheetText(_Strict):
    """V1.2 story 5 (CAP-17): the component sheet of an option, five blocks: what it is for,
    when to use or avoid it, what it costs, what the literature says (with its sources, at
    least one) and what the bench measured (empty while nothing is published)."""

    purpose_text: str = Field(min_length=1)
    when_text: str = Field(min_length=1)
    cost_text: str = Field(min_length=1)
    literature_text: str = Field(min_length=1)
    bench_text: str = ""
    sources: list[SourceText] = Field(min_length=1)


class QuestionTypeTexts(_Strict):
    factual_text: str = Field(min_length=1)
    multi_hop_text: str = Field(min_length=1)
    global_text: str = Field(min_length=1)
    no_answer_text: str = Field(min_length=1)
    temporal_text: str = Field(min_length=1)
    cross_lingual_text: str = Field(min_length=1)
    follow_up_text: str = Field(min_length=1)


class PreparedTexts(_Strict):
    """V1.2 story 4 (CAP-2): the prepared-question selector."""

    label_text: str = Field(min_length=1)
    free_text: str = Field(min_length=1)
    types: QuestionTypeTexts


class CompareTexts(_Strict):
    """V1.2 story 4 (CAP-9): the pin and the comparison of two runs."""

    title_text: str = Field(min_length=1)
    hint_text: str = Field(min_length=1)
    pin_text: str = Field(min_length=1)
    pin_wait_text: str = Field(min_length=1)
    unpin_text: str = Field(min_length=1)
    pinned_status_text: str = Field(min_length=1)  # `{question}`
    pinned_text: str = Field(min_length=1)
    current_text: str = Field(min_length=1)
    empty_pin_text: str = Field(min_length=1)
    empty_current_text: str = Field(min_length=1)
    need_pin_text: str = Field(min_length=1)
    need_current_text: str = Field(min_length=1)
    other_question_text: str = Field(min_length=1)
    at_text: str = Field(min_length=1)  # `{time}`
    search_text: str = Field(min_length=1)
    context_text: str = Field(min_length=1)
    answer_text: str = Field(min_length=1)
    costs_text: str = Field(min_length=1)
    prompt_text: str = Field(min_length=1)
    no_answer_text: str = Field(min_length=1)
    none_text: str = Field(min_length=1)
    same_text: str = Field(min_length=1)
    differs_text: str = Field(min_length=1)
    lost_text: str = Field(min_length=1)
    added_text: str = Field(min_length=1)


class RagLabContent(_Strict):
    """`content/rag_lab.yaml`: every French text of the page, a text per kind of stage, per
    option and per setting."""

    title_text: str = Field(min_length=1)
    intro_text: str = Field(min_length=1)
    busy_text: str = Field(min_length=1)
    chain_title_text: str = Field(min_length=1)
    chain_help_text: str = Field(min_length=1)
    question_label_text: str = Field(min_length=1)
    question_placeholder_text: str = Field(min_length=1)
    default_question_text: str = Field(min_length=1, max_length=QUESTION_MAX)
    run_text: str = Field(min_length=1)
    stop_text: str = Field(min_length=1)
    running_text: str = Field(min_length=1)
    # Lot 5a: the three views (sequence, architecture, focus) and the two modes.
    modes_label_text: str = Field(min_length=1)
    compose_text: str = Field(min_length=1)
    play_text: str = Field(min_length=1)
    sequence_title_text: str = Field(min_length=1)
    architecture_title_text: str = Field(min_length=1)
    focus_title_text: str = Field(min_length=1)
    focus_empty_text: str = Field(min_length=1)
    focus_no_run_text: str = Field(min_length=1)
    focus_position_text: str = Field(min_length=1)
    uses_title_text: str = Field(min_length=1)
    reads_text: str = Field(min_length=1)
    writes_text: str = Field(min_length=1)
    calls_text: str = Field(min_length=1)
    same_model_text: str = Field(min_length=1)
    question_received_text: str = Field(min_length=1)
    # Composer, the last run being the edited chain's: its figures are in « Dérouler ».
    focus_play_hint_text: str = Field(min_length=1)
    # Lot 5b: the row of the ready-made architectures (Composer).
    presets_title_text: str = Field(min_length=1)
    # Lot 5a-2: the stepper's legend in « Dérouler » (guided tour, live, ended, replay).
    legend_tour_text: str = Field(min_length=1)
    legend_live_text: str = Field(min_length=1)
    legend_done_text: str = Field(min_length=1)
    legend_replay_text: str = Field(min_length=1)
    details_text: str = Field(min_length=1)
    results_empty_text: str = Field(min_length=1)
    generation_not_run_text: str = Field(min_length=1)
    # Lot 5c-3: the generation run by the active model: its progress in tokens (« {done} /
    # {total} tokens »), the prompt rendered (folded), the answer, before its first token, and
    # while the model reasons before answering.
    progress_tokens_text: str = Field(min_length=1)
    prompt_sent_text: str = Field(min_length=1)
    answer_title_text: str = Field(min_length=1)
    answer_waiting_text: str = Field(min_length=1)
    answer_reasoning_text: str = Field(min_length=1)
    # Lot 5c-4: « Télécharger (≈ {size_mb} Mo) » for a model missing, in its stage (Composer),
    # « Arrêter » while it downloads, and the line once it is there.
    download_label_text: str = Field(min_length=1)
    download_stop_text: str = Field(min_length=1)
    download_done_text: str = Field(min_length=1)
    borrowed_text: str = Field(min_length=1)
    loaded_text: str = Field(min_length=1)
    input_text: str = Field(min_length=1)
    output_text: str = Field(min_length=1)
    facts_text: str = Field(min_length=1)
    duration_text: str = Field(min_length=1)
    memory_text: str = Field(min_length=1)
    last_run_text: str = Field(min_length=1)
    add_text: str = Field(min_length=1)
    add_button_text: str = Field(min_length=1)
    move_before_text: str = Field(min_length=1)
    move_after_text: str = Field(min_length=1)
    remove_text: str = Field(min_length=1)
    reset_chain_text: str = Field(min_length=1)
    unavailable_text: str = Field(min_length=1)
    queries_text: str = Field(min_length=1)  # V1.2 story 5: « Requêtes produites »
    costs: CostTexts
    tabs: TabTexts
    prepared: PreparedTexts
    compare: CompareTexts
    status: StatusTexts
    columns: ColumnTexts
    stages: dict[str, StageText]
    options: dict[str, dict[str, OptionText]]
    params: dict[str, ParamText]
    steps: dict[str, StepText]
    components: dict[str, ComponentText]
    groups: dict[str, GroupText]
    phases: dict[str, PhaseText]
    presets: dict[str, PresetText]
    preset_families: dict[str, PresetFamilyText]  # V1.2 story 10
    # V1.2 story 5 (CAP-17): « kind.option » -> its sheet.
    sheets: dict[str, SheetText] = {}

    @model_validator(mode="after")
    def _every_kind_option_and_setting(self) -> RagLabContent:
        """A text for each kind, option, setting, step, component, group, phase and preset
        the workshop offers, and no other."""
        if set(self.stages) != set(KINDS):
            raise ValueError(f"stages : il faut exactement {', '.join(KINDS)}")
        for name, keys in (
            ("steps", STEPS),
            ("components", COMPONENTS),
            ("groups", GROUPS),
            ("phases", PHASES),
            ("presets", PRESETS),
            ("preset_families", PRESET_FAMILIES),
        ):
            if set(getattr(self, name)) != set(keys):
                raise ValueError(f"{name} : il faut exactement {', '.join(keys)}")
        for key, step in STEPS.items():
            # A step that only reads a stage (Documents, the question and its Embedding) says
            # what it does itself: its stage's explanation is about another step.
            if not step.own and self.steps[key].explain_text is None:
                raise ValueError(f"steps.{key} : il faut un explain_text")
        for kind, options in OPTIONS.items():
            if set(self.options.get(kind, {})) != set(options):
                raise ValueError(f"options.{kind} : il faut exactement {', '.join(options)}")
        if set(self.options) != set(OPTIONS):
            raise ValueError(f"options : il faut exactement {', '.join(OPTIONS)}")
        if set(self.params) != set(BOUNDS):
            raise ValueError(f"params : il faut exactement {', '.join(BOUNDS)}")
        # V1.2 story 10: each preset in exactly one family.
        families = [p for members in PRESET_FAMILIES.values() for p in members]
        for preset in PRESETS:
            if families.count(preset) != 1:
                raise ValueError(f"preset_families : il faut exactement une famille pour {preset}")
        if set(families) != set(PRESETS):
            raise ValueError(f"preset_families : il faut exactement {', '.join(PRESETS)}")
        wanted = {f"{k}.{o}" for k in SHEETED_KINDS for o in OPTIONS[k]}
        if set(self.sheets) != wanted:
            raise ValueError(f"sheets : il faut exactement {', '.join(sorted(wanted))}")
        return self


_CONTENT: dict[str, tuple[int, RagLabContent]] = {}  # the latest read, by path


def load_lab_content(lang: str = config.DEFAULT_LANGUAGE) -> RagLabContent:
    """Read `content/rag_lab.yaml` in `lang` (languages 4/5: the session's, never
    `settings.json`'s), again once the file changed: a corrected file shows on the page's
    reload. Raises on a missing or invalid file. Only the latest read of a file is kept."""
    path = config.content_file("rag_lab.yaml", lang)
    mtime = path.stat().st_mtime_ns
    kept = _CONTENT.get(str(path))
    if kept is not None and kept[0] == mtime:
        return kept[1]
    content = RagLabContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    _CONTENT[str(path)] = (mtime, content)
    return content


load_lab_content.cache_clear = _CONTENT.clear  # type: ignore[attr-defined]


# ---------- chains ----------


class Stage(_Strict):
    """One stage of a chain: its kind, the option chosen and its settings."""

    id: str = Field(pattern=r"^[a-z0-9_]{1,16}$")
    kind: str = Field(max_length=32)
    option: str = Field(max_length=32)
    params: dict[str, int] = {}


class Pipeline(_Strict):
    """A chain: its name (« A », kept for the pages that send it) and its stages, in order."""

    label_text: str = Field(default="A", min_length=1, max_length=40)
    stages: list[Stage] = Field(min_length=1, max_length=12)

    def find(self, kind: str) -> Stage | None:
        return next((s for s in self.stages if s.kind == kind), None)


def default_pipeline(cfg: config.Config) -> Pipeline:
    """The chain the RAG brick runs: its chunk size, its embedding model, the sqlite-vec
    index, its candidates, its reranker, its `top_k`, then the active model's generation."""
    stages = [
        ("chunking", "paragraphs", {"chunk_max_chars": cfg.rag_chunk_max_chars}),
        ("embedding", "declared", {}),
        ("vector_store", "sqlite_vec", {}),
        ("vector_search", "cosine", {"candidates": cfg.rag_rerank_candidates}),
        ("rerank", "declared", {}),
        ("context", "excerpts", {"top_k": cfg.rag_top_k}),
        ("generation", "active", {}),
    ]
    return Pipeline(
        label_text="A",
        stages=[
            Stage(id=f"s{i}", kind=kind, option=option, params=params)
            for i, (kind, option, params) in enumerate(stages, start=1)
        ],
    )


@dataclass
class OptionState:
    """What the page shows of an option: its name, whether it can be chosen (with why not),
    and a note on what a run would meet (a model missing, the brick's index stale). Lot 5c-4:
    `download`, its model's files missing: the `download_model` target and the button's
    label (`{"target", "label_text"}`), else `None`."""

    label_text: str
    available: bool = True
    reason_text: str | None = None
    note_text: str | None = None
    download: dict[str, str] | None = None


@dataclass
class Catalog:
    """The kinds, options and settings the workshop offers now, and the shipped chain.
    `lang`: the session's language (languages 5/5), that of `content`, in which the
    refusals and the options' reasons (a `Message` rendered) are written."""

    content: RagLabContent
    default: Pipeline
    options: dict[tuple[str, str], OptionState]
    lang: str = config.DEFAULT_LANGUAGE

    def bounds(self, name: str) -> tuple[int, int]:
        """A setting's bounds; the shipped value always fits (a `[rag]` outside them)."""
        low, high = BOUNDS[name]
        for stage in self.default.stages:
            if name in stage.params:
                low, high = min(low, stage.params[name]), max(high, stage.params[name])
        return low, high

    def payload(self) -> dict[str, Any]:
        stages = []
        for kind in KINDS:
            text = self.content.stages[kind]
            options = []
            for option in self.kind_options(kind):
                state = self.options.get((kind, option))
                if state is None:
                    continue
                params = []
                for name in PARAMS.get((kind, option), ()):
                    low, high = self.bounds(name)
                    params.append(
                        {
                            "name": name,
                            "label_text": self.content.params[name].label_text,
                            "unit_text": self.content.params[name].unit_text,
                            "min": low,
                            "max": high,
                            "default": param(Stage(id="x", kind=kind, option=option), name, self),
                        }
                    )
                options.append(
                    {
                        "id": option,
                        "label_text": state.label_text,
                        "available": state.available,
                        "reason_text": _rendered(state.reason_text, self.lang),
                        "note_text": _rendered(state.note_text, self.lang),
                        "params": params,
                        "download": state.download,
                    }
                )
            stages.append(
                {
                    "kind": kind,
                    "label_text": text.label_text,
                    "explain_text": text.explain_text,
                    "movable": kind in RETRIEVAL,
                    # V1.2 story 5: a stage added opens the retrieval segment, after this one.
                    "insert_after": "vector_store" if kind == "query" else None,
                    "options": options,
                    # B1 (2026-10-05): the models to download from this stage, the figure the
                    # architecture's tile says (« 2 modèles à télécharger »).
                    "download_count": sum(1 for o in options if o["download"]),
                }
            )
        return {
            "stages": stages,
            "insert_before": FIXED_TAIL[0],
            **self._views(),
            "presets": self._presets(),
            # V1.2 story 10: the families the presets are drawn in, and the Context options
            # that read the whole corpus (a chain with one of them has no search).
            "preset_families": [
                {"id": f, "label_text": self.content.preset_families[f].label_text}
                for f in PRESET_FAMILIES
            ],
            "corpus_options": list(CORPUS_OPTIONS),
            # V1.2 story 11: every Context option without a retrieval segment (`rag.js`).
            "searchless_options": list(SEARCHLESS_OPTIONS),
        }

    def kind_options(self, kind: str) -> list[str]:
        """A kind's options in the order drawn: the workshop's own (`OPTIONS`, the shipped one
        first), then those the session adds (lot 5c-1: the declared embedding models of
        `[[rag_lab.embeddings]]`, by their id), in the order declared."""
        static = list(OPTIONS.get(kind, ()))
        return static + [o for k, o in self.options if k == kind and o not in static]

    def preset_pipeline(self, preset: str) -> Pipeline:
        """The shipped chain, its retrieval segment replaced by the preset's, each stage of
        it at its shipped settings. V1.2 story 10: a preset of `PRESET_CONTEXT` also sets the
        Context's option (without settings); the others keep the shipped Context."""
        segment = [
            (kind, option, self._shipped_params(kind, option)) for kind, option in PRESETS[preset]
        ]
        head = [s for s in self.default.stages if s.kind in FIXED_HEAD]
        tail = [s for s in self.default.stages if s.kind in FIXED_TAIL]
        ends = [(s.kind, s.option, dict(s.params)) for s in tail]
        context = PRESET_CONTEXT.get(preset)
        if context is not None:
            ends = [
                ("context", context, self._shipped_params("context", context))
                if e[0] == "context"
                else e
                for e in ends
            ]
        stages = [(s.kind, s.option, dict(s.params)) for s in head]
        stages += segment + ends
        return Pipeline(
            label_text=self.default.label_text,
            stages=[
                Stage(id=f"s{i}", kind=kind, option=option, params=params)
                for i, (kind, option, params) in enumerate(stages, start=1)
            ],
        )

    def _shipped_params(self, kind: str, option: str) -> dict[str, int]:
        probe = Stage(id="x", kind=kind, option=option)
        return {name: param(probe, name, self) for name in PARAMS.get((kind, option), ())}

    def _presets(self) -> list[dict[str, Any]]:
        """Lot 5b: the ready-made architectures, their texts, their segment (kind, option,
        shipped settings) and whether they run now: the session's verdict (`check_pipeline`)
        on the shipped chain with that segment, its refusal as the reason; the notes of its
        options (what a run would meet: the reranker's files missing), in its language."""
        presets = []
        family_of = {p: f for f, members in PRESET_FAMILIES.items() for p in members}
        for key in PRESETS:
            chain = self.preset_pipeline(key)
            segment = chain.stages[len(FIXED_HEAD) : -len(FIXED_TAIL)]
            context = chain.find("context")
            assert context is not None  # the shipped chain has its Context
            refusal = check_pipeline(chain, self)
            notes = []
            for stage in segment:
                state = self.options.get((stage.kind, stage.option))
                note = _rendered(state.note_text, self.lang) if state else None
                if note and note not in notes:
                    notes.append(note)
            presets.append(
                {
                    "id": key,
                    "label_text": self.content.presets[key].label_text,
                    "explain_text": self.content.presets[key].explain_text,
                    "segment": [
                        {"kind": s.kind, "option": s.option, "params": dict(s.params)}
                        for s in segment
                    ],
                    "available": refusal is None,
                    "reason_text": refusal[0] if refusal else None,
                    "note_text": " ".join(notes) or None,
                    # V1.2 story 10: its family, and the Context it sets (`replaces_context`)
                    # or that a chain without search gets back when it is applied.
                    "family": family_of[key],
                    "context": {"option": context.option, "params": dict(context.params)},
                    "replaces_context": key in PRESET_CONTEXT,
                }
            )
        return presets

    def _views(self) -> dict[str, Any]:
        """Lot 5a: the sequence's steps (the table step → components), the architecture's
        components and groups, the bands of the two phases, with their texts."""
        texts = self.content
        steps = []
        for key, step in STEPS.items():
            text = texts.steps[key]
            uses = [
                {"component": c, "how": how}
                for how, names in (("reads", step.reads), ("writes", step.writes))
                for c in names
            ] + [{"component": c, "how": "calls"} for c in step.calls]
            explain = text.explain_text
            if explain is None and step.stage is not None:
                explain = texts.stages[step.stage].explain_text
            steps.append(
                {
                    "key": key,
                    "phase": step.phase,
                    "stage": step.stage,
                    "own": step.own,
                    "part": step.part,
                    "options": list(step.options),
                    "hidden_with": list(step.hidden_with),
                    "uses": uses,
                    "label_text": text.label_text,
                    "action_text": text.action_text,
                    "explain_text": explain,
                    "note_text": text.note_text,
                }
            )
        return {
            "steps": steps,
            "components": [
                {
                    "id": key,
                    "group": group,
                    "icon": icon,
                    "stage": stage,
                    "label_text": texts.components[key].label_text,
                    "note_text": texts.components[key].note_text,
                }
                for key, (group, icon, stage) in COMPONENTS.items()
            ],
            "groups": [{"id": g, "label_text": texts.groups[g].label_text} for g in GROUPS],
            "phases": [{"id": p, **texts.phases[p].model_dump()} for p in PHASES],
        }

    def option_label(self, kind: str, option: str) -> str:
        state = self.options.get((kind, option))
        return state.label_text if state else option


def _bounds_fr(
    name: str, low: int, high: int, catalog: Catalog, lang: str = config.DEFAULT_LANGUAGE
) -> str:
    text = catalog.content.params[name]
    return _t(
        "check.bounds",
        lang,
        setting=text.label_text.lower(),
        low=lang_int(low, lang),
        high=lang_int(high, lang),
        unit=text.unit_text,
    ).strip()


def check_pipeline(
    pipeline: Pipeline, catalog: Catalog, *, lang: str | None = None
) -> tuple[str, str | None] | None:
    """Why the workshop refuses this chain, in `lang` (the catalog's by default), and the id
    of the stage at fault (`None` when no stage is), or `None` when it runs. The chunking,
    the embedding and the vector store open it, the context and the generation close it, in
    that order; between them, the searches, the fusion and the reranking in any order, each
    once, at least one search; two searches need a fusion after them, a fusion two searches
    before it, a reranking a search before it. Then each stage's option and settings."""
    lang = lang or catalog.lang
    names = {k: catalog.content.stages[k].label_text for k in catalog.content.stages}

    def text(key: str, /, **kw: Any) -> str:
        return _t(f"check.{key}", lang, **kw)

    stages = pipeline.stages
    ids = [s.id for s in stages]
    if len(set(ids)) != len(ids):
        return text("duplicate_id"), None
    for stage in stages:
        if stage.kind not in OPTIONS:
            return text("unknown_kind", kind=stage.kind), stage.id
    seen: set[str] = set()
    for stage in stages:
        if stage.kind in seen:
            return text("once", stage=names[stage.kind]), stage.id
        seen.add(stage.kind)
    kinds = [s.kind for s in stages]
    head, tail = list(FIXED_HEAD), list(FIXED_TAIL)
    order = " → ".join(names[k].lower() for k in (*FIXED_HEAD, *FIXED_TAIL) if k in names)
    for kind in (*head, *tail):
        if kind not in kinds:
            return text("fixed_missing", stage=names[kind], order=order), None
    if kinds[: len(head)] != head or kinds[-len(tail) :] != tail:
        wrong = next(
            s
            for i, s in enumerate(stages)
            if (s.kind in head and i != head.index(s.kind))
            or (s.kind in tail and i != len(stages) - len(tail) + tail.index(s.kind))
        )
        return text("fixed_place", stage=names[wrong.kind], order=order), wrong.id
    segment = stages[len(head) : -len(tail)]
    searches = [s for s in segment if s.kind in SEARCHES]
    # V1.2 story 10: a Context that reads the whole corpus takes no search, nor any stage of
    # the segment; the head stays in the chain without running (its availability unchecked).
    # V1.2 story 11: the same for a Context that searches by itself (its own message).
    context_option = stages[-len(tail)].option
    whole = context_option in SEARCHLESS_OPTIONS
    if whole and segment:
        option = catalog.option_label("context", context_option)
        key = "corpus_needs_no_search" if context_option in CORPUS_OPTIONS else "searches_itself"
        return text(key, stage=names[segment[0].kind], option=option), segment[0].id
    if not whole:
        refused = _segment_refusal(segment, searches, names, text, stages[-len(tail)].id)
        if refused is not None:
            return refused
    for stage in stages:
        label = names[stage.kind]
        state = catalog.options.get((stage.kind, stage.option))
        if state is None:
            return text("unknown_option", stage=label, option=stage.option), stage.id
        if not state.available and not (whole and stage.kind in FIXED_HEAD):
            reason = _rendered(state.reason_text, lang)
            return (
                text("unavailable", stage=label, option=state.label_text, reason=reason),
                stage.id,
            )
        allowed = PARAMS.get((stage.kind, stage.option), ())
        unknown = set(stage.params) - set(allowed)
        if unknown:
            return text("unknown_setting", stage=label, names=", ".join(sorted(unknown))), stage.id
        for name in allowed:
            if name not in stage.params:
                continue
            low, high = catalog.bounds(name)
            if not low <= stage.params[name] <= high:
                bounds = _bounds_fr(name, low, high, catalog, lang)
                return text("out_of_bounds", stage=label, bounds=bounds), stage.id
    context = pipeline.find("context")
    top_k = param(context, "top_k", catalog) if context else 0
    for stage in searches:
        candidates = param(stage, "candidates", catalog)
        if candidates < top_k:
            return (
                text(
                    "too_few_candidates",
                    stage=names[stage.kind],
                    kept=count_text(candidates, "kept_candidate", lang),
                    extracts=count_text(top_k, "extract", lang),
                    candidates=count_text(top_k, "candidate", lang),
                ),
                stage.id,
            )
    return None


def _segment_refusal(
    segment: Sequence[Stage],
    searches: Sequence[Stage],
    names: dict[str, str],
    text: Callable[..., str],
    context_id: str,
) -> tuple[str, str | None] | None:
    """The retrieval segment's own rules: at least one search, a fusion for two searches and
    after them, a reranking and a query understanding on the right side of the searches."""
    if not searches:
        return text("no_search", stage=names["context"]), context_id
    position = {s.id: i for i, s in enumerate(segment)}
    fusion = next((s for s in segment if s.kind == "fusion"), None)
    if len(searches) == 2:
        second = searches[1]
        if fusion is None:
            return text("fusion_needed", stage=names[second.kind]), second.id
        if position[fusion.id] < position[second.id]:
            return text("fusion_before", stage=names["fusion"]), fusion.id
    elif fusion is not None:
        return text("fusion_alone", stage=names["fusion"]), fusion.id
    rerank = next((s for s in segment if s.kind == "rerank"), None)
    if rerank is not None and position[rerank.id] < position[searches[0].id]:
        return text("rerank_before", stage=names["rerank"]), rerank.id
    understanding = next((s for s in segment if s.kind == "query"), None)
    if understanding is not None and position[understanding.id] > position[searches[0].id]:
        return text("query_before", stage=names["query"]), understanding.id
    return None


def validate_pipeline(
    pipeline: Pipeline, catalog: Catalog, *, lang: str | None = None
) -> str | None:
    """Why the workshop refuses this chain (in `lang`, the catalog's by default, naming the
    stage at fault), or `None`."""
    refusal = check_pipeline(pipeline, catalog, lang=lang)
    return refusal[0] if refusal else None


def param(stage: Stage, name: str, catalog: Catalog) -> int:
    """A setting of a stage: its value, else the shipped chain's."""
    if name in stage.params:
        return int(stage.params[name])
    shipped = catalog.default.find(stage.kind) or catalog.default.find(
        "vector_search" if name == "candidates" else stage.kind
    )
    if shipped is not None and name in shipped.params:
        return int(shipped.params[name])
    return PARAM_DEFAULTS.get(name, BOUNDS[name][0])


# ---------- figures in French ----------


def fr_int(n: int) -> str:
    """« 1 536 »: French thousands separator (narrow no-break space)."""
    return f"{n:,}".replace(",", " ")


def count_fr(n: int, one: str, many: str | None = None) -> str:
    """« 1 extrait », « 29 extraits »: a count and its noun, agreed."""
    return f"{fr_int(n)} {one if n == 1 else (many or one + 's')}"


def fr_score(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}".replace(".", ",")


def fr_rank(n: int) -> str:
    return "1er" if n == 1 else f"{n}ᵉ"


def fr_ms(ms: int) -> str:
    return f"{fr_int(ms)} ms"


def _mo(n: int) -> str:
    return config.mo_fr(n)


def size_fr(n: int) -> str:
    """« 19 Ko », « 1,5 Mo »: a size small or large."""
    if n < _MIB:
        return f"{fr_int(max(1, round(n / 1024)))} Ko"
    return f"{n / _MIB:.1f} Mo".replace(".", ",")


# ---------- figures and texts in the session's language (languages 5/5) ----------
# French keeps the functions above, byte for byte; `messages.number` writes the others.


def _t(key: str, lang: str, /, **kw: Any) -> str:
    """`rag_lab.{key}` of `content/messages.yaml`, in `lang`."""
    return msg(f"rag_lab.{key}", lang, **kw)


def _french(lang: str) -> bool:
    return config.as_language(lang) == config.DEFAULT_LANGUAGE


def _rendered(value: Any, lang: str) -> Any:
    """A text given by the session (a `Message`, rendered in `lang`), `None` kept."""
    return None if value is None else render(value, lang)


def lang_int(n: int, lang: str) -> str:
    return fr_int(n) if _french(lang) else number(n, lang)


def agreed(key: str, n: int, lang: str) -> str:
    """A plural of `rag_lab`, agreed as the workshop always did: singular for 1 only."""
    return _t(key, lang, count=1 if n == 1 else 2)


def mark_text(author: str, method: str, model: str, lang: str) -> str:
    """V1.2 story 6: where a context comes from, « précalculé · heuristique, sans LLM » or
    « reconstruit · par le modèle X »."""
    how = (
        _t("chunking.mark.heuristic", lang)
        if method == rag_contexts.HEURISTIC
        else _t("chunking.mark.llm", lang, model=model)
    )
    return f"{_t(f'chunking.mark.{author}', lang)} · {how}"


def count_text(n: int, noun: str, lang: str) -> str:
    """`count_fr` in `lang`: « 3 extraits », « 3 excerpts » (`rag_lab.noun.{noun}`)."""
    return f"{lang_int(n, lang)} {agreed(f'noun.{noun}', n, lang)}"


def score_text(value: float | None, lang: str) -> str:
    if value is None or _french(lang):
        return fr_score(value)
    return number(value, lang, 3)


def rank_text(n: int, lang: str) -> str:
    """`fr_rank` in `lang`: « 1er », « 1st », « 1. »."""
    if n == 1:
        key = "first"
    elif n % 100 in (11, 12, 13):
        key = "th"
    else:
        key = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return _t(f"rank.{key}", lang, n=n)


def ms_text(ms: int, lang: str) -> str:
    return f"{lang_int(ms, lang)} ms"


def mo_text(n: int, lang: str) -> str:
    """Bytes in Mo (MB), rounded, without the unit."""
    return _mo(n) if _french(lang) else number(round(n / _MIB), lang)


def size_text(n: int, lang: str) -> str:
    """`size_fr` in `lang`."""
    if n < _MIB:
        return _t("size.kib", lang, n=lang_int(max(1, round(n / 1024)), lang))
    value = f"{n / _MIB:.1f}".replace(".", ",") if _french(lang) else number(n / _MIB, lang, 1)
    return _t("size.mib", lang, n=value)


def quoted(text: str, lang: str) -> str:
    """« text », in `lang`'s quotation marks."""
    return _t("quoted", lang, text=text)


# ---------- the corpus's vectors, cached under `rag_lab_dir()` (AD-20) ----------

CHUNKS_FILE = "chunks.json"  # written last: its presence says the folder is whole
VECTORS_FILE = "vectors.f32"
INDEX_FILE = "index.sqlite"


_DIGESTS: dict[str, tuple[int, int, str]] = {}  # by path: its size, its mtime, its sha256


def file_digest(path: Path) -> str:
    """A file's sha256, computed again only when its size or modification time changed; the
    latest one per path is kept."""
    stat = path.stat()
    kept = _DIGESTS.get(str(path))
    if kept is None or kept[:2] != (stat.st_size, stat.st_mtime_ns):
        kept = (stat.st_size, stat.st_mtime_ns, rag_index.file_sha256(path))
        _DIGESTS[str(path)] = kept
    return kept[2]


def folder_identity(folder: Path) -> tuple[int, str]:
    """A folder's files (a fastembed model): their total size, and one sha256 over each
    file's path and sha256."""
    digest = hashlib.sha256()
    size = 0
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        size += path.stat().st_size
        digest.update(f"{path.relative_to(folder).as_posix()}\x1f{file_digest(path)}\x1e".encode())
    return size, digest.hexdigest()


def cache_key(
    identity: dict[str, Any],
    chunk_max_chars: int,
    digest: str,
    chunking: dict[str, str] | None = None,
) -> str:
    """The folder of a corpus embedded by a model: the model's identity (id, dimensions, file
    size and sha256), the chunk size and the chunks' digest. V1.2 story 6: `chunking`, for an
    option other than `paragraphs` (its name, and for `contextual` the fingerprint of the
    contexts applied): the text embedded is not the chunk's alone."""
    parts: dict[str, Any] = {
        "embedder": identity,
        "chunk_max_chars": chunk_max_chars,
        "corpus": digest,
    }
    if chunking:
        parts["chunking"] = chunking
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:20]


def _replace(path: Path, data: bytes) -> None:
    """A file written whole or not at all: a temporary file, then `os.replace`."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_vectors(
    folder: Path,
    chunks: Sequence[Chunk],
    vectors: Sequence[Sequence[float]],
    identity: dict,
    truncated: int | None = None,
) -> None:
    """The vectors (float32, `array('f')`), then the chunks and what identifies them; lot
    5c-1: how many chunks the model truncated (`None`: it does not say), said again when the
    cache is read."""
    folder.mkdir(parents=True, exist_ok=True)
    flat = array("f", (x for v in vectors for x in v))
    _replace(folder / VECTORS_FILE, flat.tobytes())
    meta = {
        "embedder": identity,
        "dims": len(vectors[0]) if vectors else 0,
        "count": len(vectors),
        "truncated": truncated,
        "chunks": [list(c) for c in chunks],
    }
    _replace(folder / CHUNKS_FILE, json.dumps(meta, ensure_ascii=False).encode("utf-8"))


def read_vectors(folder: Path, chunks: Sequence[Chunk], dims: int) -> list[list[float]] | None:
    """The cached vectors of exactly these chunks, or `None` (absent, partial, another corpus)."""
    try:
        meta = json.loads((folder / CHUNKS_FILE).read_text(encoding="utf-8"))
        data = (folder / VECTORS_FILE).read_bytes()
    except (OSError, ValueError):
        return None
    if meta.get("dims") != dims or meta.get("count") != len(chunks):
        return None
    if [tuple(c) for c in meta.get("chunks", [])] != [tuple(c) for c in chunks]:
        return None
    if len(data) != 4 * dims * len(chunks):
        return None
    flat = array("f")
    flat.frombytes(data)
    return [list(flat[i * dims : (i + 1) * dims]) for i in range(len(chunks))]


def read_truncated(folder: Path) -> int | None:
    """Lot 5c-1: the chunks the model truncated when the cache was written, or `None`."""
    try:
        meta = json.loads((folder / CHUNKS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = meta.get("truncated") if isinstance(meta, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


BUILD_COSTS_FILE = "build_costs.json"


def brick_costs_path(index: Path) -> Path:
    """V1.2 story 3: where the cost of a shipped index's build is kept, next to it
    (`rag_index.sqlite` -> `rag_index.cost.json`), written by `scripts/build_rag_index.py`."""
    return index.with_suffix(".cost.json")


def _costs_file(source: Path) -> Path:
    return source if source.suffix == ".json" else source / BUILD_COSTS_FILE


def read_build_costs(source: Path) -> dict[str, Any]:
    """The costs recorded when a content was built (`source`: the cache's folder or a
    sidecar file), by part (`embedding`, `vector_store:faiss`...); `{}` when none."""
    try:
        data = json.loads(_costs_file(source).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_build_cost(source: Path, key: str, cost: StageCost, *, reset: bool = False) -> None:
    """Records one built part's cost (`reset`: the other parts are those of an older build,
    forgotten). Never raises: a cost not kept is a cost shown as unknown."""
    target = _costs_file(source)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {} if reset else read_build_costs(target)
        data[key] = cost.record()
        _replace(target, json.dumps(data, ensure_ascii=False).encode("utf-8"))
    except OSError:
        pass


def recorded_cost(source: Path, key: str, kind: str) -> StageCost:
    """A part built earlier, its cost read back and marked `measured_at_build`; when the
    record is absent, a cost without figures that says so."""
    cost = StageCost.from_record("build", kind, read_build_costs(source).get(key))
    if cost is not None:
        return cost
    return StageCost(
        "build", kind, measured_at_build=True, note_text=Message("rag_lab.costs.build_unknown")
    )


TIE_DIGITS = 6  # two scores equal to this many decimals are a tie, whatever the float noise
TIE_MARGIN = 16  # the extra neighbours an index is asked for, to settle ties the same way


def top(found: Sequence[tuple[float, int]], k: int) -> list[tuple[int, float]]:
    """`(score, chunk_id)` pairs to the `k` best `(chunk_id, score)`: every store ranks alike,
    by score (a tie within the float noise of float32 arithmetic broken by chunk id), the
    score bounded to [0, 1] with 3 decimals."""
    found = [(s if math.isfinite(s) else 0.0, cid) for s, cid in found]  # NaN: no likeness
    ranked = sorted(found, key=lambda x: (-round(x[0], TIE_DIGITS), x[1]))[:k]
    return [(cid, round(min(1.0, max(0.0, s)), 3)) for s, cid in ranked]


def as_float32(vector: Sequence[float]) -> list[float]:
    """A vector as the stores keep it (float32), for every store to compare alike."""
    return list(array("f", vector))


class MemoryStore:
    """Exhaustive search in pure Python: the dot product of the normalized question with each
    normalized vector (its cosine), every vector read, no index."""

    def __init__(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        self._chunks = list(chunks)
        self._vectors = [as_float32(v) for v in vectors]

    def search(self, vector: Sequence[float], k: int) -> list[tuple[int, float]]:
        """`(chunk_id, score)` of the `k` nearest, the score bounded to [0, 1] with 3
        decimals; ties by chunk id, as sqlite-vec's query orders them."""
        query = as_float32(vector)
        scored = [
            (sum(a * b for a, b in zip(query, v, strict=True)), i + 1)
            for i, v in enumerate(self._vectors)
        ]
        return top(scored, k)

    def close(self) -> None:
        pass


# Increment 3: the vector stores of the `rag-alt` extra, their module and French name.
LIBRARIES = {"faiss": ("faiss", "FAISS"), "lancedb": ("lancedb", "LanceDB")}
INSTALL_FR = "uv sync --extra compression --extra rag-alt"


def _find_spec(name: str) -> Any:
    """`importlib.util.find_spec`, without importing the module (the end-to-end run replaces
    it to play a workstation without the extra)."""
    return importlib.util.find_spec(name)


def installed(name: str) -> bool:
    """Whether a module could be imported, read without importing it."""
    try:
        return _find_spec(name) is not None
    except (ImportError, ValueError):  # a module in `sys.modules` without its spec
        return name in sys.modules


def not_installed_fr(option: str) -> str:
    """Why FAISS or LanceDB cannot be chosen: the extra, and the command that installs it.
    A `Message` (French as a `str`), rendered in the catalog's language by `payload`."""
    return Message("rag_lab.not_installed", library=LIBRARIES[option][1], command=INSTALL_FR)


@dataclass
class Imported:
    """A library of the extra, imported once for the life of WaveStack: its module, and what
    its import added to WaveStack's memory (said by the stage)."""

    module: Any
    facts: list[tuple[str, str]]


def _as_matrix(numpy: Any, vectors: Sequence[Sequence[float]]) -> Any:
    return numpy.asarray(vectors, dtype=numpy.float32)


class FaissStore:
    """FAISS, exhaustive inner product (`IndexFlatIP`) on the normalized float32 vectors:
    their cosine. Built once in the key's folder (`write_index`, a temporary file, then
    `os.replace`), then read."""

    def __init__(self, faiss: Any, folder: Path, vectors: Sequence[Sequence[float]]) -> None:
        import numpy

        self._numpy = numpy
        path = folder / "faiss" / "index.faiss"
        dims = len(vectors[0])
        index = None
        if path.is_file():
            try:
                index = faiss.read_index(str(path))
            except Exception:  # noqa: BLE001 - rebuilt below
                index = None
            if index is not None and (index.ntotal != len(vectors) or index.d != dims):
                index = None
        self.built = index is None
        if index is None:
            index = faiss.IndexFlatIP(dims)
            index.add(_as_matrix(numpy, vectors))
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            try:
                faiss.write_index(index, str(tmp))
                os.replace(tmp, path)
            except BaseException:
                tmp.unlink(missing_ok=True)
                raise
        self._index = index
        self.path = path

    def search(self, vector: Sequence[float], k: int) -> list[tuple[int, float]]:
        wanted = min(self._index.ntotal, k + TIE_MARGIN)
        scores, ids = self._index.search(_as_matrix(self._numpy, [vector]), wanted)
        found = [(float(s), int(i) + 1) for s, i in zip(scores[0], ids[0], strict=True) if i >= 0]
        return top(found, k)

    def close(self) -> None:
        self._index = None


class LanceStore:
    """LanceDB, a table `chunks` (`id`, `vector`) searched with the cosine metric. Built once
    in a temporary folder of the key's folder, then moved into place; then read. A table of
    another size or dimension is let go (Windows keeps an open table's files) and deleted."""

    TABLE = "chunks"

    def __init__(self, lancedb: Any, folder: Path, vectors: Sequence[Sequence[float]]) -> None:
        path = folder / "lancedb"
        dims = len(vectors[0])
        table = None
        if path.is_dir():
            try:
                table = lancedb.connect(str(path)).open_table(self.TABLE)
                first = table.head(1).to_pylist()
                if table.count_rows() != len(vectors) or len(first[0]["vector"]) != dims:
                    table = None
            except Exception:  # noqa: BLE001 - rebuilt below
                table = None
            gc.collect()  # a stale table's handles let go before its files are deleted
        self.built = table is None
        if table is None:
            tmp = folder / "lancedb.tmp"
            _delete(tmp)
            try:
                rows = [
                    {"id": i + 1, "vector": [float(x) for x in v]} for i, v in enumerate(vectors)
                ]
                lancedb.connect(str(tmp)).create_table(self.TABLE, data=rows, mode="overwrite")
                gc.collect()
                _delete(path)
                os.replace(tmp, path)
            except BaseException:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
            table = lancedb.connect(str(path)).open_table(self.TABLE)
        self._table = table
        self.path = path

    def search(self, vector: Sequence[float], k: int) -> list[tuple[int, float]]:
        query = self._table.search(list(vector), vector_column_name="vector")
        rows = query.distance_type("cosine").limit(k + TIE_MARGIN).to_list()
        found = [(1.0 - float(r["_distance"]), int(r["id"])) for r in rows]
        return top(found, k)

    def close(self) -> None:
        self._table = None


def _delete(folder: Path) -> None:
    """A folder of the workshop removed, or a `StageFailed` saying why it cannot be."""
    if not folder.exists():
        return
    try:
        shutil.rmtree(folder)
    except OSError as exc:
        raise StageFailed(
            Message("rag_lab.folder_held", folder=folder, error=type(exc).__name__, cause=str(exc))
        ) from exc


class _SqliteStore:
    """A sqlite-vec index (the brick's, read only, or the workshop's), searched through the
    `Retriever` port."""

    def __init__(self, path: Path, embedder: Embedder) -> None:
        self._retriever = SqliteVecRetriever(path, embedder, 1)

    def search(self, vector: Sequence[float], k: int) -> list[tuple[int, float]]:
        found = self._retriever.nearest(list(vector), k + TIE_MARGIN)
        return top([(1.0 - distance, chunk_id) for chunk_id, distance in found], k)

    def close(self) -> None:
        self._retriever.close()


# ---------- a run ----------


def _keyed(text: str) -> Message:
    """A text given to a stage's exception: a `Message` kept, any other text as it is."""
    return text if isinstance(text, Message) else Message("common.verbatim", text=text)


class StageFailed(KeyedError):
    """A stage cannot do its work: its reason, a `Message` (French as `str()` and
    `message_text`, `render(lang)` in the session's) or a text kept as it is. `soft`: the
    chain goes on (the reranking), else the next stages are skipped. Lot 5c-3: `result`, what
    the stage still shows (the generation's prompt, too long to be sent)."""

    def __init__(
        self, message_text: str, *, soft: bool = False, result: _Result | None = None
    ) -> None:
        super().__init__(_keyed(message_text))
        self.message_text: str = self.message
        self.soft = soft
        self.result = result


class StageSkipped(KeyedError):
    """A stage that does not run (the reranker is not on the workstation): why, as
    `StageFailed` says it; `result`, what the stage still shows (lot 5c-3)."""

    def __init__(self, reason_text: str, *, result: _Result | None = None) -> None:
        super().__init__(_keyed(reason_text))
        self.reason_text: str = self.message
        self.result = result


class LabCancelled(Exception):
    """« Arrêter », seen between two stages, two passages or two candidates (lot 5c-3: or
    during the generation, `result` what it had produced)."""

    def __init__(self, result: _Result | None = None) -> None:
        super().__init__()
        self.result = result


@dataclass
class Lent:
    """A model for the run: borrowed from the RAG brick (never closed by the run), or loaded
    for it (closed at its end by whoever lent it)."""

    model: Any
    borrowed: bool
    label_text: str


class Loans:
    """The models a run loads itself (AD-8): the budget checked first (a refusal in figures,
    nothing loaded), then the load and its grant; `close()` closes each and frees its slot. A
    model the brick holds is borrowed: neither checked, granted nor closed. Lot 5c-1: each
    model has its own slot (a declared embedding model `rag_lab.embedding.<id>`), the
    brick's never touched."""

    def __init__(self, registry: LoadRegistry) -> None:
        self._registry = registry
        self._opened: list[tuple[Any, str]] = []

    def lend(
        self,
        *,
        borrowed: Any,
        label_text: str,
        noun_text: str,
        unavailable_text: str | None,
        cost: int,
        slot: str,
        open_model: Callable[[], Any],
        soft: bool = False,
    ) -> Lent:
        """`borrowed`: the brick's model, else `None`; `unavailable_text`: why it cannot load
        (a missing file). `soft`: its failure lets the chain go on (the reranker), and a
        missing file only skips the stage."""
        if borrowed is not None:
            return Lent(borrowed, True, label_text)
        if unavailable_text is not None:
            if soft:
                raise StageSkipped(unavailable_text)
            raise StageFailed(unavailable_text)
        # Finition V1 (#9): « pour charger le modèle d'embedding X », its article included.
        named = Message("session.rag_lab.to_load", noun=noun_text, model=label_text)
        refusal = self._registry.check_component(named, cost, slot)
        if refusal is not None:
            raise StageFailed(refusal, soft=soft)
        try:
            model = open_model()
        except Exception as exc:  # noqa: BLE001 - said in the stage, never a crash
            raise StageFailed(
                Message(
                    "rag_lab.load_failed",
                    noun=noun_text,
                    model=label_text,
                    error=type(exc).__name__,
                    cause=str(exc),
                ),
                soft=soft,
            ) from exc
        self._registry.grant(label_text, cost, slot)
        self._opened.append((model, slot))
        return Lent(model, False, label_text)

    def close(self) -> list[str]:
        """Close what the run loaded, free its slots; the errors met, in French."""
        errors = []
        while self._opened:
            model, slot = self._opened.pop()
            try:
                model.close()
            except Exception as exc:  # noqa: BLE001 - it is forgotten all the same
                errors.append(f"{type(exc).__name__} : {exc}")
            self._registry.release(slot)
        return errors


@dataclass(frozen=True)
class GenerationAsk:
    """Lot 5c-3: what the generation hands the session: the context the chain built (its
    introduction and its excerpts, empty when it built none), the question, the stage's step
    id (the model call's scope), its progress callback (tokens produced, the reserve) and the
    stop test."""

    context_text: str
    question: str
    step_id: str
    progress: Callable[[int, int], None]
    cancelled: Callable[[], bool]
    # V1.2 story 5 (CAP-3): a short task (the query understanding) instead of an answer: the
    # system prompt is this instruction (never the brick's), no reasoning, and at most
    # `reserve` tokens written.
    instruction: str | None = None
    reserve: int | None = None
    # V1.2 story 10 (CAG): the prompt up to the question is the prefix kept in the model's
    # memory (`cached_corpus`); `on_prefix` is called once when the session starts building
    # it (the « Préfixe en cache » line then runs).
    cached_prefix: bool = False
    on_prefix: Callable[[], None] | None = None


@dataclass
class CagPrefix:
    """V1.2 story 10: what the session did with the CAG's prefix. `status`: `ok` (built by
    this call, `built`, or read back from the cache entry), `skipped` (nothing built: why in
    `reason_text`) or `error`. `tokens`: the prefix's tokens (`exact`: counted by the engine,
    else estimated). `cost`: its measure in its time (`build` for a run, `update` for an
    update), the entry's record when it was built earlier (`measured_at_build`). `cache`:
    `RagLabCache`'s fields. `warning_text`: what went wrong without failing (memory, lost)."""

    status: str
    tokens: int | None = None
    exact: bool = True
    built: bool = False
    cost: StageCost | None = None
    cache: dict[str, Any] | None = None
    reason_text: Any = None
    warning_text: Any = None


@dataclass
class Generated:
    """Lot 5c-3: what the active model did with it. `status`: `completed`, `limit` (the
    reserve reached), `cancelled`, `error` (`error_text` says why) or `too_long` (nothing
    sent: `prompt_tokens` over `window − reserve`). `prompt_text`: the prompt rendered
    exactly (the local engine's text, a cloud request's body); `exact`: its tokens counted
    by the engine, else estimated. `system_prompt`: the workshop's system prompt was sent."""

    model_label: str
    prompt_text: str
    prompt_tokens: int
    exact: bool
    window: int
    reserve: int
    system_prompt: bool
    status: str = "completed"
    answer_text: str = ""
    output_tokens: int = 0
    error_text: str | None = None
    # V1.2 story 3 (CAP-8): the call's own duration, its dollars (`None`: not priced, 0 for a
    # local model) and its footprint, as the model call measured them.
    duration_ms: int | None = None
    cost_usd: float | None = None
    impact: greenops.Impact | None = None
    # V1.2 story 10 (CAG): the prompt tokens the call evaluated (the rest read from the cache;
    # `None`: unknown), the cache's state of the call (`RagLabCache`'s fields) and the prefix.
    evaluated_tokens: int | None = None
    cache: dict[str, Any] | None = None
    prefix: CagPrefix | None = None


@dataclass
class LabDeps:
    """What a run is given: nothing else of the session reaches it."""

    content: RagContent  # the brick's texts: its corpus and its excerpts' format
    texts: RagLabContent
    catalog: Catalog
    shipped_chunk_max_chars: int
    brick_index: Path
    # Why the brick's index cannot serve (absent, stale, of another model), or `None`.
    brick_index_error: str | None
    lab_dir: Path  # `config.rag_lab_dir()`: the workshop's vectors and indexes
    embedder: Callable[[str], Lent]  # option -> the embedding model, or `StageFailed`
    # option -> what identifies the embedding model (id, dims, size, sha256): its cache's key
    identity: Callable[[str], dict[str, Any]]
    # option (`faiss`, `lancedb`) -> the library, imported once, or `StageFailed`
    importer: Callable[[str], Imported]
    reranker: Callable[[str], Lent]  # option -> the reranker, or `StageSkipped`/`StageFailed`
    cancelled: Callable[[], bool]
    # kind, payload, step id and component of the event
    emit: Callable[[str, dict[str, Any], str, str], None]
    rss: Callable[[], int | None]
    # Languages (4/5): the session's, the corpus's (`content` is `rag.yaml` read in it)
    lang: str = config.DEFAULT_LANGUAGE
    # Lot 5c-3: the active model's generation, or `StageSkipped` (no model loaded); `None`:
    # the stage is skipped.
    generator: Callable[[GenerationAsk], Generated] | None = None
    # V1.2 story 3 (CAP-8): a local tracker around the embedding, the reranking and the
    # indexing (`None`: no footprint), and the tokens of a text (an estimate).
    meter: Callable[[], Measure] | None = None
    estimate_tokens: Callable[[str], int] = lambda text: config.estimate_tokens(text, 4.0)
    # V1.2 story 3: the work copy of the corpus, read by the chain instead of the shipped
    # corpus when it changes something (`None` or empty: the shipped corpus).
    work_copy: workcopy.WorkCopy | None = None
    # V1.2 story 5: the questions asked before in the session (oldest first), which the
    # `follow_up` option reads as the conversation the workshop does not have.
    history: Sequence[str] = ()
    # V1.2 story 7 (CAP-5): the session's compressor, borrowed (never loaded nor closed here):
    # `(compressor, None)`, or `(None, why it is unavailable)`; the chars an excerpt must have
    # to be compressed; the parts of the prompt the generation would send for a context and a
    # question, `(kind, text)` with kind `system`, `context` or `question` (the session's one
    # function, also used by the generation). Defaults: no compressor, no system prompt.
    compressor: Callable[[], tuple[Compressor | None, Any]] = lambda: (None, None)
    compression_min_chars: int = 300
    prompt_parts: Callable[[str, str], Sequence[tuple[str, str]]] = lambda context, question: (
        ([("context", context)] if context else []) + [("question", question)]
    )
    # V1.2 story 10: the session's effective window (the gauge of a whole corpus), and the
    # CAG's prefix built for a context (the update's « Préfixe »): `(context_text, question)`
    # -> `CagPrefix` measured in `update`; `None`: no local model, the part is estimated.
    window: int = 0
    cag: Callable[[str, str], CagPrefix] | None = None
    # V1.2 story 11: the generation's output reserve (the final prompt holds in `window −
    # reserve`), and the frame the session puts around a stage's several model calls (the
    # agent's rounds, the descent's levels): the main context's engine state saved once.
    reserve: int = 0
    model_scope: Callable[[], AbstractContextManager[Any]] = nullcontext
    # V1.2 story 13: GraphRAG's mode (`local`, `global`), and the graph of the chain's
    # documents with the milliseconds its construction took (the session's cache); `None`:
    # built here.
    graph_mode: str = "local"
    graph: Callable[[Sequence[DocText]], tuple[rag_graph.Graph, int]] | None = None


@dataclass
class Item:
    """An excerpt in a ranked list: its rank (from 1), where it was before, its score."""

    chunk_id: int
    doc_id: str
    title_text: str
    text: str
    score: float | None
    rank: int = 0
    before: int | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)
    # V1.2 story 7 (CAP-5): the context's passages: the position in the context, whole or cut,
    # the estimated tokens (before a compression) and after, the compression's transforms and
    # why it failed on this one.
    placed: int | None = None
    state: str | None = None
    tokens: int | None = None
    tokens_after: int | None = None
    transforms: list[str] = field(default_factory=list)
    error_text: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "placed": self.placed,
            "state": self.state,
            "tokens": self.tokens,
            "tokens_after": self.tokens_after,
            "transforms": self.transforms,
            "error_text": self.error_text,
            "rank": self.rank,
            "before": self.before,
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "title_text": self.title_text,
            "text": self.text,
            "score": self.score,
            "sources": self.sources,
        }


@dataclass
class _Result:
    input_text: str = ""
    output_text: str = ""
    facts: list[tuple[str, str]] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    borrowed: bool = False
    # Lot 5c-1: what the stage met without failing (chunks truncated by the embedding model).
    warning_text: str | None = None
    # Lot 5c-3: the generation's prompt, rendered as sent.
    prompt_text: str | None = None
    # V1.2 story 3: what the stage cost, by time; `None`: the stage's duration, in its time.
    costs: list[StageCost] | None = None
    # V1.2 story 5: the queries the query understanding produced, shown in the focus.
    queries: list[str] = field(default_factory=list)
    # V1.2 story 6: the chunking's first chunks, as the focus lists them, and how many in all.
    chunks: list[dict[str, Any]] = field(default_factory=list)
    chunks_total: int = 0
    # V1.2 story 7: the passages the budget left out, the tokens used and the budget, and the
    # parts of the prompt the generation would send, with their total.
    dropped: list[Item] = field(default_factory=list)
    budget: dict[str, Any] | None = None
    prompt_parts: list[dict[str, Any]] = field(default_factory=list)
    prompt_tokens: int | None = None
    # V1.2 story 10: the window a whole corpus is shown against, and the CAG's cache.
    window: int | None = None
    cache: dict[str, Any] | None = None
    # V1.2 story 11: the agent's rounds (`agent_loop`) and the descent's levels (`section_tree`).
    agent: dict[str, Any] | None = None
    tree: dict[str, Any] | None = None
    graph: dict[str, Any] | None = None  # V1.2 story 13: GraphRAG's query (`graph_search`)


# V1.2 story 3: the time a stage's duration counts in, when it gives no costs of its own.
COST_PHASE = {
    "chunking": "build",
    "vector_store": "build",
    "lexical_index": "build",
    "vector_search": "query",
    "lexical_search": "query",
    "fusion": "query",
    "rerank": "query",
    "context": "query",
}
# V1.2 story 10: the footprint of a stage an architecture does not run (none, measured as such).
NO_IMPACT = greenops.Impact("codecarbon", None, 0.0, 0.0, 0.0, 0.0)
UPDATE_RUN_PREFIX = "upd"  # the id of an update run (`upd1`): its events are not the last run
# V1.2 story 6: the id of a rebuild of the contexts (`ctx1`), apart from the runs as well.
REBUILD_RUN_PREFIX = "ctx"
APART_PREFIXES = (UPDATE_RUN_PREFIX, REBUILD_RUN_PREFIX)


@dataclass
class _Chain:
    """What the stages of the chain hand each other."""

    pipeline: Pipeline
    chunk_max_chars: int = 0
    chunks: list[Chunk] = field(default_factory=list)
    embedder: Embedder | None = None
    embedder_label: str = ""
    query_vector: list[float] | None = None
    # V1.2 story 5: what the searches run; empty: the question as typed. `as_document`: the
    # text is a hypothetical answer (HyDE), embedded as a passage is.
    queries: list[str] = field(default_factory=list)
    as_document: bool = False
    vectors: list[list[float]] | None = None  # the passages', when the store needs them
    key: str = ""  # the cache's folder of this corpus and model
    store: Any = None  # `MemoryStore`, `_SqliteStore`…
    lexical: LexicalIndex | None = None  # B2: BM25's index, built at the end of BUILD
    lists: list[list[Item]] = field(default_factory=list)  # each search's, until fused
    list_kinds: list[str] = field(default_factory=list)  # the stage that made each list
    context: list[Item] = field(default_factory=list)
    context_text: str = ""
    status: str = "ok"
    # V1.2 story 6: the chunking option, what identifies it in the cache's key (`None`:
    # `paragraphs`), the parents of a `parent_child` chain (and each child's), the contexts of
    # a `contextual` one, and the models already lent (a run loads each once).
    option: str = "paragraphs"
    chunking_key: dict[str, str] | None = None
    parents: list[Chunk] = field(default_factory=list)
    parent_of: list[int] = field(default_factory=list)
    contexts: rag_contexts.Matched | None = None
    lent: dict[str, Lent] = field(default_factory=dict)

    @property
    def ranked(self) -> list[Item] | None:
        """The list the next stage works on: the last one made."""
        return self.lists[-1] if self.lists else None


class LabRun:
    """One run of the workshop: one chain (`pipeline`) on one question (lot 5c-1: one chain
    per run, the A/B comparison is gone). `run()` emits `rag_lab_run_started`, a
    `rag_lab_stage_started` / `rag_lab_stage_ended` pair per stage run (only the latter for a
    stage skipped or not run), and `rag_lab_run_ended`; it never raises. B2: a chain with
    BM25 gets one pair more, its index part at the end of BUILD, under the BM25 stage's id
    (`kind` « lexical_index », `part` « index », step id `….index`)."""

    def __init__(self, run_id: str, question: str, pipeline: Pipeline, deps: LabDeps) -> None:
        self.run_id = run_id
        self.question = question
        self.pipeline = pipeline
        self.deps = deps
        self.chain: _Chain | None = None
        self.ended = False  # `rag_lab_run_ended` emitted
        self.costs: list[StageCost] = []  # V1.2 story 3: every part's cost, by time

    # -- events --

    def _emit(self, kind: str, payload: dict[str, Any], step_id: str, component: str) -> None:
        self.deps.emit(kind, {"run_id": self.run_id, **payload}, step_id, component)

    def _step(self, index: int) -> str:
        return f"{self.run_id}.s{index}"

    def _label(self, stage: Stage) -> str:
        return self.deps.texts.stages[stage.kind].label_text

    # -- texts, in the session's language (languages 5/5) --

    @property
    def _lang(self) -> str:
        return self.deps.lang

    def _text(self, key: str, /, **kw: Any) -> str:
        return _t(key, self._lang, **kw)

    def _int(self, n: int) -> str:
        return lang_int(n, self._lang)

    def _count(self, n: int, noun: str) -> str:
        return count_text(n, noun, self._lang)

    def _quoted(self, text: str) -> str:
        return quoted(text, self._lang)

    # -- the run --

    def run(self) -> str:
        started = time.monotonic()
        texts = self.deps.texts
        stages = [
            {
                "stage_id": s.id,
                "kind": s.kind,
                "option": s.option,
                "label_text": self._label(s),
                "option_label_text": self.deps.catalog.option_label(s.kind, s.option),
                "params": s.params,
            }
            for s in self.pipeline.stages
        ]
        self._emit(
            "rag_lab_run_started",
            {
                "question": self.question,
                "stages": stages,
                "phase_label": self._text(
                    "run.phase", running=texts.running_text, question=self.question[:80]
                ),
            },
            self.run_id,
            "rag_lab",
        )
        status = "error"
        try:
            chain = self.chain = _Chain(self.pipeline)
            try:
                self._run_chain(chain)
            finally:
                if chain.store is not None:
                    try:
                        chain.store.close()
                    except Exception:  # noqa: BLE001 - a store closed badly is forgotten
                        pass
            status = chain.status
        except Exception:  # noqa: BLE001 - the run ends in error, `run_ended` all the same
            status = "error"
        finally:
            self.end(status, _ms(time.monotonic() - started))
        return status

    SUMMARY_PHASES: tuple[str, ...] = ("build", "query")

    def cost_summary(self, phases: Sequence[str], complete: bool = True) -> list[dict[str, Any]]:
        """V1.2 story 3: the costs of the phases that have a part, summed; a run that did not
        end `ok` gives lower bounds (`partial`)."""
        sums = [greenops.summarize(self.costs, p, self._lang) for p in phases]
        return [x | {"partial": x["partial"] or not complete} for x in sums if x["parts"]]

    def end(self, status: str, duration_ms: int) -> None:
        """`rag_lab_run_ended`, once: the page never stays « en cours »."""
        if self.ended:
            return
        self.ended = True
        self._emit(
            "rag_lab_run_ended",
            {
                "status": status,
                "duration_ms": duration_ms,
                "cost_summary": self.cost_summary(self.SUMMARY_PHASES, status == "ok"),
            },
            self.run_id,
            "rag_lab",
        )

    def _searchless(self, chain: _Chain) -> bool:
        """V1.2 story 10: the chain's Context reads the whole corpus (no index, no search);
        V1.2 story 11: or searches by itself (the agent's tools, PageIndex's tree)."""
        context = chain.pipeline.find("context")
        return context is not None and context.option in SEARCHLESS_OPTIONS

    def _run_chain(self, chain: _Chain) -> None:
        stopped = False  # an earlier stage failed or was stopped: the rest is skipped
        indexed = False  # B2: BM25's index part run (at the end of BUILD)
        whole = self._searchless(chain)
        for index, stage in enumerate(chain.pipeline.stages, start=1):
            if not indexed and stage.kind not in FIXED_HEAD:
                indexed = True
                stopped = self._lexical_index_part(chain, stopped)
            step_id = self._step(index)
            component = f"rag_lab.{stage.kind}"
            base = {"stage_id": stage.id, "kind": stage.kind}
            base["option"] = stage.option
            if stopped:
                self._ended(step_id, component, base, "skipped", _Result(), None, 0, None)
                continue
            if whole and stage.kind in FIXED_HEAD:
                # V1.2 story 10: in the chain, never run: nothing indexed, nothing to build.
                unused = _Result(costs=[StageCost("build", stage.kind, 0, 0, 0.0, NO_IMPACT)])
                context = chain.pipeline.find("context")
                corpus = context is not None and context.option in CORPUS_OPTIONS
                reason = self._text("stage.not_used" if corpus else "stage.not_used_searchless")
                self._ended(step_id, component, base, "skipped", unused, reason, 0, None)
                continue
            if stage.kind == "generation" and stage.option == "not_run":
                result = self._generation(chain)
                self._ended(step_id, component, base, "not_run", result, None, 0, None)
                continue
            if self.deps.cancelled():
                self._ended(step_id, component, base, "cancelled", _Result(), None, 0, None)
                chain.status, stopped = "cancelled", True
                continue
            self._emit(
                "rag_lab_stage_started",
                base | {"phase_label": self._text("stage.running", stage=self._label(stage))},
                step_id,
                component,
            )
            rss_before = self.deps.rss()
            started = time.monotonic()
            status, error_text, result = "ok", None, _Result()
            try:
                result = self._run_stage(chain, stage, step_id, component, base)
            except LabCancelled as stop:
                status, error_text = "cancelled", self._text("stage.stopped")
                chain.status, stopped = "cancelled", True
                result = stop.result or result
            except StageSkipped as skipped:
                status, error_text = "skipped", skipped.render(self._lang)
                result = skipped.result or self._passed_on(chain, error_text)
            except StageFailed as failed:
                status, error_text = "error", failed.render(self._lang)
                if failed.soft:
                    result = failed.result or self._passed_on(chain, error_text)
                else:
                    chain.status, stopped = "error", True
                    result = failed.result or result
            except Exception as exc:  # noqa: BLE001 - AD-16: a stage's failure, never a crash
                status = "error"
                error_text = self._text(
                    "stage.failed",
                    error=type(exc).__name__,
                    cause=exception_text(exc, self._lang),
                )
                chain.status, stopped = "error", True
            duration = _ms(time.monotonic() - started)
            self._ended(step_id, component, base, status, result, error_text, duration, rss_before)

    def _lexical_index_part(self, chain: _Chain, stopped: bool) -> bool:
        """B2 (2026-10-05): BM25's first part, its inverted index built from the Chunks at the
        end of BUILD, when the chain has a BM25 stage: its own `rag_lab_stage_started` /
        `rag_lab_stage_ended` (the BM25 stage's id, `kind` « lexical_index », `part` « index »),
        figures and duration. Returns whether the rest of the chain is skipped."""
        stages = chain.pipeline.stages
        lexical = next((s for s in stages if s.kind == "lexical_search"), None)
        if lexical is None:
            return stopped
        step_id = f"{self._step(stages.index(lexical) + 1)}.index"
        step_label = self.deps.texts.steps["lexical_index"].label_text
        component = "rag_lab.lexical_index"
        base = {
            "stage_id": lexical.id,
            "kind": "lexical_index",
            "option": lexical.option,
            "part": "index",
        }
        if stopped:
            self._ended(step_id, component, base, "skipped", _Result(), None, 0, None)
            return stopped
        if self.deps.cancelled():
            self._ended(step_id, component, base, "cancelled", _Result(), None, 0, None)
            chain.status = "cancelled"
            return True
        self._emit(
            "rag_lab_stage_started",
            base | {"phase_label": self._text("stage.running", stage=step_label)},
            step_id,
            component,
        )
        rss_before = self.deps.rss()
        started = time.monotonic()
        status, error_text, result = "ok", None, _Result()
        try:
            result = self._lexical_index(chain)
        except StageFailed as failed:
            status, error_text = "error", failed.render(self._lang)
            chain.status, stopped = "error", True
        except Exception as exc:  # noqa: BLE001 - AD-16: a stage's failure, never a crash
            status = "error"
            error_text = self._text(
                "stage.failed", error=type(exc).__name__, cause=exception_text(exc, self._lang)
            )
            chain.status, stopped = "error", True
        duration = _ms(time.monotonic() - started)
        self._ended(step_id, component, base, status, result, error_text, duration, rss_before)
        return stopped

    def _ended(
        self,
        step_id: str,
        component: str,
        base: dict[str, Any],
        status: str,
        result: _Result,
        error_text: str | None,
        duration_ms: int,
        rss_before: int | None,
    ) -> None:
        rss = self.deps.rss() if status in ("ok", "error", "cancelled") or rss_before else None
        memory_text = None
        if rss is not None:
            memory_text = self._text("stage.memory", mo=mo_text(rss, self._lang))
            if rss_before is not None:
                delta = rss - rss_before
                sign = "+" if delta >= 0 else "−"
                memory_text = self._text(
                    "stage.memory_during",
                    memory=memory_text,
                    sign=sign,
                    mo=mo_text(abs(delta), self._lang),
                )
        costs = result.costs
        if costs is None and status == "ok" and base["kind"] in COST_PHASE:
            costs = [StageCost(COST_PHASE[base["kind"]], base["kind"], duration_ms=duration_ms)]
        self.costs += costs or []
        self._emit(
            "rag_lab_stage_ended",
            base
            | {
                "costs": [c.payload(self._lang) for c in costs or []],
                "status": status,
                "input_text": result.input_text,
                "output_text": result.output_text,
                "facts": [
                    {"label_text": render(k, self._lang), "value_text": render(v, self._lang)}
                    for k, v in result.facts
                ],
                "items": [i.payload() for i in result.items],
                "borrowed": result.borrowed,
                "error_text": error_text,
                "warning_text": result.warning_text,
                "prompt_text": result.prompt_text,
                "duration_ms": duration_ms,
                "rss_bytes": rss,
                "memory_text": memory_text,
                "queries": result.queries,
                "chunks": result.chunks,
                "chunks_total": result.chunks_total,
                "dropped": [i.payload() for i in result.dropped],
                "budget": result.budget,
                "prompt_parts": result.prompt_parts,
                "prompt_tokens": result.prompt_tokens,
                "window": result.window,
                "cache": result.cache,
                "agent": result.agent,
                "tree": result.tree,
                "graph": result.graph,
            },
            step_id,
            component,
        )

    def _progress(self, step_id: str, component: str, base: dict[str, Any]):  # noqa: ANN202
        """A progress callback: at most ten events a second, the last one always."""
        last = 0.0

        def progress(done: int, total: int) -> None:
            nonlocal last
            now = time.monotonic()
            if done < total and now - last < PROGRESS_INTERVAL_S:
                return
            last = now
            self._emit(
                "rag_lab_stage_progress", base | {"done": done, "total": total}, step_id, component
            )

        return progress

    def _check(self) -> None:
        if self.deps.cancelled():
            raise LabCancelled()

    def _run_stage(
        self, chain: _Chain, stage: Stage, step_id: str, component: str, base: dict[str, Any]
    ) -> _Result:
        progress = self._progress(step_id, component, base)
        if stage.kind == "chunking":
            return self._chunking(chain, stage)
        if stage.kind == "embedding":
            return self._embedding(chain, stage, progress)
        if stage.kind == "vector_store":
            return self._vector_store(chain, stage)
        if stage.kind == "query":
            return self._query(chain, stage, step_id, progress)
        if stage.kind == "vector_search":
            return self._vector_search(chain, stage)
        if stage.kind == "lexical_search":
            return self._lexical_search(chain, stage)
        if stage.kind == "fusion":
            return self._fusion(chain, stage)
        if stage.kind == "rerank":
            return self._rerank(chain, stage, progress)
        if stage.kind == "context":
            # V1.2 story 11: one progress event per round of the agent, per level of the tree.
            def tick(done: int, total: int) -> None:
                payload = base | {"done": done, "total": total}
                self._emit("rag_lab_stage_progress", payload, step_id, component)

            return self._context(chain, stage, step_id, tick)
        if stage.kind == "generation":
            return self._generation_run(chain, step_id, progress)
        raise StageFailed(Message("rag_lab.stage.unknown", kind=stage.kind))

    def _passed_on(self, chain: _Chain, reason_text: str) -> _Result:
        """A reranking skipped or failed: the search's order goes on unchanged."""
        n = len(chain.ranked or [])
        return _Result(
            input_text=self._text("passed_on.input", candidates=self._count(n, "candidate")),
            output_text=self._text("passed_on.output", reason=reason_text),
        )

    # -- the stages --

    def _uses_brick_index(self, chain: _Chain) -> bool:
        """The brick's own configuration (its embedding model, its chunk size, sqlite-vec):
        its index serves, read only."""
        store = chain.pipeline.find("vector_store")
        embedding = chain.pipeline.find("embedding")
        chunking = chain.pipeline.find("chunking")
        return (
            chunking is not None
            and chunking.option == "paragraphs"  # V1.2 story 6: the index is the brick's chunks
            and store is not None
            and store.option == "sqlite_vec"
            and embedding is not None
            and embedding.option == "declared"
            and chain.chunk_max_chars == self.deps.shipped_chunk_max_chars
            and not self._reads_work_copy()
        )

    def _reads_work_copy(self) -> bool:
        """V1.2 story 3: the work copy changes the corpus, the chain reads it (never the
        brick's index, built from the shipped corpus)."""
        return self.deps.work_copy is not None and not self.deps.work_copy.empty

    def _chunking(self, chain: _Chain, stage: Stage) -> _Result:
        size = param(stage, "chunk_max_chars", self.deps.catalog)
        chain.chunk_max_chars = size
        chain.option = stage.option
        if stage.option != "paragraphs":
            return self._chunking_other(chain, stage, size)
        source = self._text("chunking.source_corpus")
        chunks: list[Chunk] = []
        if self._uses_brick_index(chain) and self.deps.brick_index_error is None:
            # Its ids are the index's: never the corpus's chunks under the brick's vectors.
            try:
                chunks = rag_index.read_chunks(self.deps.brick_index)
            except Exception as exc:  # noqa: BLE001 - said in the stage
                raise StageFailed(
                    Message(
                        "rag_lab.chunking.index_unreadable",
                        error=type(exc).__name__,
                        cause=exception_text(exc, self._lang),
                    )
                ) from exc
            source = self._text("chunking.source_index")
        if not chunks and self._reads_work_copy():
            chunks = workcopy.chunks(self.deps.content, size, self.deps.lang, self.deps.work_copy)
            source = self._text("chunking.source_work_copy")
        elif not chunks:
            chunks = chunk_corpus(self.deps.content, size, self.deps.lang)
        if not chunks:
            raise StageFailed(Message("rag_lab.chunking.no_chunks"))
        chain.chunks = chunks
        return self._chunking_result(chain, size, source)

    def _chunking_result(
        self,
        chain: _Chain,
        size: int,
        source: str,
        output: str = "chunking.output",
        facts: Sequence[tuple[str, str]] = (),
        **output_kw: str,
    ) -> _Result:
        """The chunking stage's figures, whatever the option: documents, extracts, sizes, then
        the option's own `facts`; V1.2 story 6: the first chunks, for the focus."""
        chunks = chain.chunks
        docs = len({c.doc_id for c in chunks})
        longest = max(len(c.text) for c in chunks)
        mean = round(sum(len(c.text) for c in chunks) / len(chunks))
        text, count = self._text, self._int

        def chars(n: int) -> str:
            return text("chunking.characters", n=count(n))

        return _Result(
            input_text=text(
                "chunking.input",
                documents=self._count(docs, "document"),
                declared=count(len(self.deps.content.documents)),
            ),
            output_text=text(
                output,
                extracts=self._count(len(chunks), "extract"),
                size=count(size),
                source=source,
                **output_kw,
            ),
            facts=[
                (text("chunking.max_size"), chars(size)),
                (text("chunking.extracts"), count(len(chunks))),
                (text("chunking.mean"), chars(mean)),
                (text("chunking.longest"), chars(longest)),
                *facts,
            ],
            chunks=self._chunk_rows(chain),
            chunks_total=len(chunks),
        )

    def _cut(self, text: str) -> str:
        return text if len(text) <= FOCUS_CHUNK_CHARS else text[: FOCUS_CHUNK_CHARS - 1] + "…"

    def _mark(self, applied: rag_contexts.Applied) -> str:
        return mark_text(applied.author, applied.method, applied.model, self._lang)

    def _chunk_rows(self, chain: _Chain) -> list[dict[str, Any]]:
        """The first `FOCUS_CHUNKS_MAX` chunks, as the focus lists them: their document and
        rank, their text, their parent (`parent_child`), their context and its mark."""
        rows: list[dict[str, Any]] = []
        for i, chunk in enumerate(chain.chunks[:FOCUS_CHUNKS_MAX]):
            row: dict[str, Any] = {
                "doc_id": chunk.doc_id,
                "title_text": chunk.title_text,
                "position": chunk.position,
                "text": self._cut(chunk.text),
            }
            if chain.parents:
                parent = chain.parents[chain.parent_of[i]]
                row["parent_position"] = parent.position
                row["parent_text"] = self._cut(parent.text)
            if chain.contexts is not None:
                applied = chain.contexts.applied[i]
                if applied is not None:
                    row["context_text"] = self._cut(applied.context_text)
                    row["context_label"] = self._mark(applied)
            rows.append(row)
        return rows

    def _lend(self, chain: _Chain, option: str) -> Lent:
        """The embedding model of the chain, lent once per run (the semantic chunking and the
        Embedding stage share it)."""
        if option not in chain.lent:
            chain.lent[option] = self.deps.embedder(option)
        return chain.lent[option]

    def _chunking_other(self, chain: _Chain, stage: Stage, size: int) -> _Result:
        """V1.2 story 6 (CAP-4): `semantic`, `parent_child` and `contextual` read the same
        documents as `paragraphs` (the corpus, or the work copy), never the brick's index."""
        text, count = self._text, self._int
        copy = self.deps.work_copy if self._reads_work_copy() else None
        documents = workcopy.documents(self.deps.content, self.deps.lang, copy)
        source = self._text("chunking.source_work_copy" if copy else "chunking.source_corpus")
        parents = chunk_documents(documents, size)
        if not parents:
            raise StageFailed(Message("rag_lab.chunking.no_chunks"))
        option = stage.option
        chain.chunking_key = {"option": option}
        if option == "semantic":
            return self._semantic(chain, documents, parents, size, source)
        if option == "parent_child":
            children, parent_of = chunk_parent_child(parents, CHILD_MAX_CHARS)
            chain.chunks, chain.parents, chain.parent_of = children, parents, parent_of
            return self._chunking_result(
                chain,
                size,
                source,
                "chunking.output_parent_child",
                [
                    (text("chunking.parents"), count(len(parents))),
                    (text("chunking.child_max"), text("chunking.characters", n=CHILD_MAX_CHARS)),
                ],
                children=self._count(len(children), "child"),
                child=count(CHILD_MAX_CHARS),
                parents=self._count(len(parents), "parent"),
            )
        # contextual: the `paragraphs` chunks, each with the context of its fingerprint
        book = rag_contexts.load_book(self.deps.lang, self.deps.lab_dir)
        matched = rag_contexts.match(parents, book)
        chain.chunks, chain.contexts = parents, matched
        chain.chunking_key["contexts"] = matched.fingerprint
        header = book.header
        found = len(parents) - matched.missing
        result = self._chunking_result(
            chain,
            size,
            source,
            "chunking.output_contextual",
            [
                (text("chunking.with_context"), count(found)),
                (text("chunking.without_context"), count(matched.missing)),
                (text("chunking.ignored_contexts"), count(matched.ignored)),
                (
                    text("chunking.context_origin"),
                    self._mark(rag_contexts.Applied("", header.author, header.method, header.model))
                    if header is not None
                    else text("chunking.no_contexts"),
                ),
            ],
            with_context=self._count(found, "extract"),
        )
        if book.error and book.shipped is None:
            result.warning_text = text("chunking.contexts_unreadable", error=book.error)
        elif matched.missing or matched.ignored:
            result.warning_text = text(
                "chunking.contexts_stale",
                missing=self._count(matched.missing, "extract"),
                ignored=count(matched.ignored),
            )
        # Built beforehand: what the build cost is the record of the file (never this run's).
        if header is not None:
            result.costs = [
                StageCost(
                    "build",
                    "chunking",
                    header.tokens,
                    header.duration_ms,
                    measured_at_build=True,
                    note_text=Message("rag_lab.costs.contexts_measure", model=header.model),
                )
            ]
        return result

    def _semantic(
        self,
        chain: _Chain,
        documents: Sequence[DocText],
        paragraphs: list[Chunk],
        size: int,
        source: str,
    ) -> _Result:
        """Chunks cut where the similarity between neighbouring sentences drops, by the
        embedding model of the chain; without a usable one, the `paragraphs` chunks and a
        warning."""
        text, count = self._text, self._int
        embedding = chain.pipeline.find("embedding")
        assert embedding is not None  # `check_pipeline` keeps the fixed head
        try:
            lent = self._lend(chain, embedding.option)
        except (StageFailed, StageSkipped) as unusable:
            chain.chunks = paragraphs
            chain.chunking_key = None  # the `paragraphs` chunks: their vectors, their cache
            result = self._chunking_result(chain, size, source)
            result.warning_text = text(
                "chunking.semantic_fallback", reason=unusable.render(self._lang)
            )
            return result
        embedder: Embedder = lent.model

        def embed(sentences: list[str]) -> list[list[float]]:
            out: list[list[float]] = []
            for at in range(0, len(sentences), EMBED_BATCH):
                self._check()
                out += embedder.embed_passages(sentences[at : at + EMBED_BATCH])
            return out

        started = time.monotonic()
        probe = Probe(self.deps.meter)
        try:
            chunks, sentences = chunk_semantic(documents, embed, size, SEMANTIC_PERCENTILE)
        finally:
            cost = self._cost("build", "chunking", probe)
        cost = replace(cost, tokens=sum(self.deps.estimate_tokens(c.text) for c in chunks))
        chain.chunks = chunks
        result = self._chunking_result(
            chain,
            size,
            source,
            "chunking.output_semantic",
            [
                (text("chunking.sentences"), count(sentences)),
                (text("fact.model"), lent.label_text),
                (
                    text("chunking.sentences_duration"),
                    ms_text(_ms(time.monotonic() - started), self._lang),
                ),
            ],
            sentences=self._count(sentences, "sentence"),
        )
        result.costs = [cost]
        return result

    def _embedding(
        self, chain: _Chain, stage: Stage, progress: Callable[[int, int], None]
    ) -> _Result:
        lent = self._lend(chain, stage.option)
        embedder: Embedder = lent.model
        chain.embedder_label = lent.label_text
        self._check()
        text = self._text
        n = self._int(len(chain.chunks))
        passages_n = self._count(len(chain.chunks), "passage")
        vectors_n = self._count(len(chain.chunks), "vector")
        facts = [
            (text("fact.model"), lent.label_text),
            (text("fact.dimensions"), self._int(embedder.dims)),
        ]
        truncated: int | None = None  # the passages the model cut, when it says so
        costs: list[StageCost] = []
        if self._uses_brick_index(chain):
            if self.deps.brick_index_error is None:
                passages = text("embedding.brick_passages", passages=passages_n)
                costs.append(
                    recorded_cost(brick_costs_path(self.deps.brick_index), "embedding", "embedding")
                )
            else:
                passages = text("embedding.brick_unusable")
        else:
            identity = self.deps.identity(stage.option)
            digest = rag_index.corpus_digest(chain.chunks)
            chain.key = cache_key(identity, chain.chunk_max_chars, digest, chain.chunking_key)
            folder = self.deps.lab_dir / chain.key
            vectors = read_vectors(folder, chain.chunks, embedder.dims)
            if vectors is not None:
                passages = text("embedding.cached", vectors=vectors_n, key=chain.key)
                costs.append(recorded_cost(folder, "embedding", "embedding"))
                facts.append((text("fact.passages"), text("embedding.cached_fact", n=n)))
                truncated = read_truncated(folder)
            else:
                vectors = []
                total = len(chain.chunks)
                passages_of = self._passages(chain)
                started = time.monotonic()
                truncated = 0 if getattr(embedder, "max_tokens", None) else None
                probe = Probe(self.deps.meter)
                try:
                    for at in range(0, total, EMBED_BATCH):
                        self._check()
                        vectors += embedder.embed_passages(passages_of[at : at + EMBED_BATCH])
                        # Lot 5c-1: the passages of this batch the model cut at `max_tokens`.
                        cut = getattr(embedder, "last_truncated", None)
                        known = truncated is not None and isinstance(cut, int)
                        truncated = truncated + cut if known else None
                        progress(min(at + EMBED_BATCH, total), total)
                finally:
                    built = self._cost("build", "embedding", probe, self._tokens(passages_of))
                if len(vectors) != total or any(len(v) != embedder.dims for v in vectors):
                    raise StageFailed(Message("rag_lab.embedding.wrong_dims", dims=embedder.dims))
                write_vectors(folder, chain.chunks, vectors, identity, truncated)
                write_build_cost(folder, "embedding", built)
                costs.append(built)
                seconds = time.monotonic() - started
                passages = text(
                    "embedding.computed",
                    passages=passages_n,
                    duration=ms_text(_ms(seconds), self._lang),
                    key=chain.key,
                )
                facts.append(
                    (text("fact.passages"), text("embedding.computed_fact", passages=passages_n))
                )
            chain.vectors = vectors
        warning = self._truncation(embedder, truncated, len(chain.chunks))
        probe = Probe(self.deps.meter)
        try:
            vector = embedder.embed_queries([self.question])[0]
        finally:
            costs.append(
                self._cost("query", "embedding", probe, self.deps.estimate_tokens(self.question))
            )
        if not any(vector):
            raise StageFailed(Message("rag_lab.embedding.null_vector"))
        chain.embedder = embedder
        chain.query_vector = vector
        separator = text("list_separator")
        shown = separator.join(score_text(v, self._lang) for v in vector[:4])
        facts.append((text("fact.provenance"), self._provenance(lent)))
        return _Result(
            input_text=text(
                "embedding.input",
                question=self.question,
                extracts=self._count(len(chain.chunks), "extract"),
            ),
            output_text=text(
                "embedding.output", n=self._int(len(vector)), shown=shown, passages=passages
            ),
            facts=facts,
            borrowed=lent.borrowed,
            warning_text=warning,
            costs=costs,
        )

    def _cost(self, phase: str, kind: str, probe: Probe, tokens: int | None = None) -> StageCost:
        """V1.2 story 3: the part's cost, its probe stopped: its duration, its footprint, and
        0 dollars (a local model bills nothing)."""
        duration, impact = probe.stop()
        return StageCost(phase, kind, tokens, duration, 0.0, impact)

    def _tokens(self, passages: Sequence[str]) -> int:
        return sum(self.deps.estimate_tokens(p) for p in passages)

    def _passages(self, chain: _Chain) -> list[str]:
        """What is embedded and indexed for each chunk: its title and text, with its context
        first when the chain is `contextual` (V1.2 story 6)."""
        contexts = chain.contexts.contexts if chain.contexts is not None else None
        return [
            rag_index.passage_text(c, contexts[i] if contexts else "")
            for i, c in enumerate(chain.chunks)
        ]

    def _truncation(self, embedder: Embedder, truncated: int | None, total: int) -> str | None:
        """Lot 5c-1: « 3 chunks sur 29 dépassent 512 tokens, tronqués », a warning (never an
        error) when the model cut passages at its `max_tokens`; `None` when none was cut or
        the model does not say (fastembed, the brick's index read as it is)."""
        max_tokens = getattr(embedder, "max_tokens", None)
        if not truncated or not isinstance(max_tokens, int):
            return None
        return self._text(
            "embedding.truncated",
            count=truncated,  # « 1 chunk sur 16 dépasse … », « 3 chunks sur 16 dépassent … »
            chunks=self._count(truncated, "chunk"),
            total=self._int(total),
            max=self._int(max_tokens),
        )

    def _provenance(self, lent: Lent) -> str:
        return self.deps.texts.borrowed_text if lent.borrowed else self.deps.texts.loaded_text

    def _vector_store(self, chain: _Chain, stage: Stage) -> _Result:
        if chain.embedder is None:
            raise StageFailed(Message("rag_lab.vector_store.no_embedder"))
        n = len(chain.chunks)
        dims = chain.embedder.dims
        text, count = self._text, self._int
        vectors_fact, metric_fact = text("fact.vectors"), text("fact.metric")
        if self._uses_brick_index(chain):
            if self.deps.brick_index_error is not None:
                raise StageFailed(self.deps.brick_index_error)
            path = self.deps.brick_index
            meta = rag_index.read_meta(path)
            chain.store = _SqliteStore(path, chain.embedder)
            return _Result(
                costs=[],  # built with the vectors: the Embedding's record has it all
                input_text=text(
                    "vector_store.brick_input",
                    vectors=self._count(meta.chunks, "vector"),
                    dims=count(meta.dims),
                    model=meta.embedding_model_id,
                    date=meta.built_at[:10],
                ),
                output_text=text("vector_store.brick_output", file=path.name),
                facts=[
                    (text("fact.file"), str(path)),
                    (vectors_fact, count(meta.chunks)),
                    (metric_fact, text("vector_store.cosine")),
                ],
            )
        if chain.vectors is None:
            raise StageFailed(Message("rag_lab.vector_store.no_vectors"))
        vectors_text = text(
            "vector_store.vectors", vectors=self._count(n, "vector"), dims=count(dims)
        )
        input_text = text("vector_store.input", vectors=vectors_text)
        if stage.option == "memory":
            probe = Probe(self.deps.meter)
            try:
                chain.store = MemoryStore(chain.chunks, chain.vectors)
            finally:
                cost = self._cost("build", "vector_store", probe)
            size = n * dims * 4
            return _Result(
                costs=[cost],
                input_text=input_text,
                output_text=text("vector_store.memory_output", size=size_text(size, self._lang)),
                facts=[(vectors_fact, count(n)), (metric_fact, text("vector_store.cosine_dot"))],
            )
        if stage.option == "sqlite_vec":
            path = self.deps.lab_dir / chain.key / INDEX_FILE
            built = text("vector_store.reread")
            try:
                meta = rag_index.read_meta(path) if path.is_file() else None
            except Exception:  # noqa: BLE001 - rebuilt below
                meta = None
            fits = (
                meta is not None
                and meta.chunks == n
                and meta.dims == dims
                and meta.chunk_max_chars == chain.chunk_max_chars
                and meta.corpus_sha256 == rag_index.corpus_digest(chain.chunks)
            )
            costs_at = self.deps.lab_dir / chain.key
            cost = recorded_cost(costs_at, "vector_store:sqlite_vec", "vector_store")
            if not fits:
                self._check()
                probe = Probe(self.deps.meter)
                try:
                    rag_index.write_index(
                        path,
                        chain.chunks,
                        chain.vectors,
                        model_id=chain.embedder.model_id,
                        dims=dims,
                        chunk_max_chars=chain.chunk_max_chars,
                    )
                finally:
                    cost = self._cost("build", "vector_store", probe)
                write_build_cost(costs_at, "vector_store:sqlite_vec", cost)
                built = text("vector_store.built", vectors=self._count(n, "vector"))
            chain.store = _SqliteStore(path, chain.embedder)
            return _Result(
                costs=[cost],
                input_text=input_text,
                output_text=text("vector_store.sqlite_output", state=built, key=chain.key),
                facts=[
                    (text("fact.file"), str(path)),
                    (vectors_fact, count(n)),
                    (metric_fact, text("vector_store.cosine")),
                ],
            )
        if stage.option in LIBRARIES:
            label = LIBRARIES[stage.option][1]
            imported = self.deps.importer(stage.option)
            self._check()
            folder = self.deps.lab_dir / chain.key
            key = f"vector_store:{stage.option}"
            probe = Probe(self.deps.meter)
            try:
                if stage.option == "faiss":
                    store: Any = FaissStore(imported.module, folder, chain.vectors)
                    kind = text("vector_store.faiss_kind")
                else:
                    store = LanceStore(imported.module, folder, chain.vectors)
                    kind = text("vector_store.lancedb_kind")
            finally:
                measured = self._cost("build", "vector_store", probe)
            chain.store = store
            if store.built:
                cost = measured
                write_build_cost(folder, key, cost)
            else:
                cost = recorded_cost(folder, key, "vector_store")
            vectors_n = self._count(n, "vector")
            state = text(
                "vector_store.built" if store.built else "vector_store.reread_count",
                vectors=vectors_n,
            )
            return _Result(
                costs=[cost],
                input_text=input_text,
                output_text=text(
                    "vector_store.library_output",
                    library=label,
                    state=state,
                    kind=kind,
                    key=chain.key,
                ),
                facts=[
                    (text("fact.folder"), str(store.path)),
                    (vectors_fact, count(n)),
                    *imported.facts,
                ],
            )
        raise StageFailed(Message("rag_lab.vector_store.unknown", option=stage.option))

    def _query(
        self, chain: _Chain, stage: Stage, step_id: str, progress: Callable[[int, int], None]
    ) -> _Result:
        """V1.2 story 5 (CAP-3): the workshop's active model turns the question into the
        queries the searches run (`rewrite`: one, `decompose`: several, `follow_up`: one that
        stands alone, `hyde`: a hypothetical answer). Without a model, without a previous
        question for `follow_up`, or when the model gives nothing usable, the question goes on
        as typed and the stage says why (skipped, or a warning); a failed call is a soft
        failure."""
        option, text = stage.option, self._text
        history = [h for h in self.deps.history if h.strip()][-HISTORY_MAX:]
        shown = text("query.input", question=self._quoted(self.question))
        if option == "follow_up":
            shown += " " + text(
                "query.input_history", history=join([self._quoted(h) for h in history], self._lang)
            )
        unchanged = _Result(input_text=shown, output_text=text("query.unchanged"))
        if option == "follow_up" and not history:
            unchanged.output_text = text("query.no_history")
            raise StageSkipped(Message("rag_lab.query.no_history_reason"), result=unchanged)
        if self.deps.generator is None:
            raise StageSkipped(Message("rag_lab.query.no_model"), result=unchanged)
        self._check()
        user = self.question
        if option == "follow_up":
            user = text(
                "query.follow_up_user",
                history="\n".join(f"- {h}" for h in history),
                question=self.question,
            )
        ask = GenerationAsk(
            context_text="",
            question=user,
            step_id=step_id,
            progress=progress,
            cancelled=self.deps.cancelled,
            instruction=text(f"query.instruction.{option}", max=SUBQUERIES_MAX),
            reserve=QUERY_RESERVE,
        )
        try:
            got = self.deps.generator(ask)
        except StageSkipped as skipped:
            skipped.result = skipped.result or unchanged
            raise
        result = _Result(
            input_text=shown,
            output_text=text("query.unchanged"),
            facts=[(text("fact.model"), got.model_label)],
            prompt_text=got.prompt_text,
        )
        result.costs = [
            StageCost(
                "query",
                "query",
                got.prompt_tokens + got.output_tokens,
                got.duration_ms,
                got.cost_usd,
                got.impact,
                note_text=None
                if got.cost_usd is not None or got.impact is not None
                else Message("rag_lab.costs.generation_unpriced"),
            )
        ]
        if got.status == "cancelled":
            raise LabCancelled(result)
        if got.status == "too_long":
            result.costs = []
            raise StageFailed(
                Message("rag_lab.query.too_long", window=self._int(got.window)),
                soft=True,
                result=result,
            )
        if got.status not in ("completed", "limit"):
            raise StageFailed(
                got.error_text or Message("rag_lab.query.model_error"), soft=True, result=result
            )
        queries = parse_queries(option, got.answer_text)
        if not queries:
            result.warning_text = text("query.empty")
            return result
        chain.queries = queries
        chain.as_document = option == "hyde"
        result.queries = queries
        if len(queries) == 1:
            result.output_text = queries[0]
        else:
            result.output_text = "\n".join(f"{n}. {q}" for n, q in enumerate(queries, start=1))
        result.facts.append((text("fact.queries"), self._int(len(queries))))
        if option == "hyde":
            result.facts.append((text("fact.embedded_as"), text("query.as_passage")))
        return result

    def _vector_search(self, chain: _Chain, stage: Stage) -> _Result:
        if chain.store is None or chain.query_vector is None:
            raise StageFailed(Message("rag_lab.vector_search.no_store"))
        k = param(stage, "candidates", self.deps.catalog)
        if chain.queries:  # V1.2 story 5: the queries the query understanding produced
            vectors = self._embed_queries(chain)
            found = [chain.store.search(vector, k) for vector in vectors]
            hits, sources = self._merged(chain, "vector_search", found, k)
        else:
            hits, sources = chain.store.search(chain.query_vector, k), {}
        items = []
        for rank, (chunk_id, score) in enumerate(hits, start=1):
            chunk = chain.chunks[chunk_id - 1]
            items.append(
                Item(
                    chunk_id,
                    chunk.doc_id,
                    chunk.title_text,
                    chunk.text,
                    score,
                    rank=rank,
                    sources=sources.get(chunk_id, []),
                )
            )
        chain.lists.append(items)
        chain.list_kinds.append("vector_search")
        best = items[0].score if items else None
        worst = items[-1].score if items else None
        text = self._text
        return _Result(
            input_text=text(
                "vector_search.input", vectors=self._count(len(chain.chunks), "vector")
            ),
            output_text=text(
                "vector_search.output",
                extracts=self._count(len(items), "extract"),
                best=score_text(best, self._lang),
                worst=score_text(worst, self._lang),
            ),
            facts=[
                (text("fact.requested"), self._int(k)),
                (text("fact.found"), self._int(len(items))),
                *self._queries_fact(chain),
            ],
            items=items,
        )

    def _embed_queries(self, chain: _Chain) -> list[list[float]]:
        """V1.2 story 5: the vector of each query, by the chain's embedding model; a
        hypothetical answer (HyDE) is embedded as a passage is, not as a question."""
        embedder = chain.embedder
        if embedder is None:
            raise StageFailed(Message("rag_lab.vector_search.no_store"))
        queries = chain.queries
        if chain.as_document:
            vectors = embedder.embed_passages(queries)
        else:
            vectors = embedder.embed_queries(queries)
        if len(vectors) != len(queries) or not all(any(v) for v in vectors):
            raise StageFailed(Message("rag_lab.embedding.null_vector"))
        return vectors

    def _merged(
        self, chain: _Chain, kind: str, found: list[list[tuple[int, float]]], k: int
    ) -> tuple[list[tuple[int, float]], dict[int, list[dict[str, Any]]]]:
        """V1.2 story 5: a search run once per query gives one list; with several queries the
        lists are fused by reciprocal rank (as the Fusion stage does), the first `k` kept, and
        each excerpt says where each query ranked it. One query: its list as it is."""
        if len(found) == 1:
            return found[0], {}
        label = self.deps.texts.stages[kind].label_text
        ranks = [{c: (r, sc) for r, (c, sc) in enumerate(hits, start=1)} for hits in found]
        fused = rrf([[c for c, _ in hits] for hits in found])[:k]
        sources = {
            chunk_id: [
                {
                    "kind": kind,
                    "label_text": f"{label} {n}",
                    "rank": seen.get(chunk_id, (None, None))[0],
                    "score": seen.get(chunk_id, (None, None))[1],
                }
                for n, seen in enumerate(ranks, start=1)
            ]
            for chunk_id, _ in fused
        }
        return [(c, round(score, 4)) for c, score in fused], sources

    def _queries_fact(self, chain: _Chain) -> list[tuple[str, str]]:
        if not chain.queries:
            return []
        return [(self._text("fact.queries"), self._int(len(chain.queries)))]

    def _rerank(self, chain: _Chain, stage: Stage, progress: Callable[[int, int], None]) -> _Result:
        candidates = chain.ranked
        if not candidates:
            raise StageSkipped(Message("rag_lab.rerank.no_candidates"))
        lent = self.deps.reranker(stage.option)
        reranker: Reranker = lent.model
        passages = [f"{c.title_text}\n{c.text}" for c in candidates]
        probe = Probe(self.deps.meter)
        try:
            raw = reranker.score(self.question, passages, self.deps.cancelled, progress)
        except RerankCancelled:
            raise LabCancelled() from None
        except Exception as exc:  # noqa: BLE001 - the chain goes on with the search's order
            raise StageFailed(
                Message(
                    "rag_lab.rerank.failed",
                    error=type(exc).__name__,
                    cause=exception_text(exc, self._lang),
                ),
                soft=True,
            ) from exc
        finally:
            tokens = sum(self.deps.estimate_tokens(f"{self.question}\n{p}") for p in passages)
            rerank_cost = self._cost("query", "rerank", probe, tokens)
        if len(raw) != len(candidates):
            scores_n, candidates_n = len(raw), len(candidates)
            raise StageFailed(
                Message(
                    "rag_lab.rerank.mismatch",
                    scores=Lazy(lambda lang: count_text(scores_n, "score", lang)),
                    candidates=Lazy(lambda lang: count_text(candidates_n, "candidate", lang)),
                ),
                soft=True,
            )
        scores = []
        for item in raw:
            try:
                value = float(item.score)
            except (TypeError, ValueError):
                raise StageFailed(Message("rag_lab.rerank.not_a_number"), soft=True) from None
            scores.append(min(1.0, max(0.0, value)))
        cut = sum(1 for item in raw if getattr(item, "truncated", False) is True)
        # Stable, as the brick's: the reranker's score, then the search's rank. Lot 5c-2: on
        # the score as the model gives it (bounded), rounded for display only: a reranker's
        # saturated probabilities (0.99991, 0.99995) would otherwise tie at 1.000.
        order = sorted(range(len(candidates)), key=lambda i: (-scores[i], candidates[i].rank))
        items = []
        for rank, i in enumerate(order, start=1):
            c = candidates[i]
            items.append(
                Item(
                    c.chunk_id,
                    c.doc_id,
                    c.title_text,
                    c.text,
                    round(scores[i], 3),
                    rank=rank,
                    before=c.rank,
                    sources=c.sources
                    or [
                        {
                            "kind": self._made_by(chain),
                            "label_text": self.deps.texts.stages[self._made_by(chain)].label_text,
                            "rank": c.rank,
                            "score": c.score,
                        }
                    ],
                )
            )
        chain.lists[-1] = items
        moved = max(items, key=lambda x: (x.before or 0) - x.rank)
        text = self._text
        climb = (
            text(
                "rerank.climb",
                title=moved.title_text,
                before=rank_text(moved.before or 0, self._lang),
                after=rank_text(moved.rank, self._lang),
            )
            if (moved.before or 0) > moved.rank
            else text("rerank.unchanged")
        )
        return _Result(
            input_text=text("rerank.input", candidates=self._count(len(candidates), "candidate")),
            output_text=text(
                "rerank.output",
                candidates=self._count(len(items), "reordered_candidate"),
                climb=climb,
            ),
            facts=[
                (text("fact.model"), lent.label_text),
                (text("fact.pairs"), self._int(len(candidates))),
                *self._score_reading(reranker),
                (text("fact.provenance"), self._provenance(lent)),
            ],
            items=items,
            borrowed=lent.borrowed,
            warning_text=self._pairs_cut(reranker, cut, len(candidates)),
            costs=[rerank_cost],
        )

    def _score_reading(self, reranker: Reranker) -> list[tuple[str, str]]:
        """Lot 5c-2: how the model's figure became the score (the sigmoid of a logit, or the
        model's own probability), as a fact; none when the reranker does not say."""
        reading = getattr(reranker, "score_reading", None)
        if reading not in ("sigmoid", "probability"):
            return []
        return [(self._text("fact.score_reading"), self._text(f"rerank.reading.{reading}"))]

    def _pairs_cut(self, reranker: Reranker, cut: int, total: int) -> str | None:
        """Lot 5c-2: « 2 candidats sur 8 dépassent la longueur d'une paire : coupés à 1 024
        tokens… », a warning (never an error); `None` when no pair was cut or the reranker
        does not say its length."""
        max_tokens = getattr(reranker, "max_tokens", None)
        if not cut or not isinstance(max_tokens, int):
            return None
        return self._text(
            "rerank.truncated",
            count=cut,
            candidates=self._count(cut, "candidate"),
            total=self._int(total),
            max=self._int(max_tokens),
        )

    def _made_by(self, chain: _Chain) -> str:
        """The kind of the stage that made the chain's current list (a search or the fusion)."""
        return chain.list_kinds[-1] if chain.list_kinds else "vector_search"

    def _lexical_index(self, chain: _Chain) -> _Result:
        """B2: BM25's inverted index of the Chunks (`LexicalIndex`), kept for the search."""
        if not chain.chunks:
            raise StageFailed(Message("rag_lab.lexical_search.no_chunks"))
        passages = self._passages(chain)
        probe = Probe(self.deps.meter)
        try:
            built = chain.lexical = lexical_index(passages, self.deps.lang)
        finally:
            index_cost = self._cost("build", "lexical_index", probe)
        # The tokens BM25 indexed: its terms' occurrences, the tokenizer's own count.
        index_cost = replace(index_cost, tokens=built.occurrences)
        text, count = self._text, self._int
        # BM25 normalises by this mean: one decimal, as it reads it.
        mean = number(built.mean if built.occurrences else 0, self._lang, 1)
        return _Result(
            costs=[index_cost],
            input_text=text(
                "lexical_index.input", extracts=self._count(len(chain.chunks), "extract")
            ),
            output_text=text(
                "lexical_index.output",
                terms=count(built.vocabulary),
                occurrences=count(built.occurrences),
                mean=mean,
            ),
            facts=[
                (text("lexical_index.chunks"), count(built.n)),
                (text("lexical_index.terms"), count(built.vocabulary)),
                (text("lexical_index.occurrences"), count(built.occurrences)),
                (text("lexical_index.mean"), text("lexical_index.mean_value", n=mean)),
                (
                    text("lexical_index.params"),
                    text(
                        "lexical_index.params_value",
                        k1=number(BM25_K1, self._lang, 1),
                        b=number(BM25_B, self._lang, 2),
                    ),
                ),
                (text("fact.model"), text("lexical_index.no_model")),
            ],
        )

    def _lexical_search(self, chain: _Chain, stage: Stage) -> _Result:
        if not chain.chunks:
            raise StageFailed(Message("rag_lab.lexical_search.no_chunks"))
        k = param(stage, "candidates", self.deps.catalog)
        if chain.lexical is None:  # its part not run (never in a chain run): built here
            self._lexical_index(chain)
        queries = chain.queries or [self.question]
        per_query = []
        for query in queries:
            scored = bm25_scores(chain.lexical, query, self.deps.lang)
            per_query.append(
                [
                    (chunk_id, round(score, 3))
                    for score, chunk_id in sorted(
                        ((score, i + 1) for i, score in enumerate(scored) if score > 0),
                        key=lambda x: (-round(x[0], TIE_DIGITS), x[1]),
                    )[:k]
                ]
            )
        found, sources = self._merged(chain, "lexical_search", per_query, k)
        items = []
        for rank, (chunk_id, score) in enumerate(found, start=1):
            chunk = chain.chunks[chunk_id - 1]
            items.append(
                Item(
                    chunk_id,
                    chunk.doc_id,
                    chunk.title_text,
                    chunk.text,
                    score,
                    rank=rank,
                    sources=sources.get(chunk_id, []),
                )
            )
        chain.lists.append(items)
        chain.list_kinds.append("lexical_search")
        text = self._text
        terms = [t for query in queries for t in bm25_terms(query, self.deps.lang)]
        words = ", ".join(self._quoted(w) for w in dict.fromkeys(terms))
        return _Result(
            input_text=text(
                "lexical_search.input",
                words=words or text("lexical_search.no_words"),
                extracts=self._count(len(chain.chunks), "extract"),
            ),
            output_text=text("lexical_search.output", extracts=self._count(len(items), "extract")),
            facts=[
                (text("fact.requested"), self._int(k)),
                (text("fact.found"), self._int(len(items))),
                *self._queries_fact(chain),
            ],
            items=items,
        )

    def _fusion(self, chain: _Chain, stage: Stage) -> _Result:
        if len(chain.lists) < 2:
            raise StageFailed(Message("rag_lab.fusion.needs_two"))
        kinds = chain.list_kinds[-len(chain.lists) :]
        found: dict[int, Item] = {}
        ranks: dict[str, dict[int, tuple[int, float | None]]] = {}
        for kind, ranked in zip(kinds, chain.lists, strict=True):
            ranks[kind] = {i.chunk_id: (i.rank, i.score) for i in ranked}
            for item in ranked:
                found.setdefault(item.chunk_id, item)
        fused = rrf([[i.chunk_id for i in ranked] for ranked in chain.lists])
        items = []
        for rank, (chunk_id, score) in enumerate(fused, start=1):
            item = found[chunk_id]
            sources = [
                {
                    "kind": kind,
                    "label_text": self.deps.texts.stages[kind].label_text,
                    "rank": ranks[kind].get(chunk_id, (None, None))[0],
                    "score": ranks[kind].get(chunk_id, (None, None))[1],
                }
                for kind in kinds
            ]
            items.append(
                Item(
                    chunk_id,
                    item.doc_id,
                    item.title_text,
                    item.text,
                    round(score, 4),
                    rank=rank,
                    sources=sources,
                )
            )
        both = sum(1 for chunk_id, _ in fused if all(chunk_id in ranks[k] for k in kinds))
        text = self._text
        sizes = join([f"{len(r)}" for r in chain.lists], self._lang)
        chain.lists = [items]
        chain.list_kinds = ["fusion"]
        return _Result(
            input_text=text("fusion.input", sizes=sizes),
            output_text=text(
                "fusion.output",
                extracts=self._count(len(items), "extract"),
                both=self._int(both),
                found=agreed("fusion.found", both, self._lang),
                k=RRF_K,
            ),
            facts=[
                (text("fact.constant"), str(RRF_K)),
                (text("fact.fused"), self._int(len(items))),
            ],
            items=items,
        )

    def _context(
        self,
        chain: _Chain,
        stage: Stage,
        step_id: str = "",
        tick: Callable[[int, int], None] = lambda *_: None,
    ) -> _Result:
        if stage.option == "agent_loop":  # V1.2 story 11
            return self._context_agent(chain, step_id, tick)
        if stage.option == "section_tree":
            return self._context_tree(chain, step_id, tick)
        if stage.option == "graph_search":  # V1.2 story 13
            return self._context_graph(chain, step_id, tick)
        if stage.option in CORPUS_OPTIONS:
            return self._context_corpus(chain, stage)
        ranked = chain.ranked
        if ranked is None:
            raise StageFailed(Message("rag_lab.context.nothing"))
        top_k = param(stage, "top_k", self.deps.catalog)
        if chain.parents:
            return self._context_parents(chain, stage, ranked, top_k)
        picks = [
            Item(
                c.chunk_id,
                c.doc_id,
                c.title_text,
                c.text,
                c.score,
                rank=rank,
                before=c.rank,
                sources=c.sources,
            )
            for rank, c in enumerate(ranked[:top_k], start=1)
        ]
        return self._context_build(chain, stage, ranked, picks)

    def _context_parents(
        self, chain: _Chain, stage: Stage, ranked: list[Item], top_k: int
    ) -> _Result:
        """V1.2 story 6: the children were searched, their parents are returned, once each,
        in the order their best child ranks, `top_k` at most. Story 7: the budget, the order
        and the compression then work on these parents, as on any passage."""
        seen: set[int] = set()
        picks: list[Item] = []
        read = 0
        for child in ranked:
            read += 1
            parent_id = chain.parent_of[child.chunk_id - 1]
            if parent_id in seen:
                continue
            seen.add(parent_id)
            parent = chain.parents[parent_id]
            picks.append(
                Item(
                    child.chunk_id,
                    parent.doc_id,
                    parent.title_text,
                    parent.text,
                    child.score,
                    rank=len(picks) + 1,
                    before=child.rank,
                    sources=child.sources,
                )
            )
            if len(picks) == top_k:
                break
        # Children sharing a parent: fewer than `top_k` parents among the candidates searched.
        short = None
        if len(picks) < min(top_k, len(ranked)):
            short = self._text(
                "context.parents_short",
                kept=self._int(len(picks)),
                top_k=self._int(top_k),
                read=self._int(read),
            )
        return self._context_build(chain, stage, ranked, picks, read=read, warning=short)

    # -- V1.2 story 7 (CAP-5): the context's budget, order and compression --

    @staticmethod
    def _edge_positions(count: int) -> list[int]:
        """The position in the context of the passage of each relevance rank (from 1): the
        best first, the second last, the third second, the fourth last but one, and so on."""
        positions, left, right = [], 1, count
        for rank in range(1, count + 1):
            if rank % 2:
                positions.append(left)
                left += 1
            else:
                positions.append(right)
                right -= 1
        return positions

    @classmethod
    def _layout(
        cls, parts: Sequence[tuple[Item, str]], ordered: bool
    ) -> list[tuple[Item, str, int]]:
        """The passages `(item, raw text)` in the order of the context, with their position;
        `ordered`: extremities first (three passages or more), else the relevance order."""
        count = len(parts)
        positions = (
            cls._edge_positions(count) if ordered and count >= 3 else list(range(1, count + 1))
        )
        placed = [(item, raw, pos) for (item, raw), pos in zip(parts, positions, strict=True)]
        return sorted(placed, key=lambda p: p[2])

    def _assemble(self, parts: Sequence[tuple[Item, str]], ordered: bool) -> str:
        """The context text: the introduction, then each passage formatted at its position."""
        if not parts:
            return ""
        content = self.deps.content
        excerpts = [
            content.excerpt(pos, item.title_text, raw)
            for item, raw, pos in self._layout(parts, ordered)
        ]
        return "\n\n".join([content.intro_text, *excerpts])

    @staticmethod
    def _cut_at(raw: str, limit: int) -> str:
        """`raw[:limit]` cut at its last end of sentence, else at its last word, plus the
        mark; empty when nothing of the text is left."""
        head = raw[:limit]
        ends = [m.end() for m in _SENTENCE_END.finditer(head)]
        if ends:
            head = head[: ends[-1]]
        else:
            space = max(head.rfind(" "), head.rfind("\n"))
            head = head[:space] if space > 0 else head
        head = head.rstrip()
        return f"{head} {CUT_MARK}" if head else ""

    def _cut_to_fit(
        self, whole: list[tuple[Item, str]], item: Item, budget: int, ordered: bool
    ) -> str | None:
        """The longest start of `item.text`, cut as `_cut_at` does, with which the context
        still holds in `budget` tokens, or `None` if not even a word fits."""
        estimate = self.deps.estimate_tokens

        def fits(cut: str) -> bool:
            return bool(cut) and estimate(self._assemble([*whole, (item, cut)], ordered)) <= budget

        raw = item.text
        low, high = 0, len(raw) - 1  # the longest limit whose cut fits (the cut grows with it)
        while low < high:
            mid = (low + high + 1) // 2
            if fits(self._cut_at(raw, mid)):
                low = mid
            else:
                high = mid - 1
        cut = self._cut_at(raw, low)
        return cut if low > 0 and fits(cut) else None

    def _smallest_cut(self, raw: str) -> str:
        """The first sentence of a passage (its first words without one), cut: what is kept of
        the best passage when the budget cannot hold even a word of it."""
        first = _SENTENCE_END.search(raw)
        return self._cut_at(raw, first.end() if first else 80) or f"{raw[:80]} {CUT_MARK}"

    def _context_build(
        self,
        chain: _Chain,
        stage: Stage,
        ranked: list[Item],
        picks: list[Item],
        read: int | None = None,
        warning: str | None = None,
    ) -> _Result:
        """The stage's result for the `picks` (the relevance order, `top_k` at most, their raw
        text): `excerpts` keeps them all as they are; the other options fit them in the
        budget, then order them (`order`, `compress`), then compress them (`compress`)."""
        deps, say = self.deps, self._text
        content, estimate = deps.content, deps.estimate_tokens
        if stage.option == "excerpts":
            items = [
                replace(
                    p,
                    text=content.excerpt(p.rank, p.title_text, p.text),
                    placed=p.rank,
                    state="whole",
                )
                for p in picks
            ]
            for item in items:
                item.tokens = estimate(item.text)
            text = "\n\n".join([content.intro_text, *(i.text for i in items)]) if items else ""
            result = _Result(warning_text=warning)
            facts = [self._kept_fact(len(items), len(ranked))]
        else:
            result = self._context_budgeted(stage, picks, warning)
            items, text = result.items, result.output_text
            facts = [self._kept_fact(len(items), len(ranked)), *result.facts]
        chain.context = items
        chain.context_text = text
        if read is not None:
            facts.append((say("fact.children_read"), self._int(read)))
        facts += [
            (say("fact.characters"), self._int(len(text))),
            (say("fact.placement"), content.placement_text),
        ]
        result.facts, result.items = facts, items
        result.input_text = say("context.input", extracts=self._count(len(ranked), "extract"))
        result.output_text = text or say("context.empty")
        self._prompt_preview(result, text)
        return result

    # -- V1.2 story 10: the whole corpus in the context (long context, CAG) --

    def _corpus_documents(self, copy: workcopy.WorkCopy | None) -> list[DocText]:
        return workcopy.documents(self.deps.content, self.deps.lang, copy)

    def _corpus_text(self, documents: Sequence[DocText]) -> str:
        """The introduction, then each document whole, formatted as an excerpt at its rank."""
        content = self.deps.content
        excerpts = [content.excerpt(n, d.title_text, d.text) for n, d in enumerate(documents, 1)]
        return "\n\n".join([content.intro_text, *excerpts])

    def _context_corpus(self, chain: _Chain, stage: Stage) -> _Result:
        """`full_corpus` and `cached_corpus`: the documents the chain reads (the work copy while
        it differs from the shipped corpus), each whole, in their order; no budget, no cut, no
        order, no compression. One item per document (its rank, placed there, whole)."""
        deps, say, count = self.deps, self._text, self._int
        copy = deps.work_copy if self._reads_work_copy() else None
        documents = self._corpus_documents(copy)
        if not documents:
            raise StageFailed(Message("rag_lab.update.empty_corpus"))
        source = say("chunking.source_work_copy" if copy else "chunking.source_corpus")
        items = []
        for rank, doc in enumerate(documents, start=1):
            formatted = deps.content.excerpt(rank, doc.title_text, doc.text)
            items.append(
                Item(
                    rank,
                    doc.doc_id,
                    doc.title_text,
                    doc.text,
                    None,
                    rank=rank,
                    placed=rank,
                    state="whole",
                    tokens=deps.estimate_tokens(formatted),
                )
            )
        text = self._corpus_text(documents)
        chain.context, chain.context_text = items, text
        result = _Result(
            input_text=say(
                "context.corpus_input", documents=self._count(len(items), "document"), source=source
            ),
            output_text=text,
            items=items,
            window=deps.window or None,
        )
        self._prompt_preview(result, text)
        used = result.prompt_tokens or 0
        result.facts = [
            (say("fact.documents"), count(len(items))),
            (say("fact.source"), source),
            (say("fact.characters"), count(len(text))),
            (
                say("fact.window_used"),
                say("context.window_used", used=count(used), window=count(deps.window))
                if deps.window
                else count(used),
            ),
            (say("fact.placement"), deps.content.placement_text),
        ]
        if stage.option == "cached_corpus":
            result.facts.append((say("fact.cache"), say("context.cached_note")))
        return result

    # -- V1.2 story 11: searching without vectors (the agent's tools, PageIndex's tree) --

    def _ask(
        self,
        step_id: str,
        instruction: str,
        context_text: str,
        question: str,
        reserve: int = AGENT_RESERVE,
    ) -> Generated:
        """One short call of the active model (an action, a choice, a summary): its own
        instruction, no reasoning, at most `reserve` tokens written (`AGENT_RESERVE`; V1.2
        story 13: `GRAPH_RESERVE` for the graph's calls)."""
        assert self.deps.generator is not None  # checked by the caller
        ask = GenerationAsk(
            context_text=context_text,
            question=question,
            step_id=step_id,
            progress=lambda *_: None,
            cancelled=self.deps.cancelled,
            instruction=instruction,
            reserve=reserve,
        )
        return self.deps.generator(ask)

    @staticmethod
    def _call_cost(phase: str, kind: str, got: Generated) -> StageCost:
        return StageCost(
            phase,
            kind,
            got.prompt_tokens + got.output_tokens,
            got.duration_ms,
            got.cost_usd,
            got.impact,
            note_text=None
            if got.cost_usd is not None or got.impact is not None
            else Message("rag_lab.costs.generation_unpriced"),
        )

    def _room(self, *texts: str, reserve: int = AGENT_RESERVE) -> int | None:
        """The estimated tokens a short call's prompt has left, `window − reserve` minus the
        texts it always sends; `None` when the window is unknown (no bound)."""
        if not self.deps.window:
            return None
        used = sum(self.deps.estimate_tokens(t) for t in texts)
        return self.deps.window - reserve - used

    @staticmethod
    def _preview(text: str) -> str:
        flat = " ".join(text.split())
        return flat if len(flat) <= PREVIEW_CHARS else flat[: PREVIEW_CHARS - 1].rstrip() + "…"

    def _searchless_items(
        self, found: Sequence[tuple[str, str, str, bool, dict[str, Any]]]
    ) -> list[Item]:
        """The context's elements, in the order read: `(doc_id, title, text, cut, source)`,
        each formatted as an excerpt at its rank."""
        items = []
        for rank, (doc_id, title, raw, cut, source) in enumerate(found, start=1):
            formatted = self.deps.content.excerpt(rank, title, raw)
            items.append(
                Item(
                    rank,
                    doc_id,
                    title,
                    formatted,
                    None,
                    rank=rank,
                    placed=rank,
                    state="cut" if cut else "whole",
                    tokens=self.deps.estimate_tokens(formatted),
                    sources=[source],
                )
            )
        return items

    def _fit_generation(self, items: list[Item]) -> tuple[list[Item], int]:
        """The elements the final prompt (instruction, elements, question) holds in `window −
        reserve`: the oldest left out first. Returns them and how many were left out."""
        deps = self.deps
        if not deps.window:
            return items, 0
        usable = deps.window - deps.reserve
        kept = list(items)

        def tokens(chosen: list[Item]) -> int:
            text = self._context_text(chosen) if chosen else ""
            return sum(deps.estimate_tokens(t) for _, t in deps.prompt_parts(text, self.question))

        while kept and tokens(kept) > usable:
            kept.pop(0)
        for placed, item in enumerate(kept, start=1):
            item.placed = placed
        return kept, len(items) - len(kept)

    def _searchless_end(
        self, chain: _Chain, result: _Result, items: list[Item], warnings: list[tuple[str, str]]
    ) -> None:
        """The elements kept become the chain's context; the warnings, joined, the stage's."""
        kept, dropped = self._fit_generation(items)
        if dropped:
            warnings.append(
                (
                    "agent_context_trimmed",
                    self._text("agent.context_trimmed", count=self._int(dropped)),
                )
            )
        text = self._context_text(kept) if kept else ""
        chain.context, chain.context_text = kept, text
        result.items, result.output_text = kept, text
        result.warning_text = " ".join(w for _, w in warnings) or None
        self._prompt_preview(result, text)

    def _transcript(self, log: Sequence[tuple[str, str]], room: int | None) -> tuple[str, int]:
        """The previous actions and their results, as each round shows them to the model; the
        oldest results replaced by « [résultat écarté] » while it does not hold in `room`."""
        say, estimate = self._text, self.deps.estimate_tokens
        label, gone = say("agent.result_label"), say("agent.result_dropped")
        entries = [f"{line}\n{label}\n{text}" for line, text in log]
        dropped = 0
        if room is not None:
            while dropped < len(entries) and estimate("\n\n".join(entries)) > room:
                entries[dropped] = f"{log[dropped][0]}\n{label}\n{gone}"
                dropped += 1
        return "\n\n".join(entries), dropped

    def _context_agent(
        self, chain: _Chain, step_id: str, tick: Callable[[int, int], None]
    ) -> _Result:
        """`agent_loop` (V1.2 story 11, CAP-7): the model searches the corpus with three tools
        (`list_files`, `grep`, `read_file`) on the chain's documents (the work copy while it
        differs), one action per round, until `ACTION: ANSWER`, `MAX_AGENT_ROUNDS` rounds or
        `UNREADABLE_MAX` unreadable answers in a row. Each tool's result is an element of the
        context, with its source; a refused action is said to the model, never raised. A
        document's text is data: only the model's own lines are read for an action."""
        deps, say, count = self.deps, self._text, self._int
        copy = deps.work_copy if self._reads_work_copy() else None
        docs = self._corpus_documents(copy)
        source = say("chunking.source_work_copy" if copy else "chunking.source_corpus")
        documents = self._count(len(docs), "document")
        result = _Result(
            input_text=say("agent.input", documents=documents, source=source),
            costs=[],
        )
        if deps.generator is None:
            raise StageSkipped(Message("rag_lab.generation.no_model"), result=result)
        tools = agent_tools.Workspace(docs, self._lang, deps.estimate_tokens)
        instruction = say("agent.instruction", max=MAX_AGENT_ROUNDS)
        user = say("agent.user", question=self.question)
        room = self._room(instruction, user)
        turns: list[dict[str, Any]] = []
        log: list[tuple[str, str]] = []
        found: list[tuple[str, str, str, bool, dict[str, Any]]] = []
        stop, streak, last, model, error = "round_limit", 0, "", "", None
        trimmed = 0
        with deps.model_scope():
            for round_ in range(1, MAX_AGENT_ROUNDS + 1):
                if deps.cancelled():
                    stop = "cancelled"
                    break
                transcript, dropped = self._transcript(log, room)
                trimmed = max(trimmed, dropped)
                got = self._ask(step_id, instruction, transcript, user)
                result.costs.append(self._call_cost("query", "agent_loop", got))  # type: ignore[union-attr]
                model = got.model_label or model
                turn: dict[str, Any] = {
                    "round": round_,
                    "action": None,
                    "argument": "",
                    "status": "",
                    "result_preview": "",
                    "result_chars": 0,
                    "result_tokens": 0,
                    "cut": False,
                    "prompt_tokens": got.prompt_tokens,
                    "output_tokens": got.output_tokens,
                    "answer_preview": self._preview(got.answer_text),
                }
                turns.append(turn)
                if got.status in ("cancelled", "too_long") or got.status not in (
                    "completed",
                    "limit",
                ):
                    stop = got.status if got.status in ("cancelled", "too_long") else "error"
                    turn["status"], error = stop, got.error_text
                    break
                last = got.answer_text
                action = agent_tools.parse_action(got.answer_text)
                if action is None:
                    streak += 1
                    turn["status"] = "unreadable"
                    log.append((say("agent.unreadable_line"), say("agent.unreadable_feedback")))
                    tick(round_, MAX_AGENT_ROUNDS)
                    if streak >= UNREADABLE_MAX:
                        stop = "unreadable"
                        break
                    continue
                streak = 0
                turn["action"], turn["argument"] = action.name, action.argument
                if action.name == "answer":
                    turn["status"], stop = "answer", "answer"
                    tick(round_, MAX_AGENT_ROUNDS)
                    break
                if deps.cancelled():  # read before each tool too
                    turn["status"], stop = "cancelled", "cancelled"
                    break
                out = tools.run(action)
                turn["status"] = "ok" if out.ok else "refused"
                turn["result_preview"] = self._preview(out.text)
                turn["result_chars"] = len(out.text)
                turn["result_tokens"] = deps.estimate_tokens(out.text)
                turn["cut"] = out.cut
                line = f"ACTION: {action.name}" + (f" {action.argument}" if action.argument else "")
                log.append((line, out.text))
                if out.ok:
                    found.append(self._agent_element(round_, action, out))
                tick(round_, MAX_AGENT_ROUNDS)
        rounds = len(turns)
        warnings: list[tuple[str, str]] = []
        if stop == "round_limit":
            warnings.append(("agent_round_limit", say("agent.round_limit", rounds=count(rounds))))
        elif stop == "unreadable":
            cut = self._preview(last)[:80]
            warnings.append(
                (
                    "agent_unreadable",
                    say("agent.unreadable", rounds=count(rounds), last=self._quoted(cut)),
                )
            )
        elif stop == "too_long":
            warnings.append(("agent_too_long", say("agent.too_long")))
        if trimmed:
            warnings.append(
                ("agent_round_trimmed", say("agent.round_trimmed", count=count(trimmed)))
            )
        self._searchless_end(chain, result, self._searchless_items(found), warnings)
        tokens = sum(t["result_tokens"] for t in turns if t["status"] == "ok")
        actions = [t["action"] or "?" for t in turns]
        result.facts = [
            (say("fact.model"), model or "—"),
            (
                say("fact.rounds"),
                say("agent.rounds", rounds=count(rounds), max=count(MAX_AGENT_ROUNDS)),
            ),
            (
                say("fact.actions"),
                ", ".join(a.upper() if a == "answer" else a for a in actions) or "—",
            ),
            (say("fact.result_tokens"), count(tokens)),
            (say("fact.source"), source),
        ]
        result.agent = {
            "rounds": rounds,
            "max_rounds": MAX_AGENT_ROUNDS,
            "stop": stop,
            "turns": turns,
            "result_tokens": tokens,
            "warnings": [{"code": c, "text": t} for c, t in warnings],
        }
        if stop == "cancelled":
            raise LabCancelled(result)
        if stop == "error":
            raise StageFailed(error or Message("rag_lab.agent.model_error"), result=result)
        return result

    def _agent_element(
        self, round_: int, action: agent_tools.Action, out: agent_tools.AgentResult
    ) -> tuple[str, str, str, bool, dict[str, Any]]:
        """A tool's result as an element of the context: the document read (`read_file`),
        else the corpus (a `grep`'s lines, the list of files)."""
        say = self._text
        if out.doc is not None:
            doc_id, title = out.doc.doc_id, out.doc.title_text
        elif action.name == "grep":
            doc_id, title = "corpus", say("agent.grep_title", terms=action.argument)
        else:
            doc_id, title = "corpus", say("agent.list_title")
        source = {
            "kind": action.name,
            "label_text": ", ".join(out.files) or "corpus",
            "rank": round_,
            "score": None,
        }
        return doc_id, title, out.text, out.cut, source

    def _tree_build_cost(self, tree: pageindex.Tree, built_ms: int) -> StageCost:
        """The tree's construction, in `build`: the rule's, measured by this run (no token);
        the model's, read from the rebuilt file's header (its tokens, its duration)."""
        if tree.rebuilt is not None:
            return StageCost(
                "build",
                "section_tree",
                tree.rebuilt.tokens,
                tree.rebuilt.duration_ms,
                None,
                None,
                measured_at_build=True,
                note_text=Message("rag_lab.costs.tree_measure", model=tree.rebuilt.model),
            )
        return StageCost("build", "section_tree", 0, built_ms, 0.0, None)

    def tree_mark(self, tree: pageindex.Tree) -> str:
        """« arbre livré, calculé par une règle, sans modèle » or « arbre reconstruit par le
        modèle X »."""
        if tree.rebuilt is not None:
            return self._text("tree.mark_rebuilt", model=tree.rebuilt.model)
        return self._text("tree.mark_shipped")

    def _level_fit(
        self, children: list[pageindex.Node], room: int | None
    ) -> tuple[list[pageindex.Node], int]:
        """The children a level's list holds in `room`: the last ones left out."""
        listed = list(children)
        if room is None:
            return listed, 0
        while len(listed) > 1 and self.deps.estimate_tokens(pageindex.level_list(listed)) > room:
            listed.pop()
        return listed, len(children) - len(listed)

    def _context_tree(
        self, chain: _Chain, step_id: str, tick: Callable[[int, int], None]
    ) -> _Result:
        """`section_tree` (V1.2 story 11, CAP-7, PageIndex): the tree of sections of the chain's
        documents (precomputed summaries, the structure from the documents), gone down one level
        at a time: the model reads one numbered list of the children of the nodes kept (title
        and summary) and answers `CHOICE: 3, 7` (at most `PAGEINDEX_BREADTH`) or `CHOICE: NONE`;
        the sections reached give an element each (the section's whole text)."""
        deps, say, count = self.deps, self._text, self._int
        copy = deps.work_copy if self._reads_work_copy() else None
        docs = self._corpus_documents(copy)
        source = say("chunking.source_work_copy" if copy else "chunking.source_corpus")
        began = time.perf_counter()
        tree = pageindex.load_tree(docs, self._lang, deps.lab_dir)
        built_ms = math.ceil((time.perf_counter() - began) * 1000)
        nodes = len(tree.nodes)
        result = _Result(
            input_text=say(
                "tree.input",
                nodes=self._count(nodes, "node"),
                documents=self._count(len(docs), "document"),
                source=source,
            ),
            costs=[self._tree_build_cost(tree, built_ms)],
        )
        result.facts = [
            (say("fact.tree"), self.tree_mark(tree)),
            (say("fact.nodes"), count(nodes)),
            (say("fact.stale"), count(tree.stale)),
        ]
        payload: dict[str, Any] = {
            "author": tree.header.author if tree.header else "shipped",
            "method": tree.header.method if tree.header else pageindex.HEURISTIC,
            "model": tree.header.model if tree.header else pageindex.HEURISTIC,
            "mark_text": self.tree_mark(tree),
            "nodes": nodes,
            "depth": tree.depth(),
            "stale": tree.stale,
            "levels": [],
            "chosen": [],
            "stop": "no_model",
            "warnings": [],
        }
        result.tree = payload
        if deps.generator is None:
            raise StageSkipped(Message("rag_lab.generation.no_model"), result=result)
        instruction = say("tree.instruction", breadth=PAGEINDEX_BREADTH)
        user = say("tree.user", question=self.question)
        room = self._room(instruction, user)
        warnings: list[tuple[str, str]] = []
        frontier = [tree.root]
        reached: list[pageindex.Node] = []
        stop, error, model, level = "done", None, "", 0
        depth = max(1, tree.depth())
        with deps.model_scope():
            while True:
                children: list[pageindex.Node] = []
                for node in frontier:
                    kids = tree.children(node.id)
                    if kids:
                        children += kids
                    elif node.id != pageindex.ROOT_ID:
                        reached.append(node)
                if not children:
                    break
                level += 1
                listed, cut = self._level_fit(children, room)
                if cut:
                    warnings.append(
                        (
                            "tree_level_trimmed",
                            say("tree.level_trimmed", count=count(cut), level=count(level)),
                        )
                    )
                if deps.cancelled():
                    stop = "cancelled"
                    break
                got = self._ask(step_id, instruction, pageindex.level_list(listed), user)
                result.costs.append(self._call_cost("query", "section_tree", got))  # type: ignore[union-attr]
                model = got.model_label or model
                entry: dict[str, Any] = {
                    "level": level,
                    "shown": [
                        {
                            "number": n,
                            "node_id": c.id,
                            "title_text": c.title_text,
                            "summary_text": c.summary_text,
                        }
                        for n, c in enumerate(listed, start=1)
                    ],
                    "chosen": [],
                    "trimmed": cut,
                    "answer_preview": self._preview(got.answer_text),
                    "prompt_tokens": got.prompt_tokens,
                    "output_tokens": got.output_tokens,
                }
                payload["levels"].append(entry)
                if got.status not in ("completed", "limit"):
                    stop = got.status if got.status in ("cancelled", "too_long") else "error"
                    error = got.error_text
                    break
                picked = pageindex.parse_choice(got.answer_text, len(listed))
                tick(level, depth)
                if picked is None:
                    stop = "unreadable"
                    warnings.append(("tree_unreadable", say("tree.unreadable")))
                    break
                entry["chosen"] = [listed[n - 1].id for n in picked]
                if not picked:
                    stop = "none"
                    warnings.append(("no_node_chosen", say("tree.no_node_chosen")))
                    break
                frontier = [listed[n - 1] for n in picked]
        if stop == "too_long":
            warnings.append(("tree_too_long", say("agent.too_long")))
        found = []
        for node in reached:
            doc = tree.nodes[node.doc_id] if node.doc_id in tree.nodes else node
            source = {
                "kind": "section_tree",
                "label_text": node.id,
                "rank": node.rank,
                "score": None,
            }
            found.append((node.doc_id or node.id, doc.title_text, node.text, False, source))
        self._searchless_end(chain, result, self._searchless_items(found), warnings)
        result.facts[:0] = [(say("fact.model"), model or "—")]
        result.facts.append((say("fact.levels"), count(level)))
        result.facts.append((say("fact.sections"), count(len(reached))))
        payload |= {
            "chosen": [n.id for n in reached],
            "stop": stop,
            "warnings": [{"code": c, "text": t} for c, t in warnings],
        }
        if stop == "cancelled":
            raise LabCancelled(result)
        if stop == "error":
            raise StageFailed(error or Message("rag_lab.agent.model_error"), result=result)
        return result

    def _rewrite_summaries(
        self,
        nodes: Sequence[pageindex.Node],
        step_id: str,
        phase: str,
        progress: Callable[[int, int], None] = lambda *_: None,
    ) -> tuple[str, list[pageindex.TreeNode], int, int, str]:
        """The summaries of `nodes` rewritten by the active model, one call each (its cost in
        `phase`, added to the run's): `(status, entries written, tokens written, failures,
        model)`. A node the model fails on, or leaves empty, keeps its summary."""
        deps, say = self.deps, self._text
        entries: list[pageindex.TreeNode] = []
        failed = tokens = 0
        model, status = "", "ok"
        instruction = say("tree.rewrite_instruction", max=TREE_SUMMARY_MAX_CHARS)
        with deps.model_scope():
            for done, node in enumerate(nodes, start=1):
                if deps.cancelled():
                    status = "cancelled"
                    break
                text, _ = agent_tools.cut_to_tokens(
                    node.text, TREE_SOURCE_MAX_TOKENS, deps.estimate_tokens
                )
                got = self._ask(
                    step_id,
                    instruction,
                    say("tree.rewrite_source", title=node.title_text, text=text),
                    say("tree.rewrite_user"),
                )
                self.costs.append(self._call_cost(phase, "section_tree", got))
                model = got.model_label or model
                if got.status == "cancelled":
                    status = "cancelled"
                    break
                summary = (
                    pageindex.clean_summary(got.answer_text)
                    if got.status in ("completed", "limit")
                    else ""
                )
                if summary:
                    entry = node.entry()
                    entries.append(entry.model_copy(update={"summary_text": summary}))
                    tokens += got.prompt_tokens + got.output_tokens
                else:
                    failed += 1
                progress(done, len(nodes))
        return status, entries, tokens, failed, model

    # -- V1.2 story 13 (CAP-7): GraphRAG's knowledge graph --

    def _graph_of(self, documents: Sequence[DocText]) -> tuple[rag_graph.Graph, int]:
        """The graph of the chain's documents and the milliseconds its construction took (the
        session's cache keeps both, by language and corpus)."""
        if self.deps.graph is not None:
            return self.deps.graph(documents)
        deps = self.deps
        return graph_for(
            deps.content, deps.lang, deps.shipped_chunk_max_chars, documents, deps.lab_dir
        )

    def _graph_build_cost(self, kg: rag_graph.Graph, built_ms: int) -> StageCost:
        """The graph's construction, in `build`: the rule's, measured (no token); the model's,
        read from the rebuilt file's header (its tokens, its duration)."""
        if kg.rebuilt is not None:
            return StageCost(
                "build",
                "graph_search",
                kg.rebuilt.tokens,
                kg.rebuilt.duration_ms,
                None,
                None,
                measured_at_build=True,
                note_text=Message("rag_lab.costs.graph_measure", model=kg.rebuilt.model),
            )
        return StageCost("build", "graph_search", 0, built_ms, 0.0, None)

    def _graph_call(
        self, step_id: str, instruction: str, source: str, user: str
    ) -> tuple[Generated, bool]:
        """One call of the graph (a question's entities, a « map », a passage's extraction, a
        community's summary): `source` cut to hold in `window − reserve`."""
        room = self._room(instruction, user, reserve=GRAPH_RESERVE)
        cut = False
        if source and room is not None and self.deps.estimate_tokens(source) > room:
            source, cut = agent_tools.cut_to_tokens(source, max(room, 1), self.deps.estimate_tokens)
        return self._ask(step_id, instruction, source, user, reserve=GRAPH_RESERVE), cut

    @staticmethod
    def _stopped(got: Generated) -> str | None:
        if got.status in ("completed", "limit"):
            return None
        return got.status if got.status in ("cancelled", "too_long") else "error"

    def _context_graph(
        self, chain: _Chain, step_id: str, tick: Callable[[int, int], None]
    ) -> _Result:
        """`graph_search` (V1.2 story 13, CAP-7, GraphRAG): the knowledge graph of the chain's
        documents (the work copy included), queried in the page's mode. Local: one call names
        the question's entities (`ENTITIES: a, b`), the graph gives their neighbours and the
        evidence passages of their relations. Global: the closest communities each go through
        a « map » call (`POINTS: …` or `POINTS: NONE`); the generation is the « reduce ». No
        audience filter (D7): each element says its own."""
        deps, say, count = self.deps, self._text, self._int
        copy = deps.work_copy if self._reads_work_copy() else None
        docs = self._corpus_documents(copy)
        source = say("chunking.source_work_copy" if copy else "chunking.source_corpus")
        kg, built_ms = self._graph_of(docs)
        mode = deps.graph_mode if deps.graph_mode in GRAPH_MODES else "local"
        result = _Result(
            input_text=say(
                "graph.input",
                entities=self._count(len(kg.entities), "entity"),
                relations=self._count(len(kg.relations), "relation"),
                communities=self._count(len(kg.communities), "community"),
                documents=self._count(len(docs), "document"),
                source=source,
            ),
            costs=[self._graph_build_cost(kg, built_ms)],
        )
        mark = graph_mark(kg, self._lang)
        estimate = graph_estimate(kg, deps.estimate_tokens, self._lang)
        result.facts = [
            (say("fact.graph"), mark),
            (say("fact.graph_mode"), say(f"graph.mode_{mode}")),
            (say("fact.entities"), count(len(kg.entities))),
            (say("fact.relations"), count(len(kg.relations))),
            (say("fact.communities"), count(len(kg.communities))),
            (say("fact.evidence_stale"), count(kg.stale)),
        ]
        if estimate is not None:
            result.facts.append((say("fact.graph_estimate"), estimate["text"]))
        payload: dict[str, Any] = {
            "author": kg.header.author if kg.header else "shipped",
            "method": kg.header.method if kg.header else rag_graph.HEURISTIC,
            "model": kg.header.model if kg.header else rag_graph.HEURISTIC,
            "mark_text": mark,
            "rule_note_text": None if kg.rebuilt else say("graph.rule_note"),
            "mode": mode,
            "entities": len(kg.entities),
            "relations": len(kg.relations),
            "communities": len(kg.communities),
            "isolated": kg.isolated,
            "stale": kg.stale,
            "estimate": estimate,
            "asked": [],
            "matched": [],
            "neighbours": [],
            "passages": [],
            "ranked": [],
            "calls": 0,
            "answer_preview": "",
            "stop": "no_model",
            "warnings": [],
        }
        result.graph = payload
        if deps.generator is None:
            raise StageSkipped(Message("rag_lab.generation.no_model"), result=result)
        warnings: list[tuple[str, str]] = []
        with deps.model_scope():
            if mode == "global":
                stop, found, error = self._graph_global(
                    kg, payload, result, step_id, tick, warnings
                )
            else:
                stop, found, error = self._graph_local(kg, payload, result, step_id, tick, warnings)
        if stop == "too_long":
            warnings.append(("graph_too_long", say("agent.too_long")))
        self._searchless_end(chain, result, self._searchless_items(found), warnings)
        result.facts.append((say("fact.graph_calls"), count(payload["calls"])))
        payload |= {"stop": stop, "warnings": [{"code": c, "text": t} for c, t in warnings]}
        if stop == "cancelled":
            raise LabCancelled(result)
        if stop == "error":
            raise StageFailed(error or Message("rag_lab.agent.model_error"), result=result)
        return result

    @staticmethod
    def _entity_rows(kg: rag_graph.Graph, ids: Sequence[str]) -> list[dict[str, Any]]:
        return [
            {"id": e, "name": kg.entities[e].name, "audience": kg.entities[e].audience} for e in ids
        ]

    def _graph_local(
        self,
        kg: rag_graph.Graph,
        payload: dict[str, Any],
        result: _Result,
        step_id: str,
        tick: Callable[[int, int], None],
        warnings: list[tuple[str, str]],
    ) -> tuple[str, list[tuple[str, str, str, bool, dict[str, Any]]], Any]:
        say = self._text
        if self.deps.cancelled():
            return "cancelled", [], None
        instruction = say("graph.local_instruction", max=rag_graph.LOCAL_MAX_ENTITIES)
        got, _ = self._graph_call(
            step_id, instruction, "", say("graph.local_user", question=self.question)
        )
        result.costs.append(self._call_cost("query", "graph_search", got))  # type: ignore[union-attr]
        payload["calls"] = 1
        payload["answer_preview"] = self._preview(got.answer_text)
        tick(1, 1)
        if stop := self._stopped(got):
            return stop, [], got.error_text
        names = rag_graph.parse_entities(got.answer_text)
        if names is None:
            warnings.append(("graph_unreadable", say("graph.unreadable")))
            return "unreadable", [], None
        payload["asked"] = names
        ids = rag_graph.match_entities(kg, names)
        if not ids:
            listed = join([self._quoted(n) for n in names], self._lang) or "—"
            warnings.append(("no_entity_matched", say("graph.no_entity_matched", names=listed)))
            return "none", [], None
        pick = rag_graph.select_local(kg, ids)
        payload["matched"] = self._entity_rows(kg, pick.entities)
        payload["neighbours"] = self._entity_rows(kg, pick.neighbours)
        backs: dict[str, list[str]] = {}
        for rel in pick.relations:
            pair = f"{kg.entities[rel.source].name} — {kg.entities[rel.target].name}"
            for m in rel.evidence:
                backs.setdefault(m, []).append(pair)
        names_text = ", ".join(kg.entities[e].name for e in pick.entities)
        neighbours_text = ", ".join(kg.entities[e].name for e in pick.neighbours) or "—"
        found: list[tuple[str, str, str, bool, dict[str, Any]]] = [
            (
                "graph",
                say("graph.entities_title"),
                say("graph.entities_text", entities=names_text, neighbours=neighbours_text),
                False,
                {"kind": "graph_entities", "label_text": names_text, "rank": None, "score": None},
            )
        ]
        for p in pick.passages:
            source = {
                "kind": "graph_search",
                "label_text": p.id,
                "rank": p.rank,
                "score": None,
                "audience": p.audience,
            }
            found.append((p.doc_id, p.title_text, p.text, False, source))
            payload["passages"].append(
                {
                    "passage_id": p.id,
                    "doc_id": p.doc_id,
                    "rank": p.rank,
                    "audience": p.audience,
                    "relation_text": "; ".join(backs.get(p.id, [])[:3]),
                    "chars": len(p.text),
                    "preview": self._preview(p.text),
                }
            )
        return "done", found, None

    def _graph_global(
        self,
        kg: rag_graph.Graph,
        payload: dict[str, Any],
        result: _Result,
        step_id: str,
        tick: Callable[[int, int], None],
        warnings: list[tuple[str, str]],
    ) -> tuple[str, list[tuple[str, str, str, bool, dict[str, Any]]], Any]:
        say, count = self._text, self._int
        picks = rag_graph.select_global(kg, self.question, self._lang)
        rows = [
            {
                "community_id": p.community.id,
                "entities": p.names[:12],
                "size": len(p.community.entities),
                "sources": p.community.sources,
                "audience": p.audience,
                "score": p.score,
                "summary_preview": self._preview(p.community.summary_text),
                "answer_preview": "",
                "kept": False,
                "trimmed": False,
                "prompt_tokens": 0,
                "output_tokens": 0,
            }
            for p in picks
        ]
        payload["ranked"] = rows
        if not picks:
            warnings.append(("no_community_relevant", say("graph.no_community_relevant")))
            return "none", [], None
        instruction = say("graph.map_instruction")
        user = say("graph.map_user", question=self.question)
        found: list[tuple[str, str, str, bool, dict[str, Any]]] = []
        stop, error, trimmed, unreadable = "done", None, 0, 0
        for n, (pick, row) in enumerate(zip(picks, rows, strict=True), start=1):
            if self.deps.cancelled():
                stop = "cancelled"
                break
            passages = "\n\n".join(p.text for p in pick.passages)
            source = say(
                "graph.map_source",
                id=pick.community.id,
                sources=", ".join(pick.community.sources),
                entities=", ".join(pick.names),
                summary=pick.community.summary_text,
                passages=passages,
            )
            got, cut = self._graph_call(step_id, instruction, source, user)
            result.costs.append(self._call_cost("query", "graph_search", got))  # type: ignore[union-attr]
            payload["calls"] += 1
            trimmed += cut
            row |= {
                "trimmed": cut,
                "answer_preview": self._preview(got.answer_text),
                "prompt_tokens": got.prompt_tokens,
                "output_tokens": got.output_tokens,
            }
            tick(n, len(picks))
            if halt := self._stopped(got):
                stop, error = halt, got.error_text
                break
            points = rag_graph.parse_points(got.answer_text)
            if points is None:
                unreadable += 1
                continue
            if not points:
                continue
            row["kept"] = True
            title = say(
                "graph.community_title",
                id=pick.community.id,
                sources=", ".join(pick.community.sources[:4]),
            )
            element = {
                "kind": "graph_community",
                "label_text": ", ".join(pick.community.sources),
                "rank": n,
                "score": None,
                "audience": pick.audience,
            }
            found.append(("community", title, points, False, element))
        if trimmed:
            warnings.append(
                ("graph_input_trimmed", say("graph.input_trimmed", count=count(trimmed)))
            )
        if unreadable:
            warnings.append(
                ("graph_unreadable", say("graph.map_unreadable", count=count(unreadable)))
            )
        if stop == "done" and not found:
            warnings.append(("no_community_relevant", say("graph.no_community_relevant")))
            stop = "none"
        return stop, found, error

    def _extract_by_model(
        self,
        passages: Sequence[rag_graph.Passage],
        step_id: str,
        phase: str,
        kind: str,
        progress: Callable[[int, int], None] = lambda *_: None,
        total: int = 0,
    ) -> dict[str, Any]:
        """Each passage extracted by the active model (`ENTITY:` / `RELATION:`), one call each
        (its cost in `phase`, added to the run's). A passage whose answer is unreadable keeps
        the rule's extraction (`fallback`). Stops at « Arrêter »."""
        say = self._text
        out: dict[str, Any] = {
            "status": "ok",
            "extractions": {},
            "fallback": 0,
            "model": "",
            "input": 0,
            "output": 0,
            "calls": 0,
            "trimmed": 0,
        }
        instruction = say("graph.extract_instruction")
        user = say("graph.extract_user")
        for done, p in enumerate(passages, start=1):
            if self.deps.cancelled():
                out["status"] = "cancelled"
                break
            source = say("graph.extract_source", id=p.id, title=p.title_text, text=p.text)
            got, cut = self._graph_call(step_id, instruction, source, user)
            self.costs.append(self._call_cost(phase, kind, got))
            out["calls"] += 1
            out["trimmed"] += cut
            out["model"] = got.model_label or out["model"]
            out["input"] += got.prompt_tokens
            out["output"] += got.output_tokens
            if got.status == "cancelled":
                out["status"] = "cancelled"
                break
            found = None if self._stopped(got) else rag_graph.parse_extraction(got.answer_text)
            if found is None:
                out["fallback"] += 1
            else:
                out["extractions"][p.id] = found
            progress(done, total or len(passages))
        return out

    def _summarize_by_model(
        self,
        kg: rag_graph.Graph,
        targets: Sequence[rag_graph.Community],
        step_id: str,
        phase: str,
        kind: str,
        progress: Callable[[int, int], None] = lambda *_: None,
        start: int = 0,
        total: int = 0,
    ) -> dict[str, Any]:
        """Each community's summary written by the active model, one call each; a community
        the model fails on keeps the rule's summary (`failed`)."""
        say = self._text
        out: dict[str, Any] = {
            "status": "ok",
            "written": [],
            "failed": 0,
            "model": "",
            "input": 0,
            "output": 0,
            "calls": 0,
            "trimmed": 0,
        }
        instruction = say("graph.summary_instruction", max=rag_graph.COMMUNITY_SUMMARY_MAX_CHARS)
        user = say("graph.summary_user")
        for done, c in enumerate(targets, start=1):
            if self.deps.cancelled():
                out["status"] = "cancelled"
                break
            passages = rag_graph.key_passages(kg, c.entities, rag_graph.GLOBAL_KEY_PASSAGES + 1)
            source = say(
                "graph.summary_source",
                entities=", ".join(kg.entities[e].name for e in c.entities),
                passages="\n\n".join(p.text for p in passages),
            )
            got, cut = self._graph_call(step_id, instruction, source, user)
            self.costs.append(self._call_cost(phase, kind, got))
            out["calls"] += 1
            out["trimmed"] += cut
            out["model"] = got.model_label or out["model"]
            out["input"] += got.prompt_tokens
            out["output"] += got.output_tokens
            if got.status == "cancelled":
                out["status"] = "cancelled"
                break
            summary = "" if self._stopped(got) else rag_graph.clean_summary(got.answer_text)
            if summary:
                c.summary_text, c.summary_source = summary, "rebuilt"
                out["written"].append(c.id)
            else:
                c.summary_text = c.summary_text or rag_graph.rule_summary(kg, c.entities)
                out["failed"] += 1
            progress(start + done, total or len(targets))
        return out

    def _kept_fact(self, kept: int, total: int) -> tuple[str, str]:
        say = self._text
        return (
            say("fact.kept"),
            say("context.kept", kept=self._int(kept), total=self._int(total)),
        )

    def _prompt_preview(self, result: _Result, context_text: str) -> None:
        """The parts of the prompt the generation would send, with their estimated tokens."""
        parts = []
        for kind, part_text in self.deps.prompt_parts(context_text, self.question):
            parts.append(
                {
                    "kind": kind,
                    "label_text": self._text(f"prompt.{kind}"),
                    "text": part_text,
                    "tokens": self.deps.estimate_tokens(part_text),
                }
            )
        result.prompt_parts = parts
        result.prompt_tokens = sum(p["tokens"] for p in parts)

    def _context_text(self, items: Sequence[Item]) -> str:
        """The introduction and the passages as the context places them."""
        ordered = sorted(items, key=lambda i: i.placed or 0)
        return "\n\n".join([self.deps.content.intro_text, *(i.text for i in ordered)])

    def _context_budgeted(self, stage: Stage, picks: list[Item], warning: str | None) -> _Result:
        """`budget`, `order` and `compress`: the passages enter whole, in the relevance order,
        while the context holds in the budget; the first that does not is cut (at the end of a
        sentence, else of a word) and marked, the others are dropped. The best passage is cut
        rather than left out. Then the order, then the compression. The items returned are the
        passages in the context, in the relevance order; `output_text` is the context text."""
        deps, say, count = self.deps, self._text, self._int
        content, estimate, option = deps.content, deps.estimate_tokens, stage.option
        budget = param(stage, "budget_tokens", deps.catalog)
        ordered = option in ("order", "compress")
        whole: list[tuple[Item, str]] = []
        cut: tuple[Item, str] | None = None
        dropped: list[Item] = []
        for index, pick in enumerate(picks):
            trial = [*whole, (pick, pick.text)]
            if estimate(self._assemble(trial, ordered)) <= budget:
                whole = trial
                continue
            cut_text = self._cut_to_fit(whole, pick, budget, ordered)
            if cut_text is None and not whole:
                cut_text = self._smallest_cut(pick.text)
            if cut_text is not None:
                cut = (pick, cut_text)
            dropped = picks[index + (1 if cut is not None else 0) :]
            break
        parts = sorted([*whole, *([cut] if cut else [])], key=lambda p: p[0].rank)
        position = {item.rank: pos for item, _, pos in self._layout(parts, ordered)}
        items: list[Item] = []
        for item, raw in parts:
            formatted = content.excerpt(position[item.rank], item.title_text, raw)
            items.append(
                replace(
                    item,
                    text=formatted,
                    placed=position[item.rank],
                    state="cut" if cut and item is cut[0] else "whole",
                    tokens=estimate(formatted),
                )
            )
        removed = 0
        if cut is not None:
            shown = next(i for i in items if i.rank == cut[0].rank)
            full = content.excerpt(shown.placed or 0, shown.title_text, cut[0].text)
            removed = max(0, estimate(full) - (shown.tokens or 0))
        left_out = []
        for pick in dropped:
            formatted = content.excerpt(pick.rank, pick.title_text, pick.text)
            left_out.append(replace(pick, text=formatted, tokens=estimate(formatted)))
        warnings = [warning] if warning else []
        if cut is not None or dropped:
            warnings.append(
                say(
                    "context.budget_cut",
                    budget=count(budget),
                    whole=count(len(whole)),
                    cut=count(1 if cut else 0),
                    dropped=count(len(dropped)),
                )
            )
        if cut is not None and not whole:
            warnings.append(say("context.budget_tiny"))
        facts = [
            (say("fact.whole"), count(len(whole))),
            (
                say("fact.cut"),
                say("context.cut_some", tokens=count(removed)) if cut else say("context.cut_none"),
            ),
            (say("fact.dropped"), count(len(dropped))),
        ]
        if ordered:
            ranks = ", ".join(str(i.rank) for i in sorted(items, key=lambda i: i.placed or 0))
            facts.append(
                (
                    say("fact.order"),
                    say("context.order_edges", ranks=ranks)
                    if len(items) >= 3
                    else say("context.order_short"),
                )
            )
        text = self._context_text(items) if items else ""
        before = estimate(text)
        if before > budget:  # the best passage's first sentence alone goes over it: said
            warnings.append(say("context.budget_over", used=count(before), budget=count(budget)))
        used_fact = (
            say("fact.tokens_used"),
            say("context.budget_used", used=count(before), budget=count(budget)),
        )
        facts.insert(3, used_fact)
        if option == "compress":
            text = self._compress_items(items, text, facts, warnings)
        out = _Result(items=items, output_text=text, facts=facts, dropped=left_out)
        out.warning_text = " ".join(warnings) or None
        out.budget = {
            "used": estimate(text),
            "budget": budget,
            "before": before if option == "compress" else None,
        }
        return out

    def _compress_items(
        self, items: list[Item], text: str, facts: list[tuple[str, str]], warnings: list[str]
    ) -> str:
        """`compress`: the session's compressor, borrowed, on each passage in turn (never on the
        introduction), above the session's threshold; a failure keeps the passage as it was.
        Unavailable: the context stays as `order` built it, and the reason is said. Returns the
        context text after, `items` updated."""
        deps, say, count = self.deps, self._text, self._int
        estimate = deps.estimate_tokens
        compressor, why = deps.compressor()
        for item in items:
            item.tokens_after = item.tokens
        if compressor is None:
            reason = render(why or Message("session.rag_lab.compress_not_wanted"), self._lang)
            warnings.append(say("context.compress_unavailable", reason=reason))
            facts.append((say("fact.compression"), say("context.compress_off")))
            return text
        failures: list[str] = []
        changed = 0
        for item in sorted(items, key=lambda i: i.placed or 0):
            self._check()  # « Arrêter » is read between two passages
            if len(item.text.strip()) < deps.compression_min_chars:
                continue
            try:
                got = compressor.compress(item.text)
                after = (got.text or "").strip()
                transforms = [str(t) for t in (got.transforms or ())]
            except Exception as exc:  # noqa: BLE001 - AD-16: the passage goes on as it was
                item.error_text = say(
                    "context.compress_failed_item",
                    error=type(exc).__name__,
                    cause=exception_text(exc, self._lang),
                )
                failures.append(item.error_text)
                continue
            tokens_after = estimate(after) if after else 0
            if after and after != item.text.strip() and tokens_after < (item.tokens or 0):
                item.text, item.tokens_after, item.transforms = after, tokens_after, transforms
                changed += 1
        before = sum(i.tokens or 0 for i in items)
        after_total = sum(i.tokens_after or 0 for i in items)
        facts.append(
            (
                say("fact.compression"),
                say(
                    "context.compress_tokens",
                    before=count(before),
                    after=count(after_total),
                    compressor=compressor.label_text,
                ),
            )
        )
        facts.append(
            (
                say("fact.compressed"),
                say("context.compress_count", changed=count(changed), total=count(len(items))),
            )
        )
        if failures:
            warnings.append(
                say("context.compress_failed", count=count(len(failures)), first=failures[0])
            )
            facts.append((say("fact.compress_failures"), count(len(failures))))
        return self._context_text(items)

    def _generation_context(self, chain: _Chain) -> str:
        """« le contexte construit (3 extraits), puis la question », or the question alone."""
        if chain.status != "ok" or not chain.context_text:
            return self._text("generation.question_only")
        context = chain.pipeline.find("context")
        option = context.option if context is not None else ""
        if option in CORPUS_OPTIONS:  # V1.2 story 10: every document, whole
            documents = self._count(len(chain.context), "document")
            return self._text("generation.with_corpus", documents=documents)
        if option in SEARCHLESS_OPTIONS:  # V1.2 story 11: what the model read by itself
            elements = self._count(len(chain.context), "element")
            return self._text("generation.with_read", elements=elements)
        kept = self._count(len(chain.context), "extract")
        return self._text("generation.with_context", extracts=kept)

    def _generation(self, chain: _Chain) -> _Result:
        """« Ne pas générer »: what the model would receive, nothing sent."""
        context = self._generation_context(chain)
        return _Result(
            input_text=self._text("generation.input", context=context, question=self.question),
            output_text=self.deps.texts.generation_not_run_text,
        )

    def _generation_run(
        self, chain: _Chain, step_id: str, progress: Callable[[int, int], None]
    ) -> _Result:
        """Lot 5c-3: the workshop's active model reads the workshop's system prompt, the
        context built and the question, within a turn's bounds (its output reserve, its
        reasoning budget); its answer is the stage's output, the prompt sent shown as is.
        Without a model, the stage is skipped; a prompt longer than the room fails it, nothing
        sent; « Arrêter » stops it and the run; the reserve reached cuts the answer (a
        warning)."""
        context = self._generation_context(chain)
        would = _Result(
            input_text=self._text("generation.input", context=context, question=self.question)
        )
        context_stage = chain.pipeline.find("context")
        cached = bool(
            context_stage and context_stage.option == "cached_corpus" and chain.status == "ok"
        )
        prefix = _PrefixPart(self, chain) if cached else None
        if self.deps.generator is None:
            if prefix is not None:
                prefix.skip(self._text("cache.no_model"))
            raise StageSkipped(Message("rag_lab.generation.no_model"), result=would)
        self._check()
        ask = GenerationAsk(
            context_text=chain.context_text if chain.status == "ok" else "",
            question=self.question,
            step_id=step_id,
            progress=progress,
            cancelled=self.deps.cancelled,
            cached_prefix=cached,
            on_prefix=prefix.start if prefix is not None else None,
        )
        try:
            got = self.deps.generator(ask)
        except StageSkipped as skipped:
            skipped.result = skipped.result or would
            if prefix is not None:
                prefix.skip(skipped.render(self._lang))
            raise
        except BaseException:
            if prefix is not None:
                prefix.skip(self._text("cache.not_built"))
            raise
        if prefix is not None:
            prefix.end(got)
        text, count = self._text, self._int
        system = text("generation.system_prompt" if got.system_prompt else "generation.no_system")
        prompt_tokens = ("" if got.exact else "≈ ") + count(got.prompt_tokens)
        facts = [
            (text("fact.model"), got.model_label),
            (text("fact.prompt_tokens"), prompt_tokens),
        ]
        result = _Result(
            input_text=text(
                "generation.sent", system=system, context=context, question=self.question
            ),
            facts=facts,
            prompt_text=got.prompt_text,
        )
        if got.status == "too_long":
            result.input_text = would.input_text  # nothing was sent: what it would receive
            usable = got.window - got.reserve
            raise StageFailed(
                Message(
                    "rag_lab.generation.too_long",
                    tokens=prompt_tokens,
                    usable=count(usable),
                    window=count(got.window),
                    reserve=count(got.reserve),
                ),
                result=result,
            )
        produced = ("" if got.exact else "≈ ") + count(got.output_tokens)
        facts.append(
            (
                text("fact.output_tokens"),
                text("generation.produced", done=produced, reserve=count(got.reserve)),
            )
        )
        result.output_text = got.answer_text
        # V1.2 story 10 (CAG): the tokens read from the cache are not evaluated again.
        evaluated = got.prompt_tokens
        notes: list[str] = []
        if got.evaluated_tokens is not None:
            evaluated = got.evaluated_tokens
            read = max(0, got.prompt_tokens - evaluated)
            facts.append((text("fact.cache_read"), count(read)))
            facts.append((text("fact.evaluated"), count(evaluated)))
            if read:
                notes.append(text("costs.cache_read", tokens=count(read)))
        if got.cache is not None:
            result.cache = got.cache
            facts.append((text("fact.cache_state"), text(f"cache.state.{got.cache['state']}")))
        if got.prefix is not None and got.prefix.warning_text:
            result.warning_text = render(got.prefix.warning_text, self._lang)
        if got.cost_usd is None and got.impact is None:
            notes.append(render(Message("rag_lab.costs.generation_unpriced"), self._lang))
        # V1.2 story 3: a call stopped or in error was sent all the same, its cost is kept.
        result.costs = [
            StageCost(
                "query",
                "generation",
                evaluated + got.output_tokens,
                got.duration_ms,
                got.cost_usd,
                got.impact,
                note_text=" ".join(notes) or None,
            )
        ]
        if got.status == "cancelled":
            raise LabCancelled(result)
        if got.status not in ("completed", "limit"):  # `error`, or a status it does not know
            raise StageFailed(
                got.error_text or Message("rag_lab.generation.model_error"), result=result
            )
        if not got.answer_text.strip():
            result.output_text = text("generation.empty")
        if got.status == "limit":
            cut = text("generation.cut", max=count(got.reserve))
            result.warning_text = " ".join(filter(None, [result.warning_text, cut]))
        return result


class _PrefixPart:
    """V1.2 story 10: the « Préfixe en cache » line of a `cached_corpus` chain, a part of the
    Context stage run apart (`part` « prefix », kind `cache_prefix`, step `….prefix`, as BM25's
    index): started when the session begins to build the prefix (`start`), ended once the
    generation says what it did with it (`end`), or skipped (`skip`)."""

    def __init__(self, run: LabRun, chain: _Chain) -> None:
        stages = chain.pipeline.stages
        context = next(s for s in stages if s.kind == "context")
        self.run = run
        self.step_id = f"{run._step(stages.index(context) + 1)}.prefix"
        self.component = "rag_lab.cache_prefix"
        self.base = {
            "stage_id": context.id,
            "kind": "cache_prefix",
            "option": context.option,
            "part": "prefix",
        }
        self.started = False
        self.rss_before: int | None = None
        self.at = 0.0

    def start(self) -> None:
        if self.started:
            return
        self.started = True
        label = self.run.deps.texts.steps["cache_prefix"].label_text
        self.run._emit(
            "rag_lab_stage_started",
            self.base | {"phase_label": self.run._text("stage.running", stage=label)},
            self.step_id,
            self.component,
        )
        self.rss_before = self.run.deps.rss()
        self.at = time.monotonic()

    def _close(self, status: str, result: _Result, error_text: str | None) -> None:
        duration = _ms(time.monotonic() - self.at) if self.started else 0
        rss_before = self.rss_before if self.started else None
        step, component, base = self.step_id, self.component, self.base
        self.run._ended(step, component, base, status, result, error_text, duration, rss_before)

    def skip(self, reason_text: str) -> None:
        """Nothing kept: skipped, or in error once begun (the call went wrong meanwhile)."""
        self._close("error" if self.started else "skipped", _Result(costs=[]), reason_text)

    def end(self, got: Generated) -> None:
        run, prefix = self.run, got.prefix
        say, count = run._text, run._int
        if prefix is None or got.status == "too_long":
            self.skip(say("cache.too_long" if got.status == "too_long" else "cache.not_built"))
            return
        tokens = ("" if prefix.exact else "≈ ") + count(prefix.tokens or 0)
        cache = prefix.cache or {}
        facts = [(say("fact.prefix_tokens"), tokens)]
        if cache.get("state_bytes") is not None:
            facts.append((say("fact.state_size"), size_text(cache["state_bytes"], run._lang)))
        if cache.get("build_ms") is not None:
            facts.append((say("fact.prefix_duration"), ms_text(cache["build_ms"], run._lang)))
        result = _Result(
            input_text=say("cache.input"),
            facts=facts,
            costs=[prefix.cost] if prefix.cost else [],
            cache=prefix.cache,
        )
        if prefix.warning_text:
            result.warning_text = render(prefix.warning_text, run._lang)
        if prefix.status != "ok":
            reason = render(prefix.reason_text or say("cache.not_built"), run._lang)
            status = "error" if prefix.status == "error" else "skipped"
            self._close(status, result, reason)
            return
        self.start()  # read back from the cache entry: nothing built by this call
        result.output_text = say("cache.built" if prefix.built else "cache.reused", tokens=tokens)
        self._close("ok", result, None)


class UpdateRun(LabRun):
    """V1.2 story 3 (CAP-8): the cost of an update of the corpus, measured on the work copy
    (`workcopy`), for the chain's own components. One operation (add, modify, delete one
    document) is applied to the copy; then only what a real update would redo is run and
    measured, as the `update` time: the passages that changed are chunked and embedded (the
    other vectors are those of the shipped corpus, from the cache or computed first, outside
    the cost), the vector store and BM25's index are rebuilt whole (the workshop's stores do
    not take one vector at a time). Emits the same events as a run, under the id `upd{n}`:
    `rag_lab_run_started`, a stage pair per part, `rag_lab_run_ended` with the `update` sum."""

    SUMMARY_PHASES = ("update",)

    def __init__(
        self,
        run_id: str,
        label_text: str,
        pipeline: Pipeline,
        deps: LabDeps,
        before: workcopy.WorkCopy,
        after: workcopy.WorkCopy,
    ) -> None:
        super().__init__(run_id, label_text, pipeline, deps)
        self.before, self.after = before, after
        self.state: dict[str, Any] = {}
        # Called with the copy once measured, before `rag_lab_run_ended`: the page reloads the
        # copy on that event, so it must already be saved (review of V1.2 story 5).
        self.keep: Callable[[workcopy.WorkCopy], None] | None = None

    def _label_of(self, stage: Stage, kind: str) -> str:
        if kind == "lexical_index":
            return self.deps.texts.steps["lexical_index"].label_text
        return self._label(stage)

    def _ref(self, stage: Stage, kind: str) -> dict[str, Any]:
        return {
            "stage_id": stage.id,
            "kind": kind,
            "option": stage.option,
            "label_text": self._label_of(stage, kind),
            "option_label_text": self.deps.catalog.option_label(stage.kind, stage.option),
            "params": stage.params,
        }

    def _parts(self) -> list[tuple[Stage, str, Callable[[Stage], _Result]]]:
        pipeline = self.pipeline
        context = pipeline.find("context")
        # V1.2 story 10: the long context reads the corpus at each question, nothing to redo;
        # the CAG reloads its whole prefix (any change invalidates all that follows it).
        if context is not None and context.option in ("full_corpus", "agent_loop"):
            return []  # V1.2 story 11: the agent reads the source at each question too
        if context is not None and context.option == "section_tree":
            return [(context, "section_tree", self._update_tree)]
        if context is not None and context.option == "graph_search":  # V1.2 story 13
            return [(context, "graph_search", self._update_graph)]
        if context is not None and context.option == "cached_corpus":
            return [(context, "cache_prefix", self._update_prefix)]
        chunking = pipeline.find("chunking")
        embedding = pipeline.find("embedding")
        store = pipeline.find("vector_store")
        lexical = pipeline.find("lexical_search")
        assert chunking and embedding and store  # `check_pipeline` keeps the fixed head
        parts = [
            (chunking, "chunking", self._update_chunking),
            (embedding, "embedding", self._update_embedding),
            (store, "vector_store", self._update_store),
        ]
        if lexical is not None:
            parts.append((lexical, "lexical_index", self._update_lexical))
        return parts

    def cost_summary(self, phases: Sequence[str], complete: bool = True) -> list[dict[str, Any]]:
        """V1.2 story 10: an update with no part to redo (the long context) costs nothing,
        said as such (`parts` 0, zero tokens and duration, the note)."""
        if self._parts():
            return super().cost_summary(phases, complete)
        nothing = greenops.summarize([], "update", self._lang)
        note = self._text("update.nothing_to_redo")
        return [nothing | {"tokens": 0, "duration_ms": 0, "usd": 0.0, "note_text": note}]

    def run(self) -> str:
        started = time.monotonic()
        parts = self._parts()
        self._emit(
            "rag_lab_run_started",
            {
                "question": self.question,
                "stages": [self._ref(stage, kind) for stage, kind, _ in parts],
                "phase_label": self._text(
                    "run.phase", running=self.deps.texts.running_text, question=self.question[:80]
                ),
            },
            self.run_id,
            "rag_lab",
        )
        status = "ok"
        try:
            for index, (stage, kind, fn) in enumerate(parts, start=1):
                status = self._part(index, stage, kind, fn, status)
        except Exception:  # noqa: BLE001 - the run ends in error, `run_ended` all the same
            status = "error"
        if status == "ok" and self.keep is not None:
            try:  # kept only when it was measured, and before the page reloads it
                self.keep(self.after)
            except Exception:
                self.end("error", _ms(time.monotonic() - started))
                raise  # the session says it (`session.rag_lab.interrupted`)
        self.end(status, _ms(time.monotonic() - started))
        return status

    def _part(
        self,
        index: int,
        stage: Stage,
        kind: str,
        fn: Callable[[Stage], _Result],
        previous: str,
    ) -> str:
        step_id, component = self._step(index), f"rag_lab.{kind}"
        base = {"stage_id": stage.id, "kind": kind, "option": stage.option}
        if previous != "ok":
            self._ended(step_id, component, base, "skipped", _Result(costs=[]), None, 0, None)
            return previous
        if self.deps.cancelled():
            self._ended(step_id, component, base, "cancelled", _Result(costs=[]), None, 0, None)
            return "cancelled"
        self._emit(
            "rag_lab_stage_started",
            base | {"phase_label": self._text("stage.running", stage=self._label_of(stage, kind))},
            step_id,
            component,
        )
        rss_before = self.deps.rss()
        started = time.monotonic()
        status, error_text, result = "ok", None, _Result(costs=[])
        try:
            result = fn(stage)
        except LabCancelled:
            status, error_text = "cancelled", self._text("stage.stopped")
        except StageSkipped as skipped:  # V1.2 story 10: estimated, the update goes on
            status, error_text = "skipped", skipped.render(self._lang)
            result = skipped.result or result
        except StageFailed as failed:
            status, error_text = "error", failed.render(self._lang)
            result = failed.result or result
        except Exception as exc:  # noqa: BLE001 - AD-16: a stage's failure, never a crash
            status = "error"
            error_text = self._text(
                "stage.failed", error=type(exc).__name__, cause=exception_text(exc, self._lang)
            )
        duration = _ms(time.monotonic() - started)
        if status == "ok" and result.costs is None:
            result.costs = [StageCost("update", kind, duration_ms=duration)]
        self._ended(step_id, component, base, status, result, error_text, duration, rss_before)
        return "ok" if status == "skipped" else status

    def _update_prefix(self, stage: Stage) -> _Result:
        """V1.2 story 10 (CAG): the prefix of the copy after the operation (the instruction and
        the whole corpus), rebuilt whole from an emptied memory by the session, measured in
        `update`; once the update ends `ok`, it becomes the session's cache entry. Without a
        local model: skipped, its tokens estimated."""
        documents = self._corpus_documents(self.after)
        if not documents:
            raise StageFailed(Message("rag_lab.update.empty_corpus"))
        context_text = self._corpus_text(documents)
        question = self.deps.texts.default_question_text
        say, count = self._text, self._int
        built = self.deps.cag(context_text, question) if self.deps.cag else None
        if built is None or built.status == "skipped":
            parts = self.deps.prompt_parts(context_text, question)
            estimate = sum(self.deps.estimate_tokens(t) for k, t in parts if k != "question")
            estimated = StageCost(
                "update", "cache_prefix", estimate, note_text=Message("rag_lab.costs.estimated")
            )
            reason = (built.reason_text if built else None) or Message("rag_lab.cache.no_model")
            raise StageSkipped(
                reason,
                result=_Result(
                    input_text=say("update.prefix_input", documents=count(len(documents))),
                    output_text=say("update.prefix_estimated", tokens=count(estimate)),
                    costs=[estimated],
                ),
            )
        if built.status != "ok":
            raise StageFailed(built.reason_text or Message("rag_lab.cache.not_built"))
        tokens = ("" if built.exact else "≈ ") + count(built.tokens or 0)
        facts = [(say("fact.prefix_tokens"), tokens)]
        cache = built.cache or {}
        if cache.get("state_bytes") is not None:
            facts.append((say("fact.state_size"), size_text(cache["state_bytes"], self._lang)))
        result = _Result(
            input_text=say("update.prefix_input", documents=count(len(documents))),
            output_text=say("update.prefix_output", tokens=tokens),
            facts=facts,
            costs=[built.cost] if built.cost else [],
            cache=built.cache,
        )
        if built.warning_text:
            result.warning_text = render(built.warning_text, self._lang)
        return result

    def _update_tree(self, stage: Stage) -> _Result:
        """V1.2 story 11 (PageIndex): only the subtree of the document the operation touched is
        computed again (the document and its sections; a deletion removes its subtree), then
        the root. It follows the tree in use: rebuilt by a model and a model loaded, the
        touched document's summaries are rewritten by the model (its tokens and seconds, kept
        in the rebuilt file); else by the rule (milliseconds, no token)."""
        deps, say, count = self.deps, self._text, self._int
        before = {d.doc_id: d for d in self._corpus_documents(self.before)}
        after_docs = self._corpus_documents(self.after)
        if not after_docs:
            raise StageFailed(Message("rag_lab.update.empty_corpus"))
        after = {d.doc_id: d for d in after_docs}
        touched = [i for i, d in after.items() if i not in before or before[i].text != d.text]
        removed = [i for i in before if i not in after]
        rebuilt = pageindex.load_files(self._lang, deps.lab_dir)[1]
        gone = sum(len(pageindex.build_tree([before[i]])) - 1 for i in removed)
        total = len(pageindex.build_tree(after_docs))
        began = time.perf_counter()
        # The touched documents' subtree, under a root of their own: the corpus's root is
        # then the same rule on the documents' titles and fingerprints (counted, not redone).
        sub = pageindex.build_tree([after[i] for i in touched])
        redone = [n for n in sub.values() if n.id != pageindex.ROOT_ID]
        by_model = rebuilt is not None and deps.generator is not None and bool(redone)
        facts = [
            (
                say("fact.nodes_redone"),
                say("tree.redone", redone=count(len(redone)), total=count(total)),
            ),
            (say("fact.nodes_removed"), count(gone)),
        ]
        result = _Result(
            input_text=say(
                "update.tree_input",
                documents=self._count(len(touched) + len(removed), "document"),
            ),
            facts=facts,
        )
        if not by_model:
            # A deleted document's model summaries leave the rebuilt file (story 18: erased).
            pageindex.forget(self._lang, removed, deps.lab_dir)
            ms = math.ceil((time.perf_counter() - began) * 1000)
            result.output_text = say(
                "update.tree_rule", redone=count(len(redone)), removed=count(gone)
            )
            result.costs = [StageCost("update", "section_tree", 0, ms, 0.0, None)]
            result.facts.append((say("fact.tree"), say("tree.by_rule")))
            return result
        step_id = f"{self.run_id}.tree"
        mark = len(self.costs)
        started = time.monotonic()
        status, entries, tokens, failed, model = self._rewrite_summaries(redone, step_id, "update")
        duration = _ms(time.monotonic() - started)
        costs, self.costs = self.costs[mark:], self.costs[:mark]  # the part's, said by `_ended`
        result.costs = costs
        if status == "cancelled":
            raise LabCancelled(result)
        pageindex.forget(self._lang, removed, deps.lab_dir)
        if entries:
            pageindex.write_rebuilt(
                self._lang,
                entries,
                model=model or "?",
                tokens=tokens,
                duration_ms=duration,
                folder=deps.lab_dir,
            )
        result.output_text = say(
            "update.tree_model",
            redone=count(len(entries)),
            failed=count(failed),
            removed=count(gone),
            model=model or "—",
        )
        result.facts.append((say("fact.tree"), say("tree.by_model", model=model or "—")))
        return result

    def _update_graph(self, stage: Stage) -> _Result:
        """V1.2 story 13 (GraphRAG): the four parts of a graph's update. (a) Extraction of the
        touched document alone (by the rule, with the frozen vocabulary; graph rebuilt by a model
        and a model loaded: one call per passage of the document); (b) fusion: its evidence
        replaced, the entities and relations left without evidence removed; (c) communities
        computed again from the previous ones; (d) summaries rewritten only for the communities
        whose fingerprint changed (by the rule, or one call each by the model)."""
        deps, say, count = self.deps, self._text, self._int
        lang, size = self._lang, deps.shipped_chunk_max_chars
        before_docs = self._corpus_documents(self.before)
        after_docs = self._corpus_documents(self.after)
        if not after_docs:
            raise StageFailed(Message("rag_lab.update.empty_corpus"))
        before = {d.doc_id: d for d in before_docs}
        after = {d.doc_id: d for d in after_docs}
        touched = [i for i, d in after.items() if i not in before or before[i].text != d.text]
        removed = [i for i in before if i not in after]
        audiences = graph_audiences(deps.content)
        construction = self._corpus_documents(None)
        shipped, rebuilt, _ = rag_graph.load_files(lang, deps.lab_dir)
        # The graph in place before the operation, outside the cost (it was already built).
        old = rag_graph.assemble(
            before_docs,
            lang,
            size,
            audiences=audiences,
            construction=construction,
            shipped=shipped,
            rebuilt=rebuilt,
        )
        vocab = rag_graph.vocabulary(construction, lang, size)
        by_model = rebuilt is not None and deps.generator is not None
        step_id = f"{self.run_id}.graph"
        mark = len(self.costs)
        costs: list[StageCost] = []
        out: dict[str, Any] = {}
        # (a) extraction
        redo = rag_graph.passages_of([after[i] for i in touched], size, audiences)
        began = time.perf_counter()
        if by_model and redo:
            with deps.model_scope():
                out = self._extract_by_model(redo, step_id, "update", "graph_extraction")
            fresh = out["extractions"]
            terms = rag_graph.terms_for(after_docs, vocab, lang, size)
            for p in redo:
                fresh.setdefault(p.id, rag_graph.extract(p.text, terms, lang))
            costs += self.costs[mark:]
            self.costs = self.costs[:mark]
            if out["status"] == "cancelled":
                raise LabCancelled(_Result(costs=costs))
        else:
            terms = rag_graph.terms_for(after_docs, vocab, lang, size)
            fresh = {p.id: rag_graph.extract(p.text, terms, lang) for p in redo}
            costs.append(StageCost("update", "graph_extraction", 0, _elapsed(began), 0.0, None))
        extraction_note = Message(
            "rag_lab.graph.part_extraction",
            passages=count(len(redo)),
            calls=count(out.get("calls", 0)),
        )
        if costs:
            costs[0] = replace(costs[0], note_text=extraction_note)
        else:
            costs.append(
                StageCost("update", "graph_extraction", 0, 0, 0.0, None, note_text=extraction_note)
            )
        # (b) fusion
        began = time.perf_counter()
        gone = set(touched) | set(removed)
        extractions = {
            pid: x for pid, x in old.extractions.items() if old.passages[pid].doc_id not in gone
        } | fresh
        passages = rag_graph.passages_of(after_docs, size, audiences)
        kg = rag_graph.merge(passages, extractions)
        kg.chunk_max_chars = size
        kg.shipped, kg.rebuilt = shipped, rebuilt
        changed_entities = _changed(
            {e.id: e.mentions for e in old.entities.values()},
            {e.id: e.mentions for e in kg.entities.values()},
        )
        changed_relations = _changed(
            {k: r.evidence for k, r in old.relations.items()},
            {k: r.evidence for k, r in kg.relations.items()},
        )
        costs.append(
            StageCost(
                "update",
                "graph_merge",
                0,
                _elapsed(began),
                0.0,
                None,
                note_text=Message(
                    "rag_lab.graph.part_merge",
                    entities=count(changed_entities),
                    relations=count(changed_relations),
                ),
            )
        )
        # (c) communities, from the previous ones
        began = time.perf_counter()
        previous = [c.entities for c in old.communities.values()]
        rag_graph.form_communities(kg, previous, (rebuilt, shipped), summarize=False)
        known = {c.sha256 for c in old.communities.values()}
        redone = [c for c in kg.communities.values() if c.sha256 not in known]
        costs.append(
            StageCost(
                "update",
                "graph_communities",
                0,
                _elapsed(began),
                0.0,
                None,
                note_text=Message(
                    "rag_lab.graph.part_communities",
                    communities=count(len(kg.communities)),
                    changed=count(len(redone)),
                ),
            )
        )
        # (d) summaries, of the communities whose fingerprint changed only
        began = time.perf_counter()
        summaries: dict[str, Any] = {"written": [], "failed": 0, "calls": 0}
        if by_model and redone:
            mark = len(self.costs)
            with deps.model_scope():
                summaries = self._summarize_by_model(
                    kg, redone, step_id, "update", "graph_summaries"
                )
            part = self.costs[mark:]
            self.costs = self.costs[:mark]
            if summaries["status"] == "cancelled":
                raise LabCancelled(_Result(costs=costs + part))
        else:
            for c in redone:
                c.summary_text = c.summary_text or rag_graph.rule_summary(kg, c.entities)
            part = [StageCost("update", "graph_summaries", 0, _elapsed(began), 0.0, None)]
        for c in kg.communities.values():  # the untouched ones keep the rule's when unknown
            c.summary_text = c.summary_text or rag_graph.rule_summary(kg, c.entities)
        part[0] = replace(
            part[0],
            note_text=Message(
                "rag_lab.graph.part_summaries",
                rewritten=count(len(redone)),
                total=count(len(kg.communities)),
            ),
        )
        costs += part
        # A deleted document leaves none of its evidence in the rebuilt file (story 18).
        rag_graph.forget(lang, removed, deps.lab_dir)
        if by_model:
            self._keep_rebuilt(kg, out, summaries, costs)
        facts = [
            (say("fact.graph_part_extraction"), count(len(redo))),
            (
                say("fact.graph_part_merge"),
                say(
                    "graph.merge_fact",
                    entities=count(changed_entities),
                    relations=count(changed_relations),
                ),
            ),
            (say("fact.graph_part_communities"), count(len(kg.communities))),
            (
                say("fact.graph_part_summaries"),
                say(
                    "graph.summaries_fact",
                    rewritten=count(len(redone)),
                    total=count(len(kg.communities)),
                ),
            ),
            (say("fact.graph"), say("graph.by_model") if by_model else say("graph.by_rule")),
        ]
        return _Result(
            input_text=say(
                "update.graph_input",
                documents=self._count(len(touched) + len(removed), "document"),
            ),
            output_text=" ".join(
                render(c.note_text, lang) for c in costs if c.note_text is not None
            ),
            facts=facts,
            costs=costs,
        )

    def _keep_rebuilt(
        self,
        kg: rag_graph.Graph,
        extracted: dict[str, Any],
        summaries: dict[str, Any],
        costs: Sequence[StageCost],
    ) -> None:
        """An update of a graph rebuilt by a model: the model's extractions and summaries
        written back into the rebuilt file, its measure added to the earlier one."""
        earlier = kg.rebuilt
        if earlier is None:
            return
        kept = [c.id for c in kg.communities.values() if c.summary_source == "rebuilt"]
        models = [m for m in earlier.model.split(" + ") if m]
        for model in (extracted.get("model"), summaries.get("model")):
            if model and model not in models:
                models.append(model)
        file = rag_graph.to_file(
            kg,
            author="rebuilt",
            model=" + ".join(models) or "?",
            only_model=True,
            summaries=kept,
            measure={
                "duration_ms": (earlier.duration_ms or 0) + sum(c.duration_ms or 0 for c in costs),
                "input_tokens": (earlier.input_tokens or 0)
                + extracted.get("input", 0)
                + summaries.get("input", 0),
                "output_tokens": (earlier.output_tokens or 0)
                + extracted.get("output", 0)
                + summaries.get("output", 0),
                "calls": (earlier.calls or 0)
                + extracted.get("calls", 0)
                + summaries.get("calls", 0),
            },
        )
        rag_graph.write_rebuilt(self._lang, file, self.deps.lab_dir)

    # -- the parts --

    @staticmethod
    def _key(chunk: Chunk) -> tuple[str, str, str]:
        return (chunk.doc_id, chunk.title_text, chunk.text)

    def _update_chunking(self, stage: Stage) -> _Result:
        if stage.option != "paragraphs":  # V1.2 story 6: the intention refuses it first
            raise StageFailed(Message("session.rag_lab.update_chunking"))
        size = param(stage, "chunk_max_chars", self.deps.catalog)
        content, lang = self.deps.content, self.deps.lang
        before = workcopy.chunks(content, size, lang, self.before)
        after = workcopy.chunks(content, size, lang, self.after)
        if not after:
            raise StageFailed(Message("rag_lab.update.empty_corpus"))
        old = {self._key(c) for c in before}
        now = {self._key(c) for c in after}
        new = [c for c in after if self._key(c) not in old]
        gone = [c for c in before if self._key(c) not in now]
        self.state |= {"size": size, "before": before, "after": after, "new": new}
        count = self._int
        return _Result(
            input_text=self.question,
            output_text=self._text(
                "update.chunking_output",
                before=count(len(before)),
                after=count(len(after)),
                new=count(len(new)),
                gone=count(len(gone)),
            ),
            facts=[
                (self._text("update.fact_new"), count(len(new))),
                (self._text("update.fact_gone"), count(len(gone))),
            ],
        )

    @staticmethod
    def _texts_of(chunks: Sequence[Chunk]) -> list[str]:
        return [rag_index.passage_text(c) for c in chunks]

    def _vectors_of(self, embedder: Embedder, chunks: Sequence[Chunk]) -> list[list[float]]:
        out: list[list[float]] = []
        for at in range(0, len(chunks), EMBED_BATCH):
            self._check()
            batch = chunks[at : at + EMBED_BATCH]
            out += embedder.embed_passages([rag_index.passage_text(c) for c in batch])
        if len(out) != len(chunks) or any(len(v) != embedder.dims for v in out):
            raise StageFailed(Message("rag_lab.embedding.wrong_dims", dims=embedder.dims))
        return out

    def _update_embedding(self, stage: Stage) -> _Result:
        lent = self.deps.embedder(stage.option)
        embedder: Embedder = lent.model
        state, count = self.state, self._int
        before, after, new = state["before"], state["after"], state["new"]
        identity = self.deps.identity(stage.option)
        key = cache_key(identity, state["size"], rag_index.corpus_digest(before))
        folder = self.deps.lab_dir / key
        facts = [(self._text("fact.model"), lent.label_text)]
        vectors = read_vectors(folder, before, embedder.dims)
        if vectors is None:  # the shipped corpus first, outside the update's cost
            probe = Probe(self.deps.meter)
            try:
                vectors = self._vectors_of(embedder, before)
            finally:
                built = self._cost(
                    "build", "embedding", probe, self._tokens(self._texts_of(before))
                )
            write_vectors(folder, before, vectors, identity, None)
            write_build_cost(folder, "embedding", built)
            facts.append((self._text("update.fact_prepared"), count(len(before))))
        known = {self._key(c): v for c, v in zip(before, vectors, strict=True)}
        probe = Probe(self.deps.meter)
        try:
            computed = self._vectors_of(embedder, new) if new else []
        finally:
            cost = self._cost("update", "embedding", probe, self._tokens(self._texts_of(new)))
        fresh = {self._key(c): v for c, v in zip(new, computed, strict=True)}
        state["vectors"] = [known.get(self._key(c)) or fresh[self._key(c)] for c in after]
        state["embedder"] = embedder
        facts.append((self._text("update.fact_embedded"), count(len(new))))
        text = (
            self._text("update.embedding_output", new=count(len(new)), after=count(len(after)))
            if new
            else self._text("update.embedding_none")
        )
        return _Result(
            input_text=self._text("update.embedding_input", after=count(len(after))),
            output_text=text,
            facts=facts,
            borrowed=lent.borrowed,
            costs=[cost],
        )

    def _update_store(self, stage: Stage) -> _Result:
        state = self.state
        after, vectors, embedder = state["after"], state["vectors"], state["embedder"]
        scratch = self.deps.lab_dir / "work_corpus" / f"{self.deps.lang}-update"
        _delete(scratch)
        probe = Probe(self.deps.meter)
        store: Any = None
        try:
            if stage.option == "memory":
                store = MemoryStore(after, vectors)
            elif stage.option == "sqlite_vec":
                scratch.mkdir(parents=True, exist_ok=True)
                rag_index.write_index(
                    scratch / INDEX_FILE,
                    after,
                    vectors,
                    model_id=embedder.model_id,
                    dims=embedder.dims,
                    chunk_max_chars=state["size"],
                )
            elif stage.option in LIBRARIES:
                imported = self.deps.importer(stage.option)
                cls = FaissStore if stage.option == "faiss" else LanceStore
                store = cls(imported.module, scratch, vectors)
            else:
                raise StageFailed(Message("rag_lab.vector_store.unknown", option=stage.option))
        finally:
            cost = self._cost("update", "vector_store", probe)
            if store is not None:
                try:
                    store.close()
                except Exception:  # noqa: BLE001 - a store closed badly is forgotten
                    pass
            try:
                _delete(scratch)
            except StageFailed:
                pass  # a held scratch folder is removed by the next update
        return _Result(
            input_text=self._text("update.store_input", vectors=self._int(len(after))),
            output_text=self._text("update.store_output", option=stage.option),
            facts=[(self._text("fact.vectors"), self._int(len(after)))],
            costs=[cost],
        )

    def _update_lexical(self, stage: Stage) -> _Result:
        after = self.state["after"]
        passages = [rag_index.passage_text(c) for c in after]
        probe = Probe(self.deps.meter)
        try:
            built = lexical_index(passages, self.deps.lang)
        finally:
            cost = self._cost("update", "lexical_index", probe)
        count = self._int
        return _Result(
            input_text=self._text("update.store_input", vectors=count(len(after))),
            output_text=self._text(
                "update.lexical_output",
                terms=count(built.vocabulary),
                occurrences=count(built.occurrences),
            ),
            facts=[(self._text("lexical_index.terms"), count(built.vocabulary))],
            costs=[replace(cost, tokens=built.occurrences)],
        )


class RebuildRun(LabRun):
    """V1.2 story 6 (CAP-4): the contexts of the `contextual` chunking rewritten by the
    workshop's active model, as contextual retrieval describes it (the whole document and the
    chunk in, a short context out), into the workshop's data folder (never `content/`). A run
    of its own, id `ctx{n}`: `rag_lab_run_started`, one stage (the chunking, its progress in
    chunks), `rag_lab_run_ended` with the `build` sum. A chunk the model fails on, or leaves
    empty, keeps its context; « Arrêter » stops between two chunks and keeps the contexts
    made."""

    SUMMARY_PHASES = ("build",)
    TARGETS = ("contexts", "pageindex", "graph")  # V1.2 story 13: GraphRAG's graph

    def __init__(
        self,
        run_id: str,
        question: str,
        pipeline: Pipeline,
        deps: LabDeps,
        target: str = "contexts",
    ) -> None:
        super().__init__(run_id, question, pipeline, deps)
        # V1.2 story 11: the contexts of the contextual chunking, or PageIndex's summaries.
        self.target = target

    def _rebuilt_stage(self) -> tuple[Stage, str]:
        """The chain's stage the rebuild shows, and its kind in the events."""
        if self.target in ("pageindex", "graph"):
            context = self.pipeline.find("context")
            assert context is not None  # `check_pipeline` keeps the fixed tail
            return context, "section_tree" if self.target == "pageindex" else "graph_search"
        stage = self.pipeline.find("chunking")
        assert stage is not None  # `check_pipeline` keeps the fixed head
        return stage, "chunking"

    def run(self) -> str:
        started = time.monotonic()
        stage, kind = self._rebuilt_stage()
        self._emit(
            "rag_lab_run_started",
            {
                "question": self.question,
                "stages": [
                    {
                        "stage_id": stage.id,
                        "kind": kind,
                        "option": stage.option,
                        "label_text": self._label(stage),
                        "option_label_text": self.deps.catalog.option_label(
                            stage.kind, stage.option
                        ),
                        "params": stage.params,
                    }
                ],
                "phase_label": self._text(
                    "run.phase", running=self.deps.texts.running_text, question=self.question[:80]
                ),
            },
            self.run_id,
            "rag_lab",
        )
        status = "error"
        try:
            status = self._rebuild(stage)
        except Exception:  # noqa: BLE001 - the run ends in error, `run_ended` all the same
            status = "error"
        finally:
            self.end(status, _ms(time.monotonic() - started))
        return status

    def _rebuild(self, stage: Stage) -> str:
        kind = self._rebuilt_stage()[1]
        step_id, component = self._step(1), f"rag_lab.{kind}"
        base = {"stage_id": stage.id, "kind": kind, "option": stage.option}
        self._emit(
            "rag_lab_stage_started",
            base | {"phase_label": self._text("stage.running", stage=self._label(stage))},
            step_id,
            component,
        )
        rss_before = self.deps.rss()
        started = time.monotonic()
        status, error_text, result = "ok", None, _Result(costs=[])
        try:
            if self.target == "pageindex":
                status, result = self._rewrite_tree(step_id, component, base)
            elif self.target == "graph":  # V1.2 story 13
                status, result = self._rebuild_graph(step_id, component, base)
            else:
                status, result = self._rewrite(stage, step_id, component, base)
        except StageSkipped as skipped:
            status, error_text = "skipped", skipped.render(self._lang)
        except StageFailed as failed:
            status, error_text = "error", failed.render(self._lang)
        except Exception as exc:  # noqa: BLE001 - AD-16: a stage's failure, never a crash
            status = "error"
            error_text = self._text(
                "stage.failed", error=type(exc).__name__, cause=exception_text(exc, self._lang)
            )
        duration = _ms(time.monotonic() - started)
        self._ended(step_id, component, base, status, result, error_text, duration, rss_before)
        return {"ok": "ok", "cancelled": "cancelled"}.get(status, "error")

    def _rewrite_tree(
        self, step_id: str, component: str, base: dict[str, Any]
    ) -> tuple[str, _Result]:
        """V1.2 story 11 (PageIndex): every summary of the tree (documents, sections) of the
        chain's documents rewritten by the active model, node by node, into the data folder
        (`method: llm`); the structure stays the corpus's. « Arrêter » keeps the earlier state:
        nothing is written (the file is replaced whole or not at all)."""
        deps, text, count = self.deps, self._text, self._int
        if deps.generator is None:
            raise StageSkipped(Message("rag_lab.contexts.no_model"))
        copy = deps.work_copy if self._reads_work_copy() else None
        documents = workcopy.documents(deps.content, deps.lang, copy)
        nodes = [n for n in pageindex.build_tree(documents).values() if n.id != pageindex.ROOT_ID]
        if not nodes:
            raise StageFailed(Message("rag_lab.update.empty_corpus"))
        progress = self._progress(step_id, component, base)
        began = time.monotonic()
        status, entries, tokens, failed, model = self._rewrite_summaries(
            nodes, step_id, "build", progress
        )
        if status == "ok" and entries:
            pageindex.write_rebuilt(
                deps.lang,
                entries,
                model=model or "?",
                tokens=tokens,
                duration_ms=_ms(time.monotonic() - began),
                folder=deps.lab_dir,
            )
        result = _Result(
            costs=[],  # the per-node costs are in the run's sum
            input_text=text("tree.rebuild_input", nodes=self._count(len(nodes), "node")),
            output_text=text(
                "tree.rebuild_output",
                done=count(len(entries)),
                total=count(len(nodes)),
                failed=count(failed),
            ),
            facts=[
                (text("fact.model"), model or "—"),
                (text("contexts.fact_rebuilt"), count(len(entries))),
                (text("contexts.fact_kept"), count(failed)),
                (text("contexts.fact_tokens"), count(tokens)),
            ],
        )
        return status, result

    def _rebuild_graph(
        self, step_id: str, component: str, base: dict[str, Any]
    ) -> tuple[str, _Result]:
        """V1.2 story 13 (GraphRAG): the graph of the chain's documents extracted again by the
        active model, passage by passage (`ENTITY:` / `RELATION:`), merged by name, its
        communities computed again, then one summary per community; written into the data
        folder (`method: llm`) at the end only: « Arrêter » keeps the earlier state. A passage
        whose answer is unreadable keeps the rule's extraction (`graph_passages_fallback`)."""
        deps, say, count = self.deps, self._text, self._int
        if deps.generator is None:
            raise StageSkipped(Message("rag_lab.contexts.no_model"))
        lang, size = self._lang, deps.shipped_chunk_max_chars
        copy = deps.work_copy if self._reads_work_copy() else None
        documents = workcopy.documents(deps.content, deps.lang, copy)
        passages = rag_graph.passages_of(documents, size, graph_audiences(deps.content))
        if not passages:
            raise StageFailed(Message("rag_lab.update.empty_corpus"))
        progress = self._progress(step_id, component, base)
        shipped = rag_graph.load_files(lang, deps.lab_dir)[0]
        planned = len(passages) + (len(shipped.communities) if shipped is not None else 0)
        began = time.monotonic()
        with deps.model_scope():
            out = self._extract_by_model(
                passages, step_id, "build", "graph_search", progress, planned
            )
            summaries: dict[str, Any] = {"status": "ok", "written": [], "failed": 0}
            kg = None
            if out["status"] == "ok":
                terms = rag_graph.vocabulary(documents, lang, size).terms  # recomputed here
                extractions = {
                    p.id: out["extractions"].get(p.id) or rag_graph.extract(p.text, terms, lang)
                    for p in passages
                }
                kg = rag_graph.merge(passages, extractions)
                kg.chunk_max_chars = size
                rag_graph.form_communities(kg, summarize=False)
                targets = list(kg.communities.values())
                summaries = self._summarize_by_model(
                    kg,
                    targets,
                    step_id,
                    "build",
                    "graph_search",
                    progress,
                    len(passages),
                    len(passages) + len(targets),
                )
        status = "cancelled" if "cancelled" in (out["status"], summaries["status"]) else "ok"
        if status == "ok" and kg is not None:
            file = rag_graph.to_file(
                kg,
                author="rebuilt",
                model=out["model"] or summaries.get("model") or "?",
                only_model=True,
                summaries=summaries["written"],
                measure={
                    "duration_ms": _ms(time.monotonic() - began),
                    "input_tokens": out["input"] + summaries.get("input", 0),
                    "output_tokens": out["output"] + summaries.get("output", 0),
                    "calls": out["calls"] + summaries.get("calls", 0),
                },
            )
            rag_graph.write_rebuilt(lang, file, deps.lab_dir)
        warnings = []
        if out["fallback"]:
            warnings.append(say("graph.passages_fallback", count=count(out["fallback"])))
        trimmed = out["trimmed"] + summaries.get("trimmed", 0)
        if trimmed:
            warnings.append(say("graph.input_trimmed", count=count(trimmed)))
        spent = (
            out["input"] + out["output"] + summaries.get("input", 0) + summaries.get("output", 0)
        )
        result = _Result(
            costs=[],  # the per-call costs are in the run's sum
            input_text=say("graph.rebuild_input", passages=self._count(len(passages), "passage")),
            output_text=say(
                "graph.rebuild_output",
                done=count(len(out["extractions"])),
                total=count(len(passages)),
                fallback=count(out["fallback"]),
                summaries=count(len(summaries["written"])),
                communities=count(len(kg.communities) if kg else 0),
            ),
            facts=[
                (say("fact.model"), out["model"] or "—"),
                (say("fact.graph_extracted"), count(len(out["extractions"]))),
                (say("fact.graph_fallback"), count(out["fallback"])),
                (say("fact.graph_summarized"), count(len(summaries["written"]))),
                (say("contexts.fact_tokens"), count(spent)),
            ],
            warning_text=" ".join(warnings) or None,
        )
        return status, result

    def _rewrite(
        self, stage: Stage, step_id: str, component: str, base: dict[str, Any]
    ) -> tuple[str, _Result]:
        deps, text, count = self.deps, self._text, self._int
        if deps.generator is None:
            raise StageSkipped(Message("rag_lab.contexts.no_model"))
        size = param(stage, "chunk_max_chars", deps.catalog)
        copy = deps.work_copy if self._reads_work_copy() else None
        documents = workcopy.documents(deps.content, deps.lang, copy)
        by_id = {d.doc_id: d for d in documents}
        chunks = chunk_documents(documents, size)
        if not chunks:
            raise StageFailed(Message("rag_lab.chunking.no_chunks"))
        progress = self._progress(step_id, component, base)
        entries: list[rag_contexts.ContextEntry] = []
        failed = tokens = 0
        model = ""
        status = "ok"
        began = time.monotonic()
        try:
            for done, chunk in enumerate(chunks, start=1):
                if deps.cancelled():
                    status = "cancelled"
                    break
                document = by_id[chunk.doc_id]
                ask = GenerationAsk(
                    context_text=text(
                        "contexts.document", title=document.title_text, text=document.text.strip()
                    ),
                    question=text("contexts.user", chunk=chunk.text),
                    step_id=step_id,
                    progress=lambda *_: None,
                    cancelled=deps.cancelled,
                    instruction=text("contexts.instruction"),
                    reserve=CONTEXT_MAX_TOKENS,
                )
                got = deps.generator(ask)  # `StageSkipped` without a model: nothing was rewritten
                model = got.model_label or model
                self.costs.append(
                    StageCost(
                        "build",
                        "chunking",
                        got.prompt_tokens + got.output_tokens,
                        got.duration_ms,
                        got.cost_usd,
                        got.impact,
                        note_text=None
                        if got.cost_usd is not None or got.impact is not None
                        else Message("rag_lab.costs.generation_unpriced"),
                    )
                )
                if got.status == "cancelled":
                    status = "cancelled"
                    break
                context = (
                    rag_contexts.clean_context(got.answer_text)
                    if got.status in ("completed", "limit")
                    else ""
                )
                if context:
                    entries.append(
                        rag_contexts.ContextEntry(
                            doc_id=chunk.doc_id,
                            position=chunk.position,
                            sha256=rag_contexts.fingerprint(chunk.text),
                            context_text=context,
                        )
                    )
                    tokens += got.output_tokens or deps.estimate_tokens(context)
                else:
                    failed += 1  # soft: the chunk keeps its context
                progress(done, len(chunks))
        finally:
            if entries:
                rag_contexts.write_rebuilt(
                    deps.lang,
                    entries,
                    model=model or "?",
                    chunk_max_chars=size,
                    tokens=tokens,
                    duration_ms=_ms(time.monotonic() - began),
                    folder=deps.lab_dir,
                )
        result = _Result(
            costs=[],  # the per-chunk costs are in the run's sum
            input_text=text("contexts.input", chunks=self._count(len(chunks), "extract")),
            output_text=text(
                "contexts.output",
                done=count(len(entries)),
                total=count(len(chunks)),
                failed=count(failed),
            ),
            facts=[
                (text("fact.model"), model or "—"),
                (text("contexts.fact_rebuilt"), count(len(entries))),
                (text("contexts.fact_kept"), count(failed)),
                (text("contexts.fact_tokens"), count(tokens)),
            ],
        )
        return status, result


# ---------- V1.2 story 13 (CAP-7): GraphRAG's graph, as the run and the page read it ----------


def graph_audiences(content: RagContent) -> dict[str, str]:
    """Each document's audience (`RagContent`): an added document is everyone's."""
    return {d.id: d.audience for d in content.documents}


def _elapsed(began: float) -> int:
    return max(1, math.ceil((time.perf_counter() - began) * 1000))


def _changed(before: dict[Any, list[str]], after: dict[Any, list[str]]) -> int:
    """The keys added, removed, or whose evidence changed."""
    return sum(1 for k in set(before) | set(after) if before.get(k) != after.get(k))


def graph_for(
    content: RagContent, lang: str, size: int, documents: Sequence[DocText], folder: Path
) -> tuple[rag_graph.Graph, int]:
    """The graph of `documents` (the structure from them, the rebuilt file read first) and the
    milliseconds its construction took. The vocabulary is the shipped corpus's (frozen)."""
    began = time.perf_counter()
    built = rag_graph.load_graph(
        documents,
        lang,
        size,
        audiences=graph_audiences(content),
        construction=workcopy.documents(content, lang, None),
        folder=folder,
    )
    return built, _elapsed(began)


def graph_key(lang: str, size: int, documents: Sequence[DocText], folder: Path) -> str:
    """What a graph is built from: the language, the passages' size, the documents' texts and
    the shipped and rebuilt files (the session's cache is keyed by it)."""
    digest = hashlib.sha256(f"{lang}\n{size}\n".encode())
    for doc in documents:
        digest.update(f"{doc.doc_id}\n{rag_contexts.fingerprint(doc.text)}\n".encode())
    for path in (
        config.content_file(rag_graph.GRAPH_FILE, lang),
        rag_graph.rebuilt_path(lang, folder),
    ):
        digest.update((file_digest(path) if path.is_file() else "-").encode())
    return digest.hexdigest()


def graph_mark(kg: rag_graph.Graph, lang: str) -> str:
    """« graphe livré, calculé par une règle, sans modèle » or « graphe reconstruit par le
    modèle X »."""
    if kg.rebuilt is not None:
        return _t("graph.mark_rebuilt", lang, model=kg.rebuilt.model)
    return _t("graph.mark_shipped", lang)


def graph_estimate(
    kg: rag_graph.Graph, estimate_tokens: Callable[[str], int], lang: str
) -> dict[str, Any] | None:
    """For a graph computed by the rule only: what an extraction by a model would need (a call
    per passage, plus one per community; the passages' tokens by the session's counter).
    Labelled an estimate, never measured, in no sum. `None` for a rebuilt graph."""
    if kg.rebuilt is not None:
        return None
    calls = len(kg.passages) + len(kg.communities)
    tokens = sum(estimate_tokens(p.text) for p in kg.passages.values())
    text = _t("graph.estimate", lang, calls=lang_int(calls, lang), tokens=lang_int(tokens, lang))
    return {"calls": calls, "input_tokens": tokens, "text": text}


def _ms(seconds: float) -> int:
    return round(seconds * 1000)


# Short words that say nothing of a subject, by language, accents folded (BM25 skips them;
# the corpus, read from the session's language's index, and the question are in it). Words that
# may be acronyms or times are kept: « it », « us », « who » (IT, US, WHO), « am » (9 am).
STOP_WORDS_BY_LANG: dict[str, frozenset[str]] = {
    "fr": frozenset(
        "au aux avec ce ces cette dans de des du elle elles en est et il ils la le les leur "
        "leurs lui mais me ne nous on ou par pas pour qu que qui sa se ses si son sont sur ta "
        "te tes ton tu un une vos votre vous".split()
    ),
    "en": frozenset(
        "a about after all also an and any are as at be been before being but by can "
        "could did do does for from had has have he her here him his how if in into is its "
        "me more most my no not of on or other our out over she should so some such than "
        "that the their them then there these they this those to too under up was we were "
        "what when where which while whom why will with would you your".split()
    ),
    "de": frozenset(
        "aber alle als am an auch auf aus bei bin bis bist da damit dann das dass dem den "
        "der des die dir doch du durch ein eine einem einen einer eines er es fur hat haben "
        "hatte ich ihr ihre im in ist ja kann man mit nach nicht noch nur ob oder sich sie "
        "sind so uber um und uns unter vom von vor war waren was wenn wer werden wie wir "
        "wird wo zu zum zur".split()
    ),
}


_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_QUOTES = " \t\"'«»“”„`"


# A preamble the model adds (« Voici la question reformulée : »), alone on its line or before
# the quoted query on the same line.
_PREAMBLE_QUOTED = re.compile(r"^[^:«\"“]{1,80}:\s*[«\"“](.+?)[»\"”]\s*$")


def _clean_line(line: str) -> str:
    line = _BULLET.sub("", line).strip()
    if line.endswith(":"):  # a preamble alone on its line, never a query
        return ""
    if quoted := _PREAMBLE_QUOTED.match(line):
        line = quoted.group(1)
    return line.strip(_QUOTES)


def parse_queries(option: str, answer: str) -> list[str]:
    """V1.2 story 5 (CAP-3): the queries in a model's answer to the query understanding.
    A preamble (a line ending with a colon, or « … : » before a quoted query) is dropped.
    `rewrite` and `follow_up`: the first non-empty line. `decompose`: one query per line,
    bullets and numbers removed, duplicates dropped, `SUBQUERIES_MAX` kept. `hyde`: the whole
    answer, one paragraph. Each is cut at its bound; nothing usable gives an empty list."""
    lines = [c for line in answer.splitlines() if (c := _clean_line(line))]
    if option == "hyde":
        whole = " ".join(lines)
        return [whole[:HYDE_MAX_CHARS].strip()] if whole else []
    if option == "decompose":
        unique = dict.fromkeys(line[:QUERY_MAX_CHARS].strip() for line in lines)
        return list(unique)[:SUBQUERIES_MAX]
    return [lines[0][:QUERY_MAX_CHARS].strip()] if lines else []


def fold(text: str) -> str:
    """Lower case, accents dropped (« Télétravail » → « teletravail », « für » → « fur »)."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def bm25_terms(text: str, lang: str = config.DEFAULT_LANGUAGE) -> list[str]:
    """BM25's words: `\\w+` in lower case, accents folded, two characters or more (« IA »,
    « RH », « 35 » kept), the short stop words of `lang` (the session's) left out."""
    stop = STOP_WORDS_BY_LANG.get(
        config.as_language(lang), STOP_WORDS_BY_LANG[config.DEFAULT_LANGUAGE]
    )
    return [w for w in _WORD.findall(fold(text)) if len(w) >= 2 and w not in stop]


@dataclass(eq=False)
class LexicalIndex:
    """B2 (2026-10-05): BM25's inverted index, built once at BUILD (no learned model, only
    counts): each document's terms and how often they occur in it, its length in terms, each
    term's document frequency (the documents that contain it) and the mean length."""

    counts: list[dict[str, int]]
    lengths: list[int]
    df: dict[str, int]
    mean: float

    @property
    def n(self) -> int:
        return len(self.lengths)

    @property
    def vocabulary(self) -> int:
        """The distinct terms of the index."""
        return len(self.df)

    @property
    def occurrences(self) -> int:
        """Every term of every document, repeats included."""
        return sum(self.lengths)


def lexical_index(documents: Sequence[str], lang: str = config.DEFAULT_LANGUAGE) -> LexicalIndex:
    """The inverted index BM25 reads (`bm25_terms` of each document; `lang`: whose stop
    words)."""
    docs = [bm25_terms(d, lang) for d in documents]
    counts: list[dict[str, int]] = []
    df: dict[str, int] = {}
    for words in docs:
        tf: dict[str, int] = {}
        for word in words:
            tf[word] = tf.get(word, 0) + 1
        counts.append(tf)
        for word in tf:
            df[word] = df.get(word, 0) + 1
    lengths = [len(d) for d in docs]
    mean = (sum(lengths) / len(docs) or 1.0) if docs else 1.0
    return LexicalIndex(counts=counts, lengths=lengths, df=df, mean=mean)


def bm25_scores(
    index: LexicalIndex, query: str, lang: str = config.DEFAULT_LANGUAGE
) -> list[float]:
    """Okapi BM25 of each document of `index` for the query: k1 = 1.5, b = 0.75, the idf
    `ln(1 + (N − df + 0.5) / (df + 0.5))` (never negative), read from the index's counts."""
    n = index.n
    terms = list(dict.fromkeys(bm25_terms(query, lang)))
    scores = []
    for counts, length in zip(index.counts, index.lengths, strict=True):
        score = 0.0
        for term in terms:
            tf = counts.get(term, 0)
            if not tf:
                continue
            df = index.df[term]
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            norm = tf + BM25_K1 * (1 - BM25_B + BM25_B * length / index.mean)
            score += idf * tf * (BM25_K1 + 1) / norm
        scores.append(score)
    return scores


def bm25(query: str, documents: Sequence[str], lang: str = config.DEFAULT_LANGUAGE) -> list[float]:
    """Okapi BM25 of each document for the query, in pure Python: the index built
    (`lexical_index`), then the query scored on it (`bm25_scores`); `lang`: whose stop
    words."""
    return bm25_scores(lexical_index(documents, lang), query, lang)


def rrf(lists: Sequence[Sequence[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal rank fusion of ranked lists of ids: `(id, Σ 1 / (k + rank))`, best first
    (ties by best rank, then id)."""
    scores: dict[int, float] = {}
    best: dict[int, int] = {}
    for ranked in lists:
        for rank, item in enumerate(ranked, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            best[item] = min(best.get(item, rank), rank)
    return sorted(scores.items(), key=lambda x: (-round(x[1], TIE_DIGITS), best[x[0]], x[0]))


def last_run(envelopes: Sequence[Any]) -> list[dict[str, Any]]:
    """The envelopes of the last run in `envelopes` (a journal's), from its
    `rag_lab_run_started` on: the page rebuilds it after a reload (AD-1)."""
    start = next(
        (
            i
            for i in range(len(envelopes) - 1, -1, -1)
            if envelopes[i].kind == "rag_lab_run_started"
            and not str(envelopes[i].payload.get("run_id", "")).startswith(APART_PREFIXES)
        ),
        None,
    )
    if start is None:
        return []
    run_id = envelopes[start].payload.get("run_id")
    return [
        e.model_dump(mode="json")
        for e in envelopes[start:]
        if e.kind.startswith("rag_lab_") and e.payload.get("run_id") == run_id
    ]


def last_update(envelopes: Sequence[Any]) -> list[dict[str, Any]]:
    """V1.2 story 3: the envelopes of the last update run (`upd{n}`) in `envelopes`, from its
    `rag_lab_run_started` on, so that the page shows its cost again after a reload."""
    start = next(
        (
            i
            for i in range(len(envelopes) - 1, -1, -1)
            if envelopes[i].kind == "rag_lab_run_started"
            and str(envelopes[i].payload.get("run_id", "")).startswith(UPDATE_RUN_PREFIX)
        ),
        None,
    )
    if start is None:
        return []
    run_id = envelopes[start].payload.get("run_id")
    return [
        e.model_dump(mode="json")
        for e in envelopes[start:]
        if e.kind.startswith("rag_lab_") and e.payload.get("run_id") == run_id
    ]
