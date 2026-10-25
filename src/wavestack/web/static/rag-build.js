// V1.2 story 4, tab « Construire » (CAP-2): the prepared-question selector of the bar, with its
// type's badge. The rest of the tab (the chain, its views, the focus, the costs) is the common
// `rag.js`. Registered with the shell (`registerTab`).

import { $, el, keep, QUESTION_KEY, registerTab, store, text } from "./rag.js";

// A selector next to the free question, with its type's badge.
function renderPrepared() {
  const select = $("rag-prepared");
  const questions = store.questions;
  $("rag-prepared-box").hidden = !questions.length;
  if (!questions.length) return;
  const current = questions.find((q) => q.question_text === $("rag-question").value);
  select.replaceChildren(new Option(text("prepared.free_text"), ""));
  const groups = new Map();
  for (const q of questions) {
    if (!groups.has(q.type)) {
      const group = el("optgroup");
      group.label = text(`prepared.types.${q.type}_text`) || q.type;
      groups.set(q.type, group);
    }
    groups.get(q.type).append(new Option(q.question_text, q.id));
  }
  select.append(...groups.values());
  select.value = current?.id ?? "";
  const badge = $("rag-question-type");
  badge.hidden = !current;
  badge.textContent = current ? text(`prepared.types.${current.type}_text`) || current.type : "";
  badge.dataset.type = current?.type ?? "";
}

function pickPrepared() {
  const q = store.questions.find((x) => x.id === $("rag-prepared").value);
  const input = $("rag-question");
  if (q) {
    input.value = q.question_text;
    keep(QUESTION_KEY, input.value);
  }
  renderPrepared();
}

function mount() {
  $("rag-prepared").addEventListener("change", pickPrepared);
  $("rag-question").addEventListener("input", renderPrepared);
}

registerTab("build", { mount, render: renderPrepared });
