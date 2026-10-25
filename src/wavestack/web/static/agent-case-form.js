// V1.5 CAP-3 (story 3): « En faire un cas », the drawer of the Vue humain that turns a finished
// turn into an agent case. The server rebuilds the draft from the journal (`GET /api/agent_eval/draft`),
// tells whether the case fails on that turn (`POST .../verdict`, no model call) and saves it
// (`POST .../cases`); this module only shows them and sends what the formatter typed.
//
// Contract with `app.js` and the story 4 (`agent-eval.js`): the ES exports below, no global.
// It loads its own stylesheet, so `index.html` stays as it is.

import { dateTimeFormat, joinList, numberFormat, t } from "./i18n.js";

const API = "/api/agent_eval";
const VERDICT_DELAY_MS = 250;
const MAX_CHECKS = 2;
const KINDS = ["tool_called", "tool_not_called", "argument_never", "answer_contains", "hook_decided", "subagent_called", "turn_completed"];
// The parameters of each kind, in the order they are shown; `before` is the only optional one.
const PARAMS = {
  tool_called: ["tool", "before"],
  tool_not_called: ["tool"],
  argument_never: ["tool", "argument", "contains"],
  answer_contains: ["text"],
  hook_decided: ["hook", "decision"],
  subagent_called: [],
  turn_completed: [],
};
const OPTIONAL = new Set(["before"]);
const DECISIONS = ["block", "ask_human"];

const tc = (key, vars) => t(`main.agent_case.${key}`, vars);

let openView = null;
const savedListeners = new Set();
let stylesheet = null;
let current = null; // the open drawer's state, or null (closed)
let ids = 0;

// ---------- the module's interface ----------

/** A main message turn, ended, that no case run played. `started` and `ended` are the payloads. */
export function canMakeCase(turnStarted, turnEnded) {
  if (!turnStarted || !turnEnded) return false;
  return (turnStarted.kind ?? "message") === "message" && !turnStarted.case_id;
}

/** « Ouvrir Évaluer l'agent »: `fn(caseId)`. The button stays hidden until a function is given. */
export function registerOpenView(fn) {
  openView = fn;
}

/** `fn(case)` after each saved case; returns the function that unsubscribes. */
export function onCaseSaved(fn) {
  savedListeners.add(fn);
  return () => savedListeners.delete(fn);
}

/** Opens the drawer on `turnId`; `opener` gets the focus back when it closes. */
export async function openCaseForm(turnId, opener) {
  if (current) close({ focus: false });
  const state = {
    turnId,
    opener,
    turnLabel: opener?.dataset?.turnLabel || turnId,
    drawer: null,
    draft: null,
    form: null,
    initial: "",
    verdictSeq: 0,
    timer: null,
    saving: false,
    done: false,
    confirm: null,
    parts: {},
  };
  current = state;
  const drawer = el("aside", "ae-drawer");
  state.drawer = drawer;
  drawer.hidden = true;
  drawer.setAttribute("role", "dialog");
  drawer.setAttribute("aria-modal", "true");
  drawer.tabIndex = -1;
  const titleId = `ae-form-title-${++ids}`;
  drawer.setAttribute("aria-labelledby", titleId);
  const title = el("h3", "", tc("form.title"));
  title.id = titleId;
  drawer.append(title, el("p", "ae-loading", tc("form.loading")));
  drawer.addEventListener("keydown", (event) => onKey(state, event));
  (document.querySelector('[data-pane="human"]') ?? document.body).appendChild(drawer);
  await stylesReady();
  if (current !== state) return;
  drawer.hidden = false;
  drawer.focus();
  const result = await fetchJson(`${API}/draft?turn_id=${encodeURIComponent(turnId)}`);
  if (current !== state) return;
  if (!result.ok) {
    refuse(state, result.body?.detail && typeof result.body.detail === "string" ? result.body.detail : tc("form.error.no_answer"));
    return;
  }
  state.draft = result.body;
  buildForm(state);
  scheduleVerdict(state, 0);
}

export function closeCaseForm() {
  if (current) close({ focus: true });
}

// ---------- plumbing ----------

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function code(text) {
  return el("code", "", text);
}

