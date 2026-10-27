---
title: 'Story 16.8 : retrait des actions forcées'
type: 'refactor'
created: '2026-10-27'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-retours-2026-10-27/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-retours-2026-10-27/brownfield.md'
---

## Intent

CAP-5 : les actions forcées (bouton « Forcer », armement, puces « Armé : … », abandon d'action) disparaissent de l'interface, des routes, de la séance, des contenus fr/en/de, des tests, des E2E et de la doc. La suite complète (CI) et les E2E restent verts. Vague V2, après 16.5, en parallèle de 16.9. Opus.

## Inventaire (grep du 27/10 sur e9baeeb0, faux positifs écartés)

Faux positifs à **ne pas** toucher : `-Force` PowerShell (README, install.ps1, docs/installation.md, docs/modeles.md), « ARM » (docs/installation.md), « in force » des corpus et index RAG en anglais, `forced-colors` (pages.css:1581, app.css:1483), `closeDrawer(force)` et `closeMemoryDrawer(force)` (app.js:2264, 2389), `refresh(force)` (rag-evaluate.js:88), `armed` des faux serveurs (tests/test_e2e_fake_openai.py, test_rag_lab_no_index.py), `bound.click(force=True)` Playwright, test_llm_lab.py:666, test_mcp_github_auth.py:148, test_openai_responses.py:910, test_rag_lab_otel.py:342, reranker.py:255, render.py:575, les préréglages RAG (`PRESETS` de rag/lab.py, rag.js) et **`call_presets` de content/mcp.yaml**, lus aussi par l'Atelier MCP (`mcp.js:1765-2041`, `app_session.py:13960-13978`) : à garder.

Correction de brownfield.md : le champ `force` des briques n'est ni dans `bricks/contract.py` ni dans `content/bricks/*.yaml`. Il vit dans `trace/catalog.py` (`BrickForce`, `BrickState.force`) et vient de `content/subagent.yaml`.

**Séance et routes**
- `session/app_session.py` : `ArmedAction` (:567), `ArmRefused` (:590), `TurnState.armed` (:620), `self._armed` (:1190, :7308), `arm`, `disarm` et l'émission de `armed_actions_changed` (:5325-5440), prise des actions au tour (:5208-5228), consommation (:7971, :8013), `action_dropped` et `_armed_call`, `_forced_unavailable` (:8799-8900), `trigger = user` (:8105, :4469), extra Gemini des appels fabriqués (:8859-8860, :4512). Formulaires : `parameters` et `presets` des options d'outils (:1698-1702), `calls` des serveurs MCP (:1617-1649), `_subagent_card()["force"]` (:1721-1727 ; garder `limits_text`).
- `session/effects.py:45-50,72` : `ArmConsumed`.
- `web/app.py` : import `ArmRefused` (:57), `ArmIntention` (:190), `DisarmIntention` (:207), routes `/api/intentions/arm` et `/disarm` (:1626-1644), `armed_actions_changed` de l'état rechargé (:1129, :1146).
- `trace/catalog.py` : `ToolPresetState` (:637), `McpCallOption` (:644), champs `parameters`, `presets`, `tools`, `calls` de l'option (:660-667), `BrickForce` (:673-681), `BrickState.force` (:775), section « forced actions » (:1011-1033), kinds `armed_actions_changed` et `action_dropped` (:2342-2343). Vérifier avant de retirer `tools` (documentation MCP chargeable « par force ») qu'aucun autre lecteur ne l'utilise.
- `tools/registry.py:79-100` (`ToolPreset`, `presets`), `subagent.py:10,23-33` (`force_label_text`, `task_label_text`, `presets`), `mcp/servers.py:72-87` (garder `CallPreset` et `call_presets`, retirer seulement la mention du forçage dans le commentaire), `tools/parser.py:32` et `config.py:262` (commentaires).

**Interface**
- `app.js` : `store.openBrickHelp` « force-section » (:112), `store.armed` et libellés (:130-138), `case "armed_actions_changed"` (:374, :7041), `renderedArmed` (:1201-1244), `forcedToggle` (:1258), puces de carte et `cardForce` (:1359-1366), `.force-form` de `BRICK_CONTROLS` (:1423), bouton d'option (:1764-1774), bloc :1795-2160 (`memoryForceOption` à `disarmAction`, `armedChips`), puces du compositeur (:3802-3844), `loadShowForced` (:7979), `store.armed` au rechargement (:8100), lignes « Action forcée abandonnée » de l'orchestration (:6127-6140). Le badge `triggerBadge` (:2165-2176, :5739, :5830, :6015-6023, :6242) : voir Q2.
- `index.html:196` (`#armed-chips`).
- `app.css` : :1396 (badge user, Q2), :2472-2640 (`.force-*`, `.armed-*`), :3784-3790, :4209. **Garder** `.force-error` : il sert aux erreurs de téléchargement (app.js:1260, 1502, 1543, 1584, 1670, 1710 ; E2E run_e2e.py:6609, 6869). Le renommer `brick-error` est hors périmètre.

**Contenus** (fr, puis en et de mêmes clés)
- `content/ui.yaml` : `main.force.*` (:270-293), `main.trigger.user` (:218, Q2), `main.orch.rows.forced_action` et `dropped_title` (:939-940), `armed_actions_changed` et `action_dropped` (:1089-1090), `no_armed` (:1184). Idem `i18n/en/ui.yaml` (:207, 258-281, 927-928, 1077-1078, 1172) et `i18n/de/ui.yaml`.
- `content/messages.yaml` : `session.arm.*` (:352-368), `session.forced.*` (:466-480), mention « pas même forcée » de `cloud_no_tools` (:328). Idem en, de.
- `content/subagent.yaml` (:14-25), `content/tools.yaml` (`presets`, :5-92), `content/mcp.yaml:27` (commentaire seulement), `content/bricks/subagent.yaml:16`, `content/bricks/global_memory.yaml:13,23`, `content/memory/memory.yaml:26,30` (« écriture forcée ») : réécrire sans le forçage. Idem en, de.
- `content/scenarios.yaml` (34 lignes) et en, de : chaque consigne de secours « Afficher les actions forcées… Armer… » (voir Q1).

**Tests et E2E**
- Supprimer `tests/test_forced.py` (614 lignes).
- Retirer les tests qui arment : test_cloud.py:736 et :1460, test_compression.py:230, test_global_memory.py:164-235, :448-463, :618-625 (garder le 422 d'un texte non textuel s'il porte sur le tiroir), test_replay.py:124, test_scenarios.py:121-127 et :155 (`_armed`), test_subagent.py:154-207, :366, :472-474, :865-874, test_tool_result_bound.py:303, test_rag_rerank.py:768 (remplacer l'armement par une délégation du modèle ou retirer), test_i18n.py:876, test_content_language.py:482-588, test_program.py:251-358, :457.
- `tools/e2e/run_e2e.py` : `show_forced` et `arm` (:320-336), `s_forced_native` (:6250) et ses aides (:6118-6278) et son entrée (:19914), parties forcées de `s_mcp_full` (:5018-5027), `s_mcp_lazy` (:5186-5233), `s_caveman` (:5286-5312), `s_hooks` (:5353-5388), `s_subagent` (:5548-5619), `s_global_memory` (:6414-6444), `s_compression` (:8378-8400), `s_content_language` (`_forced_read`, :9146-9300). `tools/e2e/README.md:391, 621, 734`.
- `test-durations-*.json` : retirer les entrées des tests supprimés (ou laisser la CI les régénérer).

**Docs** : `docs/guide.md:55, 105-108, 662` ; module pédagogique = consignes de `scenarios.yaml` ci-dessus.

## Ordre de suppression

1. Tests et E2E d'abord (ils fixent ce qui disparaît), puis interface (app.js, index.html, app.css), puis routes (web/app.py), puis séance (app_session, effects), puis catalogue et modèles de contenu (catalog, registry, subagent), enfin contenus fr/en/de et docs.
2. `uv run pytest` ciblé à chaque couche (test_subagent, test_global_memory, test_scenarios, test_program, test_content_language, test_i18n, test_web_app), puis `git grep -n -i -E "armed|ArmRefused|show_?forced|force-(form|button|section)|main\.force|session\.(arm|forced)"` doit être vide hors faux positifs.
3. E2E par tranches : `mcp_full, mcp_lazy, caveman, hooks`, puis `subagent, global_memory, compression, content_language`, puis `programme, soc`.

## Risques

- Séance persistée : aucune (app_session.py:970, briques en mémoire). `wavestack.forcedActions` reste dans le localStorage des navigateurs : sans effet, le lire n'est plus fait.
- Traces historiques : la trace est en mémoire ; pas de fichier à relire. Retirer les kinds du catalogue est sûr ; vérifier seulement l'export OTel (aucune mention trouvée).
- `CloudModel` est strict (`extra="forbid"`, config.py:71) : retirer `tool_call_extra` ferait échouer un `wavestack.toml` d'utilisateur qui le porte (wavestack.toml:516, 562). Voir Q3.
- Scénarios et programme : `test_program` et `test_content_language` vérifient le texte des consignes ; les réaligner dans le même commit.

## Recouvrement avec 16.5 (fusionnée avant)

16.5 réécrit app.js:1253-1446 (panneau des briques) et ui.yaml:201-243. Zones communes : `forcedToggle` (:1258), `cardForce` et puces de carte (:1359-1366), `BRICK_CONTROLS` (:1423), l'info-bulle « ? » remplacée par `<details>` alors que `store.openBrickHelp` porte aussi « force-section ». Rebaser sur 16.5, puis retirer ces appels dans sa version. Recouvrement avec 16.9 : aucun bloc commun dans app.js (16.9 touche :2946-3142 et ses appels) ; ui.yaml et app.css : sections distinctes.

## Questions pour Anaël

1. **Consignes de secours des scénarios** (« si le modèle ne le fait pas, armez… ») : supprimer la phrase ou la remplacer par « reformulez ou rejouez le dernier prompt » ? Recommandation : remplacer par « rejouez le dernier prompt », plus court et toujours possible.
2. **Badge « Forcé par l'utilisateur »** (`trigger = user`) : plus aucun appel ne le produit. Retirer le badge, la clé `main.trigger.user` et la valeur `user` de `Trigger` ? Recommandation : oui pour le badge et la clé, garder la valeur `user` du `Literal` (sans risque, utile aux approbations).
3. **`tool_call_extra`** (extra Gemini des appels fabriqués) devient inutile. Recommandation : retirer son usage et le champ du `wavestack.toml` livré, mais garder le champ dans `CloudModel`, marqué « ignoré, gardé pour les configurations existantes ».
4. **Formulaire d'appel d'outil** : les préréglages de `content/tools.yaml` et les descriptions de paramètres ne servent qu'au forçage. Recommandation : les retirer ; garder `call_presets` de mcp.yaml, utilisé par l'Atelier MCP.

## Décisions d'Anaël (2026-10-27)

Q1 à Q4 : recommandations retenues telles quelles.
