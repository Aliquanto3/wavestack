// V1.2 story 11 (CAP-7), searching without vectors: the focus of the agent's rounds
// (`agent_loop`), of PageIndex's descent (`section_tree`), and the « Arbre » card (who wrote the
// tree, the stale nodes, « Reconstruire » and « Rétablir »). Every figure is the session's (AD-1):
// the `agent` and `tree` fields of the Context stage's `rag_lab_stage_ended`, and the `pageindex`
// block of `contexts` in `/api/rag_lab`. Every text is drawn as text (`textContent`).

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

const tree = { error: null };

const contextOption = () => (chain()?.stages ?? []).find((s) => s.kind === "context")?.option ?? null;

// The agent's rounds: the action, its status, the call's tokens, the result cut.
function agentTurns(agent) {
  const box = el("div", "rag-agent");
  box.append(
    el("p", "rag-agent-title", t("rag.agent_title", { rounds: fmtInt(agent.rounds), max: fmtInt(agent.max_rounds) })),
  );
  const list = el("ol", "rag-agent-turns");
  for (const turn of agent.turns ?? []) {
    const item = el("li", "rag-agent-turn");
    item.dataset.status = turn.status;
    const head = el("p", "rag-agent-head");
    const action = turn.action ? `${turn.action === "answer" ? "ANSWER" : turn.action}${turn.argument ? ` ${turn.argument}` : ""}` : "—";
    head.append(
      el("span", "rag-agent-round", t("rag.agent_round", { round: fmtInt(turn.round) })),
      el("code", "rag-agent-action", action),
      el("span", "rag-agent-status", t(`rag.agent_status_${turn.status}`)),
    );
    item.append(head);
    item.append(
      el(
        "p",
        "rag-agent-tokens",
        t("rag.agent_tokens", { prompt: fmtInt(turn.prompt_tokens), output: fmtInt(turn.output_tokens) }),
      ),
    );
    if (turn.result_preview) {
      item.append(
        el("p", "rag-agent-result", t("rag.agent_result", { tokens: fmtInt(turn.result_tokens), text: turn.result_preview })),
      );
    } else if (turn.answer_preview && turn.status !== "answer") {
      item.append(el("p", "rag-agent-result", t("rag.agent_answer", { text: turn.answer_preview })));
    }
    list.append(item);
  }
  box.append(list);
  return box;
}

// PageIndex's descent: per level, the children shown (title, summary), the model's choice.
function treeLevels(info) {
  const box = el("div", "rag-tree");
  box.append(el("p", "rag-tree-title", t("rag.tree_title", { levels: fmtInt(info.levels?.length ?? 0) })));
  if (info.mark_text) box.append(el("p", "rag-tree-mark", info.mark_text));
  for (const level of info.levels ?? []) {
    const part = el("div", "rag-tree-level");
    part.dataset.level = String(level.level);
    part.append(el("p", "rag-tree-level-title", t("rag.tree_level", { level: fmtInt(level.level), count: fmtInt(level.shown.length) })));
    const chosen = new Set(level.chosen ?? []);
    const list = el("ol", "rag-tree-children");
    for (const child of level.shown ?? []) {
      const item = el("li", "rag-tree-child");
      item.classList.toggle("is-chosen", chosen.has(child.node_id));
      item.append(el("span", "rag-tree-child-title", child.title_text));
      if (child.summary_text) item.append(el("span", "rag-tree-child-summary", child.summary_text));
      list.append(item);
    }
    part.append(list);
    const picked = (level.chosen ?? []).join(", ") || t("rag.tree_none");
    part.append(el("p", "rag-tree-chosen", t("rag.tree_chosen", { chosen: picked })));
    box.append(part);
  }
  box.append(el("p", "rag-tree-reached", t("rag.tree_reached", { nodes: (info.chosen ?? []).join(", ") || t("rag.tree_none") })));
  return box;
}

// The « Arbre » card: the tree read now, its stale nodes, « Reconstruire » and « Rétablir ».
function treeCard() {
  const info = store.contexts?.pageindex;
  const box = el("div", "rag-tree-card");
  box.append(el("p", "rag-tree-card-title", t("rag.tree_card_title")));
  if (!info) return box;
  box.append(el("p", "rag-tree-card-summary", info.summary_text));
  if (info.measure_text) box.append(el("p", "rag-note", info.measure_text));
  if (info.stale) box.append(el("p", "rag-stage-warning", t("rag.tree_stale", { count: fmtInt(info.stale) })));
  const buttons = el("p", "rag-contexts-buttons");
  const blocked = Boolean(busyReason()) || store.pending;
  const rebuild = el("button", "rag-button-secondary", t("rag.tree_rebuild"));
  rebuild.type = "button";
  rebuild.id = "rag-tree-rebuild";
  rebuild.disabled = blocked || Boolean(info.rebuild_blocked_text);
  rebuild.title = info.rebuild_blocked_text || "";
  rebuild.addEventListener("click", rebuildTree);
  const reset = el("button", "rag-button-secondary", t("rag.tree_reset"));
  reset.type = "button";
  reset.id = "rag-tree-reset";
  reset.disabled = blocked || !info.rebuilt;
  reset.addEventListener("click", resetTree);
  buttons.append(rebuild, reset);
  box.append(buttons);
  if (info.rebuild_blocked_text) box.append(el("p", "rag-note", info.rebuild_blocked_text));
  const job = store.rebuild;
  if (job && !job.ended && job.total) {
    box.append(el("p", "rag-contexts-progress", t("rag.tree_progress", { done: fmtInt(job.done), total: fmtInt(job.total) })));
  } else if (job?.error) {
    box.append(el("p", "rag-stage-error", job.error));
  } else if (job?.output) {
    box.append(el("p", "rag-contexts-done", job.output));
  }
  if (tree.error) box.append(el("p", "rag-stage-error", tree.error));
  return box;
}

async function rebuildTree() {
  tree.error = null;
  store.pending = true;
  renderBusy();
  const answer = await post("/api/intentions/rag_lab_rebuild", { pipelines: store.pipelines, target: "pageindex" });
  store.pending = false;
  if (!answer.ok) tree.error = refusalText(answer);
  renderBusy();
  renderCurrent();
}

async function resetTree() {
  tree.error = null;
  const answer = await post("/api/rag_lab/pageindex/reset", {});
  if (answer.ok) {
    store.contexts = answer.body.contexts;
    store.rebuild = null;
  } else {
    tree.error = refusalText(answer);
  }
  renderCurrent();
}

registerFocus((box, step, stage) => {
  if (step.stage !== "context") return;
  const ended = stage?.ended;
  if (ended?.agent && step.key !== "tree_build") box.append(agentTurns(ended.agent));
  if (ended?.tree && step.key !== "tree_build") box.append(treeLevels(ended.tree));
  if (contextOption() === "section_tree" && ["tree_build", "tree_levels", "context"].includes(step.key)) {
    box.append(treeCard());
  }
});
