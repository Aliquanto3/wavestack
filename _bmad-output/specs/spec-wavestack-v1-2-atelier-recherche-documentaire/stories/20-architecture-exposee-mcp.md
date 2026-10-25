---
title: 'Story 20 : architecture composée exposée en serveur MCP (optionnel)'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/architectures.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/vues.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/brownfield.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/attaques-et-conformite.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le formateur compose une architecture dans l'atelier (dense, hybride, reranking…), mais seul le participant, dans la page, peut l'interroger. CAP-18 demande qu'il puisse l'exposer comme serveur MCP, pour la brancher dans un client (Claude Code, Copilot Studio) et montrer ce qu'est un outil de recherche documentaire vu de l'extérieur. Aujourd'hui l'application est seulement **cliente** MCP (`mcp/connection.py`, `mcp/lab.py`) ; son seul serveur, `mcp/local_server.py`, est un glossaire en stdio, lancé par la session pour son propre modèle.

**Approach:** Un serveur MCP **en lecture seule**, démarré et arrêté depuis la page de l'atelier, qui expose la chaîne composée **figée au démarrage** :
1. un outil `search_documents(question, top_k)` qui exécute le segment de recherche de la chaîne sur le corpus fictif Exemplia et renvoie des passages **cités** (document, titre, position, extrait, score) ; il ne génère rien, c'est le modèle du client qui rédige ;
2. un outil `describe_architecture()` qui dit quelle architecture est exposée, ses étapes, et ses limites (corpus fictif, lecture seule) ;
3. une carte « Exposer en MCP » (démarrer, arrêter, adresse, jeton, commande de branchement, outils avec leur niveau de risque) ;
4. un **client MCP de test** (SDK `mcp` déjà épinglé) qui liste l'outil et reçoit des passages cités, en CI, sans réseau ni modèle réel.

Aucune dépendance nouvelle (`mcp>=2.2,<2.3` et `mcp-types` sont déjà dans `pyproject.toml`). Le contenu est servi par la session (AD-1) ; la page dessine.

## Boundaries & Constraints

