// V1.5 CAP-4 (story 4): the « Évaluer l'agent » view. It lists the cases (the provided suite and
// the session's), launches a run (the suite, one try each, or one case, 1 or 3 tries), follows it
// by polling `GET /api/agent_eval/state` (once a second, view open and a run going, one request at
// a time), shows each case's result, its trace, the session's runs and the comparison of two.
// The badges, verdicts, traces and comparisons are the server's; this module only shows them.
//
// Contract with `app.js`: the ES exports below, no global, never an import of `app.js` (a
// cycle). With the story 3: `registerOpenView` and `onCaseSaved` of `agent-case-form.js`.
// Decision 8: the panel covers Contexte LLM and Orchestration by CSS (`data-agent-eval` on
// `.right`), without panes.js. It loads its own stylesheets, so `index.html` loads none.

import { onCaseSaved, registerOpenView } from "./agent-case-form.js";
import { dateTimeFormat, t } from "./i18n.js";

const API = "/api/agent_eval";
const POLL_MS = 1000;
const FRESH_MS = 1000;
const STYLESHEETS = ["/static/agent-case-form.css", "/static/agent-eval.css"];
const STATUS_CLASS = { passed: "passed", failed: "failed", not_run: "not-run", running: "running", pending: "pending" };
const DOT_CLASS = { passed: "ok", failed: "ko", not_run: "skip" };

const ta = (key, vars) => t(`main.agent_eval.${key}`, vars);

const view = {
  open: false,
  panel: null,
  stale: true, // a reload is due at the next opening
  loading: false,
  cases: null, // CasesListing, the last one shown
  state: null, // EvalState
  runs: new Map(), // run_id → Run, the finished ones never change
  noAnswer: false,
  refusal: "",
  warned: false, // the first-run warning, once per page
  pendingLaunch: null, // {caseId, k} waiting for the warning's « Lancer »
  confirmClear: false,
  stopClicked: null, // the run_id « Arrêter » was clicked for
  trials: new Map(), // caseId → 1 | 3, the choice beside « Lancer »
  traces: new Map(), // `${runId}|${caseId}` → {trial, data, loading, gone}
  pick: { a: null, b: null, manual: false },
  comparison: null, // {key, data, sameRun}
  highlight: null,
  polling: false,
  again: false,
  timer: null,
  progressKey: null,
  session: null, // the last live `session_state` payload
  polledAt: 0,
  signature: null, // the last state shown: an identical poll renders nothing (an open menu stays)
  starting: null, // a POST /runs on its way (true), then its run_id until `GET /state` lists it
  alerted: new Set(), // the alerts of the last render: a kept one is not announced again
  badgeTriedAt: 0,
};

let ids = 0;

registerOpenView((caseId) => openView(caseId));
onCaseSaved(() => refreshCases());
stylesReady();
document.getElementById("agent-eval-toggle")?.addEventListener("click", () => (view.open ? closeView() : openView()));

// ---------- the module's interface ----------

/** Opens the view; `caseId`: scrolls to that case and highlights it. */
export function openView(caseId) {
  view.highlight = caseId ?? null;
  if (!view.open) {
    view.open = true;
    const panel = ensurePanel();
    const human = document.querySelector('.top-row > .pane[data-pane="human"]');
    if (human) human.after(panel);
    else document.querySelector(".top-row")?.appendChild(panel);
    document.querySelector(".right")?.setAttribute("data-agent-eval", "open");
    toggle()?.setAttribute("aria-pressed", "true");
  }
  render();
  view.panel.querySelector("h3")?.focus();
  if (view.stale || !view.cases) refresh();
  else poll();
}

export function closeView() {
  if (!view.open) return;
  const hadFocus = view.panel.contains(document.activeElement);
  view.open = false;
  clearTimeout(view.timer);
  view.timer = null;
  view.panel.remove();
  document.querySelector(".right")?.removeAttribute("data-agent-eval");
  toggle()?.setAttribute("aria-pressed", "false");
  if (hadFocus) toggle()?.focus();
}

/** Called by `app.js` at each live `session_state`. */
export function sessionStateChanged(state) {
  const before = sessionKey();
  view.session = state ?? null;
  if (!view.open) {
    view.stale = true;
    return;
  }
  if (sessionKey() !== before) view.signature = null; // the buttons' state changes: render
  poll();
}

