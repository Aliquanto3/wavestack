// Story 30: the RAG workshop. Everything it shows comes from `GET /api/rag_lab` or from a
// `rag_lab_*` event of the journal (AD-1): the catalog, the options' availability, the
// excerpts, their ranks and scores, the durations and the memory are built in Python. The
// page lays them out and runs no computation of its own.
//
// Lot 5a: one section, three views side by side (vues-atelier-rag.md): the sequence (BUILD
// then RUN, a line per step), the architecture (the components the chain calls on, by
// group) and the focus on one step, every step's detail folded under them. The table step →
// components is the session's (`catalog.steps`). In « Composer » the chain's editor lives in
// the sequence's lines; the A/B comparison is gone from the page (lot 5c-1: and from the
// session, one chain per run).
//
// Lot 5a-2: in « Dérouler » the steps and the components arrive one by one, by a stepper
// (`diagram.createStepper`) whose frames are the sequence's steps: every step pushed for a
// guided tour without a run, else one frame per step the run reached (its `rag_lab_*` events,
// live). The frame shown lights its step and its components, its wires flow while it runs,
// the focus shows its figures; the steps and tiles after it keep their place, invisible.
//
// Languages (4/5): the page's own texts come from `content/ui.yaml` (section `rag`) through
// `t()`, its formats from the language (`i18n.js`); the workshop's texts stay those of
// `content/rag_lab.yaml`, read in the session's language by `GET /api/rag_lab`.

import { createStepper, light, svgEl, wire, wireLayer } from "./diagram.js";
import { numberFormat, ready as textsReady, t } from "./i18n.js";
import { feedBar } from "./bar.js";

const $ = (id) => document.getElementById(id);
const quote = (value) => t("common.format.quote", { text: value });

// What the tabs' files (`rag-<tab>.js`) read of the common code: see `registerTab`.
const store = {
  content: null,
  catalog: null,
  defaultPipeline: null,
  unavailable: null,
  session: { state: "diagnostic", reason_text: null },
  serverInstance: null,
  lastSeq: 0,
  pending: false, // a POST sent, not answered yet
  run: null, // the projection of the last run: its question and its stages
  pipelines: [], // the chain being edited (one: the session runs one chain)
  refusals: [], // why the session would refuse it (`POST /api/rag_lab/validate`)
  validating: 0, // the last validation asked, so that a late answer is dropped
  mode: "play", // « compose » or « play » (vues-atelier-rag.md §1)
  current: null, // the step shown in the focus (its key), or none
  replaying: false, // `last_run` being read again: one render at its end, not one per event
  land: false, // a run just ended: its stepper lands on its last frame, or its failed step
  promptOpen: false, // lot 5c-3: the generation's prompt unfolded, kept across the renders
  download: null, // lot 5c-4: the download this page launched, { target, kind }, until `idle`
  downloadNotices: {}, // lot 5c-4: its outcome, said in its stage, by kind: { text, error }
  costs: { build: null, query: null }, // V1.2 story 3: the last run's sums by time
  update: null, // the last update run: { runId, label, ended, summary }
  workCopy: null, // the corpus's work copy (where it lives, what it changes, its documents)
  contexts: null, // V1.2 story 6: the contexts read (header, rebuilt or not, why no rebuild)
  rebuild: null, // the last rebuild of the contexts: { runId, done, total, ended, error, output }
  contextError: null, // a rebuild or a reset refused, said in the focus
  copyOp: null, // the operation whose form is open: add, modify or delete
  tab: "build", // V1.2 story 4: the view tab shown
  questions: [], // V1.2 story 4: the prepared questions (CAP-2), from `GET /api/rag_lab`
  mounted: false, // V1.2 story 4: the page is ready, the tabs' `mount` hooks ran
};

// ---------- small helpers ----------

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

// A text of content/rag_lab.yaml by its dotted path, `{name}` replaced by `values[name]`.
function text(path, values = {}) {
  let value = store.content;
  for (const key of path.split(".")) value = value?.[key];
  if (typeof value !== "string") return "";
  return value.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));
}

// « 1 536 » (narrow no-break space in French) and « 0,812 »: formatting only, in the
// session's language (read at each use: the language is known once `textsReady` resolved).
const fmtInt = (n) => (typeof n === "number" ? numberFormat().format(n) : "—");
// A fusion's score (1 / (60 + rank)) needs a fourth decimal to tell two apart.
const fmtScore = (x) => {
  if (typeof x !== "number") return "—";
  const digits = x > 0 && x < 0.1 ? 4 : 3;
  return numberFormat({ minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: false }).format(x);
};
// « 1er », « 2ᵉ » (« No. 2 », « Nr. 2 »): a plural pair of the catalogue, by the rank.
const fmtRank = (n) => (typeof n === "number" ? t("rag.rank", { count: n }) : t("rag.rank_absent"));
const labelled = (label, value) => t("common.format.label_value", { label, value });

const QUESTION_KEY = "wavestack.ragLab.question";
const CHAINS_KEY = "wavestack.ragLab"; // the chain being edited (a browser setting only)
const MODE_KEY = "wavestack.ragLab.mode";
const MODES = ["compose", "play"];
// Lot 5c-3: the version of the saved chain. Before it (no version), Generation had a single
// option, `not_run`: a chain saved then had not chosen « Ne pas générer ».
const CHAINS_VERSION = 2;

function stored(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function keep(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // no storage (private window, blocked data): the value lives with the page
  }
}

// Never rejects: a network failure is an answer too, with a French detail.
async function post(path, body) {
  let response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return { ok: false, status: 0, body: { detail: t("common.unreachable") } };
  }
  let answer = {};
  try {
    answer = await response.json();
  } catch {
    answer = {};
  }
  return { ok: response.ok, status: response.status, body: answer };
}

function refusalText(answer) {
  const detail = answer.body?.detail;
  if (typeof detail === "string") return detail;
  return answer.status ? t("common.refused_http", { status: String(answer.status) }) : t("common.unreachable");
}

// ---------- the chain ----------

function stageInfo(kind) {
  return store.catalog?.stages.find((s) => s.kind === kind) ?? null;
}

function optionInfo(kind, option) {
  return stageInfo(kind)?.options.find((o) => o.id === option) ?? null;
}

const clone = (value) => JSON.parse(JSON.stringify(value));

function chain() {
  return store.pipelines[0] ?? null;
}

// The chain remembered by the browser, when it still has the shipped chain's shape. A page
// of before lot 5a may have saved two (A and B): only A is kept.
function loadChains() {
  let saved = null;
  try {
    saved = JSON.parse(stored(CHAINS_KEY) || "null");
  } catch {
    saved = null;
  }
  // Only the shape the session accepts is checked here (a saved chain of an older page, or
  // edited by hand, falls back to the shipped one); the session says whether a chain runs.
  const only = (value, keys) =>
    value !== null && typeof value === "object" && !Array.isArray(value) && Object.keys(value).every((k) => keys.includes(k));
  const stageShaped = (s) =>
    only(s, ["id", "kind", "option", "params"]) &&
    typeof s.id === "string" &&
    /^[a-z0-9_]{1,16}$/.test(s.id) &&
    typeof s.kind === "string" &&
    typeof s.option === "string" &&
    (s.params === undefined || (only(s.params, Object.keys(s.params)) && Object.values(s.params).every(Number.isInteger)));
  const shaped = (p) =>
    only(p, ["label_text", "stages"]) &&
    (p.label_text === undefined || (typeof p.label_text === "string" && p.label_text.length >= 1 && p.label_text.length <= 40)) &&
    Array.isArray(p.stages) &&
    p.stages.length >= 1 &&
    p.stages.length <= 12 &&
    p.stages.every(stageShaped);
  // Languages (2/5): a chain saved before names its label `label_fr`; read as `label_text`.
  const renamed = (p) => {
    if (p === null || typeof p !== "object" || !("label_fr" in p) || "label_text" in p) return p;
    const { label_fr: label, ...rest } = p;
    return { label_text: label, ...rest };
  };
  const pipelines = Array.isArray(saved?.pipelines) ? saved.pipelines.slice(0, 1).map(renamed) : [];
  if (!pipelines.length || !pipelines.every(shaped)) return [clone(store.defaultPipeline)];
  if (saved.version === undefined) {
    // Lot 5c-3: saved before the generation ran, its `not_run` was the only option.
    for (const p of pipelines) {
      for (const s of p.stages) if (s.kind === "generation" && s.option === "not_run") s.option = "active";
    }
  }
  return pipelines;
}

function saveChains() {
  keep(CHAINS_KEY, JSON.stringify({ version: CHAINS_VERSION, pipelines: store.pipelines }));
}

function forgetChains() {
  try {
    localStorage.removeItem(CHAINS_KEY);
  } catch {
    // nothing stored
  }
}

function paramInput(stage, param) {
  const label = el("label", "rag-param");
  label.append(el("span", "rag-param-name", param.label_text));
  const input = el("input", "rag-param-input");
  input.type = "number";
  input.min = String(param.min);
  input.max = String(param.max);
  input.step = "1";
  input.value = String(stage.params?.[param.name] ?? param.default);
  input.dataset.stageId = stage.id;
  input.dataset.param = param.name;
  input.title = t("rag.param_range", { min: fmtInt(param.min), max: fmtInt(param.max), unit: param.unit_text }).trim();
  input.addEventListener("change", () => {
    const value = Number(input.value);
    stage.params = { ...(stage.params || {}) };
    if (input.value.trim() !== "" && Number.isInteger(value)) {
      stage.params[param.name] = value;
    } else {
      // A field cleared or not a whole number: the value the chain keeps, shown again.
      input.value = String(stage.params[param.name] ?? param.default);
    }
    saveChains();
    validateChains();
  });
  label.append(input, el("span", "rag-param-unit", param.unit_text));
  return label;
}

function optionSelect(stage, info) {
  const select = el("select", "rag-option");
  select.setAttribute("aria-label", t("rag.option_label", { stage: info.label_text }));
  select.dataset.stageId = stage.id;
  for (const option of info.options) {
    const item = el("option", null, option.available ? option.label_text : `${option.label_text} (${text("unavailable_text")})`);
    item.value = option.id;
    item.disabled = !option.available;
    if (option.reason_text) item.title = option.reason_text;
    select.append(item);
  }
  select.value = stage.option;
  select.addEventListener("change", () => {
    const option = info.options.find((o) => o.id === select.value);
    stage.option = select.value;
    // The option's own settings, at their shipped values.
    stage.params = Object.fromEntries((option?.params ?? []).map((p) => [p.name, p.default]));
    changed();
    document.querySelector(`select.rag-option[data-stage-id="${stage.id}"]`)?.focus();
  });
  return select;
}

// A chain stage's editor, in its line of the sequence (Composer): its option, its settings,
// what a run would meet, and ▲ ▼ Retirer for the retrieval segment.
function stageControls(stage, index) {
  const info = stageInfo(stage.kind);
  const option = optionInfo(stage.kind, stage.option);
  const box = el("div", "rag-seq-controls");
  if (info && info.options.length > 1) box.append(optionSelect(stage, info));
  else box.append(el("span", "rag-chain-option", option?.label_text ?? stage.option));
  for (const param of option?.params ?? []) box.append(paramInput(stage, param));
  if (info?.movable) box.append(moveButtons(index));
  if (option?.note_text) box.append(el("p", "rag-chain-note", option.note_text));
  for (const other of info?.options ?? []) {
    if (!other.available && other.reason_text) {
      box.append(el("p", "rag-chain-unavailable", labelled(other.label_text, other.reason_text)));
    }
  }
  const downloads = el("div", "rag-chain-downloads");
  downloads.dataset.kind = stage.kind;
  fillDownloads(downloads);
  box.append(downloads);
  return box;
}

// ---------- lot 5c-4: a model missing, downloaded from its stage ----------

// The components whose download outcome the stage says: the workshop's models, and the
// brick's (its « declared » options). Taken only during a download this page launched.
// (Built from their parts: a quoted `rag.…` would read as a text key of ui.yaml.)
const DOWNLOAD_COMPONENTS = [
  ...["embedding", "rerank"].map((c) => `rag_lab.${c}`),
  ...["retriever", "reranker"].map((c) => `rag.${c}`),
];

