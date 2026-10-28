# Support de LiquidAI LFM3-1.7B

Source : essais du 2026-10-28 sur un autre poste (llama-server b11938+, llama-cpp-python 0.3.36), relecture du code de `main` (ea21ac7a) et des fichiers publiés sur Hugging Face (`LiquidAI/LFM3-1.7B`, `LiquidAI/LFM3-1.7B-GGUF`) ; mesures du 2026-10-28 sur le PC cible, llama.cpp b11938, `LFM3-1.7B-QAD-Q4_0.gguf`, code de `main` à 6206790e (v1.7.1) : `rapport-mesures-2026-10-28.md`.
Objectif : un fichier LFM3 est reconnu pour ce qu'il est, en direct comme servi par llama-server (capacités, éditeur), et la mémoire d'un modèle servi est celle que son processus occupe vraiment (mémoire résidente lue, décision d'Anaël du 2026-10-28), son KV estimé sans le gonfler (fenêtre glissante). Correctifs seulement, sans fonction nouvelle.

Stories : `stories.yaml` (id N). Specs de story dans `stories/N-slug.md`. Ajustées le 2026-10-28 avec les mesures du PC cible (16 Go) : `rapport-mesures-2026-10-28.md`.

## Le modèle

- Architecture GGUF `lfm3`. 24 couches (`config.json`, `layer_types`) : 13 convolutions courtes (sans cache KV), 5 attentions à fenêtre glissante de 256 tokens, 6 attentions globales. 4 têtes KV de 128. Contexte natif de 262 144 tokens. GGUF de 1,05 Go (QAD-Q4_0) à 3,47 Go (F16), 1,10 Go en Q4_K_M.
- Le GGUF porte `lfm3.attention.sliding_window` (256) et `lfm3.attention.sliding_window_pattern` (relevé sur le fichier réel : liste de 24 booléens, vrai aux couches 4, 8, 12, 16, 20) ; `head_count_kv` par couche (4 sur les 11 couches d'attention, 0 ailleurs).
- Template ChatML (`<|im_start|>`, `<|im_end|>`), appels `<tool_call><function=…><parameter=…>` (format `qwen3_coder`), `enable_thinking` (vrai par défaut), `<think>`, blocs `{% generation %}` (déjà rendus par `context/render.py`).
- llama-cpp-python ≤ 0.3.36 ne connaît pas `lfm3` : le chargement en direct échoue. llama.cpp le connaît depuis b11938. Avec llama-server, tout marche sans code : famille `qwen3` reconnue par le template, appels d'outil corrects avec et sans raisonnement. Mémoire mesurée sur le PC cible (QAD-Q4_0, `-c 16384`) : 2,1 Go résidents, 1,2 Go privés, avec `-np 4` comme `-np 1` (cache unifié : les emplacements coûtent ≈ 10 Mo). Environ 800 Mo privés viennent du réarrangement des poids Q4_0 pour le CPU (repack) ; avec `--no-repack`, 1,3 Go résidents et 412 Mo privés (KV ≈ 195 Mo + tampons de calcul ≈ 200 Mo), mais génération −25 % et lecture du prompt −45 %.

## Les trois écarts

1. **Capacités en direct.** `capabilities_for` (`models/capabilities.py:103`) ne reconnaît le template façon Qwen3 que sans architecture (`by_template`, l.142-146), sinon par `arch.startswith("qwen3")` (l.164). Avec `architecture="lfm3"` (lecture de l'en-tête par le catalogue, ou un futur llama-cpp-python), le template contient `<function=` : il échoue aussi à la branche `hermes` (l.175) et tombe au cas générique, sans analyseur d'appels ni arrêt. Effet de bord constaté : servi par llama-server avec un chemin `-m` relatif (en-tête illisible), la famille `qwen3` déduite du template passe avant le nom dans `catalog.publisher_for` : LFM3 est rangé chez « Qwen (Alibaba) ». Le message d'échec en direct existe déjà (`models.probe.incompatible` cite l'architecture non prise en charge et llama-server) mais ne nomme pas l'architecture.
2. **KV par token.** `probe.kv_bytes_per_token` (`models/probe.py:78`) compte toutes les couches d'attention pour tout le contexte (docstring l.85 : « Sliding-window attention is not taken into account »). Les couches de convolution sont déjà exclues par la liste `head_count_kv` à zéros (cas LFM2). Pour LFM3 : 22 528 octets par token au lieu de 12 288 pour la part qui croît avec le contexte (×1,8).
3. **Mémoire d'un modèle servi.** `servers.served_bytes` (`models/servers.py:983`) : taille du fichier + KV × `n_ctx`, soit 1 353 Mo pour LFM3 contre 2 112 Mo résidents mesurés. Ni le repack ni les tampons de calcul ne sont comptés, et un chemin `-m` relatif (`_local`, l.1031) n'est pas lu : l'estimation se réduit alors à la taille du fichier. Décision d'Anaël (2026-10-28) : le budget compte la **mémoire résidente** du processus llama-server, **lue** avec psutil (processus à l'écoute du port du serveur), plutôt qu'estimée. L'estimation reste en repli quand le processus est introuvable ou illisible. Les emplacements (`-np`) sortent du périmètre : le cache est unifié et la lecture les compte de toute façon.

## Hors périmètre

- Pas de mise à jour imposée de llama-cpp-python (`pyproject.toml` : `>=0.3.35,<0.4`). Quand une version connaîtra `lfm3`, la story 1 suffit pour le direct.
- Pas d'ajout de LFM3 au catalogue de téléchargement : en direct il ne se charge pas avec la version installée, et proposer de télécharger un modèle inutilisable en direct serait trompeur. À reconsidérer avec la mise à jour de llama-cpp-python.
- Pas de table des motifs de fenêtre glissante par architecture (Gemma 2 et 3 : motif codé en dur dans llama.cpp, absent du GGUF) : sans la clé `sliding_window_pattern`, le calcul reste celui d'aujourd'hui (surestimation sans danger).
- Pas d'option `--no-repack` proposée ni recommandée par WaveStack : elle ralentit la génération de 25 %, et la mémoire lue suit de toute façon le choix de l'utilisateur.
- Pas de part fixe du cache à fenêtre glissante par emplacement dans l'estimation de repli (≈ 2,5 Mo par emplacement pour LFM3, cache unifié).
- `HYBRID_ARCHITECTURES` (`session/llm_lab.py:607`) : pas besoin d'y ajouter `lfm3`, la liste `head_count_kv` à zéros (ou les clés `shortconv.`) suffit à classer le modèle en hybride. À vérifier sur l'en-tête réel (story 2, tâche 1).

## Ordre et dépendances

| Vague | Stories | Après |
|---|---|---|
| V0 | 1 · 2 | — |
| V1 | 3 | 3 ← 2 (même fichier `servers.py`) |

Les stories 1 et 2 ne partagent que `probe.py`, à des endroits différents (message d'échec de la sonde ; `kv_bytes_per_token`). La story 3 ne dépend pas du code de la story 2, seulement de son fichier `servers.py` : elle passe après sa fusion pour éviter les conflits.

## Fichiers partagés

- `src/wavestack/models/probe.py` : story 1 (message d'échec), story 2 (calcul), lignes différentes.
- `src/wavestack/models/servers.py` : story 2 (`served_kv` passe `sliding=True`), story 3 (`served_bytes`, `_local`, lecture du processus). Story 3 après fusion de la 2.
- `tests/test_model_servers.py` : stories 2 et 3.
- `content/messages.yaml` (+ `content/i18n/{en,de}/messages.yaml`) : story 1 seulement.
- Fixture `tests/fixtures/lfm3_chat_template.jinja` (story 1) et métadonnées LFM3 relevées sur le GGUF réel (story 2, constante `LFM3_1_7B`).

Contraintes communes :
- Textes en fr dans `content/`, surcouches en et de sous `content/i18n/{en,de}/`, jamais de littéral français dans le code Python.
- `uv run`, ruff, tests ciblés en local ; E2E nommés dans le rapport, lancés par l'orchestrateur.
- Aucun test ne demande le vrai GGUF : en-têtes écrits par `tests/gguf_writer.py` ou dictionnaires de métadonnées, comme `QWEN35_2B` (`tests/test_probe.py:422`).
