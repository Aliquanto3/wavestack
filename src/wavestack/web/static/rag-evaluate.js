// V1.2 story 15 (CAP-11), tab « evaluate »: the judges against the reference annotation, the
// aggregates with their n, and the four traps of the judges. The figures are the session's
// (`/api/rag_lab/evaluation`, AD-1): the page sends the finished runs it holds, receives the
// table and the aggregates, and draws them. The one view that averages; the banner « Démonstration,
// pas un banc » is outside every folding section. Registered with the shell (`registerTab`).

import { $, el, quote, registerTab, store } from "./rag.js";

const ev = {
  body: null, // the last answer of `/api/rag_lab/evaluation`
  runs: new Map(), // `question_id/preset` -> the finished run this page holds (lost at reload)
  sent: "", // the runs last sent, so that an unchanged list is not sent again
  trap: null, // the trap shown
  notice: null, // { text, error } of the last judgment asked
  busy: false,
};

const fill = (template, values = {}) => String(template ?? "").replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));

const t = (path, values = {}) => {
  let value = ev.body?.texts;
  for (const key of path.split(".")) value = value?.[key];
  return typeof value === "string" ? fill(value, values) : "";
};

const number = (value) =>
  value === null || value === undefined
    ? "—"
    : new Intl.NumberFormat(document.documentElement.lang || undefined, { maximumFractionDigits: 2 }).format(value);

const verdictText = (verdict) => t(`verdicts.${verdict}`);
const roleText = (role) => t(`roles.${role}`);
const judgeName = (role, cell) => cell?.judge_label || ev.body?.judges?.[role]?.label || roleText(role);

// ----- the finished runs of this page -----

const questionOfRun = (run) => store.questions.find((q) => q.question_text === run.question) ?? null;

function presetOfRun(run) {
  const kinds = new Set(["vector_search", "lexical_search", "fusion"]);
  const segment = run.stages.filter((s) => kinds.has(s.kind));
  const found = (store.catalog?.presets ?? []).find(
    (p) => p.segment.length === segment.length && p.segment.every((s, i) => s.kind === segment[i].kind && s.option === segment[i].option),
  );
  return found?.id ?? "custom";
}

function answerOfRun(run) {
  const stage = run.stages.find((s) => s.kind === "generation");
  return stage?.ended && typeof stage.ended.prompt_text === "string" ? stage.ended.output_text || "" : "";
}

const ORDERED = new Set(["vector_search", "lexical_search", "fusion", "rerank", "context"]);

function collectRun() {
  const run = store.run;
  if (!run?.ended || run.ended.status !== "ok") return;
  const question = questionOfRun(run);
  if (!question) return; // a free question has no expected passage and does not count in n
  const preset = presetOfRun(run);
  ev.runs.set(`${question.id}/${preset}`, {
    run_id: run.runId,
    question_id: question.id,
    preset,
    top_k: run.stages.find((s) => s.kind === "context")?.params?.top_k ?? 3,
    stages: run.stages
      .filter((s) => s.status === "ok" && ORDERED.has(s.kind) && Array.isArray(s.ended?.items))
      .map((s) => ({ kind: s.kind, items: s.ended.items.map((i) => ({ doc_id: i.doc_id, text: i.text })) })),
    answer_text: answerOfRun(run),
  });
}

async function send(path, payload) {
  try {
    const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    let body = {};
    try {
      body = await response.json();
    } catch {
      body = {};
    }
    return { ok: response.ok, status: response.status, body };
  } catch {
    return { ok: false, status: 0, body: {} };
  }
}

async function refresh(force = false) {
  const runs = [...ev.runs.values()];
  const key = JSON.stringify(runs.map((r) => r.run_id));
  if (!force && key === ev.sent) return;
  ev.sent = key;
  ev.asked = (ev.asked ?? 0) + 1;
  const asked = ev.asked;
  const answer = await send("/api/rag_lab/evaluation", { runs });
  // A late answer (an older request) does not overwrite a newer one: it could say `judging` again.
  if (asked !== ev.asked) return answer.ok;
  if (answer.ok) {
    ev.body = { ...answer.body, panel: ev.body?.panel ?? null };
    ev.busy = Boolean(answer.body.judging);
  }
  draw();
  return answer.ok;
}

