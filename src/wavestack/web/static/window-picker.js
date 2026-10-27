// Story 26: the context window (DESIGN.md > window-picker, AD-9). Story 16.9 (CAP-7): one
// module for the main screen and the RAG workshop, its panel built here (one source).
// Every figure and text of the panel comes from `context_window_state` (AD-1): the browser
// only lays them out, marks the choice noted and says why « Appliquer » is disabled.
import { numberFormat, t } from "./i18n.js";

let page = null; // { getSessionState, onStatus }, once mounted
let windowState = null;
let windowPick = null;
let windowError = null;
let renderedWindowKey = null;
let windowApplying = false; // a POST in flight: a second click sends nothing
let claudeCacheApplying = false; // V1.3 story 5: the cache setting's own POST
let claudeCachePick = null; // ... and the choice it carries, shown until the session answers

const $ = (id) => document.getElementById(id);
const windowPanel = () => $("window-panel");
const fmt = (n) => numberFormat({ maximumFractionDigits: 1 }).format(n);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

const sessionState = () => page?.getSessionState() ?? null;
const betweenTurns = () => sessionState()?.reason_text || t("main.window.between_turns");

async function postIntention(path, body) {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function withId(node, id, attrs = {}) {
  node.id = id;
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
  return node;
}

const CACHE_CHOICES = [
  ["off", "main.window.claude_cache_off"],
  ["5m", "main.window.claude_cache_5m"],
  ["1h", "main.window.claude_cache_1h"],
];

function cacheChoice([value, key]) {
  const label = el("label", "window-choice-label");
  const input = el("input");
  input.type = "radio";
  input.name = "claude-cache";
  input.value = value;
  label.append(input, " ", el("span", "", t(key)));
  return label;
}

// The button and its panel, in `mount` (`<div id="window-picker">` of each page).
function build(mount) {
  const toggle = withId(el("button", "window-toggle"), "window-toggle", {
    "aria-haspopup": "dialog",
    "aria-expanded": "false",
    "aria-controls": "window-panel",
  });
  toggle.type = "button";
  toggle.append(el("span", "window-toggle-long", t("main.window.toggle")), " ", withId(el("span", "", "…"), "window-toggle-value"), " ▾");
  const panel = withId(el("section", "window-panel"), "window-panel", { role: "dialog", "aria-labelledby": "window-panel-title" });
  panel.hidden = true;
  const sizes = el("fieldset", "window-choices");
  sizes.append(el("legend", "window-choices-legend", t("main.window.size_legend")), withId(el("div"), "window-choices"));
  const cache = withId(el("fieldset", "window-choices"), "claude-cache", { "data-testid": "claude-cache" });
  cache.append(el("legend", "window-choices-legend", t("main.window.claude_cache_legend")), ...CACHE_CHOICES.map(cacheChoice));
  const current = withId(el("p", "window-current"), "window-current");
  current.hidden = true;
  const scroll = el("div", "window-scroll");
  scroll.append(
    withId(el("h3", "window-panel-title", t("main.window.panel_title")), "window-panel-title"),
    withId(el("p", "window-help"), "window-help"),
    el("p", "window-help", t("main.window.saved_help")),
    current,
    sizes,
    withId(el("p", "window-note"), "window-note"),
    cache,
    withId(el("p", "window-note"), "claude-cache-note")
  );
  const alert = withId(el("p", "window-alert"), "window-alert", { role: "alert" });
  alert.hidden = true;
  const apply = withId(el("button", "window-apply", t("main.window.apply")), "window-apply");
  const close = withId(el("button", "window-close", t("common.close")), "window-close");
  apply.type = close.type = "button";
  const actions = el("div", "window-actions");
  actions.append(apply, close);
  panel.append(scroll, alert, actions);
  mount.classList.add("window-picker");
  mount.replaceChildren(toggle, panel);
}

/** Mounts the picker once per page. `getSessionState()`: `{ state, reason_text }` (the panel
 * acts between two turns only); `onStatus(text)`: what the page's status line says after an
 * « Appliquer » (a refusal, or the session's answer; `null` clears it). */
export function createWindowPicker({ mount, getSessionState, onStatus = () => {} }) {
  page = { getSessionState, onStatus };
  build(mount);
  $("window-toggle").addEventListener("click", () => {
    if (windowPanel().hidden) openWindowPanel();
    else closeWindowPanel(true);
  });
  $("window-close").addEventListener("click", () => closeWindowPanel(true));
  $("window-apply").addEventListener("click", applyWindow);
  $("claude-cache").addEventListener("change", (event) => {
    if (event.target.name === "claude-cache") applyClaudeCache(event.target.value);
  });
  $("window-choices").addEventListener("change", (event) => {
    if (event.target.name !== "window-choice") return;
    windowPick = Number(event.target.value);
    windowError = null;
    renderWindowPicker();
  });
  window.addEventListener("resize", () => {
    if (!windowPanel().hidden) placeWindowPanel();
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".window-picker")) closeWindowPanel();
  });
  renderWindowPicker();
}

