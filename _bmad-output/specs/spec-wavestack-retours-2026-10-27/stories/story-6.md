---
title: 'Story 6 : Serveur MCP avec ressource et prompt'
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

**Problem:** L'Atelier MCP n'a que des serveurs qui exposent des outils (`mcp/servers.py:42-52` : local stdio, datagouv, mslearn, github). CAP-9 veut qu'un serveur expose aussi au moins une ressource et un prompt, utilisables jusqu'à la réponse du modèle, pour montrer ces deux primitives MCP à l'apprenant. `mcp/lab.py:64-65,298-299,582-583` sait déjà appeler `resources/list` et `prompts/list` quand un serveur les annonce — il manque seulement un serveur qui les annonce pour de vrai.

**Approach:** Choisir entre un serveur public existant (ressources seulement, aucun prompt trouvé en vivant) et un petit serveur maison en Streamable HTTP local (ressource + prompt écrits par la story). Vérification en direct ci-dessous : aucun serveur public candidat n'expose les deux. **Recommandation : option B**, un serveur maison, sur le modèle déjà présent dans le dépôt (`mcp/architecture_server.py`).

## Vérification en direct (2026-10-27)

Requêtes JSON-RPC `initialize` puis `resources/list`/`prompts/list` envoyées en HTTP aux deux candidats que l'Open Question de SPEC.md citait comme annonçant les deux capacités :

| Serveur | `capabilities` à `initialize` | `resources/list` | `prompts/list` |
|---|---|---|---|
| `https://mcp.deepwiki.com/mcp` | `resources`, `prompts`, `tools` tous annoncés | `{"resources": []}` | `{"prompts": []}` |
| `https://mcp.context7.com/mcp` | `resources`, `prompts`, `tools` tous annoncés | `{"resources": []}` | `{"prompts": []}` |

Confirme l'Open Question de SPEC.md : les deux annoncent les capacités mais renvoient des listes vides — inutilisables pour la démonstration (CAP-9 veut qu'on *utilise* une ressource et un prompt jusqu'à la réponse du modèle, pas seulement les lister). Aucun autre candidat public connu (modelcontextprotocol.io, Hugging Face) n'expose de prompt. Un serveur public conforme peut apparaître après cette date ; revérifier avant de coder si l'option A est choisie.

## Option A — serveur public, ressources seulement

- **Ce qui est montré à l'apprenant :** une ressource lue via `resources/read`, sans prompt (CAP-9 non atteint à la lettre : « au moins une ressource et un prompt »). Écarté par la vérification ci-dessus, sauf si Anaël accepte d'assouplir CAP-9 à « ressource seule » ou trouve un autre serveur public conforme.
- **Code à écrire :** minime — ajouter l'entrée dans `mcp_servers()` (`mcp/servers.py:42-52`) et son texte (`content/mcp.yaml`), rien côté `mcp/lab.py` (déjà générique).
- **Risques :** dépôt public → aucune clé requise idéalement (serveurs anonymes ok) ; disponibilité hors du contrôle du projet (serveur tiers qui change ou tombe) ; pas de garantie qu'il reste conforme CAP-9 dans le temps.
- **Vérification :** `resources/list` en direct (fait ci-dessus, aucun prompt) ; test sur faux serveur impossible à distinguer d'un test sur le vrai serveur pour la partie liste (déjà couvert par `mcp/lab.py`).

## Option B — petit serveur maison, Streamable HTTP local (recommandé)

