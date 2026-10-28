# Run autonome LFM3 (2026-10-28)

Spec : `_bmad-output/specs/spec-wavestack-lfm3/`. Enchaînement par story : dev-story → second-avis → reviewer → PR → CI verte → fusion.

## Périmètre

| Périmètre | Epics | Note |
|-----------|-------|------|
| Dans le run | Epics 1 à 1 | Stories LFM3 1 (PR seule, déjà revue), 2 et 3 |

Au plus 1 stories en développement à la fois

## Sprint 1 — LFM3

| Vague | Stories en parallèle | Après |
|-------|----------------------|-------|
| V0 | 1 · 2 | — |
| V1 | 3 | 3 ← 2 |

## Règles et décisions

- 2026-10-28 : vérification préalable de la story 3 : `psutil.net_connections` trouve sans droits admin (session non élevée) le PID d'un processus enfant à l'écoute, en 5 ms, et `memory_info().rss` est lisible.
- 2026-10-28 : llama-cpp-python 0.3.35 crée le contexte avec `swa_full = True` par défaut et WaveStack ne le passe jamais : le chemin direct garde le calcul KV complet (story 2).
- Story 2 part de la branche de la story 1 (même fichier `probe.py`) ; sa PR est reciblée sur `main` après fusion de #166.

## Journal

- 2026-10-28 09:46 · 1 · PR · #166 ouverte · 75439216
- 2026-10-28 09:52 · 2 · dev · spec prête, lancé · f92da5ba
- 2026-10-28 09:58 · 1 · CI · verte (8/8) · 75439216
- 2026-10-28 09:59 · 1 · fusion · #166 fusionnée (squash) · dc846bdc
- 2026-10-28 10:06 · 2 · dev · fini, rebasée sur main, 291 tests verts · 2e596cfd
- 2026-10-28 10:06 · 2 · second-avis · lancé · 2e596cfd
- 2026-10-28 10:13 · 2 · second-avis · 6 constats (1 medium) · 2e596cfd
- 2026-10-28 10:13 · 2 · review · 2 medium corrigés, 1 low différé, relu par l'orchestrateur · 63a1afb5
- 2026-10-28 10:13 · 2 · PR · #167 ouverte · 63a1afb5
- 2026-10-28 10:13 · 3 · dev · spec prête, lancé depuis la branche de la story 2 · 79a066db
- 2026-10-28 10:25 · 2 · CI · verte (8/8) · 63a1afb5
- 2026-10-28 10:25 · 2 · fusion · #167 fusionnée (squash) · 7119e8e7
- 2026-10-28 10:30 · 3 · dev · fini, rebasée sur main · ddfb0301
- 2026-10-28 10:30 · 3 · second-avis · lancé · ddfb0301
- 2026-10-28 10:35 · 3 · second-avis · 5 constats (1 medium) · ddfb0301
- 2026-10-28 10:35 · 3 · review · lancé · ddfb0301
- 2026-10-28 10:44 · 3 · review · 2 medium corrigés, 2 low différés, relu par l'orchestrateur · b8175103
- 2026-10-28 10:44 · 3 · PR · #168 ouverte · b8175103
- 2026-10-28 10:54 · 3 · CI · verte (8/8) · b8175103
- 2026-10-28 10:54 · 3 · fusion · #168 fusionnée (squash) · 46fb1580
- 2026-10-28 10:55 · run · décision · run terminé : stories 1, 2 et 3 fusionnées (#166, #167, #168) · 46fb1580