const sessionKey = () => `${view.session?.state ?? ""}|${view.session?.reason_text ?? ""}`;

/** « Cas : titre » before a case run's turn, or null; the title from `GET /cases`' cache. */
export function caseBadge(caseId) {
  if (!caseId) return null;
  const badge = el("span", "ae-badge", ta("badge", { title: titleOf(caseId) }));
  badge.dataset.caseId = caseId;
  // Review: at most one try every few seconds, the chat being rendered at each event.
  if (!view.cases && !view.loading && Date.now() - view.badgeTriedAt > 5000) {
    view.badgeTriedAt = Date.now();
    refreshCases();
  }
  return badge;
}

// ---------- loading ----------

async function refresh() {
  view.stale = false;
  view.signature = null;
  view.loading = true;
  render();
  const [listing, state] = await Promise.all([getJson(`${API}/cases`), getJson(`${API}/state`)]);
  view.loading = false;
  if (listing.ok) view.cases = listing.body;
  if (state.ok) await applyState(state.body);
  view.noAnswer = !listing.ok || !state.ok;
  updateBadges();
  render();
  if (view.open && running()) schedule();
}

async function refreshCases() {
  if (!view.open) view.stale = true;
  view.loading = true;
  const listing = await getJson(`${API}/cases`);
  view.loading = false;
  if (listing.ok) view.cases = listing.body;
  else if (view.open) view.noAnswer = true;
  updateBadges();
  if (view.open) render();
}

/** One `GET /state`, then the next a second after the answer while a run goes on. */
async function poll() {
  if (!view.open) return;
  if (view.polling) {
    view.again = true;
    return;
  }
  clearTimeout(view.timer);
  view.timer = null;
  view.polling = true;
  view.polledAt = Date.now();
  const state = await getJson(`${API}/state`);
  const fetched = state.ok ? await applyState(state.body) : 0;
  view.noAnswer = !state.ok;
  view.polling = false;
  if (!view.open) return;
  // Review: an unchanged state renders nothing (an open « 1 ou 3 essais » menu, a click stay).
  const signature = `${view.noAnswer}|${Boolean(view.starting)}|${JSON.stringify(state.body)}`;
  if (fetched || signature !== view.signature) render();
  view.signature = signature;
  if (view.again) {
    view.again = false;
    poll();
  } else if (running()) {
    schedule();
  }
}

function schedule() {
  clearTimeout(view.timer);
  view.timer = setTimeout(poll, POLL_MS);
}

/** The new state; the runs not known yet, or changed, are read (the current one only when its
 * case or try changed, decision 14). */
async function applyState(state) {
  const previous = view.state;
  view.state = state;
  const current = state.current;
  const key = current ? `${current.run_id}|${current.index}|${current.trial}` : null;
  const moved = key !== view.progressKey;
  view.progressKey = key;
  if (!running()) view.stopClicked = null;
  const listed = new Set(state.runs.map((r) => r.run_id));
  if (typeof view.starting === "string" && listed.has(view.starting)) view.starting = null;
  for (const id of [...view.runs.keys()]) if (!listed.has(id)) view.runs.delete(id);
  const wanted = state.runs.filter((summary) => {
    const known = view.runs.get(summary.run_id);
    if (!known || known.status !== summary.status) return true;
    return summary.status === "running" && moved;
  });
  const answers = await Promise.all(wanted.map((s) => getJson(`${API}/runs/${encodeURIComponent(s.run_id)}`)));
  answers.forEach((answer, i) => {
    if (answer.ok) view.runs.set(wanted[i].run_id, answer.body);
    else if (answer.status !== 404) view.noAnswer = true;
  });
  if (previous && previous.runs.length !== state.runs.length && !view.pick.manual) view.comparison = null;
  updateBadges();
  return wanted.length;
}

/** Launching waits for an idle session: a turn that ignored « Arrêter » may outlive its run. */
function blocked() {
  const state = view.session?.state;
  return Boolean(view.starting) || running() || Boolean(state && state !== "idle");
}

function blockedReason() {
  if (running()) return ta("busy");
  return view.session?.reason_text || ta("busy");
}

function running() {
  const state = view.state;
  return Boolean(state && (state.current || state.runs.some((r) => r.status === "running")));
}

