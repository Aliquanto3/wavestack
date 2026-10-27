// Story 9 (CAP-7, CAP-9): the barre commune's two buttons and their flyouts, the same static
// HTML in each of the five pages, one implementation (`bar.js`, loaded after site-nav.js,
// like it): « Dépense » (the session's spend and its economies, "Bilan de la séance") and
// « Journal » (the session's refusals and blocks, a 5-event preview).
//
// - Non modal, one open at a time (ux/EXPERIENCE.md bar-flyout): a click toggles its own
//   panel and closes the other; Escape closes the open one and returns the focus to its
//   button; a click outside both closes them too (a page change closes them for free, a
//   full navigation).
// - Its state: `GET /api/state` at load, and again each time a panel opens. Every page's own
//   `/api/stream` reader (app.js, llm.js, rag.js, mcp.js, the diagnostic's) hands each
//   envelope to `feedBar`, which keeps `consumption_updated`, `security_event` and
//   `model_call_ended`, in O(1), never a walk of the journal (a structure that only grows
//   during a session). `seq` orders the sources: a snapshot older than the last event fed is
//   ignored.
// - Story 1 (CAP-2, 2026-10-27): the Journal also lists every model call, of every onglet
//   (contrat figé, `story-1.md`), derived client-side from the envelopes as they are
//   (Décision Q1): the onglet from `context_id`, the model from the last `active_model` the
//   stream gave (`session_state`, `turn_started`), so a replay labels each call as it was.
//   These entries never carry a prompt nor an answer. Bounded in memory to 500, like
//   `SecurityJournal`, kept in the tab's `sessionStorage` across its pages; a filter keeps
//   only the security decisions.
// - It replaces the main screen's former « Dépense estimée » gauge (ux/EXPERIENCE.md): the
//   panel carries what the gauge said (the euros, the cap, the footprint, the reset).

import { dateTimeFormat, has, numberFormat, rangeText, ready, t } from "./i18n.js";

const $ = (id) => document.getElementById(id);

let consumption = null; // the `consumption_updated` shape, or null before any paid/impactful call
let deniedCount = 0; // the session's refusals and blocks (the red badge), security only
let logEntries = []; // newest first, kind "security" or "model_call", bounded to LOG_KEPT
let securityOnly = false; // the « Sécurité seulement » filter
let logExpanded = false; // the dépliable history, past the 5-line preview
let maxSessionUsd = null; // finition V1 (#27): `[finops] max_session_usd`, from `/api/state`
let seq = 0; // the newest journal `seq` the figures above reflect
// Story 1 (CAP-2): the model calls have their own mark, never the snapshot's `seq` (an
// `/api/state` tip would drop a call emitted but not yet streamed: the server keeps no copy).
let modelSeq = 0; // the newest `model_call_ended` fed
let model = null; // `{label, hosting}` the stream last named, in `seq` order
let modelAt = 0; // the `seq` of the envelope that named it (0: none yet)
let saved = null; // the previous page's calls, merged once `/api/state` confirms its process
let instanceId = null; // the journal's process, `/api/state`'s

const LOG_KEPT = 500; // the same order of magnitude as `SecurityJournal` (`_KEPT`)
const LOG_PREVIEW = 5;
const STORAGE_KEY = "wavestack.bar.log"; // this browser tab only, across its page loads
// The onglet, from the envelope's own `context_id`: `main`, a sub-agent's or none is the
// conversation.
const TAB_OF = { llm: "tab_llm", rag_lab: "tab_rag", mcp_lab: "tab_mcp", diag: "tab_models" };
// What a page that listens by name (EventSource) adds for the Journal's model calls.
export const BAR_MODEL_KINDS = ["model_call_ended", "session_state", "turn_started"];

const modelOf = (active) => (active ? { label: active.label, hosting: active.hosting } : null);

