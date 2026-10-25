// V1.2 story 4, tab « Comparer » (CAP-9): the pinned run kept as a small snapshot in the browser
// (it survives a reload), drawn beside the current run, row by row (search, context, answer,
// costs), the differences marked. Figures and strings are the session's (AD-1). Registered with
// the shell (`registerTab`); the pin button sits in the Build bar, wired here.

import { $, costFigures, el, fmtInt, keep, quote, registerTab, store, stored, text } from "./rag.js";

const PIN_KEY = "wavestack.ragLab.pin";
const RETRIEVAL_KINDS = ["vector_search", "lexical_search", "fusion", "rerank"];
let pin = null; // the pinned run's snapshot

// ----- the pin: a run kept as a small snapshot, drawn beside the current one -----

function loadPin() {
  try {
    const pin = JSON.parse(stored(PIN_KEY) ?? "null");
    return pin && typeof pin === "object" && Array.isArray(pin.stages) ? pin : null;
  } catch {
    return null;
  }
}

// A finished run as the comparison reads it: the question, the chain's names, each stage's
// passages (rank, title: no text), the prompt and the answer, the costs by time. Strings and
// figures of the session's events, none computed here (AD-1).
function snapshotOf(run, costs, update) {
  const stages = run.stages.map((s) => ({
    kind: s.kind,
    option: s.option,
    label_text: s.label_text,
    option_label_text: s.option_label_text,
    status: s.status,
    items: (s.ended?.items ?? []).map((i) => ({ key: `${i.doc_id}:${i.chunk_id}`, rank: i.rank, title_text: i.title_text })),
    prompt_text: s.ended?.prompt_text ?? null,
    output_text: s.kind === "generation" ? (s.ended?.output_text ?? "") : "",
  }));
  return {
    question: run.question,
    at: run.startedAt,
    stages,
    costs: { build: costs.build ?? null, update: update?.summary ?? null, query: costs.query ?? null },
  };
}

const runEndedWell = () => Boolean(store.run?.ended && store.run.ended.status === "ok");

function pinRun() {
  if (!runEndedWell()) return;
  pin = snapshotOf(store.run, store.costs, store.update);
  keep(PIN_KEY, JSON.stringify(pin));
  renderPin();
  renderCompare();
}

function unpinRun() {
  pin = null;
  try {
    localStorage.removeItem(PIN_KEY);
  } catch {
    // no storage: the pin lived with the page
  }
  renderPin();
  renderCompare();
}

function renderPin() {
  const ready = runEndedWell();
  const button = $("rag-pin");
  button.disabled = !ready;
  button.title = ready ? "" : text("compare.pin_wait_text");
  $("rag-pin-status").textContent = pin ? text("compare.pinned_status_text", { question: quote(pin.question) }) : "";
}

// The roles the comparison aligns the stages on, whatever the chains: the search (the last
// retrieval stage's list), the context (what the prompt receives), the answer.
function roleOf(snap, role) {
  if (role === "search") {
    const found = snap.stages.filter((s) => RETRIEVAL_KINDS.includes(s.kind) && s.items.length);
    return { items: found[found.length - 1]?.items ?? [] };
  }
  if (role === "context") return { items: snap.stages.find((s) => s.kind === "context")?.items ?? [] };
  const stage = snap.stages.find((s) => s.kind === "generation");
  return { items: [], answer: stage?.output_text ?? "", prompt: stage?.prompt_text ?? null };
}

function passageList(items, others, side) {
  const list = el("ol", "rag-cmp-passages");
  const known = new Set(others.map((i) => i.key));
  for (const item of items) {
    // What the other column lacks: lost (pinned side), added (current side).
    const apart = !known.has(item.key);
    const li = el("li", apart ? "is-apart" : "");
    li.dataset.key = item.key;
    li.append(el("span", "rag-num", fmtInt(item.rank)), el("span", "rag-doc-title", item.title_text));
    if (apart) li.append(el("span", `rag-cmp-mark is-${side}`, text(side === "pinned" ? "compare.lost_text" : "compare.added_text")));
    list.append(li);
  }
  if (!items.length) list.append(el("li", "rag-note", text("compare.none_text")));
  return list;
}

const COST_KEYS = ["tokens", "duration_ms", "usd", "energy_wh_min", "gco2e_min"];
const costDiffers = (a, b) => COST_KEYS.some((k) => (a?.[k] ?? null) !== (b?.[k] ?? null));

function cmpRow(role, title) {
  const row = el("section", "rag-cmp-row");
  row.dataset.role = role;
  const cells = el("div", "rag-cmp-cells");
  row.append(el("h4", "rag-cmp-row-title", title), cells);
  return { row, cells };
}

