// V1.2 story 9 (CAP-10): the rank of the expected passage at each stage of a finished run, the
// stage at fault, and the three recorded failure cases (« Où naît l'erreur »), replayed without
// the model. Every figure and every verdict is the session's (`/api/rag_lab/diagnosis`, AD-1);
// the page draws them. One question, one run: no mean here (the means are the Evaluate tab's).
// Registered with the shell (`registerTab`); its section sits under the Build tab's views.

import { $, el, fmtInt, quote, registerTab, store } from "./rag.js";

const diag = { texts: null, cases: [] };
const done = new Map(); // run id -> the diagnosis of that run (a journal event must not ask again)
let shownCase = null;

const t = (path, values = {}) => {
  let value = diag.texts;
  for (const key of path.split(".")) value = value?.[key];
  if (typeof value !== "string") return "";
  return value.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));
};

// A setting of the chain the run ran (`rag_lab_run_started` carries its stages' params), not
// of the chain as edited since; the chain under edit, then the shipped value, as a fallback.
function paramOf(kind, name, fallback) {
  const ran = store.run?.stages.find((s) => s.kind === kind);
  const edited = store.pipelines[0]?.stages.find((s) => s.kind === kind);
  return ran?.params?.[name] ?? edited?.params?.[name] ?? fallback;
}

const RANKED = new Set(["vector_search", "lexical_search", "fusion", "rerank", "context"]);

// ----- drawing one diagnosis (the same for a run and for a recorded case) -----

function stepLine(step, fault) {
  const li = el("li", fault?.kind === step.kind ? "is-fault" : "");
  li.dataset.stage = step.kind;
  li.append(el("span", "rag-doc-title", t(`stages.${step.kind}_text`)));
  let state;
  if (step.kind === "chunking") state = step.intact ? t("whole_text") : t("cut_chunk_text");
  else state = step.rank ? t("rank_text", { rank: fmtInt(step.rank), of: fmtInt(step.of) }) : t("absent_text");
  const figure = el("span", "rag-num", state);
  figure.dataset.rank = step.rank ?? "";
  li.append(figure);
  if (fault?.kind === step.kind) li.append(el("span", "rag-cmp-mark", t(`reasons.${fault.reason}_text`)));
  return li;
}

function drawPassage(passage) {
  const box = el("div", "rag-diag-passage");
  box.dataset.doc = passage.doc_id;
  box.append(el("h4", "rag-cost-title", t("passage_text", { doc: passage.doc_id })));
  box.append(el("p", "rag-note", quote(passage.anchor_text)));
  const list = el("ol", "rag-diag-steps");
  for (const step of passage.steps) list.append(stepLine(step, passage.fault));
  box.append(list);
  const verdict = el("p", "rag-diag-verdict");
  verdict.dataset.fault = passage.fault ? `${passage.fault.kind}:${passage.fault.reason}` : "";
  verdict.textContent = passage.fault ? t("fault_text", { stage: t(`stages.${passage.fault.kind}_text`) }) : t("no_fault_text");
  box.append(verdict);
  if (passage.rescued_by) box.append(el("p", "rag-note", t("rescued_text", { stage: t(`stages.${passage.rescued_by}_text`) })));
  if (passage.note === "middle") box.append(el("p", "rag-note", t("middle_text")));
  return box;
}

function drawResult(result) {
  const parts = result.passages.map(drawPassage);
  if (parts.length) parts.push(el("p", "rag-note", t("budget_text", { budget: fmtInt(result.budget), tolerance: fmtInt(result.tolerance) })));
  return parts;
}

// ----- the diagnosis of the current run -----

const questionOfRun = () => store.questions.find((q) => q.question_text === store.run?.question) ?? null;
const finishedWell = () => Boolean(store.run?.ended && store.run.ended.status === "ok");

// An empty list is sent too: a search that found nothing is where the passage was lost.
function runLists() {
  return store.run.stages
    .filter((s) => s.status === "ok" && RANKED.has(s.kind) && Array.isArray(s.ended?.items))
    .map((s) => ({ kind: s.kind, items: s.ended.items.map((i) => ({ doc_id: i.doc_id, text: i.text, placed: i.placed ?? null })) }));
}

async function askRun(question) {
  const runId = store.run.runId;
  done.set(runId, "pending");
  try {
    const response = await fetch("/api/rag_lab/diagnosis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question_id: question.id,
        chunk_max_chars: paramOf("chunking", "chunk_max_chars", 700),
        top_k: paramOf("context", "top_k", 3),
        stages: runLists(),
      }),
    });
    done.set(runId, response.ok ? await response.json() : "failed");
  } catch {
    done.set(runId, "failed");
  }
  renderRun();
}

function renderRun() {
  const box = $("rag-diag-run");
  if (!box || !diag.texts) return;
  let parts;
  if (!finishedWell()) {
    const typed = $("rag-question").value.trim();
    const prepared = store.questions.some((q) => q.question_text === typed);
    parts = [el("p", "rag-note", t(prepared ? "wait_text" : "free_question_text"))];
  } else if (!questionOfRun()) {
    parts = [el("p", "rag-note", t("free_question_text"))];
  } else {
    const got = done.get(store.run.runId);
    if (got === undefined) askRun(questionOfRun());
    if (got === undefined || got === "pending") return;
    if (got === "failed") parts = [el("p", "rag-error", t("run_unavailable_text"))];
    else parts = got.passages.length ? drawResult(got) : [el("p", "rag-note", t("no_expected_text"))];
  }
  box.replaceChildren(...parts);
}

// ----- « Où naît l'erreur »: the recorded cases -----

function renderCases() {
  if (!diag.texts) return;
  const group = $("rag-cases");
  const built = diag.cases.map((c) => `${c.id}:${c.title_text}`).join("|");
  if (group.dataset.built !== built) {
    group.replaceChildren(
      ...diag.cases.map((c) => {
        const button = el("button", "rag-button-secondary", c.title_text);
        button.type = "button";
        button.dataset.case = c.id;
        button.addEventListener("click", () => playCase(c.id));
        return button;
      }),
    );
    group.dataset.built = built;
  }
  for (const button of group.children) button.setAttribute("aria-pressed", String(button.dataset.case === shownCase));
}

async function playCase(id) {
  shownCase = id;
  renderCases();
  const box = $("rag-case");
  let result = null;
  try {
    const response = await fetch(`/api/rag_lab/diagnosis/cases/${encodeURIComponent(id)}`);
    if (response.ok) result = await response.json();
  } catch {
    result = null;
  }
  const meta = diag.cases.find((c) => c.id === id);
  if (!result || !meta) {
    box.replaceChildren(el("p", "rag-error", t("replay_failed_text")));
    return;
  }
  box.dataset.case = id;
  box.replaceChildren(
    el("span", "rag-badge", t("replay_badge_text")),
    el("h4", "rag-cost-title", meta.title_text),
    el("p", "rag-cmp-question", quote(meta.question_text)),
    el("p", "rag-note", meta.explain_text),
    ...drawResult(result),
  );
}

// ----- the shell's hooks -----

async function mount() {
  try {
    const response = await fetch("/api/rag_lab/diagnosis");
    if (!response.ok) return;
    const body = await response.json();
    diag.texts = body.texts;
    diag.cases = body.cases;
  } catch {
    return;
  }
  $("rag-diag-title").textContent = t("title_text");
  $("rag-diag-hint").textContent = t("hint_text");
  $("rag-cases-title").textContent = t("cases_title_text");
  $("rag-cases-hint").textContent = t("cases_hint_text");
  renderCases();
  renderRun();
}

registerTab("diagnosis", { mount, render: renderRun });
