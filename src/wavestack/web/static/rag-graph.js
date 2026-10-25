// V1.2 story 13 (CAP-7), GraphRAG: the mode of the query (local or global), the focus of the
// graph's query (the entities recognized, their neighbours and the evidence; or the communities
// ranked and their « map »), and the « Graphe » card (who built the graph, its numbers, the stale
// evidence, the labelled estimate, an accessible table of entities and communities with their
// audience, « Reconstruire » and « Rétablir »). Every figure is the session's (AD-1): the `graph`
// field of the Context stage's `rag_lab_stage_ended`, and the `graph` block of `contexts` in
// `/api/rag_lab`. Every text is drawn as text (`textContent`). No drawing of the graph (Reports).

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

const graph = { error: null };
const MODES = ["local", "global"];

const contextOption = () => (chain()?.stages ?? []).find((s) => s.kind === "context")?.option ?? null;
const audienceText = (audience) => t(audience === "hr" ? "rag.graph_audience_hr" : "rag.graph_audience_all");

function audienceBadge(audience) {
  const badge = el("span", "rag-graph-audience", audienceText(audience));
  badge.dataset.audience = audience;
  return badge;
}

// The mode of the next query: a choice of the page, sent with « Lancer » (`graph_mode`).
function modePicker() {
  const box = el("fieldset", "rag-graph-mode");
  box.id = "rag-graph-mode";
  box.append(el("legend", "", t("rag.graph_mode_label")));
  for (const mode of MODES) {
    const label = el("label", "rag-graph-mode-option");
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "rag-graph-mode";
    input.value = mode;
    input.checked = (store.graphMode || "local") === mode;
    input.addEventListener("change", () => {
      store.graphMode = mode;
    });
    label.append(input, document.createTextNode(` ${t(`rag.graph_mode_${mode}`)}`));
    box.append(label);
  }
  return box;
}

function entityList(className, title, rows) {
  const part = el("div", className);
  part.append(el("p", "rag-graph-subtitle", title));
  const list = el("ul", "rag-graph-entities");
  for (const row of rows) {
    const item = el("li", "rag-graph-entity");
    item.append(el("span", "rag-graph-entity-name", row.name), audienceBadge(row.audience));
    list.append(item);
  }
  if (!rows.length) list.append(el("li", "rag-note", t("rag.graph_none")));
  part.append(list);
  return part;
}

// The query: local (entities, neighbours, evidence) or global (communities, their « map »).
function graphQuery(info) {
  const box = el("div", "rag-graph");
  box.dataset.mode = info.mode;
  box.append(el("p", "rag-graph-title", t(`rag.graph_title_${info.mode === "global" ? "global" : "local"}`, { calls: fmtInt(info.calls) })));
  if (info.mark_text) box.append(el("p", "rag-graph-mark", info.mark_text));
  if (info.mode === "global") {
    const list = el("ol", "rag-graph-communities");
    for (const row of info.ranked ?? []) {
      const item = el("li", "rag-graph-community");
      item.classList.toggle("is-kept", Boolean(row.kept));
      const head = el("p", "rag-graph-community-head");
      head.append(
        el("span", "rag-graph-community-id", t("rag.graph_community", { id: row.community_id, size: fmtInt(row.size) })),
        audienceBadge(row.audience),
      );
      item.append(head);
      item.append(el("p", "rag-note", t("rag.graph_sources", { sources: (row.sources ?? []).join(", ") })));
      item.append(el("p", "rag-note", t("rag.graph_score", { score: fmtInt(row.score) })));
      if (row.answer_preview) item.append(el("p", "rag-graph-answer", t("rag.graph_map_answer", { text: row.answer_preview })));
      list.append(item);
    }
    if (!(info.ranked ?? []).length) list.append(el("li", "rag-note", t("rag.graph_none")));
    box.append(list);
    return box;
  }
  if ((info.asked ?? []).length) box.append(el("p", "rag-note", t("rag.graph_asked", { names: info.asked.join(", ") })));
  box.append(entityList("rag-graph-matched", t("rag.graph_matched"), info.matched ?? []));
  box.append(entityList("rag-graph-neighbours", t("rag.graph_neighbours"), info.neighbours ?? []));
  const evidence = el("ol", "rag-graph-passages");
  for (const p of info.passages ?? []) {
    const item = el("li", "rag-graph-passage");
    const head = el("p", "rag-graph-passage-head");
    head.append(el("code", "rag-graph-passage-id", p.passage_id), audienceBadge(p.audience));
    item.append(head);
    if (p.relation_text) item.append(el("p", "rag-note", t("rag.graph_backs", { relations: p.relation_text })));
    item.append(el("p", "rag-graph-preview", p.preview));
    evidence.append(item);
  }
  box.append(el("p", "rag-graph-subtitle", t("rag.graph_evidence")), evidence);
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
    for (const cell of cells) {
      const td = el("td", "");
      if (cell instanceof Node) td.append(cell);
      else td.textContent = String(cell ?? "");
      tr.append(td);
    }
    body.append(tr);
  }
  tbl.append(thead, body);
  wrap.append(tbl);
  return wrap;
}

