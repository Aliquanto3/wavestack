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
- 2026-10-24 23:11 · 1.2-1 · fusion · #79 MERGED · 72cfdf0
- 2026-10-24 23:11 · 1.3-1 · dev · lancé (phase spec) · 72cfdf0
- 2026-10-24 23:12 · 1.4-1 · dev · lancé (créneau libre pendant la V1.3-1) · 72cfdf0
- 2026-10-24 23:13 · 1.3-1 · dev · spec prête (phase 1) · dd32e23
- 2026-10-24 23:13 · 1.3-1 · review · relecture de la spec lancée · dd32e23
- 2026-10-24 23:15 · 1.3-1 · review · spec approuvée après 4 corrections importantes (lecture locale sans last_cache_reuse, collision cache_savings, règle d'écriture par pivot, tests listés) · 23e84c8
- 2026-10-24 23:15 · 1.3-1 · décision · à revoir : non caché local = None « sans objet », distingué par cache_origin · 23e84c8
- 2026-10-24 23:15 · 1.3-1 · décision · à revoir : champ cache_write_1h_tokens ajouté dès la story 1 (Anthropic ephemeral_1h) pour les stories 4 et 5 · 23e84c8
- 2026-10-24 23:15 · 1.3-1 · décision · à revoir : cache_origin None seulement pour une trace antérieure ; usage estimé = provider, cases None · 23e84c8
- 2026-10-24 23:15 · 1.3-1 · dev · phase 2 (code) lancée · 23e84c8
- 2026-10-24 23:17 · 1.4-1 · dev · fini ; E2E disciplines 52 OK (PYTHONUTF8=1 requis sous Windows) ; skills tiers dans hooks, échafaudage dans native_tools · f916b57
- 2026-10-24 23:17 · 1.4-1 · décision · à revoir : scénario de sécurité des skills tiers = hooks · f916b57
- 2026-10-24 23:17 · 1.4-1 · second-avis · lancé · f916b57
- 2026-10-24 23:18 · 1.4-3 · dev · lancé · 72cfdf0
- 2026-10-24 23:21 · 1.3-1 · dev · fini ; contrat : cache_origin, cache_read_tokens, cache_write_tokens, cache_write_1h_tokens, cache_uncached_tokens (int | None) · ab89fb3
- 2026-10-24 23:21 · 1.3-1 · second-avis · lancé · ab89fb3