// A stage's « Télécharger » lines, one per option whose files are missing (the session's
// target and label, AD-1), the progress and « Arrêter » in place of the one downloading, and
// the last outcome under them.
function fillDownloads(box) {
  const kind = box.dataset.kind;
  const options = (stageInfo(kind)?.options ?? []).filter((o) => o.download);
  box.replaceChildren();
  for (const option of options) {
    const target = option.download.target;
    const line = el("p", "rag-chain-download");
    line.dataset.target = target;
    line.append(el("span", "rag-chain-download-name", option.label_text));
    const ours = store.download?.target === target;
    line.classList.toggle("is-active", ours);
    if (ours && store.session.state === "download") {
      const progress = el("span", "rag-chain-download-progress", store.session.reason_text || "");
      progress.setAttribute("role", "status");
      const stop = el("button", "rag-button-secondary rag-download-stop", text("download_stop_text"));
      stop.type = "button";
      stop.dataset.target = target;
      stop.addEventListener("click", stopRun);
      line.append(progress, stop);
    } else {
      const button = el("button", "rag-button-secondary rag-download", option.download.label_text);
      button.type = "button";
      button.dataset.target = target;
      button.setAttribute("aria-label", labelled(option.label_text, option.download.label_text));
      const busy = busyReason();
      button.disabled = Boolean(busy || store.download);
      if (busy) button.title = busy;
      button.addEventListener("click", () => downloadModel(kind, target));
      line.append(button);
    }
    box.append(line);
  }
  const notice = store.downloadNotices[kind];
  if (notice) {
    const said = el("p", `rag-chain-download-notice${notice.error ? " is-error" : ""}`, notice.text);
    said.setAttribute("role", "status");
    box.append(said);
  }
  box.hidden = !box.childElementCount;
}

// The download line the keyboard was on ({ target, kind }), found again after its line is
// drawn again: its button (« Télécharger », « Arrêter »), else its stage's option.
let downloadFocus = null;

function noteDownloadFocus() {
  const line = document.activeElement?.closest?.(".rag-chain-download");
  if (line) downloadFocus = { target: line.dataset.target, kind: line.parentElement?.dataset.kind };
}

function restoreDownloadFocus() {
  if (!downloadFocus) return;
  const active = document.activeElement;
  if (active && active !== document.body && active.isConnected) {
    // Elsewhere now (or still there): nothing to give back.
    if (!active.closest(".rag-chain-download")) downloadFocus = null;
    return;
  }
  const line = [...document.querySelectorAll(".rag-chain-download")].find((l) => l.dataset.target === downloadFocus.target);
  const button = line?.querySelector("button:not(:disabled)");
  if (button) button.focus();
  else if (!line) document.querySelector(`#rag-seq .rag-chain-card[data-kind="${downloadFocus.kind}"] select.rag-option`)?.focus();
  else return; // its button disabled for now (the download starting): given back later
  downloadFocus = null;
}

// Every stage's lines drawn again in place (the progress, once a second), the keyboard's
// focus kept on the same target's line.
function renderDownloads() {
  noteDownloadFocus();
  for (const box of document.querySelectorAll(".rag-chain-downloads")) fillDownloads(box);
  restoreDownloadFocus();
}

async function downloadModel(kind, target) {
  noteDownloadFocus();
  store.download = { target, kind };
  delete store.downloadNotices[kind];
  renderDownloads();
  const answer = await post("/api/intentions/download_model", { target });
  if (answer.ok) {
    renderDownloads();
    return;
  }
  // Refused (the room on the disk, the session busy, the files already there): nothing
  // started; the catalog read again (a file copied by hand meanwhile).
  if (store.download?.target === target) store.download = null;
  store.downloadNotices[kind] = { text: refusalText(answer), error: true };
  await reloadCatalog();
}

// The catalog only, read again (a download ended): the options' availability, their reasons
// and their « Télécharger », the chain checked again.
async function reloadCatalog() {
  try {
    const response = await fetch("/api/rag_lab");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const body = await response.json();
    if (body.catalog) store.catalog = body.catalog;
  } catch {
    // the next reload of the page reads it
  }
  noteDownloadFocus();
  redraw();
  restoreDownloadFocus();
  validateChains();
}

// A download's outcome (`effect_applied`, `harness_error` outside a turn), said in the stage
// of the download this page launched; a load failing afterwards is not the stage's.
function downloadOutcome(envelope) {
  if (!store.download || envelope.turn_id || !DOWNLOAD_COMPONENTS.includes(envelope.component)) return;
  const p = envelope.payload;
  let notice = null;
  if (envelope.kind === "harness_error") {
    const cause = p.cause ? t("main.bricks.notice_cause", { cause: p.cause }) : null;
    notice = { text: [p.message_text, cause, p.effect_text].filter(Boolean).join(" "), error: true };
  } else if (p.effect === "model_download") {
    notice = { text: text("download_done_text"), error: false };
  } else if (p.effect === "model_download_stopped") {
    notice = { text: (p.lines ?? []).join(" "), error: false };
  }
  if (!notice) return;
  store.downloadNotices[store.download.kind] = notice;
  renderDownloads();
}

// Increment 4: a stage of the retrieval segment moves by buttons (keyboard included), never
// by drag and drop, and can be removed; the session says whether the chain still runs.
function isMovable(stage) {
  return Boolean(stage && stageInfo(stage.kind)?.movable);
}

function moveButtons(index) {
  const stages = chain().stages;
  const box = el("div", "rag-chain-moves");
  const button = (label, symbol, action, disabled, onClick) => {
    const b = el("button", "rag-move-button", symbol);
    b.type = "button";
    b.setAttribute("aria-label", label);
    b.title = label;
    b.disabled = disabled;
    b.dataset.stageId = stages[index].id;
    b.dataset.action = action;
    b.addEventListener("click", onClick);
    return b;
  };
  const move = (delta) => () => {
    const [stage] = stages.splice(index, 1);
    stages.splice(index + delta, 0, stage);
    changed();
    const action = delta < 0 ? "before" : "after";
    const again = document.querySelector(`.rag-move-button[data-stage-id="${stage.id}"][data-action="${action}"]`);
    (again && !again.disabled ? again : document.querySelector(`#rag-seq [data-stage-id="${stage.id}"] .rag-move-button:not(:disabled)`))?.focus();
  };
  const remove = text("remove_text") || t("rag.remove");
  box.append(
    button(text("move_before_text") || t("rag.move_before"), "▲", "before", !isMovable(stages[index - 1]), move(-1)),
    button(text("move_after_text") || t("rag.move_after"), "▼", "after", !isMovable(stages[index + 1]), move(1)),
    button(remove, remove, "remove", false, () => {
      stages.splice(index, 1);
      changed();
      document.querySelector("#rag-palette-a select")?.focus();
    }),
  );
  return box;
}

function renderPalette() {
  const box = $("rag-palette-a");
  box.replaceChildren();
  const pipeline = chain();
  if (!pipeline || !store.catalog || store.mode !== "compose") return;
  const present = new Set(pipeline.stages.map((s) => s.kind));
  const absent = store.catalog.stages.filter((s) => s.movable && !present.has(s.kind));
  if (!absent.length) return;
  const label = el("label", "rag-palette-label");
  label.append(el("span", null, text("add_text") || t("rag.add")));
  const select = el("select", "rag-palette-select");
  for (const info of absent) {
    const option = el("option", null, info.label_text);
    option.value = info.kind;
    select.append(option);
  }
  label.append(select);
  const add = el("button", "rag-button-secondary rag-palette-add", text("add_button_text") || t("rag.add_button"));
  add.type = "button";
  add.addEventListener("click", () => {
    const info = store.catalog.stages.find((s) => s.kind === select.value);
    const choice = info?.options.find((o) => o.available) ?? info?.options[0];
    if (!info || !choice) return;
    const used = new Set(pipeline.stages.map((s) => s.id));
    let n = pipeline.stages.length + 1;
    while (used.has(`s${n}`)) n += 1;
    const stage = {
      id: `s${n}`,
      kind: info.kind,
      option: choice.id,
      params: Object.fromEntries(choice.params.map((p) => [p.name, p.default])),
    };
    const before = pipeline.stages.findIndex((s) => s.kind === store.catalog.insert_before);
    // A stage that opens the retrieval segment (the query understanding) goes after its anchor.
    const anchor = info.insert_after ? pipeline.stages.findIndex((s) => s.kind === info.insert_after) : -1;
    pipeline.stages.splice(anchor >= 0 ? anchor + 1 : before < 0 ? pipeline.stages.length : before, 0, stage);
    changed();
    document.querySelector("#rag-palette-a select")?.focus();
  });
  box.append(label, add);
}

function changed() {
  saveChains();
  redraw();
  validateChains();
}

// The session's verdict on the chain being edited, shown on the line at fault.
// Asked once the edits pause (a run's fields send several at once): one request, the last.
let validationTimer = null;
function validateChains() {
  clearTimeout(validationTimer);
  validationTimer = setTimeout(askValidation, 200);
}

async function askValidation() {
  const asked = ++store.validating;
  const answer = await post("/api/rag_lab/validate", { pipelines: store.pipelines });
  if (asked !== store.validating) return;
  if (answer.ok) {
    store.refusals = answer.body.refusals ?? [];
  } else if (answer.status === 422) {
    // A chain the session cannot even read: back to the shipped one.
    store.pipelines = [clone(store.defaultPipeline)];
    forgetChains();
    redraw();
    validateChains();
    return;
  } else {
    store.refusals = [{ stage_id: null, reason_text: refusalText(answer) }];
  }
  renderRefusals();
  renderBusy();
}

// The reasons said once to a screen reader, when they change (never at each render).
let announced = "";
function announceRefusals() {
  const said = store.refusals.map((r) => r.reason_text).join(" ");
  if (said === announced) return;
  announced = said;
  $("rag-refusal-live").textContent = said;
}

function renderRefusals() {
  for (const node of document.querySelectorAll(".rag-chain-refusal")) node.remove();
  for (const row of document.querySelectorAll(".rag-chain-card.is-invalid")) row.classList.remove("is-invalid");
  const general = $("rag-chain-refusal-a");
  general.hidden = true;
  general.textContent = "";
  for (const refusal of store.refusals) {
    const row = refusal.stage_id ? document.querySelector(`#rag-seq .rag-chain-card[data-stage-id="${refusal.stage_id}"]`) : null;
    // A line not shown yet (« Dérouler », after the frame shown): said in the general line.
    if (row && !row.classList.contains("is-hidden")) {
      row.classList.add("is-invalid");
      row.querySelector(".rag-seq-head").after(el("p", "rag-chain-refusal", refusal.reason_text));
    } else {
      general.hidden = false;
      general.textContent = [general.textContent, refusal.reason_text].filter(Boolean).join(" ");
    }
  }
  announceRefusals();
  wires?.schedule();
}

// ---------- lot 5b: the ready-made architectures (vues-atelier-rag.md §8) ----------

// V1.2 story 10: the chain's Context reads the whole corpus (long context, CAG): no search.
// V1.2 story 11: and every Context option that searches by itself (agent, tree): no segment.
const corpusOption = (option) =>
  (store.catalog?.searchless_options ?? store.catalog?.corpus_options ?? []).includes(option);
const contextOf = (pipeline) => (pipeline?.stages ?? []).find((s) => s.kind === "context") ?? null;

// The preset whose segment (kind, option, in order) is the chain's retrieval segment, if any;
// V1.2 story 10: a preset that sets the Context also matches on its option.
function currentPreset() {
  const segment = (chain()?.stages ?? []).filter(isMovable);
  const context = contextOf(chain());
  return (
    (store.catalog?.presets ?? []).find(
      (preset) =>
        preset.segment.length === segment.length &&
        preset.segment.every((s, i) => s.kind === segment[i].kind && s.option === segment[i].option) &&
        (preset.replaces_context ? context?.option === preset.context?.option : !corpusOption(context?.option)),
    ) ?? null
  );
}

