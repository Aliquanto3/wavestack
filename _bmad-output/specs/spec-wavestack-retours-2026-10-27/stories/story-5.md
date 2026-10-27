---
title: 'Story 5 : Carte du harnais et panneau des briques'
type: 'feature'
created: '2026-10-27'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-retours-2026-10-27/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-retours-2026-10-27/brownfield.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Dans la carte du harnais, les deux boutons (`index.html:110` `harness-map-open`, une classe jamais définie ; `index.html:348` `class="primary"` hors `.drawer-actions`, donc sans style) n'ont pas le style de l'application ; les deux sources (Barbaste et al., arXiv 2609.00006 ; Böckeler, martinfowler.com) sont du texte brut, non cliquables ; « guide », « capteur calculé » et « capteur déduit » ne sont définis nulle part ; « places de marché » apparaît en français là où le reste de l'app dit déjà « marketplaces ». Dans le panneau des briques, le libellé « Éteinte » encombre une brique dont le switch dit déjà qu'elle est éteinte ; les disciplines s'affichent « Prompt engineering », « Context engineering », « Harness engineering » alors que la légende voisine dit déjà « prompt ⊂ contexte ⊂ harnais » ; les explications de brique (Outils, MCP, Sous-agent, Garde-fous, Compression, et les autres bricks qui en ont) s'ouvrent dans une info-bulle Popover API (Chromium seulement), moins accessible que le motif `<details>` déjà utilisé ailleurs dans l'app (`brickOptions`, `reasoningBlock`).

**Approach:** Styler les deux boutons de la carte en étendant les sélecteurs CSS partagés (`.harness-map-open`, `.harness-map-head button.primary`) plutôt qu'en dupliquant des règles. Remplacer le texte « sources » par deux `<a target="_blank" rel="noopener">`, URL vérifiées à la main (voir Code Map). Ajouter trois entrées de glossaire (`guide`, `sensor_computed`, `sensor_inferred`) citées dans la légende de la carte via `[[g:clé]]` (le mécanisme générique de `glossary.js` les rend cliquables automatiquement). Remplacer « places de marché » par « marketplaces » (déjà le choix de l'anglais et de l'allemand). Faire disparaître le libellé de statut quand une brique est éteinte et disponible (`brickStatus` renvoie `""`, pas de `<p>` ajouté). Raccourcir les trois libellés de discipline à « Prompt », « Contexte », « Harnais ». Remplacer l'info-bulle « ? » par un `<details class="brick-explain">` : son résumé montre le premier bloc d'explication, visuellement replié à deux lignes par `-webkit-line-clamp` tant qu'il n'est pas ouvert ; les blocs suivants (paragraphes et listes) apparaissent dessous une fois ouvert. L'état ouvert/fermé reste dans `store.openBrickHelp`, comme avant.

## Boundaries & Constraints

**Always:**
- Les deux boutons de la carte utilisent les mêmes règles CSS que les autres boutons de l'app (primaire plein / secondaire contour), pas de nouvelle palette.
- Les liens des sources ouvrent dans un nouvel onglet (`target="_blank"`, `rel="noopener"`), URL vérifiées avant d'être écrites (voir Code Map).
- Les trois termes du glossaire existent en fr, en, de, mêmes clés, mêmes définitions traduites.
- Le panneau des briques ne perd aucune information : l'explication complète reste accessible après un clic, au clavier (`<details>`/`<summary>` sont nativement accessibles au clavier) comme à la souris.
- Fichiers partagés (16.1 `bar.js`/`pages.css`, 16.2 `glossary.yaml`, 16.3 `mcp.*`) : non touchés, sauf l'ajout en fin de `glossary.yaml` (fr/en/de), sans réordonner l'existant.

**Never:**
- Ne pas toucher au code des actions forcées (`forcedToggle`, `cardForce`, `BRICK_CONTROLS`, `.force-form`, `openBrickHelp` clé `"force-section"`) : la story 16.8 les retire. Leur propre info-bulle « ? » (`force-help`/`#explain-force-section`) garde le motif Popover API tel quel.
- Ne pas inventer de réponse à la question ouverte « Peut-être » de la carte (SPEC.md Open Questions) : rien n'a été ajouté sur ce point, à trancher par Anaël.
- Ne pas changer `content/mcp.yaml`, `bar.js` ni `pages.css`.

## Code Map