export function feedBar(envelope) {
  const kind = envelope.kind;
  const payload = envelope.payload;
  if (kind === "session_state" || kind === "turn_started") {
    // AD-12: the model of the calls that follow, as the stream said it then.
    if (payload.active_model !== undefined && envelope.seq > modelAt) {
      model = modelOf(payload.active_model);
      modelAt = envelope.seq;
    }
    return;
  }
  if (kind === "model_call_ended") {
    if (envelope.seq <= modelSeq) return;
    modelSeq = envelope.seq;
    // The diagnostic tests each cloud entry, not the session's model: no label to give.
    pushLogEntry(modelCallEntry(envelope, payload, envelope.context_id === "diag" ? null : model));
    return;
  }
  if ((kind !== "consumption_updated" && kind !== "security_event") || envelope.seq <= seq) return;
  seq = envelope.seq;
  if (kind === "consumption_updated") {
    consumption = payload;
    renderSpend();
    return;
  }
  deniedCount = payload.denied_count;
  pushLogEntry({
    kind: "security",
    ts: payload.ts,
    source: payload.source,
    name: payload.name,
    label_text: payload.label_text,
    decision: payload.decision,
    reason_text: payload.reason_text,
  });
}

// Contrat figé (story 1, `story-1.md`) : jamais `text`, `raw_output`, `reasoning` ni
// `tool_calls` — aucune entrée ne porte le prompt ni la réponse. `seq` : interne, pour ne
// pas doubler les appels qu'une page rejoue et que la page précédente avait gardés.
function modelCallEntry(envelope, payload, modele) {
  return {
    kind: "model_call",
    seq: envelope.seq,
    ts: envelope.ts,
    onglet: t(`common.bar.log.${TAB_OF[envelope.context_id] ?? "tab_conversation"}`),
    modele,
    tokens_in: payload.prompt_tokens,
    tokens_out: payload.output_tokens,
    cout_usd: payload.cost_in_usd != null && payload.cost_out_usd != null ? payload.cost_in_usd + payload.cost_out_usd : null,
    empreinte:
      payload.impact_method != null
        ? {
            energy_wh_min: payload.energy_wh_min,
            energy_wh_max: payload.energy_wh_max,
            gco2e_min: payload.gco2e_min,
            gco2e_max: payload.gco2e_max,
            impact_method: payload.impact_method,
          }
        : null,
    duree_ms: payload.duration_ms,
  };
}

// The badge, and one row prepended when the panel is open (its other rows, one unfolded or
// focused, stay as they are); a closed panel is drawn when it opens. Never the whole list.
function pushLogEntry(entry) {
  logEntries.unshift(entry);
  if (logEntries.length > LOG_KEPT) logEntries.pop();
  renderLogBadge();
  const list = $("bar-log-list");
  if (!list || $("bar-log-panel")?.hidden !== false) return;
  if (securityOnly && entry.kind !== "security") return;
  if (list.querySelector(".bar-flyout-empty")) return renderLogPanel();
  list.prepend(logRow(entry));
  while (list.children.length > (logExpanded ? LOG_KEPT : LOG_PREVIEW)) list.lastElementChild.remove();
  renderLogMore(filteredLog().length);
}

// The server keeps no Journal of the model calls (Décision Q1): this tab's `sessionStorage`
// carries them from one page to the next, gone with the tab.
// shortcut: a call ended while no page of the tab streams (between two loads) is missed;
// a server-side Journal would close that gap.
function restoreModelCalls() {
  try {
    saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "null");
  } catch {
    saved = null; // a storage refused or unreadable: the Journal starts with this page
  }
}

function saveModelCalls() {
  try {
    const entries = logEntries.filter((e) => e.kind === "model_call");
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ instanceId, modelSeq, model, modelAt, entries }));
  } catch {
    // Same: nothing more to keep.
  }
}

// Once `/api/state` names the process: the previous page's calls join this page's (a replay
// from 0 may have fed some of them again: `seq` dedups), another process's are dropped.
function mergeSaved() {
  const from = saved;
  saved = null;
  if (!from || from.instanceId !== instanceId || !Array.isArray(from.entries)) return;
  const fed = new Set(logEntries.map((e) => e.seq));
  logEntries.push(...from.entries.filter((e) => !fed.has(e.seq)));
  // Once per page: a replay may have fed newer calls than some kept ones, or older.
  logEntries.sort((a, b) => new Date(b.ts) - new Date(a.ts));
  logEntries.length = Math.min(logEntries.length, LOG_KEPT);
  modelSeq = Math.max(modelSeq, from.modelSeq ?? 0);
  if ((from.modelAt ?? 0) > modelAt) ({ model, modelAt } = from);
}

