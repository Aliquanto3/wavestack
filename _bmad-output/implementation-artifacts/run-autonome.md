# Run autonome : corrections de la recette v1.7.0 (v1.7.1)

Lancé le 2026-10-27 à la demande d'Anaël, après le run des retours du 27/10 (archivé dans [run-autonome-retours-2026-10-27.md](run-autonome-retours-2026-10-27.md)). Orchestration : session principale Opus 5.5.

## Périmètre

| Périmètre | Epics | Note |
|---|---|---|
| Dans le run | Epics 17 à 17 | epic 17 dans `sprint-status.yaml` ; story 17.N = id N de `stories.yaml` |
| Hors run | CT-06 (Caveman avec un vrai modèle local) | pas de défaut noté |

Spec : `_bmad-output/specs/spec-wavestack-recette-v1-7-0/` (SPEC.md, stories.yaml, stories/story-N.md).

Au plus 3 stories en développement à la fois (3,6 Go de RAM libre au départ ; les agents de dev ne lancent pas d'E2E, l'orchestrateur les lance un par un)

## Sprint 1 — Recette v1.7.0

| Vague | Stories en parallèle | Après |
|---|---|---|
| V0 | 17.1 · 17.2 · 17.3 | — |
| V1 | 17.4 · 17.5 | 17.5 ← 17.1 (content/ui.yaml) |
| Fin | version 1.7.1 | ← toutes ; tag annoté et release GitHub |

## Règles du run

- Par story : `dev-story` (Sonnet) écrit `stories/story-N.md` puis code, `second-avis` (Haiku), `reviewer` (Opus, avec la liste du second avis, rebasé sur `origin/main`), PR, CI verte, fusion, vérification `MERGED`, journal.
- Pas de relecture de spec par Anaël (constats précisés en amont).
- Fichiers partagés (`content/ui.yaml`, `app.js`) : fusion l'une après l'autre, rebase avant revue.
- Worktrees `../wavestack-r171-s<N>`, branches `fix/r171-story-N-…`.
- Chaque choix fait à la place d'Anaël : ligne `décision · à revoir`.

## Décisions

- 17.3 : la colonne Modèle du schéma MCP suit l'hébergement du modèle actif (Anaël : « SLM local » est faux pour un modèle cloud).

## Reprise après /clear

- Lire ce fichier, puis `sprint-status.yaml` ; l'état réel prime : `gh pr list --state open`, `git -C ../wavestack-r171-s<N> log -3 --oneline`.
- Fin de run : rapport `rapport-run-recette-v1-7-0.md`, version 1.7.1, mémoire du projet, suppression des worktrees.

## Journal

- 2026-10-27 15:27 · run · décision · ancien run archivé, epic 17 créé, constats CT-01 à CT-05 précisés par Anaël · —
