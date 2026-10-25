// V1.2 story 16 (CAP-12): the last run as a tree of steps (step, sub-step, model call), with
// durations and tokens, and its OTLP export. The tree is the session's (`steps` of
// `rag_lab_run_ended`, built from the journal by `trace/tree.py`, AD-1); the page draws it.
// The export button shows only when the `otel` extra is installed and `[otel] endpoint` set
// (`GET /api/rag_lab/otel`); nothing leaves otherwise.

import { $, el, fmtInt, post, registerTab, store, text } from "./rag.js";

const otel = { state: null, busy: false, result: null, resultRun: null };

const STATUS = {
  error: "status.error_text",
  skipped: "status.skipped_text",
  cancelled: "status.cancelled_text",
  not_run: "status.not_run_text",
  running: "status.running_text",
  length: "tree.length_text",
};

function figures(node) {
  const parts = [];
  if (typeof node.duration_ms === "number") parts.push(`${fmtInt(node.duration_ms)} ms`);
  if (typeof node.input_tokens === "number" || typeof node.output_tokens === "number") {
    parts.push(text("tree.tokens_text", { input: fmtInt(node.input_tokens), output: fmtInt(node.output_tokens) }));
  } else if (typeof node.tokens === "number") {
    parts.push(text("tree.tokens_count_text", { count: fmtInt(node.tokens) }));
  }
  if (STATUS[node.status]) parts.push(text(STATUS[node.status]));
  return parts;
}

function branch(node) {
  const li = el("li", `rag-tree-node is-${node.kind}`);
  li.dataset.step = node.id;
  li.dataset.kind = node.kind;
  li.dataset.status = node.status;
  const line = el("span", "rag-tree-line");
  line.append(el("span", "rag-tree-name", node.name));
  if (node.kind === "model_call" && node.model && node.model !== node.name) line.append(el("code", "rag-tree-model", node.model));
  for (const figure of figures(node)) line.append(el("span", "rag-tree-figure", figure));
  li.append(line);
  if (node.children?.length) {
    const ul = el("ul");
    ul.append(...node.children.map(branch));
    li.append(ul);
  }
  return li;
}

function renderTree() {
  const box = $("rag-tree-body");
  if (!box || !store.content) return;
  const steps = store.run?.ended?.steps;
  if (!steps) {
    box.replaceChildren(el("p", "rag-note rag-tree-empty", text("tree.empty_text")));
  } else {
    const ul = el("ul", "rag-tree-root");
    ul.append(branch(steps));
    box.replaceChildren(ul);
  }
  renderExport();
}

function renderExport() {
  const note = $("rag-otel-note");
  const button = $("rag-otel-export");
  const result = $("rag-otel-result");
  if (!note || !button || !store.content) return;
  const state = otel.state;
  if (otel.resultRun !== (store.run?.runId ?? null)) otel.result = null; // another run: its own export
  let message = "";
  if (state && !state.available) message = text("tree.otel_missing_text");
  else if (state && !state.ready) message = text("tree.otel_unset_text");
  else if (state) message = text(state.capture_content ? "tree.otel_content_text" : "tree.otel_ready_text", { endpoint: state.endpoint });
  note.textContent = message;
  button.hidden = !state?.ready;
  button.disabled = otel.busy || !store.run?.ended?.steps;
  result.textContent = otel.busy ? text("tree.export_running_text") : (otel.result ?? "");
}

async function exportRun() {
  const runId = store.run?.ended?.run_id;
  if (!runId || otel.busy) return;
  otel.busy = true;
  otel.result = null;
  otel.resultRun = store.run?.runId ?? null;
  renderExport();
  const answer = await post("/api/rag_lab/otel/export", { run_id: runId });
  otel.busy = false;
  otel.result = answer.ok
    ? text("tree.export_done_text", { count: fmtInt(answer.body.spans), endpoint: answer.body.endpoint })
    : text("tree.export_failed_text", { reason: answer.body.detail ?? String(answer.status) });
  renderExport();
}

async function mount() {
  $("rag-otel-export")?.addEventListener("click", exportRun);
  try {
    const response = await fetch("/api/rag_lab/otel");
    if (response.ok) otel.state = await response.json();
  } catch {
    otel.state = null;
  }
  renderTree();
}

registerTab("tree", { mount, render: renderTree });