function runningId() {
  const state = view.state;
  return state?.current?.run_id ?? state?.runs.find((r) => r.status === "running")?.run_id ?? null;
}

// ---------- actions ----------

function launch(caseId, k) {
  if (blocked()) return;
  if (!view.warned && (view.state?.runs.length ?? 0) === 0) {
    view.warned = true;
    view.pendingLaunch = { caseId, k };
    render();
    view.panel.querySelector('[data-focus-key="first-run-go"]')?.focus();
    return;
  }
  start(caseId, k);
}

async function start(caseId, k) {
  if (blocked()) return; // review: a double click, or the warning's « Lancer » meanwhile
  view.pendingLaunch = null;
  view.refusal = "";
  view.starting = true;
  render();
  const answer = await sendJson("POST", `${API}/runs`, { case_id: caseId, k });
  // Until `GET /state` lists the run, the buttons stay disabled (a second POST would get a 409).
  view.starting = answer.ok && typeof answer.body?.run_id === "string" ? answer.body.run_id : null;
  if (answer.ok) {
    view.noAnswer = false;
    view.highlight = null;
  } else if (typeof answer.body?.detail === "string") {
    view.refusal = answer.body.detail;
  } else {
    view.noAnswer = true;
  }
  if (view.open) {
    render();
    poll();
  }
}

async function stopRun() {
  view.stopClicked = runningId();
  render();
  view.panel.querySelector(".ae-progress")?.focus();
  const answer = await sendJson("POST", "/api/intentions/stop", {});
  if (!answer.ok) view.noAnswer = true;
  poll();
}

async function deleteCase(caseId) {
  view.refusal = "";
  const answer = await sendJson("DELETE", `${API}/cases/${encodeURIComponent(caseId)}`);
  if (!answer.ok) {
    if (typeof answer.body?.detail === "string") view.refusal = answer.body.detail;
    else view.noAnswer = true;
  }
  await refreshCases();
}

async function clearCases() {
  view.confirmClear = false;
  view.refusal = "";
  const answer = await sendJson("DELETE", `${API}/cases`);
  if (!answer.ok) {
    if (typeof answer.body?.detail === "string") view.refusal = answer.body.detail;
    else view.noAnswer = true;
  }
  await refreshCases();
  view.panel.querySelector('[data-focus-key="clear"]')?.focus();
}

async function toggleTrace(run, result) {
  const key = `${run.run_id}|${result.case_id}`;
  if (view.traces.has(key)) {
    view.traces.delete(key);
    render();
    return;
  }
  const failed = result.trials.find((trial) => trial.status === "failed" && trial.has_trace);
  const first = failed ?? result.trials.find((trial) => trial.has_trace) ?? result.trials[0];
  await loadTrace(run, result, first?.trial ?? 1);
}

async function loadTrace(run, result, trial) {
  const key = `${run.run_id}|${result.case_id}`;
  const entry = { trial, data: null, loading: true, gone: false };
  view.traces.set(key, entry);
  render();
  const query = new URLSearchParams({ case_id: result.case_id, trial: String(trial) });
  const answer = await getJson(`${API}/runs/${encodeURIComponent(run.run_id)}/trace?${query}`);
  if (view.traces.get(key) !== entry) return; // folded or another try asked meanwhile
  entry.loading = false;
  if (answer.ok) entry.data = answer.body;
  else if (answer.status === 404) entry.gone = true;
  else view.noAnswer = true;
  render();
}

async function compare() {
  const { a, b } = view.pick;
  const key = `${a}|${b}`;
  if (a === b) {
    view.comparison = { key, data: null, sameRun: true };
    render();
    return;
  }
  const answer = await getJson(`${API}/compare?${new URLSearchParams({ a, b })}`);
  if (answer.ok) view.comparison = { key, data: answer.body, sameRun: false };
  else if (answer.status === 422) view.comparison = { key, data: null, sameRun: true };
  else view.noAnswer = true;
  render();
}

// ---------- rendering ----------