/** The session's `context_window_state` (live, or from `/api/state` at a reload). */
export function handleWindowState(payload) {
  windowState = payload ?? null;
  renderWindowPicker();
}

export const windowPanelOpen = () => Boolean(windowPanel() && !windowPanel().hidden);

// Lot K (K8): the panel drops under its button, left-aligned; when that would take it past
// the window's right edge (853 px at a 150 % zoom, no pane hidden), it moves left by the
// overflow, never past the window's left edge. Its width already fits the window (CSS).
function placeWindowPanel() {
  const panel = windowPanel();
  panel.style.left = "";
  const margin = 16; // --spacing-4, the gutter the CSS width keeps on each side
  const rect = panel.getBoundingClientRect();
  const overflow = rect.right - (document.documentElement.clientWidth - margin);
  if (overflow > 0) panel.style.left = `${-Math.min(overflow, Math.max(0, rect.left - margin))}px`;
}

function openWindowPanel() {
  windowPick = windowState?.configured ?? null;
  windowError = null;
  windowPanel().hidden = false;
  $("window-toggle").setAttribute("aria-expanded", "true");
  placeWindowPanel();
  renderWindowPicker();
  const checked = windowPanel().querySelector('input[name="window-choice"]:checked');
  (checked ?? windowPanel().querySelector('input[name="window-choice"]'))?.focus();
}

export function closeWindowPanel(returnFocus = false) {
  if (!windowPanelOpen()) return;
  windowPanel().hidden = true;
  windowError = null;
  const toggle = $("window-toggle");
  toggle.setAttribute("aria-expanded", "false");
  if (returnFocus) toggle.focus();
}

// Why « Appliquer » cannot act on the choice noted, else `null`.
function windowApplyReason(ws, pick) {
  if (sessionState()?.state !== "idle") return betweenTurns();
  if (ws.locked_text) return ws.locked_text;
  if (pick === ws.configured) return t("main.window.already", { window: pick });
  const choice = ws.choices.find((c) => c.window === pick);
  if (!choice) return t("main.window.choose");
  return choice.fits ? null : choice.refusal_text;
}

export function renderWindowPicker() {
  if (!page) return; // not mounted yet: the state is kept, drawn at the mount
  const ws = windowState;
  const toggle = $("window-toggle");
  setText($("window-toggle-value"), ws ? fmt(ws.window) : "…");
  toggle.disabled = !ws;
  // Lot K (A3): the button shows the effective window; the one chosen, when it differs
  // (llama-server's `-c`, the native context…), is in its tooltip.
  const chosen = ws && ws.configured !== ws.window ? t("main.window.chosen", { window: ws.configured }) : "";
  const title = !ws
    ? t("main.window.waiting")
    : t("main.window.toggle_title", { window: ws.window, bound: ws.bound_text ? `, ${ws.bound_text}` : "", chosen });
  if (toggle.title !== title) toggle.title = title;
  toggle.setAttribute("aria-label", ws ? t("main.window.toggle_label", { window: ws.window }) : t("main.window.panel_title"));
  if (!ws || windowPanel().hidden) return;
  const pick = windowPick ?? ws.configured;
  const list = $("window-choices");
  setText($("window-help"), t("main.window.help", { window: ws.default }));
  // A value set by hand outside the choices: said, no choice marked « (actuelle) ».
  const offList = !ws.choices.some((c) => c.current);
  const currentLine = $("window-current");
  currentLine.hidden = !offList;
  setText(currentLine, offList ? t("main.window.current_off_list", { window: ws.configured }) : "");
  // Rebuilt only when the session's figures change: an arrow key moving the choice keeps
  // its focus (the choice noted is set in place below); a rebuild gives it back.
  const key = JSON.stringify(ws);
  if (key !== renderedWindowKey) {
    renderedWindowKey = key;
    const focused = list.contains(document.activeElement) ? document.activeElement.value : null;
    list.replaceChildren(...ws.choices.map(windowChoiceNode));
    if (focused !== null) list.querySelector(`input[name="window-choice"][value="${focused}"]`)?.focus();
  }
  for (const input of list.querySelectorAll('input[name="window-choice"]')) {
    const checked = Number(input.value) === pick;
    if (input.checked !== checked) input.checked = checked;
    input.closest(".window-choice").classList.toggle("is-picked", checked);
  }
  setText($("window-note"), ws.read_note_text);
  // V1.3 story 5: Claude's prompt cache; the state (and the reason it is greyed) is the
  // session's, the browser only lays it out.
  const cacheReason = claudeCacheApplying
    ? t("main.window.claude_cache_pending")
    : ws.claude_cache_locked_text || (sessionState()?.state !== "idle" ? betweenTurns() : null);
  for (const input of document.querySelectorAll('input[name="claude-cache"]')) {
    input.checked = input.value === (claudeCacheApplying ? claudeCachePick : ws.claude_cache);
    input.disabled = Boolean(cacheReason);
  }
  setText($("claude-cache-note"), cacheReason ?? ws.claude_cache_note_text ?? "");
  const apply = $("window-apply");
  const reason = windowApplying ? t("main.window.request_pending") : windowApplyReason(ws, pick);
  apply.disabled = Boolean(reason);
  const applyTitle = reason ?? t("main.window.apply_title", { window: pick });
  if (apply.title !== applyTitle) apply.title = applyTitle;
  const alert = $("window-alert");
  alert.hidden = !windowError;
  setText(alert, windowError ?? "");
}

