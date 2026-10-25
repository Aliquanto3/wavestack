// V1.2 story 19 (CAP-16, CAP-17), the "Fiches" tab: the component sheets and the architecture sheets,
// with the compliance sheet on seven axes. Declared content served by the session (AD-1, `/api/rag_lab/
// sheets`): the page asks for a sheet, receives it, draws it. Nothing is computed here. A level states
// an exposure in a word and a chip, never a verdict. Every text is drawn as text (`textContent`).

import { t } from "./i18n.js";
import { $, el, registerTab } from "./rag.js";

const sh = { body: null, current: null, asked: 0 };

const fill = (template, values = {}) => String(template ?? "").replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));

const tx = (path, values = {}) => {
  let value = sh.body?.texts;
  for (const key of path.split(".")) value = value?.[key];
  return typeof value === "string" ? fill(value, values) : "";
};

async function getJson(url) {
  try {
    const response = await fetch(url);
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

async function load() {
  const body = await getJson("/api/rag_lab/sheets");
  if (!body) return;
  sh.body = body;
  drawChrome();
  drawList();
  if (sh.current) await open(sh.current.type, sh.current.id);
  else $("rag-sh-sheet").replaceChildren();
}

function drawChrome() {
  $("rag-sh-banner").textContent = tx("banner_text");
  $("rag-sh-title").textContent = tx("title_text");
  $("rag-sh-hint").textContent = tx("hint_text");
  $("rag-sh-list").setAttribute("aria-label", tx("list_label_text"));
}

function entry(type, id, label, extra) {
  const button = el("button", "rag-sh-entry", label);
  button.type = "button";
  button.dataset.sheetType = type;
  button.dataset.sheetId = id;
  button.setAttribute("aria-pressed", String(sh.current?.type === type && sh.current?.id === id));
  if (extra) button.append(" ", el("span", "rag-badge", extra));
  button.addEventListener("click", () => open(type, id));
  return button;
}

function drawList() {
  const list = $("rag-sh-list");
  list.replaceChildren(el("h3", "rag-sh-group", tx("components_title_text")));
  const components = el("div", "rag-sh-entries");
  for (const c of sh.body.components) components.append(entry("component", c.key, `${c.kind_label_text} : ${c.label_text}`));
  list.append(components, el("p", "rag-note", sh.body.pending_text), el("h3", "rag-sh-group", tx("architectures_title_text")));
  const archs = el("div", "rag-sh-entries");
  for (const a of sh.body.architectures) {
    archs.append(entry("architecture", a.id, a.label_text, a.available ? null : tx("upcoming_text", { story: a.story })));
  }
  list.append(archs);
}

async function open(type, id) {
  sh.asked += 1;
  const asked = sh.asked;
  const sheet = await getJson(`/api/rag_lab/sheets/${type}/${encodeURIComponent(id)}`);
  if (asked !== sh.asked) return;
  sh.current = { type, id };
  for (const button of $("rag-sh-list").querySelectorAll(".rag-sh-entry")) {
    button.setAttribute("aria-pressed", String(button.dataset.sheetType === type && button.dataset.sheetId === id));
  }
  const box = $("rag-sh-sheet");
  box.dataset.sheet = `${type}.${id}`;
  if (!sheet) {
    box.replaceChildren(el("p", "rag-note", tx("error_text")));
    return;
  }
  box.replaceChildren(...(type === "component" ? componentNodes(sheet) : architectureNodes(sheet)));
}

function block(key, ...children) {
  const section = el("section", "rag-sh-block");
  section.dataset.block = key;
  section.append(el("h4", "rag-sh-block-title", tx(`blocks.${key}`)), ...children);
  return section;
}

function sourcesNode(sheet) {
  const wrap = el("div", "rag-sh-sources");
  if (sheet.sources?.length) {
    const list = el("ul", "rag-sh-source-list");
    for (const source of sheet.sources) {
      const link = el("a", "", source.label_text);
      link.href = source.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      const item = el("li");
      item.append(link);
      list.append(item);
    }
    wrap.append(el("h5", "rag-sh-sub", tx("sources_title_text")), list);
  }
  if (sheet.no_source_text) wrap.append(el("p", "rag-note", sheet.no_source_text));
  return wrap;
}

function fiveBlocks(sheet) {
  return [
    block("purpose", el("p", "", sheet.purpose_text)),
    block("when", el("p", "", sheet.when_text)),
    block("cost", el("p", "", sheet.cost_text)),
    block("literature", el("p", "", sheet.literature_text), sourcesNode(sheet)),
    block("bench", el("p", "", sheet.bench_text || tx("bench_empty_text"))),
  ];
}

function componentNodes(sheet) {
  return [el("h3", "rag-sh-name", `${sheet.kind_label_text} : ${sheet.label_text}`), ...fiveBlocks(sheet)];
}

function chip(level) {
  if (!level) return el("span", "rag-note", tx("no_level_text"));
  const node = el("span", `status-chip${level === "low" ? "" : ` status-chip-${level}`}`, t(`mcp.policy.risk.${level}`));
  node.dataset.level = level;
  return node;
}

// The link opens the Attack tab through the hash (`rag.js` listens to it), then brings the card to the screen.
function goTo(id, tries = 0) {
  const panel = $("rag-panel-attack");
  const target = document.getElementById(id);
  if (panel && !panel.hidden && target) {
    target.scrollIntoView({ block: "start" });
    target.tabIndex = -1;
    target.focus();
    return;
  }
  if (tries < 60) requestAnimationFrame(() => goTo(id, tries + 1));
}

function demoLink(axis) {
  const link = el("a", "rag-sh-demo", tx(`demo.${axis.id}`));
  link.href = "#attack";
  link.dataset.demo = axis.demo;
  link.addEventListener("click", () => goTo(axis.demo));
  return link;
}

function listOf(items) {
  const list = el("ul", "rag-sh-components");
  for (const text of items) list.append(el("li", "", text));
  return list;
}

function axisCell(axis) {
  const cell = el("td");
  cell.append(el("p", "rag-sh-axis-text", axis.text));
  if (axis.components) {
    cell.append(el("h5", "rag-sh-sub", tx("components_located_text")), listOf(axis.components.map((c) => `${tx(`components.${c.id}`)} : ${tx(`classes.${c.class}`)}`)));
  }
  if (axis.before_search !== undefined) cell.append(el("p", "rag-note", tx(axis.before_search ? "before_yes_text" : "before_no_text")));
  if (axis.places) {
    cell.append(
      el("h5", "rag-sh-sub", tx("places_title_text")),
      listOf(axis.places.map((p) => p.label_text)),
      el("p", "rag-note", `${tx("update_title_text")} : ${axis.update_text}`),
      el("p", "rag-note", tx("update_unmeasured_text")),
    );
  }
  return cell;
}

function complianceTable(sheet) {
  const table = el("table", "rag-sh-table");
  const head = el("tr");
  for (const key of ["axis", "level", "text", "link"]) {
    const th = el("th", "", tx(`columns.${key}`));
    th.setAttribute("scope", "col");
    head.append(th);
  }
  const thead = el("thead");
  thead.append(head);
  const body = el("tbody");
  for (const axis of sheet.axes) {
    const row = el("tr");
    row.dataset.axis = axis.id;
    const name = el("th", "", tx(`axes.${axis.id}`));
    name.setAttribute("scope", "row");
    const level = el("td");
    level.append(chip(axis.level));
    const link = el("td");
    if (axis.demo) link.append(demoLink(axis));
    row.append(name, level, axisCell(axis), link);
    body.append(row);
  }
  table.append(thead, body);
  return table;
}

function architectureNodes(sheet) {
  const nodes = [el("h3", "rag-sh-name", sheet.label_text)];
  if (!sheet.available) nodes.push(el("p", "rag-badge rag-sh-upcoming", tx("upcoming_text", { story: sheet.story })));
  nodes.push(...fiveBlocks(sheet));
  const compliance = block("compliance", el("p", "rag-eval-banner rag-sh-legal", sheet.banner_text), el("p", "rag-note", `${tx("levels_note_text")} ${tx("level_hint_text")}`), complianceTable(sheet));
  compliance.querySelector(".rag-sh-block-title").textContent = tx("compliance_title_text");
  nodes.push(compliance);
  return nodes;
}

registerTab("sheets", {
  show: () => (sh.body ? undefined : load()), // the page reloads on a language change
});
