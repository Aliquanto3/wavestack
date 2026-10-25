// V1.2 story 8 (CAP-6), System One's decision layer: the focus of the router, of the passage
// filter and of the grounding check lists each decision with its author (classifier or judge),
// its probability and the threshold. Every figure is the session's (AD-1): the `decisions` field
// of the stage's `rag_lab_stage_ended`. Every text is drawn as text (`textContent`).

import { t } from "./i18n.js";
import { el, labelled, registerFocus } from "./rag.js";

const KINDS = ["router", "passage_filter", "grounding_check"];

function decisionRow(decision) {
  const item = el("li", "rag-decision");
  item.dataset.author = decision.author;
  item.dataset.verdict = decision.verdict;
  item.dataset.below = String(Boolean(decision.below));
  const head = el("p", "rag-decision-head");
  head.append(
    el("span", "rag-decision-subject", decision.subject_text),
    el("span", "rag-badge rag-decision-verdict", decision.verdict_text),
  );
  const figures = el("p", "rag-decision-figures");
  figures.append(
    el("span", "rag-decision-author", labelled(t("rag.decision_author"), decision.author_text)),
    el("span", "rag-decision-probability", labelled(t("rag.decision_probability"), decision.probability_text)),
    el("span", "rag-decision-threshold", labelled(t("rag.decision_threshold"), decision.threshold_text)),
  );
  if (decision.below) figures.append(el("span", "rag-badge rag-decision-below", t("rag.decision_below")));
  if (decision.truncated) figures.append(el("span", "rag-decision-cut", t("rag.decision_truncated")));
  item.append(head, figures);
  if (decision.judge_text) item.append(el("p", "rag-decision-judge", t("rag.decision_judge", { text: decision.judge_text })));
  if (decision.note_text) item.append(el("p", "rag-decision-note", decision.note_text));
  return item;
}

function decisionsBlock(decisions) {
  const box = el("div", "rag-decisions");
  box.append(el("p", "rag-decisions-title", t("rag.decision_title")));
  const list = el("ul", "rag-decisions-list");
  for (const decision of decisions) list.append(decisionRow(decision));
  box.append(list);
  return box;
}

registerFocus((box, step, stage) => {
  if (!KINDS.includes(step.stage)) return;
  const decisions = stage?.ended?.decisions;
  if (decisions?.length) box.append(decisionsBlock(decisions));
});
