// V1.2 story 17 (CAP-13), tab « attack »: the « Document piégé » card. The figures are the session's
// (`/api/rag_lab/attack`, AD-1): the page sends its own state (the trap's activation, the scenario,
// the guardrail and its mode, the graph's step) with every request, receives the two columns of the
// target question and draws them. The state lives here and is lost at reload: the session keeps
// nothing. Every text of a document is drawn as text (`textContent`), never as HTML. The card of
// the story 18 (Effacement, Droits) has its place below, still « à venir ».

import { $, el, registerTab, store } from "./rag.js";

const at = {
  body: null, // the last answer of `GET /api/rag_lab/attack` (texts, scenarios, defaults)
  result: null, // the last answer of `POST /api/rag_lab/attack`
  trap: false, // the trapped document in the corpus in memory
  scenario: "injection",
  guard: false,
  mode: "block", // « Bloquer » by default
  step: "start", // the graph's step
  asked: 0,
  loaded: false,
};

const fill = (template, values = {}) => String(template ?? "").replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));

const t = (path, values = {}) => {
  let value = at.body?.texts;
  for (const key of path.split(".")) value = value?.[key];
  return typeof value === "string" ? fill(value, values) : "";
};

const number = (value) =>
  value === null || value === undefined
    ? "—"
    : new Intl.NumberFormat(document.documentElement.lang || undefined, { maximumFractionDigits: 2 }).format(value);

const rankText = (rank) => (rank === null || rank === undefined ? t("rank_absent_text") : String(rank));

async function load() {
  try {
    const response = await fetch("/api/rag_lab/attack");
    if (response.ok) at.body = await response.json();
  } catch {
    at.body = null;
  }
  at.loaded = true;
  drawControls();
  await run();
}