// ----- drawing -----

function provenanceText() {
  const p = ev.body.provenance;
  const names = { local: ev.body.judges.local.label, cloud: ev.body.judges.cloud.label };
  if (p.kind === "recorded") return t("provenance_recorded_text", { date: p.recorded_on, ...names });
  return t("provenance_constructed_text", names);
}

function annotationText() {
  const a = ev.body.annotation;
  return a.annotated_by === "draft" ? t("annotation_draft_text") : t("annotation_human_text", { by: a.annotated_by, on: a.annotated_on ?? "" });
}

function agreementLine(role, judged, reference) {
  const line = el("li", "rag-eval-judge");
  line.dataset.role = role;
  if (!judged) {
    line.append(el("span", "rag-note", `${roleText(role)} : ${t("agreement.none_text")}`));
    return line;
  }
  line.append(el("span", "rag-eval-who", `${roleText(role)} (${judgeName(role, judged)}) : ${verdictText(judged.verdict)} `));
  const state = judged.agreement;
  let said;
  if (state === "disagree") said = t("agreement.disagree_text", { judge: verdictText(judged.verdict), reference: verdictText(reference) });
  else if (state === "agree") said = t("agreement.agree_text");
  else if (state === "unannotated") said = t("agreement.unannotated_text");
  else said = t("agreement.unreadable_text");
  const mark = el("span", `rag-cmp-mark rag-eval-${state}`, `${state === "disagree" ? "≠ " : state === "agree" ? "= " : ""}${said}`);
  mark.dataset.agreement = state;
  line.append(mark);
  if (judged.why_text) line.append(el("span", "rag-note", ` ${quote(judged.why_text)}`));
  return line;
}

function cellOf(criterion, cell) {
  const td = el("td", "rag-eval-cell");
  td.dataset.criterion = criterion;
  if (!cell.applicable) {
    td.append(el("span", "rag-note", t("not_applicable_text")));
    return td;
  }
  const list = el("ul", "rag-eval-judges");
  list.append(el("li", "rag-eval-ref", `${t("reference_text")} : ${cell.reference ? verdictText(cell.reference) : t("agreement.unannotated_text")}`));
  if (cell.rule) list.append(el("li", "rag-eval-rule", t("rule_text", { value: t(`rule_values.${cell.rule}`) })));
  for (const role of ["local", "cloud"]) list.append(agreementLine(role, cell.judges[role], cell.reference));
  td.append(list);
  return td;
}

function drawTable() {
  const { rows } = ev.body.table;
  const criteria = ev.body.criteria;
  const table = el("table", "rag-eval-table");
  const thead = el("thead");
  const head = el("tr");
  for (const label of [t("question_col_text"), t("architecture_col_text"), "", ...criteria.map((c) => t(`criteria.${c}.label_text`))]) head.append(el("th", "", label));
  thead.append(head);
  table.append(thead);
  const body = el("tbody");
  for (const row of rows) {
    const tr = el("tr");
    tr.dataset.question = row.question_id;
    tr.dataset.preset = row.preset;
    tr.dataset.source = row.source;
    const first = el("td", "rag-eval-q");
    first.append(el("strong", "", row.question_text), el("span", "rag-note", ` ${row.type}`), el("div", "rag-note", quote(row.answer_text)));
    tr.append(first, el("td", "", `${row.preset} · ${t(row.source === "session" ? "session_source_text" : "recorded_source_text")}`));
    const metrics = el("td", "rag-eval-metrics");
    for (const [label, value] of [
      [t("recall_text", { k: row.top_k }), row.recall_at_k],
      [t("mrr_text"), row.reciprocal_rank],
    ]) {
      metrics.append(el("div", "rag-num", `${label} : ${value === null ? t("not_applicable_text") : number(value)}`));
    }
    tr.append(metrics);
    for (const criterion of criteria) tr.append(cellOf(criterion, row.cells[criterion]));
    body.append(tr);
  }
  table.append(body);
  return table;
}