function stylesReady() {
  if (!stylesheet) {
    stylesheet = new Promise((resolve) => {
      const link = el("link");
      link.rel = "stylesheet";
      link.href = "/static/agent-case-form.css";
      link.addEventListener("load", resolve);
      link.addEventListener("error", resolve); // unstyled but usable
      document.head.appendChild(link);
    });
  }
  return stylesheet;
}

async function fetchJson(url, body) {
  try {
    const response = await fetch(url, body === undefined ? undefined : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const parsed = await response.json().catch(() => null);
    return { ok: response.ok, status: response.status, body: parsed };
  } catch {
    return { ok: false, status: 0, body: null };
  }
}

function openerTarget(state) {
  if (state.opener?.isConnected) return state.opener;
  return document.querySelector(`[data-focus-key="agent-case:${state.turnId}"]`);
}

function close({ focus }) {
  const state = current;
  current = null;
  state.verdictSeq += 1;
  clearTimeout(state.timer);
  state.drawer.remove();
  if (focus) openerTarget(state)?.focus();
}

/** State 3: the drawer closes, the reason shows under the turn's actions. */
function refuse(state, text) {
  const target = openerTarget(state);
  close({ focus: true });
  const row = target?.closest(".turn-actions");
  if (!row) return;
  row.parentElement.querySelector(".ae-refusal")?.remove();
  const note = el("p", "bubble-note is-error ae-refusal", text);
  note.setAttribute("role", "alert");
  row.after(note);
}

function focusables(drawer) {
  return [...drawer.querySelectorAll("button, input, select, textarea")].filter((n) => !n.disabled && !n.closest("[hidden]"));
}

function onKey(state, event) {
  if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    cancel(state);
  } else if (event.key === "Tab") {
    const nodes = focusables(state.drawer);
    if (!nodes.length) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === state.drawer)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
}

// ---------- the form ----------

function toolNames(draft) {
  const seen = [];
  for (const call of draft.tool_calls) if (!seen.includes(call.tool)) seen.push(call.tool);
  for (const name of draft.tools) if (!seen.includes(name)) seen.push(name);
  return seen;
}

/** The parameters a kind starts with, filled from the turn. */
function prefill(kind, draft) {
  const first = draft.tool_calls[0];
  switch (kind) {
    case "tool_called":
      return { tool: first?.tool ?? "", before: "" };
    case "tool_not_called":
      return { tool: first?.tool ?? "" };
    case "argument_never": {
      const [name, value] = Object.entries(first?.arguments ?? {})[0] ?? ["", ""];
      return { tool: first?.tool ?? "", argument: name, contains: typeof value === "string" ? value : JSON.stringify(value) };
    }
    case "hook_decided": {
      const seen = draft.hooks_decided[0];
      return { hook: seen?.hook ?? "", decision: DECISIONS.includes(seen?.decision) ? seen.decision : "" };
    }
    case "answer_contains":
      return { text: "" };
    default:
      return {};
  }
}

function firstCheck(draft) {
  const kind = draft.origin_status !== "completed" || !draft.tool_calls.length ? "turn_completed" : "tool_called";
  return { kind, params: prefill(kind, draft) };
}

function initialForm(draft) {
  return {
    title_text: "",
    prompt: draft.prompt,
    include_history: draft.history_available && draft.history.length > 0 && draft.bricks.includes("short_memory"),
    freeze_system_prompt: false,
    approval: draft.approval,
    on_overflow: draft.on_overflow,
    symptom_text: "",
    assertion_text: "",
    checks: [firstCheck(draft)],
    max_model_calls: String(draft.suggested_max_model_calls),
  };
}

const dirty = (state) => JSON.stringify(state.form) !== state.initial;

function body(state) {
  const f = state.form;
  return {
    turn_id: state.turnId,
    title_text: f.title_text,
    symptom_text: f.symptom_text,
    assertion_text: f.assertion_text,
    prompt: f.prompt,
    include_history: f.include_history,
    freeze_system_prompt: f.freeze_system_prompt,
    approval: f.approval,
    on_overflow: f.on_overflow,
    max_model_calls: Number.parseInt(f.max_model_calls, 10) || 0,
    checks: f.checks.map((c) => ({ kind: c.kind, ...Object.fromEntries(PARAMS[c.kind].map((p) => [p, c.params[p] ?? ""])) })),
  };
}