// Applying a preset replaces the retrieval segment only, its stages at the settings the
// session gives (the shipped ones); the session then says whether the chain runs. A stage of a
// kind already there keeps its id.
function applyPreset(preset) {
  const pipeline = chain();
  if (!pipeline) return;
  const old = pipeline.stages.filter(isMovable);
  const kept = pipeline.stages.filter((s) => !isMovable(s));
  const used = new Set(kept.map((s) => s.id));
  const idOf = (kind) => {
    const same = old.find((s) => s.kind === kind && !used.has(s.id));
    if (same) return same.id;
    let n = 1;
    while (used.has(`s${n}`) || old.some((s) => s.id === `s${n}`)) n += 1;
    return `s${n}`;
  };
  const segment = preset.segment.map((s) => {
    const stage = { id: idOf(s.kind), kind: s.kind, option: s.option, params: clone(s.params ?? {}) };
    used.add(stage.id);
    return stage;
  });
  const before = kept.findIndex((s) => s.kind === store.catalog.insert_before);
  kept.splice(before < 0 ? kept.length : before, 0, ...segment);
  // V1.2 story 10: a preset without an index sets the Context; a search preset gives a chain
  // that read the whole corpus its Context back (the others keep theirs).
  const context = kept.find((s) => s.kind === "context");
  if (context && preset.context && (preset.replaces_context || corpusOption(context.option))) {
    context.option = preset.context.option;
    context.params = clone(preset.context.params ?? {});
  }
  pipeline.stages = kept;
  changed();
  document.querySelector(`#rag-presets .rag-preset[data-preset="${preset.id}"]`)?.focus();
}

function renderPresets() {
  const box = $("rag-presets");
  box.replaceChildren();
  const presets = store.catalog?.presets ?? [];
  box.hidden = store.mode !== "compose" || !presets.length || !chain();
  if (box.hidden) return;
  const title = text("presets_title_text");
  box.setAttribute("aria-label", title);
  box.append(el("span", "rag-presets-label", title));
  const current = currentPreset();
  // V1.2 story 10 (vues.md): one section per family, in the session's order.
  const families = store.catalog.preset_families ?? [];
  const sections = new Map();
  for (const family of families) {
    const section = el("div", "doc-family rag-preset-family");
    section.dataset.family = family.id;
    section.setAttribute("role", "group");
    section.setAttribute("aria-label", family.label_text);
    section.append(el("span", "rag-preset-family-label", family.label_text));
    sections.set(family.id, section);
    box.append(section);
  }
  for (const preset of presets) {
    const target = sections.get(preset.family) ?? box;
    const label = preset.available ? preset.label_text : `${preset.label_text} (${text("unavailable_text")})`;
    const button = el("button", "rag-preset", label);
    button.type = "button";
    button.dataset.preset = preset.id;
    button.classList.toggle("is-unavailable", !preset.available);
    // The explanation, why it would not run, what a run would meet: the tooltip, and the
    // same text described to the keyboard and screen readers (`title` reaches neither).
    const help = [preset.explain_text, preset.reason_text, preset.note_text].filter(Boolean).join("\n");
    button.title = help;
    const described = el("span", "rag-visually-hidden", help);
    described.id = `rag-preset-help-${preset.id}`;
    button.setAttribute("aria-describedby", described.id);
    button.setAttribute("aria-pressed", String(preset.id === current?.id));
    button.addEventListener("click", () => applyPreset(preset));
    target.append(button, described);
  }
}

function resetChains() {
  store.pipelines = [clone(store.defaultPipeline)];
  forgetChains();
  redraw();
  validateChains();
}

// ---------- the three views (lot 5a, vues-atelier-rag.md §3 to §5, §7) ----------

// The sequence of the chain being edited: BUILD's steps, then RUN's own steps (the question,
// its embedding), then the chain's RUN stages in its order. Each entry: its step (from the
// catalog), the chain's stage it shows (or none), that stage's index in the chain.
function sequence() {
  const catalog = store.catalog;
  const stages = chain()?.stages ?? [];
  if (!catalog) return [];
  const of = (kind) => stages.find((s) => s.kind === kind) ?? null;
  const entries = [];
  const push = (step, stage) => entries.push({ step, stage, index: stage ? stages.indexOf(stage) : -1 });
  // V1.2 story 10: a line drawn for some options of its stage only (the CAG's prefix), or
  // never with some Context options (the question's embedding, without any search).
  const context = of("context");
  const drawn = (step) =>
    (!step.stage || of(step.stage)) &&
    (!step.options?.length || step.options.includes(of(step.stage)?.option)) &&
    !(step.hidden_with ?? []).includes(context?.option);
  for (const step of catalog.steps) {
    if (step.phase !== "build" || !drawn(step)) continue;
    push(step, step.stage ? of(step.stage) : null);
  }
  for (const step of catalog.steps) {
    if (step.phase !== "run" || step.own || !drawn(step)) continue;
    push(step, step.stage ? of(step.stage) : null);
  }
  for (const stage of stages) {
    const step = catalog.steps.find((s) => s.own && s.stage === stage.kind);
    if (step && step.phase === "run") push(step, stage);
  }
  return entries;
}

function seqRow(entry, n) {
  const { step, stage, index } = entry;
  const row = el("li", `rag-seq-step is-${step.phase}`);
  row.dataset.step = step.key;
  if (step.stage === "generation") row.classList.add("is-model");
  if (step.own && stage) {
    // The editor's selectors (SPEC.md): the line is the chain's stage card.
    row.classList.add("rag-chain-card");
    row.dataset.kind = stage.kind;
    row.dataset.stageId = stage.id;
  }
  const head = el("button", "rag-seq-head");
  head.type = "button";
  head.append(el("span", "rag-chain-number", String(n)), el("span", "rag-seq-name", step.label_text));
  const pill = el("span", "rag-seq-status");
  pill.hidden = true;
  head.append(pill);
  head.addEventListener("click", () => {
    const focused = document.activeElement === head;
    select(step.key);
    // « Dérouler » draws the lines again: the keyboard's focus back on this line's head.
    if (focused && !head.isConnected) {
      document.querySelector(`#rag-seq .rag-seq-step[data-step="${step.key}"] .rag-seq-head`)?.focus();
    }
  });
  row.append(head, el("p", "rag-seq-line", step.action_text));
  if (store.mode === "compose") {
    if (step.own && stage) row.append(stageControls(stage, index));
    else if (step.key === "embed_query") row.append(el("p", "rag-seq-same", text("same_model_text")));
  }
  return row;
}

function renderPhase(id) {
  const phase = store.catalog.phases.find((p) => p.id === id);
  const band = $(`rag-phase-${id}`);
  band.replaceChildren();
  if (!phase) return;
  band.append(el("span", "rag-phase-tag", phase.tag_text), el("span", null, phase.label_text), el("small", null, phase.help_text));
}

// `shown`: the last step visible (« Dérouler »: the frame shown; the steps after it keep their
// place, invisible, and so does the RUN band before its first step).
function renderSequence(entries, shown) {
  renderPhase("build");
  renderPhase("run");
  const lists = { build: $("rag-seq-build"), run: $("rag-seq-run") };
  lists.build.replaceChildren();
  lists.run.replaceChildren();
  entries.forEach((entry, i) => {
    const row = seqRow(entry, i + 1);
    row.classList.toggle("is-hidden", i > shown);
    lists[entry.step.phase]?.append(row);
  });
  const firstRun = entries.findIndex((e) => e.step.phase === "run");
  $("rag-phase-run").classList.toggle("is-hidden", firstRun >= 0 && shown < firstRun);
  renderPalette();
}

// The tiles visible at the last render: a tile revealed since then arrives (`is-new`).
// `null`: none arrives at the next render (the stepper rebuilt, straight to its frame).
let seen = null;

// A tile's subtitle: the chosen option of its stage (the embedding model, the reranker, the
// store), else its own note.
function subtitle(component) {
  if (component.id === "answer") return answerOf(shownRun()) || component.note_text;
  const stage = component.stage ? chain()?.stages.find((s) => s.kind === component.stage) : null;
  return (stage && optionInfo(stage.kind, stage.option)?.label_text) || component.note_text;
}

// Lot 5c-3: the answer of a run's generation, as it arrives (the `model_delta` of the workshop's
// context), then as its end says it; none when nothing was sent (« Ne pas générer », skipped).
function answerOf(run) {
  const stage = run?.stages.find((s) => s.kind === "generation");
  if (!stage) return "";
  if (stage.ended) return typeof stage.ended.prompt_text === "string" ? stage.ended.output_text : "";
  return stage.status === "running" ? stage.live : "";
}

// The answer tile follows the run between two frames (its subtitle only).
function renderAnswerTile() {
  const sub = document.querySelector('#rag-arch .rag-arch-tile[data-component="answer"] .rag-arch-sub');
  const component = store.catalog?.components.find((c) => c.id === "answer");
  if (!sub || !component) return;
  const said = subtitle(component);
  if (sub.textContent !== said) sub.textContent = said;
  sub.title = said;
}

function renderArchitecture(entries, shown) {
  const box = $("rag-arch-groups");
  box.replaceChildren();
  const componentsOf = (list) => new Set(list.flatMap((e) => e.step.uses.map((u) => u.component)));
  // A tile exists only when a step of the chain calls on it (no Reranker without reranking);
  // in « Dérouler », it shows once a step up to the frame shown has called on it.
  const used = componentsOf(entries);
  const revealed = componentsOf(entries.slice(0, shown + 1));
  const playing = store.mode === "play";
  for (const group of store.catalog.groups) {
    const tiles = store.catalog.components.filter((c) => c.group === group.id && used.has(c.id));
    if (!tiles.length) continue;
    const section = el("section", "rag-arch-group");
    section.dataset.group = group.id;
    section.classList.toggle("is-hidden", !tiles.some((c) => revealed.has(c.id)));
    section.append(el("h4", null, group.label_text));
    const list = el("ul");
    for (const component of tiles) {
      const tile = el("li", "rag-arch-tile");
      tile.dataset.component = component.id;
      if (!revealed.has(component.id)) tile.classList.add("is-hidden");
      else if (playing && seen && !seen.has(component.id)) tile.classList.add("is-new");
      const icon = el("span", "rag-arch-icon", component.icon);
      icon.setAttribute("aria-hidden", "true");
      const sub = el("span", "rag-arch-sub", subtitle(component));
      sub.title = sub.textContent;
      tile.append(icon, el("span", "rag-arch-name", component.label_text), sub);
      const count = downloadCount(component.stage);
      if (count) tile.append(downloadMention(component.stage, count));
      list.append(tile);
    }
    section.append(list);
    // B1: a stage the chain lacks (no tile: the Reranker) with models to download, said at
    // the foot of its group.
    for (const component of store.catalog.components) {
      if (component.group !== group.id || used.has(component.id)) continue;
      const count = downloadCount(component.stage);
      if (count && stageInfo(component.stage)?.movable) section.append(downloadHint(component, count));
    }
    box.append(section);
  }
  seen = revealed;
}

// ---------- B1 (2026-10-05): where « Télécharger » is, said on the architecture ----------

// The models a stage offers to download (the session's figure, AD-1), 0 for none.
function downloadCount(kind) {
  return (kind && stageInfo(kind)?.download_count) || 0;
}

// « 2 modèles à télécharger » on a tile: its click opens the stage's line in Composer.
function downloadMention(kind, count) {
  const button = el("button", "rag-arch-download", t("rag.arch_downloads", { count }));
  button.type = "button";
  button.dataset.stage = kind;
  button.title = t("rag.arch_downloads_title", { stage: stageInfo(kind)?.label_text ?? kind });
  // Two tiles may say the same: the accessible name says whose models.
  const component = store.catalog.components.find((c) => c.stage === kind);
  if (component) button.setAttribute("aria-label", labelled(component.label_text, button.textContent));
  button.addEventListener("click", () => openDownloads(kind));
  return button;
}

// « Reranker : 1 modèle à télécharger ; ajoutez l'étape Reranking… »: its click opens
// Composer, the stage chosen in « Ajouter un composant ».
function downloadHint(component, count) {
  const stage = stageInfo(component.stage)?.label_text ?? component.stage;
  const button = el("button", "rag-arch-download-hint", t("rag.arch_downloads_add", { count, component: component.label_text, stage }));
  button.type = "button";
  button.dataset.stage = component.stage;
  button.title = t("rag.arch_downloads_title", { stage });
  button.addEventListener("click", () => {
    setMode("compose");
    const select = document.querySelector("#rag-palette-a select");
    if (!select) return;
    select.value = component.stage;
    const add = document.querySelector("#rag-palette-a .rag-palette-add");
    add?.scrollIntoView({ block: "nearest" });
    add?.focus();
  });
  return button;
}