async function run() {
  if (!at.body) return;
  at.asked += 1;
  const asked = at.asked;
  const payload = { scenario: at.scenario, trap_active: at.trap, guardrails: at.guard, mode: at.mode, graph_step: at.step };
  let answer = null;
  try {
    const response = await fetch("/api/rag_lab/attack", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    answer = response.ok ? await response.json() : null;
  } catch {
    answer = null;
  }
  // A late answer (an older request) does not overwrite a newer one.
  if (asked !== at.asked) return;
  at.result = answer;
  drawResult();
}

// ----- the controls -----

function drawControls() {
  if (!at.body) return;
  const scenario = at.body.scenarios.find((s) => s.id === at.scenario);
  const isGraph = at.scenario === "graph";
  $("rag-atk-banner").textContent = t("banner_text");
  $("rag-atk-title").textContent = t("title_text");
  $("rag-atk-hint").textContent = t("hint_text");
  $("rag-atk-trap-label").textContent = t("trap_label_text", { title: at.body.doc.title_text });
  $("rag-atk-trap").checked = at.trap;
  $("rag-atk-trap-state").textContent = at.trap ? t("trap_active_text") : t("trap_inactive_text");
  $("rag-atk-scope").textContent = t("trap_scope_text");
  $("rag-atk-scenario-title").textContent = t("scenario_label_text");
  drawScenarioButtons();
  $("rag-atk-explain").textContent = scenario?.explain_text ?? "";
  $("rag-atk-provenance").textContent = scenario?.provenance.text ?? "";
  $("rag-atk-guard-box").hidden = isGraph;
  $("rag-atk-guard-label").textContent = t("guardrails_label_text");
  $("rag-atk-guard").checked = at.guard;
  $("rag-atk-mode-label").textContent = t("mode_label_text");
  $("rag-atk-mode-block-text").textContent = t("mode_block_text");
  $("rag-atk-mode-flag-text").textContent = t("mode_flag_text");
  $("rag-atk-mode-block").checked = at.mode === "block";
  $("rag-atk-mode-flag").checked = at.mode === "flag";
  $("rag-atk-modes").disabled = !at.guard;
  drawGuardState();
  $("rag-atk-question").textContent = `${t("question_label_text")} : ${at.body.question.text}`;
  $("rag-atk-question").hidden = isGraph;
  $("rag-atk-run").textContent = t("relaunch_text");
  $("rag-atk-run").hidden = isGraph;
  $("rag-atk-limits-title").textContent = t("limits_title_text");
  $("rag-atk-limits").replaceChildren(...(at.body.texts.limits ?? []).map((line) => el("li", "", line)));
  $("rag-atk-soon").textContent = t("story18_text");
}

function drawGuardState() {
  const guard = at.result?.guard ?? at.body.guard;
  $("rag-atk-guard-state").textContent = guard.loaded ? t("guard_loaded_text") : `${t("guard_missing_text")} ${guard.reason_text ?? ""}`;
  $("rag-atk-guard-link").textContent = t("guard_link_text");
  $("rag-atk-guard-link").hidden = guard.loaded;
}

function drawScenarioButtons() {
  const group = $("rag-atk-scenarios");
  if (group.dataset.built !== "1") {
    group.replaceChildren(
      ...at.body.scenarios.map((s) => {
        const button = el("button", "rag-button-secondary", s.title_text);
        button.type = "button";
        button.dataset.scenario = s.id;
        button.addEventListener("click", () => chooseScenario(s.id));
        return button;
      }),
    );
    group.dataset.built = "1";
  }
  for (const button of group.children) button.setAttribute("aria-pressed", String(button.dataset.scenario === at.scenario));
}

function chooseScenario(id) {
  at.scenario = id;
  at.step = "start";
  at.result = null;
  drawControls();
  drawResult();
  run();
}

// ----- the result -----

function passageNode(p) {
  const box = el("li", "rag-atk-passage");
  box.dataset.role = p.role;
  box.dataset.outcome = p.outcome ?? "kept";
  box.dataset.docId = p.doc_id;
  box.append(el("strong", "", t("passage_text", { rank: p.rank, title: p.title_text, position: p.position, score: number(p.score) })));
  box.append(" ", el("span", "rag-badge", t(`roles.${p.role}`)));
  const trap = p.role === "injection" || p.role === "false_claim";
  if (trap) box.append(el("p", "rag-note", t("payload_title_text")));
  box.append(el("p", "rag-atk-text", p.text)); // text only: the trapped text is never HTML
  if (trap) box.append(el("p", "rag-note", t("payload_note_text")));
  if (p.check) {
    const line = el("p", "rag-atk-verdict", `${p.verdict_text} — ${p.outcome_text}`);
    line.dataset.decision = p.check.decision;
    box.append(line);
    if (p.check.recorded) {
      const recorded = el("p", "rag-note", `${p.check.recorded.text} (${p.check.recorded.provenance.text})`);
      recorded.dataset.recorded = "1";
      box.append(recorded);
    }
  }
  return box;
}

function column(kind, data, result) {
  const box = el("div", "rag-atk-column");
  box.dataset.column = kind;
  box.append(el("h4", "rag-cost-title", t(`${kind}_title_text`)));
  box.append(el("p", "rag-note", t("passages_title_text")));
  const list = el("ul", "rag-atk-list");
  list.append(...data.passages.map((p) => passageNode(p)));
  box.append(list);
  const answer = el("div", "rag-atk-answer");
  answer.dataset.kind = data.answer.kind;
  answer.append(el("strong", "", t("answer_title_text")), el("p", "rag-atk-text", data.answer.text));
  box.append(answer);
  if (!result.trap_active) box.append(el("p", "rag-note", t("answer_clean_note_text")));
  box.append(el("p", "rag-note", result.provenance.text));
  if (data.limit_text) {
    const limit = el("p", "rag-atk-limit", data.limit_text);
    limit.dataset.limit = "poisoning";
    box.append(limit);
  }
  return box;
}

function poisoningHelps() {
  const box = el("div");
  box.id = "rag-atk-poison-helps";
  box.append(el("h4", "rag-cost-title", t("poisoning.helps_title_text")));
  const list = el("ul", "rag-atk-list");
  list.append(...(at.body.texts.poisoning.helps ?? []).map((line) => el("li", "", line)));
  box.append(list);
  return box;
}

function drawResult() {
  const result = at.result;
  const isGraph = at.scenario === "graph";
  $("rag-atk-passages-box").hidden = isGraph || !result;
  $("rag-atk-graph-box").hidden = !isGraph || !result;
  document.getElementById("rag-atk-poison-helps")?.remove();
  if (!result || !at.body) return;
  drawGuardState();
  const c = result.corpus;
  const corpus = [t("corpus_text", { docs: c.documents, chunks: c.passages, size: c.max_chars, k: c.k })];
  if (c.trap_passages) corpus.push(t("trap_corpus_text", { count: c.trap_passages }));
  $("rag-atk-corpus").textContent = corpus.join(" ");
  if (isGraph) {
    drawGraph(result.graph);
    return;
  }
  const r = result.role_ranks;
  $("rag-atk-ranks").textContent = result.trap_active
    ? t("ranks_text", { false_claim: rankText(r.false_claim), legit: rankText(r.legit), injection: rankText(r.injection) })
    : "";
  const columns = [column("without", result.without, result)];
  if (result.with) {
    columns.push(column("with", result.with, result));
  } else {
    const off = el("div", "rag-atk-column");
    off.dataset.column = "with";
    off.append(el("h4", "rag-cost-title", t("with_title_text")), el("p", "rag-note", t("with_off_text")));
    columns.push(off);
  }
  const area = $("rag-atk-columns");
  area.replaceChildren(...columns);
  $("rag-atk-journal").textContent = result.with ? t("journal_text") : "";
  if (result.with && at.scenario === "poisoning") area.after(poisoningHelps());
}

// ----- the graph -----

function drawGraph(graph) {
  const texts = at.body.texts.graph;
  $("rag-atk-graph-note").textContent = texts.illustrative_text;
  $("rag-atk-graph-steps-title").textContent = texts.steps_title_text;
  const group = $("rag-atk-graph-steps");
  if (group.dataset.built !== "1") {
    group.replaceChildren(
      ...at.body.graph_steps.map((step) => {
        const button = el("button", "rag-button-secondary", texts.steps[step]);
        button.type = "button";
        button.dataset.step = step;
        button.addEventListener("click", () => chooseStep(step));
        return button;
      }),
    );
    group.dataset.built = "1";
  }
  for (const button of group.children) button.setAttribute("aria-pressed", String(button.dataset.step === graph.step));
  $("rag-atk-graph-state").textContent = graph.state_text;
  const message = $("rag-atk-graph-message");
  message.textContent = graph.message_text ?? "";
  message.hidden = !graph.message_text;
  $("rag-atk-graph-rel-title").textContent = texts.relations_title_text;
  $("rag-atk-graph-relations").replaceChildren(
    ...graph.relations.map((r) => {
      const item = el("li", "", r.label_text);
      item.dataset.relation = r.id;
      if (r.is_false) item.append(" ", el("span", "rag-atk-false", texts.false_mark_text));
      return item;
    }),
  );
  $("rag-atk-graph-sum-title").textContent = texts.summary_title_text;
  const summary = $("rag-atk-graph-summary");
  summary.textContent = graph.summary_text;
  summary.dataset.poisoned = String(graph.false_relation_present);
  summary.dataset.stale = String(graph.stale);
  if (graph.stale) summary.append(" ", el("span", "rag-atk-false", texts.stale_text));
}

function chooseStep(step) {
  at.step = step;
  if (step === "inject") at.trap = true;
  if (step === "remove") at.trap = false;
  drawControls();
  run();
}

// ----- the events and the shell's hooks -----

function wire() {
  $("rag-atk-trap").addEventListener("change", (event) => {
    at.trap = event.target.checked;
    // Unticking after the injection is the removal: the graph keeps what it learnt.
    if (at.scenario === "graph") at.step = !at.trap && at.step === "inject" ? "remove" : "start";
    drawControls();
    run();
  });
  $("rag-atk-guard").addEventListener("change", (event) => {
    at.guard = event.target.checked;
    drawControls();
    run();
  });
  for (const id of ["rag-atk-mode-block", "rag-atk-mode-flag"]) {
    $(id).addEventListener("change", (event) => {
      if (!event.target.checked) return;
      at.mode = event.target.value;
      run();
    });
  }
  $("rag-atk-run").addEventListener("click", () => run());
}

let wired = false;

function ensure() {
  if (wired) return;
  wire();
  wired = true;
}

registerTab("attack", {
  mount() {
    ensure();
    if (store.tab === "attack") load();
  },
  show() {
    ensure();
    if (at.loaded) {
      drawControls();
      run();
    } else {
      load();
    }
  },
});
