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
| V2 | 15.4 ★ | 15.4 ← 15.1 ; 15.4 ← 15.3 |
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

## Décisions

- 2026-10-25 : 3e créneau autorisé par Anaël pour une story largement indépendante ; seule 15.2 l'est (phase spec, fichiers propres), son code attend la fusion de 15.1. 15.3 partage le front avec 15.6.
- 2026-10-25 : points `spec_checkpoint` tranchés par le reviewer, comme au run précédent ; à confirmer par Anaël.

## Reprise après /clear

- Lire ce fichier en entier, puis `sprint-status.yaml` ; l'état réel prime : `gh pr list --state open`, `git -C ../wavestack-v15-s<n> log -3 --oneline` pour chaque story en cours.
- Une story dont le dev a commité sans rapport : relancer la chaîne à partir de `second-avis` sur son dernier commit.
- E2E : `TEMP` et `TMP` en chemin long (`C:\Users\Utilisateur\AppData\Local\Temp`).
- Fichiers temporaires des agents : chacun dans `scratchpad\s<story>`.
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