// Composer, the stage's own line selected, its first « Télécharger » focused.
function openDownloads(kind) {
  const step = store.catalog?.steps.find((s) => s.own && s.stage === kind);
  setMode("compose");
  if (!step) return;
  select(step.key);
  const row = document.querySelector(`#rag-seq .rag-seq-step[data-step="${step.key}"]`);
  // Its select when every button is disabled (the session busy, a download going on).
  const button =
    row?.querySelector(".rag-download:not(:disabled)") ?? row?.querySelector("select.rag-option") ?? row?.querySelector(".rag-seq-head");
  row?.scrollIntoView({ block: "nearest" });
  button?.focus();
}

// ---------- the run, as the sequence reads it ----------

// A stage's settings, those left out at their shipped value: a run and the chain compared.
function settingsOf(kind, option, params) {
  const values = Object.fromEntries((optionInfo(kind, option)?.params ?? []).map((p) => [p.name, p.default]));
  Object.assign(values, params ?? {});
  return JSON.stringify(Object.keys(values).sort().map((name) => [name, values[name]]));
}

// The run « Dérouler » shows: the last one, when it ran the chain being edited (its stages,
// options and settings, in order). A chain edited since then gets its guided tour instead.
function shownRun() {
  return store.mode === "play" ? chainRun() : null;
}

// The last run, when it ran the chain being edited; else none.
function chainRun() {
  if (!store.run) return null;
  const stages = chain()?.stages ?? [];
  if (store.run.stages.length !== stages.length) return null;
  const same = store.run.stages.every((s, i) => {
    const mine = stages[i];
    return (
      s.stage_id === mine.id &&
      s.kind === mine.kind &&
      s.option === mine.option &&
      settingsOf(s.kind, s.option, s.params) === settingsOf(mine.kind, mine.option, mine.params)
    );
  });
  return same ? store.run : null;
}

// What a step shows of the run: its stage, or (B2) the part of it the step names, waiting
// until the part's first event (a run ended without it, one of before B2: not run).
function runStage(step) {
  if (!step.stage || !shownRun()) return null;
  const stage = store.run.stages.find((s) => s.kind === step.stage) ?? null;
  if (!stage || !step.part) return stage;
  const status = store.run.ended ? "skipped" : "waiting";
  return stage.parts?.[step.part] ?? { kind: step.key, status, progress: null, ended: null };
}

// A line with figures of its own (status line with its duration, warning, duration and
// memory in the focus): its stage's own line, or (B2) a part of it run apart.
const ownFigures = (step) => Boolean(step.own || step.part);

// The pill of a line in « Dérouler », once a run is known: a stage's own status and duration;
// Documents and the question's Embedding take their stage's status without a duration.
function pillOf(step) {
  if (!shownRun()) return null;
  if (step.key === "question") return { status: "ok", said: text("question_received_text") };
  const stage = runStage(step);
  if (!stage) return null;
  return { status: stage.status, said: stepStatus(step, stage) };
}

// A step's status: its stage's own line (progress, duration), or only its status for a step
// that reads a stage (its duration is the stage's, not its own).
function stepStatus(step, stage) {
  return ownFigures(step) ? statusLine(stage) : text(STATUS_KEYS[stage.status] ?? "") || stage.status;
}

function renderPills() {
  for (const row of document.querySelectorAll("#rag-seq .rag-seq-step")) {
    const step = store.catalog?.steps.find((s) => s.key === row.dataset.step);
    const pill = row.querySelector(".rag-seq-status");
    const shown = step ? pillOf(step) : null;
    pill.hidden = !shown;
    pill.textContent = shown?.said ?? "";
    if (shown) row.dataset.run = shown.status;
    else delete row.dataset.run;
  }
}

// ---------- the focus ----------

function uses(step) {
  const box = el("div", "rag-focus-uses");
  box.append(el("span", "rag-view-label", text("uses_title_text")));
  const how = { reads: text("reads_text"), writes: text("writes_text"), calls: text("calls_text") };
  for (const use of step.uses) {
    const component = store.catalog.components.find((c) => c.id === use.component);
    if (!component) continue;
    const tag = el("span", "rag-tag");
    const icon = el("span", "rag-tag-icon", component.icon);
    icon.setAttribute("aria-hidden", "true");
    tag.append(icon, ` ${component.label_text} · ${how[use.how] ?? use.how}`);
    tag.dataset.component = component.id;
    tag.dataset.how = use.how;
    box.append(tag);
  }
  return box;
}

// Lot 5c-3: the prompt the generation sent, exactly, folded (its state kept across renders).
function promptBlock(prompt) {
  const details = el("details", "rag-prompt");
  details.open = store.promptOpen;
  details.addEventListener("toggle", () => {
    store.promptOpen = details.open;
  });
  details.append(el("summary", null, text("prompt_sent_text")), el("pre", "rag-focus-pre", prompt));
  return details;
}

// Lot 5c-3: the model's answer (`waiting`: before its first token).
function answerBlock(answer, waiting = false) {
  const box = el("div", "rag-answer");
  box.append(el("span", "rag-view-label", text("answer_title_text")));
  box.append(el("p", `rag-answer-text${waiting ? " is-waiting" : ""}`, answer));
  return box;
}

function focusIo(rows) {
  const dl = el("dl", "rag-focus-io");
  for (const [label, value, className] of rows) {
    if (value) dl.append(el("dt", null, label), el("dd", className ?? null, value));
  }
  return dl;
}

// V1.2 story 5 (CAP-3): the queries the query understanding produced, one line each.
function queriesList(queries) {
  const box = el("div", "rag-focus-queries");
  box.append(el("p", "rag-focus-queries-title", text("queries_text")));
  const list = el("ol", "rag-focus-queries-list");
  for (const query of queries) list.append(el("li", null, query));
  box.append(list);
  return box;
}

// What the step received, produced and cost in the last run (« Dérouler » only, §5, §7).
function focusRun(box, step) {
  const run = shownRun();
  if (!run) {
    // Composer, the last run being this chain's: its figures are one click away.
    const hint = store.mode === "compose" && chainRun() ? "focus_play_hint_text" : "focus_no_run_text";
    box.append(el("p", "rag-note rag-focus-hint", text(hint)));
    return;
  }
  if (step.key === "question") {
    box.append(focusIo([[text("question_label_text"), quote(run.question)]]));
    return;
  }
  const stage = runStage(step);
  if (!stage) {
    box.append(el("p", "rag-note rag-focus-hint", text("focus_no_run_text")));
    return;
  }
  box.append(el("p", "rag-focus-status", stepStatus(step, stage)));
  const ended = stage.ended;
  if (!ended && step.stage === "generation" && stage.status === "running") {
    // Lot 5c-3: the answer as the model writes it.
    // Before its first word: the model reads the prompt, or reasons.
    const waiting = stage.reasoning ? "answer_reasoning_text" : "answer_waiting_text";
    box.append(stage.live ? answerBlock(stage.live) : answerBlock(text(waiting), true));
  }
  if (!ended) return;
  if (ended.error_text) box.append(el("p", "rag-stage-error", ended.error_text));
  // Lot 5c-1: what the stage met without failing (chunks truncated), on its own lines only.
  if (ended.warning_text && ownFigures(step)) box.append(el("p", "rag-stage-warning", ended.warning_text));
  if (step.key === "documents") {
    box.append(focusIo([[text("input_text"), ended.input_text]]));
    return;
  }
  if (step.key === "embed_query") {
    box.append(focusIo([[text("input_text"), quote(run.question)]]));
  } else if (step.stage === "generation" && typeof ended.prompt_text === "string") {
    // Lot 5c-3: run by the active model: what it was sent, then its answer.
    box.append(focusIo([[text("input_text"), ended.input_text]]), promptBlock(ended.prompt_text));
    if (ended.output_text) box.append(answerBlock(ended.output_text));
  } else if (["context", "generation"].includes(step.stage)) {
    box.append(focusIo([[text("input_text"), ended.input_text]]));
    if (ended.output_text) box.append(el("pre", "rag-focus-pre", ended.output_text));
  } else {
    box.append(
      focusIo([
        [text("input_text"), ended.input_text],
        [text("output_text"), ended.output_text],
      ]),
    );
  }
  if (ended.facts?.length) {
    const facts = el("ul", "rag-focus-facts");
    for (const fact of ended.facts) facts.append(el("li", null, labelled(fact.label_text, fact.value_text)));
    box.append(facts);
  }
  if (ended.queries?.length) box.append(queriesList(ended.queries));
  if (step.key === "chunking" && ended.chunks?.length) box.append(chunksList(ended));
  if (step.key === "chunking" && stage.option === "contextual") box.append(contextControls());
  if (step.stage === "context" && ended.budget) box.append(budgetGauge(ended.budget));
  // V1.2 story 10: the whole corpus against the window, and the CAG's cache (the run's).
  if (step.stage === "context" && typeof ended.window === "number") box.append(windowGauge(ended));
  if (step.key === "cache_prefix" || (step.stage === "context" && stage.option === "cached_corpus")) {
    box.append(cacheBlock(runCache(ended)));
  }
  if (step.key !== "embed_query" && ended.items?.length) box.append(itemsTable(ended.items));
  if (step.stage === "context" && ended.dropped?.length) box.append(droppedList(ended.dropped));
  if (step.stage === "context" && ended.prompt_parts?.length) box.append(promptParts(ended));
  if (ownFigures(step) && ["ok", "error", "cancelled"].includes(stage.status)) {
    const foot = el("p", "rag-stage-figures");
    foot.append(el("span", "rag-stage-duration", labelled(text("duration_text"), `${fmtInt(ended.duration_ms)} ms`)));
    if (ended.memory_text) foot.append(el("span", "rag-stage-memory", labelled(text("memory_text"), ended.memory_text)));
    box.append(foot);
  }
}

function renderFocus(entries) {
  const box = $("rag-focus");
  box.replaceChildren();
  const i = entries.findIndex((e) => e.step.key === store.current);
  const step = i >= 0 ? entries[i].step : null;
  box.classList.toggle("is-run", step?.phase === "run");
  box.dataset.step = step?.key ?? "";
  if (!step) {
    box.append(el("p", "rag-focus-phase", text("focus_title_text")), el("p", "rag-focus-explain", text("focus_empty_text")));
    return;
  }
  const phase = store.catalog.phases.find((p) => p.id === step.phase);
  box.append(
    el(
      "p",
      "rag-focus-phase",
      text("focus_position_text", { phase: phase ? `${phase.tag_text} · ${phase.label_text}` : step.phase, n: i + 1, total: entries.length }),
    ),
  );
  const title = el("h3");
  title.append(el("span", "rag-chain-number", String(i + 1)), el("span", "rag-focus-name", step.label_text));
  box.append(title, el("p", "rag-focus-action", step.action_text));
  if (step.note_text) box.append(el("p", "rag-focus-note", step.note_text));
  if (step.explain_text) box.append(el("p", "rag-focus-explain", step.explain_text));
  if (step.uses.length) box.append(uses(step));
  focusRun(box, step);
  // V1.2 story 11: what a module adds to a step's focus (rag-agentic.js: the tree card).
  for (const extra of focusExtras) extra(box, step, runStage(step));
}

// V1.2 story 11: the hooks a module adds to the focus, called with the box, the step and the
// run's stage of it (`null` without a run).
const focusExtras = [];
export function registerFocus(hook) {
  focusExtras.push(hook);
  if (store.mounted) renderCurrent();
}

// ---------- the wires: from the step shown to the components it calls on ----------

let wires = null;

