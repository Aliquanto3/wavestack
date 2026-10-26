"""V1.5 story 4, part 4b: the « Évaluer l'agent » view's texts (`main.agent_eval.*`, three
languages) and the module's contract with `app.js`, `index.html` and the story 3's form."""

from __future__ import annotations

import re

import pytest
import yaml

from wavestack import config

STATIC = config.repo_root() / "src" / "wavestack" / "web" / "static"
SCRIPT = (STATIC / "agent-eval.js").read_text(encoding="utf-8")
LANGS = ("fr", "en", "de")
_VARIABLE = re.compile(r"\{(\w+)\}")
PLURALS = ("case.trials", "trials.summary", "runs.result", "runs.not_run", "clear_confirm.ask")
# The keys built at run time, with every value the server can send.
DYNAMIC = (
    [f"status.{s}" for s in ("passed", "failed", "not_run", "running", "pending")]
    + [f"compare.field.{f}" for f in ("model", "system_prompt")]
    + [f"compare.change.{c}" for c in ("regressed", "fixed", "unchanged")]
    + [f"runs.status.{s}" for s in ("cancelled", "budget", "error")]
)


def _tree(lang: str) -> dict:
    path = config.content_file("ui.yaml", lang)
    return yaml.safe_load(path.read_text(encoding="utf-8"))["main"]


def _node(tree: dict, dotted: str):
    for part in dotted.split("."):
        if not isinstance(tree, dict) or part not in tree:
            return None
        tree = tree[part]
    return tree


def _leaves(tree: dict, prefix: str = "") -> dict[str, str]:
    found: dict[str, str] = {}
    for key, value in tree.items():
        if isinstance(value, dict):
            found |= _leaves(value, f"{prefix}{key}.")
        else:
            found[prefix + key] = value
    return found


def _used_keys() -> set[str]:
    direct = re.findall(r'\bta\(\s*"([a-z0-9_.]+)"', SCRIPT)
    # A ternary's keys: `ta(shown ? "trace.hide" : "trace.show")`.
    ternary = re.findall(r'\bta\([^()"]*\?\s*"([a-z0-9_.]+)"\s*:\s*"([a-z0-9_.]+)"', SCRIPT)
    return set(direct) | {k for pair in ternary for k in pair} | set(DYNAMIC)


@pytest.mark.parametrize("lang", LANGS)
def test_every_text_the_view_asks_for_exists(lang):
    tree = _tree(lang)["agent_eval"]
    keys = _used_keys()
    assert {"title", "run_suite", "clear", "compare.title", "trace.show"} <= keys
    assert len(keys) > 60
    for key in sorted(keys):
        value = _node(tree, key)
        if key in PLURALS:
            assert isinstance(value, dict) and set(value) == {"one", "other"}, (lang, key)
        else:
            assert isinstance(value, str) and value.strip(), (lang, key)
    # The failing check's label: the story 3's kinds, plus the cap's own key.
    assert isinstance(_node(tree, "check.model_calls_max"), str)
    kinds = _tree(lang)["agent_case"]["form"]["checks"]["kind"]
    assert "main.agent_case.form.checks.kind.${kind}" in SCRIPT and len(kinds) == 7


@pytest.mark.parametrize("lang", ("en", "de"))
def test_the_translation_mirrors_the_french_keys_and_variables(lang):
    french = _leaves(_tree("fr")["agent_eval"])
    translated = _leaves(_tree(lang)["agent_eval"])
    assert set(translated) == set(french), sorted(set(translated) ^ set(french))
    for key, value in translated.items():
        assert set(_VARIABLE.findall(value)) == set(_VARIABLE.findall(french[key])), (lang, key)


def test_every_plural_has_its_count_and_both_forms():
    for lang in LANGS:
        tree = _tree(lang)["agent_eval"]
        for key in PLURALS:
            forms = _node(tree, key)
            assert set(forms) == {"one", "other"}, (lang, key)
    # `count` picks the form: each call of a plural passes it.
    for key in PLURALS:
        calls = re.findall(rf'ta\("{re.escape(key)}", \{{([^}}]*)\}}', SCRIPT)
        assert calls and all(re.search(r"\bcount\b", c) for c in calls), key


