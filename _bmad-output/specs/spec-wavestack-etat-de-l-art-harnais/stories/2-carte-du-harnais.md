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
- Pas de nouvelle dépendance ; seulement des ajouts (pas de réécriture) dans les fichiers carrefour (`ui.yaml`, `messages.yaml`, `scenarios.yaml`, `app.py`, `app.js`, `run_e2e.py`, `trace/catalog.py`).
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

- Pas de nouvelle route ni de nouvel événement : la carte se dessine côté client depuis le dernier `bricks_changed` (`store.bricks`), qui contient déjà toutes les briques, éteintes comprises (`wanted`, `available`).
- `BrickState` (`trace/catalog.py`) gagne, en ajouts à valeur par défaut : `subsystem: str | None = None`, `roles: list[str] = []`, `sensor_kind: str | None = None` ; la session les copie de la déclaration dans le dictionnaire de chaque brique (`_emit_bricks_now`, `session/app_session.py`), validé par `BricksChangedPayload`. Les tests qui construisent `BrickState` sans ces champs restent verts.
- Vérifié à la revue : `_emit_bricks_now` parcourt toutes les briques du registre, et `emit_initial` émet `bricks_changed` dès le démarrage, avant tout modèle ; le front le garde dans `store.bricks` (la liste est `store.bricks.bricks`). La carte est donc disponible sans modèle chargé ; si `store.bricks` est encore `null`, le bouton reste désactivé.
- Brique grisée : `!(wanted && available)` (éteinte par le participant ou indisponible : extra manquant, capacité du modèle) ; `pending` ne grise pas.
- Libellés (titre, sous-titre, légende, 7 sous-systèmes, rôles, « cœur », « Briques éteintes : grisées, toujours placées », « Non montré ici », sources, boutons) : `ui.yaml` sous `harness_map.*`, fr/en/de. Les noms de briques viennent de `label_text` de `bricks_changed`.
- Légende de la maquette 1, deux lignes : symboles de rôle (◆ guide, ◉ capteur calculé, ◎ capteur déduit, · capacité, c'est-à-dire `roles` vide ; les hooks portent ◆◉) ; « Couleur de la pastille = discipline (prompt ⊂ contexte ⊂ harnais) ». Les symboles sont `aria-hidden`, doublés d'un texte accessible (nom du rôle) sur chaque brique.
- Pastille de discipline : à droite de chaque brique, couleur `--color-discipline-{category}` (champ `category` déjà dans `BrickState`), texte accessible = `category_text`.
- Ordre des 7 cases : celui du tableau de `carte-du-harnais.md` ; briques dans l'ordre du registre au sein d'un sous-système ; une colonne sous 640 px (maquette 1).

### Dialogue

- Composant réutilisé : l'élément natif `<dialog class="audit-dialog">` (`index.html:306`, `app.css:2879`, ouvert par `showModal()`), que DESIGN.md décrit comme `dialog` sur `{colors.surface-raised}` bordé d'encre. Nouvel élément `<dialog class="audit-dialog harness-map-dialog" id="harness-map-dialog" aria-labelledby="harness-map-title">` ; la variante plein écran est une classe ajoutée dans `app.css`, avec les jetons existants (pastille de discipline : `--color-discipline-{d}`, comme la jauge). Aucune nouvelle famille de composants.
- Ouverture :
  - depuis la consigne du scénario `harness_map` (popover `#scenario-info-popover`, rendu par `renderScenarioInfo`) : bouton « Carte du harnais » sous le texte quand `scenario.id === "harness_map"` ; le popover se ferme à l'ouverture ;
  - depuis le panneau des briques : bouton secondaire en pied de `#bricks`, toujours visible.
- Focus : `showModal()` donne le focus à « Fermer » (`autofocus`) ; à la fermeture (bouton « Fermer », Échap natif, clic hors dialogue), le focus retourne au bouton d'origine mémorisé à l'ouverture (depuis la consigne : le bouton « i » `#scenario-info`, le popover étant fermé).
- La carte est redessinée à chaque ouverture depuis `store.bricks.bricks` ; une brique grisée (règle ci-dessus) reçoit une classe dédiée.

### Scission du programme

- `content/scenarios.yaml` (`program`) : le module 6 devient « Sous-agent » (`duration_min: 45`, `scenarios: [subagent]`) ; module 7 « Contexte long et carte » (`duration_min: 45`, `scenarios: [compression, harness_map]`). La V1.4-4 insérera `compaction` entre les deux. Le module RAG reste à 45 min (60 min : story 3).
- Miroir `content/i18n/{en,de}/scenarios.yaml` : titres des deux modules (en : « Sub-agent » et « Long context and map »).
- Nouveau scénario `harness_map`, dernier du programme : mêmes briques que `compression` (configuration complète, pas un écart) ; consigne qui dit d'ouvrir « Carte du harnais », de repérer guides et capteurs, et le sous-système sans brique ; aucun appel d'outil attendu. Le schéma impose au moins un prompt (`scenarios.py:37`, `prompts: list[str] = Field(min_length=1)`) : ne pas l'assouplir, donner un seul prompt neutre sans outil, par ex. « En une phrase, qu'est-ce qu'un harnais d'agent ? ».
- **Cumul CAP-40, tranché à la revue : le sous-agent devient la troisième exception AD-9.** Mesure du 2026-10-24 avec `subagent` ajouté aux `bricks` de `compression` : `test_every_scenario_fits_the_default_window_with_every_prompt` échoue à l'estimation de 2 caractères par token, celle de la CI (`compression` prompt 1 : 1 791 × 1,1 + 63 + 1 654 = 3 687 > 3 584) ; il passe avec la jauge exacte de Qwen3.5-2B (`WAVESTACK_TEST_GGUF`). Comme la CI n'a pas de GGUF, et que le sous-agent offert pendant la démonstration de compression inviterait le petit modèle à déléguer la lecture du journal (le résultat d'outil à compresser ne passerait plus par le contexte principal), le sous-agent n'est pas reconduit :
  - `tests/test_program.py` : `NEVER_CARRIED = {"reasoning", "rag", "subagent"}` ; `NEVER_CARRIED_FR["subagent"] = ("sans le sous-agent",)` ; renommer `test_reasoning_and_rag_stay_in_their_module…` en `test_never_carried_bricks_stay_in_their_module…` ; aucun autre test affaibli, la fenêtre reste vérifiée sur tous les scénarios ;
  - en-tête de `content/scenarios.yaml` : « avec trois exceptions (AD-9) », troisième puce : le sous-agent, montré au module 6, n'est reconduit dans aucun module suivant : sa description d'outil prend de la place dans la fenêtre, et le petit modèle déléguerait la lecture que la compression doit montrer ; rallumez-le à la main ;
  - `compression` garde ses `bricks` actuelles (sans `subagent`), `restore_memory: true` (premier scénario du module 7, déjà exigé par le test) et `mcp_lazy: true`.
- Consigne de `compression`, premier scénario du module 7 : elle doit contenir « sans le sous-agent » et exactement « sans le raisonnement ni le RAG » (`NEVER_CARRIED_FR["rag"]` ; le texte actuel « sans le sous-agent (ni le raisonnement ni le RAG) » ne passe pas). Par ex. : « Les briques des modules précédents restent actives (MCP en lazy loading), sans le sous-agent, et sans le raisonnement ni le RAG ; la brique Compression s'y ajoute… ». Miroirs en et de alignés (sens, pas de test de phrase).
- `docs/guide.md:89` : la ligne du tableau devient deux lignes, modules 6 « Sous-agent » et 7 « Contexte long et carte », 45 min chacun.

### Tests et E2E qui comptent les modules ou citent le module 6

- `tests/test_scenarios.py:41` : `len(program["modules"]) == 6` passe à 7 ; ligne 38 : `len(ids) == 20` passe à 21 (`harness_map`) ; les index 4 (ligne 92) et 2 (ligne 105) ne bougent pas.
- `tests/test_program.py` : l'ordre FR38 reste valable (`subagent` puis `compression`) ; vérifier que `harness_map`, sans brique nouvelle, passe les tests d'ensemble des scénarios (prompts, fenêtre, formes).
- `tests/test_content_language.py` (lignes ~136, 300, 329, 370) : relire les attentes de titres et de modules.
- `tools/e2e/run_e2e.py` : `s_scenarios` (~5717) lit `content["program"]` pour le sélecteur (`Module {i} · … · {n} min`) et prend le module 5 par `program[4]` : suit la scission sans changement, à confirmer ; chercher tout autre E2E qui désigne `subagent` ou `compression` comme module 6.
- Nouveau `tests/test_harness_map.py` (exhaustivité) : chaque brique du registre a un `subsystem` parmi les 7 et des `roles` valides ; `sensor` impose `sensor_kind`, son absence l'interdit ; chaque sous-système a son libellé dans `ui.yaml` fr, en et de ; chaque rôle a son libellé ; `BrickState` porte les champs ; `test_i18n.py` vert avec les nouvelles clés.
- Nouvel E2E `s_harness_map` : lancer `harness_map`, ouvrir par la consigne, vérifier 7 sous-systèmes, 12 briques placées, une brique éteinte grisée, les sources citées ; Échap ferme et le focus revient au bouton d'origine ; rouvrir depuis le panneau des briques et fermer par « Fermer ».

## Points ouverts

- Libellés des 7 sous-systèmes : **résolu** (vérifiés sur arXiv 2609.00006, tableau 1, §2.3, dans cet ordre) ; en / fr / de : Agent loop / Boucle de l'agent / Agentenschleife ; LLM integration / Intégration du LLM / LLM-Integration ; Tools & actions / Outils et actions / Werkzeuge und Aktionen ; Memory & context / Mémoire et contexte / Gedächtnis und Kontext ; Safety & permissions / Sécurité et permissions / Sicherheit und Berechtigungen ; Orchestration / Orchestration / Orchestrierung ; Extensibility / Extensibilité / Erweiterbarkeit. Identifiants de code inchangés (`tools`, `security`…).
- Placement et rôles du tableau : validés avec cette spec (point de contrôle tenu par la revue du 2026-10-24).

## Reports

- Clic sur une brique de la carte pour ouvrir sa carte dans le panneau (facultatif dans la maquette 1).

</intent-contract>

## Revue

### Passe 1 (2026-10-24, SHA revu f24734c)

Relecture de spec avant code (point de contrôle tenu à la place d'Anaël), branche rebasée sur origin/main e15cc3e.

- Important, high, orchestrateur (arXiv vérifié) : libellés « Tools » et « Security » faux ; corrigé (Tools & actions, Safety & permissions, fr/de fidèles ; `carte-du-harnais.md`, question ouverte retirée de `SPEC.md`).
- Important, high, revue (mesure) : ajouter `subagent` à `compression` déborde l'estimation de la CI (3 687 > 3 584) ; corrigé : sous-agent troisième exception AD-9, test de fenêtre intact.
- Important, medium, revue : consigne actuelle de `compression` sans la phrase exacte « sans le raisonnement ni le RAG » ; corrigé (phrase imposée, exemple donné).
- Important, medium, revue : `prompts` vide refusé par le schéma (`min_length=1`) ; corrigé (un prompt neutre, schéma inchangé).
- Important, medium, revue : `test_scenarios.py:38` compte 20 scénarios, oublié ; corrigé (21).
- Nit, low, revue : `state.bricks` au lieu de `store.bricks.bricks`, règle de grisé floue, carte avant tout modèle ; corrigé (vérifié : `emit_initial` émet toutes les briques).
- Nit, low, revue : légende des rôles et pastille de discipline de la maquette 1 seulement évoquées ; corrigé (symboles, texte accessible, jeton `--color-discipline-{category}`).
- Nit, low, revue : service par `bricks_changed` sans route : suffisant (toutes les briques, `wanted`/`available`), confirmé.
