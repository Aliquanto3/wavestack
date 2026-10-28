---
title: 'Story 10 : Panneau des briques allégé (suite de la story 5, CAP-4)'
type: 'feature'
created: '2026-10-28'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-retours-2026-10-27/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-retours-2026-10-27/brownfield.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-retours-2026-10-27/stories/story-5.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La story 5 (CAP-4) a remplacé l'info-bulle « ? » du panneau des briques par un
`<details class="brick-explain">`, mais chaque carte garde encore une ligne de puces
(`category_text` + `hosting_text`), une ligne « Peuvent sortir du poste : … » toujours visible
pour Outils et MCP, une puce « Local » par option, et le lien « Atelier MCP ↗ » sur sa propre
ligne : cinq à six lignes par carte avant même l'explication, pour un panneau qui doit tenir sur
un seul écran avec dix briques.

**Approach:** Retirer les puces de catégorie/hébergement des cartes (le contrat serveur
`category_text`/`hosting_text` reste inchangé, lu ailleurs — `brickStatus`, schéma). Ne garder
qu'un badge « 🌐 RÉSEAU » dans la ligne du titre, seulement si une option activée de la brique
sort du poste. Dans la liste des options, retirer la puce « Local » par ligne (ne garder que
« RÉSEAU » quand l'option sort). Remplacer la ligne « Peuvent sortir du poste » (texte complet,
toujours visible) par une ligne d'une phrase, seulement quand au moins une option activée sort
du poste (« 🌐 Sort du poste : {noms des options activées} ») ; le texte complet
(`outbound_text`, inchangé côté serveur) devient le dernier paragraphe du `<details
class="brick-explain">`. Réduire l'aperçu replié de l'explication à une ligne
(`-webkit-line-clamp: 1`). Déplacer le lien « Atelier MCP » de sa propre ligne à côté du résumé
des serveurs MCP (`<details class="brick-options">`), dans une rangée flexible, texte raccourci
« Atelier MCP » (revue) : un sibling du `<details>`, jamais dans son `<summary>`, pour qu'un clic dessus
n'ouvre/ne ferme pas la liste.

## Boundaries & Constraints

**Always:**
- Le contrat serveur (`category_text`, `hosting_text`, `outbound_text` dans
  `BrickContent`/`_emit_bricks_now`) reste inchangé : aucune modification côté `src/wavestack/
  session`, `src/wavestack/bricks`, `src/wavestack/trace`.
- Le texte complet de ce qui sort du poste (`outbound_text`) reste accessible, en entier, dans
  l'explication de la brique — jamais perdu, seulement replié par défaut.
- Le lien « Atelier MCP » reste un `<a>` natif, accessible au clavier (focus, Entrée), avec le
  même `href="/mcp"` et le même `title`.
- Les nouvelles clés i18n existent en fr, en, de, mêmes clés (`main.bricks.outbound_summary` ;
  `main.bricks.mcp_workshop` raccourci, revue), `{names}` dans les trois langues.

**Never:**
- Ne pas retirer `category_text`/`hosting_text` du schéma JSON ni des fichiers `content/
  bricks/*.yaml` : lus ailleurs (`app.js:~7165`, infobulles du schéma).
- Ne pas toucher au serveur (`app_session.py`, `contract.py`, `catalog.py`).
- Ne pas changer les contrôles des actions forcées (`BRICK_CONTROLS`, `.force-form`) : hors
  périmètre (story 16.8).

## Code Map

- `src/wavestack/web/static/app.js:1230-1310` (`renderBricks`) — plus de `div.brick-tags`
  (`category-chip`, `hosting-tag-local`) ; le badge réseau rejoint la ligne `.brick-head` ;
  nouvelle ligne `p.brick-outbound` en résumé (une phrase, options activées et réseau
  seulement), condition `!parentOff && networkOptions.length`.
- `src/wavestack/web/static/app.js:1660-1712` (`brickOptions`) — plus de puce « Local » par
  option ; la puce réseau seulement si `option.network`.
- `src/wavestack/web/static/app.js:1306-1332` (`renderBricks`) — `brickOptions` + lien Atelier
  MCP regroupés dans `div.brick-options-row` (brique `mcp` seulement) ; le `<details
  class="brick-explain">` gagne un dernier paragraphe `p.brick-outbound` (texte complet) quand
  la brique a `explanation_text` et `outbound_text`.
- `src/wavestack/web/static/app.css:2126-2420` — suppression de `.brick-tags`, `.category-chip`
  (3 règles, devenues mortes) ; `.hosting-tag-local` gardé (utilisé hors du panneau : indicateur
  de modèle, page annexe) ; `-webkit-line-clamp` de `.brick-explain-summary` : 2 → 1 ; nouvelle
  `.brick-options-row` (flex, `<details>` + lien Atelier) ; `.brick-workshop-link` ajuste
  `flex: 0 0 auto`.