function incomplete(state) {
  return state.form.checks.some((c) => PARAMS[c.kind].some((p) => !OPTIONAL.has(p) && !String(c.params[p] ?? "").trim()));
}

let seq = 0;
function control(state, tag, name, value, attributes = {}) {
  const node = el(tag);
  node.id = `ae-f-${++seq}`;
  node.dataset.field = name;
  Object.assign(node, attributes);
  if (value !== undefined) node.value = value;
  return node;
}

function labelled(text, node) {
  const row = el("div", "ae-field");
  const label = el("label", "", text);
  label.htmlFor = node.id;
  row.append(label, node);
  return row;
}

function option(value, text, selected) {
  const node = el("option", "", text);
  node.value = value;
  node.selected = selected;
  return node;
}

function selectOf(state, name, choices, value) {
  const node = control(state, "select", name);
  for (const [v, text] of choices) node.appendChild(option(v, text, v === value));
  return node;
}

function checkbox(text, checked, onChange, disabled = false) {
  const label = el("label", "ae-check-line");
  const input = el("input");
  input.type = "checkbox";
  input.checked = checked;
  input.disabled = disabled;
  input.addEventListener("change", () => onChange(input.checked));
  label.append(input, document.createTextNode(` ${text}`));
  return label;
}

function changed(state, node, run) {
  clearError(node);
  run();
  scheduleVerdict(state);
  refreshActions(state);
}

function buildForm(state) {
  const { draft, drawer } = state;
  state.form = initialForm(draft);
  state.initial = JSON.stringify(state.form);
  const f = state.form;
  const title = drawer.querySelector("h3");
  const when = dateTimeFormat({ dateStyle: "short", timeStyle: "short" }).format(new Date(draft.date));
  const subtitle = el("p", "ae-subtitle", tc("form.subtitle", { turn: state.turnLabel, model: draft.model?.label ?? "?", date: when }));
  drawer.replaceChildren(title, subtitle);

  if (draft.origin_status !== "completed") {
    const note = el("p", "ae-banner", tc("form.incomplete", { status: draft.origin_status }));
    note.setAttribute("role", "note");
    drawer.appendChild(note);
  }

  const titleInput = control(state, "input", "title_text", f.title_text);
  titleInput.addEventListener("input", () => changed(state, titleInput, () => (f.title_text = titleInput.value)));
  drawer.appendChild(labelled(tc("form.field.title"), titleInput));

  const prompt = control(state, "textarea", "prompt", f.prompt, { rows: 2 });
  prompt.addEventListener("input", () => changed(state, prompt, () => (f.prompt = prompt.value)));
  drawer.appendChild(labelled(tc("form.field.prompt"), prompt));

  drawer.appendChild(configBlock(draft));
  drawer.appendChild(toolsBlock(draft));

  // The history: a checkbox, or why there is none.
  if (draft.history_available) {
    const count = draft.history.length;
    drawer.appendChild(checkbox(tc("form.history.include", { count }), f.include_history, (v) => changed(state, drawer, () => (f.include_history = v)), count === 0));
    if (draft.history_note === "compacted") drawer.appendChild(el("p", "ae-note", tc("form.history.compacted")));
  } else {
    drawer.appendChild(el("p", "ae-note", tc("form.history.unavailable")));
  }
  drawer.appendChild(checkbox(tc("form.freeze_prompt"), f.freeze_system_prompt, (v) => changed(state, drawer, () => (f.freeze_system_prompt = v))));

  const approval = selectOf(state, "approval", [["refuse", tc("form.approval.refuse")], ["approve", tc("form.approval.approve")]], f.approval);
  approval.addEventListener("change", () => changed(state, approval, () => (f.approval = approval.value)));
  drawer.appendChild(labelled(tc("form.approval.label"), approval));
  const overflow = selectOf(
    state,
    "on_overflow",
    ["none", "compaction", "sliding_window"].map((v) => [v, tc(`form.overflow.${v}`)]),
    f.on_overflow
  );
  overflow.addEventListener("change", () => changed(state, overflow, () => (f.on_overflow = overflow.value)));
  drawer.appendChild(labelled(tc("form.overflow.label"), overflow));

  const symptom = control(state, "input", "symptom_text", f.symptom_text);
  symptom.addEventListener("input", () => changed(state, symptom, () => (f.symptom_text = symptom.value)));
  drawer.appendChild(labelled(tc("form.field.symptom"), symptom));
  const assertion = control(state, "input", "assertion_text", f.assertion_text);
  assertion.addEventListener("input", () => changed(state, assertion, () => (f.assertion_text = assertion.value)));
  drawer.appendChild(labelled(tc("form.field.assertion"), assertion));

  const checks = el("fieldset", "ae-checks");
  checks.dataset.field = "checks";
  state.parts.checks = checks;
  drawer.appendChild(checks);
  renderChecks(state);

  const cap = control(state, "input", "max_model_calls", f.max_model_calls, { inputMode: "numeric" });
  cap.addEventListener("input", () => changed(state, cap, () => (f.max_model_calls = cap.value)));
  drawer.appendChild(labelled(tc("form.field.max_calls"), cap));

  const verdict = el("div", "ae-verdict pending");
  verdict.setAttribute("role", "status");
  verdict.textContent = tc("form.verdict.pending");
  state.parts.verdict = verdict;
  drawer.appendChild(verdict);

  const saveError = el("p", "ae-error ae-save-error");
  saveError.setAttribute("role", "alert");
  saveError.hidden = true;
  state.parts.saveError = saveError;
  const actions = el("div", "ae-actions");
  const save = el("button", "ae-button primary", tc("form.save"));
  save.type = "button";
  save.addEventListener("click", () => submit(state));
  const cancelButton = el("button", "ae-button", tc("form.cancel"));
  cancelButton.type = "button";
  cancelButton.addEventListener("click", () => cancel(state));
  actions.append(save, cancelButton);
  state.parts.save = save;
  state.parts.cancel = cancelButton;
  state.parts.actions = actions;
  drawer.append(saveError, actions);
  titleInput.focus();
}

