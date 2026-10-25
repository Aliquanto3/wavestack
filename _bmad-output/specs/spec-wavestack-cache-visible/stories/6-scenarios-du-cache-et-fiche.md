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

## Revue

### Passe 1 (2026-10-25, SHA revu 95770bc)

Base à jour (origin/main ff8c405, aucune fusion nécessaire).

- Important, medium, second avis : « Vider le cache » situé « sous la conversation » alors que le bouton est dans l'en-tête du volet « Vue humain » (index.html:175). Corrigé en fr, en et de, dans le guide et dans la fiche.
- Important, medium, reviewer : `test_content_language.py` rouge en de (`cache_claude` cite « nicht im Cache », qui n'est pas le libellé de la jauge allemande « nicht gecacht »). Le test n'était pas dans la vérification de la story. Corrigé.
- Nit, low, second avis : « Aucun outil ici » alors que le scénario déclare `read_file`. Corrigé (« les outils restent allumés, mais aucun prompt ne les appelle »), dans les trois langues.
- Nit, low, second avis : jauge allemande « nicht im Cache » au lieu de « nicht gecacht » (ui.yaml:780) dans `cache_read`. Corrigé ; le bilan garde « Nicht im Cache », son libellé à lui.
- Nit, low, second avis : « la lecture coûte le dixième de l'entrée » dans un scénario local. Corrigé en « chez Claude, … », dans les trois langues.
- Nit, low, second avis : fiche en français seul et commande `/agent-cost-kit:mesurer-couts` absente sur le poste pro. Corrigé pour la commande (« si le plugin est installé ») ; pour la fiche, rejeté : en et de disent déjà qu'elle est en français, la traduire sort du périmètre.
- Nit, low, second avis : l'E2E éteint Outils, MCP, Skills, Hooks et Compression. Rejeté : limite connue du faux moteur, déjà consignée dans les reports ; les causes et les lectures du cache sont bien vérifiées.
- Nit, low, second avis : ajustement AD-9 non exécuté. Rejeté : `test_program.py` vérifie déjà les briques du module, et les quatre fichiers ciblés passent (262 verts).
- Nit, low, second avis : totaux (27 scénarios, 6 h 45) en conflit avec la 14.4. Rejeté : le second à fusionner refait les totaux, comme le prévoit la story.
- Complexité : 0 constat (contenu et docs, aucune structure qui grossit).

Tests : ruff, contrôle rapide, `pytest tests/test_program.py tests/test_scenarios.py tests/test_i18n.py tests/test_content_language.py` (262 verts), E2E `cache_module programme` (26 vérifications vertes, captures restaurées).