- `content/ui.yaml` (+ `content/i18n/{en,de}/ui.yaml`), section `main.bricks` — deux nouvelles
  clés : `outbound_summary` (« 🌐 Sort du poste : {names} »), `mcp_workshop` raccourci
  (« Atelier MCP », revue ; plus de `mcp_workshop_short`).
- `docs/guide.md:51-55` — description du panneau des briques réalignée (plus de catégorie
  affichée, badge réseau conditionnel, aperçu d'une ligne).

## Tests et E2E à réaligner

- `tools/e2e/run_e2e.py::_outbound_card` (appelée par `s_network_tools`) — ne vérifie plus un
  `p.brick-outbound` visible et complet, options repliées ; vérifie désormais une ligne
  (options activées et réseau seulement : « Jours fériés, Résumé Wikipédia, Lecture de page
  web ») repliée, puis le texte complet (tous les outils déclarés, serveurs MCP publics compris)
  dans l'explication, dépliée puis repliée.
- `tools/e2e/run_e2e.py` (scénario `s_disciplines`) — l'assertion de la puce `.brick-network`
  (« 🌐 RÉSEAU ») est inchangée (même classes, nouveau parent `.brick-head`) ; non modifiée.
- `tools/e2e/run_e2e.py` (scénario `s_mcp_lab`) — l'assertion du lien `a.brick-workshop-link`
  (`href="/mcp"`, count 1) est inchangée (même élément, nouvel emplacement dans le DOM).
- `tests/` : aucun test serveur ne lit `category_text`/`hosting_text`/`outbound_text` côté rendu
  HTML (contrat inchangé) ; pas de modification.
- `docs/guide.md` : paragraphe du panneau des briques réaligné (puces et aperçu).
- `.claude/skills/demo-recette-chrome/SKILL.md`, `docs/recette/cahier-tests-chrome.html` :
  vérifiés, aucune mention des éléments retirés.

## Verification

**Commandes exécutées pendant le développement :**
- `uv run python .claude/cost-kit/controle_rapide.py` — propre (ruff check + format).
- `uv run pytest -q --tb=short tests/test_bricks.py tests/test_i18n.py` — 245 passés.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge
  --only native_tools network_tools disciplines mcp_full subagent mcp_lab` — 217 vérifications
  réussies, 0 échec. Captures régénérées et gardées (scénarios lancés) : 01, 01b, 05, 08, 08b,
  10, 10b, 19, 29, 31, 32, 33, 40, 41, 42, 61, 62, 63 ; capture 29 et 10 relues à l'œil (gain de
  place visible : jusqu'à cinq cartes de brique visibles sans défilement contre deux ou trois
  avant).

**Non lancé :** suite complète pytest (tests ciblés suffisants, aucun code serveur touché) ; les
autres scénarios E2E (hors périmètre de la story).

</frozen-after-approval>

## Revue

### Passe 1 (2026-10-28, SHA revu 1e686639)

Base à jour (origin/main 3e4a3de4), pas de rebase.

- Important · medium · second avis · corrigé : la sous-option Reranking (carte RAG, `rerankParts`) gardait la puce « Local », contraire à l'intention (2) ; puce retirée.
- Important · medium · second avis · corrigé : le badge « 🌐 RÉSEAU » dans le `<label class="brick-head">` entrait dans le nom accessible de l'interrupteur (« Outils RÉSEAU ») ; `aria-hidden="true"` comme le cadenas voisin, l'information reste lue par la ligne « 🌐 Sort du poste : … », toujours présente dans le même cas. Le clic sur le badge bascule la brique comme un clic sur son nom : comportement du titre, gardé.
- Important · low · second avis · corrigé : le lien Atelier MCP n'était rendu qu'avec au moins un serveur ; de nouveau inconditionnel.
- Nit · low · second avis · corrigé : « Atelier ↗ » sans « MCP » dans le nom accessible, flèche de lien externe pour une page interne, clé `mcp_workshop` morte ; texte « Atelier MCP » (« MCP workshop », « MCP-Werkstatt ») porté par `mcp_workshop`, `mcp_workshop_short` supprimée.
- Nit · low · second avis · corrigé : E2E des nouvelles règles ajoutés (disciplines : aucune puce « Local », aucun « RÉSEAU » sur brique éteinte ; mcp_lab : texte du lien « Atelier MCP »).
- Rejeté · Pyright `ok: bool` dans run_e2e.py : aucune de ces lignes n'est introduite par ce commit.
- Complexité : 0 constat (rendu par carte, aucune structure qui grossit).

Tests : contrôle rapide OK ; `tests/test_bricks.py tests/test_i18n.py` 245 passés ; E2E disciplines, native_tools, network_tools, mcp_full, mcp_lab (185 OK) puis rag, rag_rerank (75 OK), captures de ces scénarios regénérées.