function configBlock(draft) {
  const box = el("div", "ae-field");
  box.appendChild(el("span", "ae-legend", tc("form.config.legend")));
  const view = el("div", "ae-readonly");
  const windowText = draft.window == null ? tc("form.config.window_unset") : numberFormat().format(draft.window);
  view.appendChild(el("div", "", tc("form.config.line", { bricks: joinList(draft.bricks), window: windowText })));
  for (const [name, list] of [["tools", draft.tools], ["hooks", draft.hooks], ["skills", draft.skills], ["mcp", draft.mcp_servers]]) {
    if (!list.length) continue;
    const line = el("div", "");
    line.append(code(name), ": ");
    list.forEach((id, i) => line.append(i ? ", " : "", code(id)));
    view.appendChild(line);
  }
  if (draft.not_kept.length) {
    const options = joinList(draft.not_kept.map((k) => tc(`form.config.option.${k}`)));
    view.appendChild(el("div", "ae-note", tc("form.config.not_kept", { options })));
  }
  box.appendChild(view);
  return box;
}

function toolsBlock(draft) {
  const box = el("div", "ae-field");
  box.appendChild(el("span", "ae-legend", tc("form.tools.legend")));
  const view = el("div", "ae-readonly");
  if (!draft.tool_calls.length) view.textContent = tc("form.tools.none");
  draft.tool_calls.forEach((call, i) => {
    const line = el("div", "");
    line.append(`${i + 1}. `, code(call.tool), "(");
    Object.entries(call.arguments).forEach(([name, value], n) => {
      line.append(n ? ", " : "", `${name} = `, code(JSON.stringify(value)));
    });
    line.append(")");
    if (call.status) line.append(` → ${call.status}`);
    view.appendChild(line);
  });
  box.appendChild(view);
  return box;
}

// ---------- the checks ----------

