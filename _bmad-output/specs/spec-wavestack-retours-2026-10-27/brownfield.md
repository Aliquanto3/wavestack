# Brownfield : diagnostic du 27/10 (v1.6.2, commit e9baeeb0)

Lu dans le code, sans vérification visuelle. Chemins sous `src/wavestack/` sauf mention.

## Barre (CAP-1, CAP-2)

- Montant absent : `web/static/bar.js:124-125`, `paid = c.calls > 0`. `models/cloud_base.py:1266-1281` ne calcule `out.cost` que si le modèle a un `pricing`, alors que l'empreinte (`:1309`) est calculée pour tout modèle cloud. `_accumulate` n'incrémente `calls` que si un coût existe. Gemma n'a volontairement pas de `pricing` (`wavestack.toml:549`), d'où une empreinte sans montant.
- Débordement : `#bar-spend-detail` et `#bar-spend-footprint` portent la classe `.bar-flyout-note` (`web/static/pages.css:309`), sans `overflow-wrap`, comme élément de grille sans `min-width: 0` (`.bar-flyout`, `pages.css:261`). La plage est construite sans espace (`i18n.js:71`).
- Journal : `bar.js:27-36` ne garde que les enveloppes `security_event`. `trace/catalog.py:2272` `SecurityEventPayload` est émis par `_emit_security` (`session/app_session.py`, appels MCP et verdicts des garde-fous). Les appels cloud passent tous par `cloud_base.py` (`record_spend`, `:1321`) ; les appels locaux passent ailleurs (à repérer).

## Harnais (CAP-3, CAP-4, CAP-5)

- Boutons de la carte : `index.html:110` porte `class="harness-map-open"`, une classe jamais définie. `index.html:348` porte `class="primary"`, qui n'a de style que dans `.drawer-actions` (`app.css:104-120`).
- Contenu : `content/ui.yaml:1223-1250` (`main.harness_map.*`). Sources sans lien en `:1231` (Barbaste et al., arXiv 2609.00006 ; Böckeler, martinfowler.com), rendues par `app.js:7905`. Légende des rôles en `:1227`, rendue par `app.js:7900`. « Places de marché » en `:1230`. Le glossaire `content/glossary.yaml` n'a aucune entrée guide ni capteur (citation `[[g:clé]]`).
- « Éteinte » : `ui.yaml:243`, rendu par `app.js:1446`. Étiquettes « … engineering » : `ui.yaml:201-203`, `disciplineLegend()` (`app.js:188-193`, appelée en `:1253`) et `card.dataset.discipline` (`app.js:1273`).
- Explications des briques : `content/bricks/*.yaml` `explanation_text`, affichées dans une info-bulle « ? » (`app.js:1368-1390`, Chromium seulement). Le motif `<details>` existe déjà (`app.js:1732`, `:3395`, `:4618`).
- Actions forcées : `ui.yaml:270-279` (`main.force.*`), `messages.yaml` (`session.arm.*`, `session.forced.*`), `app_session.py:5325` et suivantes (`arm`, `disarm`, `ArmRefused`), `web/app.py:1626-1644` et `:207` (`ArmIntention`, `DisarmIntention`), `trace/catalog.py`, `session/effects.py`, `bricks/contract.py` (champ `force`), `mcp/servers.py`, `subagent.py`, `app.js:1366` et `:1798-2160`, `app.css:2548` et `:3784`, `tests/test_forced.py`, ainsi que d'autres tests et E2E (grep `force`, `arm`).

## Atelier LLM (CAP-6)

- Découpage : `llm.js:461-472` lit `$("llm-prompt").value`. Le texte de départ vient de `content/llm_lab.yaml:336`, le brouillon est gardé dans localStorage (`llm.js:110-118`, `:2488`). Limite de 2 000 caractères (`llm.html:118`, `session/llm_lab.py:28`).
- Génération : `llm.js:2017-2030` envoie le texte brut ; le gabarit de chat est appliqué côté serveur et n'est pas affiché.
- Couleurs : alternance par parité (`llm.css:258-264`, `--color-primary-soft` et `--color-accent-soft`), sans légende.
- Fragment : `llm.js:1908` (`unit === "fragment"`), textes en `llm_lab.yaml:433-442`. Le débit s'affiche en `llm.js:1985`. `greenops.py` existe mais n'est pas branché sur `llm_lab.py`.

## Atelier RAG (CAP-7)

- Génération : options fixes `active` et `not_run` (`rag/lab.py:129-130`) ; libellé en `app_session.py:11024-11031`, affiché comme sous-titre de la tuile (`rag.js:787-790`). Les sélecteurs passent par le générique `optionSelect` (`rag.js:241-262`), et les options de modèle viennent de `kind_options()` (`rag/lab.py:1031`, `[[rag_lab.embeddings]]`).
- Contexte long et CAG : il faut une fenêtre d'au moins `NO_INDEX_WINDOW` = 16384 (`rag/lab.py:225`), plus un moteur local pour le CAG (`app_session.py:11097-11127`). Le réglage de la fenêtre vit dans `index.html:290-314` et `app.js:2946-3142`, via `/api/intentions/context_window` (`set_context_window`, `app_session.py:2769`). `rag.html` ne charge pas `app.js`.

## Atelier MCP (CAP-8, CAP-9)

- Serveurs : `mcp/servers.py:42-52` (local en stdio, datagouv, mslearn, github), textes dans `content/mcp.yaml`. Aucun champ de logo ; seuls des emojis marquent le type de capacité (`mcp.js:1683-1694`).
- Réponse tronquée : `mcp.js:415-416` `clip(...)`, 60 caractères (`mcp.js:117`). Le texte complet est dans `renderModelPane` (`mcp.js:989`).
- Schéma « Avant » : `buildBefore()` (`mcp.js:1372-1420`). `BEFORE = ("local","datagouv","mslearn")` (`mcp/lab.py:85`), `BEFORE_SHAPES` sans github (`mcp.js:1375`, d'où le rond par défaut), `before.integrations` sans github (`content/mcp_lab.yaml:196`, d'où la ligne vide). Classe `.is-hidden-side` sur les serveurs réseau (`mcp.css:1660`, d'où les pointillés). « Avec MCP » est un SVG dessiné par JS dans `#mcp-arch`.

## Sécurité (CAP-10)

- `web/static/security.html` (177 lignes), `security.js` (352 lignes), textes `security.*` produits par `AppSession.security_state()` (`app_session.py:13815`). Composants déjà en place : `.sec-question-card`, la table `.sec-matrix` avec `status-chip`, et `disclosure-row` (`pages.css:387-434`). Charte : `DESIGN.md`.