function ensurePanel() {
  if (view.panel) return view.panel;
  const panel = el("section", "ae-panel");
  panel.id = "agent-eval-panel";
  panel.setAttribute("aria-labelledby", "agent-eval-title");
  panel.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.stopPropagation();
    if (view.pendingLaunch || view.confirmClear) {
      view.pendingLaunch = null;
      view.confirmClear = false;
      render();
      return;
    }
    closeView();
  });
  // The header (model, system prompt) changes outside any run: read again when the formatter
  // comes back to the view, at most every few seconds.
  const fresh = () => {
    if (!running() && Date.now() - view.polledAt > FRESH_MS) poll();
  };
  panel.addEventListener("pointerenter", fresh);
  panel.addEventListener("focusin", fresh);
  view.panel = panel;
  toggle()?.setAttribute("aria-controls", panel.id);
  return panel;
}

function render() {
  if (!view.open || !view.panel) return;
  const panel = view.panel;
  const focusKey = panel.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
  rendering.alerts = new Set();
  const title = el("h3", "", ta("title"));
  title.id = "agent-eval-title";
  title.tabIndex = -1;
  const nodes = [title, header(), el("p", "ae-banner", ta("banner"))];
  if (view.noAnswer) nodes.push(alertLine(ta("error.no_answer")));
  if (!view.cases) {
    if (view.loading) nodes.push(el("p", "ae-reason", ta("loading")));
  } else {
    if (running()) nodes.push(progress());
    nodes.push(...caseGroups());
    if (view.pendingLaunch) nodes.push(firstRunBox());
    if (view.confirmClear) nodes.push(clearBox());
    nodes.push(mainActions());
    if (view.refusal) nodes.push(alertLine(view.refusal));
    nodes.push(...runsSection());
  }
  const keep = focusKey === "agent-eval-title" ? null : focusKey;
  const hadFocus = panel.contains(document.activeElement);
  view.alerted = rendering.alerts;
  rendering.alerts = null;
  panel.replaceChildren(...nodes);
  const kept = keep ? panel.querySelector(`[data-focus-key="${CSS.escape(keep)}"]`) : null;
  if (kept) kept.focus();
  // Review: the focused control gone (the progress bar at the run's end), the title takes it.
  else if (hadFocus) title.focus();
  if (view.highlight) {
    const item = panel.querySelector(`.ae-case[data-case-id="${CSS.escape(view.highlight)}"]`);
    if (item && !item.dataset.scrolled) item.scrollIntoView({ block: "nearest" });
  }
}

function header() {
  const head = el("div", "ae-head");
  const state = view.state;
  const model = state?.header.model?.label ?? ta("head.no_model");
  head.appendChild(el("span", "", ta("head.model", { model })));
  if (state) {
    const prompt = state.header.system_prompt;
    const which = ta(prompt.is_default ? "head.prompt_default" : "head.prompt_custom");
    head.appendChild(el("span", "", ta("head.prompt", { start: prompt.start_text, state: which })));
  }
  return head;
}

function progress() {
  const box = el("div", "ae-progress");
  box.setAttribute("role", "status");
  box.tabIndex = -1;
  box.dataset.focusKey = "progress"; // « Arrêter » gives it the focus: kept by the next polls
  const current = view.state.current;
  if (!current) {
    // Review: before the first try (or between two cases), « Arrêter » stays offered.
    box.appendChild(el("span", "", ta("busy")));
    const id = runningId();
    if (id && view.stopClicked === id) box.appendChild(el("span", "", ta("stop_requested")));
    else if (id) box.appendChild(button("ae-button ae-danger", ta("stop"), "stop", stopRun));
    return box;
  }
  const scope = view.state.runs.find((r) => r.run_id === current.run_id)?.scope ?? "suite";
  const [done, total, text] =
    scope === "suite"
      ? [current.index - 1, current.total, ta("progress.suite", { index: String(current.index), total: String(current.total) })]
      : [current.trial - 1, current.k, ta("progress.trials", { trial: String(current.trial), k: String(current.k) })];
  box.appendChild(el("span", "", text));
  const bar = el("span", "bar");
  bar.setAttribute("aria-hidden", "true");
  const fill = el("span");
  fill.style.width = `${Math.round((100 * done) / Math.max(total, 1))}%`;
  bar.appendChild(fill);
  box.appendChild(bar);
  if (current.stop_requested || view.stopClicked === current.run_id) {
    box.appendChild(el("span", "", ta("stop_requested")));
  } else {
    const stop = button("ae-button ae-danger", ta("stop"), "stop", stopRun);
    box.appendChild(stop);
  }
  return box;
}

