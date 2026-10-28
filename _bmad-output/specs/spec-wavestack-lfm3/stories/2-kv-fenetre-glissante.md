---
title: 'Story 2 : KV par token avec attention à fenêtre glissante'
type: 'bugfix'
created: '2026-10-28'
status: 'ready-for-dev'
route: 'dispatch'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-lfm3/SPEC.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** `probe.kv_bytes_per_token(meta)` (`src/wavestack/models/probe.py:78`) compte les
couches à fenêtre glissante comme si elles gardaient tout le contexte : 22 528 octets par token
pour LFM3-1.7B au lieu de 12 288 (6 couches globales × 2 048). Un modèle servi par
llama-server, qui alloue un cache réduit pour ces couches, est donc surestimé (369 Mo au lieu
d'environ 201 Mo à `-c 16384`).

**Approach:** un drapeau `sliding=False` par défaut ; avec `sliding=True` et un motif
`{arch}.attention.sliding_window_pattern` valide (plus `{arch}.attention.sliding_window` > 0),
seules les couches globales comptent. Une aide `sliding_kv(meta)` expose la part fixe des
couches à fenêtre (utilisée par la story 3). Seul `servers.served_kv` passe `sliding=True`.

## Boundaries & Constraints

**Always:**
- Fonction pure : chaque appelant dit ce que son moteur alloue. Valeur par défaut inchangée
  (`sliding=False`) : aucun appelant non modifié ne voit de différence.
- Motif accepté sous deux formes, comme `get_key_or_arr` de llama.cpp : une liste d'un booléen
  par couche (longueur `block_count`, vrai = fenêtre glissante), ou une valeur seule appliquée à
  toutes les couches.
- Motif invalide (longueur différente de `block_count` ou de la liste `head_count_kv`, type
  inattendu), motif absent, ou `sliding_window` absent ou nul : motif ignoré, même valeur que
  sans `sliding`, jamais d'exception.
- Le cas `full_attention_interval` (Qwen3.5) reste tel quel : pas de combinaison avec un motif.

**Never:**
- Ne pas deviner un motif (Gemma 2 et 3 portent `sliding_window` sans motif : rien ne change).
- Ne pas passer `sliding=True` pour Ollama (`ollama_load_bytes`, `app_session.py` l.1978 et
  2875 : allocation non vérifiée) ni pour le chemin direct (llama-cpp-python 0.3.35 crée le
  contexte avec `swa_full = True` par défaut, lu le 2026-10-28 dans `.venv` ; WaveStack ne
  passe jamais `swa_full` : le cache direct est alloué en entier).
- Ne pas changer `PROBE_VERSION` : `probed_entry` recalcule déjà `kv_bytes_per_token` depuis
  l'en-tête à chaque lecture.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| LFM3, sliding | `LFM3_1_7B`, `sliding=True` | 12 288 | — |
| LFM3, défaut | `LFM3_1_7B`, sans `sliding` | 22 528 (inchangé) | — |
| Motif valeur seule vraie | `sliding_window_pattern = True`, `sliding=True` | 0 ; `sliding_kv` = part de toutes les couches | — |
| Fenêtre sans motif (Gemma 3) | `sliding_window` seul | même valeur qu'avec `sliding=False` | motif ignoré |
| Motif sans fenêtre / fenêtre 0 | motif présent, `sliding_window` absent ou 0 | même valeur qu'avec `sliding=False` | motif ignoré |
| Motif de longueur fausse | liste ≠ `block_count` ou ≠ liste `head_count_kv` | même valeur qu'avec `sliding=False` | jamais d'exception |
| `sliding_kv` LFM3 | `LFM3_1_7B` | `(10240, 256)` | `None` sans fenêtre ou motif lisible |
| Qwen3.5 | `QWEN35_2B` / `QWEN35_4B`, avec ou sans `sliding` | valeurs actuelles inchangées | — |
| Servi | GGUF LFM3 (écrit par `gguf_writer`) servi par llama-server, chemin absolu | `served_kv` = 12 288 | — |

</intent-contract>

## Code Map

- `src/wavestack/models/probe.py:78-115` -- `kv_bytes_per_token(meta)` : ajouter `*, sliding: bool = False` ; aujourd'hui trois branches (`head_count_kv` absent, liste, entier avec `full_attention_interval`). Corriger la docstring (l.85, « Sliding-window attention is not taken into account »).
- `src/wavestack/models/probe.py` (nouvelles aides près de l.78) -- `_sliding_layers(meta) -> list[bool] | None` (privée) et `sliding_kv(meta) -> tuple[int, int] | None` (publique, story 3).
- `src/wavestack/models/probe.py:379-401` -- `gguf_kv_bytes_per_token(path)` et `_header_kv(path, size, mtime)` (`lru_cache`) : ajouter `sliding=False`, qui entre dans la clé du cache.
- `src/wavestack/models/servers.py:1022-1028` -- `served_kv` : passer `sliding=True`. `ollama_load_bytes` (l.1005-1019) inchangé.
- `src/wavestack/session/app_session.py:1964, 1978, 2873, 2875` -- lecture seule : fichier direct ou Ollama, gardent `sliding=False`.
- `tests/test_probe.py:465-490` -- section lot K, `QWEN35_2B` (l.469), `QWEN35_4B` (l.479) : modèle pour la constante `LFM3_1_7B` et la nouvelle section.
- `tests/gguf_writer.py` -- écrit un GGUF de test (déjà utilisé par `test_probe.py` pour `gguf_kv_bytes_per_token`) ; vérifier qu'il sait écrire un tableau de booléens, l'étendre sinon.
- `tests/test_model_servers.py` -- `test_llama_server_memory_counts_its_whole_context` et `test_llama_server_with_several_slots_counts_the_whole_context` (tiny-llama sans fenêtre) restent verts sans modification.
- `src/wavestack/session/llm_lab.py:607,643` (`HYBRID_ARCHITECTURES`, `classify_header`) -- lecture seule, pour le test `hybrid`.

En-tête réel de `LFM3-1.7B-QAD-Q4_0.gguf`, relu le 2026-10-28 sur le poste de dev (clés `lfm3.*`) :
`block_count` = 24 ; `attention.head_count` = 16 ; `attention.head_count_kv` =
`[0,0,4,0,4,0,4,0,4,0,4,0,4,0,4,0,4,0,4,0,4,0,4,0]` (24 entrées, 4 aux indices pairs de 2
à 22, soit 11 couches d'attention) ; `key_length` = `value_length` = 128 ; `embedding_length` = 2048 ;
`sliding_window` = 256 ; `sliding_window_pattern` = 24 booléens, vrai aux indices 4, 8, 12, 16,
20 ; `shortconv.l_cache` = 7 ; `context_length` = 262144.

## Tasks & Acceptance

**Execution:**
- `src/wavestack/models/probe.py` -- `_sliding_layers`, `kv_bytes_per_token(meta, *, sliding=False)` (avec motif valide, ne sommer que les couches dont le drapeau est faux, sur la liste par couche des têtes KV : la liste `head_count_kv`, ou l'entier répété `block_count` fois hors `full_attention_interval`), `sliding_kv`, `gguf_kv_bytes_per_token(path, *, sliding=False)`, `_header_kv(..., sliding=False)` -- cœur du correctif.
- `src/wavestack/models/servers.py` -- `served_kv` passe `sliding=True` ; docstring à jour -- llama-server alloue un cache réduit par défaut (`--swa-full` absent).
- `tests/test_probe.py` -- constante `LFM3_1_7B` (valeurs ci-dessus, date et poste du relevé en commentaire) et section « fenêtre glissante » après le lot K couvrant toute la matrice, plus un GGUF écrit par `gguf_writer` lu par `gguf_kv_bytes_per_token(path, sliding=True)` -- garde-fou de la règle.
- `tests/test_model_servers.py` -- nouveau cas : GGUF LFM3 écrit par `gguf_writer`, `served_kv` = 12 288 -- vérifie le branchement.
- `tests/test_llm_lab.py` -- `classify_header(LFM3_1_7B)` donne `hybrid` (importer la constante ou la recopier) -- confirme qu'il n'y a pas à ajouter `lfm3` à `HYBRID_ARCHITECTURES` ; si le test échoue, l'ajouter et le dire dans le rapport.

**Acceptance Criteria:**
- Given un modèle LFM3 servi par llama-server avec un chemin absolu lisible, when le diagnostic estime sa mémoire, then la part KV vaut 12 288 octets × `n_ctx`.
- Given un modèle chargé en direct ou par Ollama, when sa mémoire est estimée, then le résultat est identique à celui d'avant la story.

## Spec Change Log

## Review Triage Log

## Design Notes

Part fixe des couches à fenêtre : llama.cpp leur garde environ `fenêtre × emplacements + ubatch`
tokens, quantité non proportionnelle au contexte. `sliding_kv` renvoie seulement `(octets par
token de ces couches, fenêtre)` ; la story 3 décide comment l'ajouter.

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_probe.py tests/test_model_servers.py tests/test_llm_lab.py tests/test_memory_budget.py` -- expected: tout vert
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected: OK