function drawWires({ box }) {
  const defs = svgEl("defs");
  const head = svgEl("marker", {
    id: "rag-arrow",
    viewBox: "0 0 10 10",
    refX: 9,
    refY: 5,
    markerWidth: 6,
    markerHeight: 6,
    orient: "auto-start-reverse",
  });
  head.append(svgEl("path", { d: "M0 0 L10 5 L0 10 z", class: "rag-arrow-head" }));
  defs.append(head);
  const parts = [defs];
  const step = store.catalog?.steps.find((s) => s.key === store.current);
  const row = step && document.querySelector(`#rag-seq .rag-seq-step[data-step="${step.key}"] .rag-seq-head`);
  if (!row) return parts;
  const from = box(row);
  const flowing = store.mode === "play" && runStage(step)?.status === "running";
  step.uses.forEach((use, i) => {
    const tile = document.querySelector(`#rag-arch .rag-arch-tile[data-component="${use.component}"]`);
    if (!tile) return;
    const to = box(tile);
    const x1 = from.r + 2;
    const y1 = from.cy + (i - (step.uses.length - 1) / 2) * 8;
    const x2 = to.l - 2;
    const y2 = to.cy;
    const dx = Math.max(30, (x2 - x1) / 2);
    // Read: from the component to the step; written or called: from the step to it.
    const d =
      use.how === "reads"
        ? `M${x2} ${y2} C${x2 - dx} ${y2}, ${x1 + dx} ${y1}, ${x1 + 6} ${y1}`
        : `M${x1} ${y1} C${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2 - 4} ${y2}`;
    parts.push(wire(d, "diagram-path"));
    const core = wire(d, `diagram-path-core${flowing ? " is-flow" : ""}`);
    core.setAttribute("marker-end", "url(#rag-arrow)");
    core.dataset.component = use.component;
    parts.push(core);
  });
  return parts;
}

// The step shown: its line selected (Composer) or lit with its components (Dérouler), its
// focus, its wires.
function renderCurrent(entries = sequence()) {
  if (store.current && !entries.some((e) => e.step.key === store.current)) store.current = null;
  const views = $("rag-views");
  let lit = null;
  for (const row of views.querySelectorAll(".rag-seq-step")) {
    const on = row.dataset.step === store.current;
    row.classList.toggle("is-selected", on && store.mode === "compose");
    row.querySelector(".rag-seq-head").setAttribute("aria-pressed", String(on));
    if (on) lit = row;
  }
  const step = store.catalog?.steps.find((s) => s.key === store.current);
  const nodes = [];
  if (store.mode === "play" && lit && step) {
    nodes.push(lit);
    for (const use of step.uses) {
      const tile = views.querySelector(`.rag-arch-tile[data-component="${use.component}"]`);
      if (tile) nodes.push(tile);
    }
  }
  light(views, nodes);
  renderFocus(entries);
  wires?.schedule();
}

function select(key) {
  if (store.mode === "play" && stepper) {
    // « Dérouler »: the line's frame (vues-atelier-rag.md §3).
    const i = stepper.frames.indexOf(key);
    if (i >= 0) stepper.show(i);
    return;
  }
  store.current = key;
  renderCurrent();
}

function renderModes() {
  $("rag-views").dataset.mode = store.mode;
  for (const button of document.querySelectorAll("#rag-modes [data-mode]")) {
    button.setAttribute("aria-pressed", String(button.dataset.mode === store.mode));
  }
  $("rag-reset-chain").hidden = store.mode !== "compose";
  $("rag-stepper").hidden = store.mode !== "play";
}

function setMode(mode) {
  if (!MODES.includes(mode) || mode === store.mode) return;
  store.mode = mode;
  keep(MODE_KEY, mode);
  if (mode === "compose") store.current = null; // no step selected (§7)
  redraw({ restart: true });
}

// ---------- « Dérouler »: the stepper (lot 5a-2, vues-atelier-rag.md §6) ----------

let stepper = null;
let quiet = false; // the stepper being rebuilt: one render at the end, not one per frame

// The frames the stepper should hold, a step's key each: every step of the sequence for the
// guided tour; with a run, the steps up to the last one the run reached (a stage with an
// event). The steps that read a stage (Documents, the question and its Embedding) come with
// the next step of their own: the question is embedded during `embedding`, but the sequence
// shows it just before the retrieval.
function playFrames(entries) {
  const run = shownRun();
  if (!run) return entries.map((e) => e.step.key);
  const reached = new Set(run.stages.filter((s) => s.status !== "waiting").map((s) => s.stage_id));
  // B2: a part run apart (BM25's index, at BUILD) is reached on its own first event.
  const partReached = (e) => {
    const stage = run.stages.find((s) => s.stage_id === e.stage.id);
    return Boolean(stage?.parts?.[e.step.part] && stage.parts[e.step.part].status !== "waiting");
  };
  let last = -1;
  entries.forEach((e, i) => {
    if (!e.stage) return;
    if (e.step.part ? partReached(e) : e.step.own && reached.has(e.stage.id)) last = i;
  });
  return entries.slice(0, last + 1).map((e) => e.step.key);
}

// Where an ended run lands: the first step in error (or stopped), else the last frame.
function landing(keys = stepper?.frames ?? []) {
  const steps = store.catalog?.steps ?? [];
  const failed = keys.findIndex((key) => {
    const step = steps.find((s) => s.key === key);
    return Boolean(step && ownFigures(step)) && ["error", "cancelled"].includes(runStage(step)?.status);
  });
  return failed >= 0 ? failed : keys.length - 1;
}

// The stepper brought to the frames the page should show: the missing ones pushed (live, the
// last one shown), else rebuilt (`restart`, or a sequence that changed): `clear()`, every frame
// pushed, then image 1 for the tour, the landing frame for an ended run, the live one for a
// run going on. True when it rendered the views.
function syncFrames({ restart = false } = {}) {
  if (store.mode !== "play" || !stepper || !store.catalog || !chain()) return false;
  const keys = playFrames(sequence());
  const have = stepper.frames;
  const prefix = have.length <= keys.length && have.every((key, i) => key === keys[i]);
  if (!restart && prefix) {
    if (have.length === keys.length) return false;
    const live = stepper.live;
    for (const key of keys.slice(have.length)) stepper.push(key);
    return live;
  }
  quiet = true;
  stepper.clear();
  for (const key of keys) stepper.push(key);
  quiet = false;
  const run = shownRun();
  store.current = null;
  seen = null;
  if (!keys.length) {
    renderViews();
    return true;
  }
  if (!run) stepper.show(0);
  else if (run.ended) stepper.show(landing(keys));
  else stepper.follow();
  return true;
}

// A frame shown (◀, ▶, a line clicked, a frame pushed live): its step lit, the views drawn.
function showFrame(key) {
  if (quiet) return;
  store.current = key ?? null;
  renderViews();
}

function renderLegend() {
  const legend = $("rag-legend");
  if (store.mode !== "play" || !stepper) {
    legend.textContent = "";
    return;
  }
  const run = shownRun();
  // « Suivre le direct » means nothing in the guided tour: shown with a run only.
  stepper.element.querySelector(".diagram-step-live").hidden = !run;
  let key = "legend_tour_text";
  if (run && !run.ended) key = stepper.live ? "legend_live_text" : "legend_replay_text";
  else if (run) key = stepper.index === landing() ? "legend_done_text" : "legend_replay_text";
  legend.textContent = text(key);
}

// The views drawn again, the stepper first brought up to date in « Dérouler ».
function redraw(options) {
  if (store.mode === "play" && syncFrames(options)) return;
  renderViews();
}

function renderViews() {
  if (!store.catalog || !chain()) return;
  const entries = sequence();
  // « Composer »: everything visible; « Dérouler »: up to the frame shown.
  const shown = store.mode === "play" ? (stepper?.index ?? -1) : entries.length - 1;
  renderModes();
  renderPresets();
  renderSequence(entries, shown);
  renderArchitecture(entries, shown);
  renderPills();
  renderCurrent(entries);
  renderRefusals();
  renderLegend();
}

// ---------- the run, projected from its events ----------

function stageOf(envelope) {
  const p = envelope.payload;
  if (!store.run || store.run.runId !== p.run_id) return null;
  return store.run.stages.find((s) => s.stage_id === p.stage_id) ?? null;
}

// B2: what an event updates: its stage, or the part of it it names (`part`, BM25's index),
// kept apart so that the stage's own status is not touched.
function partOf(envelope) {
  const stage = stageOf(envelope);
  const part = envelope.payload.part;
  if (!stage || !part) return stage;
  stage.parts[part] ??= { kind: envelope.payload.kind, status: "waiting", progress: null, ended: null };
  return stage.parts[part];
}

function applyEnvelope(envelope) {
  store.lastSeq = Math.max(store.lastSeq, envelope.seq);
  // Story 9 (CAP-3, CAP-7, CAP-9): the bar's « Dépense » and « Journal », live, in O(1).
  feedBar(envelope);
  const p = envelope.payload;
  if (isUpdateEvent(envelope)) {
    applyUpdateEnvelope(envelope);
    return;
  }
  if (isRebuildEvent(envelope)) {
    applyRebuildEnvelope(envelope);
    return;
  }
  switch (envelope.kind) {
    case "session_state": {
      const was = store.session.state;
      store.session = { state: p.state, reason_text: p.reason_text };
      if (p.state === "idle" && closeStaleRun()) renderRun();
      renderBusy();
      // Lot 5c-4: a download ended (this page's or another's): the catalog read again.
      // V1.2 story 10: a model (re)loaded, its window changed: the options' reasons too.
      if (was === "download" && p.state !== "download") {
        store.download = null;
        reloadCatalog();
      } else if (was === "model_load" && p.state !== "model_load") {
        reloadCatalog();
      } else {
        renderDownloads();
      }
      return;
    }
    case "effect_applied":
    case "harness_error":
      downloadOutcome(envelope);
      return;
    case "context_window_state": {
      // V1.2 story 10: the long context and the CAG need a window: read again on a change.
      const key = `${p.configured}/${p.window}/${p.model_label ?? ""}`;
      if (store.windowSeen !== undefined && store.windowSeen !== key) reloadCatalog();
      store.windowSeen = key;
      return;
    }
    case "rag_lab_run_started":
      store.run = {
        runId: p.run_id,
        question: p.question,
        startedAt: envelope.ts,
        ended: null,
        // B2: `parts`, a stage's parts run apart (BM25's index, at BUILD), by name.
        stages: p.stages.map((s) => ({ ...s, status: "waiting", progress: null, ended: null, live: "", reasoning: false, parts: {} })),
      };
      store.costs = { build: null, query: null }; // V1.2 story 3: never the previous run's figures
      break;
    case "rag_lab_stage_started": {
      const stage = partOf(envelope);
      if (stage) stage.status = "running";
      break;
    }
    case "rag_lab_stage_progress": {
      const stage = partOf(envelope);
      if (stage) stage.progress = { done: p.done, total: p.total };
      break;
    }
    case "rag_lab_stage_ended": {
      const stage = partOf(envelope);
      if (stage) {
        stage.status = p.status;
        stage.ended = p;
      }
      break;
    }
    case "model_delta": {
      // Lot 5c-3: the generation's answer as it arrives (AD-1: the session's text, never
      // computed here); its reasoning's text is not shown, only that it is under way. A turn's
      // deltas are not the workshop's.
      if (envelope.context_id !== "rag_lab" || !["text", "reasoning"].includes(p.channel)) return;
      const stage = store.run?.stages.find((s) => s.kind === "generation" && s.status === "running");
      if (!stage) return;
      if (p.channel === "text") stage.live += p.text;
      else if (stage.reasoning) return; // already said: nothing to draw again
      else stage.reasoning = true;
      break;
    }
    case "rag_lab_run_ended":
      if (store.run && store.run.runId === p.run_id) {
        store.run.ended = p;
        store.land = true;
        keepRunCosts(p.cost_summary);
      }
      break;
    default:
      return;
  }
  if (store.replaying) return; // `last_run` read again: drawn once, at its end
  renderRun();
  renderCosts();
  renderBusy();
  everyTab("render");
}

// A run whose end never came (WaveStack failed between two events) while the session is
// back in `idle`: said ended in error, never left « en cours ».
function closeStaleRun() {
  const run = store.run;
  if (!run || run.ended) return false;
  run.ended = { status: "error", duration_ms: null };
  for (const stage of run.stages) {
    if (!stage.ended) stage.status = "skipped";
    // B2: a part run apart (BM25's index) never stays « en cours » either.
    for (const part of Object.values(stage.parts ?? {})) if (!part.ended) part.status = "skipped";
  }
  return true;
}

const STATUS_KEYS = {
  waiting: "status.waiting_text",
  running: "status.running_text",
  ok: "status.ok_text",
  error: "status.error_text",
  skipped: "status.skipped_text",
  cancelled: "status.cancelled_text",
  not_run: "status.not_run_text",
};

