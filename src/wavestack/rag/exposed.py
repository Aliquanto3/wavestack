"""V1.2 story 20 (CAP-18): what the RAG workshop exposes as an MCP server, read only.

- `refusal`: whether a chain can be exposed (decision D12), a rule computed on its stages, never
  on a preset's name. Every valid chain ends with the Context and the Generation; neither runs
  for the client. Exposable: a segment (between `FIXED_HEAD` and `FIXED_TAIL`) with a search,
  every stage of it in `EXPOSABLE_SEGMENT`, and the brick's head (its index read, never written).
- `ExposedChain`: the chain frozen at the start (a deep copy), its architecture and its stages.
- `search`: a `LabRun` of the frozen chain on the shipped corpus (no work copy, no generator,
  no compressor, no CAG), its last ranked list, the `hr` passages removed, cut to `top_k`.

Nothing here writes, generates or calls a cloud model. `rag/lab.py` is read, never changed.
"""

from __future__ import annotations

import itertools
import string
from dataclasses import dataclass, replace
from typing import Any, NamedTuple

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from wavestack import config
from wavestack.rag import lab as rag_lab
from wavestack.rag.corpus import RagContent

FILE = "rag_mcp.yaml"
# The types of stage the exposed segment may hold: the searches, the fusion, the reranking.
# `query` (its four options call the generative model) is refused; a type added later is
# refused until it is added here.
EXPOSABLE_SEGMENT = ("vector_search", "lexical_search", "fusion", "rerank")
# The brick's head: its index serves, read only (`LabRun._uses_brick_index`, copied here).
BRICK_HEAD = {"chunking": "paragraphs", "embedding": "declared", "vector_store": "sqlite_vec"}
REASONS = ("invalid", "whole_corpus", "searches_itself", "model_stage", "head")
QUESTION_MAX = rag_lab.QUESTION_MAX
TOP_K_MAX = 10
TOP_K_DEFAULT = 3
RUN_PREFIX = "mcp"  # a served call's run id, `mcp1`: its events never reach the page


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- texts (content/rag_mcp.yaml ×3) ----------


class ServerTexts(_Strict):
    instructions_text: str = Field(min_length=1)


class SearchToolTexts(_Strict):
    description_text: str = Field(min_length=1)
    question_text: str = Field(min_length=1)
    top_k_text: str = Field(min_length=1)


class DescribeToolTexts(_Strict):
    description_text: str = Field(min_length=1)


class ToolTexts(_Strict):
    search_documents: SearchToolTexts
    describe_architecture: DescribeToolTexts


class ReasonTexts(_Strict):
    invalid: str = Field(min_length=1)  # {reason}
    whole_corpus: str = Field(min_length=1)  # {option}
    searches_itself: str = Field(min_length=1)  # {option}
    model_stage: str = Field(min_length=1)  # {stage}
    head: str = Field(min_length=1)


class DescribeTexts(_Strict):
    composed_label_text: str = Field(min_length=1)
    stage_text: str = Field(min_length=1)  # {stage}, {option}
    header_text: str = Field(min_length=1)  # {architecture}
    corpus_text: str = Field(min_length=1)
    hr_text: str = Field(min_length=1)
    frozen_text: str = Field(min_length=1)
    not_run_text: str = Field(min_length=1)
    limits: list[str] = Field(min_length=1)


class SearchTexts(_Strict):
    citation_text: str = Field(min_length=1)  # {title}, {doc_id}, {position}
    passage_text: str = Field(min_length=1)  # {rank}, {citation}, {score}, {text}
    header_text: str = Field(min_length=1)  # {n}, {architecture}
    removed_text: str = Field(min_length=1)  # {n}
    none_text: str = Field(min_length=1)
    no_score_text: str = Field(min_length=1)


class CardTexts(_Strict):
    title_text: str = Field(min_length=1)
    hint_text: str = Field(min_length=1)
    state_label_text: str = Field(min_length=1)
    state_on_text: str = Field(min_length=1)
    state_off_text: str = Field(min_length=1)
    start_text: str = Field(min_length=1)
    stop_text: str = Field(min_length=1)
    address_label_text: str = Field(min_length=1)
    token_label_text: str = Field(min_length=1)
    token_hidden_text: str = Field(min_length=1)
    reveal_text: str = Field(min_length=1)
    hide_text: str = Field(min_length=1)
    copy_token_text: str = Field(min_length=1)
    copy_command_text: str = Field(min_length=1)
    copied_text: str = Field(min_length=1)
    copy_failed_text: str = Field(min_length=1)
    chain_label_text: str = Field(min_length=1)
    frozen_text: str = Field(min_length=1)
    tools_label_text: str = Field(min_length=1)
    risk_label_text: str = Field(min_length=1)
    rule_label_text: str = Field(min_length=1)
    hidden_tool_text: str = Field(min_length=1)
    command_label_text: str = Field(min_length=1)
    command_note_text: str = Field(min_length=1)
    copilot_text: str = Field(min_length=1)
    language_text: str = Field(min_length=1)
    refused_label_text: str = Field(min_length=1)