function caseGroups() {
  const listing = view.cases;
  const nodes = [el("p", "ae-group", ta("group.provided")), caseList(listing.provided, false)];
  nodes.push(el("p", "ae-group", ta("group.mine")));
  if (listing.session_error === "unreadable") nodes.push(el("p", "ae-banner", ta("mine.unreadable")));
  else if (!listing.session.length) nodes.push(el("p", "ae-reason", ta("mine.empty")));
  else nodes.push(caseList(listing.session, true));
  return nodes;
}

function caseList(cases, mine) {
  const list = el("ul", "ae-cases");
  for (const summary of cases) list.appendChild(caseItem(summary, mine));
  return list;
}

function caseItem(summary, mine) {
  const item = el("li", "ae-case");
  item.dataset.caseId = summary.id;
  if (view.highlight === summary.id) item.classList.add("is-highlighted");
  const found = resultOf(summary.id);
  const result = found?.result;
  if (result) {
    const status = el("span", `ae-status ${STATUS_CLASS[result.status] ?? ""}`, ta(`status.${result.status}`));
    item.appendChild(status);
  } else {
    item.appendChild(el("span"));
  }
  const body = el("div");
  body.appendChild(el("strong", "", summary.title_text));
  const meta = mine
    ? ta("case.meta_session", { turn: turnLabel(summary.origin_turn_id), max: String(summary.max_model_calls) })
    : ta("case.meta", { brick: summary.brick_label_text ?? summary.brick ?? "—", max: String(summary.max_model_calls) });
  body.append(" ", el("span", "meta", meta));
  if (result) body.append(...resultLines(found.run, result));
  item.appendChild(body);
  item.appendChild(caseActions(summary, mine, found));
  return item;
}

function resultLines(run, result) {
  const lines = [];
  if (result.status === "failed") {
    const trial = result.trials.find((x) => x.status === "failed" && x.failing);
    if (trial) lines.push(el("p", "ae-reason", ta("failing", { check: checkLabel(trial.failing.kind), reason: trial.failing.reason_text })));
  } else if (result.status === "not_run") {
    const first = result.trials.find((x) => x.status === "not_run");
    const reason = result.reason_text ?? first?.reason_text;
    const why = result.not_run_reason ?? first?.not_run_reason;
    if (reason) {
      const text = sentence(reason);
      lines.push(el("p", "ae-reason", why === "window" ? `${text} ${ta("case.window_hint")}` : text));
    }
  }
  if (result.ignored_ids?.length) lines.push(el("p", "ae-reason", ta("case.ignored", { ids: result.ignored_ids.join(", ") })));
  if (result.k === 3 && result.trials.length) lines.push(trialsLine(result));
  const entry = view.traces.get(`${run.run_id}|${result.case_id}`);
  if (entry) lines.push(...traceBlock(run, result, entry));
  return lines;
}

function trialsLine(result) {
  const line = el("p", "ae-reason");
  line.append(`${ta("trials.prefix", { k: String(result.k) })} `);
  const dots = el("span", "ae-dots");
  const statuses = [];
  for (let n = 1; n <= result.k; n += 1) {
    const trial = result.trials.find((x) => x.trial === n);
    const status = trial?.status ?? "pending";
    dots.appendChild(el("i", DOT_CLASS[status] ?? "skip"));
    statuses.push(ta(`status.${status}`));
  }
  dots.setAttribute("role", "img");
  dots.setAttribute("aria-label", statuses.join(", "));
  line.appendChild(dots);
  const yesNo = (value) => (value === true ? ta("yes") : value === false ? ta("no") : ta("undecided"));
  const at = yesNo(result.pass_at_k);
  const all = yesNo(result.pass_pow_k);
  const summary = ta("trials.summary", { count: result.successes, passed: String(result.successes), ran: String(result.ran), k: String(result.k), at, all });
  line.append(` ${summary}`);
  return line;
}