// The « Graphe » card: the graph read now, its estimate or its measure, the tables, the buttons.
function graphCard() {
  const info = store.contexts?.graph;
  const box = el("div", "rag-graph-card");
  box.id = "rag-graph-card";
  box.append(el("p", "rag-graph-card-title", t("rag.graph_card_title")));
  if (!info) return box;
  box.append(el("p", "rag-graph-card-summary", info.summary_text));
  if (info.rule_note_text) box.append(el("p", "rag-note rag-graph-rule", info.rule_note_text));
  if (info.estimate) {
    const estimate = el("p", "rag-note rag-graph-estimate");
    estimate.append(el("span", "rag-graph-estimate-badge", t("rag.graph_estimate_badge")), document.createTextNode(` ${info.estimate.text}`));
    box.append(estimate);
  }
  if (info.measure_text) box.append(el("p", "rag-note rag-graph-measure", info.measure_text));
  if (info.stale) box.append(el("p", "rag-stage-warning", t("rag.graph_stale", { count: fmtInt(info.stale) })));
  if (info.error_text) box.append(el("p", "rag-stage-error", info.error_text));
  box.append(modePicker());
  const buttons = el("p", "rag-contexts-buttons");
  const blocked = Boolean(busyReason()) || store.pending;
  const rebuild = el("button", "rag-button-secondary", t("rag.graph_rebuild"));
  rebuild.type = "button";
  rebuild.id = "rag-graph-rebuild";
  rebuild.disabled = blocked || Boolean(info.rebuild_blocked_text);
  rebuild.title = info.rebuild_blocked_text || "";
  rebuild.addEventListener("click", rebuildGraph);
  const reset = el("button", "rag-button-secondary", t("rag.graph_reset"));
  reset.type = "button";
  reset.id = "rag-graph-reset";
  reset.disabled = blocked || !info.rebuilt;
  reset.addEventListener("click", resetGraph);
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
  if (graph.error) box.append(el("p", "rag-stage-error", graph.error));
  box.append(
    table(
      t("rag.graph_entities_caption", { shown: fmtInt(info.entity_rows.length), total: fmtInt(info.entities) }),
      [t("rag.graph_col_entity"), t("rag.graph_col_type"), t("rag.graph_col_mentions"), t("rag.graph_col_degree"), t("rag.graph_col_community"), t("rag.graph_col_audience")],
      info.entity_rows.map((e) => [e.name, e.type ?? "—", fmtInt(e.mentions), fmtInt(e.degree), e.community ?? "—", audienceText(e.audience)]),
    ),
  );
  box.append(
    table(
      t("rag.graph_communities_caption", { total: fmtInt(info.communities), isolated: fmtInt(info.isolated) }),
      [t("rag.graph_col_community"), t("rag.graph_col_size"), t("rag.graph_col_entities"), t("rag.graph_col_sources"), t("rag.graph_col_audience"), t("rag.graph_col_summary")],
      info.community_rows.map((c) => [c.id, fmtInt(c.size), c.entities.join(", "), c.sources.join(", "), audienceText(c.audience), c.summary_text]),
    ),
  );
  return box;
}

async function rebuildGraph() {
  graph.error = null;
  store.pending = true;
  renderBusy();
  const answer = await post("/api/intentions/rag_lab_rebuild", { pipelines: store.pipelines, target: "graph" });
  store.pending = false;
  if (!answer.ok) graph.error = refusalText(answer);
  renderBusy();
  renderCurrent();
}

async function resetGraph() {
  graph.error = null;
  const answer = await post("/api/rag_lab/graph/reset", {});
  if (answer.ok) {
    store.contexts = answer.body.contexts;
    store.rebuild = null;
  } else {
    graph.error = refusalText(answer);
  }
  renderCurrent();
}

registerFocus((box, step, stage) => {
  if (step.stage !== "context") return;
  const ended = stage?.ended;
  if (ended?.graph && step.key !== "graph_build") box.append(graphQuery(ended.graph));
  if (contextOption() === "graph_search" && ["graph_build", "graph_query", "context"].includes(step.key)) {
    box.append(graphCard());
  }
});