function drawAggregates() {
  const box = el("div", "rag-eval-aggs-list");
  const { aggregates, architectures } = ev.body.table;
  for (const preset of architectures) {
    const section = el("div", "rag-eval-agg");
    section.dataset.preset = preset;
    section.append(el("h4", "rag-cost-title", `${t("architecture_col_text")} ${preset}`));
    const list = el("ul", "rag-eval-agg-lines");
    for (const a of aggregates.filter((x) => x.preset === preset)) {
      const agreementOf = a.who.startsWith("agreement_");
      const measure = a.measure === "recall_at_k" ? t("recall_text", { k: "k" }) : a.measure === "reciprocal_rank" ? t("mrr_text") : t(`criteria.${a.measure}.label_text`);
      const who = a.who === "metric" ? "" : ` · ${t(`aggregates.who.${agreementOf ? a.who.slice(10) : a.who}`)}`;
      const li = el("li", "rag-eval-agg-line");
      li.dataset.measure = a.measure;
      li.dataset.who = a.who;
      const figure = agreementOf ? t("aggregates.agreement_text", { rate: number(a.value) }) : number(a.value);
      li.append(el("span", "rag-num", `${measure}${who} : ${figure} (${t("aggregates.n_text", { n: a.n })}) `));
      if (a.too_few) li.append(el("span", "rag-cmp-mark", t("aggregates.too_few_text")));
      if (a.unreadable) li.append(el("span", "rag-note", ` ${t("aggregates.unreadable_text", { n: a.unreadable })}`));
      list.append(li);
    }
    section.append(list);
    box.append(section);
  }
  if (!architectures.length) box.append(el("p", "rag-note", t("aggregates.none_text")));
  return [el("p", "rag-note", t("aggregates.hint_text")), box];
}

function drawPanel() {
  const panel = ev.body.panel;
  const box = el("div", "rag-eval-panel-body");
  const finops = ev.body.finops;
  if (finops) box.append(el("p", "rag-note", t("panel.spend_text", { spent: `${number(finops.spent_usd)} $`, cap: `${number(finops.max_session_usd)} $` })));
  if (!panel) return box;
  const gen = panel.generator;
  box.append(el("p", "rag-note", gen ? t("panel.generator_text", { model: gen.label, family: gen.family_label }) : t("panel.no_generator_text")));
  const local = el("div", "rag-eval-local");
  local.append(el("h4", "rag-cost-title", t("panel.local_title_text")));
  if (!panel.local.some((o) => !o.reason)) local.append(el("p", "rag-note", t("panel.no_local_text")));
  for (const o of panel.local) local.append(el("p", "rag-note", o.reason ? `${o.label} — ${t("panel.rejected_text", { reason: o.reason })}` : o.label));
  const cloud = el("div", "rag-eval-cloud");
  cloud.append(el("h4", "rag-cost-title", t("panel.cloud_title_text")));
  if (!panel.cloud.length) cloud.append(el("p", "rag-note", t("panel.no_cloud_text")));
  for (const o of panel.cloud) {
    const said = o.reason ? t("panel.rejected_text", { reason: o.reason }) : o.has_key ? "" : t("panel.no_key_text");
    cloud.append(el("p", "rag-note", said ? `${o.label} — ${said}` : o.label));
  }
  box.append(local, cloud);
  return box;
}

// ----- judging one run, one criterion, one judge -----

function judgeChoices() {
  const panel = ev.body.panel;
  if (!panel) return [];
  const suffix = (o) => (o.has_key ? "" : ` (${t("panel.no_key_text")})`);
  return [
    ...panel.local.filter((o) => !o.reason).map((o) => ({ role: "local", id: o.id, label: `${roleText("local")} · ${o.label}` })),
    ...panel.cloud.filter((o) => !o.reason).map((o) => ({ role: "cloud", id: o.id, label: `${roleText("cloud")} · ${o.label}${suffix(o)}` })),
  ];
}

