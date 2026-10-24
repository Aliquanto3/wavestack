---
title: 'Carte du harnais et module « Contexte long et carte »'
type: 'feature'
created: '2026-10-24'
status: 'ready-for-dev'
baseline_revision: 'd9f223e'
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-etat-de-l-art-harnais/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-etat-de-l-art-harnais/carte-du-harnais.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-etat-de-l-art-harnais/maquettes.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md'
---

<intent-contract>

## Intent

**Problem:** Aucune carte ne situe les briques dans les 7 sous-systèmes du papier (arXiv 2609.00006) ni ne dit leur rôle de guide ou de capteur ; le module 6 « Sous-agent et compression » deviendrait trop long quand la V1.4-4 y ajoutera la compaction.

**Approach:** Chaque brique déclare son sous-système et son rôle dans le registre ; la carte est générée de ces déclarations et ouverte en dialogue ; le module 6 est scindé en « Sous-agent » et « Contexte long et carte ».

**Always:**
- Pas de nouvelle dépendance ; ajouts seulement dans les fichiers carrefour (`ui.yaml`, `messages.yaml`, `scenarios.yaml`, `app.py`, `app.js`, `run_e2e.py`, `trace/catalog.py`).
- Textes en fr, en et de, libellés des sous-systèmes traduits une fois dans `ui.yaml`.
- Une brique éteinte reste placée sur la carte, grisée : la carte décrit le harnais complet.

**Never:**
- Ne pas déclarer sous-système et rôle dans `content/bricks/*.yaml` (donnée structurelle, non traduite).
- Ne pas écrire la carte à la main dans le front : elle est générée.
- Ne pas livrer la compaction (story 4) : seul le module 7 est prêt à l'accueillir.

## Décisions de la spec

### Déclaration (sous-système et rôle)

- `bricks/contract.py` : `Subsystem = Literal["loop", "llm", "tools", "memory", "security", "orchestration", "extensibility"]` ; `SensorKind = Literal["computed", "inferred"]`.
- `BrickDeclaration` gagne trois champs :
  - `subsystem: Subsystem` (obligatoire, comme `category`) ;
  - `roles: list[Literal["guide", "sensor"]] = []` (liste vide = rôle `none` de `carte-du-harnais.md`, ni guide ni capteur ; `guide` et `sensor` se cumulent : les hooks) ;
  - `sensor_kind: SensorKind | None = None`, obligatoire si `"sensor"` est dans `roles`, interdit sinon (validateur du modèle, message clair).
- Les 12 déclarations de `bricks/registry.py` reçoivent le placement du tableau de `carte-du-harnais.md` : prompt système `memory`/guide ; raisonnement `llm` ; mémoire courte, RAG, compression `memory` ; mémoire globale `memory`/guide ; skills `extensibility`/guide ; outils natifs `tools` ; MCP `extensibility` ; hooks `extensibility`/guide et capteur calculé ; garde-fous `security`/capteur déduit ; sous-agent `orchestration`.
- Les sous-systèmes sans brique ont leur ligne « cœur » : textes `ui.yaml` `harness_map.core.{loop,llm,orchestration}`, d'après la section « Sans brique » (les bornes sont citées en prose, pas lues à l'exécution).

### Service de la carte

- Pas de nouvelle route ni de nouvel événement : la carte se dessine côté client depuis le dernier `bricks_changed` (`state.bricks`), qui contient déjà toutes les briques, éteintes comprises (`wanted`, `available`).
- `BrickState` (`trace/catalog.py`) gagne, en ajouts à valeur par défaut : `subsystem: str | None = None`, `roles: list[str] = []`, `sensor_kind: str | None = None` ; la session les copie de la déclaration quand elle construit `BrickState`. Les tests qui construisent `BrickState` sans ces champs restent verts.
- Libellés (titre, légende, 7 sous-systèmes, rôles, « cœur », « Non montré ici », sources, boutons) : `ui.yaml` sous `harness_map.*`, fr/en/de. Les noms de briques viennent de `label_text` de `bricks_changed`.
- Ordre des 7 cases : celui du tableau de `carte-du-harnais.md` ; briques dans l'ordre du registre au sein d'un sous-système ; une colonne sous 640 px (maquette 1).

### Dialogue

- Composant réutilisé : l'élément natif `<dialog class="audit-dialog">` (`index.html:306`, `app.css:2879`, ouvert par `showModal()`), que DESIGN.md décrit comme `dialog` sur `{colors.surface-raised}` bordé d'encre. Nouvel élément `<dialog class="audit-dialog harness-map-dialog" id="harness-map-dialog" aria-labelledby="harness-map-title">` ; la variante plein écran est une classe ajoutée dans `app.css`, avec les jetons existants (pastille de discipline : `--color-discipline-{d}`, comme la jauge). Aucune nouvelle famille de composants.
- Ouverture :
  - depuis la consigne du scénario `harness_map` (popover `#scenario-info-popover`, rendu par `renderScenarioInfo`) : bouton « Carte du harnais » sous le texte quand `scenario.id === "harness_map"` ; le popover se ferme à l'ouverture ;
  - depuis le panneau des briques : bouton secondaire en pied de `#bricks`, toujours visible.
