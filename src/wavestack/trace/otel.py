"""V1.2 story 16 (CAP-12): the OTLP export of a workshop run's tree, GenAI conventions.

Behind the `otel` extra (`opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-common`):
without it, `missing()` says why and nothing is built. The SDK makes the spans, the OTLP
encoder their protobuf (`ExportTraceServiceRequest`); WaveStack's factory sends it
(`net.factory.create_client`, AD-15), never the SDK's exporter. Nothing is sent without a
`[otel] endpoint`, and only on the trainer's request (the « Exporter » button).

Conventions: OpenTelemetry GenAI semantic conventions (status Development), repository
`open-telemetry/semantic-conventions-genai` read on 2026-10-25 (commit 9ffc7e0 of 2026-10-21,
built on semantic-conventions v1.44.0); attribute names as in `opentelemetry-semantic-
conventions` 0.65b0. The run is an `invoke_workflow` span, a model call a `chat` inference
span, a search stage a `retrieval` span; the other stages and their parts are `INTERNAL` spans
with `wavestack.*` attributes.

Content: by default no text leaves (the conventions' default, and WaveStack's journal rule:
the question, the passages, the prompts and the answers stay on the workstation). With
`[otel] capture_content = true` the run carries the question and the answer, a model call
its prompt and its answer (`gen_ai.input.messages`, `gen_ai.output.messages`, JSON strings).
Headers: `Content-Type`, WaveStack's `User-Agent` and, when `[otel] auth_env` names one, the
collector's `Authorization`; never a cloud model's key.
"""

from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime
from typing import Any

import httpx

from wavestack.messages import Message
from wavestack.net.factory import create_client
from wavestack.net.guard import NetworkBlocked
from wavestack.trace.catalog import RagLabStep
from wavestack.trace.tree import Texts

SCHEMA = "https://opentelemetry.io/schemas/1.44.0"
SCOPE = "wavestack.rag_lab"
WORKFLOW = "wavestack.rag_lab"
TRACES_PATH = "/v1/traces"
# The stages that search the corpus: GenAI `retrieval` spans.
RETRIEVAL_KINDS = frozenset({"vector_search", "lexical_search"})
_MODULES = ("opentelemetry.sdk.trace", "opentelemetry.exporter.otlp.proto.common")


class ExportFailed(Exception):
    def __init__(self, reason_text: Message) -> None:
        super().__init__(str(reason_text))
        self.reason_text = reason_text


def missing() -> Message | None:
    """Why the export cannot be built (the extra is not installed), or `None`."""
    for name in _MODULES:
        try:
            found = importlib.util.find_spec(name) is not None
        except ModuleNotFoundError:
            found = False
        if not found:
            return Message("rag_lab.otel.missing")
    return None


def traces_url(endpoint: str) -> str:
    """The OTLP/HTTP traces URL: the endpoint as set when it already ends in `/v1/traces`,
    otherwise that path added (the `OTEL_EXPORTER_OTLP_ENDPOINT` rule)."""
    base = endpoint.rstrip("/")
    return base if base.endswith(TRACES_PATH) else base + TRACES_PATH


def _ns(moment: datetime | None) -> int | None:
    return int(moment.timestamp() * 1_000_000_000) if moment is not None else None


def _messages(role: str, text: str) -> str:
    """The conventions' message shape (`parts` of `type` « text »), as a JSON string: span
    attributes do not take structured values yet."""
    return json.dumps(
        [{"role": role, "parts": [{"type": "text", "content": text}]}], ensure_ascii=False
    )


