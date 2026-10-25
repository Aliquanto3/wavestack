# Run autonome : V1.5 évaluer l'agent (incrément 1)

Lancé le 2026-10-25 à la demande d'Anaël, après le run V1.3, V1.4, V1.2 (archivé dans [run-autonome-v13-v14-v12-2026-10-24.md](run-autonome-v13-v14-v12-2026-10-24.md)). Orchestration : session principale Opus 5.5.

## Périmètre

| Périmètre | Epics | Note |
|---|---|---|
| Dans le run | Epics V1.5 stories 1 à 6 | epic 15 dans `sprint-status.yaml` ; story 15.N = id N de `stories.yaml` |
| Hors run | V1.5 incrément 2, V2 | incrément 2 revu après la recette de l'incrément 1 |

Spec : `_bmad-output/specs/spec-wavestack-evaluer-l-agent/` (SPEC.md, contrat-des-cas.md, brownfield.md, vues.md, maquette), PR #134.

Au plus 2 stories en développement à la fois

## Sprint 1 — V1.5 évaluer l'agent

| Vague | Stories en parallèle | Après |
|---|---|---|
| V0 | 15.1 ★ · 15.6 | — |
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

- (à remplir après 15.1 et 15.6)

## Décisions

- 2026-10-25 : points `spec_checkpoint` tranchés par le reviewer, comme au run précédent ; à confirmer par Anaël.

## Reprise après /clear

- Lire ce fichier en entier, puis `sprint-status.yaml` ; l'état réel prime : `gh pr list --state open`, `git -C ../wavestack-v15-s<n> log -3 --oneline` pour chaque story en cours.
- Une story dont le dev a commité sans rapport : relancer la chaîne à partir de `second-avis` sur son dernier commit.
- E2E : `TEMP` et `TMP` en chemin long (`C:\Users\Utilisateur\AppData\Local\Temp`).
- Fichiers temporaires des agents : chacun dans `scratchpad\s<story>`.
- Fin de run : `rapport-run-v1-5.md` (fusionné, bloqué, reporté, « à revoir », tests manuels), mémoire du projet, suppression des worktrees.

## Journal

- 2026-10-25 20:50 · run · décision · run V1.5 lancé ; run précédent archivé ; Ollama non requis (Anaël lance un benchmark) · —
