# Plan : SLM supplémentaires (après MiniCPM5-2B)

Proposition du 2026-10-24, resserrée le même jour. Décision d'Anaël : on exclut les SLM dont la licence ou l'exécution laisse un doute. Deux specs en brouillon, à passer par `bmad-build`, qui reprend à l'étape de plan. Aucun modèle n'a été lancé sur le poste de développement, où un benchmark de SLM tourne en parallèle. Les essais réels se font sur le PC cible.

## Constat (vérifié le 2026-10-24)

Pour 21 GGUF de Hugging Face, j'ai lu l'architecture et le gabarit de l'en-tête (API `?expand[]=gguf`), puis je les ai passés dans `capabilities_for` et dans `render_template`, avec un outil et un appel passé :

- **Chargement** : les 15 architectures sont toutes connues du llama.cpp embarqué (llama-cpp-python 0.3.35).
- **Ce qui manque** : la lecture des appels d'outils. Seuls les gabarits Qwen3 et MiniCPM5 (PR #82) sont lus.
- **Modèles hybrides** : le moteur (`engine.py`, `prefill`) repart déjà de zéro quand le cache ne peut pas être tronqué, comme pour Qwen3.5.

## Specs retenues

| Vague | Spec | Après | Fichiers principaux |
|---|---|---|---|
| V0 | A | — | `install.ps1`, `install.sh`, `tests/test_installers.py`, docs |
| V1 | B | A (pour les entrées d'installateur) | `capabilities.py`, fixtures, `publishers.yaml`, installateurs, docs |

B peut démarrer en parallèle de A pour sa partie code (`capabilities.py`, tests). Ses entrées d'installateur se font une fois A fusionnée.

- A, [spec-slm-a-modeles-facultatifs-installateurs.md](spec-slm-a-modeles-facultatifs-installateurs.md) : une liste de modèles facultatifs dans les installateurs (`-Models`), avec **Qwen3.5-0.8B** (aucun code : même gabarit que le 2B) et MiniCPM5.
- B, [spec-slm-b-appels-json-tool-call.md](spec-slm-b-appels-json-tool-call.md) : **Granite 4.0 350M et 1B** (non-H), appels JSON `<tool_call>` lus par `hermes`.

## Écartés

| Modèle | Raison | Pour y revenir |
|---|---|---|
| Gemma 4 E2B / E4B | Exécution : 3,1 Go et 5 Go en Q4_K_M, jamais essayé sur le PC cible. La licence ne pose pas de problème (Apache-2.0, vérifiée sur ai.google.dev) | Spec en attente : [spec-slm-c-gemma-4.md](spec-slm-c-gemma-4.md), à reprendre si le benchmark est bon |
| SmolLM3-3B | Exécution : 3B, trop près du budget mémoire | Benchmark |
| Granite 4.0-H 350M / 1B | Exécution : modèle hybride, cache non réutilisé entre les tours. Il est reconnu de fait (même gabarit que Granite), mais n'est ni proposé ni recommandé | Benchmark (temps par tour) |
| Falcon-H1 1.5B | Licence propre (Falcon LLM License, TII), modèle hybride | — |
| EXAONE 4.0 1.2B | Licence « research and educational purposes » seulement | — |
| LFM2.5 350M / 1.2B | Licence : usage commercial non couvert au-delà de 10 M$ de chiffre d'affaires ; format d'appel connu par la fiche seulement | — |
| Ministral 3 3B | Exécution : 3B, près du budget mémoire | Benchmark |
| Llama 3.2 1B | Appels en JSON nu, sans balise, peu fiables à lire | — |
| Phi-4-mini | Son gabarit ignore la variable `tools` | — |
| Gemma 3 270M / 1B | Son gabarit refuse le rôle `tool` ; il reste utilisable en conversation | — |
| Hunyuan 1.8B | Format d'appel non vérifié | — |
