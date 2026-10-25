// V1.2 story 18 (CAP-15), the "Droits d'accès" card of the Attack tab. The figures are the session's
// (`/api/rag_lab/access`, AD-1): the page sends the profile and the mode, receives what the pipeline
// read before the filter and draws it. Registered under its own key with a single `mount` hook (GET of
// the texts and the default state, no computation). Every text is drawn as text (`textContent`).

import { $, el, registerTab } from "./rag.js";

const ac = { body: null, profile: "all", mode: "after", asked: 0 };

const fill = (template, values = {}) => String(template ?? "").replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));

const t = (path, values = {}) => {
  let value = ac.body?.texts;
  for (const key of path.split(".")) value = value?.[key];
  return typeof value === "string" ? fill(value, values) : "";
};

async function load() {
  try {
    const response = await fetch("/api/rag_lab/access");
    if (response.ok) ac.body = await response.json();
  } catch {
    ac.body = null;
  }
  if (!ac.body) return;
  ac.profile = ac.body.defaults.profile;
  ac.mode = ac.body.defaults.mode;
  drawControls();
  await run();
}

async function run() {
  if (!ac.body) return;
  ac.asked += 1;
  const asked = ac.asked;
  let answer = null;
  try {
    const response = await fetch("/api/rag_lab/access", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile: ac.profile, mode: ac.mode }) });
    answer = response.ok ? await response.json() : null;
  } catch {
    answer = null;
  }
  if (asked !== ac.asked) return;
  if (answer) drawResult(answer);
}

function fillSelect(select, ids, label, current) {
  select.replaceChildren(
    ...ids.map((id) => {
      const option = el("option", "", label(id));
      option.value = id;
      return option;
    }),
  );
  select.value = current;
}

function drawControls() {
  $("rag-acc-banner").textContent = t("banner_text");
  $("rag-acc-title").textContent = t("title_text");
  $("rag-acc-hint").textContent = t("hint_text");
  $("rag-acc-profile-label").textContent = t("profile_label_text");
  $("rag-acc-mode-label").textContent = t("mode_label_text");
  fillSelect($("rag-acc-profile"), ac.body.profiles, (id) => t(`profile.${id}`), ac.profile);
  fillSelect($("rag-acc-mode"), ac.body.modes, (id) => t(`mode.${id}`), ac.mode);
  $("rag-acc-question").textContent = `${t("question_label_text")} : ${ac.body.question.text}`;
  $("rag-acc-limits").replaceChildren(...(ac.body.texts.limits ?? []).map((line) => el("li", "", line)));
}

function passageNode(p, withState) {
  const item = el("li", "rag-acc-passage");
  item.dataset.docId = p.doc_id;
  item.dataset.audience = p.audience;
  const leak = withState && p.kept === false && ac.profile === "all";
  if (leak) item.dataset.leak = "1";
  item.append(el("strong", "", t("passage_text", { rank: p.rank, title: p.title_text, position: p.position, score: p.score })));
  item.append(" ", el("span", "rag-badge", t(`audience.${p.audience}`)));
  if (withState) {
    const state = p.kept === false ? `${t("removed_text")} · ${t("leak_badge_text")}` : t("kept_text");
    item.append(" ", el("span", "rag-badge", state));
  }
  item.append(el("p", "rag-atk-text", p.text));
  return item;
}

function section(id, title, passages, emptyKey, withState) {
  const box = el("div");
  box.dataset.section = id;
  box.append(el("h4", "rag-cost-title", title));
  if (!passages.length) {
    box.append(el("p", "rag-note", t(emptyKey)));
  } else {
    const list = el("ul", "rag-atk-list");
    list.append(...passages.map((p) => passageNode(p, withState)));
    box.append(list);
  }
  return box;
}

function drawResult(r) {
  const c = r.corpus;
  $("rag-acc-corpus").textContent = t("corpus_text", { docs: c.documents, hr: c.hr_documents, chunks: c.passages, size: c.max_chars, k: r.k });
  const note = el("p", "rag-atk-limit", r.note_text);
  note.dataset.note = r.leaked.length ? "leak" : "none";
  const parts = [
    section("seen", t("seen_title_text"), r.seen_before_filter, "returned_none_text", true),
    section("returned", t("returned_title_text"), r.returned, "returned_none_text", false),
    section("leaked", t("leaked_title_text"), r.leaked, "leaked_none_text", false),
    el("p", "", t("count_text", { count: r.returned_count, k: r.k })),
    note,
  ];
  if (r.shortfall_text) parts.push(el("p", "rag-atk-limit", r.shortfall_text));
  if (r.rewrite) {
    const box = el("div");
    box.id = "rag-acc-rewrite";
    box.append(el("h4", "rag-cost-title", t("rewrite_title_text")), el("p", "rag-atk-text", r.rewrite.text), el("p", "rag-note", r.rewrite.provenance.text));
    parts.push(box);
  }
  $("rag-acc-result").replaceChildren(...parts);
}

function wire() {
  $("rag-acc-profile").addEventListener("change", (event) => {
    ac.profile = event.target.value;
    run();
  });
  $("rag-acc-mode").addEventListener("change", (event) => {
    ac.mode = event.target.value;
    run();
  });
}

registerTab("attack_access", {
  mount() {
    wire();
    load();
  },
});