- `src/wavestack/web/static/app.css:102-150` et `:2678-2690` — sélecteurs `.harness-map-open` et `.harness-map-head button.primary` ajoutés aux règles de bouton partagées (fond, contour, relief pressé, désactivé).
- `src/wavestack/web/static/app.css:2214-2246` — nouveau bloc `.brick-explain`/`.brick-explain-summary`/`.brick-explain-list` (résumé replié à deux lignes par `-webkit-line-clamp: 2` tant que `[open]` est absent).
- `src/wavestack/web/static/app.js:1325-1334` (`renderBricks`) — la ligne de statut n'est ajoutée que si `brickStatus()` renvoie un texte non vide.
- `src/wavestack/web/static/app.js:1373-1397` (`renderBricks`) — le bloc `brick.explanation_text` construit un `<details id="explain-{brick.id}" class="brick-explain">` au lieu du bouton `.brick-help` + popover.
- `src/wavestack/web/static/app.js:1443-1446` (`brickStatus`) — `!brick.wanted` renvoie `""` au lieu de `t("main.bricks.status.switched_off")`.
- `src/wavestack/web/static/app.js:7902-7920` (`drawHarnessMap`, nouvelle fonction `harnessMapSources`) — les sources en deux `<a>`, URL en dur (non traduites) : `https://arxiv.org/abs/2609.00006`, `https://martinfowler.com/articles/harness-engineering.html`.
- `content/ui.yaml` (+ `content/i18n/{en,de}/ui.yaml`) — `main.harness_map.legend_roles` cite `[[g:guide]]`/`[[g:sensor_computed]]`/`[[g:sensor_inferred]]` ; `sources` scindé en `sources_label`/`source_arxiv`/`source_fowler` ; `not_shown` dit « marketplaces » ; `main.disciplines.{prompt,context,harness}` raccourcis ; `main.bricks.status.switched_off` et `main.bricks.help_label` retirés (devenus inutilisés).
- `content/glossary.yaml` (+ `content/i18n/{en,de}/glossary.yaml`) — trois entrées ajoutées en fin de fichier : `guide`, `sensor_computed`, `sensor_inferred`.
- `tests/test_glossary.py:36-38` — plafond du glossaire fr relevé de 60 à 70 (contrat partagé avec la story 16.2, qui ajoute « fragment » et porte le compte à 59 avant cette story).

**URL vérifiées (curl, titre de page) :**
- `https://arxiv.org/abs/2609.00006` → titre « [2609.00006] Harness Engineering: Anatomy, Architecture, and Evolution of Coding Agents — A Source-Code Study of Eleven Systems », correspond à Barbaste et al. cité par le SPEC et `carte-du-harnais.md`.
- `https://martinfowler.com/articles/harness-engineering.html` → « Harness engineering for coding agent users », par Birgitta Böckeler, martinfowler.com, texte « frames the elements of a harness as guides and sensors, which may be computational or inferential » (correspond exactement à guide/capteur calculé/capteur déduit).

## Tests et E2E à réaligner

- `tests/test_glossary.py::test_the_french_glossary_has_40_to_70_valid_terms` (renommé, plafond relevé, commentaire d'une ligne).
- `tools/e2e/run_e2e.py` :
  - `_DISCIPLINE_NAMES` (story 33, scénario `s_disciplines`) : `["Prompt", "Contexte", "Harnais"]` au lieu des libellés « engineering ».
  - `s_disciplines` : la vérification « Prompt système éteint : … « Éteinte » » devient « plus de ligne d'état » (`p.brick-status` absent) ; l'ouverture/fermeture de l'explication passe par `#explain-system_prompt` (un `<details>`) et `e.open` au lieu de `:popover-open` ; plus de `page.keyboard.press("Escape")` (un `<details>` ne se ferme pas par Échap).
  - `_content_language` (scénario `s_content_language`, brique Outils en de/en) : ouverture de l'explication par un clic sur `summary` au lieu de `.brick-help` ; en mode projection, l'état ouvert du `<details>` survit au rendu (porté par `store.openBrickHelp`), donc plus besoin de recliquer ni d'Échap.
  - `s_harness_map` : deux vérifications ajoutées — les deux sources sont des `<a target="_blank">` vers les URL exactes ; les deux boutons de la carte ont la couleur de fond des styles de bouton partagés (`--color-surface-raised` pour « Carte du harnais », `--color-primary` pour « Fermer »).

## Verification

**Commands exécutées pendant le développement :**
- `uv run pytest -q --tb=short tests/test_glossary.py tests/test_i18n.py` — 220 passés.
- `uv run pytest -q --tb=short tests/test_bricks.py tests/test_content_language.py` — 100 passés.
- `uv run python .claude/cost-kit/controle_rapide.py` — propre (ruff check + format).

**E2E à lancer à la relecture (non lancés ici : poste à RAM partagée, 4 agents en parallèle) :**
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only harness_map disciplines content_language`

</frozen-after-approval>
