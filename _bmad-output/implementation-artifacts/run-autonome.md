# Run autonome : SLM supplémentaires (specs A et B)

Lancé le 2026-10-24 à la demande d'Anaël. Plan et raisons des choix : [plan-slm-supplementaires.md](plan-slm-supplementaires.md).

## Périmètre

| Périmètre | Epics | Note |
|---|---|---|
| Dans le run | Specs SLM A à B | A : [spec-slm-a-modeles-facultatifs-installateurs.md](spec-slm-a-modeles-facultatifs-installateurs.md) ; B : [spec-slm-b-appels-json-tool-call.md](spec-slm-b-appels-json-tool-call.md) |
| Hors run | Spec SLM C | Gemma 4, en attente du benchmark de SLM |

Au plus 1 stories en développement à la fois

## Sprint 1 — SLM supplémentaires

| Vague | Stories en parallèle | Après |
|---|---|---|
| V0 | A | — |
| V1 | B ★ | B ← A |

B ← A : B ajoute ses entrées d'installateur à la liste créée par A.

## Règles du run

- Par story : `dev-story` (Sonnet), puis `second-avis` (Haiku), puis `reviewer` (Opus, avec la liste du second avis), puis PR, CI verte et fusion. Une seule passe de revue.
- Poste de développement : un benchmark de SLM y tourne. On n'y lance ni modèle réel, ni suite complète : seulement ruff (contrôle rapide) et des tests ciblés. La CI de la PR (Windows, Ubuntu) sert de suite complète et de porte de fusion.
- `gh run watch <id> --interval 60`. Après `gh pr merge`, vérifier l'état `MERGED` avant de journaliser.
- Ce fichier vit sur la branche `chore/etat-run`, hors des PR de story.
- Attente humaine en fin de run : essais réels sur le PC cible (Qwen3.5-0.8B, Granite 4.0 1B et 350M, brique Outils, « Combien font 12 × 37 ? »).

## Décisions

- 2026-10-24 : exclure les SLM dont la licence ou l'exécution laisse un doute (voir le plan).
- 2026-10-24 : spec A, vérification sha256 des modèles facultatifs après téléchargement, et `-Models list`.

## Journal

- 2026-10-24 21:51 · run · décision · run autonome A puis B lancé · —
- 2026-10-24 21:52 · A · dev · lancé · —
- 2026-10-24 21:55 · A · dev · fini · f53f58f
- 2026-10-24 21:55 · A · second-avis · lancé · f53f58f
- 2026-10-24 21:56 · run · décision · benchmark en pause : tests locaux autorisés (suite complète en quatre quarts, une seule à la fois) · —
- 2026-10-24 21:59 · A · second-avis · 7 low, 0 medium/high ; empreinte 0.8B confirmée par téléchargement réel et tour Outils réel (444) · f53f58f
- 2026-10-24 21:59 · A · review · lancé · f53f58f
- 2026-10-24 22:00 · 1.2.0 · recette · MiniCPM5-2B réel : téléchargement -Models minicpm5 (1 561 318 368 octets, empreinte OK), tour Outils réel, lecteur minicpm5, calculatrice 444 en 5,2 s · —
- 2026-10-24 22:03 · A · review · 1 medium corrigé (-Models en session PowerShell), 3 low corrigés · b6380a8
- 2026-10-24 22:03 · A · PR · #86 ouverte, CI lancée · b6380a8
- 2026-10-24 22:22 · A · CI · rouge : Get-FileHash introuvable (powershell 5.1 lancé depuis pwsh) ; corrigé par SHA256 de .NET · 382834c
- 2026-10-24 22:35 · A · CI · verte (Windows, Ubuntu) · 382834c
- 2026-10-24 22:35 · A · fusion · #86 MERGED · 82e05ef
- 2026-10-24 22:35 · B · dev · lancé · ae6dba7
- 2026-10-24 22:40 · B · dev · fini ; essais réels Granite 1B (12,9 s) et 350M (4,6 s) : hermes, calculatrice 444 · 42e80dc
- 2026-10-24 22:40 · B · second-avis · lancé · 42e80dc
- 2026-10-24 22:47 · B · second-avis · 2 high (règle large : outils offerts à SmolLM3, Falcon-H1, EXAONE, Hunyuan), 3 medium, 3 low · 42e80dc
- 2026-10-24 22:47 · B · décision · Anaël : règle d'aller-retour (outils seulement si l'appel passé rendu par le gabarit est relu par hermes) · 00d67e9
- 2026-10-24 22:47 · B · review · lancé, avec la correction · 00d67e9
- 2026-10-24 22:55 · B · review · 8 constats corrigés (règle d'aller-retour, [|endofturn|], taille 0,2 Go…), 1 report (SmolLM3 servi par llama-server) · 3216834
- 2026-10-24 22:55 · B · recette · Granite 1B et 350M réels après revue : hermes, calculatrice 444 (3,1 s et 0,8 s) · 3216834
- 2026-10-24 22:55 · B · report · SmolLM3 servi par llama-server reçoit hermes par la branche qwen3 (deferred-work.md) · 4cca5dc
- 2026-10-24 22:55 · B · PR · #88 ouverte, CI lancée · 4cca5dc
- 2026-10-24 23:10 · B · CI · verte (Windows, Ubuntu) · 4cca5dc
- 2026-10-24 23:10 · B · fusion · #88 MERGED · 971f7c3
- 2026-10-24 23:10 · run · fin · A et B fusionnées ; recette réelle faite sur le poste de dev (Qwen3.5-0.8B, MiniCPM5-2B, Granite 4.0 1B et 350M) ; recette PC cible à faire par Anaël · 971f7c3
