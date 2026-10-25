// V1.2 story 18 (CAP-14), the "Effacement" card of the Attack tab. The figures are the session's
// (`/api/rag_lab/erasure`, AD-1): the page sends its own state (the sentinel's activation, the step,
// the architectures rebuilt) with every request, receives the table of places and draws it. The state
// lives here and is lost at reload. Registered under its own key, with a single `mount` hook (GET of
// the texts and the default state, no computation): the "attack" tab is never registered again, it
// would replace the hooks of the story 17. Every text is drawn as text (`textContent`).

import { $, el, registerTab } from "./rag.js";

const er = {
  body: null, // the last answer of `GET /api/rag_lab/erasure`
  result: null, // the last answer of `POST /api/rag_lab/erasure`
  sentinel: false,
  step: "idle",
  rebuilt: [],
  asked: 0,
};

const fill = (template, values = {}) => String(template ?? "").replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));

const t = (path, values = {}) => {
  let value = er.body?.texts;
  for (const key of path.split(".")) value = value?.[key];
  return typeof value === "string" ? fill(value, values) : "";
};

async function load() {
  try {
    const response = await fetch("/api/rag_lab/erasure");
    if (response.ok) er.body = await response.json();
  } catch {
    er.body = null;
  }
  drawControls();
  await run();
}