class ExposedTexts(_Strict):
    """`content/rag_mcp.yaml`: the tools' descriptions the client's model reads, the reasons of
    a refusal and the card's texts, in one language."""

    server: ServerTexts
    tools: ToolTexts
    reasons: ReasonTexts
    describe: DescribeTexts
    search: SearchTexts
    card: CardTexts

    @model_validator(mode="after")
    def _known_fields(self) -> ExposedTexts:
        self.reasons.invalid.format(reason="")
        self.reasons.whole_corpus.format(option="")
        self.reasons.searches_itself.format(option="")
        self.reasons.model_stage.format(stage="")
        self.reasons.head.format()
        self.describe.stage_text.format(stage="", option="")
        self.describe.header_text.format(architecture="")
        self.search.citation_text.format(title="", doc_id="", position=1)
        self.search.passage_text.format(rank=1, citation="", score="", text="")
        self.search.header_text.format(n=1, architecture="")
        self.search.removed_text.format(n=1)
        return self


def load_texts(lang: str | None = None) -> ExposedTexts:
    """Read at each start (a few kilobytes): raises on a missing or invalid file."""
    path = config.content_file(FILE, lang)
    return ExposedTexts.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


# ---------- the rule (D12) ----------


class Refusal(NamedTuple):
    reason: str  # one of `REASONS`
    text: str


def segment_of(pipeline: rag_lab.Pipeline) -> list[rag_lab.Stage]:
    head, tail = len(rag_lab.FIXED_HEAD), len(rag_lab.FIXED_TAIL)
    return list(pipeline.stages[head:-tail])


def brick_head(
    pipeline: rag_lab.Pipeline, catalog: rag_lab.Catalog, shipped_chunk_max_chars: int
) -> bool:
    """The brick's own head (`LabRun._uses_brick_index` without the work copy, which the
    server never reads): its chunking at the shipped size, its model, sqlite-vec."""
    for kind, option in BRICK_HEAD.items():
        stage = pipeline.find(kind)
        if stage is None or stage.option != option:
            return False
    chunking = pipeline.find("chunking")
    assert chunking is not None
    return rag_lab.param(chunking, "chunk_max_chars", catalog) == shipped_chunk_max_chars


def refusal(
    pipeline: rag_lab.Pipeline,
    catalog: rag_lab.Catalog,
    shipped_chunk_max_chars: int,
    texts: ExposedTexts,
) -> Refusal | None:
    """Why this chain cannot be exposed, in the order of `REASONS`, or `None`."""
    reasons = texts.reasons
    invalid = rag_lab.validate_pipeline(pipeline, catalog)
    if invalid is not None:
        return Refusal("invalid", reasons.invalid.format(reason=invalid))
    context = pipeline.stages[-len(rag_lab.FIXED_TAIL)]
    option = catalog.option_label(context.kind, context.option)
    if context.option in rag_lab.CORPUS_OPTIONS:
        return Refusal("whole_corpus", reasons.whole_corpus.format(option=option))
    segment = segment_of(pipeline)
    if not any(s.kind in rag_lab.SEARCHES for s in segment):
        return Refusal("searches_itself", reasons.searches_itself.format(option=option))
    outside = next((s for s in segment if s.kind not in EXPOSABLE_SEGMENT), None)
    if outside is not None:
        stage = catalog.content.stages[outside.kind].label_text
        return Refusal("model_stage", reasons.model_stage.format(stage=stage))
    if not brick_head(pipeline, catalog, shipped_chunk_max_chars):
        return Refusal("head", reasons.head.format())
    return None


# ---------- the frozen chain and what the tools return ----------


class StageInfo(_Strict):
    kind: str
    option: str
    label_text: str
    option_label_text: str


@dataclass(frozen=True)
class ExposedChain:
    """The chain frozen at the start: a deep copy, never the page's own object."""

    pipeline: rag_lab.Pipeline
    architecture: str  # the preset whose segment it has, else `custom`
    label_text: str
    stages: tuple[StageInfo, ...]


def freeze(
    pipeline: rag_lab.Pipeline, catalog: rag_lab.Catalog, texts: ExposedTexts
) -> ExposedChain:
    frozen = pipeline.model_copy(deep=True)
    segment = tuple((s.kind, s.option) for s in segment_of(frozen))
    preset = next((name for name, seg in rag_lab.PRESETS.items() if seg == segment), None)
    if preset is not None:
        label = catalog.content.presets[preset].label_text
    else:
        label = texts.describe.composed_label_text
    stages = tuple(
        StageInfo(
            kind=s.kind,
            option=s.option,
            label_text=catalog.content.stages[s.kind].label_text,
            option_label_text=catalog.option_label(s.kind, s.option),
        )
        for s in frozen.stages
    )
    return ExposedChain(frozen, preset or "custom", label, stages)