function traceBlock(run, result, entry) {
  const nodes = [];
  if (result.k === 3) {
    const picker = el("div", "ae-actions");
    for (let n = 1; n <= result.k; n += 1) {
      const trial = result.trials.find((x) => x.trial === n);
      const pick = button("ae-text", ta("trace.trial", { trial: String(n) }), `trace-trial:${result.case_id}:${n}`, () => loadTrace(run, result, n));
      pick.setAttribute("aria-pressed", String(entry.trial === n));
      pick.disabled = !trial?.has_trace;
      picker.appendChild(pick);
    }
    nodes.push(picker);
  }
  if (entry.loading) nodes.push(el("p", "ae-reason", ta("trace.loading")));
  else if (entry.gone) nodes.push(el("p", "ae-reason", ta("trace.gone")));
  else if (entry.data) {
    const list = el("ol", "ae-trace");
    list.setAttribute("aria-label", ta("trace.label"));
    for (const item of entry.data.items) {
      const line = el("li", item.fault ? "fault" : "", item.text);
      if (item.fault) line.append(" ", el("span", "sr-only", ta("trace.fault")));
      list.appendChild(line);
    }
    nodes.push(list);
  }
  return nodes;
}

function caseActions(summary, mine, found) {
  const actions = el("div", "ae-actions");
  const busy = blocked();
  const reason = busy ? blockedReason() : "";
  const choice = el("select");
  choice.setAttribute("aria-label", ta("case.trials_label", { title: summary.title_text }));
  choice.dataset.focusKey = `trials:${summary.id}`;
  for (const k of [1, 3]) {
    const option = el("option", "", ta("case.trials", { count: k }));
    option.value = String(k);
    choice.appendChild(option);
  }
  choice.value = String(view.trials.get(summary.id) ?? 1);
  choice.addEventListener("change", () => view.trials.set(summary.id, Number(choice.value)));
  choice.disabled = busy;
  choice.title = reason;
  const run = button("ae-button", ta("case.run"), `run:${summary.id}`, () => launch(summary.id, Number(choice.value)));
  run.setAttribute("aria-label", ta("case.run_label", { title: summary.title_text }));
  run.disabled = busy;
  run.title = reason;
  actions.append(choice, run);
  const result = found?.result;
  if (result && result.trials.some((x) => x.has_trace)) {
    const key = `${found.run.run_id}|${summary.id}`;
    const shown = view.traces.has(key);
    const show = button("ae-text", ta(shown ? "trace.hide" : "trace.show"), `trace:${summary.id}`, () => toggleTrace(found.run, result));
    show.setAttribute("aria-expanded", String(shown));
    actions.appendChild(show);
  }
  if (mine) {
    const remove = button("ae-text", ta("case.delete"), `delete:${summary.id}`, () => deleteCase(summary.id));
    remove.setAttribute("aria-label", ta("case.delete_label", { title: summary.title_text }));
    remove.disabled = busy;
    remove.title = reason;
    actions.appendChild(remove);
  }
  return actions;
}

function firstRunBox() {
  const box = el("div", "ae-confirm");
  box.setAttribute("role", "alert");
  const { caseId, k } = view.pendingLaunch;
  box.append(
    el("span", "", ta("first_run.text")),
    button("ae-button primary", ta("first_run.go"), "first-run-go", () => start(caseId, k)),
    button("ae-button", ta("first_run.cancel"), "first-run-cancel", () => {
      view.pendingLaunch = null;
      render();
      view.panel.querySelector('[data-focus-key="suite"]')?.focus();
    }),
  );
  return box;
}

function clearBox() {
  const box = el("div", "ae-confirm");
  box.setAttribute("role", "alert");
  const count = view.cases.session.length;
  box.append(
    el("span", "", ta("clear_confirm.ask", { count })),
    button("ae-button ae-danger", ta("clear_confirm.yes"), "clear-yes", clearCases),
    button("ae-button", ta("clear_confirm.no"), "clear-no", () => {
      view.confirmClear = false;
      render();
      view.panel.querySelector('[data-focus-key="clear"]')?.focus();
    }),
  );
  return box;
}

function mainActions() {
  const actions = el("div", "ae-actions");
  const busy = blocked();
  const reason = busy ? blockedReason() : "";
  const suite = button("ae-button primary", ta("run_suite"), "suite", () => launch(null, 1));
  suite.disabled = busy;
  suite.title = reason;
  actions.appendChild(suite);
  const listing = view.cases;
  if (listing.session.length || listing.session_error === "unreadable") {
    const clear = button("ae-text ae-danger", ta("clear"), "clear", () => {
      view.confirmClear = true;
      render();
      view.panel.querySelector('[data-focus-key="clear-no"]')?.focus();
    });
    clear.disabled = busy;
    clear.title = reason;
    actions.appendChild(clear);
  }
  return actions;
}