function renderChecks(state, focusIndex = null) {
  const { form, draft } = state;
  const box = state.parts.checks;
  box.replaceChildren(el("legend", "ae-legend", tc("form.checks.legend")));
  form.checks.forEach((check, index) => {
    const row = el("div", "ae-check");
    const kind = selectOf(state, `checks.${index}.kind`, KINDS.map((k) => [k, tc(`form.checks.kind.${k}`)]), check.kind);
    kind.setAttribute("aria-label", tc("form.checks.type_label"));
    kind.addEventListener("change", () => {
      check.kind = kind.value;
      check.params = prefill(check.kind, draft);
      renderChecks(state, index);
      scheduleVerdict(state);
      refreshActions(state);
    });
    const params = el("div", "ae-params");
    for (const name of PARAMS[check.kind]) params.appendChild(paramField(state, check, index, name));
    row.append(kind, params);
    if (form.checks.length > 1) {
      const remove = el("button", "ae-text", tc("form.checks.remove"));
      remove.type = "button";
      remove.addEventListener("click", () => {
        form.checks.splice(index, 1);
        renderChecks(state, 0);
        scheduleVerdict(state);
        refreshActions(state);
      });
      row.appendChild(remove);
    }
    box.appendChild(row);
  });
  if (form.checks.length < MAX_CHECKS) {
    const add = el("button", "ae-text", tc("form.checks.add"));
    add.type = "button";
    add.addEventListener("click", () => {
      form.checks.push(firstCheckExtra(state));
      renderChecks(state, form.checks.length - 1);
      scheduleVerdict(state);
      refreshActions(state);
    });
    box.appendChild(add);
    state.parts.add = add;
  } else {
    state.parts.add = null;
  }
  if (focusIndex !== null) box.querySelectorAll("select[data-field$='.kind']")[focusIndex]?.focus();
}

/** A second check starts as `turn_completed`, or as the first kind not already chosen. */
function firstCheckExtra(state) {
  const used = new Set(state.form.checks.map((c) => c.kind));
  const kind = ["tool_not_called", "answer_contains", "turn_completed"].find((k) => !used.has(k)) ?? "turn_completed";
  return { kind, params: prefill(kind, state.draft) };
}

function paramField(state, check, index, name) {
  const field = `checks.${index}.${name}`;
  const value = check.params[name] ?? "";
  let node;
  if (name === "tool" || name === "before") {
    const names = toolNames(state.draft);
    const blank = name === "before" || !names.length || !names.includes(value);
    node = selectOf(state, field, names.map((n) => [n, n]), value);
    if (blank) node.prepend(option("", "", value === ""));
  } else if (name === "decision") {
    node = selectOf(state, field, [["", ""], ...DECISIONS.map((d) => [d, tc(`form.checks.decision.${d}`)])], value);
  } else {
    node = control(state, "input", field, value);
  }
  const sync = () => changed(state, node, () => (check.params[name] = node.value));
  node.addEventListener(node.tagName === "SELECT" ? "change" : "input", sync);
  return labelled(tc(`form.checks.param.${name}`), node);
}

// ---------- the verdict ----------

function scheduleVerdict(state, delay = VERDICT_DELAY_MS) {
  clearTimeout(state.timer);
  state.verdictSeq += 1;
  const mine = state.verdictSeq;
  const banner = state.parts.verdict;
  if (banner) banner.classList.add("is-stale"); // the old verdict stays, greyed
  state.timer = setTimeout(() => runVerdict(state, mine), delay);
}

function showVerdict(state, kind, strong, detail = "") {
  const banner = state.parts.verdict;
  banner.className = `ae-verdict ${kind}`;
  banner.replaceChildren(...(strong ? [el("strong", "", strong)] : []), ...(detail ? [document.createTextNode(` ${detail}`)] : []));
}

async function runVerdict(state, mine) {
  if (current !== state || mine !== state.verdictSeq) return;
  if (incomplete(state)) {
    showVerdict(state, "pending", tc("form.verdict.incomplete"));
    return;
  }
  const result = await fetchJson(`${API}/verdict`, body(state));
  if (current !== state || mine !== state.verdictSeq) return; // the last answer wins
  if (result.ok) {
    const v = result.body;
    if (v.passed) showVerdict(state, "warns", tc("form.verdict.cannot_fail"));
    else showVerdict(state, "fails", tc("form.verdict.fails"), v.failing?.reason_text ?? "");
  } else if (result.status === 422) {
    showVerdict(state, "pending", tc("form.verdict.incomplete"));
  } else {
    showVerdict(state, "warns", tc("form.verdict.unavailable"));
  }
}

