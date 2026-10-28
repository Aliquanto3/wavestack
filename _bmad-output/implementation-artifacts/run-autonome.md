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
- Run terminé le 2026-10-28 : 17.1 à 17.5 fusionnées, version 1.7.1.
- Fin de run : rapport `rapport-run-recette-v1-7-0.md`, version 1.7.1, mémoire du projet, suppression des worktrees.

## Journal

- 2026-10-27 15:27 · run · décision · ancien run archivé, epic 17 créé, constats CT-01 à CT-05 précisés par Anaël · —
- 2026-10-27 15:31 · run · décision · PR #158 (état du run) en fusion automatique après CI · —
- 2026-10-27 15:31 · 17.1, 17.2, 17.3 · dev · lancé (Sonnet) · —
- 2026-10-27 16:17 · 17.1 · dev · fini · 9e0128d3
- 2026-10-27 16:17 · 17.1 · second-avis · 3 medium, 3 low · 9e0128d3
- 2026-10-27 16:17 · 17.1 · review · 6 constats corrigés (360 px réel : panneau hors fenêtre, nav en nowrap) ; E2E bar_journal bar_panels 35 OK · 068de1e3
- 2026-10-27 16:17 · 17.1 · fusion · PR #159 MERGED, CI 8/8 · ef733ee0
- 2026-10-27 16:17 · 17.1 · report · à 360 px la page Harnais fait 646 px de large (contenu de la page, hors barre) · —
- 2026-10-27 16:17 · 17.2 · décision · à revoir : le coût d'un modèle gratuit disparaissait (empreinte seule) ; ajout « 0 $, offre gratuite » · 046dddae
- 2026-10-27 16:17 · 17.2 · report · l'Atelier RAG n'indique pas l'offre gratuite (règle propre, rag/lab.py) · —
- 2026-10-27 16:17 · 17.5 · dev · lancé (Sonnet) · —
- 2026-10-27 16:29 · 17.4 · dev · lancé (Sonnet) · —
- 2026-10-27 16:29 · 17.2 · review · E2E llm_screen réaligné (faux modèle cloud sans prix) ; texte anglais $0 ; E2E 66 OK · 5bfbdc66
- 2026-10-27 16:29 · 17.2 · fusion · PR #160 MERGED, CI 8/8 · dbef8d41
- 2026-10-27 16:29 · 17.3 · second-avis · 3 medium, 3 low · d7440e2a
- 2026-10-27 16:29 · 17.3 · review · filtre invert interdit par test_web_tokens → logos -white.svg ; « Avant MCP » suit le modèle (zone Réseau) ; schémas reconstruits au changement de modèle · 1e2e929c
- 2026-10-27 16:29 · 17.3 · décision · à revoir : libellé cloud « LLM cloud » ; robot sans nom du fournisseur en cloud · 1e2e929c
- 2026-10-27 16:29 · 17.5 · dev · fini · e59702d5
- 2026-10-27 17:02 · 17.3 · CI · rouge deux fois (littéral français dans mcp/lab.py, puis ruff format), corrigé · —
- 2026-10-27 17:02 · 17.3 · fusion · PR #161 MERGED, CI 8/8, E2E mcp_lab mcp_lab_page 55 OK · 9d3fb982
- 2026-10-27 17:02 · 17.5 · second-avis · 1 medium (vue carte 560 px, pré-existant), 7 low · e59702d5
- 2026-10-27 17:02 · 17.5 · review · compteur O(1), role=status fiable, E2E renforcé ; E2E security_page 43 OK · ad56a32a
- 2026-10-27 17:02 · 17.5 · fusion · PR #162 MERGED, CI 8/8 · 6b0bd7df
- 2026-10-27 17:02 · 17.5 · report · vue en cartes sous 560 px de la maquette absente depuis 16.7 · —
- 2026-10-27 17:02 · 17.4 · dev · fini · befab6d7
- 2026-10-27 17:02 · 17.4 · second-avis · 1 medium (course amorçage /api/state vs /api/rag_lab), 4 low (libellé « onglet Atelier RAG » absent de la page, pas de test de (a)) · befab6d7
- 2026-10-27 17:02 · run · décision · pause demandée par Anaël (démo) : fusion de ce qui était prêt, 17.4 en attente de revue · —
- 2026-10-28 07:26 · run · décision · reprise demandée par Anaël : revue 17.4 puis version 1.7.1 · —
- 2026-10-28 07:26 · 17.4 · décision · à revoir : revue par `reviewer` (protocole du run) plutôt que les trois couches de `bmad-build` step-04 · —
- 2026-10-28 07:41 · 17.4 · review · course d'amorçage corrigée (rétrogradée en low), libellé « onglet Atelier RAG » rejeté (tab_rag existe), E2E cas (a) ajouté · 12e91186
- 2026-10-28 07:41 · 17.4 · E2E · rag rag_rerank rag_lab_no_index 90 OK · 12e91186
- 2026-10-28 07:41 · 17.4 · PR · #164 ouverte, CI en cours · 12e91186
- 2026-10-28 08:00 · 17.4 · fusion · PR #164 MERGED, CI 8/8 · a9b14f1f
- 2026-10-28 08:00 · run · version · 1.7.1 (manifeste, rapport rapport-run-recette-v1-7-0.md) · —
