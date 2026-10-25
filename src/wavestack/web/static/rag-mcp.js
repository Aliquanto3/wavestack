// V1.2 story 20 (CAP-18), the "Exposer en MCP" card of the Build tab. The state is the session's
// (`GET /api/rag_lab/mcp`, AD-1): the page starts the server on its chain, stops it, and draws the
// address, the token (hidden until revealed), the frozen chain and the tools with their risk. The
// token is read from that GET alone, kept in this module's memory, never stored. Every text is drawn
// as text (`textContent`).

import { t as ui } from "./i18n.js";
import { $, el, registerTab, store } from "./rag.js";

const mc = { body: null, revealed: false, busy: false };

const tx = (key) => String(mc.body?.texts?.[key] ?? "");

async function load() {
  try {
    const response = await fetch("/api/rag_lab/mcp");
    mc.body = response.ok ? await response.json() : null;
  } catch {
    mc.body = null;
  }
  draw();
}

async function send(path, body) {
  try {
    const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    let answer = {};
    try {
      answer = await response.json();
    } catch {
      answer = {};
    }
    return { ok: response.ok, body: answer };
  } catch {
    return { ok: false, body: {} };
  }
}

async function start() {
  if (mc.busy) return;
  mc.busy = true;
  const answer = await send("/api/intentions/rag_mcp_start", { pipelines: store.pipelines });
  mc.busy = false;
  mc.revealed = false;
  const refused = $("rag-mcp-refused");
  refused.hidden = answer.ok;
  refused.textContent = answer.ok ? "" : `${tx("refused_label_text")} : ${answer.body.detail ?? ""}`;
  await load();
}

async function stop() {
  if (mc.busy) return;
  mc.busy = true;
  await send("/api/intentions/rag_mcp_stop", {});
  mc.busy = false;
  mc.revealed = false;
  $("rag-mcp-refused").hidden = true;
  await load();
}

async function copy(value) {
  const said = $("rag-mcp-copied");
  try {
    await navigator.clipboard.writeText(value);
    said.textContent = tx("copied_text");
  } catch {
    said.textContent = tx("copy_failed_text");
  }
}

function riskChip(level) {
  const chip = el("span", `status-chip${level === "low" ? "" : ` status-chip-${level}`}`, ui(`mcp.policy.risk.${level}`));
  chip.dataset.level = level;
  return chip;
}

function toolNode(tool) {
  const item = el("li", "rag-mcp-tool");
  item.dataset.tool = tool.name;
  item.dataset.rule = tool.rule;
  item.append(el("code", "", tool.name), " · ", `${tx("risk_label_text")} : `, riskChip(tool.risk));
  item.append(" · ", `${tx("rule_label_text")} : ${ui(`mcp.policy.rule.${tool.rule}`)}`);
  if (!tool.announced) item.append(" · ", el("span", "rag-badge", tx("hidden_tool_text")));
  return item;
}

function chainText(chain) {
  const stages = chain.stages.map((s) => `${s.label_text} : ${s.option_label_text}`);
  return `${chain.label_text} — ${stages.join(" → ")}`;
}

function draw() {
  const b = mc.body;
  const card = $("rag-mcp-card");
  if (!b || b.available === false || !b.texts) {
    card.hidden = !b?.reason_text;
    if (b?.reason_text) $("rag-mcp-hint").textContent = b.reason_text;
    return;
  }
  card.hidden = false;
  card.dataset.running = b.running ? "1" : "0";
  $("rag-mcp-title").textContent = tx("title_text");
  $("rag-mcp-hint").textContent = tx("hint_text");
  $("rag-mcp-state").textContent = `${tx("state_label_text")} : ${b.running ? tx("state_on_text") : tx("state_off_text")}`;
  $("rag-mcp-state").dataset.state = b.running ? "on" : "off";
  $("rag-mcp-start").textContent = tx("start_text");
  $("rag-mcp-stop").textContent = tx("stop_text");
  $("rag-mcp-start").disabled = b.running;
  $("rag-mcp-stop").disabled = !b.running;
  $("rag-mcp-note").hidden = !b.note_text;
  $("rag-mcp-note").textContent = b.note_text ?? "";
  $("rag-mcp-facts").hidden = !b.running;
  $("rag-mcp-address-label").textContent = tx("address_label_text");
  $("rag-mcp-address").textContent = b.url ?? "";
  $("rag-mcp-token-label").textContent = tx("token_label_text");
  $("rag-mcp-token").textContent = mc.revealed && b.token ? b.token : tx("token_hidden_text");
  $("rag-mcp-reveal").textContent = mc.revealed ? tx("hide_text") : tx("reveal_text");
  $("rag-mcp-reveal").setAttribute("aria-pressed", String(mc.revealed));
  $("rag-mcp-copy-token").textContent = tx("copy_token_text");
  $("rag-mcp-chain-label").textContent = tx("chain_label_text");
  $("rag-mcp-chain").textContent = b.chain ? chainText(b.chain) : "";
  $("rag-mcp-frozen").hidden = !b.running;
  $("rag-mcp-frozen").textContent = tx("frozen_text");
  $("rag-mcp-tools-title").textContent = tx("tools_label_text");
  $("rag-mcp-tools").replaceChildren(...b.tools.map(toolNode));
  $("rag-mcp-command-box").hidden = !b.running || !b.command;
  $("rag-mcp-command-title").textContent = tx("command_label_text");
  const shown = b.command && !mc.revealed && b.token ? b.command.replace(b.token, tx("token_hidden_text")) : b.command;
  $("rag-mcp-command").textContent = shown ?? "";
  $("rag-mcp-copy-command").textContent = tx("copy_command_text");
  $("rag-mcp-command-note").textContent = tx("command_note_text");
  $("rag-mcp-copilot").textContent = tx("copilot_text");
  $("rag-mcp-language").textContent = tx("language_text");
}

function wire() {
  $("rag-mcp-start").addEventListener("click", start);
  $("rag-mcp-stop").addEventListener("click", stop);
  $("rag-mcp-reveal").addEventListener("click", () => {
    mc.revealed = !mc.revealed;
    draw();
  });
  $("rag-mcp-copy-token").addEventListener("click", () => mc.body?.token && copy(mc.body.token));
  $("rag-mcp-copy-command").addEventListener("click", () => mc.body?.command && copy(mc.body.command));
}

registerTab("mcp", {
  mount() {
    wire();
    load();
  },
});
