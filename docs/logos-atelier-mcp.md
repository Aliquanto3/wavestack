# Logos des serveurs de l'Atelier MCP (story 16.3, CAP-8)

[← Retour au README](../README.md)

`src/wavestack/web/static/logos/mcp/{local,datagouv,mslearn,github,_default}.svg` : un
pictogramme par serveur de l'Atelier MCP (`wavestack.mcp.servers.McpServer.logo`), chargé en
local, jamais depuis le réseau (contrainte de la spec du 27/10).

## Décision : des pictogrammes neutres, pas les marques des éditeurs

Trois des quatre serveurs touchent à une marque déposée (GitHub, Microsoft Learn) ou à une
identité réservée (la Marianne, propre à l'État français, pour data.gouv.fr). Cette story n'a
pas eu d'accès réseau pour vérifier en direct les conditions d'usage actuelles de ces marques
(brand guidelines GitHub et Microsoft, charte graphique data.gouv.fr) : par précaution, les
quatre logos sont des pictogrammes dessinés pour l'occasion, qui ne reproduisent aucune marque
déposée ni la Marianne :

- `local.svg` : un livre ouvert (le glossaire local).
- `datagouv.svg` : un cylindre de données (jamais la Marianne, réservée à l'État).
- `mslearn.svg` : un chapeau de diplômé sur un document (la documentation), jamais le logo
  Microsoft (quatre carrés) ni le nom stylisé.
- `github.svg` : des chevrons de code `</>`, jamais l'Octocat ni le wordmark GitHub.
- `_default.svg` : repli neutre pour un serveur sans pictogramme dédié (story 16.6).

Un repère existe déjà dans ce dépôt pour l'usage nominatif de marques d'éditeurs de modèles
(`src/wavestack/web/static/logos/SOURCES.md`, « marque déposée - usage éditorial nominatif »),
mais il s'appuie sur une banque de visuels validée en amont pour ces éditeurs précis ; il ne
couvre pas GitHub, Microsoft Learn ni data.gouv.fr. **À vérifier avant toute diffusion externe
ou tout remplacement par le logo réel d'un éditeur** : les conditions d'usage à jour de chaque
marque, auprès d'Anaël ou d'un juriste.

## Contrat pour un nouveau serveur (story 16.6)

Ajouter un serveur à `wavestack.mcp.servers.ALL_IDS` suffit à le faire apparaître dans le
sélecteur de l'Atelier MCP et dans le schéma « Avant MCP » (qui grandit seul). Pour son logo :

- rien à faire : il reçoit `_default.svg` ;
- ou déposer un fichier `logos/mcp/<id>.svg` (même précaution ci-dessus si la marque du
  nouveau serveur est déposée) et l'ajouter à `_LOGOS` dans `servers.py`.

Pour sa forme dans le schéma « Avant MCP », ajouter son id à `BEFORE_SHAPES` dans `mcp.js`
(sinon il reçoit la forme ronde par défaut, qui peut doubler celle d'un autre serveur) et sa
ligne à `before.integrations` dans `content/mcp_lab.yaml` (et ses traductions) : sans cette
ligne, le serveur casse la validation du contenu au démarrage (erreur explicite).
