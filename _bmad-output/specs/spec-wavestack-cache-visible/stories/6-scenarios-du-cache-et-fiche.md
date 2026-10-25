---
title: 'Story 6 : scénarios du cache et fiche'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/brownfield.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/stories/1-donnees-de-cache-par-appel.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le cache est visible (jauge, bouton, bilan, réglage Claude, stories 1 à 5) mais aucun scénario ne le fait vivre, et la formation ne relie pas le bilan d'agent-cost-kit aux trois cases de WaveStack.

**Approach:** Un module du programme, « Cache », en dernier, de cinq scénarios en fr, en et de, dont les gestes sont écrits dans `description_text` (aucune action scriptée) ; une fiche `docs/cache-de-prompt.md` et une section du guide.

## Boundaries & Constraints

- Module 8 « Cache », 45 min : lire le cache, casser le préfixe, faire expirer le cache, cache de Claude (facultatif), lire un bilan d'agent-cost-kit.
- Chaque scénario déclare les briques du dernier scénario du module 7 (compression), comme le veut la règle du programme ; le premier restaure la mémoire et rappelle les exceptions (raisonnement, RAG, sous-agent, H3).
- Claude reste facultatif : le scénario tourne sur le modèle local et décrit le geste Claude sans l'exécuter ; aucun appel réseau payant.
- Vocabulaire du bilan d'agent-cost-kit : « Lecture cache », « Écriture cache 5 min » ou « 1 h », « Non caché ».
- Fichiers carrefour (scénarios, i18n, `run_e2e.py`) : ajouts seuls.

</frozen-after-approval>

## Code Map

- `content/scenarios.yaml`, `content/i18n/{en,de}/scenarios.yaml` : module et cinq scénarios.
- `tests/test_scenarios.py` : 27 scénarios, 8 modules. `tests/test_program.py` : règles structurelles inchangées, vertes.
- `README.md`, `docs/guide.md`, `tools/demo/compose.py` : huit modules, 6 h 45.
- `docs/cache-de-prompt.md` : la fiche. `tools/e2e/run_e2e.py` : scénario `cache_module`.

## Tasks & Acceptance

- [x] Module et scénarios en fr, en, de.
- [x] Comptes et durée totale réalignés (8 modules, 6 h 45).
- [x] Fiche et section « Cache de prompt » du guide.
- [x] E2E `cache_module` : lecture, cause `system`, cause `cache_cleared`, consignes du scénario Claude et du bilan.

## Verification

- `uv run pytest -q --tb=short tests/test_scenarios.py tests/test_program.py tests/test_i18n.py` : 207 verts.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only cache_module` : 22 vérifications vertes.

## Décisions à revoir (prises par l'orchestrateur, nuit du 2026-10-25)

- Le module est le module 8, en dernier : la 14.2 a scindé le module 6 en « Sous-agent » et « Contexte long et carte ». Décision à revoir.
- La 14.4 ajoute un scénario au module 7 en parallèle : le second à fusionner refait les totaux (scénarios, durée de 6 h 45).
- Le scénario Claude n'appelle pas le réseau : décision à revoir si Anaël veut une démonstration réelle avec clé.

## Reports

- E2E : le scénario force le modèle local du faux llama-server et éteint Outils, MCP, Skills, Hooks et Compression (fenêtre du faux moteur trop petite) ; les consignes décrivent les briques complètes.
- Parcours de la recette (`docs/guide-testeur.md`) : inchangé, il ne cite aucun module.
