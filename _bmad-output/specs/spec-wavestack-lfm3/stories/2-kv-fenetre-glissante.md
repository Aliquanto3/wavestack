---
title: 'Story 2 : KV par token avec attention à fenêtre glissante'
type: 'fix'
created: '2026-10-28'
status: 'draft'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/src/wavestack/models/probe.py'
  - '{project-root}/src/wavestack/models/servers.py'
  - '{project-root}/tests/test_probe.py'
---

## Intent

`probe.kv_bytes_per_token(meta)` (`models/probe.py:78-115`) renvoie les octets de cache KV
par token de contexte, f16 : `2 × Σ têtes KV × (key_length + value_length)`. Les couches sans
KV sont déjà exclues quand `head_count_kv` est une liste par couche (zéros des couches de
convolution ou récurrentes) ou par `full_attention_interval`. Les couches à fenêtre glissante
sont comptées comme si elles gardaient tout le contexte (docstring l.85).

LFM3-1.7B : 6 couches globales et 5 à fenêtre de 256, 4 têtes KV de 128, soit 2 048 octets par
couche et par token. Aujourd'hui 11 × 2 048 = 22 528 octets par token ; la part qui croît avec
le contexte n'est que de 6 × 2 048 = 12 288. À `-c 16384`, cela fait 369 Mo estimés au lieu
d'environ 201 Mo.

La règle est générique : toute architecture dont le GGUF porte `{arch}.attention.sliding_window`
et `{arch}.attention.sliding_window_pattern`. llama.cpp lit le motif avec `get_key_or_arr` :
une liste d'un booléen par couche (vrai = fenêtre glissante), ou une valeur seule appliquée à
toutes les couches. Gemma 2 et 3 portent `sliding_window` sans motif (codé en dur dans
llama.cpp) : rien ne change pour eux.

Ce qui reste fixe (les couches à fenêtre gardent environ `fenêtre × emplacements + ubatch`
tokens) n'est pas une quantité par token : cette story l'expose par une aide, et la story 3
l'ajoute à la mémoire d'un modèle servi.

L'économie n'existe que si le moteur alloue un cache réduit. llama-server le fait par défaut
(`--swa-full` absent). La valeur par défaut de llama-cpp-python (`swa_full` du contexte) est à
lire dans le paquet installé (tâche 2) : elle décide du chemin direct.

## Given/When/Then

- Given les métadonnées LFM3 (24 couches, `head_count_kv` par couche à 0 pour les
  convolutions et à 4 ailleurs, `key_length = value_length = 128`, `sliding_window = 256`,
  motif vrai sur les 5 couches à fenêtre), When `kv_bytes_per_token(meta, sliding=True)`,
  Then 12 288.
- Given les mêmes métadonnées, When `kv_bytes_per_token(meta)` (défaut `sliding=False`),
  Then 22 528 (comportement actuel, rien ne change pour les appelants non modifiés).
- Given un motif sous forme de valeur seule vraie (toutes les couches à fenêtre), When
  `kv_bytes_per_token(meta, sliding=True)`, Then 0 octet par token pour la part croissante, et
  `sliding_kv(meta)` renvoie la part fixe de toutes les couches.
- Given `sliding_window` présent sans motif (Gemma 3), ou un motif sans `sliding_window`
  (ou à 0), When `kv_bytes_per_token(meta, sliding=True)`, Then la même valeur que sans
  `sliding` (pas de motif deviné).
- Given un motif dont la longueur diffère de `block_count` ou de la liste `head_count_kv`,
  When `kv_bytes_per_token(meta, sliding=True)`, Then le motif est ignoré (valeur sans
  `sliding`), jamais d'exception.
- Given les métadonnées LFM3, When `sliding_kv(meta)`, Then `(10 240, 256)` : 5 couches ×
  2 048 octets par token, fenêtre de 256 ; `None` sans fenêtre ou sans motif lisible.
- Given un fichier LFM3 servi par llama-server, chemin absolu lisible, When `served_kv`,
  Then 12 288 (la part croissante seulement).
- Given les en-têtes Qwen3.5 (`QWEN35_2B`, `full_attention_interval`), When le calcul
  s'applique avec ou sans `sliding`, Then 12 288 et 32 768, inchangés.

## Tâches

