---
title: 'Story 17.3 : Atelier MCP — pictogrammes, colonne Modèle et nom qui déborde'
type: 'fix'
created: '2026-10-27'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
---

## Contexte

Trois défauts de recette relevés par Anaël sur l'Atelier MCP (`/mcp`) après la v1.7.0 :

**(a) Pictogrammes illisibles en thème sombre.** Les logos neutres de WaveStack
(`src/wavestack/web/static/logos/mcp/_default.svg`, `datagouv.svg`, `mslearn.svg`,
`local.svg`) sont dessinés en navy fixe (`#33257A`), illisible sur le fond sombre. Ce
ne sont pas des logos de marque (voir `docs/logos-atelier-mcp.md`) : ils peuvent être
recolorés en CSS, contrairement au GitHub Invertocat (`github.svg`/`github-white.svg`,
déjà géré par sa propre variante, jamais touché ici).

**(b) Colonne « Modèle » toujours « SLM local ».** `content/mcp_lab.yaml` (`columns.model`)
ne porte qu'un libellé et une explication, lus sans condition par `mcp.js`
(`columnName`, `columnExplain`, et en dur dans le schéma « Avant MCP »,
`buildBefore:1400`). Avec un modèle cloud actif, le texte reste « SLM local », ce qui
est faux : le modèle ne tourne pas sur le poste.

**(c) Nom du modèle qui déborde.** Dans le schéma (bloc « robot », onglet Architecture),
le nom du modèle actif (`model.label`, parfois un nom de fichier long) peut dépasser sa
case : aucune règle de repli (retour à la ligne, ellipse) sur `.mcp-robot small`.

## Critères d'acceptation

- **Given** le thème sombre actif, **when** l'Atelier MCP affiche un serveur sans logo de
  marque dédié (glossaire local, data.gouv.fr, Microsoft Learn, ou le pictogramme de
  repli), **then** son pictogramme reste visible (recoloré), sans changer le logo GitHub
  (toujours sa propre variante clair/sombre).
- **Given** un modèle cloud actif, **when** l'Atelier MCP affiche la colonne Modèle (en-tête
  de la Séquence, bloc « robot » de l'Architecture, schéma « Avant MCP »), **then** le
  libellé et l'explication affichés viennent de la variante cloud du contenu
  (`columns.model.name_cloud_text` / `explain_cloud_text`), jamais « SLM local ».
- **Given** un modèle local actif, **when** la même colonne s'affiche, **then** le libellé
  et l'explication restent ceux d'aujourd'hui (« SLM local » et son explication).
- **Given** un nom de modèle long, **when** il s'affiche dans le bloc « robot », **then** il
  se présente sur plusieurs lignes (pas de dépassement visuel) et son texte complet reste
  lisible via l'attribut `title`.
- **Given** `content/mcp_lab.yaml` sans `name_cloud_text`/`explain_cloud_text` sur
  `columns.model`, **when** la page le charge, **then** la validation pydantic
  (`McpLabContent`) échoue avec un message explicite (le fichier reste invalide, la page
  le signale sans planter).

## Tâches

1. `src/wavestack/web/static/mcp.css` : filtre `invert(1)` en thème sombre sur
   `.mcp-server-logo` sauf `.has-dark`/`.is-dark` (GitHub) ; `overflow-wrap`/`min-width: 0`
   sur `.mcp-robot`/`.mcp-robot small`.
2. `src/wavestack/mcp/lab.py` : `ColumnText.name_cloud_text`/`explain_cloud_text`
   (optionnels), validation que `columns.model` les porte (non vides).
3. `content/mcp_lab.yaml`, `content/i18n/{en,de}/mcp_lab.yaml` : `columns.model` avec ses
   variantes cloud.
4. `src/wavestack/web/static/mcp.js` : `columnName`/`columnExplain` suivent l'hébergement
   du modèle actif (`modelInfo().hosting === "network"`) pour la colonne `model` (en-tête
   de Séquence, bloc « robot », schéma « Avant MCP », tous dérivés de ces deux fonctions) ;
   `title` sur le nom du modèle affiché (en-tête et bloc « robot »).

## Tests

- `tests/test_mcp_lab.py` (contenu existant, validation pydantic) — ciblé.
- `tests/test_i18n.py -k mcp` (cohérence fr/en/de de `mcp_lab.yaml`) — ciblé.
- `uv run python .claude/cost-kit/controle_rapide.py`.

## E2E à lancer ou réaligner (non lancés ici, run à RAM limitée)

- Scénarios existants de l'Atelier MCP (chercher `mcp_` dans `tools/e2e/`) : à rejouer en
  thème sombre pour (a), et avec un modèle cloud actif pour (b) — probablement absents
  aujourd'hui (aucun scénario ne force un modèle cloud sur cette page).
- Nouveau scénario recommandé : `mcp_model_column_follows_cloud_model` (modèle cloud actif,
  vérifie le libellé et l'explication de la colonne Modèle dans les trois schémas).
- Nouveau scénario recommandé : `mcp_dark_theme_logos_visible` (capture ou contraste des
  pictogrammes neutres en thème sombre).