function statusLine(stage) {
  const label = text(STATUS_KEYS[stage.status] ?? "") || stage.status;
  if (stage.status === "running" && stage.progress) {
    const { done, total } = stage.progress;
    // Lot 5c-3: the generation counts tokens produced against the reserve.
    const said = stage.kind === "generation" ? text("progress_tokens_text", { done: fmtInt(done), total: fmtInt(total) }) : `${fmtInt(done)} / ${fmtInt(total)}`;
    return `${label} · ${said}`;
  }
  if (stage.ended && ["ok", "error", "cancelled"].includes(stage.status)) {
    return `${label} · ${fmtInt(stage.ended.duration_ms)} ms`;
  }
  return label;
}

function itemsTable(items) {
  const table = el("table", "rag-items");
  const head = el("tr");
  for (const key of ["rank_text", "before_text", "document_text", "score_text"]) {
    head.append(el("th", null, text(`columns.${key}`)));
  }
  // V1.2 story 7 (CAP-5): the context's passages also say whether they are whole or cut, where
  // they stand in the context and what they weigh.
  const withState = items.some((item) => item.state);
  if (withState) head.append(el("th", null, t("rag.col_state")));
  const thead = el("thead");
  thead.append(head);
  const body = el("tbody");
  for (const item of items) {
    const row = el("tr");
    row.dataset.chunkId = String(item.chunk_id);
    row.append(el("td", "rag-num", fmtInt(item.rank)));
    const before = item.before === null || item.before === undefined ? "—" : fmtInt(item.before);
    const moved = typeof item.before === "number" && item.before !== item.rank;
    const beforeCell = el("td", "rag-num", before);
    if (moved) beforeCell.classList.add(item.before > item.rank ? "is-up" : "is-down");
    row.append(beforeCell);
    const doc = el("td", "rag-doc");
    doc.append(el("span", "rag-doc-title", item.title_text));
    if (item.sources?.length) {
      // Where the excerpt stood in each list before (the fusion: both searches).
      const said = item.sources.map((src) =>
        labelled(src.label_text, `${fmtRank(src.rank)}${typeof src.score === "number" ? ` (${fmtScore(src.score)})` : ""}`),
      );
      doc.append(el("span", "rag-doc-sources", said.join(" · ")));
    }
    doc.append(el("span", "rag-doc-text", item.text));
    row.append(doc);
    row.append(el("td", "rag-num", fmtScore(item.score)));
    if (withState) row.append(passageState(item));
    body.append(row);
  }
  table.append(thead, body);
  return table;
}

function stageCard(stage, index) {
  const card = el("article", "rag-stage-card");
  card.dataset.kind = stage.kind;
  card.dataset.status = stage.status;
  card.dataset.stageId = stage.stage_id;
  if (stage.kind === "generation") card.classList.add("is-model");
  const head = el("header", "rag-stage-head");
  const title = el("h3", "rag-stage-title");
  title.append(el("span", "rag-chain-number", String(index + 1)), el("span", null, stage.label_text));
  head.append(title);
  head.append(el("span", "rag-stage-status", statusLine(stage)));
  card.append(head);
  card.append(el("p", "rag-stage-option", stage.option_label_text));
  const ended = stage.ended;
  if (!ended) return card;
  if (ended.error_text) card.append(el("p", "rag-stage-error", ended.error_text));
  if (ended.warning_text) card.append(el("p", "rag-stage-warning", ended.warning_text));
  if (ended.borrowed) card.append(el("p", "rag-stage-borrowed", text("borrowed_text")));
  const dl = el("dl", "rag-stage-io");
  if (ended.input_text) dl.append(el("dt", null, text("input_text")), el("dd", "rag-stage-input", ended.input_text));
  if (ended.output_text) dl.append(el("dt", null, text("output_text")), el("dd", "rag-stage-output", ended.output_text));
  if (dl.childElementCount) card.append(dl);
  if (typeof ended.prompt_text === "string") {
    const prompt = el("details", "rag-prompt");
    prompt.append(el("summary", null, text("prompt_sent_text")), el("pre", "rag-focus-pre", ended.prompt_text));
    card.append(prompt);
  }
  if (ended.facts.length) {
    const facts = el("dl", "rag-stage-facts");
    for (const fact of ended.facts) facts.append(el("dt", null, fact.label_text), el("dd", null, fact.value_text));
    card.append(facts);
  }
  if (ended.items.length) card.append(itemsTable(ended.items));
  if (ended.memory_text || ["ok", "error", "cancelled"].includes(stage.status)) {
    const foot = el("p", "rag-stage-figures");
    foot.append(el("span", "rag-stage-duration", labelled(text("duration_text"), `${fmtInt(ended.duration_ms)} ms`)));
    if (ended.memory_text) foot.append(el("span", "rag-stage-memory", labelled(text("memory_text"), ended.memory_text)));
    card.append(foot);
  }
  return card;
}

// Every step's detail (the former section 3), folded under the views: one card per stage of
// the run's chain.
function renderResults() {
  const box = $("rag-results");
  box.replaceChildren();
  const run = store.run;
  $("rag-results-empty").hidden = Boolean(run);
  const summary = $("rag-run-summary");
  summary.hidden = !run;
  if (!run) return;
  const status = run.ended ? text(STATUS_KEYS[run.ended.status === "ok" ? "ok" : run.ended.status]) : text("status.running_text");
  summary.textContent = `${quote(run.question)} · ${status}${typeof run.ended?.duration_ms === "number" ? ` · ${fmtInt(run.ended.duration_ms)} ms` : ""}`;
  const column = el("section", "rag-lane");
  run.stages.forEach((stage, index) => column.append(stageCard(stage, index)));
  box.append(column);
}

// An event of the run: the details, then « Dérouler »: a frame per step reached (live), the
// landing frame once it ended, the pills, the focus and the wires of the step shown.
function renderRun() {
  renderResults();
  syncFrames();
  if (store.land && store.mode === "play" && stepper && shownRun()?.ended) {
    const i = landing();
    if (stepper.live && i >= 0 && i !== stepper.index) stepper.show(i);
  }
  store.land = false;
  renderPills();
  renderAnswerTile();
  renderCurrent();
  renderLegend();
}

// ---------- V1.2 story 3 (CAP-8): the costs in three times and the work copy ----------

const isUpdateEvent = (envelope) => String(envelope.payload?.run_id ?? "").startsWith("upd");

// An update run's events (`upd{n}`): its label while it runs, its `update` sum when it ends.
function applyUpdateEnvelope(envelope) {
  const p = envelope.payload;
  if (envelope.kind === "rag_lab_run_started") {
    store.update = { runId: p.run_id, label: p.question, ended: null, summary: null };
  } else if (envelope.kind === "rag_lab_run_ended" && store.update?.runId === p.run_id) {
    store.update.ended = p;
    store.update.summary = (p.cost_summary ?? []).find((s) => s.phase === "update") ?? null;
    if (!store.replaying) reloadCopy();
  } else {
    return;
  }
  if (!store.replaying) renderCosts();
}

// A run's build and query sums, for the cards: this run's only (a time it did not reach stays empty).
function keepRunCosts(summary) {
  for (const phase of ["build", "query"]) {
    store.costs[phase] = (summary ?? []).find((s) => s.phase === phase) ?? null;
  }
}

const fmtSig = (x) => numberFormat().format(Number(x.toPrecision(3)));
const fmtRange = (low, high) => (low === high || high === null ? fmtSig(low) : `${fmtSig(low)}–${fmtSig(high)}`);

function costRow(card, label, value) {
  const row = el("div", "rag-cost-row");
  row.append(el("dt", "", label), el("dd", "number", value));
  card.append(row);
}

function costFigures(summary) {
  const dl = el("dl", "rag-cost-figures");
  const none = text("costs.not_measured_text");
  costRow(dl, text("costs.tokens_text"), typeof summary.tokens === "number" ? fmtInt(summary.tokens) : none);
  costRow(dl, text("costs.duration_text"), typeof summary.duration_ms === "number" ? `${fmtInt(summary.duration_ms)} ms` : none);
  const usd = summary.usd === null ? none : summary.usd === 0 ? `0 $ (${text("costs.local_free_text")})` : `${fmtSig(summary.usd)} $`;
  costRow(dl, text("costs.usd_text"), usd);
  const wh = summary.energy_wh_min === null ? none : `${fmtRange(summary.energy_wh_min, summary.energy_wh_max)} Wh`;
  costRow(dl, text("costs.energy_text"), wh);
  const g = summary.gco2e_min === null ? none : `${fmtRange(summary.gco2e_min, summary.gco2e_max)} g`;
  costRow(dl, text("costs.gco2e_text"), g);
  return dl;
}

function costCard(phase) {
  const card = el("article", `rag-cost-card is-${phase}`);
  card.dataset.phase = phase;
  card.append(el("h4", "rag-cost-title", text(`costs.${phase}_text`)), el("p", "rag-note", text(`costs.${phase}_help_text`)));
  const summary = phase === "update" ? store.update?.summary : store.costs[phase];
  if (!summary) {
    const running = phase === "update" && store.update && !store.update.ended;
    card.append(el("p", "rag-note rag-cost-empty", running ? text("costs.update_running_text") : text(`costs.${phase}_empty_text`)));
    return card;
  }
  if (phase === "update" && store.update?.label) card.append(el("p", "rag-cost-op", `${text("costs.update_of_text")} : ${store.update.label}`));
  card.append(costFigures(summary));
  if (summary.measured_at_build) card.append(el("span", "rag-cost-badge is-build", text("costs.measured_at_build_text")));
  if (summary.partial) card.append(el("p", "rag-note rag-cost-partial", text("costs.partial_text")));
  if (summary.note_text) card.append(el("p", "rag-note rag-cost-note", summary.note_text));
  return card;
}

function renderCosts() {
  const box = $("rag-cost-cards");
  if (!box || !store.content) return;
  box.replaceChildren(...["build", "update", "query"].map(costCard));
}

// The work copy of the corpus: where it lives, what it changes, the three buttons.
function renderCopy() {
  const info = $("rag-copy-info");
  const copy = store.workCopy;
  if (!info || !copy) return;
  const changed = copy.added.length + copy.appended.length + copy.deleted.length;
  info.textContent = `${text("costs.copy_help_text", { path: copy.path })} ${
    changed
      ? text("costs.copy_changed_text", { added: copy.added.length, modified: copy.appended.length, deleted: copy.deleted.length })
      : text("costs.copy_clean_text")
  }`;
  const select = $("rag-copy-doc");
  const kept = select.value;
  select.replaceChildren(...copy.documents.map((d) => Object.assign(el("option", "", `${d.title_text} (${d.id})`), { value: d.id })));
  if (copy.documents.some((d) => d.id === kept)) select.value = kept;
  $("rag-copy-reset").hidden = copy.empty;
  renderCopyControls();
}

function renderCopyControls() {
  const blocked = Boolean(busyReason()) || store.pending;
  for (const node of document.querySelectorAll("#rag-copy button[data-op], #rag-copy-apply, #rag-copy-reset")) node.disabled = blocked;
}

async function reloadCopy() {
  try {
    const response = await fetch("/api/rag_lab");
    if (!response.ok) return;
    store.workCopy = (await response.json()).work_copy;
  } catch {
    return;
  }
  renderCopy();
}

// « Ajouter » (id, title, text), « Modifier » (document, paragraph to append), « Supprimer ».
function openCopyForm(operation) {
  store.copyOp = operation;
  const form = $("rag-copy-form");
  form.hidden = false;
  form.dataset.op = operation;
  $("rag-copy-form-title").textContent = text(`costs.${operation}_doc_text`);
  $("rag-copy-pick").hidden = operation === "add";
  $("rag-copy-new").hidden = operation !== "add";
  $("rag-copy-body-box").hidden = operation === "delete";
  $("rag-copy-hint").hidden = operation !== "modify";
  $("rag-copy-error").textContent = "";
  (operation === "add" ? $("rag-copy-id") : $("rag-copy-doc")).focus();
}

function closeCopyForm() {
  store.copyOp = null;
  $("rag-copy-form").hidden = true;
}

async function applyCopyForm() {
  const operation = store.copyOp;
  if (!operation) return;
  const error = $("rag-copy-error");
  error.textContent = "";
  const body = { operation, doc_id: operation === "add" ? $("rag-copy-id").value.trim() : $("rag-copy-doc").value, pipelines: store.pipelines };
  if (operation === "add") body.title_text = $("rag-copy-title").value;
  if (operation !== "delete") body.text = $("rag-copy-body").value;
  store.pending = true;
  renderBusy();
  const answer = await post("/api/intentions/rag_lab_update", body);
  store.pending = false;
  renderBusy();
  if (!answer.ok) {
    error.textContent = refusalText(answer);
    return;
  }
  for (const id of ["rag-copy-id", "rag-copy-title", "rag-copy-body"]) $(id).value = "";
  closeCopyForm();
}