async function refresh() {
  try {
    const body = await (await fetch("/api/state")).json();
    maxSessionUsd = body.max_session_usd ?? null;
    instanceId = body.instance_id ?? instanceId;
    mergeSaved();
    // A page streaming from the tip has no `session_state` yet: the current model meanwhile.
    if (modelAt === 0) model = modelOf(body.active_model);
    // An answer older than an event already fed would put stale figures back.
    if ((body.seq ?? 0) >= seq) {
      seq = body.seq ?? 0;
      consumption = body.consumption_updated ?? null;
      const preview = body.security_journal_preview ?? { denied_count: 0, entries: [] };
      deniedCount = preview.denied_count;
      mergeSecurityEntries(preview.entries);
    }
  } catch {
    // Kept as it was: a page briefly unreachable shows the last known state, not a blank one.
  }
  renderSpend();
  renderLog();
}

// The server only knows the security entries (bounded to the journal's own 500); the model
// calls, client-side (Décision Q1), are kept as they are. Sorted on open only, never per event.
function mergeSecurityEntries(entries) {
  const modelCalls = logEntries.filter((e) => e.kind === "model_call");
  const security = entries.map((e) => ({ kind: "security", ...e }));
  logEntries = [...security, ...modelCalls].sort((a, b) => new Date(b.ts) - new Date(a.ts)).slice(0, LOG_KEPT);
}

// ---------- formatting (figures are the session's; this only shapes them) ----------

const shortUsd = (n) =>
  n > 0 && n < 0.00005
    ? t("common.format.usd_below", { amount: numberFormat({ maximumFractionDigits: 4 }).format(0.0001) })
    : t("common.format.usd", { amount: numberFormat({ maximumFractionDigits: 4 }).format(n) });
const usd = (n) => t("common.format.usd", { amount: numberFormat({ maximumSignificantDigits: 4 }).format(n) });
// AD-4: « ≈ » on every amount of a session whose spend is (partly) estimated.
const guess = () => (consumption?.approx ? "≈ " : "");
const money = (n) => `${guess()}${shortUsd(n)}`;
const kvSeconds = (s) => numberFormat({ maximumFractionDigits: 1 }).format(s);

// ---------- « Dépense » ----------

// The session's net economy, signed (a cache write may cost more than its reads saved), or
// null when nothing priced was measured (never a fabricated « économisé 0 $ »).
function economy(c) {
  if (!c.saved_calls) return null;
  return (c.cache_saved_usd ?? 0) + (c.compression_saved_usd ?? 0);
}

function renderSpend() {
  const toggle = $("bar-spend-toggle");
  if (!toggle) return;
  toggle.hidden = !consumption;
  if (!consumption) return;
  const c = consumption;
  const paid = c.calls > 0;
  const amount = $("bar-spend-amount");
  // Story 1 (CAP-1): a montant toujours affiché, jamais `c.calls > 0` seul : un modèle sans
  // `pricing` (Gemma) a `calls === 0` mais `unpriced_calls > 0`, 0 € + l'offre gratuite,
  // jamais confondu avec un vrai 0 $.
  amount.textContent = paid ? money(c.total_usd) : shortUsd(0);
  const saved = $("bar-spend-saved");
  const net = economy(c);
  if (paid && net !== null) {
    saved.textContent =
      net >= 0 ? t("common.bar.spend.saved", { amount: money(net) }) : t("common.bar.spend.overcost", { amount: money(-net) });
  } else if (!paid && c.unpriced_calls > 0) {
    saved.textContent = t("common.bar.spend.free_tier");
  } else if (c.kv_time_saved_s > 0) {
    // A local session costs nothing: the time the KV-cache saved is its one economy.
    saved.textContent = t("common.bar.spend.time_saved", { seconds: kvSeconds(c.kv_time_saved_s) });
  } else {
    saved.textContent = "";
  }
  saved.hidden = !saved.textContent;
  toggle.setAttribute(
    "aria-label",
    [`${t("common.bar.spend.label")} ${amount.textContent}`, saved.textContent].filter(Boolean).join(" · "),
  );
  toggle.title = detailSentence(c);
  renderSpendPanel();
}

