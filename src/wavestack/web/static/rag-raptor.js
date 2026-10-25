// V1.2 story 12 (CAP-7), RAPTOR and Corrective RAG: the focus of RAPTOR's search (the nodes of
// every level kept, with their level, documents and audience), the « Arbre RAPTOR » card (who
// wrote the tree, its numbers, the stale summaries, the labelled estimate, an accessible table of
// the summaries, « Reconstruire » and « Rétablir »), and the focus of Corrective RAG's fallback
// (its verdict, the question rewritten, « je ne sais pas »). Every figure is the session's (AD-1):
// the `raptor` and `fallback` fields of `rag_lab_stage_ended`, the `raptor` block of `contexts` in
// `/api/rag_lab`. Every text is drawn as text (`textContent`); the graph card's styles serve.

import { t } from "./i18n.js";
import {
  busyReason,
  chain,
  el,
  fmtInt,
  post,
  refusalText,
  registerFocus,
  renderBusy,
  renderCurrent,
  store,
} from "./rag.js";

const raptor = { error: null };

const contextOption = () => (chain()?.stages ?? []).find((s) => s.kind === "context")?.option ?? null;
const audienceText = (audience) => t(audience === "hr" ? "rag.graph_audience_hr" : "rag.graph_audience_all");

function audienceBadge(audience) {
  const badge = el("span", "rag-graph-audience", audienceText(audience));
  badge.dataset.audience = audience;
  return badge;
}

const levelText = (level) => (level ? t("rag.raptor_level", { level: fmtInt(level) }) : t("rag.raptor_passage"));

// The search: the nodes kept, a passage (level 0) or a summary, the best first.
function raptorQuery(info) {
  const box = el("div", "rag-graph rag-raptor");
  box.append(el("p", "rag-graph-title", t("rag.raptor_title", { count: fmtInt((info.picked ?? []).length) })));
  if (info.mark_text) box.append(el("p", "rag-graph-mark", info.mark_text));
  const list = el("ol", "rag-graph-passages");
  for (const p of info.picked ?? []) {
    const item = el("li", "rag-graph-passage");
    item.dataset.level = String(p.level);
    const head = el("p", "rag-graph-passage-head");
    head.append(el("code", "rag-graph-passage-id", p.node_id), el("span", "rag-note", levelText(p.level)), audienceBadge(p.audience));
    item.append(head);
    item.append(el("p", "rag-note", t("rag.graph_sources", { sources: (p.sources ?? []).join(", ") })));
    item.append(el("p", "rag-graph-preview", p.preview));
    list.append(item);
  }
  if (!(info.picked ?? []).length) list.append(el("li", "rag-note", t("rag.graph_none")));
  box.append(list);
  return box;
}

function table(caption, headers, rows) {
  const wrap = el("div", "rag-graph-table-wrap");
  const tbl = el("table", "rag-graph-table");
  tbl.append(el("caption", "", caption));
  const head = el("tr", "");
  for (const h of headers) {
    const th = el("th", "", h);
    th.scope = "col";
    head.append(th);
  }
  const thead = el("thead", "");
  thead.append(head);
  const body = el("tbody", "");
  for (const cells of rows) {
    const tr = el("tr", "");
    for (const cell of cells) tr.append(el("td", "", String(cell ?? "")));
    body.append(tr);
  }
  tbl.append(thead, body);
  wrap.append(tbl);
  return wrap;
}