- Focus : `showModal()` donne le focus à « Fermer » (`autofocus`) ; à la fermeture (bouton « Fermer », Échap natif, clic hors dialogue), le focus retourne au bouton d'origine mémorisé à l'ouverture (depuis la consigne : le bouton « i » `#scenario-info`, le popover étant fermé).
- La carte est redessinée à chaque ouverture depuis `state.bricks` ; une brique éteinte reçoit une classe grisée.

### Scission du programme

- `content/scenarios.yaml` (`program`) : le module 6 devient « Sous-agent » (`duration_min: 45`, `scenarios: [subagent]`) ; module 7 « Contexte long et carte » (`duration_min: 45`, `scenarios: [compression, harness_map]`). La V1.4-4 insérera `compaction` entre les deux. Le module RAG reste à 45 min (60 min : story 3).
- Miroir `content/i18n/{en,de}/scenarios.yaml` : titres des deux modules (en : « Sub-agent » et « Long context and map »).
- Nouveau scénario `harness_map`, dernier du programme : mêmes briques que `compression` (configuration complète, pas un écart) ; consigne qui dit d'ouvrir « Carte du harnais », de repérer guides et capteurs, et le sous-système sans brique ; aucun appel au modèle exigé (liste `prompts` vide si le schéma l'accepte, sinon un prompt neutre).
- Cumul CAP-40 (`tests/test_program.py`, `before`) : le premier scénario du module 7 (`compression`) doit contenir toutes les briques des modules précédents, donc `subagent` s'ajoute à ses `bricks` (branché, inutilisé). **Risque** : la description d'outils du sous-agent agrandit le contexte ; rejouer `test_every_scenario_fits_the_default_window_with_every_prompt` sur `compression`. Si cela ne tient plus dans 4 096 tokens, ne pas affaiblir les tests : déclarer le sous-agent troisième exception AD-9 (`NEVER_CARRIED` et `NEVER_CARRIED_FR` de `test_program.py`, en-tête de `scenarios.yaml`) et le dire dans la consigne.
- Rappel AD-9 : la consigne de `compression`, premier scénario du module 7, contient exactement « sans le raisonnement ni le RAG » (phrase attendue par `NEVER_CARRIED_FR["rag"]`) ; elle ne dit plus « sans le sous-agent » si `subagent` est ajouté. `restore_memory: true` et `mcp_lazy: true` restent (règles du premier scénario d'un module). Miroirs en et de alignés.
- `docs/guide.md:89` : la ligne du tableau devient deux lignes, modules 6 « Sous-agent » et 7 « Contexte long et carte », 45 min chacun.

### Tests et E2E qui comptent les modules ou citent le module 6

- `tests/test_scenarios.py:41` : `len(program["modules"]) == 6` passe à 7 ; les index 4 (ligne 92) et 2 (ligne 105) ne bougent pas.
- `tests/test_program.py` : l'ordre FR38 reste valable (`subagent` puis `compression`) ; vérifier que `harness_map`, sans brique nouvelle, passe les tests d'ensemble des scénarios (prompts, fenêtre, formes).
- `tests/test_content_language.py` (lignes ~136, 300, 329, 370) : relire les attentes de titres et de modules.
- `tools/e2e/run_e2e.py` : `s_scenarios` (~5717) lit `content["program"]` pour le sélecteur (`Module {i} · … · {n} min`) et prend le module 5 par `program[4]` : suit la scission sans changement, à confirmer ; chercher tout autre E2E qui désigne `subagent` ou `compression` comme module 6.
- Nouveau `tests/test_harness_map.py` (exhaustivité) : chaque brique du registre a un `subsystem` parmi les 7 et des `roles` valides ; `sensor` impose `sensor_kind`, son absence l'interdit ; chaque sous-système a son libellé dans `ui.yaml` fr, en et de ; chaque rôle a son libellé ; `BrickState` porte les champs ; `test_i18n.py` vert avec les nouvelles clés.
- Nouvel E2E `s_harness_map` : lancer `harness_map`, ouvrir par la consigne, vérifier 7 sous-systèmes, 12 briques placées, une brique éteinte grisée, les sources citées ; Échap ferme et le focus revient au bouton d'origine ; rouvrir depuis le panneau des briques et fermer par « Fermer ».

## Points ouverts

- **À vérifier sur arXiv 2609.00006** : les libellés des 7 sous-systèmes (aucun accès web lors de cette spec). Libellés gardés, de `carte-du-harnais.md` : Boucle / Agent loop / Agentenschleife ; Intégration LLM / LLM integration / LLM-Anbindung ; Outils / Tools / Werkzeuge ; Mémoire et contexte / Memory and context / Gedächtnis und Kontext ; Sécurité / Security / Sicherheit ; Orchestration / Orchestration / Orchestrierung ; Extensibilité / Extensibility / Erweiterbarkeit. Une correction ne touche que `ui.yaml`.
- Placement et rôles du tableau : validés avec cette spec (point de contrôle).

## Reports

- Clic sur une brique de la carte pour ouvrir sa carte dans le panneau (facultatif dans la maquette 1).

</intent-contract>