// ---------- save, cancel ----------

function clearError(node) {
  const id = node.getAttribute?.("aria-describedby");
  if (!id) return;
  document.getElementById(id)?.remove();
  node.removeAttribute("aria-invalid");
  node.removeAttribute("aria-describedby");
}

function showErrors(state, errors) {
  const shown = [];
  errors.forEach((error, i) => {
    const node = state.drawer.querySelector(`[data-field="${error.field}"]`);
    if (!node) return;
    clearError(node);
    const message = el("p", "ae-error", error.message_text);
    message.id = `ae-err-${++seq}-${i}`;
    node.setAttribute("aria-invalid", "true");
    node.setAttribute("aria-describedby", message.id);
    (node.closest(".ae-field") ?? node).after(message);
    shown.push(node);
  });
  shown.sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
  const first = shown[0];
  if (first) (first.matches("fieldset") ? first.querySelector("select, input, button") : first).focus();
}

function refreshActions(state) {
  state.parts.save.disabled = state.saving;
  state.parts.save.textContent = state.saving ? tc("form.saving") : tc("form.save");
}

async function submit(state) {
  if (state.saving) return;
  for (const stale of state.drawer.querySelectorAll(".ae-error")) stale.remove();
  state.parts.saveError.hidden = true;
  state.saving = true;
  refreshActions(state);
  const result = await fetchJson(`${API}/cases`, body(state));
  if (current !== state) return;
  state.saving = false;
  refreshActions(state);
  if (result.ok) {
    saved(state, result.body.case);
  } else if (result.status === 422 && Array.isArray(result.body?.detail)) {
    showErrors(state, result.body.detail);
  } else {
    const detail = result.status === 409 && typeof result.body?.detail === "string" ? result.body.detail : tc("form.error.no_answer");
    state.parts.saveError.textContent = detail;
    state.parts.saveError.hidden = false;
  }
}

function saved(state, savedCase) {
  clearTimeout(state.timer);
  state.verdictSeq += 1;
  state.done = true;
  const title = state.drawer.querySelector("h3");
  const message = el("p", "ae-saved", tc("form.saved"));
  message.setAttribute("role", "status");
  const actions = el("div", "ae-actions");
  if (openView) {
    const open = el("button", "ae-button primary", tc("form.open_view"));
    open.type = "button";
    open.addEventListener("click", () => {
      const fn = openView;
      close({ focus: false });
      fn(savedCase.id);
    });
    actions.appendChild(open);
  }
  const done = el("button", "ae-button", tc("form.close"));
  done.type = "button";
  done.addEventListener("click", () => close({ focus: true }));
  actions.appendChild(done);
  state.drawer.replaceChildren(title, message, actions);
  (actions.firstElementChild ?? done).focus();
  for (const listener of [...savedListeners]) listener(savedCase);
}

/** « Annuler » and Échap: closes at once when nothing changed, else asks in the page. */
function cancel(state) {
  if (state.done || !dirty(state)) {
    close({ focus: true });
    return;
  }
  if (state.confirm) return;
  const box = el("div", "ae-confirm");
  box.setAttribute("role", "alertdialog");
  const ask = el("span", "", tc("form.discard.ask"));
  ask.id = `ae-confirm-${++seq}`;
  box.setAttribute("aria-labelledby", ask.id);
  const yes = el("button", "ae-button ae-danger", tc("form.discard.yes"));
  yes.type = "button";
  yes.addEventListener("click", () => close({ focus: true }));
  const no = el("button", "ae-button", tc("form.discard.no"));
  no.type = "button";
  no.addEventListener("click", () => {
    box.remove();
    state.confirm = null;
    state.parts.cancel.focus();
  });
  box.append(ask, yes, no);
  state.confirm = box;
  state.parts.actions.before(box);
  no.focus();
}
