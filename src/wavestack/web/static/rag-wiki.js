// V1.2 story 14 (CAP-7), the LLM Wiki: the focus of the index read by the model (`wiki_pages`),
// the lint's findings, and the « Wiki » card (who wrote the wiki, its pages and links, the stale
// pages, the estimate of a compilation by a model, « Reconstruire » and « Rétablir »). Every
// figure is the session's (AD-1): the `wiki` field of the Context stage's `rag_lab_stage_ended`,
// and the `wiki` block of `contexts` in `/api/rag_lab`. Every text is drawn as text.

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

const state = { error: null };

const contextOption = () => (chain()?.stages ?? []).find((s) => s.kind === "context")?.option ?? null;

// The lint's findings, one sentence each.
function lintList(info) {
  const box = el("div", "rag-wiki-lint");
  box.append(el("p", "rag-tree-level-title", t("rag.wiki_lint_title", { findings: fmtInt(info.findings ?? 0) })));
  const list = el("ul", "rag-wiki-findings");
  for (const finding of info.lint ?? []) {
    const item = el("li", "rag-wiki-finding", finding.text);
    item.dataset.code = finding.code;
    list.append(item);
  }
  if ((info.lint ?? []).length) box.append(list);
  return box;
}

// The index shown to the model (title, synthesis cut, audience), the pages it picked.
function wikiIndex(info) {
  const box = el("div", "rag-tree rag-wiki");
  box.append(el("p", "rag-tree-title", t("rag.wiki_title", { pages: fmtInt(info.shown?.length ?? 0) })));
  if (info.mark_text) box.append(el("p", "rag-tree-mark", info.mark_text));
  const chosen = new Set(info.chosen ?? []);
  const list = el("ol", "rag-tree-children rag-wiki-index");
  for (const page of info.shown ?? []) {
    const item = el("li", "rag-tree-child");
    item.dataset.page = page.page_id;
    item.classList.toggle("is-chosen", chosen.has(page.page_id));
    item.append(el("span", "rag-tree-child-title", page.title_text));
    if (page.audience === "hr") item.append(el("span", "rag-wiki-audience", t("rag.wiki_hr")));
    if (page.summary_text) item.append(el("span", "rag-tree-child-summary", page.summary_text));
    list.append(item);
  }
  box.append(list);
  box.append(el("p", "rag-tree-chosen", t("rag.wiki_chosen", { pages: (info.chosen ?? []).join(", ") || t("rag.tree_none") })));
  if (info.answer_preview) box.append(el("p", "rag-agent-tokens", t("rag.agent_answer", { text: info.answer_preview })));
  return box;
}

// The « Wiki » card: the wiki read now, its stale pages, its lint, « Reconstruire », « Rétablir ».
function wikiCard() {
  const info = store.contexts?.wiki;
  const box = el("div", "rag-tree-card rag-wiki-card");
  box.append(el("p", "rag-tree-card-title", t("rag.wiki_card_title")));
  if (!info) return box;
  box.append(el("p", "rag-tree-card-summary rag-wiki-card-summary", info.summary_text));
  if (info.measure_text) box.append(el("p", "rag-note", info.measure_text));
  if (info.estimate_text) box.append(el("p", "rag-note rag-wiki-estimate", info.estimate_text));
  if (info.stale) box.append(el("p", "rag-stage-warning", t("rag.wiki_stale", { count: fmtInt(info.stale) })));
  if (info.hr_pages) box.append(el("p", "rag-note", t("rag.wiki_hr_pages", { count: fmtInt(info.hr_pages) })));
  box.append(lintList(info));
  const buttons = el("p", "rag-contexts-buttons");
  const blocked = Boolean(busyReason()) || store.pending;
  const rebuild = el("button", "rag-button-secondary", t("rag.wiki_rebuild"));
  rebuild.type = "button";
  rebuild.id = "rag-wiki-rebuild";
  rebuild.disabled = blocked || Boolean(info.rebuild_blocked_text);
  rebuild.title = info.rebuild_blocked_text || "";
  rebuild.addEventListener("click", rebuildWiki);
  const reset = el("button", "rag-button-secondary", t("rag.wiki_reset"));
  reset.type = "button";
  reset.id = "rag-wiki-reset";
  reset.disabled = blocked || !info.rebuilt;
  reset.addEventListener("click", resetWiki);
  buttons.append(rebuild, reset);
  box.append(buttons);
  if (info.rebuild_blocked_text) box.append(el("p", "rag-note", info.rebuild_blocked_text));
  const job = store.rebuild;
  if (job && !job.ended && job.total) {
    box.append(el("p", "rag-contexts-progress", t("rag.wiki_progress", { done: fmtInt(job.done), total: fmtInt(job.total) })));
  } else if (job?.error) {
    box.append(el("p", "rag-stage-error", job.error));
  } else if (job?.output) {
    box.append(el("p", "rag-contexts-done", job.output));
  }
  if (info.error_text) box.append(el("p", "rag-stage-error", info.error_text));
  if (state.error) box.append(el("p", "rag-stage-error", state.error));
  return box;
}

async function rebuildWiki() {
  state.error = null;
  store.pending = true;
  renderBusy();
  const answer = await post("/api/intentions/rag_lab_rebuild", { pipelines: store.pipelines, target: "wiki" });
  store.pending = false;
  if (!answer.ok) state.error = refusalText(answer);
  renderBusy();
  renderCurrent();
}

async function resetWiki() {
  state.error = null;
  const answer = await post("/api/rag_lab/wiki/reset", {});
  if (answer.ok) {
    store.contexts = answer.body.contexts;
    store.rebuild = null;
  } else {
    state.error = refusalText(answer);
  }
  renderCurrent();
}

registerFocus((box, step, stage) => {
  if (step.stage !== "context") return;
  const ended = stage?.ended;
  if (ended?.wiki && step.key === "wiki_lookup" && ended.wiki.shown?.length) box.append(wikiIndex(ended.wiki));
  if (ended?.wiki && step.key === "wiki_lint") box.append(lintList(ended.wiki));
  if (contextOption() === "wiki_pages" && ["wiki_build", "wiki_lint", "wiki_lookup", "context"].includes(step.key)) {
    box.append(wikiCard());
  }
});