async function resetCopy() {
  const answer = await post("/api/rag_lab/copy/reset", {});
  if (!answer.ok) {
    $("rag-copy-error").textContent = refusalText(answer);
    return;
  }
  store.workCopy = answer.body.work_copy;
  store.update = null;
  renderCopy();
  renderCosts();
}

function wireCopy() {
  for (const button of document.querySelectorAll("#rag-copy button[data-op]")) {
    button.addEventListener("click", () => openCopyForm(button.dataset.op));
  }
  $("rag-copy-apply").addEventListener("click", applyCopyForm);
  $("rag-copy-cancel").addEventListener("click", closeCopyForm);
  $("rag-copy-reset").addEventListener("click", resetCopy);
}

// ---------- V1.2 story 7 (CAP-5): the context's budget, passages and final prompt ----------

// A badge: `data-state` is the indicator the tests read (`whole`, `cut`, `dropped`).
const badge = (state) => {
  const mark = el("span", "rag-badge", t(`rag.item_${state}`));
  mark.dataset.state = state;
  return mark;
};

// The cell of a passage of the context: whole or cut, its position, its estimated tokens
// (before and after a compression) and what the compressor did.
function passageState(item) {
  const cell = el("td", "rag-passage-state");
  cell.dataset.placed = String(item.placed ?? "");
  cell.append(badge(item.state ?? "whole"));
  if (typeof item.placed === "number") cell.append(" ", el("span", "rag-placed", t("rag.item_placed", { n: fmtInt(item.placed) })));
  if (typeof item.tokens === "number") {
    const compressed = typeof item.tokens_after === "number" && item.tokens_after < item.tokens;
    const said = compressed
      ? t("rag.item_tokens_after", { before: fmtInt(item.tokens), after: fmtInt(item.tokens_after) })
      : t("rag.item_tokens", { tokens: fmtInt(item.tokens) });
    cell.append(el("span", "rag-tokens", said));
    if (typeof item.tokens_after === "number" && !compressed && !item.error_text) {
      const unchanged = el("span", "rag-unchanged", t("rag.item_unchanged"));
      cell.append(unchanged);
    }
    if (item.transforms?.length) cell.append(el("span", "rag-transforms", t("rag.item_transforms", { names: item.transforms.join(", ") })));
  }
  if (item.error_text) cell.append(el("span", "rag-stage-error", item.error_text));
  return cell;
}

// The budget's gauge: the tokens the context takes of the tokens it may take (the session's).
function budgetGauge(budget) {
  const box = el("div", "rag-budget");
  box.dataset.used = String(budget.used);
  box.dataset.budget = String(budget.budget);
  const used = budget.before !== null && budget.before !== undefined ? budget.before : budget.used;
  box.append(el("p", "rag-budget-title", t("rag.budget_used", { used: fmtInt(used), budget: fmtInt(budget.budget) })));
  const gauge = el("meter", "rag-budget-gauge");
  gauge.min = 0;
  gauge.max = Math.max(budget.budget, used);
  gauge.value = used;
  box.append(gauge);
  if (budget.before !== null && budget.before !== undefined) {
    box.append(el("p", "rag-budget-after", t("rag.budget_compressed", { before: fmtInt(budget.before), after: fmtInt(budget.used) })));
  }
  return box;
}

// ---------- V1.2 story 10: the whole corpus against the window, the CAG's cache ----------

// The prompt's estimated tokens against the session's effective window.
function windowGauge(ended) {
  const box = el("div", "rag-window");
  const used = ended.prompt_tokens ?? 0;
  box.dataset.used = String(used);
  box.dataset.window = String(ended.window);
  box.append(el("p", "rag-window-title", t("rag.window_used", { used: fmtInt(used), window: fmtInt(ended.window) })));
  const gauge = el("meter", "rag-window-gauge");
  gauge.min = 0;
  gauge.max = Math.max(ended.window, used);
  gauge.value = used;
  box.append(gauge);
  return box;
}

// The cache of the run shown: the prefix line's, else the generation's (the session's figures).
function runCache(ended) {
  if (ended.cache) return ended.cache;
  const generation = store.run?.stages.find((s) => s.kind === "generation");
  const context = store.run?.stages.find((s) => s.kind === "context");
  return generation?.ended?.cache ?? context?.parts?.prefix?.ended?.cache ?? null;
}

// The CAG's cache: its state, the prefix's tokens, those read and evaluated, its build, its size.
function cacheBlock(cache) {
  const box = el("div", "rag-cache");
  box.append(el("p", "rag-cache-title", t("rag.cache_title")));
  if (!cache) {
    box.append(el("p", "rag-note", t("rag.cache_pending")));
    return box;
  }
  box.dataset.state = cache.state;
  const list = el("ul", "rag-cache-figures");
  const line = (key, values) => list.append(el("li", null, t(key, values)));
  line("rag.cache_state", { state: t(`rag.cache_state_${cache.state}`) });
  if (typeof cache.prefix_tokens === "number") line("rag.cache_prefix", { tokens: fmtInt(cache.prefix_tokens) });
  if (typeof cache.read_tokens === "number") line("rag.cache_read", { tokens: fmtInt(cache.read_tokens) });
  if (typeof cache.evaluated_tokens === "number") line("rag.cache_evaluated", { tokens: fmtInt(cache.evaluated_tokens) });
  if (typeof cache.build_ms === "number" && cache.state === "cold") line("rag.cache_build", { ms: fmtInt(cache.build_ms) });
  if (typeof cache.state_bytes === "number") line("rag.cache_size", { mb: fmtInt(Math.max(1, Math.round(cache.state_bytes / 1e6))) });
  box.append(list);
  return box;
}

// The passages the budget left out, with their indicator.
function droppedList(items) {
  const box = el("div", "rag-dropped");
  box.append(el("p", "rag-dropped-title", t("rag.dropped_title", { count: fmtInt(items.length) })));
  const list = el("ul", "rag-dropped-list");
  for (const item of items) {
    const row = el("li", "rag-dropped-item");
    row.dataset.chunkId = String(item.chunk_id);
    row.append(badge("dropped"), " ", el("span", "rag-doc-title", item.title_text), " ");
    row.append(el("span", "rag-tokens", t("rag.item_tokens", { tokens: fmtInt(item.tokens) })));
    row.append(el("span", "rag-doc-text", item.text));
    list.append(row);
  }
  box.append(list);
  return box;
}

// The final prompt as it leaves for the model: system instruction, context, question.
function promptParts(ended) {
  const box = el("div", "rag-prompt-parts");
  box.append(el("p", "rag-prompt-parts-title", t("rag.prompt_title")));
  for (const part of ended.prompt_parts) {
    const block = el("div", "rag-prompt-part");
    block.dataset.kind = part.kind;
    block.append(el("p", "rag-prompt-part-head", labelled(part.label_text, t("rag.item_tokens", { tokens: fmtInt(part.tokens) }))));
    block.append(el("pre", "rag-focus-pre", part.text));
    box.append(block);
  }
  box.append(el("p", "rag-prompt-parts-total", t("rag.prompt_total", { tokens: fmtInt(ended.prompt_tokens) })));
  return box;
}

// ---------- V1.2 story 6 (CAP-4): the chunks the chunking made, and the contexts' rebuild ----------

// The chunking stage's first chunks (the session cut them, AD-1): document and rank, text,
// parent (parent_child), context with its mark (contextual).
function chunksList(ended) {
  const box = el("div", "rag-chunks");
  box.append(el("p", "rag-chunks-title", t("rag.chunks_shown", { shown: fmtInt(ended.chunks.length), total: fmtInt(ended.chunks_total) })));
  const list = el("ol", "rag-chunks-list");
  for (const chunk of ended.chunks) {
    const item = el("li", "rag-chunk");
    item.dataset.doc = chunk.doc_id;
    item.dataset.position = String(chunk.position);
    item.append(el("p", "rag-chunk-title", t("rag.chunk_title", { title: chunk.title_text, position: chunk.position })));
    if (chunk.context_text) {
      const context = el("p", "rag-chunk-context");
      context.append(el("span", "rag-chunk-label", `${t("rag.chunk_context")} · `), el("span", "rag-chunk-mark", chunk.context_label), ` : ${chunk.context_text}`);
      item.append(context);
    }
    item.append(el("p", "rag-chunk-text", chunk.text));
    if (chunk.parent_text) {
      const parent = el("p", "rag-chunk-parent");
      parent.append(el("span", "rag-chunk-label", `${t("rag.chunk_parent", { position: chunk.parent_position })} `), chunk.parent_text);
      item.append(parent);
    }
    list.append(item);
  }
  box.append(list);
  return box;
}

// « Reconstruire » and « Rétablir les contextes livrés », in the focus of a contextual chunking.
function contextControls() {
  const box = el("div", "rag-contexts");
  const info = store.contexts;
  if (info?.summary_text) box.append(el("p", "rag-contexts-summary", info.summary_text));
  if (info?.expected_text) box.append(el("p", "rag-note", info.expected_text));
  const buttons = el("p", "rag-contexts-buttons");
  const rebuild = el("button", "rag-button-secondary", t("rag.contexts_rebuild"));
  rebuild.type = "button";
  rebuild.id = "rag-contexts-rebuild";
  rebuild.dataset.action = "rebuild";
  rebuild.addEventListener("click", rebuildContexts);
  const reset = el("button", "rag-button-secondary", t("rag.contexts_reset"));
  reset.type = "button";
  reset.id = "rag-contexts-reset";
  reset.dataset.action = "reset";
  reset.addEventListener("click", resetContexts);
  buttons.append(rebuild, reset);
  box.append(buttons);
  if (info?.rebuild_blocked_text) box.append(el("p", "rag-note rag-contexts-blocked", info.rebuild_blocked_text));
  const job = store.rebuild;
  if (job && !job.ended) {
    box.append(el("p", "rag-contexts-progress", t("rag.contexts_progress", { done: fmtInt(job.done), total: fmtInt(job.total) })));
  } else if (job?.error) {
    box.append(el("p", "rag-stage-error", t("rag.contexts_failed", { reason: job.error })));
  } else if (job?.output) {
    box.append(el("p", "rag-contexts-done", job.output));
  }
  if (store.contextError) box.append(el("p", "rag-stage-error", store.contextError));
  setContextButtons(box);
  return box;
}

// Why a button waits: the session busy, a POST under way, no model (rebuild), nothing rebuilt (reset).
function setContextButtons(root = document) {
  const blocked = Boolean(busyReason()) || store.pending;
  for (const button of root.querySelectorAll(".rag-contexts button")) {
    const rebuild = button.dataset.action === "rebuild";
    button.disabled = blocked || (rebuild ? Boolean(store.contexts?.rebuild_blocked_text) : !store.contexts?.rebuilt);
    button.title = (rebuild && store.contexts?.rebuild_blocked_text) || "";
  }
}

async function rebuildContexts() {
  store.contextError = null;
  store.pending = true;
  renderBusy();
  const answer = await post("/api/intentions/rag_lab_rebuild", { pipelines: store.pipelines });
  store.pending = false;
  if (!answer.ok) store.contextError = refusalText(answer);
  renderBusy();
  renderCurrent();
}

async function resetContexts() {
  store.contextError = null;
  const answer = await post("/api/rag_lab/contexts/reset", {});
  if (answer.ok) {
    store.contexts = answer.body.contexts;
    store.rebuild = null;
  } else {
    store.contextError = refusalText(answer);
  }
  renderCurrent();
}

async function reloadContexts() {
  try {
    const response = await fetch("/api/rag_lab");
    if (!response.ok) return;
    store.contexts = (await response.json()).contexts;
  } catch {
    return;
  }
  renderCurrent();
}

const isRebuildEvent = (envelope) => String(envelope.payload?.run_id ?? "").startsWith("ctx");