async function judge(run, choice, criterion) {
  ev.notice = null;
  const answer = await send("/api/intentions/rag_lab_judge", { run, role: choice.role, judge: choice.id, criterion });
  if (!answer.ok) {
    const detail = typeof answer.body.detail === "string" ? answer.body.detail : String(answer.status);
    ev.notice = { text: t("live.refused_text", { reason: detail }), error: true };
    draw();
    return;
  }
  ev.busy = true;
  draw();
  // No time limit: a local judge on CPU may take minutes. Only a server that stops answering
  // ends the wait; the button stays disabled anyway while the session is not idle.
  let failures = 0;
  while (ev.busy && failures < 5) {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    failures = (await refresh(true)) ? 0 : failures + 1;
  }
  ev.busy = false;
  if (ev.body?.judge_error) ev.notice = { text: ev.body.judge_error, error: true };
  draw();
}

function drawLive() {
  const box = el("div", "rag-eval-live");
  box.append(el("h4", "rag-cost-title", t("live.title_text")));
  const runs = [...ev.runs.values()];
  if (!runs.length) {
    box.append(el("p", "rag-note", t("live.none_text")));
    return box;
  }
  const choices = judgeChoices();
  for (const run of runs) {
    const question = store.questions.find((q) => q.id === run.question_id);
    const row = el("div", "rag-copy-form");
    row.dataset.run = run.run_id;
    row.append(el("span", "rag-eval-q", `${question?.question_text ?? run.question_id} · ${run.preset}`));
    if (!run.answer_text) {
      row.append(el("span", "rag-note", t("live.no_answer_text")));
      box.append(row);
      continue;
    }
    const criterionSelect = el("select");
    const noAnswer = question?.type === "no_answer";
    for (const c of ev.body.criteria.filter((x) => (x === "correct_refusal") === noAnswer)) {
      const option = el("option", "", t(`criteria.${c}.label_text`));
      option.value = c;
      criterionSelect.append(option);
    }
    criterionSelect.setAttribute("aria-label", t("live.criterion_text"));
    const judgeSelect = el("select");
    judgeSelect.setAttribute("aria-label", t("live.judge_text"));
    choices.forEach((c, i) => {
      const option = el("option", "", c.label);
      option.value = String(i);
      judgeSelect.append(option);
    });
    const button = el("button", "rag-button-secondary", ev.busy ? t("live.busy_text") : t("live.button_text"));
    button.type = "button";
    button.disabled = ev.busy || !choices.length || store.session.state !== "idle";
    button.addEventListener("click", () => judge(run, choices[Number(judgeSelect.value)], criterionSelect.value));
    row.append(criterionSelect, judgeSelect, button);
    box.append(row);
  }
  if (ev.notice) box.append(el("p", ev.notice.error ? "rag-error" : "rag-note", ev.notice.text));
  return box;
}

// ----- the four traps -----

function trapVerdict(label, v) {
  const box = el("div", "rag-eval-trap-verdict");
  box.append(el("strong", "", t("traps.judge_says_text", { judge: label, verdict: verdictText(v.verdict) })), el("p", "rag-note", quote(v.why_text)));
  return box;
}

function drawTrap(trap) {
  const parts = [el("span", "rag-badge", t("traps.badge_text")), el("h4", "rag-cost-title", trap.title_text), el("p", "rag-note", trap.explain_text)];
  if (trap.question_text) parts.push(el("p", "rag-cmp-question", quote(trap.question_text)));
  if (trap.answer_text) parts.push(el("p", "rag-note", `${t("traps.answer_text")} : ${quote(trap.answer_text)}`));
  if (trap.kind === "two_judges") {
    for (const role of ["local", "cloud"]) parts.push(trapVerdict(`${roleText(role)} (${trap.judges[role].label})`, trap.verdicts[role]));
  } else if (trap.kind === "variance") {
    trap.passes.forEach((p, i) => parts.push(trapVerdict(`${t("traps.pass_text", { n: i + 1 })} (${trap.judges.local.label})`, p)));
    parts.push(el("p", "rag-note", t("traps.causes_text", { causes: trap.causes.map((c) => t(`traps.causes.${c}`)).join(", ") })));
  } else if (trap.kind === "two_tools") {
    const list = el("ul", "rag-eval-claims");
    for (const c of trap.claims) list.append(el("li", "", `${c.text} — ${t(`traps.labels.${c.label}`)}`));
    parts.push(el("h5", "rag-cost-title", t("traps.claims_text")), list);
    const ragas = el("p", "rag-num", t("traps.ragas_text", { value: number(trap.ragas) }));
    ragas.dataset.tool = "ragas";
    const deepeval = el("p", "rag-num", t("traps.deepeval_text", { value: number(trap.deepeval) }));
    deepeval.dataset.tool = "deepeval";
    parts.push(ragas, deepeval);
  } else {
    parts.push(el("p", "rag-note", t("traps.ranking_text")));
    for (const role of ["local", "cloud"]) {
      const list = el("ol", "rag-eval-ranking");
      list.dataset.role = role;
      trap.ranking[role].forEach((r, i) => list.append(el("li", "", t("traps.rank_line_text", { rank: i + 1, preset: r.preset, value: number(r.value), n: r.n }))));
      parts.push(el("h5", "rag-cost-title", `${roleText(role)} (${trap.judges[role].label})`), list);
    }
  }
  return parts;
}