async function run() {
  if (!er.body) return;
  er.asked += 1;
  const asked = er.asked;
  const payload = { sentinel_active: er.sentinel, step: er.step, rebuilt: er.step === "rebuild" ? er.rebuilt : [] };
  let answer = null;
  try {
    const response = await fetch("/api/rag_lab/erasure", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    answer = response.ok ? await response.json() : null;
  } catch {
    answer = null;
  }
  if (asked !== er.asked) return; // a late answer does not overwrite a newer one
  er.result = answer;
  drawResult();
}

function drawControls() {
  if (!er.body) return;
  $("rag-era-banner").textContent = t("banner_text");
  $("rag-era-title").textContent = t("title_text");
  $("rag-era-hint").textContent = t("hint_text");
  $("rag-era-sentinel-label").textContent = t("sentinel_label_text", { title: er.body.doc.title_text });
  $("rag-era-sentinel").checked = er.sentinel;
  $("rag-era-sentinel-state").textContent = er.sentinel ? t("sentinel_active_text") : t("sentinel_inactive_text");
  $("rag-era-scope").textContent = `${t("scope_text")} ${t("code_text", { code: er.body.code })}`;
  $("rag-era-build").textContent = t("build_text");
  $("rag-era-erase").textContent = t("erase_text");
  $("rag-era-build").disabled = !er.sentinel;
  $("rag-era-erase").disabled = !er.sentinel || er.step === "idle";
  $("rag-era-limits").replaceChildren(...(er.body.texts.limits ?? []).map((line) => el("li", "", line)));
  drawRebuildButtons();
}

function drawRebuildButtons() {
  const erased = er.sentinel && (er.step === "erase" || er.step === "rebuild");
  $("rag-era-rebuild-box").hidden = !erased;
  $("rag-era-rebuild-title").textContent = t("rebuild_title_text");
  $("rag-era-rebuild").replaceChildren(
    ...er.body.architectures.map((a) => {
      const done = er.rebuilt.includes(a.id);
      const label = t("rebuild_text", { architecture: a.label_text }) + (done ? ` (${t("rebuilt_done_text")})` : "");
      const button = el("button", "rag-button-secondary", label);
      button.type = "button";
      button.dataset.architecture = a.id;
      button.setAttribute("aria-pressed", String(done));
      button.addEventListener("click", () => rebuild(a.id));
      return button;
    }),
  );
}

function rebuild(id) {
  if (!er.rebuilt.includes(id)) er.rebuilt = [...er.rebuilt, id];
  er.step = "rebuild";
  drawControls();
  run();
}

function tableNode(places) {
  const table = el("table", "rag-era-table");
  const head = el("tr");
  for (const key of ["place_header_text", "architecture_header_text", "status_header_text"]) head.append(el("th", "", t(key)));
  const thead = el("thead");
  thead.append(head);
  table.append(thead);
  const body = el("tbody");
  for (const place of places) {
    place.rows.forEach((row, index) => {
      const tr = el("tr");
      tr.dataset.place = place.id;
      tr.dataset.architecture = row.architecture;
      if (index === 0) {
        const th = el("th", "", place.label_text);
        th.scope = "rowgroup";
        th.rowSpan = place.rows.length;
        if (place.kind === "measured") th.append(" ", el("span", "rag-note", `(${t("measured_text")})`));
        if (place.illustrative_text) th.append(el("span", "rag-era-illustrative", place.illustrative_text));
        tr.append(th);
      }
      const arch = el("td", "", row.architecture_text);
      if (row.upcoming_text) arch.append(" ", el("span", "rag-note", `(${row.upcoming_text})`));
      tr.append(arch);
      const status = el("td");
      const word = el("span", "rag-era-status", place.status_text);
      word.dataset.status = place.status;
      status.append(word, el("span", "rag-note", ` — ${place.hits_text}`));
      if (place.shared_text) status.append(" ", el("span", "rag-note", `(${place.shared_text})`));
      if (place.status_note_text) status.append(el("span", "rag-era-status-note", place.status_note_text));
      tr.append(status);
      body.append(tr);
    });
  }
  table.append(body);
  return table;
}

function drawResult() {
  const result = er.result;
  const built = !!result && result.step !== "idle";
  $("rag-era-table-box").hidden = !built;
  const guard = $("rag-era-guard");
  guard.textContent = result?.guard_text ?? "";
  guard.hidden = !result?.guard_text;
  if (!result || !er.body) return;
  $("rag-era-step").textContent = t(`step_text.${result.step}`);
  const c = result.corpus;
  $("rag-era-corpus").textContent = t("corpus_text", { docs: c.documents, chunks: c.passages, size: c.max_chars, sentinel: c.sentinel_passages });
  if (!built) return;
  $("rag-era-table-title").textContent = t("table_title_text");
  $("rag-era-table").replaceChildren(tableNode(result.places));
  $("rag-era-vectors").textContent = t("vectors_text");
  const costs = $("rag-era-costs");
  costs.replaceChildren();
  if (result.costs.length) {
    costs.append(el("h4", "rag-cost-title", t("costs_title_text")));
    const list = el("ul", "rag-atk-list");
    list.append(...result.costs.map((cost) => el("li", "", cost.text)));
    costs.append(list);
  }
  $("rag-era-question-title").textContent = t("question_title_text");
  $("rag-era-question").textContent = t("question_text", { code: result.code });
  drawQuestion(result.results);
}

function drawQuestion(results) {
  const area = $("rag-era-results");
  area.replaceChildren(el("h5", "rag-cost-title", t("ranking_title_text")));
  if (!results.ranking.length) {
    area.append(el("p", "rag-note", t("ranking_none_text")));
  } else {
    const list = el("ul", "rag-atk-list");
    for (const p of results.ranking) {
      const item = el("li");
      item.append(el("strong", "", t("passage_text", { rank: p.rank, title: p.title_text, position: p.position, score: p.score })), el("p", "rag-atk-text", p.text));
      list.append(item);
    }
    area.append(list);
  }
  area.append(el("h5", "rag-cost-title", t("holding_title_text")));
  if (!results.holding.length) {
    area.append(el("p", "rag-note", t("holding_none_text")));
    return;
  }
  const list = el("ul", "rag-atk-list");
  for (const h of results.holding) {
    const item = el("li");
    item.dataset.place = h.place;
    item.append(el("strong", "", `${h.label_text} — ${h.status_text}`), el("p", "rag-atk-text", h.text));
    list.append(item);
  }
  area.append(list);
}

function setStep(step) {
  er.step = step;
  er.rebuilt = [];
  drawControls();
  run();
}

function wire() {
  $("rag-era-sentinel").addEventListener("change", (event) => {
    er.sentinel = event.target.checked;
    er.step = "idle";
    er.rebuilt = [];
    drawControls();
    run();
  });
  $("rag-era-build").addEventListener("click", () => setStep("start"));
  $("rag-era-erase").addEventListener("click", () => setStep("erase"));
}

registerTab("attack_erasure", {
  mount() {
    wire();
    load();
  },
});
