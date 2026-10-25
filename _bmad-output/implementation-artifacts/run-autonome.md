# Run autonome : V1.5 évaluer l'agent (incrément 1)

Lancé le 2026-10-25 à la demande d'Anaël, après le run V1.3, V1.4, V1.2 (archivé dans [run-autonome-v13-v14-v12-2026-10-24.md](run-autonome-v13-v14-v12-2026-10-24.md)). Orchestration : session principale Opus 5.5.

## Périmètre

| Périmètre | Epics | Note |
|---|---|---|
| Dans le run | Epics V1.5 stories 1 à 6 | epic 15 dans `sprint-status.yaml` ; story 15.N = id N de `stories.yaml` |
| Hors run | V1.5 incrément 2, V2 | incrément 2 revu après la recette de l'incrément 1 |

Spec : `_bmad-output/specs/spec-wavestack-evaluer-l-agent/` (SPEC.md, contrat-des-cas.md, brownfield.md, vues.md, maquette), PR #134.

Au plus 3 stories en développement à la fois (3e créneau seulement pour une story sans fichier commun avec les deux autres ; décision d'Anaël du 2026-10-25)

## Sprint 1 — V1.5 évaluer l'agent

| Vague | Stories en parallèle | Après |
|---|---|---|
| V0 | 15.1 ★ · 15.6 · 15.2 | 15.2 : phase spec seulement, code ← 15.1 |
| V1 | 15.2 · 15.3 | 15.2 ← 15.1 ; 15.3 ← 15.1 |
| V2 | 15.4 ★ | 15.4 ← 15.1 ; 15.4 ← 15.3 ; découpée en 4a (exécuteur et API, ← 15.2) puis 4b (vue, ← 4a et 15.3), Opus |
| V3 | 15.5 | 15.5 ← 15.2 ; 15.5 ← 15.4 ; 15.5 ← 15.6 |

## Règles du run

- Par story : `dev-story` (Opus pour 15.1 et 15.4, Sonnet pour les autres), `second-avis` (Haiku), `reviewer` (Opus, avec la liste du second avis, rebasé sur `origin/main`), PR, CI verte, fusion, vérification `MERGED`, journal.
- Contrats partagés : 15.1 annonce les noms de `contrat-des-cas.md` (champs, `kind`, statuts) et 15.6 la syntaxe de citation d'un terme du glossaire ; l'orchestrateur les reporte ici (« Contrats ») et les transmet aux stories suivantes.
- `spec_checkpoint` (15.2, 15.3, 15.4) : `dev-story` écrit la spec de story et s'arrête ; `reviewer` la relit contre SPEC.md, maquette, vues.md et brownfield.md, tranche les points ouverts ; `dev-story` reprend. Chaque choix fait à la place d'Anaël : ligne `décision · à revoir`.
- 15.2 : plafonds provisoires et liste de cas livrés ; la mesure sur le PC cible (3 exécutions par cas, max + 1) est une `attente humaine` d'Anaël qui ne bloque pas la fusion.
- Local : contrôle rapide et tests ciblés seulement ; la CI de la PR (Windows, Ubuntu) sert de suite complète. Pas d'Ollama réel (Anaël lance un benchmark en parallèle) : tests et E2E sur les faux serveurs.
- `gh run watch <id> --interval 60` ; worktrees `../wavestack-v15-s<n>`, branches `feat/v1-5-story-<n>-<slug>`, `git worktree prune` avant chaque lancement, suppression en fin de run.
- Ce fichier et `sprint-status.yaml` vivent sur `chore/etat-run`, hors des PR de story.
- Arrêt seulement pour une ressource ou une décision d'Anaël (modèle réel, PC cible) : notification, `attente humaine`, on avance ailleurs.
- Fin de lot : PR de version 1.6.0, tag annoté, release GitHub.

## Contrats

- 15.1 (214f9289) : `wavestack.agent_eval` — `cases.AgentCase` (champs de contrat-des-cas.md ; `system_prompt` interdit et `brick` obligatoire dans un cas fourni), `Provenance{source: fourni|séance|recette, date, model, turn_id, system_prompt_text, fixed_in}` (pas de champ `reference` : la recette d'origine va dans `fixed_in`), `Check` discriminé par `kind` (tool_called{tool, before?}, tool_not_called, argument_never{tool, argument, contains}, answer_contains{text}, hook_decided{hook, decision: block|ask_human}, subagent_called, turn_completed ; `model_calls_max` vient de `max_model_calls`, ajouté en dernier par verify). `RunStatus = passed|failed|not_run`, `NotRunReason = window|cancelled|budget`. `load_provided_cases(lang, known)` lit `content/agent_cases.yaml` (`cases: [...]`). `checks.verify(case, envelopes, lang) -> CaseVerdict{case_id, passed, checks: [CheckVerdict{kind, params, passed, reason_text, seq}], model_calls}` ; l'appelant filtre les enveloppes sur les tours du cas. `store` : `config.agent_cases_path()` = `data_dir()/agent_cases.json` `{version: 1, cases: [...]}` ; `read_session_cases`, `add_session_case(case, provided)`, `delete_session_case(id)`, `clear_session_cases()` ; id de séance `u` + 8 hex ; `SessionCasesUnreadable`.
- 15.6 (de484e94) : citation `[[g:clé]]` ou `[[g:clé|texte]]` (préfixe `g:` obligatoire, `[[page]]` = lien de wiki) ; `content/glossary.yaml` `terms: {clé: {term, definition}}` + surcouches en, de, 58 termes, clés en anglais ; test `tests/test_glossary.py::test_every_term_cited_by_a_content_text_exists_in_every_language`. Clés utiles au module 9 : agent_case, check, verdict, call_ceiling, budget_ceiling, pass_at_k, pass_hat_k, benchmark, regression, llm_judge, replay, witness_replay, determinism, journal, provenance, demo, harness.

- 15.3 (spec 1c4d05fc) → 15.4 : fichiers propres à 15.3 (`web/agent_case_api.py`, `web/static/agent-case-form.js` et `.css`, clés `main.agent_case.*`, `agent_case.*`) ; 15.4 crée `web/agent_eval_api.py`, `agent-eval.js`, `main.agent_eval.*`. `agent-case-form.js` exporte `openCaseForm, closeCaseForm, canMakeCase, registerOpenView(fn(caseId)), onCaseSaved(fn)` ; `agent-eval.js` les importe (jamais l'inverse). Routes `/api/agent_eval/` : 15.3 `GET /draft`, `POST /verdict`, `POST /cases` ; 15.4 `GET /cases`, `DELETE /cases`, exécutions. 15.4 met `case_id` dans le payload `turn_started` des tours d'exécution, compare `case.window` au `configured` de `context_window_state`, produit les tours `verdict_turn_ids`. 15.4 ajoute l'étape E2E « Ouvrir Évaluer l'agent ». Insertion dans les fichiers partagés : app.py après `/api/intentions/compact`, app.js après l'import de panes.js, ui.yaml après `main.compare`, run_e2e.py en fin de liste ; index.html non touché.

## Décisions

- 2026-10-25 : spec de 15.4 (9bb362e7) : état de session `agent_eval` + garde HTTP ; k = 3 réussi à la majorité stricte (pass@3 et pass^3 affichés à côté) — à revoir par Anaël ; id de configuration inconnu dans un cas de séance ignoré et montré (« Joué sans : … »), contrat inchangé — à revoir par Anaël ; mémoire globale restaurée avant chaque cas et à la fin ; tests en 16 384 avec `start(..., check_window=False)` réservé aux tests (à 4 096 le faux moteur déborde sur le résumé) ; plafond de dépense en cours de cas et `approval: approve` testés en fonction pure, à vérifier en recette.
- 2026-10-25 : spec de 15.3 : tout tour de message terminé est éligible à « En faire un cas », annulé compris (note « tour non abouti », 1re vérification proposée turn_completed) — à revoir par Anaël ; approval et on_overflow déduits du journal, modifiables.
- 2026-10-25 : spec de 15.2 (6afc1faa) : cas de recette = boucle de `get_datetime` (R22, Mistral, corrigée R23/R25), gardé comme cas de régression bien qu'il ne se reproduise pas en local — à revoir par Anaël ; H5 plafond 2 sans marge (un appel refusé n'émet pas tool_started) ; mémoire globale vérifiée sur un fait (Pascal), pas une consigne.
- 2026-10-25 : à reporter dans la spec de 15.4 : `tools/eval/case_player.py` (15.2, ~60 lignes) est repris par l'exécuteur de 15.4 puis supprimé.
- 2026-10-25 : 3e créneau autorisé par Anaël pour une story largement indépendante ; seule 15.2 l'est (phase spec, fichiers propres), son code attend la fusion de 15.1. 15.3 partage le front avec 15.6.
- 2026-10-25 : points `spec_checkpoint` tranchés par le reviewer, comme au run précédent ; à confirmer par Anaël.

## Reprise après /clear

- Lire ce fichier en entier, puis `sprint-status.yaml` ; l'état réel prime : `gh pr list --state open`, `git -C ../wavestack-v15-s<n> log -3 --oneline` pour chaque story en cours.
- Une story dont le dev a commité sans rapport : relancer la chaîne à partir de `second-avis` sur son dernier commit.
- E2E : `TEMP` et `TMP` en chemin long (`C:\Users\Utilisateur\AppData\Local\Temp`).
- Fichiers temporaires des agents : chacun dans `C:\Users\Utilisateur\AppData\Local\Temp\wavestack-v15\s<story>` (le scratchpad de session a expiré).
- Fin de run : `rapport-run-v1-5.md` (fusionné, bloqué, reporté, « à revoir », tests manuels), mémoire du projet, suppression des worktrees.

## Journal

- 2026-10-25 20:50 · run · décision · run V1.5 lancé ; run précédent archivé ; Ollama non requis (Anaël lance un benchmark) · —
- 2026-10-25 20:58 · run · fusion · #134 MERGED dans main (squash) : spec V1.5 · 3214fec5
- 2026-10-25 20:58 · 15.1 · dev · lancé (Opus, ../wavestack-v15-s1) · —
- 2026-10-25 20:58 · 15.6 · dev · lancé (Sonnet, ../wavestack-v15-s6) · —
- 2026-10-25 21:03 · run · décision · 3e créneau (Anaël) : phase spec de 15.2 avancée en V0 · —
- 2026-10-25 21:03 · 15.2 · dev · lancé (Sonnet, phase spec, ../wavestack-v15-s2) · —
- 2026-10-25 21:07 · 15.2 · dev · fini (phase spec, 8 cas, 9 points ouverts) · 87c373ec
- 2026-10-25 21:07 · 15.2 · review · lancé (spec_checkpoint, Opus) · —
- 2026-10-25 21:09 · 15.6 · dev · fini (58 termes, E2E glossary vert) · de484e94
- 2026-10-25 21:09 · 15.6 · second-avis · lancé · —
- 2026-10-25 21:09 · 15.1 · dev · fini (60 tests) · 214f9289
- 2026-10-25 21:09 · 15.1 · second-avis · lancé · —
- 2026-10-25 21:11 · 15.6 · second-avis · 1 medium (YAMLError non attrapée dans /api/glossary), 6 low · de484e94
- 2026-10-25 21:11 · 15.6 · review · lancé (Opus) · —
- 2026-10-25 21:12 · 15.1 · second-avis · 2 medium (cas fourni sans événement exigé ; tour annulé ou bloqué jugé complet), 3 low · 214f9289
- 2026-10-25 21:12 · 15.1 · review · lancé (Opus) · —
- 2026-10-25 21:12 · 15.2 · review · spec ready-for-dev, 9 points tranchés · 6afc1faa
- 2026-10-25 21:12 · 15.2 · décision · cas de recette get_datetime (Mistral) gardé comme régression · à revoir
- 2026-10-25 21:12 · 15.2 · attente humaine · mesure des plafonds sur le PC cible (tools/eval/measure_cases.py), après fusion · —
- 2026-10-25 21:16 · 15.6 · review · prête (1 medium et 3 low corrigés, 2 faux, 1 laissé) · 4179682c
- 2026-10-25 21:16 · 15.6 · fusion · PR #135 ouverte, CI en cours · 4179682c
- 2026-10-25 21:16 · 15.3 · dev · lancé (Sonnet, phase spec, ../wavestack-v15-s3) · —
- 2026-10-25 21:18 · 15.1 · review · prête (2 medium et 3 low corrigés ; ajout cases.POSITIVE_KINDS) · e53f3702
- 2026-10-25 21:18 · 15.1 · décision · précision de contrat-des-cas.md sortie de la branche de story vers la PR docs #136 · aa2ca985
- 2026-10-25 21:18 · 15.1 · fusion · PR #137 ouverte, CI en cours · aa2ca985
- 2026-10-25 21:19 · 15.3 · dev · fini (phase spec, 9 points ouverts) · 69b8840e
- 2026-10-25 21:19 · 15.3 · review · lancé (spec_checkpoint, Opus) · —
- 2026-10-25 21:25 · 15.6 · CI · verte (8/8) · 4179682c
- 2026-10-25 21:25 · 15.6 · fusion · #135 MERGED dans main (squash) · 23108ae2
- 2026-10-25 21:26 · 15.3 · review · spec ready-for-dev, 9 points tranchés · 1c4d05fc
- 2026-10-25 21:26 · 15.3 · décision · tour annulé éligible à « En faire un cas » · à revoir
- 2026-10-25 21:30 · 15.1 · CI · verte (8/8) · aa2ca985
- 2026-10-25 21:30 · 15.1 · fusion · #137 MERGED dans main (squash) · a1f970bc
- 2026-10-25 21:30 · run · fusion · #136 MERGED dans main (précision de contrat-des-cas.md) · 85534df4
- 2026-10-25 21:30 · 15.2 · dev · lancé (Sonnet, code, rebasé sur 85534df4) · —
- 2026-10-25 21:30 · 15.3 · dev · lancé (Sonnet, code, rebasé sur 85534df4) · —
- 2026-10-25 21:31 · 15.4 · dev · lancé (Opus, phase spec, ../wavestack-v15-s4) · —
- 2026-10-25 21:44 · 15.2 · dev · fini (8 cas, tools/eval, 139 tests) · 74b431a7
- 2026-10-25 21:44 · 15.2 · second-avis · lancé · —
- 2026-10-25 21:44 · 15.4 · dev · fini (phase spec : état de session agent_eval, 11 points ouverts) · 63c0c771
- 2026-10-25 21:44 · 15.4 · review · lancé (spec_checkpoint, Opus) · —
- 2026-10-25 21:45 · 15.4 · dev · spec mise à jour avec les écarts de 15.2 (accesseurs publics de configuration, case_player supprimé) · 87a40c37
- 2026-10-25 21:51 · 15.2 · second-avis · 4 medium (plafond mesuré sur les échecs ; cas joués hors de leur fenêtre, compaction non prouvée ; cas R22 sans brique Raisonnement ; symptôme de chemin_invente non vérifié), 7 low · 74b431a7
- 2026-10-25 21:51 · 15.2 · review · lancé (Opus) · —
- 2026-10-25 21:52 · 15.4 · review · spec ready-for-dev, découpage 4a/4b, 11 points tranchés · 9bb362e7
- 2026-10-25 21:52 · 15.4 · décision · k = 3 réussi à la majorité ; id inconnu ignoré et montré · à revoir
- 2026-10-25 21:52 · 15.3 · dev · fini (E2E agent_case 34/34) · c26438b6
- 2026-10-25 21:52 · 15.3 · second-avis · lancé · —
- 2026-10-25 21:57 · 15.3 · second-avis · 1 high (tiroir qui ne se ferme plus après modification, plantage pendant le chargement), 3 medium (erreur d'enregistrement silencieuse ; abandon pendant l'enregistrement ; collision de turn_id), 4 low · c26438b6
- 2026-10-25 21:57 · 15.3 · review · lancé (Opus) · —
- 2026-10-25 22:02 · 15.2 · review · prête (4 medium et 5 low corrigés ; brique reasoning ajoutée au cas R22 ; compaction du cas TLV prouvée) · b43d4bd8
- 2026-10-25 22:02 · 15.2 · PR · #138 ouverte, CI en cours · b43d4bd8
