---
title: 'Story 16.3 : Atelier MCP, logos, réponse dépliable et schéma Avant/Avec (CAP-8)'
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

**Problem:** Dans l'Atelier MCP, aucun serveur n'a de logo (seuls des emojis marquent le réseau
et le type de capacité), la réponse finale du modèle se clippe à 60 caractères dans Séquence
(`mcp.js:415`) sans moyen de la lire en entier, et le schéma « Avant MCP » (`BEFORE` dans
`mcp/lab.py`, `BEFORE_SHAPES` dans `mcp.js`, `before.integrations` dans `content/mcp_lab.yaml`)
a été écrit pour 3 serveurs : GitHub (4ᵉ serveur depuis la story 3 de la V1.1 vague 2) y
apparaît avec la forme ronde par défaut, une ligne vide (`before.integrations` ne l'a pas) et
une ligne de source en pointillés (`.is-hidden-side`, pensée pour un serveur réseau quelconque).

**Approach:** Un logo local par serveur (SVG, jamais chargé du réseau), la réponse finale
dépliable en entier (le mécanisme de détail au clic existe déjà pour chaque flèche de
Séquence, il manquait seulement le texte complet) et lisible aussi sous « Envoyer au
modèle », et un schéma Avant/Avec dont les lignes et les rangées sont dérivées de
`servers.ALL_IDS` plutôt qu'écrites en dur pour 3 serveurs.

## Boundaries & Constraints

**Always:**
- Logos en SVG locaux sous `src/wavestack/web/static/logos/mcp/{id}.svg`, servis par
  `/static/logos/...`, jamais chargés du réseau. Faute d'accès réseau pour vérifier en direct
  les conditions d'usage à jour des marques GitHub, Microsoft et de la charte data.gouv.fr
  (Marianne exclue, réservée à l'État), les quatre pictogrammes sont dessinés pour l'occasion,
  sans reproduire une marque déposée ni la Marianne (détail et contrat pour un futur serveur :
  `docs/logos-atelier-mcp.md`). `McpServer.logo` (nouvelle propriété, `wavestack.mcp.servers`)
  retombe sur `_default.svg` pour un id inconnu ; le champ est servi dans `GET /api/mcp_lab`
  (`_mcp_lab_servers`).
- `servers.ALL_IDS` (nouvelle constante, `local`, `datagouv`, `mslearn`, `github`) est la seule
  source des ids de `mcp_servers()` et de `mcp.lab.BEFORE` (avant : une liste de 3, dupliquée).
  Un serveur ajouté plus tard (story 16.6) n'a qu'à y figurer : le schéma « Avant MCP » grandit
  seul (lignes du host et des deux zones recalculées par `buildBefore()` à chaque rendu,
  `grid-row: -1` au lieu de `/4`) et `before.integrations` sans sa ligne échoue clairement à la
  validation du contenu (pydantic), au lieu d'afficher une ligne vide.
- GitHub reçoit sa propre forme (carré, `BEFORE_SHAPES.github` dans `mcp.js`) et sa ligne
  « Code pour l'API GitHub » (`content/mcp_lab.yaml` et ses surcouches en/de). La classe
  `.is-hidden-side` (ligne de source en pointillés) est retirée partout dans le schéma
  Avant/Avec : chaque source, locale ou réseau, s'affiche en entier.
- La réponse finale garde son aperçu à 60 caractères dans la ligne de Séquence (`clip()`,
  inchangé) ; son détail, déjà dépliable au clic comme toute flèche, porte désormais le texte
  complet (`arrow.full`, jamais tronqué). Sous « Envoyer au modèle », une ligne neuve
  (`#mcp-ask-answer`) affiche la dernière réponse finale en entier, sous la ligne de modèle
  existante.
- Textes fr + surcouches `content/i18n/{en,de}/` (ui.yaml : `mcp.ask.answer`,
  `mcp.detail.reply` ; mcp_lab.yaml : `before.integrations.github`), mêmes clés.
- Aucune nouvelle dépendance Python ou JS.

**Never:** toucher `app_session.py`, `content/ui.yaml`, `app.js` ou `pages.css` au-delà de
l'ajout strictement nécessaire (un champ `logo` et deux clés de texte) ; changer
`lab.SERVER_IDS` (3, la Séquence ne couvre pas GitHub, hors périmètre) ; reproduire une marque
déposée ou la Marianne ; charger un logo depuis le réseau.

## I/O & Edge-Case Matrix

| Cas | Entrée | Sortie |
|---|---|---|
| Sélecteur de serveur | `GET /api/mcp_lab` | 4 serveurs, chacun avec `logo` (`mcp/<id>.svg`), affiché hors ligne |
| Id futur sans logo dédié | `McpServer("futur", url).logo` | `mcp/_default.svg` (fichier présent) |
| Réponse finale (Séquence) | clic sur la ligne de réponse | détail déplié : texte complet, jamais tronqué |
| Réponse finale (par le modèle) | un tour « par le modèle » terminé | `#mcp-ask-answer` affiche la réponse en entier |
| Schéma Avant MCP | vue « Avant MCP » | GitHub : forme carrée, ligne « Code pour l'API GitHub », aucune source en pointillés |
| Contenu invalide | `before.integrations` sans une des 4 clés | `McpLabContent` lève (`before.integrations : il faut exactement …`) |

## Tests & Validation

- `tests/test_mcp.py` : `ALL_IDS`, `McpServer.logo` (4 serveurs connus + repli), fichiers SVG
  présents sur disque.
- `tests/test_mcp_lab.py` : `BEFORE == ALL_IDS`, `before.integrations` complet (4 clés, texte
  GitHub), validation qui échoue sans une clé, `logo` dans `mcp_lab_state()["servers"]`.
- E2E (`--only mcp_lab mcp_lab_page`) : 4 logos chargés dans le sélecteur ; réponse finale
  dépliée en entier dans Séquence et sous « Envoyer au modèle » ; vue « Avant MCP » avec la
  forme et la ligne de GitHub, sans ligne en pointillés ; aucune erreur JavaScript.

</frozen-after-approval>