function runsSection() {
  const nodes = [el("p", "ae-group", ta("runs.title"))];
  const finished = (view.state?.runs ?? []).filter((r) => r.status !== "running");
  if (!finished.length) {
    nodes.push(el("p", "ae-reason", ta("runs.empty")));
    return nodes;
  }
  const known = new Set(finished.map((r) => r.run_id));
  const pick = view.pick;
  if (!pick.manual || !known.has(pick.a) || !known.has(pick.b)) {
    pick.manual = false;
    pick.b = finished[finished.length - 1].run_id;
    pick.a = finished[Math.max(finished.length - 2, 0)].run_id;
  }
  const table = el("table", "ae-table");
  const head = el("tr");
  for (const key of ["runs.pick_a", "runs.pick_b", "runs.col.time", "runs.col.model", "runs.col.prompt", "runs.col.result"]) {
    const cell = el("th", "", ta(key));
    cell.scope = "col";
    head.appendChild(cell);
  }
  const thead = el("thead");
  thead.appendChild(head);
  const tbody = el("tbody");
  for (const summary of finished) tbody.appendChild(runRow(summary));
  table.append(thead, tbody);
  nodes.push(table);
  if (finished.length >= 2) nodes.push(...compareSection());
  return nodes;
}

function runRow(summary) {
  const row = el("tr");
  row.dataset.runId = summary.run_id;
  const time = timeText(summary.started_at);
  for (const side of ["a", "b"]) {
    const cell = el("td");
    const radio = el("input");
    radio.type = "radio";
    radio.name = `agent-eval-pick-${side}`;
    radio.value = summary.run_id;
    radio.checked = view.pick[side] === summary.run_id;
    radio.dataset.focusKey = `pick-${side}:${summary.run_id}`;
    radio.setAttribute("aria-label", ta("runs.pick_label", { pick: side.toUpperCase(), time }));
    radio.addEventListener("change", () => {
      view.pick[side] = summary.run_id;
      view.pick.manual = true;
      view.comparison = null;
      render();
    });
    cell.appendChild(radio);
    row.appendChild(cell);
  }
  row.appendChild(el("td", "num", time));
  row.appendChild(el("td", "", summary.model_label ?? "—"));
  row.appendChild(el("td", "", ta(summary.system_prompt_is_default ? "head.prompt_default" : "head.prompt_custom")));
  const result = el("td", "num");
  const run = view.runs.get(summary.run_id);
  if (summary.scope === "case" && run?.cases?.length) {
    const trials = ta("case.trials", { count: summary.k });
    result.appendChild(el("span", "meta", ta("runs.scope_case", { title: run.cases[0].title_text, trials })));
  }
  const parts = [ta("runs.result", { count: summary.passed, passed: String(summary.passed), ran: String(summary.ran) })];
  if (summary.not_run) parts.push(ta("runs.not_run", { count: summary.not_run }));
  if (["cancelled", "budget", "error"].includes(summary.status)) parts.push(ta(`runs.status.${summary.status}`));
  result.append(parts.join(" "));
  row.appendChild(result);
  return row;
}

