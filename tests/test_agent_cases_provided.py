"""V1.5 story 2 (CAP-2): the eight provided agent cases, checked in both directions through
the session (a scripted fake engine: the case passes; an idle one: it fails), and the
measure tool (`tools/eval/`, never run on a real model)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml
from fake_engine import FakeEngine, booted_session
from test_tools import QWEN, call

from wavestack import config
from wavestack.agent_eval.cases import POSITIVE_KINDS, AgentCase, load_provided_cases
from wavestack.agent_eval.checks import verify

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "tools" / "eval"
LANGS = ("fr", "en", "de")
CASES_FILE = ROOT / "content" / "agent_cases.yaml"

SCRIPTS: dict[str, list[str]] = {
    "heure_get_datetime": [call("get_datetime"), "Il est 10 h 12."],
    "chemin_invente": [
        call("read_file", path="."),
        call("read_file", path="notes_reunion.txt"),
        "Le fichier demandé n'existe pas ; voici les notes de réunion.",
    ],
    "h1_bloque_confidentiel": [
        call("read_file", path="confidentiel/budget_projet.txt"),
        "Je n'ai pas pu lire ce fichier.",
    ],
    "memoire_globale_prenom": [
        "Vous vous appelez Pascal et vous êtes consultant en cybersécurité."
    ],
    "code_talvane_apres_compaction": [
        "Résumé : le code du projet Talvane est TLV-7731-QZ.",
        "Le code du projet Talvane est TLV-7731-QZ.",
    ],
    "delegation_sous_agent": [
        call("delegate", task="Lis guide_harnais.md et résume-le."),
        call("read_file", path="guide_harnais.md"),
        "Résumé du guide en trois lignes.",
        "Le guide tient en trois lignes.",
    ],
    "recherche_avant_lecture": [
        call("search_documents", query="mot de passe"),
        call("read_file", path="corpus/mots_de_passe.md"),
        "Au moins 14 caractères.",
    ],
    "h5_refuse_sans_rappel": [
        call("public_holidays", year="2026"),
        "Je n'ai pas pu vérifier ces jours fériés.",
    ],
}


@pytest.fixture(scope="module")
def player():
    sys.path.insert(0, str(EVAL))
    try:
        spec = importlib.util.spec_from_file_location("case_player", EVAL / "case_player.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["case_player"] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(EVAL))
        sys.modules.pop("case_player", None)


def _cases(lang: str) -> dict[str, AgentCase]:
    return {c.id: c for c in load_provided_cases(lang)}


# The fake engine counts one token per byte, a real small model about 3.5 characters per token:
# the cases, written for a 4096-token window, are played here on a 16384 one. At 4096 the fake
# engine overflows on a corpus document, and on the compaction case even for its summary call.
def _session(outputs: list[str] | None = None, lang: str = "fr", window: int = 16384):
    if outputs is None:
        engine = FakeEngine(output="", template=QWEN.decode("utf-8"), architecture="qwen35")
    else:
        engine = FakeEngine(outputs=outputs, template=QWEN.decode("utf-8"), architecture="qwen35")
    return engine, booted_session(engine, window=window, values={"language": lang})


def _play(player, case: AgentCase, outputs: list[str] | None, lang: str = "fr"):
    engine, session = _session(outputs, lang)
    try:
        return engine, verify(case, player.play_case(session, case), lang)
    finally:
        session.close()


# ---------- the files ----------


def test_eight_cases_with_the_same_ids_and_checks_in_the_three_languages():
    by_lang = {lang: load_provided_cases(lang) for lang in LANGS}
    fr = by_lang["fr"]
    assert len(fr) == 8 and len({c.id for c in fr}) == 8
    assert set(SCRIPTS) == {c.id for c in fr}  # a ninth case without a script breaks the suite
    for lang in ("en", "de"):
        other = by_lang[lang]
        assert [c.id for c in other] == [c.id for c in fr]
        for a, b in zip(fr, other, strict=True):
            for field in (
                "brick",
                "bricks",
                "tools",
                "hooks",
                "skills",
                "mcp_servers",
                "window",
                "approval",
                "on_overflow",
                "max_model_calls",
                "checks",
            ):
                assert getattr(a, field) == getattr(b, field), (a.id, field)
            assert b.prompt != a.prompt and b.title_text != a.title_text
    for cases in by_lang.values():
        for c in cases:
            assert c.title_text and c.symptom_text and c.assertion_text
            assert c.history == [] or c.id == "code_talvane_apres_compaction"


def test_translations_are_real_files_not_the_french_fallback():
    for lang in ("en", "de"):
        path = ROOT / "content" / "i18n" / lang / "agent_cases.yaml"
        assert config.content_file("agent_cases.yaml", lang) == path and path.is_file()
        assert yaml.safe_load(path.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("lang", LANGS)
def test_every_case_demands_an_event_present(lang):
    for case in load_provided_cases(lang):
        assert any(c.kind in POSITIVE_KINDS for c in case.checks), case.id


def test_configuration_is_explicit_and_without_system_prompt():
    for case in load_provided_cases("fr"):
        assert case.system_prompt is None and case.approval == "refuse"
        assert case.skills == [] and case.mcp_servers == []
        assert case.tools is not None and case.hooks is not None, case.id


def test_provenance_recipe_case_and_the_seven_others():
    cases = _cases("fr")
    recipe = cases["heure_get_datetime"].provenance
    assert (recipe.source, recipe.date, recipe.model) == ("recette", "2026-10-02", None)
    assert "resultats-restes-pc-2026-10.md" in (recipe.fixed_in or "")
    assert list(ROOT.glob("_bmad-output/**/resultats-restes-pc-2026-10.md"))
    others = [c for i, c in cases.items() if i != "heure_get_datetime"]
    assert len(others) == 7 and {c.provenance.source for c in others} == {"fourni"}


def test_caps_are_positive_and_h5_keeps_its_contract_cap():
    cases = _cases("fr")
    assert all(c.max_model_calls >= 1 for c in cases.values())
    assert cases["h5_refuse_sans_rappel"].max_model_calls == 2


def test_compaction_case_history_overflows_a_4096_window_and_keeps_the_code_in_the_first_exchange():
    case = _cases("fr")["code_talvane_apres_compaction"]
    assert (case.window, case.on_overflow) == (4096, "compaction")
    assert len(case.history) == 4 and "TLV-7731-QZ" in case.history[0].assistant
    assert all("TLV-7731-QZ" not in e.user + e.assistant for e in case.history[1:])
    assert "TLV-7731-QZ" not in case.prompt
    assert sum(len(e.user + e.assistant) for e in case.history) > 4096 * 3


# ---------- both directions, through the session ----------


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("case_id", sorted(SCRIPTS))
def test_the_case_passes_on_a_scripted_engine(player, case_id, lang):
    case = _cases(lang)[case_id]

    engine, verdict = _play(player, case, SCRIPTS[case_id], lang)

    failed = [(c.kind, c.reason_text) for c in verdict.checks if not c.passed]
    assert failed == [] and verdict.passed
    assert verdict.model_calls == len(SCRIPTS[case_id]) == len(engine.calls)
    assert verdict.checks[-1].kind == "model_calls_max"


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("case_id", sorted(SCRIPTS))
def test_the_case_fails_on_an_idle_engine(player, case_id, lang):
    case = _cases(lang)[case_id]

    _, verdict = _play(player, case, None, lang)

    assert not verdict.passed
    positive = [c for c in verdict.checks if c.kind in POSITIVE_KINDS]
    assert positive and any(not c.passed and c.reason_text.strip() for c in positive)


def test_a_slow_loop_of_the_recipe_case_breaks_its_cap(player):
    case = _cases("fr")["heure_get_datetime"]

    _, verdict = _play(player, case, [call("get_datetime")] * 3 + ["Il est 10 h."])

    cap = verdict.checks[-1]
    assert not verdict.passed and not cap.passed
    assert cap.reason_text == "4 appels au modèle pour un plafond de 3"
    assert all(c.passed for c in verdict.checks[:-1])  # only the cap fails


def test_the_loop_to_the_step_limit_of_the_recipe_case_fails_every_check(player):
    case = _cases("fr")["heure_get_datetime"]

    _, verdict = _play(player, case, [call("get_datetime")])  # R22: never answers

    assert not verdict.passed and not any(c.passed for c in verdict.checks)
    assert all("tour incomplet" in c.reason_text for c in verdict.checks)


def test_h5_calling_the_tool_again_after_the_refusal_breaks_the_cap_of_two(player):
    case = _cases("fr")["h5_refuse_sans_rappel"]
    outputs = [call("public_holidays", year="2026")] * 2 + ["Je ne sais pas."]

    _, verdict = _play(player, case, outputs)

    cap = verdict.checks[-1]
    assert (cap.kind, cap.passed) == ("model_calls_max", False)
    assert verdict.model_calls == 3 and cap.params == {"max": 2}
    assert not verdict.passed


# ---------- the measure tool ----------


@pytest.fixture
def measure_module(player):
    sys.path.insert(0, str(EVAL))
    try:
        spec = importlib.util.spec_from_file_location("measure_cases", EVAL / "measure_cases.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["measure_cases"] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(EVAL))
        sys.modules.pop("measure_cases", None)


def test_measure_proposes_the_largest_count_plus_one_and_leaves_h5_to_its_contract(
    measure_module, tmp_path
):
    cases = [
        c
        for c in load_provided_cases("fr")
        if c.id in ("heure_get_datetime", "h5_refuse_sans_rappel")
    ]
    # get_datetime: 2, then 3, then 2 model calls; then H5's two runs of two calls.
    gd = call("get_datetime")
    h5 = call("public_holidays", year="2026")
    outputs = [gd, "ok", gd, gd, "ok", gd, "ok", h5, "non", h5, "non", h5, "non"]
    _, session = _session(outputs)
    before = hashlib.sha256(CASES_FILE.read_bytes()).hexdigest()

    results = measure_module.measure(session, cases, runs=3)
    text = measure_module.render(results, 3)
    out = tmp_path / "out.json"
    out.write_text(json.dumps([r.__dict__ for r in results]), encoding="utf-8")

    heure, h5_result = results
    assert heure.calls == [2, 3, 2] and heure.observed_max == 3 and heure.proposed_cap == 4
    assert h5_result.calls == [2, 2, 2] and h5_result.proposed_cap is None
    assert "heure_get_datetime: max_model_calls: 4" in text
    assert "h5_refuse_sans_rappel: plafond du contrat (2), non relevé" in text
    assert json.loads(out.read_text(encoding="utf-8"))[0]["calls"] == [2, 3, 2]
    assert hashlib.sha256(CASES_FILE.read_bytes()).hexdigest() == before  # the file is untouched


def test_measure_skips_a_case_whose_window_is_not_the_current_one(measure_module):
    case = _cases("fr")["code_talvane_apres_compaction"].model_copy(update={"window": 8192})
    _, session = _session(["ok"], window=4096)

    (result,) = measure_module.measure(session, [case], runs=3)

    assert (
        result.calls == [] and result.skipped == "non mesurable ici (fenêtre 8192, courante 4096)"
    )
    assert "non mesurable ici" in measure_module.render([result], 3)


def test_measure_main_refuses_a_missing_model(measure_module, tmp_path, capsys):
    code = measure_module.main(["--model", str(tmp_path / "absent.gguf")])

    assert code == 2 and "Modèle introuvable" in capsys.readouterr().err