function windowChoiceNode(choice) {
  const row = el("div", "window-choice");
  row.dataset.window = String(choice.window);
  row.classList.toggle("is-refused", !choice.fits);
  const label = el("label", "window-choice-label");
  const input = el("input");
  input.type = "radio";
  input.name = "window-choice";
  input.value = String(choice.window);
  input.disabled = !choice.fits; // AD-9: a refused choice is only disabled, its reason shown
  const details = el("div", "window-choice-details");
  const figures = el("span", "window-choice-figures");
  figures.id = `window-choice-${choice.window}`;
  label.append(input, el("strong", "", t("main.window.choice", { window: choice.window })));
  if (choice.current) label.append(el("span", "window-choice-current", ` ${t("main.window.current")}`));
  figures.append(el("span", "window-choice-line", choice.kv_text), el("span", "window-choice-line", choice.read_text));
  if (choice.bound_text) figures.append(el("span", "window-choice-line window-choice-bound", choice.bound_text));
  const verdict = choice.fits
    ? el("span", "window-choice-verdict is-fits", `✓ ${t("main.window.fits")}`)
    : el("span", "window-choice-verdict is-refused", `⚠ ${choice.refusal_text}`);
  verdict.id = `window-choice-${choice.window}-verdict`;
  details.append(figures, verdict);
  // The figures and the verdict (a refused choice's reason) describe the radio.
  input.setAttribute("aria-describedby", `${figures.id} ${verdict.id}`);
  row.append(label, details);
  return row;
}

// V1.3 story 5: the cache setting applies at once (no « Appliquer »); a refusal is shown in
// the panel's alert, the radios go back to the session's state.
async function applyClaudeCache(value) {
  if (claudeCacheApplying) return;
  windowError = null;
  claudeCacheApplying = true;
  claudeCachePick = value;
  renderWindowPicker();
  try {
    const response = await postIntention("/api/intentions/claude_cache", { value });
    const answer = await response.json().catch(() => ({}));
    if (!response.ok) {
      windowError = typeof answer.detail === "string" ? answer.detail : t("main.window.claude_cache_refused");
    }
  } catch (error) {
    windowError = t("main.request_failed", { error: error.message });
  } finally {
    claudeCacheApplying = false;
  }
  renderWindowPicker();
}

async function applyWindow() {
  const ws = windowState;
  if (!ws || windowApplying) return;
  const pick = windowPick ?? ws.configured;
  windowError = null;
  windowApplying = true;
  renderWindowPicker(); // « Appliquer » disabled during the request
  try {
    const response = await postIntention("/api/intentions/context_window", { window: pick });
    const answer = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof answer.detail === "string" ? answer.detail : t("main.window.refused");
      windowError = detail; // in the panel and in the page's status line
      page.onStatus(detail);
    } else {
      closeWindowPanel(true);
      // A reload is followed as a model load (`model_load_*`); otherwise the answer says it.
      page.onStatus(answer.switching ? null : answer.message_text ?? null);
    }
  } catch (error) {
    windowError = t("main.request_failed", { error: error.message });
  } finally {
    windowApplying = false;
  }
  renderWindowPicker();
}