class Passage(_Strict):
    rank: int
    doc_id: str
    chunk_id: int
    title_text: str
    position: int  # the excerpt's rank in its document
    text: str
    score: float | None
    citation: str


class SearchResult(_Strict):
    architecture: str
    label_text: str
    top_k: int
    passages: list[Passage]
    removed_hr: int  # the passages of an `hr` document removed from the ranked list


class Description(_Strict):
    server: str
    architecture: str
    label_text: str
    stages: list[StageInfo]
    searched: list[str]  # the kinds the server runs for the client (the head and the segment)
    corpus_text: str
    hr_text: str
    frozen_text: str
    not_run_text: str
    limits: list[str]
    top_k_max: int


def describe(chain: ExposedChain, texts: ExposedTexts, server: str) -> Description:
    d = texts.describe
    searched = [s.kind for s in chain.pipeline.stages if s.kind not in rag_lab.FIXED_TAIL]
    return Description(
        server=server,
        architecture=chain.architecture,
        label_text=chain.label_text,
        stages=list(chain.stages),
        searched=searched,
        corpus_text=d.corpus_text,
        hr_text=d.hr_text,
        frozen_text=d.frozen_text,
        not_run_text=d.not_run_text,
        limits=list(d.limits),
        top_k_max=TOP_K_MAX,
    )


def describe_text(description: Description, texts: ExposedTexts) -> str:
    d = texts.describe
    lines = [d.header_text.format(architecture=description.label_text)]
    lines += [
        f"- {d.stage_text.format(stage=s.label_text, option=s.option_label_text)}"
        for s in description.stages
    ]
    lines += [description.not_run_text, description.corpus_text, description.hr_text]
    lines += [description.frozen_text, *(f"- {x}" for x in description.limits)]
    return "\n".join(lines)


class SearchFailed(Exception):
    """The run did not end `ok`: its status and the first stage's error, if any."""

    def __init__(self, status: str, error_text: str | None) -> None:
        super().__init__(status)
        self.status = status
        self.error_text = error_text


_RUNS = itertools.count(1)


def hr_documents(content: RagContent) -> frozenset[str]:
    return frozenset(d.id for d in content.documents if d.audience == "hr")


def search(
    chain: ExposedChain,
    question: str,
    top_k: int,
    deps: rag_lab.LabDeps,
    texts: ExposedTexts,
) -> SearchResult:
    """One `LabRun` of the frozen chain on `deps.content` (the shipped corpus), whatever `deps`
    holds of a work copy, a generator, a compressor or a CAG: none of them reaches the run. Its
    last ranked list (that of the segment's last stage), the `hr` passages removed, ranked again
    from 1 and cut to `top_k`. Raises `SearchFailed` when the run did not end `ok`."""
    errors: list[str] = []

    def capture(kind: str, payload: dict[str, Any], step_id: str, component: str) -> None:
        if kind == "rag_lab_stage_ended" and payload.get("status") == "error":
            errors.append(str(payload.get("error_text") or ""))

    confined = replace(
        deps,
        emit=capture,
        generator=None,
        cag=None,
        work_copy=None,
        history=(),
        meter=None,
        compressor=lambda: (None, None),
    )
    run = rag_lab.LabRun(f"{RUN_PREFIX}{next(_RUNS)}", question, chain.pipeline, confined)
    status = run.run()
    if status != "ok" or run.chain is None:
        raise SearchFailed(status, errors[0] if errors else None)
    ranked = run.chain.ranked or []
    hr = hr_documents(deps.content)
    kept = [item for item in ranked if item.doc_id not in hr]
    chunks = run.chain.chunks
    passages = []
    for rank, item in enumerate(kept[:top_k], start=1):
        position = chunks[item.chunk_id - 1].position if 0 < item.chunk_id <= len(chunks) else 0
        citation = texts.search.citation_text.format(
            title=item.title_text, doc_id=item.doc_id, position=position
        )
        passages.append(
            Passage(
                rank=rank,
                doc_id=item.doc_id,
                chunk_id=item.chunk_id,
                title_text=item.title_text,
                position=position,
                text=item.text,
                score=item.score,
                citation=citation,
            )
        )
    return SearchResult(
        architecture=chain.architecture,
        label_text=chain.label_text,
        top_k=top_k,
        passages=passages,
        removed_hr=len(ranked) - len(kept),
    )


def search_text(found: SearchResult, texts: ExposedTexts, lang: str) -> str:
    s = texts.search
    lines = [s.header_text.format(n=len(found.passages), architecture=found.label_text)]
    for p in found.passages:
        score = rag_lab.score_text(p.score, lang) if p.score is not None else s.no_score_text
        lines.append(
            s.passage_text.format(rank=p.rank, citation=p.citation, score=score, text=p.text)
        )
    if not found.passages:
        lines.append(s.none_text)
    if found.removed_hr:
        lines.append(s.removed_text.format(n=found.removed_hr))
    return "\n\n".join(lines)
