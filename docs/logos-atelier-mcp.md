# Logos des serveurs de l'Atelier MCP (CAP-8)

[← Retour au README](../README.md)

`src/wavestack/web/static/logos/mcp/` : un logo par serveur de l'Atelier MCP
(`wavestack.mcp.servers.McpServer.logo`), servi en local, jamais chargé depuis le réseau.
Un fichier absent ou un serveur sans logo dédié reçoit le pictogramme neutre `_default.svg`.

## GitHub

Le logo GitHub (Invertocat noir ou blanc, non modifié) provient de l'archive officielle
brand.github.com/GitHub_Logos.zip. Il est affiché pour signaler l'intégration avec le serveur
MCP GitHub, comme le permettent les règles de marque de GitHub
(https://brand.github.com/foundations/logo). GitHub est une marque de GitHub, Inc. et
n'approuve pas WaveStack.

Fichiers : `github.svg` (`GitHub_Invertocat_Black.svg`, thème clair) et `github-white.svg`
(`GitHub_Invertocat_White.svg`, thème sombre), copiés tels quels de l'archive, jamais
recolorés en CSS.

## Microsoft Learn

Les logos Microsoft exigent une licence
(https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks). L'Atelier affiche donc
un pictogramme neutre et le nom "Microsoft Learn" en texte seulement. Microsoft Learn est une
marque de Microsoft Corporation.

## data.gouv.fr

Le logo data.gouv.fr relève de la Marque d'État et aucune règle publique ne l'ouvre aux tiers
(https://www.data.gouv.fr/pages/legal/charter). L'Atelier affiche un pictogramme neutre et le
nom en texte jusqu'à une autorisation écrite d'Etalab ou de la DINUM.

## Ajouter un serveur

Ajouter son id à `wavestack.mcp.servers.ALL_IDS` (et son URL dans `mcp_servers()`) le fait
apparaître dans le sélecteur et dans le schéma « Avant MCP », qui grandit seul. Il faut aussi
ses lignes `before.integrations` et `servers` dans `content/mcp_lab.yaml` et ses traductions :
sans elles, la validation du contenu échoue au démarrage (erreur explicite). Sa forme dans le
schéma vient de `BEFORE_SHAPES` dans `mcp.js` (rond par défaut). Pour son logo, déposer
`logos/mcp/<id>.svg` et l'ajouter à `_LOGOS` dans `servers.py`, après vérification des règles
de la marque.
