# Run autonome : retours du 27/10 (v1.7.0)

Lancé le 2026-10-27 à la demande d'Anaël, après le run V1.5 (archivé dans [run-autonome-v15-2026-10-25.md](run-autonome-v15-2026-10-25.md)). Orchestration : session principale Opus 5.5.

## Périmètre

| Périmètre | Epics | Note |
|---|---|---|
| Dans le run | Epics 16 à 16 | epic 16 dans `sprint-status.yaml` ; story 16.N = id N de `stories.yaml` |
| Hors run | Recette guidée des sous-onglets RAG | session dédiée après le lot |

Spec : `_bmad-output/specs/spec-wavestack-retours-2026-10-27/` (SPEC.md, brownfield.md, stories.yaml). Specs de story dans `stories/story-N.md` du même dossier.

Au plus 3 stories en développement à la fois (la maquette 16.4 et les phases de spec ne comptent pas)

## Sprint 1 — Retours du 27/10

| Vague | Stories en parallèle | Après |
|---|---|---|
| V0 | 16.1 ★ · 16.2 · 16.3 · 16.4 (humaine) | 16.1 : spec relue par Anaël avant le code ; 16.4 : maquette avec bmad-ux, validée par Anaël |
| V1 | 16.5 · 16.6 · 16.7 | 16.6 ← 16.3 ; 16.7 ← 16.1 ; 16.7 ← 16.4 ; 16.6 : spec relue par Anaël |
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

## Décisions

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