// The « Arbre RAPTOR » card: the tree read now, its estimate or its measure, its summaries.
function raptorCard() {
  const info = store.contexts?.raptor;
  const box = el("div", "rag-graph-card");
  box.id = "rag-raptor-card";
  box.append(el("p", "rag-graph-card-title", t("rag.raptor_card_title")));
  if (!info) return box;
  box.append(el("p", "rag-graph-card-summary", info.summary_text));
  if (info.rule_note_text) box.append(el("p", "rag-note rag-graph-rule", info.rule_note_text));
  if (info.estimate) {
    const estimate = el("p", "rag-note rag-graph-estimate");
    estimate.append(el("span", "rag-graph-estimate-badge", t("rag.graph_estimate_badge")), document.createTextNode(` ${info.estimate.text}`));
    box.append(estimate);
  }
  if (info.measure_text) box.append(el("p", "rag-note rag-graph-measure", info.measure_text));
  if (info.stale) box.append(el("p", "rag-stage-warning", t("rag.raptor_stale", { count: fmtInt(info.stale) })));
  if (info.error_text) box.append(el("p", "rag-stage-error", info.error_text));
  const buttons = el("p", "rag-contexts-buttons");
  const blocked = Boolean(busyReason()) || store.pending;
  const rebuild = el("button", "rag-button-secondary", t("rag.raptor_rebuild"));
  rebuild.type = "button";
  rebuild.id = "rag-raptor-rebuild";
  rebuild.disabled = blocked || Boolean(info.rebuild_blocked_text);
  rebuild.title = info.rebuild_blocked_text || "";
  rebuild.addEventListener("click", rebuildTree);
  const reset = el("button", "rag-button-secondary", t("rag.raptor_reset"));
  reset.type = "button";
  reset.id = "rag-raptor-reset";
  reset.disabled = blocked || !info.rebuilt;
  reset.addEventListener("click", resetTree);
  buttons.append(rebuild, reset);
  box.append(buttons);
  if (info.rebuild_blocked_text) box.append(el("p", "rag-note", info.rebuild_blocked_text));
  const job = store.rebuild;
  if (job && !job.ended && job.total) {
    box.append(el("p", "rag-contexts-progress", t("rag.graph_progress", { done: fmtInt(job.done), total: fmtInt(job.total) })));
  } else if (job?.error) {
    box.append(el("p", "rag-stage-error", job.error));
  } else if (job?.output) {
    box.append(el("p", "rag-contexts-done", job.output));
  }
  if (raptor.error) box.append(el("p", "rag-stage-error", raptor.error));
  box.append(
    table(
      t("rag.raptor_caption", { total: fmtInt(info.summaries), passages: fmtInt(info.passages), alone: fmtInt(info.unparented) }),
      [t("rag.raptor_col_node"), t("rag.raptor_col_level"), t("rag.raptor_col_children"), t("rag.graph_col_sources"), t("rag.graph_col_audience"), t("rag.graph_col_summary")],
      (info.node_rows ?? []).map((n) => [n.id, fmtInt(n.level), fmtInt(n.children), n.sources.join(", "), audienceText(n.audience), n.summary_text]),
    ),
  );
  return box;
}

async function rebuildTree() {
  raptor.error = null;
  store.pending = true;
  renderBusy();
  const answer = await post("/api/intentions/rag_lab_rebuild", { pipelines: store.pipelines, target: "raptor" });
  store.pending = false;
  if (!answer.ok) raptor.error = refusalText(answer);
  renderBusy();
  renderCurrent();
}

async function resetTree() {
  raptor.error = null;
  const answer = await post("/api/rag_lab/raptor/reset", {});
  if (answer.ok) {
    store.contexts = answer.body.contexts;
    store.rebuild = null;
  } else {
    raptor.error = refusalText(answer);
  }
  renderCurrent();
}

// Corrective RAG's fallback: its verdict, the question rewritten, the answer « je ne sais pas ».
function fallbackFocus(info) {
  const box = el("div", "rag-graph rag-fallback");
  box.dataset.verdict = info.verdict;
  box.append(el("p", "rag-graph-title", t(`rag.fallback_${info.verdict}`, { before: fmtInt(info.kept_before), after: fmtInt(info.kept_after ?? 0) })));
  if (info.rewritten) box.append(el("p", "rag-note", t("rag.fallback_rewritten", { query: info.rewritten })));
  if (info.abstained) box.append(el("p", "rag-stage-warning", t("rag.fallback_abstained")));
  box.append(el("p", "rag-note", t("rag.fallback_no_web")));
  return box;
}

registerFocus((box, step, stage) => {
  const ended = stage?.ended;
  if (step.stage === "fallback" && ended?.fallback) box.append(fallbackFocus(ended.fallback));
  if (step.stage !== "context") return;
  if (ended?.raptor && step.key !== "raptor_build") box.append(raptorQuery(ended.raptor));
  if (contextOption() === "raptor_search" && ["raptor_build", "raptor_query", "context"].includes(step.key)) {
    box.append(raptorCard());
  }
});
