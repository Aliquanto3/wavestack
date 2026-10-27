# Run autonome : retours du 27/10 (v1.7.0)

Lancé le 2026-10-27 à la demande d'Anaël, après le run V1.5 (archivé dans [run-autonome-v15-2026-10-25.md](run-autonome-v15-2026-10-25.md)). Orchestration : session principale Opus 5.5.

## Périmètre

| Périmètre | Epics | Note |
|---|---|---|
| Dans le run | Epics 16 à 16 | epic 16 dans `sprint-status.yaml` ; story 16.N = id N de `stories.yaml` |
| Hors run | Recette guidée des sous-onglets RAG | session dédiée après le lot |

Spec : `_bmad-output/specs/spec-wavestack-retours-2026-10-27/` (SPEC.md, brownfield.md, stories.yaml). Specs de story dans `stories/story-N.md` du même dossier.

Au plus 4 stories en développement à la fois (3 au départ, 4e créneau autorisé par Anaël le 2026-10-27 ; E2E lancés un par un par l'orchestrateur)

## Sprint 1 — Retours du 27/10

| Vague | Stories en parallèle | Après |
|---|---|---|
| V0 | 16.1 ★ · 16.2 · 16.3 · 16.4 (humaine) | 16.1 : spec relue par Anaël avant le code ; 16.4 : maquette avec bmad-ux, validée par Anaël |
| V1 | 16.5 · 16.7 | 16.7 ← 16.1 ; 16.6 annulée par Anaël le 27/10 |
| V2 | 16.8 · 16.9 | 16.8 ← 16.5 ; 16.8 et 16.9 : specs relues par Anaël, Opus, rebaser (app.js) |
| Fin | version 1.7.0 | ← toutes ; tag annoté et release GitHub |

## Règles du run

- Par story : `dev-story` (Sonnet ; Opus pour 16.8 et 16.9), `second-avis` (Haiku), `reviewer` (Opus, avec la liste du second avis, rebasé sur `origin/main`), PR, CI verte, fusion, vérification `MERGED`, journal.
- `spec_checkpoint` (16.1, 16.6, 16.8, 16.9) : `dev-story` écrit `stories/story-N.md` et s'arrête ; Anaël la relit (notification) ; le code attend son accord. Les specs de V1 et V2 sont écrites en avance pour grouper les relectures.
- 16.4 : maquette HTML (bmad-ux, DESIGN.md existant) dans le dossier de spec ; 16.7 attend la validation d'Anaël.
- Fichiers partagés (`app_session.py`, `content/ui.yaml`, `app.js`, `pages.css`) : fusion l'une après l'autre, rebase avant revue.
- Local : ruff + tests ciblés ; la CI de branche sert de suite complète. Worktrees `../wavestack-r27-s<N>`, branches `feat/r27-story-N-…`.
- Chaque choix fait à la place d'Anaël : ligne `décision · à revoir`.

## Contrats

- 16.1 (5271be9) → 16.7 : entrée du Journal `{kind: model_call|security, onglet, modele: {label, hosting}|null, tokens_in, tokens_out, cout_usd|null, empreinte|null, duree_ms}`, sans prompt ni réponse ; `feedBar(envelope)` (revue c8ac88e1 : onglet tiré de `context_id`, modèle du dernier `active_model` du flux), champ interne `seq` ; constante `BAR_MODEL_KINDS` exportée par bar.js pour les pages.

- Glossaire : plafond de 60 termes fr dans tests/test_glossary.py:38 ; 16.2 l'amène à 59, 16.5 relève le plafond pour ses 3 termes.

## Décisions

## Prochaines étapes (run terminé le 2026-10-27)

Run terminé : epic 16 fusionné, version 1.7.0 publiée. Suite : recette de la 1.7.0 et recette guidée des sous-onglets RAG, d'après [rapport-run-retours-2026-10-27.md](rapport-run-retours-2026-10-27.md).

## Reprise après /clear

- Lire ce fichier, puis `sprint-status.yaml` ; l'état réel prime : `gh pr list --state open`, `git -C ../wavestack-r27-s<N> log -3 --oneline`.
- Une story dont le dev a commité sans rapport : relancer la chaîne à partir de `second-avis` sur son dernier commit.
- Fin de run : `rapport-run-retours-2026-10-27.md`, version 1.7.0, mémoire du projet, suppression des worktrees.

## Journal

- 2026-10-27 06:10 · run · décision · ancien run archivé, epic 16 créé · —
- 2026-10-27 06:13 · 16.2 · dev · lancé (Sonnet) · —
- 2026-10-27 06:13 · 16.3 · dev · lancé (Sonnet) · —
- 2026-10-27 06:13 · 16.1, 16.6 · dev · spec lancée (Sonnet) · —
- 2026-10-27 06:13 · 16.8, 16.9 · dev · spec lancée (Opus) · —
- 2026-10-27 06:13 · 16.4 · dev · maquette lancée (Opus, bmad-ux) · —
- 2026-10-27 06:13 · run · blocked · fusion de la PR #148 (spec) refusée par le classifieur, accord d'Anaël attendu · —
- 2026-10-27 07:01 · 16.1, 16.3, 16.4, 16.6, 16.8, 16.9 · blocked · quatre agents arrêtés par le watchdog vers 06:18 (flux coupé), relancés là où ils en étaient · —
- 2026-10-27 07:03 · 16.4 · dev · fini, maquette-securite.html + ux-securite.md, validation d'Anaël attendue · —
- 2026-10-27 07:03 · 16.8, 16.9 · dev · specs écrites (story-8.md, story-9.md), relecture d'Anaël attendue · —
- 2026-10-27 07:05 · 16.1, 16.6 · dev · specs écrites (story-1.md, story-6.md), relecture d'Anaël attendue · —
- 2026-10-27 07:12 · 16.4 · décision · maquette Sécurité validée par Anaël · —
- 2026-10-27 07:25 · 16.1, 16.8, 16.9 · décision · specs relues par Anaël, réponses consignées dans chaque story-N.md (16.9 : un modèle local choisi dans le RAG change le modèle de l'application) · —
- 2026-10-27 07:25 · 16.6 · report · annulée par Anaël : pas de serveur public avec ressource et prompt, pas de second serveur maison · —
- 2026-10-27 07:26 · 16.1 · dev · lancé (Sonnet) · —
- 2026-10-27 07:28 · run · décision · Anaël autorise la fusion des PR du run ; #148 en fusion automatique après CI · —
- 2026-10-27 07:31 · 16.3 · dev · relancé après la coupure de 06:18, en cours · —
- 2026-10-27 07:31 · 16.4 · fusion · maquette validée, fusionnée avec la spec (#148 MERGED) · 41ff7916
- 2026-10-27 07:31 · 16.8 · attente humaine · spec validée, code après 16.5 · —
- 2026-10-27 07:31 · 16.9 · attente humaine · spec validée, code après 16.5 · —
- 2026-10-27 07:33 · 16.2 · dev · fini (étape 1 non reproduite, rien changé dessus ; E2E llm 129 OK) · 612fd704
- 2026-10-27 07:33 · 16.2 · second-avis · lancé · 612fd704
- 2026-10-27 07:33 · 16.5 · dev · lancé (Sonnet) · —
- 2026-10-27 07:33 · 16.2 · décision · g CO₂e local masqué (spec : énergie seule) · 612fd704
- 2026-10-27 07:34 · run · décision · Anaël autorise un 4e créneau ; E2E lancés un par un par l'orchestrateur à la revue, plus par les agents de dev · —
- 2026-10-27 07:34 · 16.9 · dev · lancé (Opus), 4e créneau, avancée de V2 (ne dépend pas de 16.5) · —
- 2026-10-27 07:35 · 16.2 · décision · Anaël veut aussi les g CO₂e pour un modèle local ; à appliquer par le reviewer · —
- 2026-10-27 07:36 · 16.3 · dev · fini (E2E mcp_lab et mcp_lab_page OK, 69 vérifications) · ba735a33
- 2026-10-27 07:36 · 16.3 · décision · à revoir : logos des serveurs en pictogrammes neutres, conditions d'usage des marques non vérifiées · ba735a33
- 2026-10-27 07:36 · 16.3 · second-avis · lancé · ba735a33
- 2026-10-27 07:38 · 16.3 · décision · Anaël : vérifier les conditions de chaque marque et mettre les vrais logos là où c'est permis ; recherche lancée (Opus), intégration par le reviewer de 16.3 · ba735a33
- 2026-10-27 07:39 · 16.2 · second-avis · fini : 1 medium (E2E de l'étape 6 absents, captures modifiées), 4 low · 612fd704
- 2026-10-27 07:39 · 16.2 · review · lancé (Opus, rebase, + g CO₂e local) · 612fd704
- 2026-10-27 07:39 · 16.3 · second-avis · fini : 1 medium (source GitHub vide dans le schéma), 4 low ; revue après la recherche sur les logos · ba735a33
- 2026-10-27 07:40 · 16.3 · décision · logos : GitHub autorisé (Invertocat officiel non modifié) ; Microsoft Learn (licence requise) et data.gouv.fr (Marque d'État) restent en pictogramme neutre · ba735a33
- 2026-10-27 07:40 · 16.3 · review · lancé (Opus, rebase, + logo GitHub et mentions) · ba735a33
- 2026-10-27 07:43 · 16.3 · décision · Microsoft : aucune charte d'icônes ne couvre une icône Microsoft Learn dans une application ; icônes produit interdites « in software applications » (page copyright/permissions) ; pictogramme neutre confirmé · —
- 2026-10-27 07:47 · 16.2 · review · fini : 1 medium + 3 low corrigés, CO₂e local ajouté, rebasé · 2125bc65
- 2026-10-27 07:47 · 16.2 · PR · #149 ouverte · 2125bc65
- 2026-10-27 07:47 · 16.2 · E2E · llm_screen lancé par l'orchestrateur · 2125bc65
- 2026-10-27 07:51 · 16.2 · E2E · llm_screen 66 OK, 0 échec (PYTHONUTF8=1 obligatoire sous Windows) · 2125bc65
- 2026-10-27 07:57 · 16.2 · CI · verte (8/8) · 2125bc65
- 2026-10-27 07:57 · 16.2 · fusion · #149 MERGED · 117863cb
- 2026-10-27 07:59 · 16.3 · review · fini : 1 medium + 4 low corrigés, Invertocat noir et blanc, rebasé sur 117863cb · ed5473be
- 2026-10-27 07:59 · 16.3 · PR · #150 ouverte · ed5473be
- 2026-10-27 07:59 · 16.3 · E2E · mcp_lab mcp_lab_page lancés par l'orchestrateur · ed5473be
- 2026-10-27 08:01 · 16.3 · E2E · mcp_lab mcp_lab_page 54 OK, 0 échec (une ressource ERR_FAILED en console, attendue au scénario hors réseau) ; captures MCP commitées · 6d57a865
- 2026-10-27 08:04 · 16.1 · dev · fini (E2E de CAP-1/CAP-2 non écrits) · 5271be9
- 2026-10-27 08:04 · 16.1 · second-avis · lancé · 5271be9
- 2026-10-27 08:06 · 16.5 · dev · fini (URL vérifiées ; « Peut-être » de la carte non traité, question à Anaël) · 8dca61ec
- 2026-10-27 08:06 · 16.5 · second-avis · lancé · 8dca61ec
- 2026-10-27 08:07 · 16.1 · second-avis · fini : 2 high (rejeu mal étiqueté ; Sécurité et Diagnostic sans appels), 3 medium, 3 low · 5271be9
- 2026-10-27 08:07 · 16.1 · review · lancé (Opus, rebase, + E2E de la barre à écrire) · 5271be9
- 2026-10-27 08:09 · 16.5 · second-avis · fini : 0 high, 2 medium, 5 low · 8dca61ec
- 2026-10-27 08:09 · 16.5 · review · lancé (Opus, rebase) · 8dca61ec
- 2026-10-27 08:14 · 16.3 · CI · verte (8/8) · 6d57a865
- 2026-10-27 08:14 · 16.3 · fusion · #150 MERGED · 72832fb8
- 2026-10-27 08:15 · 16.5 · décision · Anaël : « Peut-être » de la carte du harnais sans suite, question close · —
- 2026-10-27 08:17 · 16.9 · dev · fini (raison du CAG cachée hors sélection, rendue visible) · 612503f6
- 2026-10-27 08:17 · 16.9 · second-avis · lancé · 612503f6
- 2026-10-27 08:26 · 16.9 · second-avis · fini : 0 high, 4 medium, 5 low · 612503f6
- 2026-10-27 08:26 · 16.9 · review · lancé (Opus, rebase) · 612503f6
- 2026-10-27 08:43 · 16.1 · review · fini : 2 high + 2 high revue + 3 medium corrigés (onglet et modèle tirés de l'enveloppe, Journal gardé entre pages, E2E bar_journal), rebasé sur 72832fb8 · c8ac88e1
- 2026-10-27 08:43 · 16.1 · E2E · bar_panels bar_journal lancés par l'orchestrateur · c8ac88e1
- 2026-10-27 08:45 · 16.1 · E2E · bar_panels OK ; bar_journal 30 OK, 2 échecs (débordement à 360 px du Bilan et du Journal) ; passe 2 de revue · c8ac88e1
- 2026-10-27 08:49 · 16.5 · review · fini : 1 high + 2 medium corrigés, rebasé sur 72832fb8 · 5f933f80
- 2026-10-27 08:49 · 16.5 · PR · ouverte, E2E après ceux de 16.1 (port commun) · 5f933f80
- 2026-10-27 08:49 · 16.9 · review · fini : 2 corrigés (test coût/empreinte, clé retirée), 7 écartés motivés, rebasé sur 72832fb8 · 5b53ceac
- 2026-10-27 08:49 · 16.9 · PR · ouverte, E2E en file après 16.1 et 16.5 · 5b53ceac
- 2026-10-27 08:57 · 16.1 · décision · Anaël : montants en dollars (barre et Journal), « — » pour les appels du diagnostic · —
- 2026-10-27 09:19 · 16.5 · CI · verte (8/8) · 5f933f80
- 2026-10-27 09:19 · 16.9 · CI · verte (8/8) · 5b53ceac
- 2026-10-27 09:19 · 16.5 · E2E · harness_map disciplines content_language lancés par l'orchestrateur · 5f933f80
- 2026-10-27 09:25 · 16.5 · E2E · disciplines et harness_map OK ; content_language : délai dépassé au changement de langue (poste chargé), relancé seul · 5f933f80
- 2026-10-27 09:31 · 16.5 · E2E · content_language échoue 2 fois (délai au changement de langue), passe sur main 72832fb8 : régression de la story, passe 2 de revue · 5f933f80
- 2026-10-27 09:44 · 16.9 · E2E · 63 OK, 7 échecs (diagnostic, rag, rag_rerank, rag_lab_no_index et rag_lab_context : body[data-rag-ready] jamais posé) ; même tranche relancée sur main pour attribuer · 5b53ceac
- 2026-10-27 09:55 · 16.9 · E2E · main 72832fb8 : 112 OK, 1 échec (rag_lab_context, préexistant) ; régressions de la story : diagnostic, rag, rag_rerank, rag_lab_no_index ; passe 2 de revue · 5b53ceac
- 2026-10-27 10:00 · 16.5 · review · passe 2 : rebasée sur 72832fb8, content_language 27 OK seul (échec attribué à un délai sous charge) · 922b5ede
- 2026-10-27 10:14 · 16.5 · CI · verte (8/8) · 922b5ede
- 2026-10-27 10:14 · 16.5 · fusion · #151 MERGED · c8e2d116
- 2026-10-27 10:14 · 16.8 · dev · lancé (Opus) · —
- 2026-10-27 10:37 · 16.9 · review · passe 2 : échecs non reproduits par la story (poste saturé) ; démarrage de rag.html allégé par précaution ; relance E2E à poste calme · e99e959b
- 2026-10-27 10:42 · 16.1 · review · passe 2 : vrai débordement à 360 px (white-space hérité de .site-nav) corrigé, bar_journal 21 OK · d4e95729
- 2026-10-27 10:42 · 16.1 · PR · #153 ouverte, rebasée sur c8e2d116 ; E2E bar après ceux de 16.9 · 7aa41a1b
- 2026-10-27 10:46 · 16.9 · E2E · rebasée sur c8e2d116 : 114 OK, 1 échec (rag_lab_no_index : le test attend data-journal-replayed sur la page RAG) ; passe 3 · 9dc8bde8
- 2026-10-27 10:47 · 16.1 · E2E · bar_panels bar_journal 32 OK, 0 échec · 7aa41a1b
- 2026-10-27 10:52 · 16.9 · review · passe 3 : test _apply_window corrigé (page RAG), rag rag_rerank rag_lab_no_index 89 OK · ff5c19c3
- 2026-10-27 10:54 · 16.1 · CI · verte (8/8) · 7aa41a1b
- 2026-10-27 10:54 · 16.1 · fusion · #153 MERGED · b2e06428
- 2026-10-27 10:54 · 16.7 · dev · lancé (Sonnet) · —
- 2026-10-27 11:04 · 16.9 · CI · verte (8/8) avant 16.1 ; rebasée sur b2e06428, E2E d'intégration bar_journal + RAG et CI relancés · a4b6e39e
- 2026-10-27 11:20 · 16.9 · E2E · intégration : RAG OK, bar_journal seul 21 OK (échecs de transport sous charge) ; CI verte (8/8) · a4b6e39e
- 2026-10-27 11:20 · 16.9 · fusion · #152 MERGED · 6ae6d8bf
- 2026-10-27 11:28 · 16.8 · dev · fini (60 fichiers, −3 301 lignes, rebasée sur 6ae6d8bf ; Caveman refait par un prompt : à valider par Anaël) · fad387cc
- 2026-10-27 11:28 · 16.8 · second-avis · lancé · fad387cc
- 2026-10-27 11:38 · 16.8 · second-avis · fini : 0 high, 1 medium (test des hooks dans le sous-agent perdu), 2 low ; aucune référence orpheline · fad387cc
- 2026-10-27 11:38 · 16.8 · review · lancé (Opus) · fad387cc
- 2026-10-27 11:39 · 16.7 · dev · fini (légende en phrases au lieu des trois états ; pas d'E2E des nouveautés) · 9383b011
- 2026-10-27 11:39 · 16.7 · second-avis · lancé · 9383b011
- 2026-10-27 11:41 · 16.7 · second-avis · fini : 1 high (détails de matrice ouverts au chargement), 4 medium (survol absent, légende, E2E), 4 low · 9383b011
- 2026-10-27 11:41 · 16.7 · review · lancé (Opus, rebase) · 9383b011
- 2026-10-27 11:47 · 16.8 · review · fini : 2 medium + 2 low corrigés (test hooks sous-agent, E2E compression) · 733875ec
- 2026-10-27 11:47 · 16.8 · PR · ouverte ; E2E tranche 1 lancée · 733875ec
- 2026-10-27 11:48 · 16.8 · E2E · tranche 1 (mcp_full mcp_lazy caveman hooks) 50 OK, 0 échec ; PR #154 ; tranche 2 lancée · 733875ec
- 2026-10-27 11:51 · 16.8 · E2E · tranche 2 : 91 OK, 1 échec (subagent : onglet « Agent principal » non resélectionné au tour suivant) ; contrôle sur main · 733875ec
- 2026-10-27 11:53 · 16.8 · E2E · subagent passe sur main 6ae6d8bf (55 OK) : régression de la story, passe 2 ; tranche 3 lancée · 733875ec
- 2026-10-27 11:56 · 16.8 · E2E · tranche 3 (programme soc native_tools skills) 108 OK, 0 échec · 733875ec
- 2026-10-27 11:57 · 16.7 · review · fini : 1 high + 5 medium corrigés (détails repliés, survols, légende à trois états, E2E), rebasée · e82bd501
- 2026-10-27 11:57 · 16.7 · PR · ouverte ; E2E après la passe 2 de 16.8 · e82bd501
- 2026-10-27 11:58 · 16.8 · review · passe 2 : test subagent corrigé (Bonjour ne délègue plus), subagent 48 OK · b16d775e
- 2026-10-27 11:58 · 16.8 · PR · #154 captures régénérées commitées · d86cba8d
- 2026-10-27 11:59 · 16.7 · E2E · 67 OK, 7 échecs : glossary ×6 (plafond E2E de 60 termes, 62 sur main depuis 16.2 et 16.5 : défaut croisé) ; security_page (élément jamais stable) ; passe 2 · e82bd501
- 2026-10-27 12:02 · 16.7 · review · passe 2 : test security_page (ligne masquée par le filtre) et plafond du glossaire E2E corrigés ; glossary security_page bar_journal 77 OK · 5a00c30d
- 2026-10-27 12:06 · 16.7 · décision · Anaël valide « Ruhe » (état au repos, légende allemande) · —
- 2026-10-27 12:07 · 16.8 · décision · Anaël valide la démo Caveman (second prompt qui fait charger le skill) · —
- 2026-10-27 12:13 · 16.8 · CI · verte (8/8) · d86cba8d
- 2026-10-27 12:13 · 16.8 · fusion · #154 MERGED · 56b91cc3
- 2026-10-27 12:13 · 16.7 · CI · verte (8/8) avant 16.8 ; rebase sur 56b91cc3 · 5a00c30d
- 2026-10-27 12:28 · 16.7 · E2E · rebasée sur 56b91cc3 : glossary security_page bar_journal 77 OK ; CI verte (8/8) · 5f9d7e31
- 2026-10-27 12:28 · 16.7 · fusion · #155 MERGED · b35ca5b2
- 2026-10-27 12:30 · run · PR · #156 version 1.7.0 ouverte · —
- 2026-10-27 12:49 · run · fusion · #156 version 1.7.0 MERGED · 5ca254d7
- 2026-10-27 12:49 · run · décision · tag v1.7.0 et release GitHub publiés ; rapport rapport-run-retours-2026-10-27.md · 5ca254d7