// A rebuild's events (`ctx{n}`): its progress in chunks, its outcome; never the last run's.
function applyRebuildEnvelope(envelope) {
  const p = envelope.payload;
  if (envelope.kind === "rag_lab_run_started") {
    store.rebuild = { runId: p.run_id, done: 0, total: 0, ended: null, error: null, output: null };
  } else if (store.rebuild?.runId !== p.run_id) {
    return;
  } else if (envelope.kind === "rag_lab_stage_progress") {
    store.rebuild.done = p.done;
    store.rebuild.total = p.total;
  } else if (envelope.kind === "rag_lab_stage_ended") {
    store.rebuild.error = p.error_text;
    store.rebuild.output = p.output_text;
  } else if (envelope.kind === "rag_lab_run_ended") {
    store.rebuild.ended = p;
    if (!store.replaying) reloadContexts();
  } else {
    return;
  }
  if (!store.replaying) renderCurrent();
}

// ---------- state of the session: what may be asked now ----------

function busyReason() {
  if (!store.content) return null;
  if (store.unavailable) return store.unavailable;
  const { state, reason_text: reason } = store.session;
  if (state !== "idle") return text("busy_text", { raison: reason || state }) || reason || state;
  return null;
}

// Why « Lancer » waits: the session busy, else a chain it would refuse.
function runBlocked() {
  return busyReason() || store.refusals[0]?.reason_text || null;
}

function renderBusy() {
  const reason = busyReason();
  const busy = $("rag-busy");
  busy.hidden = !reason;
  busy.textContent = reason || "";
  const run = $("rag-run");
  const blocked = runBlocked();
  run.disabled = Boolean(blocked) || store.pending || !store.content;
  run.title = blocked || "";
  // Lot 5c-4: « Arrêter » stops a download too (even one launched before a reload).
  $("rag-stop").disabled = !["rag_lab", "download"].includes(store.session.state);
  renderCopyControls();
  setContextButtons();
}

// ---------- V1.2 story 4: the view tabs (vues.md) ----------
// The shell is common; each tab's code lives in its own file (`rag-<tab>.js`), which registers
// its hooks here: `mount` (once, the page ready), `render` (the data or the texts changed),
// `show` (its tab opened), `envelope` (a journal event, `replaying` while the last run is read).

const tabModules = {};
const tabHook = (id, hook, ...args) => tabModules[id]?.[hook]?.(...args);
const everyTab = (hook, ...args) => Object.keys(tabModules).forEach((id) => tabHook(id, hook, ...args));

// A tab's file registers itself once; a tab arriving after the page is ready is mounted at once.
export function registerTab(id, hooks) {
  tabModules[id] = hooks;
  if (store.mounted) {
    hooks.mount?.();
    hooks.render?.();
  }
}

const TAB_IDS = ["build", "compare", "evaluate", "attack", "sheets"];

function tabFromHash() {
  const id = location.hash.replace(/^#/, "");
  return TAB_IDS.includes(id) ? id : "build";
}

function setTab(tab, { focus = false } = {}) {
  if (!TAB_IDS.includes(tab)) tab = "build";
  store.tab = tab;
  for (const button of document.querySelectorAll("#rag-tabs [data-tab]")) {
    const on = button.dataset.tab === tab;
    button.setAttribute("aria-selected", String(on));
    button.tabIndex = on ? 0 : -1;
    if (on && focus) button.focus();
  }
  for (const id of TAB_IDS) {
    const panel = $(`rag-panel-${id}`);
    if (panel) panel.hidden = id !== tab;
  }
  history.replaceState(null, "", tab === "build" ? location.pathname + location.search : `#${tab}`);
  if (tab === "build") redraw(); // the views were hidden: drawn again
  tabHook(tab, "show");
}

function renderTabs() {
  for (const button of document.querySelectorAll("#rag-tabs [data-tab]")) {
    button.textContent = text(`tabs.${button.dataset.tab}_text`);
  }
  $("rag-tabs").setAttribute("aria-label", text("tabs.label_text"));
  for (const id of ["evaluate", "attack", "sheets"]) {
    $(`rag-panel-${id}`).querySelector(".rag-soon").textContent = text("tabs.soon_text", { name: text(`tabs.${id}_text`) });
  }
}

function wireTabs() {
  const buttons = [...document.querySelectorAll("#rag-tabs [data-tab]")];
  for (const button of buttons) {
    button.addEventListener("click", () => setTab(button.dataset.tab));
    button.addEventListener("keydown", (event) => {
      const at = buttons.indexOf(button);
      const to = { ArrowRight: at + 1, ArrowLeft: at - 1, Home: 0, End: buttons.length - 1 }[event.key];
      if (to === undefined) return;
      event.preventDefault();
      const next = buttons[(to + buttons.length) % buttons.length];
      setTab(next.dataset.tab, { focus: true });
    });
  }
  window.addEventListener("hashchange", () => setTab(tabFromHash()));
}

function renderContent() {
  for (const node of document.querySelectorAll("[data-text]")) {
    const value = text(node.dataset.text);
    if (value) node.textContent = value;
  }
  if (store.content) {
    $("rag-title").textContent = store.content.title_text;
    $("rag-intro").textContent = store.content.intro_text;
    $("rag-question").placeholder = store.content.question_placeholder_text;
    $("rag-modes").setAttribute("aria-label", store.content.modes_label_text);
    renderTabs();
    everyTab("render");
  }
}

// ---------- gestures ----------

async function runChain() {
  const question = $("rag-question").value.trim();
  const status = $("rag-status");
  status.classList.remove("is-error");
  if (!question) {
    status.classList.add("is-error");
    status.textContent = t("rag.empty_question");
    return;
  }
  // The number fields' last values, even one typed without leaving its field (before
  // « Dérouler » takes the editor away).
  for (const input of document.querySelectorAll(".rag-param-input")) input.dispatchEvent(new Event("change"));
  const before = store.mode;
  setMode("play"); // « Lancer » shows the run as it goes (lot 5a-2)
  store.pending = true;
  renderBusy();
  status.textContent = text("running_text");
  // V1.2 story 13: GraphRAG's mode, chosen on its card (rag-graph.js); « local » by default.
  const body = { question, pipelines: store.pipelines, graph_mode: store.graphMode || "local" };
  const answer = await post("/api/intentions/rag_lab_run", body);
  store.pending = false;
  if (!answer.ok) {
    setMode(before); // refused: nothing runs, back where the trainer was
    status.classList.add("is-error");
    status.textContent = refusalText(answer);
  } else {
    status.textContent = "";
  }
  renderBusy();
}

async function stopRun() {
  await post("/api/intentions/stop", {});
}

// ---------- the stream ----------

// SSE read by hand, as app.js: the server names each event after its `kind`.
async function streamEvents() {
  for (;;) {
    try {
      const response = await fetch("/api/stream", {
        headers: store.lastSeq ? { "Last-Event-ID": String(store.lastSeq) } : {},
      });
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let sep;
        while ((sep = buffer.indexOf("\n\n")) !== -1) {
          const raw = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          const { event, data } = parseSseEvent(raw);
          if (!data) continue;
          if (event === "server_instance") {
            // Another process's journal: the page reloads, as the workshop does.
            if (store.serverInstance === null) store.serverInstance = data.instance_id;
            else if (data.instance_id !== store.serverInstance) {
              location.reload();
              return;
            }
          } else if (data.seq > store.lastSeq) {
            applyEnvelope(data);
          }
        }
      }
    } catch {
      // reconnection below resumes at lastSeq
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

function parseSseEvent(raw) {
  let event = null;
  let data = null;
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data = line.slice(5).trim();
  }
  if (!data) return { event, data: null };
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return { event, data: null };
  }
}

async function refresh() {
  let body;
  try {
    const response = await fetch("/api/rag_lab");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    body = await response.json();
  } catch (error) {
    const alert = $("rag-content-error");
    alert.hidden = false;
    alert.textContent = t("rag.unavailable", { cause: error.message });
    return null;
  }
  store.content = body.content;
  store.catalog = body.catalog;
  store.defaultPipeline = body.default_pipeline;
  store.unavailable = body.unavailable_text;
  store.session = body.session_state;
  store.questions = body.questions ?? [];
  const alert = $("rag-content-error");
  alert.hidden = !body.content_error_text;
  alert.textContent = body.content_error_text || "";
  renderContent();
  if (!store.pipelines.length && store.defaultPipeline) store.pipelines = loadChains();
  // The last run, rebuilt from its envelopes (AD-1): the same projection as the stream's.
  store.run = null;
  store.replaying = true;
  try {
    store.costs = { build: null, query: null };
    store.update = null;
    for (const envelope of body.last_run) applyEnvelope(envelope);
    for (const envelope of body.last_update ?? []) applyEnvelope(envelope);
    store.workCopy = body.work_copy;
    store.contexts = body.contexts ?? null;
  } finally {
    store.replaying = false;
  }
  store.land = false;
  store.lastSeq = body.seq;
  if (store.session.state === "idle") closeStaleRun();
  // « Dérouler »: the run's frames pushed again, straight to its landing frame (§6).
  redraw({ restart: true });
  renderResults();
  renderCosts();
  renderCopy();
  everyTab("render");
  if (store.catalog) validateChains();
  renderBusy();
  return body;
}

// Story 3 (V1.1, CAP-6): the Séquence grown to almost the whole window (no `.pane`/panes.js
// here, so its own toggle; Echap closes it, wired in `main`).
// Recette (fix CAP-6): the stepper (◀ ▶, legend) lives in the bar ABOVE `#rag-views`, so once
// `#rag-seq` goes `position: fixed` it is covered. Moved into the panel while expanded, put
// back at its own spot (remembered by `stepperHome`) on close.
const stepperHome = { parent: null, next: null };
function setSeqExpanded(on) {
  const seq = $("rag-seq");
  const stepperBox = $("rag-stepper");
  if (on === seq.classList.contains("is-expanded")) return; // keeps `stepperHome` as recorded
  // Moving the focused ◀/▶ blurs it to <body>: hand the focus back after the move.
  const focused = stepperBox.contains(document.activeElement) ? document.activeElement : null;
  seq.classList.toggle("is-expanded", on);
  $("rag-seq-expand").setAttribute("aria-pressed", String(on));
  if (on) {
    stepperHome.parent = stepperBox.parentElement;
    stepperHome.next = stepperBox.nextElementSibling;
    seq.querySelector(".rag-seq-view-head").after(stepperBox);
  } else if (stepperHome.parent) {
    stepperHome.parent.insertBefore(stepperBox, stepperHome.next);
    stepperHome.parent = null;
  }
  focused?.focus();
}

async function main() {
  await textsReady; // the page's texts and formats in the session's language (languages 4/5)
  const mode = stored(MODE_KEY);
  if (MODES.includes(mode)) store.mode = mode;
  wires = wireLayer($("rag-views"), drawWires);
  // The stepper before the legend, in « Dérouler »'s bar (its labels read now: after `ready`).
  stepper = createStepper($("rag-stepper"), { onShow: showFrame });
  $("rag-stepper").prepend(stepper.element);
  let body = await refresh();
  while (!body) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    body = await refresh();
  }
  const question = $("rag-question");
  question.value = stored(QUESTION_KEY) ?? (text("default_question_text") || "");
  question.addEventListener("input", () => keep(QUESTION_KEY, question.value));
  wireTabs();
  store.mounted = true;
  everyTab("mount");
  everyTab("render");
  setTab(tabFromHash());
  question.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !$("rag-run").disabled) runChain();
  });
  $("rag-run").addEventListener("click", runChain);
  $("rag-stop").addEventListener("click", stopRun);
  $("rag-reset-chain").addEventListener("click", resetChains);
  wireCopy();
  for (const button of document.querySelectorAll("#rag-modes [data-mode]")) {
    button.addEventListener("click", () => setMode(button.dataset.mode));
  }
  $("rag-seq-expand").addEventListener("click", () => setSeqExpanded(!$("rag-seq").classList.contains("is-expanded")));
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || event.defaultPrevented) return;
    if (!$("rag-seq").classList.contains("is-expanded")) return;
    event.preventDefault();
    setSeqExpanded(false);
  });
  document.body.dataset.ragReady = "true";
  streamEvents();
}

main();

export { $, el, text, quote, fmtInt, keep, stored, store, costFigures, QUESTION_KEY };
// V1.2 story 11: what rag-agentic.js draws the agent's rounds and PageIndex's tree with.
export { busyReason, chain, labelled, post, refusalText, renderBusy, renderCurrent };