def _attributes(node: RagLabStep, texts: Texts | None) -> tuple[str, Any, dict[str, Any]]:
    """The span's name, kind and attributes for one node of the tree."""
    from opentelemetry.trace import SpanKind

    attrs: dict[str, Any] = {"wavestack.rag_lab.step.id": node.id}
    if node.duration_ms is not None:
        attrs["wavestack.rag_lab.duration_ms"] = node.duration_ms
    if node.kind == "run":
        attrs |= {
            "gen_ai.operation.name": "invoke_workflow",
            "gen_ai.workflow.name": WORKFLOW,
            "wavestack.rag_lab.run.id": node.id,
            "wavestack.rag_lab.status": node.status,
        }
        if texts is not None and node.id in texts.inputs:
            attrs["gen_ai.input.messages"] = _messages("user", texts.inputs[node.id])
        if texts is not None and node.id in texts.outputs:
            attrs["gen_ai.output.messages"] = _messages("assistant", texts.outputs[node.id])
        return f"invoke_workflow {WORKFLOW}", SpanKind.INTERNAL, attrs
    if node.kind == "model_call":
        model = node.model or node.name
        local = node.provider in (None, "llama_cpp")
        attrs |= {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": node.provider or "llama_cpp",
            "gen_ai.request.model": model,
            "gen_ai.response.finish_reasons": [node.status],
        }
        if node.input_tokens is not None:
            attrs["gen_ai.usage.input_tokens"] = node.input_tokens
        if node.output_tokens is not None:
            attrs["gen_ai.usage.output_tokens"] = node.output_tokens
        if texts is not None and node.id in texts.inputs:
            attrs["gen_ai.input.messages"] = _messages("user", texts.inputs[node.id])
        if texts is not None and node.id in texts.outputs:
            attrs["gen_ai.output.messages"] = _messages("assistant", texts.outputs[node.id])
        return f"chat {model}", SpanKind.INTERNAL if local else SpanKind.CLIENT, attrs
    attrs |= {
        "wavestack.rag_lab.stage.kind": node.stage_kind or "",
        "wavestack.rag_lab.stage.option": node.option or "",
        "wavestack.rag_lab.status": node.status,
    }
    for key, value in (
        ("gen_ai.usage.input_tokens", node.input_tokens),
        ("gen_ai.usage.output_tokens", node.output_tokens),
        ("wavestack.rag_lab.tokens", node.tokens),
    ):
        if value is not None:
            attrs[key] = value
    if node.kind == "stage" and node.stage_kind in RETRIEVAL_KINDS:
        attrs |= {"gen_ai.operation.name": "retrieval", "gen_ai.data_source.id": node.option}
        return f"retrieval {node.option}", SpanKind.INTERNAL, attrs
    return (
        node.name if node.kind == "part" else node.stage_kind or node.name,
        (SpanKind.INTERNAL),
        attrs,
    )


def encode(
    tree: RagLabStep, texts: Texts | None = None, *, service_version: str = ""
) -> tuple[bytes, int]:
    """The tree as an OTLP `ExportTraceServiceRequest` (protobuf) and its number of spans.
    `texts`: the opt-in content (`None`: none). Raises `ExportFailed` without the extra."""
    if (why := missing()) is not None:
        raise ExportFailed(why)
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import Status, StatusCode

    # Never the environment's resource (`OTEL_RESOURCE_ATTRIBUTES`): only these attributes.
    resource = Resource(
        {"service.name": "wavestack", "service.version": service_version}, schema_url=SCHEMA
    )
    provider = TracerProvider(resource=resource)
    memory = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    tracer = provider.get_tracer(SCOPE, service_version, schema_url=SCHEMA)
    fallback = _ns(tree.started_at) or 0

    def emit(node: RagLabStep, parent: Any) -> None:
        name, kind, attrs = _attributes(node, texts)
        start = _ns(node.started_at) or _ns(node.ended_at) or fallback
        context = trace.set_span_in_context(parent) if parent is not None else None
        span = tracer.start_span(
            name, context=context, kind=kind, attributes=attrs, start_time=start
        )
        if node.status in ("error", "cancelled", "too_long"):
            span.set_attribute("error.type", node.status)
            span.set_status(Status(StatusCode.ERROR))
        for child in node.children:
            emit(child, span)
        span.end(end_time=max(start, _ns(node.ended_at) or start))

    emit(tree, None)
    spans = memory.get_finished_spans()
    provider.shutdown()
    return encode_spans(spans).SerializeToString(), len(spans)


def send(body: bytes, endpoint: str, auth_env: str | None = None) -> None:
    """POST the protobuf to the collector through the factory (AD-15: its host must be
    allowed; it is, once `[otel] endpoint` names it). Raises `ExportFailed`."""
    headers = {"Content-Type": "application/x-protobuf"}
    auth = os.environ.get(auth_env, "").strip() if auth_env else ""
    if auth:
        headers["Authorization"] = auth
    try:
        with create_client(timeout=10.0) as client:
            response = client.post(traces_url(endpoint), content=body, headers=headers)
    except NetworkBlocked as blocked:
        raise ExportFailed(Message("rag_lab.otel.blocked", cause=blocked)) from None
    except httpx.HTTPError as exc:
        raise ExportFailed(Message("rag_lab.otel.unreachable", cause=type(exc).__name__)) from None
    if response.status_code >= 300:
        raise ExportFailed(Message("rag_lab.otel.refused", status=response.status_code))