// The former gauge's sentence: the spend in dollars, the cap, the footprint, and what resets
// them. Story 1 (CAP-3): dollars only, like the button's own amount (`usd`); no currency
// conversion.
function detailSentence(c) {
  const paid = c.calls > 0;
  const green = (c.impact_calls ?? 0) > 0;
  const sentences = [];
  if (paid) {
    sentences.push(
      t("main.consumption.spend_sentence", {
        input: `${guess()}${usd(c.total_in_usd)}`,
        output: `${guess()}${usd(c.total_out_usd)}`,
        total: `${guess()}${usd(c.total_usd)}`,
        calls: t("main.consumption.paid_calls", { count: c.calls }),
      }),
    );
    if (maxSessionUsd != null) {
      sentences.push(t("main.consumption.cap_sentence", { total: `${guess()}${usd(c.total_usd)}`, cap: usd(maxSessionUsd) }));
    }
  } else if (c.unpriced_calls > 0) {
    sentences.push(t("main.consumption.free_sentence", { calls: t("common.count.call", { count: c.unpriced_calls }) }));
  }
  if (green) {
    sentences.push(
      t("main.consumption.footprint_sentence", {
        energy: rangeText(c.energy_wh_min, c.energy_wh_max, "Wh"),
        grams: rangeText(c.gco2e_min, c.gco2e_max, "g CO₂e"),
        calls: t("common.count.call", { count: c.impact_calls }),
      }),
    );
  }
  sentences.push(paid && green ? t("main.consumption.reset_totals") : t("main.consumption.reset_total"));
  return sentences.join(" ");
}

function renderSpendPanel() {
  const bars = $("bar-savings-bars");
  const summary = $("bar-spend-summary");
  if (!bars || !summary || !consumption) return;
  const c = consumption;
  const paid = c.calls > 0;
  const real = c.total_usd;
  const net = economy(c);
  // Exact arithmetic: what the session would have cost with no cache nor compression; above
  // the real cost when they saved, below it when the cache's writes cost more.
  const without = real + (net ?? 0);
  const scale = Math.max(without, real) || 1;
  bars.replaceChildren(
    savingsBar(t("common.bar.spend.without_optimization"), without, scale),
    savingsBar(t("common.bar.spend.real_cost"), real, scale),
  );
  bars.hidden = !paid;
  const legend = document.querySelector(".bar-savings-legend");
  if (legend) legend.hidden = !paid;
  const lines = [];
  if (paid && net !== null && net < 0) {
    lines.push(t("common.bar.spend.summary_overcost", { amount: money(-net) }));
  } else if (paid && net !== null && without > 0) {
    lines.push(
      t("common.bar.spend.summary", {
        percent: String(Math.round((100 * net) / without)),
        cache: money(c.cache_saved_usd ?? 0),
        compression: money(c.compression_saved_usd ?? 0),
      }),
    );
  } else if (!(c.kv_time_saved_s > 0)) {
    lines.push(t("common.bar.spend.summary_none"));
  }
  if (c.kv_time_saved_s > 0) lines.push(t("common.bar.spend.summary_kv", { seconds: kvSeconds(c.kv_time_saved_s) }));
  summary.textContent = lines.join(" ");
  const footprint = $("bar-spend-footprint");
  const green = (c.impact_calls ?? 0) > 0;
  if (footprint) {
    footprint.textContent = green ? `🍃 ${rangeText(c.energy_wh_min, c.energy_wh_max, "Wh")} · ${rangeText(c.gco2e_min, c.gco2e_max, "g CO₂e")}` : "";
    footprint.hidden = !green;
  }
  const detail = $("bar-spend-detail");
  if (detail) detail.textContent = detailSentence(c);
  renderCacheBilan(c);
}

function savingsBar(label, amount, scale) {
  const row = document.createElement("div");
  row.className = "bar-savings-row";
  const name = document.createElement("span");
  name.textContent = label;
  const track = document.createElement("span");
  track.className = "bar-savings-track";
  const input = document.createElement("i");
  input.className = "bar-savings-in";
  const output = document.createElement("i");
  output.className = "bar-savings-out";
  const total = (consumption.total_in_usd ?? 0) + (consumption.total_out_usd ?? 0) || 1;
  // The bar's own shares, from this session's cloud totals only (sub-agent calls already in
  // them, never added again): entrée/sortie, the only split cheap enough to show honestly.
  const length = Math.max(0, amount) / scale;
  input.style.width = `${(100 * length * (consumption.total_in_usd ?? 0)) / total}%`;
  output.style.width = `${(100 * length * (consumption.total_out_usd ?? 0)) / total}%`;
  track.append(input, output);
  const value = document.createElement("span");
  value.textContent = money(amount);
  row.append(name, track, value);
  return row;
}

