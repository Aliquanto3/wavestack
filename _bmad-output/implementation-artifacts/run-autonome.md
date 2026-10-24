# Run autonome de nuit : V1.3, V1.4 puis V1.2

Lancé le 2026-10-24 à la demande d'Anaël, après le run SLM A/B (archivé dans [run-autonome-slm-2026-10-24.md](run-autonome-slm-2026-10-24.md)). Orchestration : session principale Opus 5.5.

## Périmètre

| Périmètre | Epics | Note |
|---|---|---|
| Dans le run | V1.3, V1.4, V1.2 | priorité stricte par lot ; V1.2 : PR #79 (story 1) puis stories 2 à 21 |
| Hors run | V2, SLM C | spec V2 en brouillon ; SLM C en attente du benchmark |

Specs : `_bmad-output/specs/spec-wavestack-cache-visible/` (V1.3), `spec-wavestack-etat-de-l-art-harnais/` (V1.4), `spec-wavestack-v1-2-atelier-recherche-documentaire/` (V1.2).

Au plus 2 stories en développement à la fois

## Sprint 1 — V1.3 cache visible

| Vague | Stories en parallèle | Après |
|---|---|---|
| V0 | 1.3-1 ★ | — |
| V1 | 1.3-2 · 1.3-5 | 1.3-2 ← 1.3-1 ; 1.3-5 ← 1.3-1 |
| V2 | 1.3-3 · 1.3-4 | 1.3-3 ← 1.3-2 ; 1.3-4 ← 1.3-1 |
| V3 | 1.3-6 | 1.3-6 ← 1.3-2 ; 1.3-6 ← 1.3-3 ; 1.3-6 ← 1.3-4 |

## Sprint 2 — V1.4 état de l'art des harnais

| Vague | Stories en parallèle | Après |
|---|---|---|
| V0 | 1.4-1 · 1.4-3 | 1.4-3 ← 1.2-1 (PR #79) |
| V1 | 1.4-2 | 1.4-2 ← 1.4-1 |
| V2 | 1.4-4 ★ | 1.4-4 ← 1.4-2 ; 1.4-4 ← 1.3-3 |

## Sprint 3 — V1.2 atelier recherche documentaire

| Vague | Stories en parallèle | Après |
|---|---|---|
| V0 | 1.2-1 | PR #79 : rebase, CI, fusion (revue déjà faite) |
| V1 | stories 2 à 21 | vagues fixées à l'entrée du sprint d'après stories.yaml de la V1.2 |

## Règles du run

- Par story : `dev-story` (Sonnet ; Opus pour 1.4-4), `second-avis` (Haiku), `reviewer` (Opus, avec la liste du second avis, rebasé sur `origin/main`), PR, CI verte, fusion, vérification `MERGED`, journal.
- Points de contrôle (décision d'Anaël du 2026-10-24) : `done_checkpoint` levés. `spec_checkpoint` : `dev-story` écrit la spec de story et s'arrête ; `reviewer` la relit contre SPEC.md, maquettes et brownfield.md, tranche les points ouverts ; `dev-story` reprend. Chaque choix fait à la place d'Anaël : ligne `décision · à revoir`.
- Local : contrôle rapide et tests ciblés seulement ; la CI de la PR (Windows, Ubuntu) sert de suite complète.
- `gh run watch <id> --interval 60` ; worktrees `../wavestack-<lot>-s<n>`, `git worktree prune` avant chaque lancement, suppression en fin de run.
- Ce fichier vit sur `chore/etat-run`, hors des PR de story.
- Arrêt seulement pour une ressource ou une décision d'Anaël (modèle réel, clé cloud, accès Jev, annotation, PC cible) : notification, `attente humaine`, on avance ailleurs.
- Fin de lot : PR de version (SemVer mineure suivante), tag annoté, release GitHub.

## Décisions

- 2026-10-24 : ordre V1.3, V1.4, V1.2 ; points de contrôle levés pour la nuit, revus au matin (Anaël).

## Journal

- 2026-10-24 23:10 · run · décision · run de nuit V1.3, V1.4, V1.2 lancé ; PR #87 (spec V1.4) MERGED 8174efc · —
- 2026-10-24 23:10 · 1.2-1 · CI · PR #79 rebasée sur main, CI lancée · 13453c9