# The labels the story 5 (module 9) quotes in its gestures: kept word for word.
LABELS = {
    "fr": {
        "title": "Évaluer l'agent",
        "group.provided": "Suite fournie",
        "group.mine": "Mes cas",
        "run_suite": "Lancer la suite",
        "case.run": "Lancer",
        "first_run.text": "La conversation sera vidée ; votre configuration est rétablie à la fin.",
        "case.trials.other": "{count} essais",
        "status.passed": "Réussi",
        "status.not_run": "Non lancé",
        "trace.show": "Voir le tour",
        "trials.summary.other": "{passed} réussis sur {ran} · pass@{k} : {at} · pass^{k} : {all}",
        "compare.diff": "Diffère : {fields}.",
        "compare.field.system_prompt": "prompt système",
        "compare.title": "Comparer A et B",
        "compare.change.fixed": "corrigé",
        "compare.change.regressed": "régressé",
        "compare.change.unchanged": "inchangé",
        "clear": "Effacer mes cas",
    },
    "en": {
        "title": "Evaluate the agent",
        "group.provided": "Provided suite",
        "group.mine": "My cases",
        "run_suite": "Run the suite",
        "case.run": "Run",
        "status.passed": "Passed",
        "status.not_run": "Not run",
        "trace.show": "Show the turn",
        "compare.title": "Compare A and B",
        "clear": "Clear my cases",
    },
    "de": {
        "title": "Agent bewerten",
        "group.provided": "Mitgelieferte Suite",
        "group.mine": "Meine Fälle",
        "run_suite": "Suite starten",
        "case.run": "Starten",
        "status.passed": "Bestanden",
        "status.not_run": "Nicht gestartet",
        "trace.show": "Turn anzeigen",
        "compare.title": "A und B vergleichen",
        "clear": "Meine Fälle löschen",
    },
}


@pytest.mark.parametrize("lang", LANGS)
def test_the_labels_quoted_by_the_module_9_are_kept(lang):
    tree = _tree(lang)["agent_eval"]
    for key, text in LABELS[lang].items():
        assert _node(tree, key) == text, (lang, key)


def test_the_session_state_has_its_label_in_the_event_log():
    assert _tree("fr")["log"]["session_states"]["agent_eval"] == "évaluation de l'agent"
    for lang in ("en", "de"):
        assert _tree(lang)["log"]["session_states"]["agent_eval"].strip()


# ---------- the module's contract ----------


def test_the_module_exports_its_interface_and_imports_only_its_two_neighbours():
    exported = re.findall(r"^export (?:async )?function (\w+)", SCRIPT, re.M)
    assert sorted(exported) == ["caseBadge", "closeView", "openView", "sessionStateChanged"]
    imports = re.findall(r'^import .* from "([^"]+)";', SCRIPT, re.M)
    assert sorted(imports) == ["./agent-case-form.js", "./i18n.js"]
    assert "registerOpenView(" in SCRIPT and "onCaseSaved(" in SCRIPT
    # The data never go through HTML.
    assert "innerHTML" not in SCRIPT and "insertAdjacentHTML" not in SCRIPT
    # Decision 8: the panel by CSS, never through panes.js.
    assert "createPanes" not in SCRIPT and "localStorage" not in SCRIPT
    assert 'setAttribute("data-agent-eval", "open")' in SCRIPT


def test_the_view_polls_one_request_at_a_time_and_stops_through_the_session():
    assert "const POLL_MS = 1000;" in SCRIPT
    assert "setInterval" not in SCRIPT  # the next request leaves a second after the answer
    assert '"/api/intentions/stop"' in SCRIPT
    # It never reloads the model nor changes the window.
    assert "/api/intentions/model" not in SCRIPT and "context_window" not in SCRIPT


def test_index_html_has_the_toggle_and_loads_neither_file():
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    toggle = page.index('id="agent-eval-toggle"')
    assert page.index('<header class="top-bar">') < toggle < page.index('id="pane-chips"')
    assert 'aria-label="Évaluer l\'agent" data-i18n-aria-label="main.agent_eval.toggle">' in page
    assert 'class="agent-eval-word" data-i18n="main.agent_eval.toggle">Évaluer l\'agent<' in page
    assert "agent-eval.css" not in page and "agent-eval.js" not in page
    assert "agent-case-form.css" not in page


def test_app_js_has_the_four_insertions():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    lines = app.splitlines()
    form = lines.index('import { canMakeCase, openCaseForm } from "./agent-case-form.js";')
    assert lines[form + 1].startswith(
        'import { caseBadge, sessionStateChanged } from "./agent-eval.js";'
    )
    assert "sessionStateChanged(p);" in app
    assert 'state?.state !== "agent_eval"' in app
    assert "if (turn.caseId) nodes.push(caseBadge(turn.caseId));" in app


def test_the_stylesheet_hides_the_two_panes_and_keeps_the_mockup_classes():
    css = (STATIC / "agent-eval.css").read_text(encoding="utf-8")
    assert '.right[data-agent-eval="open"] .top-row > [data-pane="ctx"]' in css
    assert '.right[data-agent-eval="open"] .top-row > [data-pane="orch"]' in css
    for name in ("ae-panel", "ae-head", "ae-progress", "ae-group", "ae-cases", "ae-case"):
        assert f".{name}" in css, name
    for name in (
        "ae-status",
        "ae-reason",
        "ae-trace",
        "ae-dots",
        "ae-table",
        "ae-diff",
        "ae-badge",
    ):
        assert f".{name}" in css, name
    # The shared ones stay in the story 3's sheet.
    assert not re.search(r"^\.ae-(button|text|danger)\b", css, re.M)