// ---------- V1.3 CAP-3: the cache bilan, « Cette conversation » and « Depuis le lancement » ----------

// The ring's posts, in the order of agent-cost-kit's bilan; each has its own CSS class (the
// `--color-segment-*` tokens, light and dark) and its text key.
const RING_POSTS = ["read", "write_5m", "write_1h", "fresh", "out"];
const RING_TEXT = { read: "read", write_5m: "write_5m", write_1h: "write_1h", fresh: "uncached", out: "out" };
const RING_GAP = 1; // units of the 100-unit circumference left between two segments

// One cache cell of a column, as text: exact, partial (a mix of declared and undeclared
// calls, never a sum shown as exact), « non déclaré » (never 0) or « sans objet » (a local
// call has no uncached part).
function cellText(cell, tokens, notApplicable) {
  const declared = cell.declared ?? 0;
  const undeclared = cell.undeclared ?? 0;
  const count = numberFormat({}).format(tokens);
  if (declared === 0 && undeclared === 0) {
    return t(notApplicable ? "common.bar.spend.cache.not_applicable" : "common.bar.spend.cache.none");
  }
  if (declared === 0) return t("common.bar.spend.cache.undeclared");
  if (undeclared === 0) return t("common.bar.spend.cache.value_exact", { tokens: count });
  return t("common.bar.spend.cache.value_partial", { tokens: count, declared, total: declared + undeclared });
}

// « Beaucoup d'écriture : le cache se perd »: the conversation's writes, the cache's priming
// (its first declared write) left out, exceed its reads; exact sums on both sides only.
function writeSignal(col) {
  const { read, write } = col.cache;
  if (!(write.declared > 0) || write.undeclared > 0 || read.undeclared > 0) return false;
  return write.tokens - (col.cold_write_tokens ?? 0) > read.tokens;
}

function ringNode(col) {
  const box = document.createElement("div");
  box.className = "bar-ring";
  const title = document.createElement("h4");
  title.textContent = t("common.bar.spend.cache.ring_title");
  box.append(title);
  const total = RING_POSTS.reduce((sum, post) => sum + Math.max(0, col.ring[post] ?? 0), 0);
  if (!(col.ring_calls > 0) || !(total > 0)) {
    const none = document.createElement("p");
    none.className = "bar-flyout-note";
    none.textContent = t("common.bar.spend.cache.ring_none");
    box.append(none);
  } else {
    const posts = RING_POSTS.filter((post) => post !== "write_1h" || col.ring[post] > 0);
    const share = (post) => (100 * Math.max(0, col.ring[post] ?? 0)) / total;
    const postName = (post) => t(`common.bar.spend.cache.${RING_TEXT[post]}`);
    const biggest = posts.reduce((a, b) => (share(b) > share(a) ? b : a));
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 42 42");
    svg.setAttribute("class", "bar-ring-svg");
    svg.setAttribute("role", "img");
    svg.setAttribute(
      "aria-label",
      t("common.bar.spend.cache.ring_label", { post: postName(biggest), percent: String(Math.round(share(biggest))) }),
    );
    const circle = (cls, dash, offset) => {
      const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("class", cls);
      c.setAttribute("cx", "21");
      c.setAttribute("cy", "21");
      c.setAttribute("r", "15.9155");
      c.setAttribute("fill", "none");
      if (dash) c.setAttribute("stroke-dasharray", dash);
      if (offset !== undefined) c.setAttribute("stroke-dashoffset", String(offset));
      return c;
    };
    svg.append(circle("bar-ring-track"));
    const shown = posts.filter((post) => share(post) > 0);
    let start = 0;
    for (const post of shown) {
      const length = share(post);
      const gap = shown.length > 1 ? Math.min(RING_GAP, length) : 0;
      svg.append(circle(`bar-ring-seg bar-ring-${post}`, `${length - gap} ${100 - length + gap}`, 25 - start));
      start += length;
    }
    const legend = document.createElement("ul");
    legend.className = "bar-ring-legend";
    for (const post of posts) {
      const item = document.createElement("li");
      const dot = document.createElement("i");
      dot.className = `bar-ring-dot bar-ring-${post}`;
      dot.setAttribute("aria-hidden", "true");
      const label = document.createElement("span");
      label.textContent = t("common.bar.spend.cache.ring_item", {
        post: postName(post),
        amount: money(col.ring[post] ?? 0),
        percent: String(Math.round(share(post))),
      });
      item.append(dot, label);
      legend.append(item);
    }
    box.append(svg, legend);
  }
  if (col.unpriced_calls > 0) {
    const note = document.createElement("p");
    note.className = "bar-flyout-note";
    note.textContent = t("common.bar.spend.cache.ring_unpriced", {
      calls: t("common.count.call", { count: col.unpriced_calls }),
    });
    box.append(note);
  }
  return box;
}