async function playTrap(id) {
  ev.trap = id;
  drawTrapButtons();
  let trap = null;
  try {
    const response = await fetch(`/api/rag_lab/evaluation/traps/${encodeURIComponent(id)}`);
    if (response.ok) trap = await response.json();
  } catch {
    trap = null;
  }
  const box = $("rag-eval-trap");
  box.dataset.trap = id;
  box.replaceChildren(...(trap ? drawTrap(trap) : [el("p", "rag-error", t("traps.failed_text"))]));
}

function drawTrapButtons() {
  const group = $("rag-eval-traps");
  const built = ev.body.traps.map((x) => `${x.id}:${x.title_text}`).join("|");
  if (group.dataset.built !== built) {
    group.replaceChildren(
      ...ev.body.traps.map((x) => {
        const button = el("button", "rag-button-secondary", x.title_text);
        button.type = "button";
        button.dataset.trap = x.id;
        button.addEventListener("click", () => playTrap(x.id));
        return button;
      }),
    );
    group.dataset.built = built;
  }
  for (const button of group.children) button.setAttribute("aria-pressed", String(button.dataset.trap === ev.trap));
}

function draw() {
  if (!ev.body?.texts) return;
  const table = ev.body.table;
  $("rag-eval-banner").textContent = t("banner_text", { n: table.n, a: table.architectures.length, j: table.judges_n });
  $("rag-eval-title").textContent = t("title_text");
  $("rag-eval-hint").textContent = t("hint_text");
  $("rag-eval-provenance").textContent = `${provenanceText()} · ${annotationText()}`;
  const translated = ev.body.lang !== ev.body.provenance.source_lang;
  $("rag-eval-translated").textContent = translated ? t("translated_text", { lang: ev.body.provenance.source_lang }) : "";
  $("rag-eval-translated").hidden = !translated;
  $("rag-eval-panel-title").textContent = t("panel.title_text");
  $("rag-eval-panel").replaceChildren(drawPanel(), drawLive());
  $("rag-eval-table").replaceChildren(drawTable());
  $("rag-eval-aggs-title").textContent = t("aggregates.title_text");
  $("rag-eval-aggs").replaceChildren(...drawAggregates());
  $("rag-eval-traps-title").textContent = t("traps.title_text");
  $("rag-eval-traps-hint").textContent = t("traps.hint_text");
  drawTrapButtons();
  $("rag-eval-sheet-title").textContent = t("sheet.title_text");
  $("rag-eval-sheet").textContent = t("sheet.body_text");
}

// ----- the shell's hooks -----

async function load() {
  try {
    const response = await fetch("/api/rag_lab/evaluation");
    if (response.ok) ev.body = await response.json();
  } catch {
    ev.body = null;
  }
  draw();
  await refresh(true);
}

function render() {
  collectRun();
  if (store.tab === "evaluate" && ev.body) refresh();
}

registerTab("evaluate", {
  mount() {
    if (store.tab === "evaluate") load();
  },
  render,
  show() {
    collectRun();
    if (ev.body) refresh(true);
    else load();
  },
});
