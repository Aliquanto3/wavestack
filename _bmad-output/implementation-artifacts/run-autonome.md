# Run autonome de nuit : V1.3, V1.4 puis V1.2

Lancé le 2026-10-24 à la demande d'Anaël, après le run SLM A/B (archivé dans [run-autonome-slm-2026-10-24.md](run-autonome-slm-2026-10-24.md)). Orchestration : session principale Opus 5.5.

## Périmètre

| Périmètre | Epics | Note |
|---|---|---|
| Dans le run | Epics 12 à 14 | epic 13 = V1.3, 14 = V1.4, 12 = V1.2 ; priorité stricte 13, 14, 12 ; story 12.1 = PR #79 |
| Hors run | V2, SLM C | spec V2 en brouillon ; SLM C en attente du benchmark |

Specs : `_bmad-output/specs/spec-wavestack-cache-visible/` (V1.3), `spec-wavestack-etat-de-l-art-harnais/` (V1.4), `spec-wavestack-v1-2-atelier-recherche-documentaire/` (V1.2).

Au plus 3 stories en développement à la fois (3e créneau seulement pour une story sans fichier commun avec les deux autres ; sinon 2 ; décision d'Anaël du 2026-10-25)

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
| V19 | 12.19b | 12.19b ← 12.19 (découpée de 12.19 au point de contrôle) |

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
- 2026-10-25 : les stories V1.2 restantes s’intègrent sur `integration/v1-2-atelier` (créée depuis main à 75864b7), PR avec `--base integration/v1-2-atelier` ; main reste à la 1.4.0 (onglet harnais) jusqu’à la fin de la V1.2, qui sera fusionnée en une fois (Anaël, formation sur l’onglet harnais).

## Reprise après /clear

- Lire ce fichier en entier, puis `sprint-status.yaml` ; l'état réel prime : `gh pr list --state open`, `git -C ../wavestack-<lot>-s<n> log -3 --oneline` pour chaque worktree d'une story en cours.
- Worktrees de la V1.2 : `../wavestack-v12-s<n>` (s11 : 12.11, spec ready-for-dev 3f8f1cd ; s19 : 12.19, a6b5584, PR à ouvrir après la revue). Les autres sont fusionnés, à supprimer en fin de run.
- Les stories V1.2 s'intègrent sur `integration/v1-2-atelier` (PR `--base integration/v1-2-atelier`, fusion `--methode merge`) ; main reste à la v1.4.0 jusqu'à la fin de la V1.2.
- Une story dont le dev a commité sans rapport : relancer la chaîne à partir de `second-avis` sur son dernier commit.
- Fusions par `scripts/file_prs.py` du kit (vérifie `MERGED`), puis journal. Sur `integration/v1-2-atelier` : `--methode merge` (les branches V1.2 sont empilées ; un squash recrée des conflits dans la story suivante).
- Fin de lot : PR de version (SemVer mineure), tag annoté, release GitHub ; V1.3 dès la fusion de 13.6, V1.4 dès celle de 14.4.
- E2E : `TEMP` et `TMP` en chemin long (`C:\Users\Utilisateur\AppData\Local\Temp`) ; un `TEMP` en nom court 8.3 peut faire échouer `rag` (« index non construit ») et tous les scénarios en aval (constat de 12.7).
- Fichiers temporaires des agents : chacun dans son sous-dossier du scratchpad (`scratchpad\s<story>`), jamais à la racine (collision de `msgs.py` constatée par 12.10).
- Fin de run : `rapport-nuit-2026-10-25.md` (fusionné, bloqué, reporté, liste « à revoir », tests manuels du matin), mémoire du projet, suppression des worktrees.

## Après le run

- (Avancée dans le run le 2026-10-25, décision d'Anaël.) Story d'outillage : accélérer les tests lents propres à Windows de `tests/test_model_servers.py` et `tests/test_context_window_setting.py` (11 à 33 s chacun sous Windows, absents du haut de la liste sous Ubuntu ; piste : connexion à un port fermé qui met ~2 s à échouer sous Windows). Gain mesuré attendu : ~2 min 30 de tests Windows. Décision d'Anaël du 2026-10-25.
- Rafraîchir `test-durations-windows-latest.json` et `test-durations-ubuntu-latest.json` depuis les artefacts `test-durations-<os>-<groupe>` d'une CI récente (fusion des 4 fichiers par système), quand l'écart entre groupes dépasse ~2 min.

## Prochaines étapes (mise à jour du 2026-10-25 17:20)

1. #123 (12.12) : file_prs.py --methode merge en cours ; à la fusion, refusionner l'intégration dans 12.16 (worktree s16, revue faite 7e97f4c9 ; vérifier que les parties run.sN.rewrite / retry_<kind> / abstain de 12.12 apparaissent dans l'arbre), PR, fusion.
2. 12.21 : téléchargement des modèles (ColPali ~5,9 Go, ColSmol ~1 Go) en cours dans ../wavestack-v12-s21 ; puis, poste libre de tout agent : `uv run --with fastembed==0.9.1 python tools/bench/v12s21_visual_search_bench.py measure --confirm-idle`, `report --write`, second avis, revue, PR.
3. Correctif préexistant de 12.13 : _update_graph écrit avant la copie gardée et garde des extractions partielles si le modèle échoue (même règle que 12.12 : StageFailed, écriture après keep) ; petite PR vers l'intégration.
4. Fin du lot V1.2 : PR integration/v1-2-atelier → main (merge), CI verte ; PR de version 1.5.0, tag annoté v1.5.0, release GitHub ; README.md à refaire (l'interface a changé avec les epics 13, 14 et 12 : onglet harnais, cache, atelier recherche documentaire à onglets, onglet « Modèles ») et démo docs/assets/wavestack-demo.gif + .mp4 à regénérer par tools/demo/compose.py (programme, modules et durées à jour), dans la PR d'intégration vers main ou une PR juste avant (demande d'Anaël du 2026-10-25) ; rapport de fin de run (fusionné, reporté, liste « à revoir », recettes d'Anaël) ; mémoire du projet ; suppression des worktrees ../wavestack-v12-s* en fin de run.

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
- 2026-10-25 07:50 · 14.4 · second-avis · 0 high, 4 medium (échanges retirés non résumés si transcription tronquée, boutons de la carte bloqués après échec, renvoi qui rejoue des outils à effet, conflits et totaux avec le module 8), 5 low · c0ba396
- 2026-10-25 07:50 · 14.4 · review · lancé (Opus, fusion de main et totaux du programme d'abord) · c0ba396
- 2026-10-25 07:51 · 12.6 · dev · spec prête (13 critères, 7 points ouverts : late chunking reporté, contextes heuristiques livrés, parent-enfant…) · 47c67a5
- 2026-10-25 07:51 · 12.6 · review · relecture de la spec lancée · 47c67a5
- 2026-10-25 07:53 · 12.15 · review · spec approuvée ; jugement par intention rag_lab_judge, exécutions envoyées par la page, grammar dans complete (engine, servers), famille = publisher_for, critère 17 ajouté · 6b1898b
- 2026-10-25 07:53 · 12.15 · décision · à revoir : 9 points tranchés par le relecteur Opus (jeu construit dense/hybrid, juge local découvert sur le poste, pas d'extra Ragas/DeepEval, MIN_SAMPLE 5, annotations draft « à valider ») · 6b1898b
- 2026-10-25 07:53 · 12.15 · attente humaine · valider les annotations de référence ; réenregistrer jeu et pièges avec un vrai juge local non Qwen et un juge cloud ; essayer « Juger cette exécution » sur CPU · —
- 2026-10-25 07:53 · 12.15 · dev · phase 2 (code) lancée · 6b1898b
- 2026-10-25 07:54 · 12.5 · second-avis · 0 high, 2 medium (course sur « Modifier » : fin émise avant la sauvegarde de la copie, préexistante, cause probable de l'échec E2E ; préambule du modèle pris pour une requête), 3 low · 9573146
- 2026-10-25 07:54 · 12.5 · review · lancé (fusion de main d'abord) · 9573146
- 2026-10-25 07:57 · 12.6 · review · spec approuvée ; STEPS et clé de cache de paragraphs inchangés, contexte heuristique « Extrait n/N de… » étiqueté « heuristique, sans LLM », intention rag_lab_rebuild, critère 14 ajouté · 282e90b
- 2026-10-25 07:57 · 12.6 · décision · à revoir : 8 points tranchés par le relecteur Opus (late chunking reporté, contextes valables à 700 caractères seulement, enfants ≤ 300, contextes reconstruits dans le dossier de données) · 282e90b
- 2026-10-25 07:57 · 12.6 · attente humaine · facultatif : regénérer rag_contexts.yaml avec un vrai modèle ; mesurer une reconstruction complète sur le PC cible ; vérifier les sources des fiches · —
- 2026-10-25 07:57 · 12.6 · dev · phase 2 (code) lancée · 282e90b
- 2026-10-25 08:08 · 14.4 · review · passe 1 : main fusionnée (module 7 de 60 min, 28 scénarios, 7 h) ; 2 medium et 2 low corrigés (échanges non résumés dits à part, boutons rétablis après échec, critère 9, _last oublié), test MCP ajouté ; E2E 41/41 et 62/62 · eae5010
- 2026-10-25 08:08 · 14.4 · décision · à revoir : boutons au débordement d'un appel ultérieur, tour rejoué avec ses outils (décision 7) ; tour de compaction visible dans Comparer ; texte « plus anciens retirés sans résumé » · eae5010
- 2026-10-25 08:08 · 14.4 · PR · #104 ouverte · eae5010
- 2026-10-25 08:13 · 12.5 · review · passe 1 : main fusionnée ; 2 medium corrigés (copie sauvée avant la fin de « Modifier » + attente de « 1 modifié » dans l'E2E ; préambules écartés par parse_queries), 2 low corrigés ; E2E 168/168 après correctif, diagnosis 81/81 · d767ef0
- 2026-10-25 08:13 · 12.5 · décision · à revoir : questions annulées gardées dans l'historique du suivi ; échec de sauvegarde de la copie = session.rag_lab.interrupted · d767ef0
- 2026-10-25 08:13 · 12.5 · PR · #105 ouverte · d767ef0
- 2026-10-25 08:21 · 14.4 · CI · rouge (Windows, Ubuntu) : harness_map en de ne citait pas le scénario Compression ; règle .compact-choice .pane-text-action hors de pages.css ; corrigé (classe compact-choice-button), tests ciblés verts · a29fecf
- 2026-10-25 08:23 · 12.6 · dev · fini ; 14 critères, build_rag_contexts.py déterministe, 485 tests ciblés verts, E2E rag rag_rerank rag_lab rag_lab_chunking 160/160 ; 12.5 revue fusionnée · 88b9a7d
- 2026-10-25 08:23 · 12.6 · décision · à revoir : coupe sémantique au 80e centile (gap >= seuil), reconstruction fusionnée avec l'existant, coût du contextual lu dans l'en-tête, outil sans --model, sources des fiches à vérifier · 88b9a7d
- 2026-10-25 08:23 · 12.6 · second-avis · lancé · 88b9a7d
- 2026-10-25 08:23 · 12.7 · dev · lancé (phase spec, empilé sur 12.6, worktree ../wavestack-v12-s7) · 88b9a7d
- 2026-10-25 08:28 · 12.7 · dev · spec prête (15 critères, 8 points ouverts : options budget / edges / compressed, budget 450 tokens estimés, compresseur emprunté à la session…) · 9feaba7
- 2026-10-25 08:28 · 12.7 · review · relecture de la spec lancée · 9feaba7
- 2026-10-25 08:31 · 12.6 · second-avis · 0 high, 2 medium (en-tête des contextes reconstruits limité au dernier run, top_k parents distincts non garanti), 4 low ; clé de cache paragraphs inchangée vérifiée · 88b9a7d
- 2026-10-25 08:31 · 12.6 · décision · à revoir : build_rag_contexts.py sans --model (pas de moteur testable sans modèle), spec mise en accord · —
- 2026-10-25 08:31 · 12.6 · review · lancé · 88b9a7d
- 2026-10-25 08:34 · 12.15 · dev · fini ; 17 critères, test_rag_evaluation 58 verts, E2E jusqu'à 181/181 ; échecs variables de rag_lab « Modifier » (branche sans le correctif de #105) et un « mémoire insuffisante » · b7d33be
- 2026-10-25 08:34 · 12.15 · décision · à revoir : verdicts yes / partly / no (1 / 0,5 / 0), jeu de 10 questions, juges cibles Granite 4.0 Micro et Mistral Small, sondage 1,5 s, juge chargé par appel, moteur sans grammar refusé comme juge · b7d33be
- 2026-10-25 08:34 · 12.15 · second-avis · lancé · b7d33be
- 2026-10-25 08:34 · 12.17 · dev · lancé (phase spec, empilé sur 12.15, worktree ../wavestack-v12-s17) · b7d33be
- 2026-10-25 08:40 · 14.4 · CI · verte après correctif · a29fecf
- 2026-10-25 08:40 · 14.4 · fusion · #104 MERGED via file_prs.py ; lot V1.4 terminé · 75864b7
- 2026-10-25 08:40 · 12.5 · CI · rouge : garde-fou des textes français sur les guillemets et le motif de préambule de parse_queries ; exceptions ajoutées, poussé · dd95df5
- 2026-10-25 08:40 · run · PR · #106 ouverte (version 1.4.0, epics 13 et 14) · —
- 2026-10-25 08:40 · run · décision · Anaël : stories V1.2 restantes sur la branche integration/v1-2-atelier, main gardée à la 1.4.0 pour la formation sur l'onglet harnais ; #105 reciblée · 75864b7
- 2026-10-25 08:40 · 12.15 · second-avis · 0 high, 1 medium (sondage arrêté à 300 s sans rétablir le bouton), 5 low ; grammar sans effet sur les appels existants vérifié · b7d33be
- 2026-10-25 08:40 · 12.15 · review · lancé (base integration/v1-2-atelier) · b7d33be
- 2026-10-25 08:40 · 12.17 · dev · lancé (phase spec, empilé sur 12.15, worktree ../wavestack-v12-s17) · b7d33be
- 2026-10-25 08:41 · run · fusion · #106 MERGED (version 1.4.0) via file_prs.py · ee6d251
- 2026-10-25 08:41 · run · décision · release v1.4.0 publiée (epics 13 et 14) ; integration/v1-2-atelier avancée à ee6d251 · ee6d251
- 2026-10-25 08:44 · 12.5 · CI · aucun contrôle sur dd95df5 (push pendant une coupure de GitHub) ; branche d'intégration fusionnée (capture 01b prise d'intégration), CI relancée · 5e991af
- 2026-10-25 08:44 · 12.17 · dev · spec prête (15 critères, 8 points ouverts : cas enregistrés, Prompt Guard not_installed honnête, mini-graphe illustratif en attendant 12.13…) · 1e6a1c5
- 2026-10-25 08:44 · 12.17 · review · relecture de la spec lancée · 1e6a1c5
- 2026-10-25 08:44 · 12.7 · review · spec approuvée après 10 corrections (options budget / order / compress d'architectures.md, PARAM_DEFAULTS, passages écartés dans dropped, règle cut élargie, prompt_parts partagé) · 1e5f3ad
- 2026-10-25 08:44 · 12.7 · décision · à revoir : 8 points tranchés par le relecteur Opus (budget 450 tokens estimés, compresseur emprunté seulement, coupe en fin de phrase avec « […] ») · 1e5f3ad
- 2026-10-25 08:44 · 12.7 · attente humaine · facultatif : mesurer avant / après de compress avec l'extra compression sur le PC cible · —
- 2026-10-25 08:44 · 12.7 · dev · phase 2 (code) lancée (Sonnet, effort high) · 1e5f3ad
- 2026-10-25 08:46 · 12.6 · review · passe 1 : 2 medium corrigés (en-tête des contextes reconstruits cumulé, avertissement context.parents_short), 2 low corrigés ; E2E 160/160 · ca5a441
- 2026-10-25 08:46 · 12.6 · décision · à revoir : avertir plutôt qu'élargir la recherche des parents ; fichier reconstruit remplacé en entier si la taille de chunk change · ca5a441
- 2026-10-25 08:46 · 12.6 · PR · #107 ouverte vers integration/v1-2-atelier (empilée sur #105) · ca5a441
- 2026-10-25 08:49 · 12.5 · CI · verte · 5e991af
- 2026-10-25 08:49 · 12.5 · fusion · #105 MERGED dans integration/v1-2-atelier via file_prs.py · 83719c1
- 2026-10-25 08:49 · 12.6 · CI · branche d'intégration fusionnée (conflits du squash de #105 résolus côté 12.6, écart vérifié = fichiers de version seuls), CI relancée · 6518c09
- 2026-10-25 08:49 · run · décision · à revoir : fusions dans integration/v1-2-atelier en --methode merge (branches empilées), squash réservé à main · —
- 2026-10-25 08:52 · 12.15 · review · passe 1 : 1 medium (sondage sans limite, arrêt après 5 échecs, bouton rétabli) et 4 low corrigés (réponse tardive ignorée, juge introuvable = 409, moteur fermé si grant échoue, JUDGE_MAX_TOKENS 256) ; E2E 181/181 · af7e5f9
- 2026-10-25 08:52 · 12.15 · décision · à revoir : JUDGE_MAX_TOKENS 256 relève aussi la réserve du juge cloud · af7e5f9
- 2026-10-25 08:52 · 12.15 · PR · #108 ouverte vers integration/v1-2-atelier · af7e5f9
- 2026-10-25 08:55 · 12.17 · review · spec approuvée ; rangs BM25 mesurés (injection hors contexte, reformulation prévue), Prompt Guard sans téléchargement (loaded_classifier), décision not_installed journalisée, références corrigées · 5dffbb1
- 2026-10-25 08:55 · 12.17 · décision · à revoir : 8 points tranchés par le relecteur Opus (cas constructed, mini-graphe illustratif, block par défaut, un seul document piégé) · 5dffbb1
- 2026-10-25 08:55 · 12.17 · attente humaine · avant de déclarer finie (done_checkpoint) : recette visuelle fr/en/de clair et sombre, relecture des reformulations en/de, vrai verdict Prompt Guard 2, enregistrement des réponses, entrées de la page Sécurité · —
- 2026-10-25 08:55 · 12.17 · dev · phase 2 (code) lancée · 5dffbb1
- 2026-10-25 09:02 · 12.6 · CI · rouge Windows groupe 4 deux fois : test_rag_lab_download::test_the_files_are_read_again_before_idle (rappel _rag_caught_up absent) ; non reproduit en local, seul ni après test_rag_lab_chunking ; hors diff de 12.6 ; 3e relance · 6518c09
- 2026-10-25 09:11 · 12.6 · CI · verte à la 3e relance (test de téléchargement instable sous Windows) · 6518c09
- 2026-10-25 09:11 · 12.6 · fusion · #107 MERGED dans integration/v1-2-atelier (merge) via file_prs.py · 746329b
- 2026-10-25 09:11 · 12.15 · CI · branche d'intégration fusionnée (4 conflits d'ajout, deux côtés gardés), 4652 tests ciblés verts, CI relancée · 9c9adf2
- 2026-10-25 09:16 · 12.15 · CI · E2E de la fusion rag rag_rerank rag_lab_chunking rag_lab_evaluate : 47/54 (rag en délai dépassé, poste chargé), relancé 94/94 · 9c9adf2
- 2026-10-25 09:18 · 12.17 · dev · fini ; 16 critères, test_rag_attack 37 verts, 4670 tests ciblés verts, E2E rag_lab_attack 28/28 deux fois ; corpus faq_mots_de_passe reformulé ×3 · d95e83a
- 2026-10-25 09:18 · 12.17 · décision · à revoir : sans Prompt Guard chargé, verdict enregistré appliqué à la colonne « avec » ; entrées de démonstration comptées dans « bloqués » ; not_installed au niveau mid ; capture sans numéro · d95e83a
- 2026-10-25 09:18 · 12.17 · second-avis · lancé (priorité : effet de la reformulation du corpus sur 12.6, 12.9, 12.15) · d95e83a
- 2026-10-25 09:19 · 12.18 · dev · lancé (phase spec, empilé sur 12.17, worktree ../wavestack-v12-s18) · d95e83a
- 2026-10-25 09:22 · 12.18 · dev · spec prête (16 critères, 8 points ouverts : instantanés en mémoire, dérivés illustratifs, sentinelle projet_orion dans l'état de la page, corpus livré inchangé) · af49d59
- 2026-10-25 09:22 · 12.18 · review · relecture de la spec lancée · af49d59
- 2026-10-25 09:22 · 12.18 · attente humaine · décision : corriger « story 14 » en « story 18 » dans projet_orion.md (corpus livré, empreintes) · —
- 2026-10-25 09:23 · 12.15 · CI · verte après une relance · 9c9adf2
- 2026-10-25 09:23 · 12.15 · fusion · #108 MERGED dans integration/v1-2-atelier (merge) via file_prs.py · b3246b2
- 2026-10-25 09:24 · 12.7 · dev · fini ; 16 critères (10 sauté : extra compression absent), 4890 tests ciblés verts, E2E 168/168 et --no-headroom 54/54 ; 12.6 et intégration fusionnées · a652ed4
- 2026-10-25 09:24 · 12.7 · décision · à revoir : libellés « Budget de contexte (tokens) », « Ordre des passages (extrémités d'abord) », « Compression (Headroom) » ; extrait formaté entier compressé ; avertissements concaténés ; citations des fiches à relire · a652ed4
- 2026-10-25 09:24 · 12.7 · second-avis · lancé · a652ed4
- 2026-10-25 09:24 · 12.10 · dev · lancé (phase spec, empilé sur 12.7, worktree ../wavestack-v12-s10) · a652ed4
- 2026-10-25 09:25 · 12.17 · second-avis · 0 high, 3 medium (verdict enregistré qui pilote la colonne « avec » sans Prompt Guard, entrées de démonstration comptées dans le journal réel, état interdit du mini-graphe), 4 low ; corpus reformulé inactif (faq_mots_de_passe active: false), aucun effet sur 12.6, 12.9, 12.15 · d95e83a
- 2026-10-25 09:25 · 12.17 · review · lancé (base integration/v1-2-atelier) · d95e83a
- 2026-10-25 09:29 · 12.10 · dev · spec prête (18 critères, 7 points ouverts : tête de chaîne skipped, CAG refusé en nuage, appel de chauffe pour llama-server, une seule entrée de cache d'état, fenêtre = 16 384) · 3ffe294
- 2026-10-25 09:29 · 12.10 · review · relecture de la spec lancée (mémoire du snapshot sur 16 Go, cache du chat) · 3ffe294
- 2026-10-25 09:30 · 12.7 · second-avis · 0 high, 1 medium (compresseur emprunté puis libéré par la session pendant l'étape), 5 low (HF_HUB_OFFLINE sans verrou, tests sans texte figé, branche Headroom de l'E2E jamais exécutée) ; prompt de la génération inchangé vérifié · a652ed4
- 2026-10-25 09:30 · 12.7 · review · lancé (fusion de l'intégration d'abord) · a652ed4
- 2026-10-25 09:31 · 12.18 · review · spec approuvée ; numéros de stories corrigés, endroits alignés sur attaques-et-conformite.md, mesures BM25 (sentinelle rangs 1-2, q_global_rh passage RH au rang 2), JS enregistré sous ses propres clés · ae54017
- 2026-10-25 09:31 · 12.18 · décision · à revoir : 8 points tranchés par le relecteur Opus (instantanés en mémoire, dérivés illustratifs, q_global_rh, tableau de 11 architectures) · ae54017
- 2026-10-25 09:31 · 12.18 · attente humaine · avant de déclarer finie (done_checkpoint) : recette visuelle fr/en/de clair et sombre, jouer effacement et droits, corpus et copie de travail inchangés, relire les contenus construits · —
- 2026-10-25 09:31 · 12.18 · dev · phase 2 (code) lancée · ae54017
- 2026-10-25 09:36 · 12.17 · review · passe 1 : 3 medium corrigés (seul le verdict réel agit, entrées de démonstration hors compteurs via record(counted=False), remove sans inject refusé), 4 low corrigés (LoadedOnly : la carte ne peut jamais charger Prompt Guard) ; E2E 102/102 · 0127a8c
- 2026-10-25 09:36 · 12.17 · décision · à revoir : sans Prompt Guard chargé, rien n'est écarté (critère 14 lu « affiché ») ; security_log.py modifié par ajout · 0127a8c
- 2026-10-25 09:36 · 12.17 · PR · #109 ouverte vers integration/v1-2-atelier · 0127a8c
- 2026-10-25 09:44 · 12.7 · review · passe 1 : medium écarté (libération du compresseur sur le worker unique, après le run, test ajouté), 4 low corrigés (excerpts figé par sha256, test Headroom réel renforcé, avertissement context.budget_over) ; E2E 168/168 · 1b92d4e
- 2026-10-25 09:44 · 12.7 · PR · #110 ouverte vers integration/v1-2-atelier · 1b92d4e
- 2026-10-25 09:45 · 12.10 · review · spec approuvée (19 critères) ; fenêtre effective, CAG à un seul état avec contrôle mémoire (LoadRegistry, RSS, MemoryError) et repli sans cache, jauge du chat qui ignore l'atelier (défaut préexistant), tests sur petit corpus · 689a1f1
- 2026-10-25 09:45 · 12.10 · décision · à revoir : 7 points tranchés par le relecteur Opus (règle 16 384 aussi en nuage, état reconstruit gardé à la mise à jour, NO_INDEX_WINDOW en >=) ; réglage de fenêtre sur la page Conversation, contre la maquette · 689a1f1
- 2026-10-25 09:45 · 12.10 · attente humaine · mesures réelles sur le PC cible (durées à froid et à chaud, taille de l'état, mémoire de crête, tokens réels du corpus) ; fenêtre de 16 384 dans 4 Go à confirmer par la story 12.2 · —
- 2026-10-25 09:45 · 12.10 · dev · phase 2 (code) lancée (Opus, effort high) · 689a1f1
- 2026-10-25 09:47 · 12.17 · CI · rouge Windows groupe 4 : même test instable test_the_files_are_read_again_before_idle ; cause : _rag_caught_up appelé par le fil de téléchargement après idle, hors du worker attendu par join ; le test attend désormais l'appel (Event, 10 s) · 4d6cc03
- 2026-10-25 09:49 · 12.18 · dev · fini ; 16 critères, 4760 tests ciblés verts, E2E rag_lab_attack et rag_lab_rights verts, rag_rerank en échec mémoire (1 à 1,25 Go de RAM libre) · 89b0697
- 2026-10-25 09:49 · 12.18 · décision · à revoir : 11 architectures et 12 endroits dont 7 construits, textes de remise en conformité écrits par le dev, rebuild vide accepté, capture 69 · 89b0697
- 2026-10-25 09:49 · 12.18 · second-avis · lancé · 89b0697
- 2026-10-25 09:50 · 12.19 · dev · lancé (phase spec, empilé sur 12.18, worktree ../wavestack-v12-s19) · 89b0697
- 2026-10-25 09:53 · 12.18 · second-avis · 0 high, 1 medium (endroit construit affiché « effacé » sans mesure), 4 low ; aucune écriture de fichier, fuite au profil Tous en mode après vérifiée, mode avant sans fuite · 89b0697
- 2026-10-25 09:53 · 12.18 · décision · à revoir : endroit construit jamais « effacé » mesuré, statut distinct « effacé (illustratif, non mesuré) » · —
- 2026-10-25 09:53 · 12.18 · review · lancé · 89b0697
- 2026-10-25 09:54 · 12.19 · dev · spec prête (17 critères, 8 points ouverts : 13 fiches de composant à écrire, RAPTOR sans source, cadre réglementaire sans niveau, niveaux proposés à relire par Anaël) · a29f707
- 2026-10-25 09:54 · 12.19 · review · relecture de la spec lancée · a29f707
- 2026-10-25 09:54 · 12.17 · CI · verte après le correctif du test instable · 4d6cc03
- 2026-10-25 09:54 · 12.17 · fusion · #109 MERGED dans integration/v1-2-atelier (merge) via file_prs.py · 16c4eca
- 2026-10-25 09:58 · 12.7 · CI · rouge (même test instable, branche sans correctif) ; intégration fusionnée, 269 tests ciblés verts, CI relancée · c7408d2
- 2026-10-25 10:01 · 12.19 · review · spec approuvée (18 critères) ; données de 12.18 relues et non recopiées, liens #attack, hypotheses tirées de litterature.md, axe réglementaire sans niveau, niveaux « proposition, à relire » · 3bbbf2f
- 2026-10-25 10:01 · 12.19 · décision · à revoir : 13 fiches de composant découpées en story 12.19b (vague V19) ; page Sécurité = même vocabulaire RISKS sans seconde matrice (lecture de CAP-16) ; RAPTOR sans source · 3bbbf2f
- 2026-10-25 10:01 · 12.19 · attente humaine · avant de déclarer finie (done_checkpoint) : relire niveaux et formulations réglementaires fr/en/de (graphrag / Droits « élevé » contre « moyen » en maquette), liens de littérature, lecture de CAP-16, recette visuelle ; source primaire de RAPTOR à ouvrir avec réseau · —
- 2026-10-25 10:01 · 12.19 · dev · phase 2 (code) lancée · 3bbbf2f
- 2026-10-25 10:03 · 12.18 · review · passe 1 : 1 medium (statut erased_illustrative « effacé (illustratif, non mesuré) ») et 4 low corrigés (ligne Source, rebuild vide 422, datifs allemands, REQUIRED_TEXTS) ; E2E 99/99 · 6bb832d
- 2026-10-25 10:03 · 12.18 · décision · à revoir : statut erased_illustrative et critère 6 réécrit · 6bb832d
- 2026-10-25 10:03 · 12.18 · PR · #111 ouverte vers integration/v1-2-atelier · 6bb832d
- 2026-10-25 10:04 · 12.7 · CI · verte · c7408d2
- 2026-10-25 10:04 · 12.7 · fusion · #110 MERGED dans integration/v1-2-atelier (merge) via file_prs.py · 3469b9e
- 2026-10-25 10:10 · 12.18 · CI · #111 en conflit après #110 (3 captures) ; intégration fusionnée, captures de l'intégration, 273 tests ciblés verts, CI relancée · c5c9f02
- 2026-10-25 10:16 · 12.18 · CI · verte · c5c9f02
- 2026-10-25 10:16 · 12.18 · fusion · #111 MERGED dans integration/v1-2-atelier (merge) via file_prs.py · 488af94
- 2026-10-25 10:34 · 12.10 · dev · fini ; 19 critères, test_rag_lab_no_index 50 verts, 5220 tests ciblés verts ; E2E 1er passage 8 échecs (RAM 790 Mo, 2 défauts corrigés), 2e 213/213 · 598f633
- 2026-10-25 10:34 · 12.10 · décision · à revoir : préfixe en cache comme partie de l'étape Contexte ; sans état gardé, la génération relit le préfixe resté dans le moteur ; catalogue de validation relu au changement de modèle ou de fenêtre ; captures 77 et 78 · 598f633
- 2026-10-25 10:34 · 12.10 · second-avis · lancé · 598f633
- 2026-10-25 10:34 · 12.11 · dev · lancé (phase spec, empilé sur 12.10, worktree ../wavestack-v12-s11) · 598f633
- 2026-10-25 10:38 · 12.11 · dev · spec prête (21 critères, 9 points ouverts : boucle agentique dans l'étape Contexte, outils sur la copie de travail, arbre à deux niveaux heuristique, famille Structure) · d9f6a59
- 2026-10-25 10:38 · 12.11 · review · relecture de la spec lancée · d9f6a59
- 2026-10-25 10:39 · 12.10 · second-avis · 0 high, 1 medium (état CAG jamais enregistré au registre de mémoire), 6 low ; restauration du moteur du chat sur tous les chemins et jauge du chat vérifiées · 598f633
- 2026-10-25 10:39 · 12.10 · review · lancé (Opus) · 598f633
- 2026-10-25 10:52 · 12.11 · review · spec approuvée ; confinement par noms virtuels corpus/<doc_id>.md (jamais de chemin ouvert), bornes chiffrées, boucle annulable, agent_unreadable, SEARCHLESS_OPTIONS en 4 usages, match_lines extrait de search_documents sans changement · 3f8f1cd
- 2026-10-25 10:52 · 12.11 · décision · à revoir : 9 points tranchés par le relecteur Opus (outils hors NATIVE_TOOLS mais mêmes noms et messages, arbre à deux niveaux, famille Structure, rebuild target) ; long_context et cag à passer available dans rag_erasure.yaml (12.10) · 3f8f1cd
- 2026-10-25 10:52 · 12.11 · report · code à lancer après le /clear de l'orchestrateur (Opus, effort high) · 3f8f1cd
- 2026-10-25 10:52 · run · décision · Anaël : le poste a 32 Go de RAM (CLAUDE.md dit 16) ; OpenRouter n'expose ni le modèle de décision Jev (seulement typesafe/jev-router) ni Microsoft-Decision-1 : chiffres publiés pour la 12.2 · —
- 2026-10-25 10:53 · 12.19 · dev · fini ; 18 critères, test_rag_sheets 38 verts, 4949 tests ciblés verts, E2E 171/171 avant la dernière fusion puis rag_lab_sheets rag_lab_rights 35/35 (combinaison complète en échec mémoire) ; 12.19b ramenée à 12 fiches (context déjà fiché) · f1cba8b
- 2026-10-25 10:53 · 12.19 · CI · défaut de l'intégration trouvé et corrigé : accolade manquante après #rag-case dans rag.css, styles des stories 6 à 18 ignorés par le navigateur · f1cba8b
- 2026-10-25 10:53 · 12.19 · décision · à revoir : ~400 textes fr/en/de écrits par le dev, graphrag / Droits « high » à trancher, couleur d'encre forcée sur les puces pour le contraste AA, champ before_search · f1cba8b
- 2026-10-25 10:53 · 12.19 · second-avis · lancé · f1cba8b
- 2026-10-25 10:55 · 12.19 · dev · complément : critère 7 sans nombre figé (available == id in PRESETS) · a6b5584
- 2026-10-25 10:55 · run · décision · contrat entre 12.10 et 12.19 : la seconde des deux à entrer dans l'intégration retire story: 10 de long_context et cag dans rag_sheets.yaml ×3 et les passe available: true dans rag_erasure.yaml ×3 · —
- 2026-10-25 10:55 · run · PR · #112 ouverte vers main (CLAUDE.md : 32 Go de RAM, accord d'Anaël) · —
- 2026-10-25 10:57 · 12.10 · review · passe 1 : 1 medium (état CAG inscrit au registre, libéré à chaque purge) et 2 low corrigés (génération arrêtée si le préfixe échoue, message d'erreur juste), probe dans un finally, 5 tests ajoutés ; 2 constats écartés avec motif ; E2E 213/213 · 911399e
- 2026-10-25 10:57 · 12.10 · décision · à revoir : refuser le CAG si _kv_per_token est illisible (le bloc d'intention dit non) ; estimation mémoire prudente (copie du contexte comptée deux fois) · 911399e
- 2026-10-25 10:57 · 12.10 · PR · #113 ouverte vers integration/v1-2-atelier · 911399e
- 2026-10-25 10:57 · 12.2 · décision · Anaël : Jev accessible par la clé OpenRouter via POST https://openrouter.ai/api/alpha/decisions (alpha ; ~typesafe/jev-latest, typesafe/jev-1.13 ; clé lue dans OPENROUTER_API_KEY ou HKCU\Environment, jamais affichée ni écrite ; ~0,00006 $ et 0,25 s par appel, d'après tests-pratiques/T9/resultats.md) ; Jev mesuré en vrai, Microsoft-Decision-1 en chiffres publiés sauf s'il est sur ce point d'accès ; données envoyées : corpus fictif Exemplia et jeu de questions · —
- 2026-10-25 11:00 · run · décision · Anaël : 16 Go = PC cible de WaveStack, les postes de développement varient (celui-ci : 32 Go) ; ligne du CLAUDE.md reformulée sur #112 · —
- 2026-10-25 11:00 · 12.2 · décision · Anaël : banc avec 6 modèles de décision en ligne par OpenRouter /api/alpha/decisions (typesafe/jev-1.14, microsoft/microsoft-decision-1, openai/gpt-6-luna-decisions, perplexity/pplx-decider-flash-v1.2, liquid/d1, inception/mercury-decide:free) + candidats locaux prévus ; clé OpenAI inutile ; modèle à poids ouverts (Kev 4B, Clef Flash) pour une story ultérieure · —
- 2026-10-25 11:02 · 12.10 · CI · verte · 911399e
- 2026-10-25 11:02 · 12.10 · fusion · #113 MERGED dans integration/v1-2-atelier (merge) via file_prs.py ; 12.19 entrera seconde et applique le contrat long_context / cag · 7f24444
- 2026-10-25 11:03 · 12.19 · second-avis · 0 high, 1 medium (règle .rag-badge réactivée par l'accolade corrigée), 5 low ; 43 sources identiques à litterature.md, accolades équilibrées · a6b5584
- 2026-10-25 11:05 · 12.19 · review · lancé (Opus ; fusion de l'intégration et contrat long_context / cag d'abord) · a6b5584
- 2026-10-25 11:05 · 12.11 · dev · phase 2 (code) lancée (Opus, effort high ; fusion de l'intégration d'abord) · 3f8f1cd
- 2026-10-25 11:07 · 12.2 · dev · lancé (phase spec, worktree ../wavestack-v12-s2 depuis l'intégration 7f24444) · 7f24444
- 2026-10-25 11:07 · run · fusion · #112 MERGED dans main (CLAUDE.md, RAM) via file_prs.py · 42b5e37
- 2026-10-25 11:11 · 12.2 · dev · spec prête (10 critères, 8 points ouverts : seuils H7 <= 0,13, ~240 items, 3 répétitions en ligne, ~4 300 appels / ~0,26 $ plafonnés à 2 $, réponses JSONL rejouables, CI sans réseau) · 422dcb5
- 2026-10-25 11:11 · 12.2 · review · relecture de la spec lancée · 422dcb5
- 2026-10-25 11:23 · 12.2 · review · spec approuvée ; jeu réel recompté (21 questions × 3 langues, 27 documents dont 25 actifs) → ~450 items, 2 répétitions en ligne (Jev déterministe dans T9), 5 400 appels plafonnés, rapport identique au rejeu, enregistrement en liste blanche, Strands Decider 2B et AnyJev à vérifier · 8719ce3
- 2026-10-25 11:23 · 12.2 · décision · à revoir : seuils du filtre 0,95 / 0,60 sans source, 2 répétitions en ligne, 0,33 $ par modèle, jeu en 3 langues avec affirmations écrites à la main, passages périmés comptés à part, tranche 3-4 Go à confirmer sur le PC cible, enregistrement en liste blanche · 8719ce3
- 2026-10-25 11:23 · 12.2 · dev · phase 2 (banc, mode à sec, tests sans réseau) lancée ; banc réel non lancé · 8719ce3
- 2026-10-25 11:23 · 12.2 · attente humaine · banc réel : ordre d'Anaël poste libre, clé OpenRouter créditée (limites du modèle :free), GGUF Qwen3.5-2B et reranker, ONNX deberta_xsmall et mdeberta à télécharger une fois ; 25 min à 1 h en ligne, ~1 h en local · —
- 2026-10-25 11:29 · 12.19 · review · passe 1 : intégration fusionnée ; 1 high (contrat 12.10 : rag_sheets.yaml ne se chargeait plus, 22 tests) et 2 medium corrigés (25 fiches en E2E, .rag-badge restreinte à [data-state], 70 règles réactivées comparées sans autre doublon) ; 2 low corrigés, 2 écartés, 1 reporté en 19b ; 475 tests ciblés, E2E 161/161 · b16730e
- 2026-10-25 11:29 · 12.19 · décision · à revoir : validateur de rag/erasure.py assoupli (story de l'architecture facultative), fichier dans la liste Never de la spec · b16730e
- 2026-10-25 11:29 · 12.19 · décision · à revoir : accolade manquante de rag.css aussi sur main (v1.4.0), corrigée à la fusion de la V1.2 · —
- 2026-10-25 11:29 · 12.19 · PR · #114 ouverte vers integration/v1-2-atelier, file_prs.py --methode merge lancé · b16730e
- 2026-10-25 11:29 · 12.2 · décision · Anaël : téléchargement des modèles du banc autorisé ; clé OpenRouter déjà en place (env et HKCU) ; téléchargement des ONNX et du reranker lancé · —
- 2026-10-25 11:37 · 12.19 · CI · verte · b16730e
- 2026-10-25 11:37 · 12.19 · fusion · #114 MERGED dans integration/v1-2-atelier (merge) via file_prs.py ; contrat des fiches transmis à 12.11 (entre seconde) · 5d74aff
- 2026-10-25 11:50 · 12.2 · dev · fini ; banc v12s2_system_one_bench.py (dry-run, online, local, memory), 117 affirmations écrites à la main, jeu de 450 items, 30 tests sans réseau, rapport gabarit « pas encore mesuré » ; critères 6 (H7) et 8 (RSS) ouverts jusqu'au banc réel · 1621e21
- 2026-10-25 11:50 · 12.2 · décision · à revoir : Strands Decider 2B et AnyJev écartés d'office (« carte non lue ») ; verdict mémoire sur le plus grand de l'ensemble de travail et de la mémoire privée ; instructions en 3 langues ; adaptateurs locaux testés seulement en réel · 1621e21
- 2026-10-25 11:50 · 12.2 · second-avis · lancé · 1621e21
- 2026-10-25 11:50 · 12.20 · dev · lancé (phase spec, worktree ../wavestack-v12-s20 depuis l'intégration 5d74aff) · 5d74aff
- 2026-10-25 11:57 · 12.20 · dev · spec prête (16 critères, 12 points ouverts : streamable HTTP monté sur le port de l'application, 2 outils en lecture seule, chaîne figée, jeton porteur par démarrage, dense / hybrid / rerank seuls exposables ; aucune dépendance nouvelle) · 5a11c7c
- 2026-10-25 11:57 · 12.20 · review · relecture de la spec lancée · 5a11c7c
- 2026-10-25 11:59 · 12.2 · second-avis · 0 high, 4 medium (401/402/403 pris pour « modèle inconnu », budget global incomplet à la reprise, corps d'erreur brut hors liste blanche, items tout en erreur sortis des métriques), 3 low ; CI sans dépendance manquante · 1621e21
- 2026-10-25 11:59 · 12.2 · review · lancé (Opus ; fusion de l'intégration, lecture des cartes de Strands Decider 2B et AnyJev) · 1621e21
- 2026-10-25 12:07 · 12.2 · attente humaine · téléchargements à ~20 Ko/s avec coupures vers Hugging Face : reranker bge-reranker-v2-m3 à 36 / 438 Mo (curl en reprise, toujours en cours), ONNX deberta_xsmall et mdeberta non téléchargés ; Qwen3.5-2B présent ; à finir sur un meilleur réseau, puis vérifier taille et sha256 du reranker · —
- 2026-10-25 12:07 · 12.2 · décision · révisions des ONNX non épinglées dans le banc v2s6 (revision vide) : épinglage demandé au reviewer de 12.2 · —
- 2026-10-25 12:18 · 12.20 · review · spec approuvée (D1 à D12) ; 4 défauts corrigés : règle d'exposition (liste blanche des étapes du segment), fuite hr (filtre côté serveur), écritures (index lu seulement, work_copy=None), POST sans Origin refusés (exception /mcp/architecture) ; montage à chaud prouvé sur mcp 2.2.0 · 96e3070
- 2026-10-25 12:18 · 12.20 · décision · à revoir : HTTP seul (stdio reporté) ; pas de ligne « exposé » dans MATRIX_ROWS ; Copilot Studio exige une adresse HTTPS publique non fournie · 96e3070
- 2026-10-25 12:18 · 12.20 · attente humaine · recette : un vrai Claude Code branché par la commande de la carte (citations, aucun passage RH), relecture des descriptions d'outils fr/en/de · —
- 2026-10-25 12:18 · 12.20 · dev · phase 2 (code) lancée (Opus, effort high, story transverse) · 96e3070
- 2026-10-25 12:18 · 12.2 · blocked · téléchargements à 9-22 Ko/s sur tous les hôtes (Hugging Face, GitHub, PyPI) ; deux curl concurrents sur le même fichier, arrêtés, fichier partiel supprimé ; script PowerShell telecharger.ps1 à lancer par Anaël hors de Claude Code · —
- 2026-10-25 12:24 · 12.2 · attente humaine · telecharger.ps1 lancé par Anaël hors de Claude Code : même débit (14-43 Ko/s, ~8 h 25 annoncées pour le reranker), lenteur du réseau du poste et non de l'isolement réseau des commandes · —
- 2026-10-25 12:29 · 12.2 · décision · modèles du banc téléchargés sur données mobiles (~5,7 Mo/s) : reranker bge-reranker-v2-m3 vérifié (taille et sha256), deberta_xsmall 262ae02 et mdeberta b5113eb (révisions transmises au reviewer pour épinglage), Qwen3.5-2B déjà présent · —
- 2026-10-25 12:33 · 12.2 · review · passe 1 : 4 medium corrigés (arrêt sur 401/402/403, budget complet à la reprise, error_summary filtré, items en erreur comptés contre le candidat), 3 low traités, révisions ONNX épinglées ; Strands Decider 2B (port ONNX q8, 31a83e0) et AnyJev (35311c5, L0 content_free sur le SLM) ajoutés ; 301 tests, rejeu identique à l'octet · e91bdca
- 2026-10-25 12:33 · 12.2 · décision · à revoir : Strands en q8 hobson v19 (seul port ONNX, q4f16 en repli) ; AnyJev en L0 content_free ; item toujours en erreur compté contre le candidat ; pas de filtre par défaut sans mesure du reranker · e91bdca
- 2026-10-25 12:33 · 12.2 · PR · #115 ouverte vers integration/v1-2-atelier, file_prs.py --methode merge lancé · e91bdca
- 2026-10-25 12:33 · 12.2 · décision · Anaël : profiter du réseau rapide ; snapshot Strands (~1,8 Go) et paquets du banc local (onnxruntime, tokenizers, AnyJev) mis en cache · —
- 2026-10-25 12:38 · 12.2 · CI · verte · e91bdca
- 2026-10-25 12:38 · 12.2 · fusion · #115 MERGED dans integration/v1-2-atelier (merge) via file_prs.py ; banc réel encore à lancer (critères 6 et 8 ouverts), story gardée in-progress · 30bbfc1
- 2026-10-25 12:38 · 12.2 · attente humaine · ordre d'Anaël pour la partie en ligne (possible avec agents en cours) ; partie locale et mémoire quand le poste est libre · —
- 2026-10-25 12:40 · 12.2 · décision · snapshot Strands 31a83e0 téléchargé (onnx_data 1,80 Go) et paquets du banc local en cache (onnxruntime 1.31.0, tokenizers 0.23.3, AnyJev 35311c5) ; le banc réel n'a plus besoin du réseau que pour OpenRouter · —
- 2026-10-25 12:42 · 12.2 · décision · Anaël : partie en ligne du banc lancée (6 modèles, ~5 400 appels, plafonds 2 $ / 6 000 appels / 0,33 $ par modèle), agents en cours sur le poste · e91bdca
- 2026-10-25 12:42 · 12.11 · dev · fini ; critères 1 à 21 (21 vérifié par capture seulement), contrat 12.19 appliqué (27 entrées), E2E 6 scénarios 189/189 avant la dernière fusion · 8b0342b
- 2026-10-25 12:42 · 12.11 · décision · à revoir : boucle et descente sur le generator existant (model_scope, réserve 128) ; lignes de séquence « Tool calls » / « Tree descent » en anglais ×3 (test_i18n) ; grep et list_files comme éléments du contexte ; borne de 400 tokens par résultat (~1 600 caractères) ; « Arrêter » la reconstruction n'écrit rien ; CHOICE: NONE profond = no_node_chosen · 8b0342b
- 2026-10-25 12:42 · 12.11 · attente humaine · done_checkpoint avec un vrai modèle sur le PC cible : protocole ACTION:, tours, plafonds, réponses illisibles, descente avant / après « Reconstruire », durées, rendu fr/en/de · —
- 2026-10-25 12:42 · 12.11 · second-avis · lancé · 8b0342b
- 2026-10-25 12:42 · 12.19b · dev · lancé (spec puis code, pas de spec_checkpoint, worktree ../wavestack-v12-s19b depuis l'intégration 30bbfc1) · 30bbfc1
- 2026-10-25 12:48 · 12.11 · second-avis · 0 high, 0 medium, 3 low (search_documents lit le corpus avant de valider la requête, audience hr lisible par l'agent comme par search_documents, entrées de documents supprimés gardées dans l'arbre reconstruit), 1 info ; confinement, bornes, annulation et contrat 12.19 sans défaut · 8b0342b
- 2026-10-25 12:48 · 12.11 · review · lancé (Opus ; règle hr à trancher en cohérence avec 12.18 et 12.20) · 8b0342b
- 2026-10-25 12:53 · 12.19b · dev · fini ; 12 fiches ×3 (H1, H14, H10 ; Sentence-BERT, DPR et fastembed pour les embeddings), PENDING_SHEET_KINDS vide, rag.sheets_error affiché, compte de l'E2E lu sur l'API ; 439 tests ciblés, E2E 172/172 · 347db6d
- 2026-10-25 12:53 · 12.19b · décision · à revoir : 4 vector stores dits exacts (sqlite-vec non vérifié dans le code) ; sources des embeddings hors litterature.md (hypothèse à y ajouter) ; H1 mesure l'hybride en bloc ; generation.not_run cite H10 · 347db6d
- 2026-10-25 12:53 · 12.19b · attente humaine · relecture des 12 fiches fr/en/de (FAISS « Meta », LanceDB, sqlite-vec, fastembed, lecture de H14) · —
- 2026-10-25 12:53 · 12.19b · second-avis · lancé · 347db6d
- 2026-10-25 12:54 · 12.13 · dev · lancé (phase spec, empilé sur 12.11, worktree ../wavestack-v12-s13) · 8b0342b
- 2026-10-25 12:57 · 12.19b · second-avis · 0 high, 0 medium, 6 low (fastembed sans consigne d'installation, échec de load() non testé, missing_sheets au niveau des familles, conflit 12.11 attendu, chiffres Sentence-BERT et DPR à revérifier, « même classement » trop fort) ; vector stores exacts confirmés dans le code · 347db6d
- 2026-10-25 12:57 · 12.19b · review · lancé (Opus) · 347db6d
- 2026-10-25 12:59 · 12.13 · dev · spec prête (20 critères, D1 à D10 : graphe livré heuristique sans modèle, propagation d'étiquettes maison sans networkx, préréglage graphrag local / global, coût du graphe livré nul et estimation étiquetée, audience hr par preuve) · 3ef995c
- 2026-10-25 12:59 · 12.13 · review · relecture de la spec lancée (règles hr et d'exposition MCP à aligner sur 12.11 et 12.20) · 3ef995c
- 2026-10-25 12:59 · 12.11 · review · passe 1 : 2 low corrigés (search_documents lit à la demande, pageindex.forget retire un document supprimé de l'arbre reconstruit), 2 écartés (filtre hr, test du lien) ; 548 tests ciblés, E2E 189/189 · ec11ca5
- 2026-10-25 12:59 · 12.11 · décision · à revoir : aucune architecture de l'atelier ne filtre l'audience hr (la carte d'accès de 12.18 montre la fuite) ; seul le MCP exposé de 12.20 filtre ; règle transmise à la relecture de 12.13 · ec11ca5
- 2026-10-25 12:59 · 12.11 · PR · #116 ouverte vers integration/v1-2-atelier, file_prs.py --methode merge lancé · ec11ca5
- 2026-10-25 13:03 · 12.19b · review · passe 1 : 1 Important low corrigé (panne de /api/rag_lab/sheets testée en E2E), 2 low corrigés (fastembed renvoie au guide, « aux égalités et arrondis près »), 2 écartés (contrôle des options déjà au chargement, chiffres Sentence-BERT et DPR relus exacts), 1 reporté (conflit 12.11) ; 371 tests, E2E 166/166 · 6b00d2c
- 2026-10-25 13:03 · 12.19b · décision · pas de passe 2 : seul constat Important = un test ajouté, de gravité low · 6b00d2c
- 2026-10-25 13:03 · 12.19b · report · PR après la fusion de #116 (12.11) et refusion de l'intégration (rag_lab.yaml ×3) · 6b00d2c
- 2026-10-25 13:06 · 12.11 · CI · verte · ec11ca5
- 2026-10-25 13:06 · 12.11 · fusion · #116 MERGED dans integration/v1-2-atelier (merge) via file_prs.py ; 12.20 prévenue (agentic et pageindex dans PRESETS) · cc3ec10
- 2026-10-25 13:06 · 12.19b · dev · refusion de l'intégration (avec 12.11) lancée avant la PR · 6b00d2c
- 2026-10-25 13:09 · 12.13 · review · spec approuvée après 2 défauts bloquants mesurés sur le corpus (règle d'entités : 25 à 31 entités sans relations ; propagation d'étiquettes : une communauté à 77-94 %) ; entités tf-idf + codes (116 à 128), Louvain phase 1 maison (15 à 17 communautés, la plus grande à 14-17 %), aucun filtre hr, exposition MCP selon 12.20 · 0cdc471
- 2026-10-25 13:09 · 12.13 · décision · à revoir : D1 graphe heuristique livré, D2 sans networkx, D5 construction du graphe livré moins chère que dense (surcoût prouvé sur graphe reconstruit), D7 pas de filtre hr (décision transverse) · 0cdc471
- 2026-10-25 13:09 · 12.13 · attente humaine · done_checkpoint : reconstruction du graphe avec un vrai modèle sur le PC cible (durée, tokens, graph_passages_fallback), local et global contre l'hybride, coût dans Comparer · —
- 2026-10-25 13:09 · 12.13 · dev · phase 2 (code) lancée (Opus, effort high ; fusion de l'intégration avec 12.11 d'abord) · 0cdc471
- 2026-10-25 13:09 · run · décision · Anaël : 3 créneaux de développement, le 3e seulement pour une story sans fichier commun avec les deux en cours · —
- 2026-10-25 13:10 · 12.19b · dev · intégration fusionnée (avec 12.11) : ui.yaml ×3 deux côtés gardés, compte de rag_lab_sheets lu sur l'API ; 390 tests, E2E 166/166 · 10106d8
- 2026-10-25 13:10 · 12.19b · PR · #117 ouverte vers integration/v1-2-atelier, file_prs.py --methode merge lancé · 10106d8
- 2026-10-25 13:14 · 12.20 · dev · fini ; critères 1 à 16 (12 et 6 vérifiés hors test dédié, 15 par la CI), test_rag_mcp 38 verts, E2E rag rag_rerank rag_lab_mcp rag_lab_sheets 96/96, agentic et pageindex refusés (searches_itself) · eda9fc8
- 2026-10-25 13:14 · 12.20 · décision · à revoir : copie de travail non vide = démarrage refusé ; argument profile en trop ignoré par le SDK ; « Arrêter » annule aussi un appel MCP ; matrix_row_of("workshop__…") renvoie network (à trancher avec la ligne « exposé ») · eda9fc8
- 2026-10-25 13:14 · 12.20 · second-avis · lancé (jeton, exception du middleware, filtre hr, cycle de vie) · eda9fc8
- 2026-10-25 13:14 · 12.14 · dev · lancé (spec puis code, pas de spec_checkpoint ; Opus, effort high ; worktree ../wavestack-v12-s14 depuis l'intégration cc3ec10 ; même schéma que 12.11 et 12.13) · cc3ec10
- 2026-10-25 13:17 · 12.19b · CI · verte · 10106d8
- 2026-10-25 13:17 · 12.19b · fusion · #117 MERGED dans integration/v1-2-atelier (merge) via file_prs.py ; 12.13 et 12.14 prévenues (fiche obligatoire pour chaque option) · 99e71ac
- 2026-10-25 13:19 · 12.20 · second-avis · 0 high, 1 medium (« Arrêter » n'annule pas l'appel MCP en cours), 5 low (déconnexion du client non traitée, langue du contenu, compte des passages RH retirés exposé au client, ligne network de la matrice, échec de serve() non signalé) ; middleware, jeton, filtre hr sans défaut · eda9fc8
- 2026-10-25 13:19 · 12.20 · review · lancé (Opus ; fusion de l'intégration avec 12.19b d'abord) · eda9fc8
- 2026-10-25 13:29 · 12.20 · review · passe 1 : intégration fusionnée (12.19b) ; 1 medium (arrêt qui annule l'appel en cours, testé) et 2 low corrigés (CancelledError journalisée, échec de démarrage remis à zéro), 2 écartés (langue, compte RH exigé par la spec), 1 figé par test (ligne network) ; 40 tests test_rag_mcp, E2E 98/98 · 914cdcd
- 2026-10-25 13:29 · 12.20 · décision · à revoir : compte des passages RH retirés dans la réponse au client (le garder au seul journal local ?), outils exposés dans la ligne « réseau » de la matrice en attendant la ligne « exposé » · 914cdcd
- 2026-10-25 13:29 · 12.20 · PR · #118 ouverte vers integration/v1-2-atelier, file_prs.py --methode merge lancé · 914cdcd
- 2026-10-25 13:35 · 12.2 · décision · Anaël : créneau sans agent réservé pour la partie locale et la mémoire du banc, après les dev de 12.13 et 12.14 et la fin de la partie en ligne ; revues de 12.13 et 12.14 ensuite · —
- 2026-10-25 13:36 · 12.20 · CI · verte · 914cdcd
- 2026-10-25 13:36 · 12.20 · fusion · #118 MERGED dans integration/v1-2-atelier (merge) via file_prs.py ; 12.13 et 12.14 prévenues · 820d109
- 2026-10-25 13:44 · run · décision · Anaël absent quelques heures : run en autonomie ; banc local et mémoire de 12.2 lancés sans attendre son accord dès que le poste est libre (Ollama fermé, applications fermées), puis reprise des développements · —
- 2026-10-25 13:44 · run · décision · Anaël : une décision ou une ressource qui lui revient ne bloque que les stories qui en dépendent ; les autres développements continuent (attente humaine journalisée, choix provisoire marqué « à revoir » si besoin) · —
- 2026-10-25 13:53 · 12.2 · dev · banc en ligne fini (12:41 → 13:53) : 5 403 appels, 0,076 $ dépensés (plafond 2 $), 6 modèles complets (~900 appels chacun, gpt-6-luna 0,036 $, jev-1.14 0,021 $) ; résultats dans tools/bench/results/2026-10-25-v12s2 · e91bdca
- 2026-10-25 14:01 · 12.14 · dev · fini ; 8 critères, wiki livré par règle (fr 67 pages, 368 liens, 108 Ko ; en et de proches), lint 6 types, requête en un appel sur l'index (4,7 Ko), forget, coûts estimés, MCP refusé ; 626 tests ciblés, E2E 85/85 et 179/179 ; intégration fusionnée (12.19b, 12.20) · 538aa5d
- 2026-10-25 14:01 · 12.14 · décision · à revoir : 10 points dans la spec (synthèses seules par le modèle, concepts tf-idf bruités, index sans synthèses des concepts pour tenir dans 8 192, lint sans contradictions, construction moins chère que dense avec le wiki livré, aucun filtre hr, Karpathy cité sans lien) · 538aa5d
- 2026-10-25 14:01 · 12.14 · attente humaine · recette avec un vrai modèle (protocole PAGES:, « Recompiler le wiki », ajout / modification / suppression, Comparer, effacement, fiche, rendu fr/en/de clair et sombre) · —
- 2026-10-25 14:01 · 12.14 · report · second avis et revue après le banc local de 12.2 (créneau sans agent) · 538aa5d
- 2026-10-25 14:05 · 12.13 · dev · fini ; 20 critères, graphe livré fr 129 entités / 826 relations / 13 communautés (la plus grande 16 %, 135 Ko), en et de proches, construction ~40 ms ; tests ciblés verts, E2E 86/86 et 168/168 ; intégration fusionnée (12.19b, 12.20) · 6bb7616
- 2026-10-25 14:05 · 12.13 · décision · à revoir : points a à j du Spec Change Log (lignes « Graph building » / « Graph query » en anglais ×3, vocabulaire gelé recalculé, fichier reconstruit limité aux sorties du modèle, forget à chaque copie gardée, lien LightRAG arXiv 2410.05779 non vérifié, RagLabRunIntention refuse les champs inconnus) · 6bb7616
- 2026-10-25 14:05 · 12.13 · attente humaine · recette avec un vrai modèle (« Reconstruire le graphe », local et global contre l'hybride, surcoût dans Comparer, rendu fr/en/de clair et sombre) · —
- 2026-10-25 14:05 · 12.2 · dev · banc local lancé sur poste libre (19,4 Go libres, CPU 0 %, aucun agent), puis memory et dry-run à la suite · e91bdca
- 2026-10-25 14:36 · 12.2 · dev · banc local fini (14:05 → 14:34) ; filtre : reranker livré par défaut, PPLX Decider Flash 1.2 en option cloud ; ancrage : deberta_xsmall par défaut (H7 9 %), Jev 1.14 en option cloud (H7 0 %) ; mémoire : pic 2 767 Mo à 16 384 tokens, hypothèse des 4 Go confirmée ; résultats commités sur feat/v1-2-story-2-banc-resultats · 43ec7c1
- 2026-10-25 14:36 · 12.2 · blocked · SLM juge en échec sur 100 % des items (logprobs demandés sur un Llama sans logits_all=True, défaut du banc) ; Strands Decider 2B écarté (opérateur ONNX com.microsoft:CausalConvWithState absent d'onnxruntime 1.31.0) ; correctif lancé, remesure du juge seule sur poste libre ensuite · 43ec7c1
- 2026-10-25 14:36 · 12.13 · second-avis · lancé (lecture seule, sans E2E) · 6bb7616
- 2026-10-25 14:36 · 12.14 · second-avis · lancé (lecture seule, sans E2E) · 538aa5d
- 2026-10-25 14:39 · 12.2 · dev · SLM juge corrigé (probabilité lue sur les logits du jeton contraint par GBNF, sans logits_all, comme LlamaCppEngine._candidates ; appel réel P(oui) 0,919) ; reprise qui remesure un candidat tout en erreur ; Strands reste écarté (CausalConvWithState sans noyau CPU fp16 dans onnxruntime ≤ 1.31.0) ; remesure du juge seule après les seconds avis en cours · 7ff9e29
- 2026-10-25 14:41 · 12.13 · second-avis · 1 high (erreur du modèle prise pour une réponse illisible à « Reconstruire » : fin ok, fichier llm écrasé sans extraction), 3 medium (garde-fous des communautés seulement en test, forget sans retour à chaque copie gardée, 85 marqueurs de conflit sur 23 fichiers avec 12.14), 4 low ; clients de RagLabRunIntention strict vérifiés sans casse · 6bb7616
- 2026-10-25 14:41 · run · décision · 12.13 et 12.14 en conflit lourd (lab.py, erasure.py, app_session.py, app.py, catalog.py, rag.css, rag.html, content ×3) : 12.13 entre la première, la revue de 12.14 refusionne l'intégration après elle et garde les deux ajouts · —
- 2026-10-25 14:41 · 12.14 · second-avis · 2 high (wiki livré à 0 token contre « coûte plus à toutes les étapes » d'architectures.md et des fiches, décision d'Anaël ; forget seulement si le Contexte est wiki_pages et après le contrôle d'annulation), 2 medium (anciennes pages d'un document modifié jamais purgées, conflits avec 12.13), 2 low · 538aa5d
- 2026-10-25 14:41 · 12.2 · dev · remesure du SLM juge seule sur poste libre (aucun agent), puis dry-run · 7ff9e29
- 2026-10-25 14:53 · 12.2 · dev · SLM juge remesuré seul (14:41 → 14:52), 470 enregistrements sans erreur : filtre AUC 0,86, 49 % de négatifs écartés ; ancrage H7 64 % ; ni défaut ni repli · 61cf5a5
- 2026-10-25 14:53 · 12.2 · décision · à revoir : la cascade vers le SLM juge de CAP-6 n'est pas viable avec Qwen3.5-2B (H7 64 %) ; 12.8 part sans repli SLM ou avec un repli signalé « non validé » · 61cf5a5
- 2026-10-25 14:53 · 12.2 · PR · #119 ouverte vers integration/v1-2-atelier (résultats du banc et correctif du juge), file_prs.py --methode merge lancé · 61cf5a5
- 2026-10-25 14:53 · 12.13 · review · lancé (Opus ; 12.13 entre avant 12.14) · 6bb7616
- 2026-10-25 14:53 · 12.8 · report · dev lancé après la fusion de #119 (rapport du banc dans l'intégration) · —
- 2026-10-25 15:00 · 12.2 · CI · verte · 61cf5a5
- 2026-10-25 15:00 · 12.2 · fusion · #119 MERGED dans integration/v1-2-atelier (merge) via file_prs.py ; banc réel complet, critères 6 et 8 mesurés · 132bbf3
- 2026-10-25 15:00 · 12.2 · attente humaine · done_checkpoint : relire le rapport du banc (seuils du filtre sans source, H7 sur un seul article, Strands écarté, SLM juge non viable) · —
- 2026-10-25 15:00 · 12.8 · dev · lancé (spec puis code, pas de spec_checkpoint ; Opus, effort high ; worktree ../wavestack-v12-s8 depuis l'intégration 132bbf3 ; cascade SLM juge en option « non validée », désactivée par défaut) · 132bbf3
- 2026-10-25 15:18 · 12.13 · review · passe 1 : high corrigé (modèle en erreur = StageFailed sans écriture, reconstruction illisible n'écrit rien), 1 medium (part extraite par le modèle affichée) et 2 low corrigés (ENTITY: NONE, verrou du cache), 4 écartés avec motif ; lien LightRAG vérifié ; tests ciblés verts, E2E 165/165 · 5979b68
- 2026-10-25 15:18 · 12.13 · PR · #120 ouverte vers integration/v1-2-atelier, file_prs.py --methode merge lancé · 5979b68
- 2026-10-25 15:18 · 12.8 · décision · diagnostics Pyright sur config.py (str passé pour Message, l. 1000-1053) à faire vérifier par le second avis de 12.8 · —
- 2026-10-25 15:36 · 12.13 · CI · rouge (Windows et Ubuntu groupe 4) : test_ui_texts, guillemets français « » dans rag.graph_title_global et rag.graph_map_answer en et de ; corrigé (“ ” et „ “), test_ui_texts et test_i18n verts, file_prs.py relancé · fad7fbe
- 2026-10-25 15:36 · run · décision · ajouter tests/test_ui_texts.py aux tests ciblés de toute story qui ajoute des textes (12.14, 12.8) · —
- 2026-10-25 15:42 · 12.13 · CI · verte après correctif · fad7fbe
- 2026-10-25 15:42 · 12.13 · fusion · #120 MERGED dans integration/v1-2-atelier (merge) via file_prs.py ; 12.8 prévenue · 1db4ec2
- 2026-10-25 15:42 · 12.14 · review · lancé (Opus ; refusion lourde avec 12.13 d'abord, test_ui_texts ajouté) · 538aa5d
- 2026-10-25 15:51 · 12.8 · dev · fini ; critères CAP-6 couverts (auteur, probabilité, seuil ; cascade qui change l'auteur ; cloud grisé sans clé testé), deberta_xsmall déclaré dans wavestack.toml (262ae02f) avec extra decision, API OpenRouter choice / score / noul, 6 fiches ×3, MCP refusé (model_stage) ; 556 tests ciblés, E2E 162/162 ; intégration fusionnée (12.13) · 76f6a095
- 2026-10-25 15:51 · 12.8 · décision · à revoir : 10 points de la spec (cascade désactivée « non validée », sens du seuil du banc contre la maquette, seuil du routeur 50 % non mesuré, routeur limité à dense / hybride / rerank, PPLX filtre et Jev routeur et ancrage, choice et score jamais appelés en réel, openrouter.ai dans [net] allowed_hosts, juge sans grammaire) · 76f6a095
- 2026-10-25 15:51 · 12.8 · attente humaine · recette : extra decision, téléchargement du classifieur, routeur et Grounding check en local ; un vrai appel cloud (forme choice, coût, plafond) · —
- 2026-10-25 15:51 · run · blocked · E2E rag_lab_context cassé sur l'intégration depuis 12.11 (attend 6 options de contexte, 8 aujourd'hui) ; hors CI ; à corriger par la revue de 12.8 · —
- 2026-10-25 15:51 · 12.8 · second-avis · lancé (défaut cloud de la palette, allowed_hosts, extra decision, diagnostics config.py) · 76f6a095
- 2026-10-25 15:51 · 12.12 · dev · lancé (spec puis code, pas de spec_checkpoint ; Opus, effort high ; empilé sur 12.8, worktree ../wavestack-v12-s12) · 76f6a095
- 2026-10-25 15:55 · 12.8 · second-avis · 2 high (option cloud choisie par défaut quand le local manque et que la clé est là ; plafond de session aveugle si usage.cost manque), 3 medium (openrouter.ai ouvert à tout client par [net] allowed_hosts ; avertissement 64 % mesuré sur un autre juge ; E2E rag_lab_context préexistant à 9 options), 2 low ; clé, seuil, hashes, extra et MCP sans défaut · 76f6a095
- 2026-10-25 15:55 · 12.8 · review · lancé (Opus ; correctif de l'E2E rag_lab_context inclus) · 76f6a095
- 2026-10-25 16:10 · 12.8 · review · passe 1 : 2 high corrigés (cloud jamais par défaut ; client de DecisionApi par net.factory, AD-15), 2 medium corrigés (test_rag_lab_query réaligné, textes de la cascade honnêtes ×3), E2E rag_lab_context à 9 options ; 3 écartés (coût absent compté 0 comme au banc, allowed_hosts global, coûts d'étape en échec) ; E2E 163/163 et 83/83 · 5285a128
- 2026-10-25 16:10 · 12.8 · décision · à revoir : plafond de session aveugle si l'API omet usage.cost (le banc l'a toujours eu sur les modèles payants) ; openrouter.ai dans [net] allowed_hosts pour toute l'application ; juge de la cascade non mesuré · 5285a128
- 2026-10-25 16:10 · 12.8 · PR · #121 ouverte vers integration/v1-2-atelier, file_prs.py --methode merge lancé ; 12.12 prévenue · 5285a128
- 2026-10-25 16:12 · 12.14 · review · passe 1 : intégration fusionnée (12.13, 22 fichiers en conflit, deux côtés gardés, structure = pageindex, graphrag, llm_wiki) ; 2 high corrigés (fiche honnête sur le coût du wiki livré, forget à chaque copie gardée), 1 medium corrigé (anciennes pages d'un document modifié), 1 low corrigé en partie, 2 écartés ; capture renumérotée 89 ; E2E 164/164 et 86/86 · e3e734b2
- 2026-10-25 16:12 · 12.14 · report · PR après la fusion de #121 (12.8) et refusion de l'intégration · e3e734b2
- 2026-10-25 16:19 · 12.8 · CI · verte · 5285a128
- 2026-10-25 16:19 · 12.8 · fusion · #121 MERGED dans integration/v1-2-atelier (merge) via file_prs.py ; 12.12 prévenue · 2b0a49e
- 2026-10-25 16:19 · 12.14 · dev · refusion de l'intégration (avec 12.8) lancée avant la PR · e3e734b2
- 2026-10-25 16:26 · 12.14 · dev · intégration fusionnée (avec 12.8) sans conflit ; 648 tests ciblés, E2E 164/164 et 92/92 · 5be654fe
- 2026-10-25 16:26 · 12.14 · PR · #122 ouverte vers integration/v1-2-atelier, file_prs.py --methode merge lancé · 5be654fe
- 2026-10-25 16:33 · 12.14 · CI · verte · 5be654fe
- 2026-10-25 16:33 · 12.14 · fusion · #122 MERGED dans integration/v1-2-atelier (merge) via file_prs.py ; 12.12 prévenue · 3525323
- 2026-10-25 16:33 · 12.16 · dev · lancé (spec puis code, pas de spec_checkpoint ; Opus, effort high ; worktree ../wavestack-v12-s16 depuis l'intégration 3525323) · 3525323
- 2026-10-25 16:57 · 12.12 · dev · fini ; RAPTOR (arbre livré par règle : fr 73 passages, 27 résumés sur 3 niveaux, 23 Ko ; ~60 ms) et CRAG (hybride, passage_filter de 12.8, étape fallback retry / abstain, sans recherche web) ; critères 1 à 10, MCP refusé, raptor_summaries mesuré, sources RAPTOR 2401.18059 et CRAG 2401.15884 ajoutées à litterature.md ; E2E 87/87, 175/175, 109/109 ; intégration fusionnée (12.8, 12.14) · 16043c36
- 2026-10-25 16:57 · 12.12 · décision · à revoir : D1 arbre par règle, D2 vecteurs de mots et BM25 au lieu des embeddings d'architectures.md, D3 résumé extractif qui privilégie les codes, D5 CRAG limité au cas « rien gardé », D6 pas de recherche web, D9 ordre des familles envoyé par le catalogue · 16043c36
- 2026-10-25 16:57 · 12.12 · attente humaine · recette : « Reconstruire l'arbre » avec un vrai modèle, RAPTOR sur q_global_rh contre l'hybride, CRAG sur q_noanswer_* · —
- 2026-10-25 16:57 · 12.12 · second-avis · lancé · 16043c36
- 2026-10-25 16:59 · 12.16 · dev · fini ; parent_step générique (hérité par RAPTOR / CRAG), arbre course / étapes / sous-étapes / appels dans Construire, export OTLP/HTTP GenAI (invoke_workflow, chat, retrieval ; semconv-genai 9ffc7e0, v1.44.0) derrière l'extra otel 1.44.0, par la fabrique, rien ne sort sans [otel] endpoint ni texte sans capture_content ; test_rag_lab_otel 10 (3 sautés en CI sans l'extra), E2E 157/157 · 219eb637
- 2026-10-25 16:59 · 12.16 · décision · à revoir : export à la demande par bouton ; SDK + encodeur au lieu de l'exporteur HTTP de brownfield.md ; [otel] auth_env ; redémarrage pour changer d'URL ; extra à 1.44.0 (pas 1.45.1) pour ne pas relever opentelemetry-api ; tests d'export hors CI · 219eb637
- 2026-10-25 16:59 · 12.16 · attente humaine · recette : uv sync --extra otel, Phoenix ou Langfuse, [otel] endpoint, « Exporter cette exécution » ; capture_content · —
- 2026-10-25 16:59 · 12.16 · second-avis · lancé · 219eb637
- 2026-10-25 16:59 · 12.21 · dev · lancé (spec et script de mesure seulement, ni téléchargement ni mesure ; worktree ../wavestack-v12-s21) ; mesure plus tard sur poste libre · 3525323
- 2026-10-25 17:02 · 12.12 · second-avis · 1 high (erreur du modèle à la mise à jour RAPTOR : fichier réécrit, run ok), 1 medium (second essai et fallback de CRAG hors du moteur d'étapes, invisibles pour l'arbre de 12.16), 5 low · 16043c36
- 2026-10-25 17:02 · 12.12 · review · lancé (Opus ; parties du fallback émises en run.sN.<partie> pour 12.16 ; 12.12 entre avant 12.16) · 16043c36
- 2026-10-25 17:04 · 12.16 · second-avis · 0 high, 3 medium ([otel] auth_env accepte OPENROUTER_API_KEY et l'enverrait au collecteur ; tests d'export jamais joués en CI ; tokens de l'étape comptés deux fois), 7 low ; défaut sûr, masquage d'Authorization et textContent vérifiés · 219eb637
- 2026-10-25 17:04 · 12.16 · review · lancé (Opus ; refusion après l'entrée de 12.12) · 219eb637
- 2026-10-25 17:09 · 12.21 · dev · spec, banc v12s21_visual_search_bench.py et rapport gabarit livrés (mesure non lancée) ; candidats colpali_v13_fp16 (Qdrant, fastembed / onnxruntime, ~5,9 Go, licence Gemma) et colsmol_256m_onnx (onnx-community, 954 Mo, MIT) ; ColQwen2.5, ColSmol-500M, ColPali torch, ColNomic, GGUF écartés avec motif ; 23 tests · e647ad10
- 2026-10-25 17:09 · 12.21 · décision · à revoir : seuils (pic ≤ 4 096 Mo, indexation ≤ 15 s par page, requête ≤ 3 s, rappel@3 ≥ 0,75) sans source sauf le budget ; corpus fr seul ; licence Gemma de ColPali ; ColQwen2.5 écarté faute de voie sans torch · e647ad10
- 2026-10-25 17:09 · 12.21 · attente humaine · accord d'Anaël pour télécharger ~6,9 Go (ou ColSmol seul ~1 Go) : réseau peut-être sur données mobiles ; mesure ~20-30 min sur poste libre ensuite ; notification envoyée · —
- 2026-10-25 17:09 · run · décision · dossier parasite C:\c\Users\… (2 Mo, fichiers de plusieurs sessions et projets, dont p0.png de 12.21) laissé en place, à supprimer par Anaël s'il le souhaite · —
- 2026-10-25 17:16 · 12.21 · décision · Anaël : téléchargement des 6,9 Go accordé, sur le WiFi actuel (~3,5 Mo/s mesuré ; données mobiles en repli si besoin) ; téléchargement lancé · e647ad10
- 2026-10-25 17:16 · 12.16 · review · passe 1 : 3 medium corrigés (auth_env refuse les clés cloud et tout …_API_KEY ; tests d'export en CI avec --extra otel et test hors boucle locale ; tokens d'étape sous wavestack.rag_lab.usage.*), 6 low corrigés (dont corps protobuf non journalisé, URL sans requête), 1 écarté ; 13 tests otel, E2E 157/157 · 7e97f4c9
- 2026-10-25 17:16 · 12.16 · décision · à revoir : hôte du collecteur autorisé pour tous les clients de la fabrique (comme un hôte cloud) ; surcoût de CI de --extra otel à relever sur la CI de la PR · 7e97f4c9
- 2026-10-25 17:16 · 12.16 · report · PR après la fusion de 12.12 et refusion de l'intégration · 7e97f4c9
- 2026-10-25 17:18 · 12.12 · review · passe 1 : high corrigé (erreur du modèle à la mise à jour RAPTOR = StageFailed, rien d'écrit), medium corrigé (parties du repli en run.sN.rewrite / run.sN.retry_<kind> / run.sN.abstain avec leurs coûts), 4 low corrigés (dont coûts d'une mise à jour annulée perdus, préexistant), 1 écarté ; sources arXiv vérifiées ; 705 tests, E2E 87/87 et 163/163 · 4b3729a4
- 2026-10-25 17:18 · 13 · report · préexistant 12.13 : _update_graph écrit avant la copie gardée et garde des extractions partielles si le modèle échoue ; petit correctif à part après 12.16 · —
- 2026-10-25 17:18 · 12.12 · PR · #123 ouverte vers integration/v1-2-atelier, file_prs.py --methode merge lancé · 4b3729a4
- 2026-10-25 17:21 · run · décision · Anaël : l'onglet « Diagnostic » devient « Modèles » ; changement lancé sur feat/v1-2-onglet-modeles vers l'intégration (worktree ../wavestack-v12-modeles) · 3525323
- 2026-10-25 17:21 · run · décision · à revoir : 🛠️ gardé ; titre de page « Modèles » ; adresse /diagnostic et clés inchangées ; textes qui renvoient à la page alignés, « diagnostic » gardé quand il désigne une vérification ; captures non régénérées sauf celles qui vérifient le libellé · —
- 2026-10-25 17:21 · run · décision · Anaël : à la fin de l'epic 12, refaire README.md et la démo (wavestack-demo.gif et .mp4, tools/demo/compose.py), l'interface ayant changé sur trois epics ; ajouté aux étapes de fin de lot · —
- 2026-10-25 17:22 · 12.21 · dev · modèles téléchargés sur le WiFi (17:16 → 17:22) : colpali_v13_fp16 ok, colsmol_256m_onnx ok ; mesure seule sur poste libre après le renommage de l'onglet, avant la refusion de 12.16 · e647ad10
- 2026-10-25 17:26 · run · dev · onglet « Modèles » fait (libellés, titres, renvois ×3, 6 pages HTML, docs, tests et E2E model_catalog) ; 5 727 tests ciblés, E2E 102/102 ; second avis lancé (lecture seule) · 3c1beb5e
- 2026-10-25 17:26 · 12.21 · dev · mesure lancée seule (18,6 Go libres, CPU 0 %) · e647ad10
- 2026-10-25 17:31 · 12.12 · CI · verte · 4b3729a4
- 2026-10-25 17:31 · 12.12 · fusion · #123 MERGED dans integration/v1-2-atelier (merge) via file_prs.py · 8a611a8
- 2026-10-25 17:31 · run · PR · onglet Modèles : second avis 4 oublis corrigés (menu Volets, docs, cahier de recette), 264 tests verts ; #124 ouverte vers l'intégration, file_prs.py lancé · fc55e52d
- 2026-10-25 17:31 · 12.21 · dev · mesure faite (17:26 → 17:28) : ne tient pas ; ColPali arrêté au plafond de sécurité (18 750 Mo), ColSmol-256M pic 6 130 Mo et requêtes refusées par le graphe ONNX (entrée de requête du banc à vérifier) ; résultats et rapport commités · 78ca191c
- 2026-10-25 17:31 · 12.21 · second-avis · lancé (lecture seule) · 78ca191c
- 2026-10-25 17:31 · 12.16 · dev · refusion de l'intégration (avec 12.12) lancée, test des parties du repli CRAG dans l'arbre · 7e97f4c9
- 2026-10-25 17:31 · 13 · dev · correctif de _update_graph lancé (schéma de _update_raptor : StageFailed, écriture après la copie gardée), branche fix/v1-2-mise-a-jour-du-graphe · 8a611a8
- 2026-10-25 17:32 · run · CI · #124 en conflit après #123 (captures 01 et 01b) ; intégration fusionnée, captures de la page Modèles gardées ; test_web_app rouge en local seulement (rag.html réécrit en CRLF par la fusion dans la copie de travail, index en LF), tests verts après normalisation ; file_prs.py relancé · d392e25a
- 2026-10-25 17:34 · 12.21 · second-avis · 1 high (test du rapport compare au gabarit, rouge), 5 medium (deferred-work non mis à jour ; « pic 6 130 Mo » = mémoire validée, RAM 3 996 Mo sous 4 096 ; requête ColSmol probablement mal construite par le banc ; chiffres extrapolés présentés comme mesurés), 3 low · 78ca191c
- 2026-10-25 17:34 · 12.21 · review · lancé (Opus ; correctif de l'entrée de requête, pas de mesure) ; remesure de ColSmol seul sur poste libre ensuite · 78ca191c
- 2026-10-25 17:40 · 12.16 · dev · intégration fusionnée (12.12) sans conflit ; test des parties du repli CRAG dans l'arbre ; 484 tests, E2E 157/157 et 87/87 · ecaf9fc6
- 2026-10-25 17:40 · 12.16 · PR · #125 ouverte vers integration/v1-2-atelier ; fusion après #124 (onglet Modèles), refusion si conflit · ecaf9fc6
- 2026-10-25 17:45 · 12.21 · review · passe 1 : intégration fusionnée ; 1 high (test du rapport sur le rejeu des résultats) et 4 medium corrigés (requête ColSmol avec image factice non nulle, appel réel ~8,3 s ; pic mémoire selon la règle du banc 12.2 ; candidat au plafond = « ne tient pas » ; deferred-work avec verdict et pistes), 4 low ; ColSmol pic 6 118 Mo (privée) / 4 244 Mo (ensemble de travail) : ne tient pas ; 70 tests · 15b01313
- 2026-10-25 17:45 · 12.21 · décision · à revoir : seuils sans source, corpus fr seul, 12 pages et 8 requêtes, plafond 16 384 Mo, licence Gemma, entrées ColSmol construites à la main, ColQwen2.5 écarté · 15b01313
- 2026-10-25 17:45 · 12.21 · report · remesure de ColSmol seul (requêtes) sur poste libre, après le correctif du graphe · 15b01313
