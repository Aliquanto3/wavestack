# Run autonome de nuit : V1.3, V1.4 puis V1.2

Lancé le 2026-10-24 à la demande d'Anaël, après le run SLM A/B (archivé dans [run-autonome-slm-2026-10-24.md](run-autonome-slm-2026-10-24.md)). Orchestration : session principale Opus 5.5.

## Périmètre

| Périmètre | Epics | Note |
|---|---|---|
| Dans le run | Epics 12 à 14 | epic 13 = V1.3, 14 = V1.4, 12 = V1.2 ; priorité stricte 13, 14, 12 ; story 12.1 = PR #79 |
| Hors run | V2, SLM C | spec V2 en brouillon ; SLM C en attente du benchmark |

Specs : `_bmad-output/specs/spec-wavestack-cache-visible/` (V1.3), `spec-wavestack-etat-de-l-art-harnais/` (V1.4), `spec-wavestack-v1-2-atelier-recherche-documentaire/` (V1.2).

Au plus 2 stories en développement à la fois

## Sprint 1 — V1.3 cache visible

| Vague | Stories en parallèle | Après |
|---|---|---|
| V0 | 13.1 ★ | — |
| V1 | 13.2 · 13.5 | 13.2 ← 13.1 ; 13.5 ← 13.1 |
| V2 | 13.3 · 13.4 | 13.3 ← 13.2 ; 13.4 ← 13.1 |
| V3 | 13.6 | 13.6 ← 13.2 ; 13.6 ← 13.3 ; 13.6 ← 13.4 |

## Sprint 2 — V1.4 état de l'art des harnais

