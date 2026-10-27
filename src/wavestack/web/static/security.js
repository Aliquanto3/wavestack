// Story 10 (CAP-3, CAP-8, CAP-9): the page Sécurité. A single read of `/api/security` (the
// question cards, the risk matrix, the active controls) and of `/api/security_journal` (the
// full journal) at load; after that, each `security_event` of the shared stream is applied
// in O(1) (a new row prepended, the two decision-based question cards replaced by the ones the
// event carries, rendered by the server from the session's counters), never a re-fetch nor a
// walk of the growing journal. The stream replays the session from its start, so nothing
// recorded between the load and its opening is lost; an entry's rank `n` drops the ones the
// loaded journal already shows.

import { dateTimeFormat, has, ready, t } from "./i18n.js";
import { BAR_MODEL_KINDS, feedBar } from "./bar.js";

const $ = (id) => document.getElementById(id);

const KEPT = 500; // the server journal's window (`security_log._KEPT`): the list never grows past it
let cardsTotal = 0; // the session's entry count the two movable cards reflect
let lastN = 0; // the rank of the newest journal row shown
let discIds = 0;

function chipClass(level) {
  return level === "low" ? "" : ` status-chip-${level}`;
}

function chip(text, level) {
  const el = document.createElement("span");
  el.className = `status-chip${chipClass(level)}`;
  el.textContent = text;
  return el;
}

function ruleText(rule) {
  return rule === "mixed" ? t("security.matrix.rule_mixed") : t(`mcp.policy.rule.${rule}`);
}

// Story 16.7 (CAP-10): a single affordance for everything clickable (cursor, hover and
// focus by `pages.css`'s rules on `.sec-question-card`, `.call-step`, `.filter-chip` and
// `.mx-toggle`); the focus follows a card's or a step's scroll, never only the scroll.
function goTo(sectionId) {
  const target = $(sectionId);
  if (!target) return;
  target.scrollIntoView({ behavior: "smooth", block: "start" });
  target.focus({ preventScroll: true });
}

// ---------- the 4 question cards (now buttons, each leading to its answer) ----------

function questionCard(ask, count, detailText, alert, goText, onClick) {
  const el = document.createElement("button");
  el.type = "button";
  el.className = "sec-question-card";
  const askEl = document.createElement("span");
  askEl.className = "sec-question-ask";
  askEl.textContent = ask;
  const figure = document.createElement("span");
  figure.className = `sec-question-figure${alert ? " alert" : ""}`;
  figure.textContent = String(count);
  const detail = document.createElement("span");
  detail.className = "sec-question-detail";
  detail.textContent = detailText;
  const go = document.createElement("span");
  go.className = "sec-question-go";
  go.textContent = goText;
  el.append(askEl, figure, detail, go);
  el.addEventListener("click", onClick);
  return el;
}

function renderQuestions(q) {
  const box = $("sec-questions");
  if (!box) return;
  box.replaceChildren(
    questionCard(t("security.questions.can_write"), q.can_write.count, q.can_write.detail_text, false, t("security.questions.go_matrix"), () => {
      setMatrixFilter("write");
      goTo("h-sec-matrix");
    }),
    questionCard(t("security.questions.authorized_by_you"), q.authorized_by_you.count, q.authorized_by_you.detail_text, false, t("security.questions.go_journal"), () => {
      setJournalFilter("allow_once");
      goTo("h-sec-journal");
    }),
    questionCard(t("security.questions.blocked"), q.blocked.count, q.blocked.detail_text, q.blocked.count > 0, t("security.questions.go_journal"), () => {
      setJournalFilter("refused");
      goTo("h-sec-journal");
    }),
    questionCard(t("security.questions.not_covered"), q.not_covered.count, q.not_covered.detail_text, false, t("security.questions.go_limits"), () => goTo("h-sec-limits")),
  );
}

// Replaces only the « qui a autorisé » and « bloqué » cards by the ones a live event carries
// (O(1): the other two cards, from the policy and the content, never change from an event).
function renderMovableQuestions(q) {
  const box = $("sec-questions");
  if (!box || box.children.length < 4) return;
  box.children[1].replaceWith(
    questionCard(t("security.questions.authorized_by_you"), q.authorized_by_you.count, q.authorized_by_you.detail_text, false, t("security.questions.go_journal"), () => {
      setJournalFilter("allow_once");
      goTo("h-sec-journal");
    }),
  );
  box.children[2].replaceWith(
    questionCard(t("security.questions.blocked"), q.blocked.count, q.blocked.detail_text, q.blocked.count > 0, t("security.questions.go_journal"), () => {
      setJournalFilter("refused");
      goTo("h-sec-journal");
    }),
  );
}