function cacheColumn(title, col, withSignal, showOneHour) {
  const section = document.createElement("section");
  section.className = "bar-cache-col";
  const head = document.createElement("h3");
  head.textContent = title;
  section.append(head);
  if (!(col.cache_calls > 0) && !(col.ring_calls > 0)) {
    const empty = document.createElement("p");
    empty.className = "bar-flyout-note";
    empty.textContent = t("common.bar.spend.cache.empty");
    section.append(empty);
    return section;
  }
  const cells = col.cache;
  const list = document.createElement("dl");
  list.className = "bar-cache-cells";
  const row = (name, text) => {
    const dt = document.createElement("dt");
    dt.textContent = t(`common.bar.spend.cache.${name}`);
    const dd = document.createElement("dd");
    dd.className = "number";
    dd.textContent = text;
    list.append(dt, dd);
  };
  row("read", cellText(cells.read, cells.read.tokens, false));
  // The 5 min write is the write less its 1 h part (a provider without detail: all 5 min).
  row("write_5m", cellText(cells.write, Math.max(0, cells.write.tokens - cells.write_1h.tokens), false));
  if (showOneHour) row("write_1h", cellText(cells.write_1h, cells.write_1h.tokens, false));
  row("uncached", cellText(cells.uncached, cells.uncached.tokens, col.cache_calls > 0));
  section.append(list);
  if (withSignal && writeSignal(col)) {
    const signal = document.createElement("p");
    signal.className = "bar-cache-signal";
    signal.setAttribute("role", "status");
    signal.textContent = t("common.bar.spend.cache.signal");
    section.append(signal);
  }
  const lines = [];
  if (col.cache_priced_calls > 0) {
    lines.push(
      t("common.bar.spend.cache.without_cache", {
        amount: money(col.total_usd + col.cache_saved_usd),
        calls: t("common.count.call", { count: col.cache_priced_calls }),
      }),
    );
  }
  if (col.kv_time_saved_s > 0) {
    lines.push(t("common.bar.spend.cache.time_saved", { seconds: kvSeconds(col.kv_time_saved_s) }));
  } else if (col.local_read_calls > 0) {
    lines.push(t("common.bar.spend.cache.time_unmeasured"));
  }
  for (const line of lines) {
    const note = document.createElement("p");
    note.className = "bar-flyout-note";
    note.textContent = line;
    section.append(note);
  }
  section.append(ringNode(col));
  return section;
}

function renderCacheBilan(c) {
  const anchor = $("bar-spend-detail");
  if (!anchor) return;
  let host = $("bar-cache-bilan");
  if (!host) {
    host = document.createElement("div");
    host.id = "bar-cache-bilan";
    host.className = "bar-cache-bilan";
    anchor.after(host);
  }
  const conversation = c.conversation;
  const counted = (col) => col && (col.cache_calls > 0 || col.ring_calls > 0);
  host.hidden = !counted(c) && !counted(conversation);
  if (host.hidden) return host.replaceChildren();
  const showOneHour = (c.cache?.write_1h?.declared ?? 0) > 0 || (conversation?.cache?.write_1h?.declared ?? 0) > 0;
  const title = document.createElement("h3");
  title.className = "bar-cache-title";
  title.textContent = t("common.bar.spend.cache.title");
  const columns = document.createElement("div");
  columns.className = "bar-cache-cols";
  if (conversation) {
    columns.append(cacheColumn(t("common.bar.spend.cache.conversation"), conversation, true, showOneHour));
  }
  columns.append(cacheColumn(t("common.bar.spend.cache.launch"), c, false, showOneHour));
  host.replaceChildren(title, columns);
}