**Always:**
- **Transport : streamable HTTP, sur le port existant de l'application, 127.0.0.1 seulement** (point ouvert 1). Le serveur est une sous-application ASGI montée sur `/mcp/architecture` ; aucun port nouveau, aucune entrée de `[net.loopback_ports]`, aucun processus fils. Arrêté, la route répond 404.
- **Accès.** Jeton porteur aléatoire (`secrets.token_urlsafe`) créé à chaque démarrage, comparé en temps constant, jamais écrit sur disque ni dans le Journal ; contrôle de `Host` (loopback) et d'`Origin` (absente ou loopback) contre la reliaison DNS. Un appel sans jeton valide reçoit 401 sans toucher à la session.
- **Chaîne figée au démarrage** (point ouvert 3) : la chaîne de la page est validée (`lab.check_pipeline`) puis copiée ; modifier la page ensuite ne change pas ce que le client voit. La carte affiche la chaîne exposée et dit qu'il faut arrêter puis démarrer pour la changer.
- **Architectures exposables** : celles dont la chaîne a un segment de recherche (`lab.RETRIEVAL`) et **aucune étape de génération, de décision ou d'appel cloud** (règle calculée sur la chaîne, pas une liste écrite en dur). `long_context` et `cag` (le corpus entier est le contexte), `agentic` (c'est l'orchestrateur du client qui joue la boucle) et `crag` (décision par modèle) sont refusés avec leur raison ; une architecture ajoutée plus tard se classe d'elle-même.
- **Confinement.** Corpus fictif Exemplia livré seulement (`corpus.load_rag_content`, le document piégé et la sentinelle restent inactifs, comme dans `rag/access.py`), profil d'accès `all` imposé par le serveur (aucun paramètre de profil dans le schéma des outils : un client ne peut pas demander les passages `hr`), aucune écriture (ni fichier, ni index, ni cache, ni copie de travail), aucune construction d'index déclenchée par un appel (index absent : erreur claire, « construisez-le dans l'atelier »). Le serveur n'appelle aucun modèle cloud ; il ne charge qu'un embedding local, pour la durée de l'appel.
- **Outils en lecture seule.** `annotations` MCP `readOnlyHint=true`, `destructiveHint=false`, `openWorldHint=false` ; schéma d'entrée strict (`question` : texte de 1 à `lab.QUESTION_MAX` caractères ; `top_k` : entier de 1 à 10, 3 par défaut) ; un seul appel à la fois (verrou), délai maximal de 30 s, refus immédiat avec un texte (`isError`) quand la session est occupée par un tour ou un run de l'atelier (point ouvert 4).
- **Politique et risques réutilisés** (point ouvert 5) : les deux outils sont déclarés dans `mcp/policy._DEFAULTS` (`workshop__search_documents` et `workshop__describe_architecture`, `low`, `allow`) ; le niveau affiché sur la carte vient de `ToolPolicy.risk_of` et se dit avec les libellés `mcp.policy.risk.*` et la puce `status-chip`. Un outil dont la règle courante (`rule_of`) n'est pas `allow` n'est pas annoncé par `tools/list` (le serveur n'a personne à qui demander : `ask` vaut refus). La matrice de la page Sécurité (`MATRIX_ROWS`) n'est pas modifiée.
- **Journal de sécurité.** Chaque appel écrit une entrée (outil, client annoncé à `initialize`, résultat, durée, nombre de passages), via `mcp/security_log.py`, **sans le texte de la question ni des passages**.
- **Cohabitation** (point ouvert 7) : le serveur exposé n'entre ni dans `mcp_servers()`, ni dans `_mcp_enabled`, ni dans les sous-options de la brique MCP, ni dans le catalogue de l'atelier MCP (`mcp/lab.py`) ; l'application ne peut pas se connecter à elle-même (les URL de `[mcp.urls]` sont fixes, test). `mcp/local_server.py` n'est pas modifié.
- **Cycle de vie.** Démarrage et arrêt par intentions de la session (`rag_mcp_start`, `rag_mcp_stop`) ; arrêt aussi à la fermeture de la session ; le démarrage est refusé avec sa raison si la chaîne n'est pas exposable, si l'index n'est pas construit ou si le corpus de l'atelier n'est pas celui du dépôt. Les descriptions des outils sont dans la langue de la session **au démarrage** ; un changement de langue arrête le serveur (la carte le dit).
- **Textes** dans `content/rag_mcp.yaml` et surcouches `content/i18n/{en,de}/rag_mcp.yaml` (descriptions d'outils vues par le modèle du client, textes de la carte, raisons de refus), résolus par `config.content_file` ; mêmes clés, mêmes bornes, seuls les textes diffèrent. Textes de session dans `content/messages.yaml` ×3 (ajouts, section `session.rag_mcp.*`).
- **Page.** Carte `rag-mcp-card` dans l'onglet Construire, code dans `rag-mcp.js` (module neuf, chargé par `rag.html`) ; tout texte par `textContent`, jetons CSS, contraste AA clair et sombre, état dit en mots (« exposée », « arrêtée »), jamais par la couleur seule ; le jeton est masqué par défaut, révélé et copié sur action.
- **Fichiers partagés en ajouts seulement** : `rag_lab.yaml` (non modifié), `ui.yaml`, `messages.yaml`, `run_e2e.py`, `rag.css` (bloc propre `/* V1.2 story 20 */`), `rag.html`, `app.py`, `app_session.py`.

**Never:** exposer une écriture, la génération, un modèle cloud, un outil de fichiers ou de shell, ou un document hors du corpus Exemplia livré ; écouter ailleurs que sur 127.0.0.1 ; ouvrir un tunnel ou une connexion sortante (Copilot Studio exige une adresse HTTPS publique : c'est une action du formateur, hors application) ; écrire le jeton ou une question dans un journal ou un fichier ; modifier `mcp/local_server.py`, `mcp/connection.py`, `MATRIX_ROWS`, `rag/lab.py`, `rag/access.py`, le corpus livré, `content/rag_lab.yaml` ; ajouter une dépendance ; charger torch.

## I/O & Edge-Case Matrix

| Cas | Entrée | Sortie |
|---|---|---|
| Démarrage | `rag_mcp_start` sur `hybrid`, index construit | serveur exposé, adresse `http://127.0.0.1:<port>/mcp/architecture`, jeton, chaîne figée, outils et niveaux |
| Architecture refusée | `cag`, `long_context`, `agentic`, `crag` | pas de démarrage ; raison dite (« le corpus entier est le contexte… ») |
| Index absent | chaîne valide, index non construit | pas de démarrage ; « construisez l'index dans l'atelier » |
| `tools/list` | client authentifié | `search_documents`, `describe_architecture` (schémas, annotations lecture seule) ; un outil de règle ≠ `allow` absent |
| `search_documents` | `{"question": "congés payés", "top_k": 3}` | 3 passages au plus : `rank`, `doc_id`, `title_text`, `position`, `text`, `score`, `citation` ; `structuredContent` et texte lisible ; aucun passage `hr` |
| Entrée hors bornes | `top_k: 50`, question vide ou > 500 caractères | erreur d'entrée MCP, aucun calcul |
| Session occupée | tour ou run de l'atelier en cours | `isError` « atelier occupé, réessayez » ; aucune attente |
| Sans jeton ou jeton faux | tout appel | 401 |
| `Host` ou `Origin` étranger | requête avec `Host: evil.example` | 403 |
| Serveur arrêté | tout appel | 404 |
| Changement de langue ou fermeture | session | serveur arrêté ; la carte revient à « arrêtée » |
| Deux démarrages | second `rag_mcp_start` | sans effet, même état renvoyé |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/exposed.py` (nouveau) : `exposable(pipeline, catalog, lang)` (règle sur les étapes, raison dite), `ExposedChain` (chaîne figée, libellé de l'architecture, étapes), `search(chain, question, top_k, deps)` (segment de recherche seul, profil `all`, passages cités), modèles pydantic stricts `Passage`, `SearchResult` ; aucune écriture, aucune génération.
- `src/wavestack/mcp/architecture_server.py` (nouveau) : serveur `MCPServer("wavestack-atelier-rag")` fabriqué par `build_server(backend, texts, policy)` (outils, annotations, filtre par règle), sous-application ASGI avec garde (jeton, `Host`, `Origin`, 404 arrêté). Importable sans effet de bord (pas de `install` du garde réseau à l'import : le module tourne dans le processus de l'application).
- `src/wavestack/mcp/policy.py` : deux lignes dans `_DEFAULTS` (ajout seul).
- `src/wavestack/session/app_session.py` (fin de la section RAG, `# V1.2 story 20`) : `rag_mcp_state`, `rag_mcp_start`, `rag_mcp_stop`, appel du serveur vers `exposed.search` sur le worker de la session, entrées du Journal de sécurité, arrêt dans `close()` et au changement de langue.
- `src/wavestack/web/app.py` (`# V1.2 story 20`) : `GET /api/rag_lab/mcp`, intentions `rag_mcp_start` et `rag_mcp_stop`, montage de la sous-application.
- `src/wavestack/web/static/rag-mcp.js` (nouveau), `rag.html` (carte et `<script>`), `rag.css` (bloc propre).
- `content/rag_mcp.yaml` et `content/i18n/{en,de}/rag_mcp.yaml` (nouveaux), `content/messages.yaml` ×3 (ajouts).
- `tests/test_rag_mcp.py` (nouveau), `tests/mcp_client.py` ou fonction dans le test (client de test), `tools/e2e/run_e2e.py` (scénario `rag_lab_mcp` ajouté), `tools/e2e/README.md`.

## Tasks & Acceptance

- [ ] `rag/exposed.py` : règle d'exposition, chaîne figée, recherche citée.
- [ ] `mcp/architecture_server.py` : outils, annotations, garde d'accès, filtre par règle.
- [ ] Session, points d'accès, intentions, Journal de sécurité, arrêt.
- [ ] Carte `rag-mcp-card` (`rag-mcp.js`, `rag.html`, `rag.css`), textes ×3.
- [ ] Tests (pytest avec client MCP, E2E), README E2E.

**Acceptance Criteria:**
1. Given l'application démarrée, when le formateur démarre l'exposition de la chaîne `hybrid` index construit, then un client MCP du SDK (`mcp.Client` sur `streamable_http_client`) avec le jeton affiché se connecte, `tools/list` renvoie `search_documents` et `describe_architecture`, et `tools/call search_documents` renvoie au plus `top_k` passages, chacun avec `doc_id`, `title_text`, `position`, `text`, `score` et `citation` (CAP-18 : « liste l'outil de recherche et reçoit des passages cités »).
2. Given `search_documents`, then ses passages sont ceux du segment de recherche de la chaîne figée (mêmes `doc_id` et mêmes rangs que `LabRun` sur la même chaîne et la même question, test d'égalité sur la chaîne lexicale du test), sans génération ni appel cloud.
3. Given la chaîne modifiée dans la page après le démarrage, then `describe_architecture` et les résultats suivent encore la chaîne figée ; après arrêt puis démarrage, ils suivent la nouvelle.
4. Given `cag`, `long_context`, `agentic` ou `crag`, then le démarrage est refusé avec une raison dite ; une architecture ajoutée plus tard à `PRESETS` est classée par la règle sur ses étapes (test sur une chaîne forgée avec une étape de génération : refusée).
5. Given le profil `all` imposé, then aucune question, aussi ciblée soit-elle (`q_global_rh`), ne renvoie un passage d'audience `hr` ; le schéma d'entrée n'a pas de paramètre de profil ni de corpus ; le document piégé et la sentinelle ne sont jamais renvoyés (test).
6. Given un appel, then rien n'est écrit : le dossier de données de la session est identique avant et après (comparaison de l'arbre) ; aucun index n'est construit (index absent : erreur, pas de construction).
7. Given les entrées hors bornes (`top_k` 0, 11, 50 ; question vide, 501 caractères), then le serveur répond par une erreur d'entrée et ne lance aucun calcul (compteur du dispositif de test).
8. Given une requête sans jeton, avec un jeton faux, ou avec `Host` ou `Origin` étranger, then 401 ou 403 ; arrêté, 404 ; le jeton change à chaque démarrage et n'apparaît ni dans le Journal, ni dans `logs`, ni dans un fichier (test qui lit le journal et le dossier de données).
9. Given `mcp.policy`, then les deux outils ont les entrées `low`/`allow`, la carte affiche leur niveau via `risk_of` et les libellés `mcp.policy.risk.*` ; avec la règle d'un outil passée à `deny` ou `ask` (`set_rule`), `tools/list` ne l'annonce plus ; `MATRIX_ROWS` et `/api/security` sont inchangés (tests de la page Sécurité verts, inchangés).
10. Given un appel, then le Journal de sécurité reçoit une entrée (outil, client annoncé, résultat, durée, nombre de passages) sans texte de question ni de passage (test).
11. Given l'atelier occupé (tour ou run en cours), then l'appel renvoie `isError` immédiatement ; deux appels simultanés sont sérialisés sans blocage de la session ; un appel dépassant 30 s se termine par une erreur (délai injecté dans le test).
12. Given la brique MCP et l'atelier MCP, then `mcp_servers()`, les sous-options de la brique et le catalogue de `/mcp` sont identiques avant et après l'exposition ; `[mcp.urls]` ne contient pas l'adresse exposée ; `mcp/local_server.py` est inchangé (`git diff --stat`).
13. Given `content/rag_mcp.yaml` ×3, then mêmes clés, mêmes bornes et mêmes placeholders en fr, en et de, sans repli silencieux sur le français ; les descriptions d'outils sont dans la langue du démarrage ; un changement de langue arrête le serveur.
14. Given la carte, then elle montre l'état en mots, l'adresse, le jeton masqué puis révélable et copiable, la chaîne exposée, les outils avec leur niveau en mot dans une `status-chip`, une commande de branchement (`claude mcp add --transport http … --header "Authorization: Bearer …"`) et la mention que Copilot Studio exige une adresse publique que l'application ne fournit pas ; clair et sombre au contraste AA ; textes par `textContent`.
15. Given la suite complète et l'E2E, then les stories 17 à 19 et leurs scénarios restent verts et inchangés ; `test_no_average_in_the_other_tabs_of_the_page` passe avec `rag-mcp.js` (aucun agrégat) ; aucune requête hors `127.0.0.1`.
16. Given la CI trois OS, then les tests de la story ne demandent ni réseau, ni modèle réel, ni port fixe (client sur transport ASGI en mémoire ou port 0 ; embedder remplacé par un double déterministe à la frontière du modèle) ; tout test qui dépend d'une dépendance optionnelle porte un marqueur de saut.

## Verification

- `uv run pytest -q --tb=short tests/test_rag_mcp.py tests/test_mcp.py tests/test_mcp_policy.py tests/test_mcp_lab.py tests/test_rag_lab.py tests/test_rag_evaluation.py tests/test_i18n.py tests/test_annex_language.py` -- vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag_lab_mcp,rag_lab_views` -- vert, tranche courte.

## Plan de tests

- **pytest, `tests/test_rag_mcp.py`**, sans réseau ni modèle réel :
  - règle d'exposition (critère 4) : `PRESETS` réels et chaîne forgée ; raisons dites ×3 langues ;
  - client MCP de test (critères 1, 2, 5, 7) : `mcp.Client` sur `streamable_http_client(url, http_client=httpx2.AsyncClient(transport=ASGITransport(app)))` (précédent : le paramètre `http_client` utilisé dans `mcp/lab.py`), chaîne lexicale sur le corpus livré ; si une chaîne sans embedding n'est pas valide, embedder déterministe en double (frontière du modèle) ;
  - garde d'accès (critère 8) : sans jeton, jeton faux, `Host` et `Origin` étrangers, arrêté ;
  - politique et Journal (critères 9, 10) : `set_rule`, entrées sans texte ;
  - confinement (critère 6) : arbre du dossier de données avant et après ;
  - concurrence et délai (critère 11) ;
  - cohabitation (critère 12) ;
  - parité des langues et arrêt au changement de langue (critère 13) ;
  - points d'accès et intentions par le client de test de `web/app.py` (ouvrir, fermer, double démarrage).
- **pytest existants à relancer** : `test_mcp.py`, `test_mcp_policy.py`, `test_mcp_lab.py`, `test_mcp_lab_policy.py`, `test_rag_lab.py`, `test_rag_evaluation.py` (`OTHER_TABS`), `test_i18n.py`, `test_annex_language.py`.
- **E2E `rag_lab_mcp`** (index construit par le scénario `rag`) : ouvrir Construire, voir la carte « arrêtée », démarrer sur `hybrid`, lire l'adresse, révéler le jeton, appeler l'adresse en JSON-RPC brut (`urllib`, `initialize`, `tools/list`, `tools/call`, réponse JSON ou SSE) et vérifier des passages cités, vérifier le 401 sans jeton, choisir `cag` et voir le démarrage refusé avec sa raison, arrêter et voir le 404, repasser en en puis de ; aucune requête hors `127.0.0.1`. Capture clair et sombre.

## Points ouverts

À trancher au point de contrôle de spec (relecteur) ; chacun porte la proposition retenue ci-dessus.

1. **Transport.** Options : stdio (processus lancé par le client, branchable dans Claude Desktop), streamable HTTP local, ou les deux. *Proposition : streamable HTTP seul, monté sur le port de l'application.* Raisons : le démarrage et l'arrêt depuis la page n'ont de sens qu'avec un serveur que l'application tient (le stdio est lancé par le client, hors de la page) ; un processus fils doublerait la mémoire (modèle d'embedding rechargé, budget 4 Go) ; Claude Code et Copilot Studio parlent HTTP. Le stdio est reporté. *Risque à vérifier par le dev avant de coder :* le gestionnaire de session de `MCPServer.streamable_http_app()` demande un cycle de vie ; s'il ne se monte pas proprement dans l'application existante, repli : `uvicorn.Server` dans un fil, sur `127.0.0.1` et un port éphémère affiché par la carte (aucun changement de `[net.loopback_ports]`, le serveur écoute seulement).
2. **Outils et schémas.** *Proposition : `search_documents(question, top_k)` et `describe_architecture()`, rien d'autre* (pas de `answer` : la génération resterait locale, lente et sans valeur pour un client qui a son propre modèle ; pas de `read_file` : c'est la recherche agentique de la story 11). Sortie : `structuredContent` (liste de passages avec `citation`) et texte lisible équivalent. Une ressource `corpus://exemplia` (liste des documents) est écartée : elle contournerait le profil d'accès.
3. **Chaîne figée ou en direct.** *Proposition : figée au démarrage*, affichée sur la carte. En direct, un client verrait changer ses résultats pendant que le participant édite, et une chaîne en cours d'édition peut être invalide.
4. **Concurrence avec l'atelier.** Le serveur s'exécute sur le worker de la session (modèles prêtés par `LoadRegistry`, un seul modèle génératif à la fois). *Proposition : refus immédiat avec « atelier occupé » plutôt qu'une file d'attente* ; aucun modèle génératif n'est chargé par le serveur.
5. **Politique et matrice des risques.** `ToolPolicy` s'applique d'ordinaire aux outils que le modèle de l'application appelle ; ici l'application est le serveur. *Proposition : réutiliser le vocabulaire (`RISKS`, `RULES`) et `_DEFAULTS` pour déclarer les deux outils et filtrer `tools/list` sur la règle, sans nouvelle ligne de `MATRIX_ROWS`* (la page Sécurité, ses tests et `/api/security` restent inchangés). Alternative plus riche, écartée ici : une ligne « exposé » dans la matrice.
6. **Confinement.** *Proposition : corpus Exemplia livré, profil `all` imposé, document piégé et sentinelle inactifs, aucune écriture, aucun cloud, pas de construction d'index à l'appel.* Un client ne peut donc ni lire les passages RH ni déclencher le piège. Les copies de travail de l'atelier (ajout, modification, suppression de documents) ne sont pas exposées.
7. **Cohabitation avec les serveurs MCP gérés.** *Proposition : rôle distinct (serveur contre client).* Le serveur exposé n'est ni un `McpServer` de `mcp_servers()`, ni une sous-option de la brique, ni listé par l'atelier MCP ; son nom d'outil est préfixé `workshop__` dans la politique.
8. **Démarrage depuis la page.** *Proposition : carte dans l'onglet Construire* (c'est là que la chaîne se compose), module `rag-mcp.js` neuf. Alternative : un onglet dédié, écarté (cinq onglets suffisent, `rag.js` partagé).
9. **Client de test en CI.** *Proposition : SDK `mcp.Client` sur transport ASGI en mémoire, chaîne lexicale, embedder déterministe en double à la frontière du modèle si la chaîne lexicale seule n'est pas valide* (à vérifier par le dev dans `check_pipeline`). Aucun port fixe, aucun réseau, aucun modèle.
10. **Jeton.** *Proposition : jeton porteur par démarrage, affiché sur la carte, jamais écrit.* Sans jeton, n'importe quelle page web ouverte dans le navigateur du formateur pourrait appeler `127.0.0.1` ; le contrôle d'`Origin` seul ne protège pas un client hors navigateur.
11. **Textes.** *Proposition : `content/rag_mcp.yaml` ×3* pour les descriptions d'outils (vues par le modèle du client, donc dans la langue du démarrage), la carte et les raisons ; `messages.yaml` ×3 pour les messages de session ; `ui.yaml` n'est pas touché.
12. **Architectures exposables.** *Proposition : règle calculée sur les étapes* (segment de recherche, ni génération, ni décision, ni cloud) plutôt qu'une liste. Les architectures sans index et l'agentique sont refusées avec leur raison ; `pageindex`, `raptor`, `graphrag`, `llm_wiki` deviendront exposables si leur story livre un segment de recherche conforme, sans changer cette story.

## Spec Change Log

- 2026-10-25 : création (phase 1, point de contrôle de spec).

## Reports

- Tâche humaine (Anaël), avant de déclarer la story finie (`done_checkpoint`) : brancher un vrai client (Claude Code : `claude mcp add --transport http …`) sur la carte, vérifier que les passages sont cités et qu'aucun passage RH ne sort ; relire les descriptions d'outils en fr, en et de.
- Ressource d'Anaël : un client réel (Claude Code) pour la recette ; Copilot Studio demande une adresse HTTPS publique (tunnel ou hébergement) : non fourni par l'application, non testé en CI.
- Reportés : transport stdio (processus lancé par le client) ; ligne « exposé » dans la matrice des risques de la page Sécurité ; exposition de `pageindex`, `raptor`, `graphrag`, `llm_wiki` et `agentic` (dépend des stories 11 à 14) ; ressource `corpus://` ; limitation de débit par client.