- **Ce qui est montré à l'apprenant :** une ressource (ex. un extrait de documentation du projet) lue via `resources/read`, et un prompt (ex. un gabarit de question) rempli via `prompts/get`, dont le résultat part au modèle — les deux jusqu'à la réponse, comme demandé.
- **Code à écrire :** un module `mcp/<nom>_server.py` sur le modèle de `mcp/architecture_server.py` (déjà dans le dépôt, déjà testé) :
  - `MCPServer` du SDK `mcp` déjà utilisé (`from mcp.server.mcpserver import MCPServer`, confirmé présent dans l'environnement — aucune nouvelle dépendance) ;
  - un `@server.resource(...)` et un `@server.prompt(...)` (décorateurs déjà exposés par `MCPServer`, confirmé par introspection : `resource`, `prompt`, `add_resource`, `add_prompt`) ;
  - montage Streamable HTTP sur un chemin dédié (`/mcp/<nom>`), 127.0.0.1 only, même garde qu'`architecture_server.py` (Origin, DNS-rebinding, pas de jeton si le contenu est public et sans risque) ;
  - entrée dans `mcp_servers()` avec une URL locale (`http://127.0.0.1:<port>/mcp/<nom>`).
- **Risques :**
  - Hors ligne : respecté, serveur local, pas d'appel réseau externe.
  - Dépôt public : le contenu de la ressource et du prompt doit être public et inoffensif (pas de secret, pas de donnée interne) ; aucune clé à commiter puisque local et sans authentification.
  - Pas de nouvelle dépendance : confirmé, le SDK `mcp` est déjà utilisé par `architecture_server.py`.
  - Risque principal : dupliquer la plomberie HTTP d'`architecture_server.py` au lieu de la réutiliser — à éviter (voir Code Map).
- **Vérification :** `resources/list` et `prompts/list` doivent renvoyer une entrée chacun une fois le serveur démarré ; test sur faux serveur (le serveur maison lui-même, lancé en mémoire dans le test, comme le fait probablement déjà `tests/test_architecture_server.py` ou équivalent — à vérifier par `git grep -l architecture_server tests`) ; vérification manuelle décrite dans les tâches ci-dessous, à faire par Anaël une fois le code en place (connexion depuis l'Atelier MCP, lecture de la ressource, exécution du prompt jusqu'à la réponse du modèle).

## Branchement sur la story 16.3 (schéma Avant/Avec)

La story 3 (en cours) dérive `BEFORE` (`mcp/lab.py:85`, aujourd'hui `("local", "datagouv", "mslearn")`), `BEFORE_SHAPES` (`mcp.js:1377`) et `before.integrations` (`content/mcp_lab.yaml`) de la liste des serveurs, pour qu'un serveur ajouté y entre seul. Cette story n'a donc **rien à faire** sur le schéma : ajouter le nouveau serveur à `mcp_servers()` suffit, à condition que la story 3 soit fusionnée en premier (ordre déjà fixé par `stories.yaml` : story 6 après story 3). Si la story 3 n'est pas encore fusionnée au moment du code, vérifier que `BEFORE`/`BEFORE_SHAPES` ne cassent pas avec un 4ᵉ serveur réseau (ajout manuel temporaire sinon).

## Boundaries & Constraints

**Always:**
- Aucune ressource ni prompt ne doit demander de clé ou de jeton secret (contrainte SPEC.md : pas de clé commitée). Un serveur local public sans authentification respecte ça par construction.
- Logo/texte du nouveau serveur en français, surcouches en/de sous `content/i18n/{en,de}/` (même story, constraint SPEC.md).
- Garde d'accès identique à `architecture_server.py` : Origin, DNS-rebinding, 127.0.0.1 only.

**Never:**
- Pas de nouvelle dépendance Python/JS sans accord d'Anaël (le SDK `mcp` est déjà une dépendance : rien à ajouter a priori).
- Ne pas dupliquer le code HTTP d'`architecture_server.py` : factoriser ce qui est commun (garde, montage) si raisonnable, sans sur-ingénierie pour un seul second serveur.
- Ne pas toucher au schéma Avant/Avec au-delà de l'ajout dans `mcp_servers()` (périmètre de la story 3).

## Tests à créer

- Test sur faux serveur (le serveur maison démarré en mémoire dans le test, comme pour `architecture_server.py`) : `resources/list` renvoie une entrée, `resources/read` renvoie le contenu attendu ; `prompts/list` renvoie une entrée, `prompts/get` renvoie le gabarit attendu avec ses arguments remplis.
- Test de bout en bout (E2E, nommé `mcp_resource_and_prompt_reach_model`) : dans l'Atelier MCP, connexion au nouveau serveur, lecture de la ressource, exécution du prompt, réponse du modèle visible dans Séquence.
- Vérification manuelle par Anaël sur le serveur réel une fois lancé (CAP-9 : « vérification manuelle sur le vrai »).

## Questions pour Anaël

1. **Option A vs B.** Recommandation : B (serveur maison), la vérification en direct du 27/10 écarte A pour le prompt. À confirmer avant le code.
2. **Contenu de la ressource et du prompt.** Pour rester pédagogique et sans risque (dépôt public), recommandation : une ressource qui donne un court extrait de documentation du projet (par ex. un glossaire ou un résumé de brique), et un prompt qui formule une question sur ce contenu. À valider : contenu exact et nom du serveur affiché.
3. **Port et nommage du nouveau serveur.** `architecture_server.py` tourne sur son propre port/chemin (`/mcp/architecture`) ; le nouveau prendrait un chemin voisin (`/mcp/<nom>`, à choisir) sur le même processus. À confirmer que ça ne crée pas de conflit avec un futur ajout.

</frozen-after-approval>

## Code Map

- `src/wavestack/mcp/architecture_server.py` — modèle à suivre (garde Origin/DNS-rebinding/127.0.0.1, montage Streamable HTTP, `MCPServer` du SDK).
- `src/wavestack/mcp/servers.py:42-52` (`mcp_servers`) — nouvelle entrée `McpServer` avec l'URL locale.
- `src/wavestack/mcp/lab.py:64-65,298-299,582-583` — déjà générique pour `resources/list`/`prompts/list`, rien à changer ici.
- `src/wavestack/mcp/lab.py:85` (`BEFORE`), `src/wavestack/web/static/mcp.js:1377` (`BEFORE_SHAPES`) — doivent déjà être dérivés par la story 3 ; vérifier l'ordre de fusion.
- `content/mcp.yaml` — textes du nouveau serveur (label, description), surcouches en/de.
- Tests : fichier qui couvre `architecture_server.py` (à repérer par `git grep -l architecture_server tests`), à dupliquer en plus léger pour le nouveau serveur.

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_mcp_lab.py` (+ le nouveau fichier de test du serveur)
- `uv run python .claude/cost-kit/controle_rapide.py`

## Décision d'Anaël (2026-10-27)

Pas de second serveur maison : l'application en a déjà un qui expose des prompts et des ressources. La story est **annulée**, faute de serveur public en ligne qui expose réellement une ressource et un prompt (vérifié le 27/10 : DeepWiki et Context7 renvoient des listes vides ; Hugging Face et modelcontextprotocol.io n'ont que des ressources). À rouvrir si un tel serveur apparaît.