function compareSection() {
  const nodes = [];
  const go = button("ae-button", ta("compare.title"), "compare", compare);
  const actions = el("div", "ae-actions");
  actions.appendChild(go);
  nodes.push(actions);
  const shown = view.comparison;
  if (!shown || shown.key !== `${view.pick.a}|${view.pick.b}`) return nodes;
  if (shown.sameRun) {
    nodes.push(el("p", "ae-head", ta("compare.same_run")));
    return nodes;
  }
  const data = shown.data;
  const fields = data.differs.map((field) => ta(`compare.field.${field}`));
  nodes.push(el("p", "ae-head", data.control || !fields.length ? ta("compare.control") : ta("compare.diff", { fields: fields.join(", ") })));
  const table = el("table", "ae-table");
  table.dataset.role = "comparison";
  const head = el("tr");
  for (const label of [ta("compare.col.case"), "A", "B", ta("compare.col.change")]) {
    const cell = el("th", "", label);
    cell.scope = "col";
    head.appendChild(cell);
  }
  const thead = el("thead");
  thead.appendChild(head);
  const tbody = el("tbody");
  for (const line of data.rows) {
    const row = el("tr");
    row.dataset.caseId = line.case_id;
    row.appendChild(el("td", "", line.title_text));
    for (const side of [line.a, line.b]) row.appendChild(el("td", "", side ? ta(`status.${side}`) : ta("compare.missing")));
    const change =
      line.change === "absent" ? ta(line.absent_from === "a" ? "compare.change.absent_a" : "compare.change.absent_b") : ta(`compare.change.${line.change}`);
    const cls = { regressed: "ae-diff reg", fixed: "ae-diff fix" }[line.change] ?? "";
    row.appendChild(el("td", cls, change));
    tbody.appendChild(row);
  }
  table.append(thead, tbody);
  nodes.push(table);
  return nodes;
}

// ---------- reading ----------

/** The case's result shown: the running run's if it plays the case, else the latest finished
 * run that played it. */
function resultOf(caseId) {
  const summaries = view.state?.runs ?? [];
  for (let i = summaries.length - 1; i >= 0; i -= 1) {
    const run = view.runs.get(summaries[i].run_id);
    const result = run?.cases?.find((c) => c.case_id === caseId);
    if (!result) continue;
    if (run.status === "running" || result.status !== "pending") return { run, result };
  }
  return null;
}

function titleOf(caseId) {
  const listing = view.cases;
  const listed = listing && [...listing.provided, ...listing.session].find((c) => c.id === caseId);
  if (listed) return listed.title_text;
  for (const run of view.runs.values()) {
    const result = run.cases?.find((c) => c.case_id === caseId);
    if (result) return result.title_text;
  }
  return caseId;
}

function updateBadges() {
  for (const badge of document.querySelectorAll(".ae-badge[data-case-id]")) {
    badge.textContent = ta("badge", { title: titleOf(badge.dataset.caseId) });
  }
}

function checkLabel(kind) {
  return kind === "model_calls_max" ? ta("check.model_calls_max") : t(`main.agent_case.form.checks.kind.${kind}`);
}

function turnLabel(turnId) {
  const number = /^t(\d+)$/.exec(turnId ?? "")?.[1];
  return number ? t("main.turn.name_inline", { n: number }) : (turnId ?? "—");
}

function timeText(iso) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : dateTimeFormat({ hour: "2-digit", minute: "2-digit" }).format(date);
}

/** « arrêté » → « Arrêté. »: a reason shown as a sentence. */
function sentence(text) {
  const trimmed = text.trim();
  const capital = trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
  return /[.!?…]$/.test(capital) ? capital : `${capital}.`;
}

// ---------- plumbing ----------

function toggle() {
  return document.getElementById("agent-eval-toggle");
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function button(className, text, focusKey, onClick) {
  const node = el("button", className, text);
  node.type = "button";
  node.dataset.focusKey = focusKey;
  node.addEventListener("click", onClick);
  return node;
}

const rendering = { alerts: null };

/** An error line; `role=alert` only when it appears, so that a reader does not read again an
 * alert a render keeps (review: once a second during a run). */
function alertLine(text) {
  const line = el("p", "ae-error", text);
  if (!view.alerted.has(text)) line.setAttribute("role", "alert");
  rendering.alerts?.add(text);
  line.id = `agent-eval-alert-${++ids}`;
  return line;
}

function stylesReady() {
  for (const href of STYLESHEETS) {
    if (document.querySelector(`link[href="${href}"]`)) continue;
    const link = el("link");
    link.rel = "stylesheet";
    link.href = href;
    document.head.appendChild(link);
  }
}

async function getJson(url) {
  return request(url, undefined);
}

async function sendJson(method, url, body) {
  const init = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) init.body = JSON.stringify(body);
  return request(url, init);
}

async function request(url, init) {
  try {
    const response = await fetch(url, init);
    const parsed = await response.json().catch(() => null);
    return { ok: response.ok, status: response.status, body: parsed };
  } catch {
    return { ok: false, status: 0, body: null };
  }
}