| Vague | Stories en parallèle | Après |
|---|---|---|
| V4 | 14.1 · 14.3 | 14.3 ← 12.1 (PR #79) |
| V5 | 14.2 | 14.2 ← 14.1 |
| V6 | 14.4 ★ | 14.4 ← 14.2 ; 14.4 ← 13.3 |

## Sprint 3 — V1.2 atelier recherche documentaire

| Vague | Stories en parallèle | Après |
|---|---|---|
| V7 | 12.1 | PR #79 : rebase, CI, fusion (revue déjà faite) |
| V8 | 12.2 (humaine) · 12.3 | 12.3 ← 12.1 |
| V9 | 12.4 | 12.4 ← 12.3 (même page) |
| V10 | 12.5 · 12.9 | 12.5 ← 12.4 ; 12.9 ← 12.4 |
| V11 | 12.6 · 12.15 | 12.6 ← 12.5 ; 12.15 ← 12.9 |
| V12 | 12.7 · 12.17 | 12.7 ← 12.6 ; 12.17 ← 12.15 |
| V13 | 12.10 · 12.18 | 12.10 ← 12.7 ; 12.18 ← 12.17 |
| V14 | 12.11 · 12.19 | 12.11 ← 12.10 ; 12.19 ← 12.18 |
| V15 | 12.13 · 12.14 | 12.13 ← 12.11 ; 12.14 ← 12.11 |
| V16 | 12.16 | 12.16 ← 12.13 ; 12.16 ← 12.14 |
| V17 | 12.8 (humaine) · 12.20 | 12.8 ← 12.2 ; 12.20 ← 12.19 |
| V18 | 12.12 · 12.21 | 12.12 ← 12.8 ; 12.21 ← 12.16 |

Deux pistes en V1.2 (relevé des fichiers du 2026-10-25) : piste chaîne (`rag/lab.py`, focus de `rag.js`) 5, 6, 7, 10, 11, 13, 14, 16, 12 ; piste onglets (`rag.js` par onglet, `rag.css`, `rag.html`, `app.py`) 9, 15, 17, 18, 19. Les deux pistes partagent `rag_lab.yaml` ×3, `ui.yaml` et `run_e2e.py` en ajouts seulement : le reviewer fusionne `origin/main` et garde les deux côtés.

## Règles du run

- Par story : `dev-story` (Sonnet ; Opus pour 14.4), `second-avis` (Haiku), `reviewer` (Opus, avec la liste du second avis, rebasé sur `origin/main`), PR, CI verte, fusion, vérification `MERGED`, journal.
- Points de contrôle (décision d'Anaël du 2026-10-24) : `done_checkpoint` levés. `spec_checkpoint` : `dev-story` écrit la spec de story et s'arrête ; `reviewer` la relit contre SPEC.md, maquettes et brownfield.md, tranche les points ouverts ; `dev-story` reprend. Chaque choix fait à la place d'Anaël : ligne `décision · à revoir`.
- Local : contrôle rapide et tests ciblés seulement ; la CI de la PR (Windows, Ubuntu) sert de suite complète.
- `gh run watch <id> --interval 60` ; worktrees `../wavestack-<lot>-s<n>`, `git worktree prune` avant chaque lancement, suppression en fin de run.
- Ce fichier vit sur `chore/etat-run`, hors des PR de story.
- Arrêt seulement pour une ressource ou une décision d'Anaël (modèle réel, clé cloud, accès Jev, annotation, PC cible) : notification, `attente humaine`, on avance ailleurs.
- Fin de lot : PR de version (SemVer mineure suivante), tag annoté, release GitHub.

## Décisions

- 2026-10-24 : ordre V1.3, V1.4, V1.2 ; points de contrôle levés pour la nuit, revus au matin (Anaël).

## Reprise après /clear

- Lire ce fichier en entier, puis `sprint-status.yaml` ; l'état réel prime : `gh pr list --state open`, `git -C ../wavestack-<lot>-s<n> log -3 --oneline` pour chaque worktree d'une story en cours.
- Worktrees : `../wavestack-v13-s6` (13.6, PR #101), `../wavestack-v14-s4` (14.4, spec `stories/4-compaction.md` ready-for-dev puis code), `../wavestack-v12-s5` (12.5), `../wavestack-v12-s9` (12.9), `../wavestack-tests-sparse` (PR #100), `../agent-cost-kit-ci-run` (PR du kit 0.12.0, dépôt agent-cost-kit).
- Une story dont le dev a commité sans rapport : relancer la chaîne à partir de `second-avis` sur son dernier commit.
- Fusions par `scripts/file_prs.py` du kit (vérifie `MERGED`), puis journal.
- Fin de lot : PR de version (SemVer mineure), tag annoté, release GitHub ; V1.3 dès la fusion de 13.6, V1.4 dès celle de 14.4.
- Fin de run : `rapport-nuit-2026-10-25.md` (fusionné, bloqué, reporté, liste « à revoir », tests manuels du matin), mémoire du projet, suppression des worktrees.

## Après le run

- (Avancée dans le run le 2026-10-25, décision d'Anaël.) Story d'outillage : accélérer les tests lents propres à Windows de `tests/test_model_servers.py` et `tests/test_context_window_setting.py` (11 à 33 s chacun sous Windows, absents du haut de la liste sous Ubuntu ; piste : connexion à un port fermé qui met ~2 s à échouer sous Windows). Gain mesuré attendu : ~2 min 30 de tests Windows. Décision d'Anaël du 2026-10-25.
- Rafraîchir `test-durations-windows-latest.json` et `test-durations-ubuntu-latest.json` depuis les artefacts `test-durations-<os>-<groupe>` d'une CI récente (fusion des 4 fichiers par système), quand l'écart entre groupes dépasse ~2 min.

## Journal

- 2026-10-24 23:10 · run · décision · run de nuit V1.3, V1.4, V1.2 lancé ; PR #87 (spec V1.4) MERGED 8174efc · —
- 2026-10-24 23:10 · 12.1 · CI · PR #79 rebasée sur main, CI lancée · 13453c9
- 2026-10-24 23:11 · 12.1 · fusion · #79 MERGED · 72cfdf0
- 2026-10-24 23:11 · 13.1 · dev · lancé (phase spec) · 72cfdf0
- 2026-10-24 23:12 · 14.1 · dev · lancé (créneau libre pendant la V1.3-1) · 72cfdf0
- 2026-10-24 23:13 · 13.1 · dev · spec prête (phase 1) · dd32e23
- 2026-10-24 23:13 · 13.1 · review · relecture de la spec lancée · dd32e23
- 2026-10-24 23:15 · 13.1 · review · spec approuvée après 4 corrections importantes (lecture locale sans last_cache_reuse, collision cache_savings, règle d'écriture par pivot, tests listés) · 23e84c8
- 2026-10-24 23:15 · 13.1 · décision · à revoir : non caché local = None « sans objet », distingué par cache_origin · 23e84c8
- 2026-10-24 23:15 · 13.1 · décision · à revoir : champ cache_write_1h_tokens ajouté dès la story 1 (Anthropic ephemeral_1h) pour les stories 4 et 5 · 23e84c8
- 2026-10-24 23:15 · 13.1 · décision · à revoir : cache_origin None seulement pour une trace antérieure ; usage estimé = provider, cases None · 23e84c8
- 2026-10-24 23:15 · 13.1 · dev · phase 2 (code) lancée · 23e84c8
- 2026-10-24 23:17 · 14.1 · dev · fini ; E2E disciplines 52 OK (PYTHONUTF8=1 requis sous Windows) ; skills tiers dans hooks, échafaudage dans native_tools · f916b57
- 2026-10-24 23:17 · 14.1 · décision · à revoir : scénario de sécurité des skills tiers = hooks · f916b57
- 2026-10-24 23:17 · 14.1 · second-avis · lancé · f916b57
- 2026-10-24 23:18 · 14.3 · dev · lancé · 72cfdf0
- 2026-10-24 23:21 · 13.1 · dev · fini ; contrat : cache_origin, cache_read_tokens, cache_write_tokens, cache_write_1h_tokens, cache_uncached_tokens (int | None) · ab89fb3
- 2026-10-24 23:21 · 13.1 · second-avis · lancé · ab89fb3
- 2026-10-24 23:22 · 14.1 · second-avis · 1 medium (consigne d'échafaudage fausse : prompts de native_tools ne nomment pas l'outil), 5 low · f916b57
- 2026-10-24 23:22 · 14.1 · review · lancé (avec E2E compression et subagent) · f916b57
- 2026-10-24 23:24 · 13.1 · second-avis · 0 high/medium, 3 low ; orchestrateur : lecture OpenAI absente = None (CAP-1), traité comme important · ab89fb3
- 2026-10-24 23:24 · 13.1 · review · lancé · ab89fb3
- 2026-10-24 23:27 · 13.1 · review · 1 medium corrigé (lecture non déclarée = None, pivots Anthropic et Responses), contrat mis à jour · c03250c
- 2026-10-24 23:27 · 13.1 · décision · à revoir : réponse Anthropic sans champs de cache = rien déclaré (None) · c03250c
- 2026-10-24 23:27 · 13.1 · PR · ouverte, CI lancée · c03250c
- 2026-10-24 23:27 · 14.1 · review · 1 medium corrigé (échafaudage déplacé dans skills), E2E subagent 58/58, compression 43/43 · 1ccca2d
- 2026-10-24 23:27 · 14.1 · décision · à revoir : consigne d'échafaudage portée par le scénario skills · 1ccca2d
- 2026-10-24 23:27 · 14.1 · PR · ouverte, CI lancée · 1ccca2d
- 2026-10-24 23:27 · 13.5 · dev · lancé (phase spec, empilé sur 13.1) · c03250c
- 2026-10-24 23:30 · 13.5 · dev · spec prête (réglage [cloud] claude_cache, points system et outils, 1 h déclaré ou ×2) · 5440690
- 2026-10-24 23:30 · 13.5 · review · relecture de la spec lancée (seuil minimal du cache Anthropic) · 5440690
- 2026-10-24 23:31 · 14.3 · dev · fini ; documents inactifs exclus, search_documents décoché au lancement (default_enabled), E2E rag_agentic 20 OK · 73ecedf
- 2026-10-24 23:31 · 14.3 · décision · à revoir : search_documents décoché par défaut, le scénario le fait cocher · 73ecedf
- 2026-10-24 23:31 · 14.3 · second-avis · lancé · 73ecedf
- 2026-10-24 23:31 · 13.2 · dev · lancé (empilé sur 13.1) · c03250c
- 2026-10-24 23:34 · 14.3 · second-avis · 1 high (test casse-sensible rouge sous Ubuntu), 1 medium (languages ignoré, comme chunk_corpus), 6 low ; confinement sans défaut · 73ecedf
- 2026-10-24 23:34 · 14.3 · review · lancé · 73ecedf
- 2026-10-24 23:35 · 13.5 · review · spec approuvée ; préfixe stable mesuré ≈ 1 000 tokens, sous le seuil du fournisseur · e193a0f
- 2026-10-24 23:35 · 13.5 · décision · à revoir : 3e point de cache sur le dernier message (sinon rien n'est mis en cache) ; la story 6 doit faire dépasser le seuil · e193a0f
- 2026-10-24 23:35 · 13.5 · décision · à revoir : cache_control seulement pour le chat (_render_chat), pas les ateliers ni Tester ; clé via config.cloud_key · e193a0f
- 2026-10-24 23:35 · 13.5 · dev · phase 2 (code) lancée · e193a0f
- 2026-10-24 23:39 · 14.3 · review · high corrigé (casse CORPUS/ sous Linux), mots vides, notice masquée, E2E par id ; rag_agentic 20/20 · 2d30c34
- 2026-10-24 23:39 · 14.3 · décision · à revoir : search_documents garde la règle languages du RAG (même corpus pour la comparaison) · 2d30c34
- 2026-10-24 23:39 · 14.3 · PR · #91 ouverte, CI lancée · 2d30c34
- 2026-10-24 23:39 · 13.1 · CI · Ubuntu verte, Windows en cours (#89) · c03250c
- 2026-10-24 23:40 · 13.2 · dev · fini ; E2E local_server 50 OK ; faux llama-server garde le préfixe (lecture locale non nulle) · eae59ca
- 2026-10-24 23:40 · 13.2 · second-avis · lancé · eae59ca
- 2026-10-24 23:43 · 13.2 · second-avis · 3 medium (« non déclaré » en local, barre du haut à 1 280 px, non caché sans écriture), 5 low · eae59ca
- 2026-10-24 23:43 · 13.2 · review · lancé · eae59ca
- 2026-10-24 23:44 · 14.1 · CI · verte (Windows, Ubuntu) · 1ccca2d
- 2026-10-24 23:44 · 14.1 · fusion · #90 MERGED · d9f223e
- 2026-10-24 23:44 · 14.3 · CI · PR #91 rebasée sur main (avec 14.1), CI relancée · —
- 2026-10-24 23:44 · 14.2 · dev · lancé (phase spec) · d9f223e
- 2026-10-24 23:46 · 13.1 · CI · verte (Windows, Ubuntu) · c03250c
- 2026-10-24 23:46 · 13.1 · fusion · #89 MERGED (aucun fichier commun avec #90) · e15cc3e
- 2026-10-24 23:48 · 13.5 · dev · fini, rebasé sur main ; E2E claude_cache 29/29 (avant rebase) · e802bd0
- 2026-10-24 23:48 · 13.5 · second-avis · lancé · e802bd0
- 2026-10-24 23:48 · 14.2 · dev · spec prête · aca8e38
- 2026-10-24 23:48 · 14.2 · décision · libellés des 7 sous-systèmes vérifiés sur arXiv 2609.00006 (tableau 1) : Tools & actions, Safety & permissions corrigés · aca8e38
- 2026-10-24 23:48 · 14.2 · review · relecture de la spec lancée · aca8e38
- 2026-10-24 23:48 · 13.4 · dev · lancé (phase spec) · e15cc3e
- 2026-10-24 23:49 · 13.2 · review · 2 medium corrigés (« non mesuré » en local, barre à 1 280 et 1 366 px vérifiée), 2 écartés · 1b0fdb5
- 2026-10-24 23:49 · 13.2 · décision · à revoir : seuil de 1 700 px du texte court de la jauge (spec de story, absent de DESIGN.md) · 1b0fdb5
- 2026-10-24 23:49 · 13.2 · PR · rebasée sur main, ouverte, CI lancée · c81b6d5
- 2026-10-24 23:49 · 13.3 · dev · lancé (empilé sur 13.2) · c81b6d5
- 2026-10-24 23:50 · 13.4 · dev · spec prête (cases partielles, anneau SVG, registre _spend_conv) · e229269
- 2026-10-24 23:50 · 13.4 · review · relecture de la spec lancée · e229269
- 2026-10-24 23:51 · 13.5 · second-avis · 0 high/medium, 5 low (dont un mock de config.cloud_key) · e802bd0
- 2026-10-24 23:51 · 13.5 · review · lancé · e802bd0
- 2026-10-24 23:53 · 14.2 · review · spec approuvée après 2 high et 3 medium corrigés (libellés du papier, compte de scénarios, état des briques, grisé, légende) · a818d6b
- 2026-10-24 23:53 · 14.2 · décision · à revoir : sous-agent = 3e exception AD-9 (compression + subagent dépasse 3 584 tokens en CI) · a818d6b
- 2026-10-24 23:53 · 14.2 · décision · à revoir : harness_map a un prompt neutre (schéma min 1 prompt) ; carte servie par bricks_changed, sans route · a818d6b
- 2026-10-24 23:53 · 14.2 · dev · phase 2 (code) lancée · a818d6b
- 2026-10-24 23:54 · 13.4 · review · spec approuvée ; signal corrigé (écriture du 1er appel retirée), cost_ring, appels sans prix comptés · fb60884
- 2026-10-24 23:54 · 13.4 · décision · à revoir : signal = écriture hors 1er appel > lecture ; appels hors tour seulement dans « Depuis le lancement » · fb60884
- 2026-10-24 23:54 · 13.4 · report · phase 2 en attente d'un créneau (2 stories en développement) · fb60884
- 2026-10-24 23:56 · 13.3 · dev · fini ; E2E local_server 53 OK, cause cache_cleared · 95c0450
- 2026-10-24 23:56 · 13.3 · second-avis · lancé · 95c0450
- 2026-10-24 23:56 · 13.4 · dev · phase 2 (code) lancée · fb60884
- 2026-10-24 23:57 · 13.5 · review · 1 medium corrigé (dégrisage à la saisie de clé), mock remplacé ; E2E claude_cache et context_window 55 OK · 3a11e05
- 2026-10-24 23:57 · 13.5 · report · story 6 : dire que changer mémoire, skills ou prompt réécrit tout le cache · 3a11e05
- 2026-10-24 23:57 · 13.5 · PR · ouverte, CI lancée · 3a11e05
- 2026-10-25 00:00 · 13.3 · second-avis · 3 medium (course vidage/tour, vidage pendant préremplissage, slot 0 seul), 4 low · 95c0450
- 2026-10-25 00:00 · 13.3 · review · lancé · 95c0450
- 2026-10-25 00:00 · 14.3 · CI · rouge sur Ubuntu après rebase sur 14.1 ; 371 tests ciblés verts en local, journal attendu · 21515b7
- 2026-10-25 00:00 · 14.3 · CI · échec Ubuntu = test_engine_candidates (probabilités, hors diff, instable présumé) ; job relancé · 21515b7
- 2026-10-25 00:05 · 14.2 · dev · fini ; E2E harness_map, programme, subagent, disciplines verts ; écart : H3 non reconduit au module 7, test_program assoupli · 0daec7d
- 2026-10-25 00:05 · 14.2 · second-avis · lancé · 0daec7d
- 2026-10-25 00:05 · 12.2 · attente humaine · banc de modèles réels (candidats System One, Qwen3.5-2B 16 384 / 4 Go) : à lancer par Anaël, hors run parallèle · —
- 2026-10-25 00:05 · 12.3 · dev · lancé (créneau libre, V1.3 et V1.4 restantes bloquées par des fusions) · e15cc3e
- 2026-10-25 00:06 · 13.2 · CI · verte (Windows, Ubuntu) · c81b6d5
- 2026-10-25 00:06 · 13.2 · fusion · #92 MERGED · 8b1245f
- 2026-10-25 00:06 · 13.5 · CI · PR #93 rebasée sur main (avec 13.2), CI relancée · —
- 2026-10-25 00:07 · 14.2 · second-avis · 1 high (test_compression cherche l'ancien module 6), 3 défauts à la fusion avec #91 (22 scénarios, 6 h, conflit run_e2e.py), 3 low · 0daec7d
- 2026-10-25 00:10 · 13.4 · dev · fini, rebasé sur main ; E2E cache_bilan et bar_panels 30 OK · 806554a
- 2026-10-25 00:10 · 13.4 · second-avis · lancé · 806554a
- 2026-10-25 00:13 · 14.3 · CI · relance encore rouge sur Ubuntu (test_engine_candidates, même assertion) ; non reproduit sous Windows ; diagnostic délégué · 21515b7
- 2026-10-25 00:13 · 13.4 · second-avis · 1 medium (anneau 1 h à brancher après #93), 4 low · 806554a
- 2026-10-25 00:13 · 13.4 · review · lancé · 806554a
- 2026-10-25 00:14 · 13.3 · review · 3 medium corrigés (vidage en file sur le worker, attente du préremplissage, tous les slots), 4 low ; E2E local_server 53/53 · 9e09b49
- 2026-10-25 00:14 · 13.3 · décision · à revoir : cause cache_cleared prioritaire sur reset et replay tant que le moteur reste vide · 9e09b49
- 2026-10-25 00:14 · 13.3 · PR · ouverte, CI lancée · 9e09b49
- 2026-10-25 00:16 · 14.3 · CI · cause : premier jeton tiré = fin de génération (température 1, sans graine), probabiliste sous Ubuntu ; test rendu robuste (jusqu'à 30 tirages), poussé · 4be2138
- 2026-10-25 00:18 · 13.4 · review · 3 low corrigés (appel local hors « sans prix », remise à zéro sous verrou, tests) ; E2E 30/30 ; branchement 1 h à faire après #93 · f06671c
- 2026-10-25 00:18 · 13.4 · décision · à revoir : appel local exclu de « sans prix déclaré » (contre une ligne de la spec de story) · f06671c
- 2026-10-25 00:23 · 13.5 · CI · verte (Windows, Ubuntu) · bdb5f81
- 2026-10-25 00:23 · 13.5 · fusion · #93 MERGED · 5c677fb
- 2026-10-25 00:23 · 13.4 · review · reprise : rebase sur main (avec #93) et branchement de la part 1 h dans cost_ring · f06671c
- 2026-10-25 00:23 · 13.3 · CI · PR #94 rebasée sur main (avec #93), CI relancée · —
- 2026-10-25 00:23 · 13.3 · CI · PR #94 en conflit avec main après #93 ; fusion de main dans la branche (sans réécriture) déléguée · 9e09b49
- 2026-10-25 00:25 · 13.4 · review · rebasée sur #93, part 1 h branchée dans cost_ring ; E2E 30/30 · b53a301
- 2026-10-25 00:25 · 13.4 · PR · ouverte, CI lancée · b53a301
- 2026-10-25 00:26 · 13.3 · CI · main fusionnée dans la branche sans conflit, tests ciblés et E2E verts, poussée, CI relancée · 02d4662
- 2026-10-25 00:28 · 12.3 · dev · fini, rebasé sur main ; E2E rag, rag_rerank, rag_lab 153 OK ; copie de travail dans le dossier de données · 6a1b3d3
- 2026-10-25 00:28 · 12.3 · second-avis · lancé · 6a1b3d3
- 2026-10-25 00:33 · 14.3 · CI · verte (Windows, Ubuntu) après correctif du test · 4be2138
- 2026-10-25 00:33 · 14.3 · CI · conflits avec main (#89, #92, #93) ; fusion de main dans la branche déléguée · 4be2138
- 2026-10-25 00:33 · 12.3 · second-avis · 6 medium (Probe non arrêtée, tokens estimés non marqués, coûts périmés, génération en erreur, index livré sans coût, mise à jour sans effet sur les questions), 7 low · 6a1b3d3
- 2026-10-25 00:33 · 12.3 · review · lancé (décision : la chaîne lit la copie de travail si raisonnable) · 6a1b3d3
- 2026-10-25 00:35 · 14.3 · CI · main fusionnée (conflits run_e2e.py et une capture résolus), tests et E2E verts, poussée · 983883d
- 2026-10-25 00:43 · 13.4 · CI · rouge (Windows, Ubuntu) : test_llm_lab, consumption_updated émis avant model_call_ended sur LLM nu ; correctif renvoyé au reviewer · b53a301
- 2026-10-25 00:44 · 12.3 · review · 6 medium traités (5 corrigés, 1 en attente humaine), 8 low ; E2E 154/154 · 0f79d92
- 2026-10-25 00:44 · 12.3 · décision · à revoir : la chaîne lit la copie de travail quand elle diffère du livré (Never de la spec de story levé) ; Modifier = ajout d'un paragraphe · 0f79d92
- 2026-10-25 00:44 · 12.3 · attente humaine · reconstruire les 3 index réels (build_rag_index.py --lang fr|en|de) pour leurs fichiers de coût · 0f79d92
- 2026-10-25 00:44 · 12.3 · PR · ouverte, CI lancée · 0f79d92
- 2026-10-25 00:44 · 12.4 · dev · lancé (empilé sur 12.3, même page) · 0f79d92
- 2026-10-25 00:44 · 13.4 · CI · cause : assertion de test_llm_lab sur l'ancien ordre (bilan désormais émis pour un appel local) ; test réaligné, code inchangé, poussé · b5386c5
- 2026-10-25 00:45 · 13.3 · CI · verte (Windows, Ubuntu) · 02d4662
- 2026-10-25 00:45 · 13.3 · fusion · #94 MERGED · c8d0a50
- 2026-10-25 05:45 · run · report · limite d'usage de 02:12 à 05:45, run à l'arrêt · —
- 2026-10-25 05:45 · 14.3 · fusion · #91 fusionnée · 48caadd
- 2026-10-25 05:45 · 12.3 · CI · rouge (couleur codée en dur dans rag.css), corrigée · de52977
- 2026-10-25 05:52 · 13.4 · dev · fusion de main dans la branche (conflit app_session.py, deux méthodes gardées) · aa3379f
- 2026-10-25 05:52 · 14.2 · review · passe 2 faite, 2 constats Important corrigés (test_compression, 22 scénarios, 6 h) · cea00e4
- 2026-10-25 05:52 · 14.2 · PR · #97 ouverte · cea00e4
- 2026-10-25 05:52 · 14.2 · décision · à revoir : capture 01b reprise de main, à regénérer par l'E2E · —
- 2026-10-25 05:52 · 14.2 · décision · à revoir : vidéo de démo non regénérée (compose.py : 7 modules · 6 h) · —
- 2026-10-25 05:52 · 14.2 · décision · à revoir : brique éteinte à opacity 0.45 (contraste 3,2:1) gardée, état aussi en texte · —
- 2026-10-25 05:53 · 14.2 · CI · E2E harness_map et rag_agentic verts en local, capture 01b regénérée · fec1aa6
- 2026-10-25 05:56 · run · décision · Anaël : CI découpée en 4 groupes par système (PR chore/ci-shards) et analyse des fichiers partagés de la V1.2 avant de planifier ses vagues · —
- 2026-10-25 05:56 · run · décision · Anaël : mesurer l'effet d'un allègement ciblé des tests (tests lents, rechargements de modèle, tests instables) sans l'appliquer pendant le run · —
- 2026-10-25 05:57 · run · décision · à revoir : V1.2 en deux pistes (chaîne et onglets), vagues V10 à V18 ; code JS de chaque onglet dans son propre fichier dès 12.4 · —
- 2026-10-25 06:03 · 12.4 · dev · fini (fichier JS par onglet, épingle en localStorage) · e4db223
- 2026-10-25 06:03 · 12.4 · décision · à revoir : épingle Comparer en localStorage ; titre « Atelier recherche documentaire », lien de barre « RAG » gardé ; questions de suivi exclues du sélecteur ; Comparer en 4 lignes sans synthèse · —
- 2026-10-25 06:03 · run · PR · #98 ouverte (CI en 4 groupes, pytest-split 0.11.0) · 2345834
- 2026-10-25 06:05 · 12.3 · fusion · #96 fusionnée · 377426f
- 2026-10-25 06:05 · 12.4 · second-avis · lancé · e4db223
- 2026-10-25 06:09 · 13.4 · fusion · #95 fusionnée · a53e96e
- 2026-10-25 06:10 · 12.4 · second-avis · 0 high, 2 medium (YAMLError non attrapé, chargement des rag-*.js non testé), 5 low · e4db223
- 2026-10-25 06:10 · 12.4 · review · lancé (fusion de main d'abord) · e4db223
- 2026-10-25 06:14 · 14.2 · fusion · #97 fusionnée · ff8c405
- 2026-10-25 06:14 · run · CI · rouge sur #98 (clé group en double dans la matrice), corrigée · a16040d
- 2026-10-25 06:15 · 13.6 · dev · lancé · ff8c405
- 2026-10-25 06:15 · 14.4 · dev · lancé (spec de story d'abord, spec_checkpoint) · ff8c405
- 2026-10-25 06:15 · 13.6 · décision · à revoir : module 8 « Cache » placé en dernier ; le second à fusionner entre 13.6 et 14.4 refait les totaux du programme · —
- 2026-10-25 06:23 · 12.4 · review · passe 1, 2 medium corrigés (YAMLError, chargement des rag-*.js testé), 4 low corrigés · 3da301f
- 2026-10-25 06:23 · 12.4 · PR · #99 ouverte · 3da301f
- 2026-10-25 06:23 · 12.4 · décision · à revoir : épingle indépendante de la langue et du corpus ; pas de tabindex sur les panneaux ; captures echec-*.jpg ignorées par git · —
- 2026-10-25 06:26 · run · CI · #98 verte en 8 groupes : Windows 9 min 10 au plus (contre 17-18 min), Ubuntu 6 min 05 ; groupes déséquilibrés, durées complètes en cours de collecte · 286f8ea
- 2026-10-25 06:27 · run · décision · Anaël : après le run, petite story à part pour les tests lents propres à Windows (test_model_servers.py, test_context_window_setting.py, ~2 min 30 sous Windows) ; rien pendant le run · —
- 2026-10-25 06:29 · 14.4 · dev · spec de story écrite (11 critères, 9 points ouverts), relecture de spec lancée · baeeb9f
- 2026-10-25 06:29 · 13.6 · dev · fini (module 8 « Cache » 45 min, 5 scénarios, fiche, 27 scénarios / 6 h 45) · 95770bc
- 2026-10-25 06:29 · 13.6 · second-avis · lancé · 95770bc
- 2026-10-25 06:34 · 13.6 · second-avis · 0 high, 1 medium (emplacement de « Vider le cache » dans la consigne), 7 low · 95770bc
- 2026-10-25 06:34 · 13.6 · review · lancé · 95770bc
- 2026-10-25 06:35 · run · décision · Anaël : correction des tests lents propres à Windows maintenant, pas après le run (risques jugés faibles) · —
- 2026-10-25 06:35 · run · dev · lancé : faux blobs creux sous Windows (chore/tests-fichiers-creux) · —
- 2026-10-25 06:38 · 12.4 · fusion · #99 fusionnée · 881e14a
- 2026-10-25 06:42 · 12.5 · dev · lancé · 881e14a
- 2026-10-25 06:47 · run · PR · #100 ouverte (faux blobs creux sous Windows : 5 tests de 2-6 s à < 0,2 s en local, deux fichiers 43,8 s → 18,0 s) · 984a492
- 2026-10-25 06:47 · run · second-avis · lancé sur #100 · 984a492
- 2026-10-25 06:47 · run · CI · #98 en conflit (.gitignore), main fusionnée, CI équilibrée par durées relancée · bb84a21
- 2026-10-25 06:47 · 12.9 · dev · lancé · 881e14a
- 2026-10-25 06:47 · 14.4 · review · point de contrôle de spec : 9 points tranchés, spec ready-for-dev (3 prompts, overflow_prompt 3 ; _gen_tps ; _wait_mcp_connections avant les verrous) · 30dca94
- 2026-10-25 06:47 · 14.4 · décision · à revoir : les 9 points ouverts de la spec tranchés par le relecteur Opus (section « Décisions du point de contrôle » de stories/4-compaction.md) · —
- 2026-10-25 06:47 · 14.4 · dev · repris (implémentation) · 30dca94
- 2026-10-25 06:47 · run · décision · à revoir : 3 stories en développement le temps que 12.5 ou 12.9 finisse (14.4 prioritaire, V1.4 avant V1.2) · —
- 2026-10-25 06:49 · run · second-avis · #100 : 0 high, 0 medium, 4 low · 984a492
- 2026-10-25 06:49 · run · review · #100 lancée en Sonnet (diff de tests de 55 lignes, second avis propre) · 984a492
- 2026-10-25 06:49 · 13.6 · review · passe 1 : 2 medium corrigés (emplacement de « Vider le cache », test_content_language en de déjà rouge) et 4 low · cf08515
- 2026-10-25 06:49 · 13.6 · PR · #101 ouverte · cf08515
- 2026-10-25 06:49 · 13.6 · décision · à revoir : fiche du cache en français seul ; mention de /agent-cost-kit:mesurer-couts « si le plugin est installé » · —
- 2026-10-25 06:51 · run · review · #100 passe 1 (Sonnet) : retour de DeviceIoControl vérifié, avertissement sinon · 0b676a7
- 2026-10-25 06:51 · run · fusion · #98 fusionnée (CI en 4 groupes équilibrés : Windows 5 min 42 au plus contre 17-18 min, Ubuntu 2 min 41) · c3d227e
- 2026-10-25 07:04 · 12.9 · dev · fini (diagnosis.py, rag-diagnosis.js, 3 routes, 3 cas enregistrés, E2E rag_lab_diagnosis 169/169) · afe6bbd
- 2026-10-25 07:04 · 12.9 · décision · à revoir : calcul côté serveur ; budget = top_k, chute tolérée 2 rangs ; 3 cas enregistrés à la main sur de vrais chunks (pas avec les vrais modèles) ; textes dans rag_diagnosis.yaml · —
- 2026-10-25 07:04 · 12.9 · décision · à revoir : CAP-2 à CAP-4 de la spec V2 marqués absorbés alors que le diagnostic en vue harnais, la synthèse A/B et les prompts suggérés sont reportés · —
- 2026-10-25 07:04 · run · PR · agent-cost-kit #24 ouverte (0.12.0, recette de CI découpée, fusion_durees.py), non fusionnée · b7bd629
- 2026-10-25 07:06 · run · fusion · #100 fusionnée (faux blobs creux sous Windows), via file_prs.py · 13bce6b
- 2026-10-25 07:10 · run · blocked · panne du classifieur du mode auto : agents de 14.4 (Opus, implémentation en cours, non commitée) et 12.5 (Sonnet) arrêtés · —
- 2026-10-25 07:18 · 13.6 · CI · #101 rouge sur Windows et Ubuntu (run 40166873731) ; base en retard sur #99 et #100 · cf08515
- 2026-10-25 07:18 · 12.5 · dev · arrêté après 2 commits (code, E2E) ; 12 captures E2E modifiées non commitées · 05ec223
- 2026-10-25 07:18 · 14.4 · dev · arrêté en pleine implémentation (kept dans CompactionChoice, puis front) ; 19 fichiers modifiés non commités · 30dca94
- 2026-10-25 07:18 · run · décision · reprise : #101 (merge main, cause CI), fusion, release V1.3 ; puis 14.4 (Opus) et 12.5 (Sonnet) depuis leur worktree ; second avis de 12.9 · —
- 2026-10-25 07:21 · 13.6 · CI · cause : test_compression attendait Compression en dernier module ; main fusionnée, test réaligné (Cache en dernier), CI relancée · 4c67f02
- 2026-10-25 07:21 · 14.4 · dev · relancé (Opus) depuis le worktree : commit du travail en cours, fusion de main, fin de l'implémentation · 30dca94
- 2026-10-25 07:21 · 12.5 · dev · relancé (Sonnet) : vérification des critères, captures, fusion de main · 05ec223
- 2026-10-25 07:21 · 12.9 · second-avis · lancé · afe6bbd
- 2026-10-25 07:27 · 13.6 · CI · verte (8 groupes) · 4c67f02
- 2026-10-25 07:27 · 13.6 · fusion · #101 MERGED via file_prs.py ; lot V1.3 terminé · 1a55608
- 2026-10-25 07:27 · run · PR · #102 ouverte (version 1.3.0) · —
- 2026-10-25 07:30 · 12.9 · second-avis · 0 high, 6 medium (découpage jugé sur le livré, aucune étape = aucune faute, budget lu sur la chaîne courante, top_k ≤ 10 contre 20, CAP-2 à 4 fermés à tort, JS sans test en CI), 4 low · afe6bbd
- 2026-10-25 07:30 · 12.9 · décision · à revoir : CAP-2 à CAP-4 de la spec V2 « partiellement absorbés », restent ouverts ; E2E hors CI (aucun E2E n'y tourne) · —
- 2026-10-25 07:30 · 12.9 · review · lancé (fusion de main d'abord) · afe6bbd
- 2026-10-25 07:32 · run · fusion · #102 MERGED (version 1.3.0) via file_prs.py · ec7e1ff
- 2026-10-25 07:32 · run · décision · release v1.3.0 publiée (tag annoté, pre-release comme les précédentes) · ec7e1ff
- 2026-10-25 07:38 · 12.9 · review · passe 1 : 5 medium corrigés (liste de l'exécution prioritaire sur le découpage livré, context:missing sans étape classante, paramètres du run, top_k ≤ 20, CAP-2 à 4 partiels), low 7 et 9 corrigés ; E2E rag rag_rerank rag_lab_diagnosis 81/81 · 50751a6
- 2026-10-25 07:38 · 12.9 · décision · à revoir : copie de travail éditée ignorée si le passage n'est dans aucune liste (Reports de la story) ; E2E rag_lab_diagnosis dépend de rag et rag_rerank · —
- 2026-10-25 07:38 · 12.9 · PR · #103 ouverte · 50751a6
- 2026-10-25 07:44 · 14.4 · dev · fini ; critères 1 à 11, test_compaction 26 verts, E2E compaction, sliding_window, compact_button, programme 41/41, local_server 55/55 ; totaux du programme à refaire avec le module 8 · c0ba396
- 2026-10-25 07:44 · 14.4 · décision · à revoir : champ kept dans CompactionChoice ; débordement du sous-agent ou du résumé ne périme pas la carte du chat ; prompt 2 de compaction lit alertes_siem.log ; menu à la largeur du volet ; captures 80 à 83 · c0ba396
- 2026-10-25 07:44 · 14.4 · second-avis · lancé · c0ba396
- 2026-10-25 07:44 · 12.9 · CI · verte · 50751a6
- 2026-10-25 07:44 · 12.9 · fusion · #103 MERGED via file_prs.py · 7a6dde0
- 2026-10-25 07:44 · 12.15 · dev · lancé (phase spec, worktree ../wavestack-v12-s15) · 50751a6
- 2026-10-25 07:46 · 12.15 · dev · spec prête (16 critères, 9 points ouverts : jeu évalué, juge local non Qwen, famille cloud, annotation, extra Ragas/DeepEval…) · d40288d
- 2026-10-25 07:46 · 12.15 · review · relecture de la spec lancée (pas de dépendance qui tire torch, cas enregistrés si modèle réel requis) · d40288d
- 2026-10-25 07:48 · 12.5 · dev · fini ; 2 critères et 4 tâches couverts, captures écartées (regénérations), 332 tests ciblés verts ; E2E 167/168 (« Modifier : mise à jour mesurée sur la copie de travail »), échecs variables d'une passe à l'autre · 9573146
- 2026-10-25 07:48 · 12.5 · décision · à revoir : suivi lu sur les 3 dernières questions, étape query à part, fusion par rangs réciproques, consigne dans messages.yaml ; sources des fiches citées sans accès réseau · —
- 2026-10-25 07:48 · 12.5 · second-avis · lancé (priorité : échec E2E « Modifier ») · 9573146
- 2026-10-25 07:48 · 12.6 · dev · lancé (phase spec, empilé sur 12.5, worktree ../wavestack-v12-s6) · 9573146