function cmpCell(side) {
  const cell = el("div", "rag-cmp-cell");
  cell.dataset.side = side;
  return cell;
}

function compareHead(side, snap) {
  const head = el("div", "rag-cmp-head");
  head.dataset.side = side;
  head.append(el("h3", "rag-cmp-side", text(side === "pinned" ? "compare.pinned_text" : "compare.current_text")));
  if (!snap) {
    head.append(el("p", "rag-note", text(side === "pinned" ? "compare.empty_pin_text" : "compare.empty_current_text")));
    return head;
  }
  const when = snap.at ? new Date(snap.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
  head.append(
    el("p", "rag-cmp-arch", snap.stages.map((s) => s.option_label_text).join(" → ")),
    el("p", "rag-cmp-question", quote(snap.question)),
    el("p", "rag-note", text("compare.at_text", { time: when })),
  );
  return head;
}

function passageRow(role, pinned, current) {
  const [a, b] = [roleOf(pinned, role), roleOf(current, role)];
  const { row, cells } = cmpRow(role, text(`compare.${role}_text`));
  const same = a.items.length === b.items.length && a.items.every((item, n) => item.key === b.items[n]?.key);
  row.classList.toggle("is-diff", !same);
  const left = cmpCell("pinned");
  const right = cmpCell("current");
  left.append(passageList(a.items, b.items, "pinned"));
  right.append(passageList(b.items, a.items, "current"));
  cells.append(left, right);
  row.append(el("p", "rag-note rag-cmp-verdict", text(same ? "compare.same_text" : "compare.differs_text")));
  return row;
}

function answerRow(pinned, current) {
  const parts = [roleOf(pinned, "answer"), roleOf(current, "answer")];
  const { row, cells } = cmpRow("answer", text("compare.answer_text"));
  row.classList.toggle("is-diff", parts[0].answer !== parts[1].answer);
  for (const [side, part] of [
    ["pinned", parts[0]],
    ["current", parts[1]],
  ]) {
    const cell = cmpCell(side);
    cell.append(el("p", "rag-cmp-answer", part.answer || text("compare.no_answer_text")));
    if (part.prompt) {
      const details = el("details", "rag-cmp-prompt");
      details.append(el("summary", "", text("compare.prompt_text")), el("pre", "rag-prompt", part.prompt));
      cell.append(details);
    }
    cells.append(cell);
  }
  return row;
}

function costsRow(pinned, current) {
  const { row, cells } = cmpRow("costs", text("compare.costs_text"));
  const left = cmpCell("pinned");
  const right = cmpCell("current");
  let anyDiff = false;
  for (const phase of ["build", "update", "query"]) {
    const a = pinned.costs?.[phase] ?? null;
    const b = current.costs?.[phase] ?? null;
    const diff = costDiffers(a, b);
    anyDiff = anyDiff || diff;
    for (const [cell, summary] of [
      [left, a],
      [right, b],
    ]) {
      const block = el("div", `rag-cmp-cost${diff ? " is-diff" : ""}`);
      block.dataset.phase = phase;
      block.append(el("h5", "rag-cost-title", text(`costs.${phase}_text`)));
      block.append(summary ? costFigures(summary) : el("p", "rag-note", text("costs.not_measured_text")));
      cell.append(block);
    }
  }
  row.classList.toggle("is-diff", anyDiff);
  cells.append(left, right);
  return row;
}

function renderCompare() {
  const box = $("rag-cmp");
  if (!box || !store.content) return;
  const pinned = pin;
  const current = runEndedWell() ? snapshotOf(store.run, store.costs, store.update) : null;
  $("rag-unpin").hidden = !pinned;
  const heads = el("div", "rag-cmp-heads");
  heads.append(compareHead("pinned", pinned), compareHead("current", current));
  const parts = [heads];
  if (pinned && current) {
    if (pinned.question !== current.question) parts.push(el("p", "rag-note rag-cmp-warning", text("compare.other_question_text")));
    parts.push(passageRow("search", pinned, current), passageRow("context", pinned, current), answerRow(pinned, current), costsRow(pinned, current));
  } else if (pinned || current) {
    parts.push(el("p", "rag-note", text(pinned ? "compare.need_current_text" : "compare.need_pin_text")));
  }
  box.replaceChildren(...parts);
}

function mount() {
  pin = loadPin();
  $("rag-pin").addEventListener("click", pinRun);
  $("rag-unpin").addEventListener("click", unpinRun);
}

function render() {
  renderPin();
  if (store.tab === "compare") renderCompare();
}

registerTab("compare", { mount, render, show: renderCompare });
