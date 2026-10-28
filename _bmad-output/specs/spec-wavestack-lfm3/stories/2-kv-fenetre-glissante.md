---
title: 'Story 2 : KV par token avec attention à fenêtre glissante'
type: 'bugfix'
created: '2026-10-28'
status: 'done'
baseline_commit: '6bb822698dfb50cf5a7074932de24400b25db84d'
route: 'dispatch'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-lfm3/SPEC.md'
warnings: []
deferred:
  - summary: 'n_ctx inférieur à la fenêtre : couches glissantes sorties du KV par token sans part fixe'
    evidence: 'sliding=True retire les 5 couches glissantes de LFM3 ; llama.cpp leur garde environ min(n_ctx, fenêtre × emplacements + ubatch) tokens, soit au plus ce nombre × 10 240 octets non comptés'
    location: 'src/wavestack/models/servers.py served_kv / served_bytes'
    severity: 'low'
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

- 2026-10-28 : implémentée telle quelle, aucun écart avec l'intent-contract. `classify_header(LFM3_1_7B)` donne déjà `hybrid` sans ajouter `lfm3` à `HYBRID_ARCHITECTURES` (confirmé par un test dédié), comme prévu par la tâche conditionnelle.

## Review Triage Log

### 2026-10-28 — Review pass
- verdicts: 9 findings — high 0, medium 2, low 3, false 4, maybe-false 0
- findings:
  - `[medium]` `[patch]` Liste `head_count_kv` de somme 0 hors motif : 0 au lieu de None (second avis 1, orchestrateur 7) — l'invariant « aucun appelant non modifié ne voit de différence » cassé (`probed_entry` remplaçait la valeur stockée par 0 ; `served_kv` donnait 0 donc `context_counted` vrai pour un en-tête sans tête KV). Corrigé : 0 seulement quand le motif a retiré des couches (`masked`), test `test_no_kv_head_at_all_stays_none_unless_the_pattern_left_them_out`.
  - `[medium]` `[patch]` (reviewer) `head_count_kv` entier sans `full_attention_interval` + motif valide : motif ignoré, alors que la tâche demande « l'entier répété `block_count` fois hors `full_attention_interval` ». Corrigé dans `_kv_per_layer` (le chemin `kv_bytes_per_token` et `sliding_kv` en profitent), test `test_single_kv_head_count_with_a_pattern_repeats_it_per_layer`.
  - `[low]` `[defer]` n_ctx inférieur à la fenêtre (second avis 3) — part fixe des couches glissantes non comptée : périmètre de la story 3 (`sliding_kv`), voir `deferred`.
  - `[low]` `[patch]` `_header_kv` appelé à 3 puis 4 arguments : deux entrées `lru_cache` par fichier (second avis 4) — `probed_entry` passe `False` explicitement.
  - `[low]` `[patch]` QWEN35_4B jamais testé avec `sliding` (second avis 5, première moitié) — assertion ajoutée (`test_qwen35_4b_unchanged_with_sliding`).
  - `[false]` `[reject]` Motif `True` seul : 0, `served_kv` = 0, `context_counted` vrai (second avis 2) — conforme à la matrice ; la part proportionnelle au contexte est bien nulle, la part fixe relève de la story 3.
  - `[false]` `[reject]` Rien ne vérifie `ollama_load_bytes` ni `app_session` (second avis 5, seconde moitié) — code non modifié, appel par défaut `sliding=False` ; leurs tests existants passent (294 verts).
  - `[false]` `[reject]` `test_llm_lab.py` importe `LFM3_1_7B` depuis `test_probe` (second avis 6) — même motif que les imports voisins (`test_model_servers`, `test_cloud`), voulu par la tâche.
  - `[false]` `[reject]` `_sliding_layers` accepte la longueur de `block_count` ou de la liste `head_count_kv` (orchestrateur 8) — dans un GGUF valide les deux sont égales (llama.cpp exige `n_layer` entrées) ; si elles diffèrent, `kv_bytes_per_token` et `sliding_kv` exigent `len(mask) == len(kv_per_layer)` et ignorent le motif : même valeur que sans `sliding`, sans exception, comme le veut la matrice.

## Design Notes

Part fixe des couches à fenêtre : llama.cpp leur garde environ `fenêtre × emplacements + ubatch`
tokens, quantité non proportionnelle au contexte. `sliding_kv` renvoie seulement `(octets par
token de ces couches, fenêtre)` ; la story 3 décide comment l'ajouter.

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_probe.py tests/test_model_servers.py tests/test_llm_lab.py tests/test_memory_budget.py` -- expected: tout vert
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected: OK

## Auto Run Result

- **Résumé :** `kv_bytes_per_token(meta, *, sliding=False)` ne compte plus, avec `sliding=True` et un motif valide, les couches à fenêtre glissante ; `sliding_kv(meta)` expose leur part (story 3) ; seul `servers.served_kv` passe `sliding=True`. LFM3-1.7B servi : 12 288 octets par token au lieu de 22 528. Revue : deux correctifs medium (0 hors motif, entier `head_count_kv` avec motif).
- **Fichiers :** `src/wavestack/models/probe.py`, `src/wavestack/models/servers.py`, `tests/gguf_writer.py`, `tests/test_probe.py`, `tests/test_model_servers.py`, `tests/test_llm_lab.py`.
- **Constats :** 9 (medium 2 corrigés, low 3 dont 2 corrigés et 1 différé à la story 3, 4 rejetés) ; voir Review Triage Log.
- **Vérification :** `uv run python -m pytest -q --tb=short tests/test_probe.py tests/test_model_servers.py tests/test_llm_lab.py tests/test_memory_budget.py` : 294 passés ; `controle_rapide.py` : OK.
- **Risques résiduels :** part fixe des couches glissantes non comptée tant que la story 3 n'est pas faite (sous-estimation d'au plus quelques Mo pour LFM3) ; un motif dont les éléments ne sont pas booléens (liste de chaînes) est converti par `bool()` au lieu d'être rejeté, cas non vu dans un GGUF réel.