// ---------- « Journal » ----------

function renderLog() {
  renderLogBadge();
  renderLogPanel();
}

function renderLogBadge() {
  const toggle = $("bar-log-toggle");
  if (!toggle) return;
  const count = $("bar-log-count");
  const n = deniedCount;
  count.textContent = t("common.bar.log.count", { count: n });
  count.hidden = n === 0;
  toggle.setAttribute(
    "aria-label",
    n === 0 ? t("common.bar.log.aria_label_zero") : t("common.bar.log.aria_label", { count: n }),
  );
}

// Story 1 (CAP-2): « Sécurité seulement » ne garde que les décisions de sécurité.
function filteredLog() {
  return securityOnly ? logEntries.filter((e) => e.kind === "security") : logEntries;
}

function renderLogPanel() {
  const list = $("bar-log-list");
  if (!list) return;
  const filtered = filteredLog();
  list.replaceChildren();
  if (filtered.length === 0) {
    const empty = document.createElement("p");
    empty.className = "bar-flyout-empty";
    empty.textContent = t("common.bar.log.empty");
    list.append(empty);
  } else {
    const shown = filtered.slice(0, logExpanded ? LOG_KEPT : LOG_PREVIEW);
    for (const entry of shown) list.append(logRow(entry));
  }
  renderLogMore(filtered.length);
}

// Décision Q2 : 5 lignes visibles, un historique dépliable pour les plus anciennes.
function renderLogMore(total) {
  const more = $("bar-log-more");
  if (!more) return;
  more.hidden = total <= LOG_PREVIEW;
  more.textContent = logExpanded ? t("common.bar.log.less") : t("common.bar.log.more");
  more.setAttribute("aria-expanded", String(logExpanded));
}

const LEVEL_OF = {
  allow: "low",
  allow_once: "low",
  passed: "low",
  partial: "low",
  deny: "high",
  blocked: "high",
  timeout: "high",
  masked: "mid",
  cancelled: "mid",
  flagged: "mid",
  error: "mid",
};

function logRow(entry) {
  const row = entry.kind === "model_call" ? modelCallRow(entry) : securityRow(entry);
  row.dataset.kind = entry.kind; // the E2E's handle on the filter and on duplicates
  if (entry.seq) row.dataset.seq = entry.seq;
  return row;
}

const DASH = () => t("common.bar.spend.cache.none"); // "—", already a glyph the app uses

function modelText(modele) {
  return modele ? `${modele.label} (${t(`main.hosting.${modele.hosting}`)})` : DASH();
}

function footprintText(empreinte) {
  if (!empreinte) return DASH(); // Décision Q4 : « — » seulement sans mesure
  return `${rangeText(empreinte.energy_wh_min, empreinte.energy_wh_max, "Wh")} · ${rangeText(empreinte.gco2e_min, empreinte.gco2e_max, "g CO₂e")}`;
}

// A local model costs nothing: « local », the free tier being an API's with no price.
function costText(coutUsd, modele) {
  if (coutUsd != null) return usd(coutUsd); // dollars, like the bar's amount (never a USD figure with a € sign)
  return `${shortUsd(0)} (${modele?.hosting === "local" ? t("main.hosting.local") : t("common.bar.log.free_tier")})`;
}

function modelCallRow(entry) {
  const row = document.createElement("li");
  row.className = "bar-log-row disclosure-row";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "bar-log-row-head disclosure-row-head";
  const chevron = document.createElement("span");
  chevron.className = "disclosure-row-chevron";
  chevron.setAttribute("aria-hidden", "true");
  chevron.textContent = "▸";
  const name = document.createElement("span");
  name.className = "disclosure-row-label";
  name.textContent = `${entry.onglet} · ${modelText(entry.modele)}`;
  button.append(chevron, name);
  const body = document.createElement("div");
  body.className = "disclosure-row-body";
  body.hidden = true;
  const p = document.createElement("p");
  p.textContent = t("common.bar.log.model_call_detail", {
    tokens_in: numberFormat({}).format(entry.tokens_in),
    tokens_out: numberFormat({}).format(entry.tokens_out),
    cost: costText(entry.cout_usd, entry.modele),
    footprint: footprintText(entry.empreinte),
    duration: numberFormat({ maximumFractionDigits: 1 }).format(entry.duree_ms / 1000),
  });
  body.append(p);
  button.addEventListener("click", () => {
    body.hidden = !body.hidden;
    button.setAttribute("aria-expanded", String(!body.hidden));
    chevron.classList.toggle("is-open", !body.hidden);
  });
  button.setAttribute("aria-expanded", "false");
  row.append(button, body);
  return row;
}