1. Relever l'en-tête réel : sur `LFM3-1.7B-QAD-Q4_0.gguf` (relevé déjà fait le 2026-10-28, rapport de mesures, écart 2 : `sliding_window_pattern` = liste de 24 booléens, vrai aux couches 4, 8, 12, 16, 20 ; `sliding_window` = 256 ; `head_count_kv` = 4 sur les 11 couches d'attention, 0 ailleurs ; fichier dans le scratchpad de la session ac4fd306, `lfm3/`, s'il existe encore), lire les clés `lfm3.*`
   avec `wavestack.models.gguf_meta.try_read_metadata` (script dans un fichier temporaire, via
   `uv run python fichier.py`, jamais `python -`). Noter la forme exacte de
   `head_count_kv` (liste par couche attendue), de `sliding_window_pattern` (liste de booléens
   attendue, une entrée par couche, ou une par couche d'attention seulement), la présence de
   `shortconv.*`. Recopier ces valeurs dans une constante `LFM3_1_7B` de `tests/test_probe.py`,
   sur le modèle de `QWEN35_2B` (l.422), avec la date et le poste du relevé. Si le motif ne
   suit pas la forme « une entrée par couche », adapter la tâche 3 et le dire dans le rapport.
2. Lire dans `.venv` la valeur par défaut de `swa_full` (`llama_cpp/llama_cpp.py`,
   `llama_context_default_params`, et `llama_cpp/llama.py`, `Llama.__init__`). Règle :
   - si `Llama` crée le contexte avec `swa_full` vrai (ou ne l'expose pas et la valeur par
     défaut de llama.cpp est vraie), le chemin direct garde `sliding=False` (le cache est
     alloué en entier) ;
   - sinon, les appels du chemin direct passent `sliding=True` (tâche 5). Écrire la valeur lue
     dans le rapport.
3. `src/wavestack/models/probe.py`, `kv_bytes_per_token(meta, *, sliding: bool = False)` :
   - construire la liste par couche des têtes KV (la liste de `head_count_kv`, ou l'entier
     répété `block_count` fois quand il n'y a pas de `full_attention_interval`) ;
   - avec `sliding` et un motif valide (`_sliding_layers(meta)`, nouvelle aide privée : la
     liste de booléens par couche, ou `None`), ne sommer que les couches dont le drapeau est
     faux ;
   - le cas `full_attention_interval` reste tel quel (pas de motif combiné) ;
   - corriger la docstring (fenêtre glissante prise en compte avec `sliding`).
4. `probe.sliding_kv(meta) -> tuple[int, int] | None` : `(octets par token des couches à
   fenêtre, fenêtre)`, même formule `2 × têtes × (k + v)` sur les seules couches du motif.
   Utilisée par la story 3.
5. `probe.gguf_kv_bytes_per_token(path, *, sliding=False)` et `_header_kv(path, size, mtime,
   sliding=False)` (le drapeau entre dans la clé du `lru_cache`). `servers.served_kv`
   (`servers.py:1022-1028`) passe `sliding=True`. `ollama_load_bytes` (l.1007) et les appels
   d'`app_session.py` (l.1964, 1978, 2873, 2875) gardent `False` pour Ollama (moteur à part,
   allocation non vérifiée) ; pour les fichiers en direct, selon la tâche 2.
6. Ne pas changer `PROBE_VERSION` : `probed_entry` (l.355-369) recalcule déjà
   `kv_bytes_per_token` depuis l'en-tête à chaque lecture.

## Tests

- `tests/test_probe.py` : section « fenêtre glissante » après celle du lot K (l.418) :
  `LFM3_1_7B` avec et sans `sliding`, `sliding_kv`, motif valeur seule, motif de longueur
  fausse, Gemma 3 sans motif, `QWEN35_2B`/`QWEN35_4B` inchangés ; test GGUF écrit par
  `tests/gguf_writer.py` (liste de booléens) lu par `gguf_kv_bytes_per_token(path,
  sliding=True)`, comme l.279 et l.300.
- `tests/test_model_servers.py` : `test_llama_server_memory_counts_its_whole_context`
  (l.1653) et `test_llama_server_with_several_slots_counts_the_whole_context` (l.1710) restent
  verts (le tiny-llama n'a pas de fenêtre) ; nouveau cas : GGUF LFM3 écrit par
  `gguf_writer`, `served_kv` donne 12 288.
- `tests/test_llm_lab.py` : `classify_header(LFM3_1_7B)` donne `hybrid` (vérifie qu'il n'y a
  pas besoin d'ajouter `lfm3` à `HYBRID_ARCHITECTURES`).
- `uv run pytest -q --tb=short tests/test_probe.py tests/test_model_servers.py tests/test_llm_lab.py tests/test_memory_budget.py`
- `uv run python .claude/cost-kit/controle_rapide.py`

## E2E à rejouer (non lancé par cette story)

Aucun : le calcul n'est visible qu'au diagnostic d'un modèle servi, sans scénario LFM3.

## Choix faits à la place d'Anaël

- Drapeau `sliding` explicite plutôt qu'une règle par moteur cachée dans le calcul : la
  fonction reste pure, chaque appelant dit ce que son moteur alloue.
- Ollama garde le calcul complet : son allocation de cache à fenêtre n'est pas vérifiée, une
  surestimation ne casse rien.
