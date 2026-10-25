"""V1.2 story 16 (CAP-12): a run of the RAG workshop as a tree of steps, read from the journal.

The step ids say the tree (`rag_lab.parent_step`): the run (`lab1`), its stages (`lab1.s3`),
a part of a stage run apart (`lab1.s3.index`). A model call is traced on its stage's step
(`step_id` and `call_id`, `origin` « model »): it becomes a child of that stage, numbered in
the order of its calls (`lab1.s3.c1`, `lab1.s3.c2`…).

Pure: the events in, a `RagLabStep` out. `texts` (the OTLP export's opt-in content only)
pairs each node's id with the text it received and the text it made; the tree itself never
carries a question, a passage or an answer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from wavestack.trace.catalog import RagLabStep
from wavestack.trace.envelope import Envelope

LAB_CONTEXT = "rag_lab"


@dataclass
class Texts:
    """What the export may send when `[otel] capture_content` is on: by node id, the text the
    step received and the one it made (`None`: none)."""

    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)


def run_events(events: Sequence[Envelope], run_id: str) -> list[Envelope]:
    """The workshop's events of run `run_id`, from its `rag_lab_run_started` to its
    `rag_lab_run_ended` (included, when it is there); empty when the run is not found."""
    start = None
    for i in range(len(events) - 1, -1, -1):
        e = events[i]
        if e.kind == "rag_lab_run_started" and e.payload.get("run_id") == run_id:
            start = i
            break
    if start is None:
        return []
    found: list[Envelope] = []
    for e in events[start:]:
        if e.context_id != LAB_CONTEXT:
            continue
        found.append(e)
        if e.kind == "rag_lab_run_ended" and e.payload.get("run_id") == run_id:
            break
    return found


def _sum(values: list[int | None]) -> int | None:
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def build(
    events: Sequence[Envelope],
    run_id: str,
    *,
    model: dict[str, Any] | None = None,
    ended: tuple[dict[str, Any], datetime] | None = None,
    texts: Texts | None = None,
) -> RagLabStep | None:
    """The tree of run `run_id` from its events (`run_events`). `model`: the run's model
    (`id`, `label`, `provider`), named on its calls. `ended`: the `rag_lab_run_ended` payload
    and time, when it is not yet in the journal (the session builds the tree just before it
    emits it). `texts`, when given, is filled with the export's opt-in content. `None`: no
    `rag_lab_run_started` for this run."""
    started = next(
        (e for e in events if e.kind == "rag_lab_run_started" and e.payload["run_id"] == run_id),
        None,
    )
    if started is None:
        return None
    labels = {s["stage_id"]: s["label_text"] for s in started.payload.get("stages", [])}
    root = RagLabStep(id=run_id, kind="run", name=run_id, status="running")
    root.started_at = started.ts
    nodes: dict[str, RagLabStep] = {run_id: root}
    calls: dict[str, int] = {}  # step id -> calls seen
    open_calls: dict[str, RagLabStep] = {}  # step id -> its call under way
    prompts: dict[str, str] = {}  # stage node id -> its prompt as sent (`prompt_text`)
    model = model or {}
    if texts is not None and started.payload.get("question"):
        texts.inputs[run_id] = started.payload["question"]

    def stage_node(e: Envelope) -> RagLabStep:
        step = e.step_id or ""
        node = nodes.get(step)
        if node is None:
            p = e.payload
            part = p.get("part")
            parent = step.rsplit(".", 1)[0] if part else run_id
            label = labels.get(p.get("stage_id", ""), p.get("kind", step))
            node = RagLabStep(
                id=step,
                parent=parent if parent in nodes else run_id,
                kind="part" if part else "stage",
                name=f"{label} · {part}" if part else label,
                stage_kind=p.get("kind"),
                option=p.get("option"),
                status="running",
            )
            nodes[step] = node
            nodes[node.parent or run_id].children.append(node)
        return node

    for e in events:
        p = e.payload
        if e.kind == "rag_lab_stage_started" and p.get("run_id") == run_id:
            stage_node(e).started_at = e.ts
        elif e.kind == "rag_lab_stage_ended" and p.get("run_id") == run_id:
            node = stage_node(e)
            node.status = p["status"]
            node.ended_at = e.ts
            node.started_at = node.started_at or e.ts
            node.duration_ms = p.get("duration_ms")
            tokens = _sum([c.get("tokens") for c in p.get("costs", [])])
            node.tokens = tokens
            if p.get("prompt_text"):
                prompts[node.id] = p["prompt_text"]
            if texts is not None and p.get("kind") == "generation" and p.get("output_text"):
                texts.outputs[run_id] = p["output_text"]
        elif e.kind == "model_call_started":
            step = e.step_id or run_id
            calls[step] = calls.get(step, 0) + 1
            parent = nodes.get(step, root)
            call = RagLabStep(
                id=f"{parent.id}.c{calls[step]}",
                parent=parent.id,
                kind="model_call",
                name=model.get("label") or model.get("id") or "model",
                model=model.get("id"),
                provider=model.get("provider"),
                status="running",
                started_at=e.ts,
            )
            parent.children.append(call)
            open_calls[step] = call
        elif e.kind == "model_call_ended":
            call = open_calls.pop(e.step_id or run_id, None)
            if call is None:
                continue
            call.status = p.get("stop_reason", "stop")
            call.ended_at = e.ts
            call.duration_ms = p.get("duration_ms")
            call.input_tokens = p.get("prompt_tokens")
            call.output_tokens = p.get("output_tokens")
            if texts is not None and p.get("text"):
                texts.outputs[call.id] = p["text"]
    # A part runs before its stage at times (BM25's index, at the end of BUILD): moved under
    # its stage once both are known.
    for node in list(nodes.values()):
        if node.kind != "part":
            continue
        owner = nodes.get(node.id.rsplit(".", 1)[0])
        if owner is not None and owner.id != node.parent:
            nodes[node.parent or run_id].children.remove(node)
            node.parent = owner.id
            owner.children.append(node)
    if ended is None:
        last = next(
            (e for e in events if e.kind == "rag_lab_run_ended" and e.payload["run_id"] == run_id),
            None,
        )
        ended = (last.payload, last.ts) if last is not None else None
    if ended is not None:
        root.status = ended[0]["status"]
        root.duration_ms = ended[0].get("duration_ms")
        root.ended_at = ended[1]
    for node in nodes.values():
        model_calls = [c for c in node.children if c.kind == "model_call"]
        if node.kind != "run" and model_calls:
            node.input_tokens = _sum([c.input_tokens for c in model_calls])
            node.output_tokens = _sum([c.output_tokens for c in model_calls])
        # The prompt as sent belongs to a stage's only call (the generation's, a short task's).
        if texts is not None and node.id in prompts and len(model_calls) == 1:
            texts.inputs[model_calls[0].id] = prompts[node.id]
    return root
