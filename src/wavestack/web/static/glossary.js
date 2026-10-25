// V1.5 story 6 (CAP-6): the harness glossary, opened by « Glossaire » in the navigation shared by
// the six pages (`#glossary-toggle`), read from `GET /api/glossary` (the setting's language).
//
// Citation syntax, shared with `wavestack.glossary.CITATION`: a text of a brick or of a scenario
// cites a term with `[[g:key]]` (shown as the term's name) or `[[g:key|displayed text]]`. Wherever
// such a text lands in the page, it becomes a button (`.glossary-cite`) that opens the glossary
// on that term; a key the glossary does not know stays as its displayed text.

import { ready, t } from "./i18n.js";

const CITATION = /\[\[g:([a-z][a-z0-9_]*)(?:\|([^\]]*))?\]\]/g;
const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "INPUT", "SELECT", "OPTION", "CODE", "PRE"]);

let terms = null; // [{key, term, definition}] once read, null while unknown
let loading = null;
let panel = null;
let opener = null;

const $ = (id) => document.getElementById(id);
const byKey = (key) => terms?.find((entry) => entry.key === key);

function load() {
  loading ??= fetch("/api/glossary")
    .then((response) => (response.ok ? response.json() : Promise.reject(new Error(response.status))))
    .then((body) => {
      terms = body.terms;
      citeAll(document.body);
      return terms;
    })
    .catch(() => {
      loading = null; // read again at the next opening
      return null;
    });
  return loading;
}

function build() {
  const root = document.createElement("div");
  root.id = "glossary-panel";
  root.className = "glossary-panel";
  root.setAttribute("role", "dialog");
  root.setAttribute("aria-modal", "false");
  root.setAttribute("aria-labelledby", "glossary-title");
  root.hidden = true;

  const head = document.createElement("div");
  head.className = "glossary-head";
  const title = document.createElement("h2");
  title.id = "glossary-title";
  title.textContent = t("common.glossary.title");
  const close = document.createElement("button");
  close.type = "button";
  close.id = "glossary-close";
  close.className = "bar-button";
  close.textContent = t("common.glossary.close");
  close.addEventListener("click", () => closeGlossary(true));
  head.append(title, close);

  const search = document.createElement("input");
  search.type = "search";
  search.id = "glossary-search";
  search.className = "glossary-search";
  search.setAttribute("aria-label", t("common.glossary.search"));
  search.placeholder = t("common.glossary.search");
  search.autocomplete = "off";
  search.addEventListener("input", renderList);

  const list = document.createElement("dl");
  list.id = "glossary-list";
  list.className = "glossary-list";

  root.append(head, search, list);
  root.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeGlossary(true);
    }
  });
  document.body.appendChild(root);
  return root;
}

const fold = (text) => text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

function renderList(focusKey = null) {
  const list = $("glossary-list");
  if (!list) return;
  list.replaceChildren();
  if (!terms) {
    const message = document.createElement("p");
    message.className = "glossary-empty";
    message.textContent = t("common.glossary.failed");
    list.appendChild(message);
    return;
  }
  const wanted = fold($("glossary-search").value.trim());
  const shown = [...terms]
    .sort((a, b) => a.term.localeCompare(b.term, document.documentElement.lang || undefined))
    .filter((entry) => !wanted || fold(`${entry.term} ${entry.definition}`).includes(wanted));
  if (!shown.length) {
    const none = document.createElement("p");
    none.className = "glossary-empty";
    none.textContent = t("common.glossary.empty");
    list.appendChild(none);
    return;
  }
  for (const entry of shown) {
    const name = document.createElement("dt");
    name.id = `glossary-term-${entry.key}`;
    name.dataset.term = entry.key;
    name.textContent = entry.term;
    const definition = document.createElement("dd");
    definition.textContent = entry.definition;
    list.append(name, definition);
  }
  if (typeof focusKey === "string") {
    const target = $(`glossary-term-${focusKey}`);
    target?.classList.add("glossary-current");
    target?.scrollIntoView({ block: "start" });
  }
}

/** Opens the glossary, on the term `key` when given. */
export async function openGlossary(key = null) {
  await ready;
  panel ??= build();
  opener = document.activeElement;
  panel.hidden = false;
  $("glossary-toggle")?.setAttribute("aria-expanded", "true");
  $("glossary-search").value = "";
  await load();
  renderList(key);
  if (!key) $("glossary-search").focus();
  else $("glossary-close").focus();
}

export function closeGlossary(returnFocus = false) {
  if (!panel || panel.hidden) return;
  panel.hidden = true;
  const toggle = $("glossary-toggle");
  toggle?.setAttribute("aria-expanded", "false");
  if (returnFocus) (opener?.isConnected ? opener : toggle)?.focus();
}

// ---------- citations ----------

function citeNode(node) {
  const text = node.nodeValue;
  CITATION.lastIndex = 0;
  if (!text.includes("[[g:") || !CITATION.test(text)) return;
  CITATION.lastIndex = 0;
  const parts = document.createDocumentFragment();
  let last = 0;
  for (const match of text.matchAll(CITATION)) {
    const [whole, key, shown] = match;
    const entry = byKey(key);
    parts.appendChild(document.createTextNode(text.slice(last, match.index)));
    last = match.index + whole.length;
    const label = shown?.trim() || entry?.term || key;
    if (!entry) {
      parts.appendChild(document.createTextNode(label));
      continue;
    }
    const cite = document.createElement("button");
    cite.type = "button";
    cite.className = "glossary-cite";
    cite.dataset.term = key;
    cite.title = entry.definition;
    cite.textContent = label;
    parts.appendChild(cite);
  }
  parts.appendChild(document.createTextNode(text.slice(last)));
  node.replaceWith(parts);
}

function citeAll(root) {
  if (!terms || !root) return;
  if (root.nodeType === Node.TEXT_NODE) {
    if (!SKIP.has(root.parentElement?.tagName) && !root.parentElement?.closest("#glossary-panel")) citeNode(root);
    return;
  }
  if (root.nodeType !== Node.ELEMENT_NODE || SKIP.has(root.tagName) || root.closest("#glossary-panel")) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) =>
      node.nodeValue.includes("[[g:") && !SKIP.has(node.parentElement?.tagName) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT,
  });
  const found = [];
  while (walker.nextNode()) found.push(walker.currentNode);
  for (const node of found) citeNode(node);
}

function bind() {
  const toggle = $("glossary-toggle");
  if (!toggle) return;
  toggle.addEventListener("click", () => (panel && !panel.hidden ? closeGlossary(true) : openGlossary()));
  document.addEventListener("click", (event) => {
    const cite = event.target.closest?.(".glossary-cite");
    if (cite) openGlossary(cite.dataset.term);
  });
  // Texts arrive after load (bricks, scenarios, turns): cite what is added or rewritten.
  new MutationObserver((records) => {
    if (!terms) return;
    for (const record of records) {
      if (record.type === "characterData") citeAll(record.target);
      else for (const added of record.addedNodes) citeAll(added);
    }
  }).observe(document.body, { childList: true, subtree: true, characterData: true });
  ready.then(load);
}

bind();