// ---------- the path of a message (call-path, 5 steps; 2 static, 3 lead to their section) ----------

function callStep(title, text, state, goText, onClick) {
  const el = document.createElement(onClick ? "button" : "div");
  el.type = onClick ? "button" : undefined;
  el.className = `call-step${onClick ? "" : " is-static"}`;
  if (!onClick) el.tabIndex = -1;
  const titleEl = document.createElement("span");
  titleEl.className = "call-step-title";
  titleEl.textContent = title;
  const textEl = document.createElement("span");
  textEl.className = "call-step-text";
  textEl.textContent = text;
  el.append(titleEl, textEl);
  if (state) {
    const stateEl = document.createElement("span");
    stateEl.className = "call-step-state";
    stateEl.append(...state);
    el.append(stateEl);
  }
  if (goText) {
    const go = document.createElement("span");
    go.className = "call-step-go";
    go.textContent = goText;
    el.append(go);
  }
  if (onClick) el.addEventListener("click", onClick);
  const li = document.createElement("li");
  li.append(el);
  return li;
}

function ruleCountsText(tr) {
  return [
    tr.allow_count ? t("security.controls.allow_count", { count: tr.allow_count }) : null,
    tr.ask_count ? t("security.controls.ask_count", { count: tr.ask_count }) : null,
    tr.deny_count ? t("security.controls.deny_count", { count: tr.deny_count }) : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

function renderPath(controls, counts) {
  const list = $("sec-path");
  if (!list) return;
  const guardrailChips = controls.guardrails.map((g) => {
    const level = g.status === "active" ? (g.mode === "block" ? "high" : "mid") : "off";
    const text = (g.modes ?? []).find((m) => m.id === g.mode)?.label_text ?? t(`main.bricks.status.${g.status}`);
    return chip(text, level);
  });
  list.replaceChildren(
    callStep(t("security.path.message.title"), t("security.path.message.text")),
    callStep(t("security.path.guardrails.title"), t("security.path.guardrails.text"), guardrailChips, t("security.path.guardrails.go"), () => goTo("h-sec-controls")),
    callStep(t("security.path.model.title"), t("security.path.model.text")),
    callStep(t("security.path.rule.title"), t("security.path.rule.text"), [sub(ruleCountsText(controls.tool_rules))], t("security.path.rule.go"), () => goTo("h-sec-matrix")),
    callStep(t("security.path.journal.title"), t("security.path.journal.text"), [sub(t("security.path.events", { count: counts.total }))], t("security.path.journal.go"), () => goTo("h-sec-journal")),
  );
}

// ---------- the risk matrix (each row dépliable: its own tools, and why the risk) ----------

let matrixFilter = "all";

function setMatrixFilter(value) {
  matrixFilter = value;
  const filters = $("sec-matrix-filters");
  if (filters) {
    filters.querySelectorAll("[data-mx]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mx === value)));
  }
  $("sec-matrix-body")
    ?.querySelectorAll("tr")
    .forEach((row) => {
      row.hidden = value === "write" && row.dataset.write !== "true";
    });
}

function matrixRow(row) {
  const id = `sec-mx-${row.id}`;
  const tr = document.createElement("tr");
  tr.dataset.write = String(row.write);
  const tool = document.createElement("td");
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "mx-toggle";
  toggle.setAttribute("aria-expanded", "false");
  toggle.setAttribute("aria-controls", id);
  const chevron = document.createElement("span");
  chevron.className = "disclosure-row-chevron";
  chevron.setAttribute("aria-hidden", "true");
  chevron.textContent = "▸";
  toggle.append(chevron, row.label_text);
  tool.append(toggle);
  if (row.write) {
    const write = document.createElement("span");
    write.className = "mx-write";
    write.setAttribute("aria-hidden", "true"); // decorative: `nature_text` already says « écriture »
    write.textContent = "✎";
    tool.append(write);
  }
  const nature = document.createElement("td");
  nature.textContent = row.nature_text;
  const risk = document.createElement("td");
  risk.append(chip(t(`mcp.policy.risk.${row.risk}`), row.risk));
  const rule = document.createElement("td");
  rule.textContent = ruleText(row.rule);
  tr.append(tool, nature, risk, rule);

  const detailTr = document.createElement("tr");
  detailTr.className = "mx-detail";
  detailTr.hidden = true;
  const detailTd = document.createElement("td");
  detailTd.colSpan = 4;
  const body = document.createElement("div");
  body.className = "mx-detail-body";
  body.id = id;
  const why = document.createElement("p");
  const strong = document.createElement("strong");
  strong.textContent = t("security.matrix.why_label");
  why.append(strong, ` ${t(`security.matrix.${row.id}.why`)}`);
  body.append(why);
  if (row.tools.length) body.append(...kv(row.tools.map((tool2) => [tool2.label_text, ruleText(tool2.rule)])));
  detailTd.append(body);
  detailTr.append(detailTd);

  toggle.addEventListener("click", () => {
    detailTr.hidden = !detailTr.hidden;
    toggle.setAttribute("aria-expanded", String(!detailTr.hidden));
    chevron.classList.toggle("is-open", !detailTr.hidden);
  });
  return [tr, detailTr];
}

function renderMatrix(rows) {
  const body = $("sec-matrix-body");
  if (!body) return;
  body.replaceChildren(...rows.flatMap(matrixRow));
  setMatrixFilter(matrixFilter);
  const legend = $("sec-matrix-legend");
  if (legend) {
    legend.replaceChildren(
      legendEntry(chip(t("mcp.policy.rule.allow"), "low"), t("security.matrix.legend_allow")),
      legendEntry(chip(t("mcp.policy.rule.ask"), "mid"), t("security.matrix.legend_ask")),
      legendEntry(chip(t("mcp.policy.rule.deny"), "high"), t("security.matrix.legend_deny")),
    );
  }
}

function legendEntry(chipEl, text) {
  const span = document.createElement("span");
  span.append(chipEl, ` ${text}`);
  return span;
}

// ---------- disclosure rows (the single pattern for technical detail, DESIGN.md) ----------

function discRow(label, badge, bodyNodes, whatText) {
  const li = document.createElement("li");
  li.className = "sec-row disclosure-row";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "sec-row-head disclosure-row-head";
  const chevron = document.createElement("span");
  chevron.className = "disclosure-row-chevron";
  chevron.setAttribute("aria-hidden", "true");
  chevron.textContent = "▸";
  const name = document.createElement("span");
  name.className = "disclosure-row-label";
  name.textContent = label;
  if (whatText) {
    const small = document.createElement("small");
    small.textContent = whatText;
    name.append(small);
  }
  button.append(chevron, name);
  if (badge) button.append(badge);
  const body = document.createElement("div");
  body.className = "disclosure-row-body";
  body.id = `sec-disc-${++discIds}`;
  body.hidden = true;
  button.setAttribute("aria-controls", body.id);
  body.append(...bodyNodes);
  button.addEventListener("click", () => {
    body.hidden = !body.hidden;
    button.setAttribute("aria-expanded", String(!body.hidden));
    chevron.classList.toggle("is-open", !body.hidden);
  });
  button.setAttribute("aria-expanded", "false");
  li.append(button, body);
  return li;
}

function kv(pairs) {
  const dl = document.createElement("dl");
  for (const [key, value] of pairs) {
    const dt = document.createElement("dt");
    dt.textContent = key;
    const dd = document.createElement("dd");
    dd.textContent = value;
    dl.append(dt, dd);
  }
  return [dl];
}

function sub(text) {
  const span = document.createElement("span");
  span.className = "sec-row-sub";
  span.textContent = text;
  return span;
}

function link(text, href) {
  const a = document.createElement("a");
  a.className = "button-secondary";
  a.href = href;
  a.textContent = text;
  return a;
}

function groupHeading(text) {
  const p = document.createElement("p");
  const strong = document.createElement("strong");
  strong.textContent = text;
  p.append(strong);
  return p;
}

// ---------- the active controls ----------

function whatText(id) {
  const key = `security.controls.what.${id}`;
  return has(key) ? t(key) : undefined;
}

function renderControls(controls) {
  const list = $("sec-controls");
  if (!list) return;
  const rows = [];

  // Every effective rule, grouped by server (a reviewer's fix: the list used to name only
  // local tools, missing GitHub and its live overrides from the matrix).
  const tr = controls.tool_rules;
  const trBits = [`${tr.count}`];
  if (tr.allow_count) trBits.push(t("security.controls.allow_count", { count: tr.allow_count }));
  if (tr.ask_count) trBits.push(t("security.controls.ask_count", { count: tr.ask_count }));
  if (tr.deny_count) trBits.push(t("security.controls.deny_count", { count: tr.deny_count }));
  const localTools = tr.tools.filter((tool) => tool.id.startsWith("local__"));
  const githubTools = tr.tools.filter((tool) => tool.id.startsWith("github__"));
  rows.push(
    discRow(
      t("security.controls.tool_rules"),
      sub(trBits.join(" · ")),
      [
        groupHeading(t("security.controls.group_local")),
        ...kv(localTools.map((tool) => [tool.label_text, ruleText(tool.rule)])),
        groupHeading(tr.network_label_text),
        ...kv([[tr.network_label_text, ruleText(tr.network_rule)]]),
        groupHeading(t("security.controls.group_github")),
        ...kv(githubTools.map((tool) => [tool.label_text, ruleText(tool.rule)])),
        ...kv([[t("security.controls.github_write_other"), ruleText("deny")]]),
        link(t("security.matrix.settle_link"), "/mcp"),
      ],
      whatText("tool_rules"),
    ),
  );

  for (const g of controls.guardrails) {
    const level = g.status === "active" ? (g.mode === "block" ? "high" : "mid") : "off";
    // The mode's own label from the card (`_guardrails_card`), else the brick's status text:
    // never a raw key.
    const statusKey = has(`main.bricks.status.${g.status}`) ? `main.bricks.status.${g.status}` : "main.bricks.status.unavailable";
    const text = (g.modes ?? []).find((m) => m.id === g.mode)?.label_text ?? t(statusKey);
    const body = g.install_text
      ? kv([[t("security.limits.reason_label"), g.install_text]])
      : kv([[t("security.controls.guardrail_mode_label"), text]]);
    rows.push(discRow(g.label_text, chip(text, level), [...body, link(t("security.controls.change_in_bricks"), "/")], whatText(g.id)));
  }

  const enabledHooks = controls.hooks.filter((h) => h.enabled);
  const hooksBody = controls.hooks.length
    ? kv(
        controls.hooks.map((h) => [
          h.label_text,
          t(h.enabled ? "security.controls.hook_active" : "security.controls.hook_inactive"),
        ]),
      )
    : kv([[t("security.controls.hooks"), t("security.controls.hooks_empty")]]);
  rows.push(discRow(t("security.controls.hooks"), sub(String(enabledHooks.length)), hooksBody, whatText("hooks")));

  const whitelistBody = controls.network_whitelist.length
    ? kv([[t("security.controls.network_whitelist"), controls.network_whitelist.join(" · ")]])
    : kv([[t("security.controls.network_whitelist"), t("security.controls.network_whitelist_empty")]]);
  rows.push(
    discRow(
      t("security.controls.network_whitelist"),
      sub(t("security.controls.domain_count", { count: controls.network_whitelist.length })),
      whitelistBody,
      whatText("network_whitelist"),
    ),
  );

  const gh = controls.github;
  const ghLevel = gh.status === "connected" ? "low" : gh.status === "expired" || gh.status === "error" ? "high" : "off";
  const ghDetail = [[t("security.controls.github_scope_label"), gh.scope], [t("security.controls.github_server_label"), gh.server]];
  if (gh.expires_in_s != null) {
    const hours = Math.floor(gh.expires_in_s / 3600);
    ghDetail.unshift([t("security.controls.github"), t("security.controls.github_expires", { time: `${hours} h` })]);
  }
  rows.push(
    discRow(t("security.controls.github"), chip(t(`security.controls.github_states.${gh.status}`), ghLevel), kv(ghDetail), whatText("github")),
  );

  list.replaceChildren(...rows);
}

// ---------- the full journal (growing; a live event only prepends, never a re-walk) ----------

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
  not_installed: "mid",
  error: "mid",
};

// Story 16.7 (CAP-10): the journal's own filters (« Tout », « Refusés et bloqués », «
// Autorisés par vous »), the same decisions the barre's red count already uses
// (`security_log._DENIED`), so the chip's own count never drifts from the badge's.
const REFUSED = new Set(["deny", "blocked"]);
let journalFilter = "all";

function journalMatches(decision, filter) {
  if (filter === "all") return true;
  return filter === "refused" ? REFUSED.has(decision) : decision === filter;
}

function setJournalFilter(value) {
  journalFilter = value;
  const filters = $("sec-journal-filters");
  if (filters) filters.querySelectorAll("[data-f]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.f === value)));
  $("sec-journal")
    ?.querySelectorAll("li[data-decision]")
    .forEach((li) => {
      li.hidden = !journalMatches(li.dataset.decision, value);
    });
}

function renderJournalFilters(counts) {
  const filters = $("sec-journal-filters");
  if (!filters) return;
  filters.querySelector('[data-f="all"]').textContent = t("security.journal.filters.all", { count: counts.total });
  filters.querySelector('[data-f="refused"]').textContent = t("security.journal.filters.refused", { count: counts.denied_count });
  filters.querySelector('[data-f="allow_once"]').textContent = t("security.journal.filters.allow_once", { count: counts.allow_once_count });
}

function journalRow(entry) {
  let when = entry.ts;
  try {
    when = dateTimeFormat({ timeStyle: "medium" }).format(new Date(entry.ts));
  } catch {
    // The raw ISO text stays rather than nothing.
  }
  const key = `common.bar.log.decisions.${entry.decision}`;
  const badge = chip(has(key) ? t(key) : entry.decision, LEVEL_OF[entry.decision] ?? "mid");
  const p = document.createElement("p");
  p.textContent = entry.reason_text;
  const li = discRow(`${when} — ${entry.label_text}`, badge, [p]);
  li.dataset.decision = entry.decision;
  li.hidden = !journalMatches(entry.decision, journalFilter);
  return li;
}

function renderJournal(entries) {
  const list = $("sec-journal");
  if (!list) return;
  if (entries.length === 0) {
    const empty = document.createElement("li");
    empty.className = "sec-empty";
    empty.textContent = t("security.journal.empty");
    list.replaceChildren(empty);
    return;
  }
  list.replaceChildren(...entries.map(journalRow));
}

function prependJournalRow(entry) {
  const list = $("sec-journal");
  if (!list) return;
  if (list.firstElementChild?.classList.contains("sec-empty")) list.replaceChildren();
  list.prepend(journalRow(entry));
  if (list.children.length > KEPT) list.lastElementChild.remove();
}

// ---------- the limits ----------

function renderLimits(limits) {
  const list = $("sec-limits");
  if (!list) return;
  list.replaceChildren(
    ...limits.map((limit) =>
      discRow(limit.statement_text, null, kv([
        [t("security.limits.reason_label"), limit.reason_text],
        [t("security.limits.production_label"), limit.production_text],
      ])),
    ),
  );
}

// ---------- the affordance legend (repliée par défaut) ----------

function renderLegend() {
  const list = $("sec-legend");
  if (!list) return;
  const ul = document.createElement("ul");
  ul.className = "legend-list";
  for (const key of ["disclosure", "card", "filter", "action", "static"]) {
    const li = document.createElement("li");
    li.textContent = t(`security.legend.${key}`);
    ul.append(li);
  }
  list.replaceChildren(discRow(t("security.legend.label"), null, [ul], t("security.legend.sub")));
}

// ---------- filter chips (matrice et journal), wired once, both widgets static in the HTML ----------

function setupFilters() {
  $("sec-matrix-filters")
    ?.querySelectorAll("[data-mx]")
    .forEach((b) => b.addEventListener("click", () => setMatrixFilter(b.dataset.mx)));
  $("sec-journal-filters")
    ?.querySelectorAll("[data-f]")
    .forEach((b) => b.addEventListener("click", () => setJournalFilter(b.dataset.f)));
}

// ---------- load, then live ----------

async function load() {
  const [security, journal] = await Promise.all([
    fetch("/api/security").then((r) => r.json()),
    fetch("/api/security_journal").then((r) => r.json()),
  ]);
  renderQuestions(security.questions);
  renderPath(security.controls, security.counts);
  renderMatrix(security.risk_matrix);
  renderControls(security.controls);
  renderJournalFilters(security.counts);
  renderLimits(security.limits);
  renderJournal(journal.entries.slice().reverse()); // newest first
  // The session's own counters (past the journal's 500-entry window), never a recount.
  cardsTotal = security.counts.total;
  lastN = journal.entries.at(-1)?.n ?? 0;
}

function openStream() {
  const source = new EventSource("/api/diagnostic/stream");
  source.addEventListener("consumption_updated", (event) => feedBar(JSON.parse(event.data)));
  // Story 1 (CAP-2): the Journal's model calls, and the model each one ran on.
  for (const kind of BAR_MODEL_KINDS) source.addEventListener(kind, (event) => feedBar(JSON.parse(event.data)));
  source.addEventListener("security_event", (event) => {
    const envelope = JSON.parse(event.data);
    feedBar(envelope);
    const entry = envelope.payload;
    if (entry.n > lastN) {
      lastN = entry.n;
      prependJournalRow(entry);
    }
    if (entry.total > cardsTotal) {
      cardsTotal = entry.total;
      renderMovableQuestions(entry.questions);
      renderJournalFilters(entry);
    }
  });
}

async function main() {
  await ready; // the page's texts and formats in the session's language (languages 4/5)
  setupFilters();
  renderLegend();
  await load();
  openStream();
}

main();
