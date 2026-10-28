# LFM3-1.7B dans WaveStack sur le PC cible (16 Go), 2026-10-28

llama.cpp b11938 (commit 19cce6919), `LFM3-1.7B-QAD-Q4_0.gguf` (1 049 615 680 octets), `-c 16384`, chemin `-m` absolu, code de `main` à 6206790e (v1.7.1). Sorties brutes : `resultat-np4.txt`, `resultat-np1.txt`, `resultat-norepack.txt`, journaux `llama-server*.log`.

## Résultats

| Mesure | -np 4 (défaut) | -np 1 | -np 1 --no-repack |
|---|---|---|---|
| Détection (`list_served`) | servi, n_ctx 16 384, slot 16 384 (`kv_unified`) | idem (slot non unifié) | idem |
| Capacités servies | qwen3, `qwen3_coder`, arrêt `<\|im_end\|>`, `enable_thinking`, `<think>` | idem | idem |
| Appel get_weather(Lyon), raisonnement | OK, 95 tokens, 12,6 tok/s en génération | OK, 122 tokens, 13,9 tok/s | OK, 71 tokens, 10,4 tok/s |
| Appel get_weather(Lyon), sans raisonnement | OK, 19 tokens, 12,7 tok/s | OK, 13,9 tok/s | OK, 9,8 tok/s |
| Lecture du prompt (89 tokens) | 44-47 tok/s | 47 tok/s | 25-26 tok/s |
| Mémoire mesurée (working set / privée) | 2 112 / 1 218 Mo | 2 101 / 1 207 Mo | 1 308 / 412 Mo |
| Estimation WaveStack (`served_bytes`) | 1 353 Mo (fichier 993 Mo + KV 352 Mo) | idem | idem |

KV théorique à 16 384 : 6 couches globales × 4 têtes × (128 + 128) × 2 octets = 12 288 octets/token, soit 192 Mo ; plus 5 couches à fenêtre de 256 (≈ 2,5 Mo par slot) et le cache des 13 convolutions (négligeable). WaveStack compte 22 528 octets/token (352 Mo).

## Les trois écarts

1. **Confirmé.** Même template, `architecture="lfm3"` : famille `lfm3`, analyseur `None`, arrêts `()` (le raisonnement reste reconnu). `src/wavestack/models/capabilities.py:142-146` (template seulement sans architecture), `:164`, `:191-199`.
2. **Confirmé.** `kv_bytes_per_token` = 22 528 au lieu de 12 288. `src/wavestack/models/probe.py:78-115`. Clés du GGUF : `lfm3.attention.sliding_window_pattern` = liste de 24 booléens (vrai aux couches 4, 8, 12, 16, 20), `lfm3.attention.sliding_window` = 256, `head_count_kv` par couche (4 sur les 11 couches d'attention, 0 ailleurs).
3. **Confirmé dans le code, partiellement rejoué.** Chemin relatif ignoré : `servers.py:1031-1032` (non rejoué ici, chemin absolu demandé) ; tampons de calcul non comptés : `servers.py:1002`. Avec un chemin absolu, le KV est bien compté.

## Différences avec l'autre poste, nouveaux constats

- Mémoire identique (≈ 2,0 Go résidents, 1,2 Go privés).
- **Les 4 slots ne coûtent presque rien** (≈ 10 Mo) : avec `-np 4`, llama-server unifie le cache (`kv_unified = true`), les 16 384 tokens sont partagés.
- **Le gros de l'écart vient du réarrangement des poids Q4_0 pour le CPU (repack)** : ≈ 800 Mo privés, une seconde copie des poids, alors que le fichier reste en partie résident par mmap. Sans repack : 412 Mo privés (KV ≈ 195 Mo + tampons de calcul ≈ 200 Mo), mais génération −25 % et lecture du prompt −45 %. WaveStack ne compte ni le repack ni les tampons.
- Template du GGUF = template servi (à un saut de ligne final près).
- Non vérifié : le rangement chez « Qwen (Alibaba) » (l'appli ne tournait pas, pas de diagnostic relevé).

## Stories proposées (specs draft dans `../spec-wavestack-lfm3/`, à ajuster)

1. **Capacités `lfm3`** (inchangée) : template Qwen3 reconnu quelle que soit l'architecture, famille `lfm3`, éditeur LiquidAI, message d'échec en direct qui nomme l'architecture.
2. **KV avec fenêtre glissante** (inchangée, valeurs confirmées) : 12 288 octets/token pour LFM3, motif lu en liste de booléens.
3. **Mémoire d'un modèle servi** (à revoir) : remplacer la constante provisoire de tampons par « poids réarrangés + KV + tampons » (≈ 2 × poids pour Q4_0 sur CPU, sauf `--no-repack`), ou lire la mémoire privée réelle du processus llama-server (port → PID) ; chemin `-m` relatif. Le nombre de slots peut sortir du périmètre (cache unifié).