function securityRow(entry) {
  const row = document.createElement("li");
  row.className = "bar-log-row disclosure-row";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "bar-log-row-head disclosure-row-head";
  const chevron = document.createElement("span");
  chevron.className = "disclosure-row-chevron";
  chevron.setAttribute("aria-hidden", "true");
  chevron.textContent = "▸";
  const name = document.createElement("span");
  name.className = "disclosure-row-label";
  name.textContent = entry.label_text ?? entry.name; // story 10: the readable label
  const chip = document.createElement("span");
  chip.className = `status-chip status-chip-${LEVEL_OF[entry.decision] ?? "mid"}`;
  const key = `common.bar.log.decisions.${entry.decision}`;
  chip.textContent = has(key) ? t(key) : entry.decision; // `t` would show the key itself
  button.append(chevron, name, chip);
  const body = document.createElement("div");
  body.className = "disclosure-row-body";
  body.hidden = true;
  let when = entry.ts;
  try {
    when = dateTimeFormat({ timeStyle: "medium" }).format(new Date(entry.ts));
  } catch {
    // The raw ISO text stays rather than nothing.
  }
  const reason = document.createElement("p");
  reason.textContent = `${when} — ${entry.reason_text}`;
  body.append(reason);
  button.addEventListener("click", () => {
    body.hidden = !body.hidden;
    button.setAttribute("aria-expanded", String(!body.hidden));
    chevron.classList.toggle("is-open", !body.hidden);
  });
  button.setAttribute("aria-expanded", "false");
  row.append(button, body);
  return row;
}

// ---------- the two flyouts: non modal, one at a time ----------

const PANELS = [
  { toggle: "bar-spend-toggle", panel: "bar-spend-panel" },
  { toggle: "bar-log-toggle", panel: "bar-log-panel" },
];

function closeAll(returnFocus = null) {
  for (const { toggle, panel } of PANELS) {
    const btn = $(toggle);
    const flyout = $(panel);
    if (!btn || !flyout || flyout.hidden) continue;
    flyout.hidden = true;
    btn.setAttribute("aria-expanded", "false");
  }
  returnFocus?.focus();
}

function openPanel(toggleId, panelId) {
  const toggle = $(toggleId);
  const panel = $(panelId);
  if (!toggle || !panel) return;
  const opening = panel.hidden;
  closeAll();
  if (!opening) return; // it was the open one: the toggle above just closed it
  panel.hidden = false;
  toggle.setAttribute("aria-expanded", "true");
  refresh(); // fresh figures each time a panel opens (the four pages with no live feed)
}

function bind() {
  const spendToggle = $("bar-spend-toggle");
  const logToggle = $("bar-log-toggle");
  if (!spendToggle || !logToggle) return;
  spendToggle.addEventListener("click", (event) => {
    event.stopPropagation();
    openPanel("bar-spend-toggle", "bar-spend-panel");
  });
  logToggle.addEventListener("click", (event) => {
    event.stopPropagation();
    openPanel("bar-log-toggle", "bar-log-panel");
  });
  const securityFilter = $("bar-log-filter-security");
  securityFilter?.addEventListener("change", () => {
    securityOnly = securityFilter.checked;
    logExpanded = false;
    renderLogPanel();
  });
  const more = $("bar-log-more");
  more?.addEventListener("click", () => {
    logExpanded = !logExpanded;
    renderLogPanel();
  });
  for (const link of document.querySelectorAll(".bar-flyout-link[data-href]")) {
    link.addEventListener("click", () => {
      location.href = link.dataset.href;
    });
  }
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".bar-flyout") && !event.target.closest(".bar-button")) closeAll();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const open = PANELS.find(({ panel }) => $(panel) && !$(panel).hidden);
    if (!open) return;
    event.preventDefault();
    closeAll($(open.toggle));
  });
  restoreModelCalls();
  addEventListener("pagehide", saveModelCalls); // once per page, never per event
  ready.then(refresh);
}

bind();
