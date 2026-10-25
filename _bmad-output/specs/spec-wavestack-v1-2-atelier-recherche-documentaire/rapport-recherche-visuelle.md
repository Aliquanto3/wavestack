# Rapport de la recherche visuelle sans OCR (ColPali, ColQwen)

V1.2, story 21, CAP-19. Généré par `tools/bench/v12s21_visual_search_bench.py report` ; il se régénère à l'identique depuis `tools/bench/results/<date>-v12s21/` (aucune date de génération).

## 1. Statut

- Mesure enregistrée le 2026-10-25 sur Windows-11-10.0.26300-SP0 (12 CPU, 31861 Mo de RAM).
- Corpus : fr, 12 pages tirées de 26 (rendu A4 150 dpi, police consola.ttf), 8 requêtes ; commit 15b013131ade711a6ee2ff8f85ef52d2dad77971.
- La mesure vaut pour le poste de développement (32 Go) : la mémoire est un pic de processus, indépendant de la RAM libre, mais les durées ne valent pas pour le PC cible (16 Go, i5) sans confirmation.

**Conclusion : ne tient pas.** Aucun candidat mesuré ne tient. ColPali v1.3, ONNX fp16 (Qdrant, fastembed) : mémoire : arrêté au plafond de sécurité de 16384 Mo (RSS à l'arrêt 18750 Mo), bien au-delà du budget de 4096 Mo; ColSmol-256M, ONNX fp32 (onnx-community) : mémoire : pic 6098 Mo > 4096 Mo ; requête : médiane 8967.2 ms > 3000 ms.

## 2. Candidats

| Candidat | Dépôt @ révision | Poids | Licence | Voie d'exécution | Langue | État |
|---|---|---|---|---|---|---|
| ColPali v1.3, ONNX fp16 (Qdrant, fastembed) | `Qdrant/colpali-v1.3-fp16` @ `e69c27e8` | 5890 Mo, ~2,9 Md (PaliGemma 3B) | Gemma Terms of Use (modèle dérivé de Gemma ; adaptateur ColPali MIT) | fastembed 0.9.1 (onnxruntime), sans torch | anglais (entraînement 100 % anglais, généralisation non anglaise non garantie) | mesuré : ne tient pas |
| ColSmol-256M, ONNX fp32 (onnx-community) | `onnx-community/colSmol-256M-ONNX` @ `12022f06` | 960 Mo, ~256 M (SmolVLM-256M) | MIT (carte onnx-community ; modèle d'origine vidore/colSmol-256M, MIT) | onnxruntime + tokenizers + pillow, entrées construites à la main, sans torch | anglais (entraînement 100 % anglais, généralisation non anglaise non garantie) | mesuré : ne tient pas |

Écartés ou en réserve, avec le motif (cartes lues le 2026-10-25, aucun poids téléchargé) :

- ColQwen2.5 v0.2 (vidore, 3B) (`vidore/colqwen2.5-v0.2 @ dcbe8d9cede518bce830488364ba0e40c873645b`) : adaptateur PEFT (240 Mo) sur Qwen2.5-VL-3B : `colpali-engine` exige torch ; aucun port ONNX ou GGUF trouvé sur le Hub (recherche du 2026-10-25) ; licence MIT.
- ColQwen2 v1.0, GGUF f16 (odellus) (`odellus/colqwen2-v1.0-gguf @ 8b4ff3b7acf948c88bb4226b6e788cdab49afbf4`) : f16 de 3 094 Mo (LLM) + 1 332 Mo (mmproj) = 4,4 Go, au-delà du budget de 4 Go à lui seul ; exige le fork crow-cli/llama.cpp (branche crow-colqwen2-mv, sorties multivecteurs), qui n'est ni llama-cpp-python ni le llama-server épinglé b11378 ; licence Apache-2.0.
- Ops-Colqwen3-4B, GGUF Q4_K_M (takenoko-gohan) (`takenoko-gohan/Ops-Colqwen3-4B-GGUF @ 463a43c16232d445546eb72880ed6e3baf3e692f`) : 3 311 Mo de poids seuls (4B), exécutable seulement par l'exemple Rust Candle (`cargo run`, compilation) ; hors des moteurs du projet ; licence Apache-2.0.
- ColSmol-500M (vidore) (`vidore/colSmol-500M @ 0aaa9726104ce485884c7b8faa8a58a72d5fdbe7`) : adaptateur PEFT (70 Mo) : torch et colpali-engine ; aucun port ONNX trouvé.
- ColPali v1.3 (vidore, safetensors) (`vidore/colpali-v1.3 @ b5c6dd62125326e6f0b540c1f7b36e901cdc0a11`) : adaptateur PEFT : torch ; le port ONNX de Qdrant ci-dessus est la voie sans torch.
- ColNomic Embed Multimodal 3B (nomic-ai) (`nomic-ai/colnomic-embed-multimodal-3b`) : adaptateur PEFT sur Qwen2.5-VL-3B : torch ; seuls des ports MLX (Apple) trouvés.
- ColSmol-256M, ONNX à nombre de tuiles dynamique (guyettinger) (`guyettinger/colSmol-256M-dynamic-onnx @ 93956db0e440eebd497bc776e7bf34a06830b0c6`) : réserve, non mesuré : sortie de `n*64+2` vecteurs, donc une disposition des `input_ids` différente de l'invite Idefics3 complète, non vérifiable sans télécharger ; l'auteur annonce ~5,0 s par image à 7 tuiles en fp32 sur CPU (publié, non vérifié) ; MIT.

## 3. Mémoire et latence

Pic retenu = le plus grand du pic de l'ensemble de travail et du pic de mémoire privée (même règle que le banc de la story 2) ; le pic de mémoire validée (commit) est donné à titre d'information, il compte des pages réservées qui ne sont pas forcément en RAM.

| Candidat | Pic retenu (Mo) | Ensemble de travail / mémoire privée / validée (Mo) | Budget 4 096 Mo (marge) | Chargement (s) | Indexation médiane / max (s par page) | Requête médiane / max (ms) | Pages indexées | Vecteurs par page |
|---|---|---|---|---|---|---|---|---|
| ColPali v1.3, ONNX fp16 (Qdrant, fastembed) | > 16384 (arrêté au plafond de sécurité ; RSS à l'arrêt 18750) | n/d | non | | | | | |
| ColSmol-256M, ONNX fp32 (onnx-community) | 6098 | 4224 / 6098 / 6109 | non (-2002 Mo) | 1,6 | 9,7 / 10,1 | 8967 / 9112 | 12 | 871 |

## 4. Qualité de la recherche et taille de l'index

| Candidat | Requêtes | Rappel@1 | Rappel@3 | MRR | Index du corpus entier (Mo, fp16, extrapolé) | Indexation du corpus entier (min, extrapolé) |
|---|---|---|---|---|---|---|
| ColPali v1.3, ONNX fp16 (Qdrant, fastembed) | non mesuré (voir section 3) | | | | | |
| ColSmol-256M, ONNX fp32 (onnx-community) | 8 | 0,62 | 0,88 | 0,76 | 5,5 (26 pages) | 4,2 |

Colonnes « extrapolé » : calculées, non mesurées (vecteurs moyens par page x pages du corpus x 128 x 2 octets ; médiane d'indexation par page x pages du corpus).

## 5. Dépendances

| Candidat | Paquets à installer (Mo sur disque) | Torch | Réseau pendant la mesure |
|---|---|---|---|
| ColPali v1.3, ONNX fp16 (Qdrant, fastembed) | non mesuré (voir section 3) | | |
| ColSmol-256M, ONNX fp32 (onnx-community) | 146 Mo, 27 paquets (fermeture de onnxruntime, tokenizers, numpy, pillow) ; dont numpy 40, onnxruntime 37, sympy 25, pillow 14, hf-xet 9, tokenizers 7, huggingface_hub 3, mpmath 1, protobuf 1 | absent | aucune tentative |

Aucune dépendance n'est ajoutée au projet : `pyproject.toml` et `uv.lock` ne changent pas ; la mesure vient de `uv run --with fastembed==0.9.1`. Une fonction de l'application ajouterait cette fermeture (onnxruntime et tokenizers sont déjà dans les extras `decision` et `guardrails`), plus fastembed pour ColPali et un modèle de 0,96 à 5,9 Go à télécharger.

## 6. Seuils, réserves et décisions

- Seuils : pic <= 4096 Mo (<= 3072 Mo : « tient », au-dessus : « tient de justesse ») ; indexation médiane <= 15 s par page ; requête médiane <= 3000 ms ; rappel@3 >= 0.75 sur au moins 6 requêtes ; pas de torch.
- Les deux modèles sont entraînés sur des données anglaises : le corpus Exemplia est français, la qualité mesurée vaut pour ce corpus et cette langue, pas pour le multilingue.
- ColPali v1.3 ONNX est sous les conditions d'utilisation de Gemma (restrictions d'usage, à transmettre en cas de redistribution) : à faire valider avant tout téléchargement par l'application.
- Les requêtes de ColPali (fastembed) font passer une image vide dans tout le graphe : leur latence est celle d'un passage complet du modèle, pas d'un encodeur de texte seul.
- Les entrées du graphe ColSmol sont construites à la main d'après la carte d'Idefics3 / ColIdefics3 ; si le graphe les refuse, la mesure l'enregistre (« non exécutable ») sans chiffre inventé. Le graphe exporté exige `pixel_values` (13 tuiles) même pour une requête de texte : la requête passe une image factice non nulle (une image nulle est retirée comme remplissage par Idefics3 et le graphe échoue), sans jeton `<image>` ; elle paie donc un passage de vision complet.
- Pages de test : rendu de texte sur fond blanc, sans mise en page riche : une borne optimiste pour la lecture, pessimiste pour l'intérêt du visuel (pas de schémas ni de scans).
- Le plafond de sécurité (16 384 Mo par défaut) arrête l'enfant pour protéger le poste ; le RSS à l'arrêt peut le dépasser (relevé toutes les 0,5 s). Un candidat arrêté « ne tient pas ».

Décisions prises sans Anaël, à revoir :

- seuils d'indexation (15 s par page), de requête (3 s) et de qualité (rappel@3 >= 0,75 sur au moins 6 requêtes) : propositions du développement, sans source.
- corpus `fr` seul : des modèles entraînés en anglais y sont jugés sur du français.
- 12 pages et 8 requêtes par défaut.
- plafond de sécurité de 16 384 Mo (arrêt de l'enfant, pas le verdict).
- ColPali v1.3 retenu malgré les conditions d'utilisation de Gemma (à valider avant toute intégration).
- entrées de ColSmol construites à la main (invite Idefics3, image factice non nulle pour une requête).
- ColQwen2.5, le plus multilingue, écarté faute de voie sans torch.

Pistes si rien ne tient :

- quantification de ColSmol (int8 ou fp16 d'onnxruntime) pour baisser le pic de mémoire.
- autre port ONNX : `guyettinger/colSmol-256M-dynamic-onnx` (tuiles dynamiques), ou un export dont l'encodeur de texte est séparé, pour qu'une requête ne paie pas le passage de vision.
- ColQwen2.5 avec torch hors de l'application (service séparé) : contraire au budget et à « pas de torch », à décider par Anaël.

### Écart à consigner dans `deferred-work.md`

```yaml
- source_spec: `_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/stories/21-recherche-visuelle-sans-ocr.md`
  summary: CAP-19, recherche visuelle sans OCR : ne tient pas. Aucun candidat mesuré ne tient. ColPali v1.3, ONNX fp16 (Qdrant, fastembed) : mémoire : arrêté au plafond de sécurité de 16384 Mo (RSS à l'arrêt 18750 Mo), bien au-delà du budget de 4096 Mo; ColSmol-256M, ONNX fp32 (onnx-community) : mémoire : pic 6098 Mo > 4096 Mo ; requête : médiane 8967.2 ms > 3000 ms.
  evidence: rapport-recherche-visuelle.md ; décision d'intégration (ou non) à prendre par Anaël. Pistes : quantification de ColSmol (int8 ou fp16 d'onnxruntime) pour baisser le pic de mémoire ; autre port ONNX : `guyettinger/colSmol-256M-dynamic-onnx` (tuiles dynamiques), ou un export dont l'encodeur de texte est séparé, pour qu'une requête ne paie pas le passage de vision ; ColQwen2.5 avec torch hors de l'application (service séparé) : contraire au budget et à « pas de torch », à décider par Anaël.
```

## 7. Commandes

```bash
# 1. téléchargement unique, seule étape réseau (huggingface.co, révisions épinglées) : ~6,9 Go
uv run --with fastembed==0.9.1 python tools/bench/v12s21_visual_search_bench.py download
# 2. mesure, poste libre de tout agent, hors ligne : ~20 min
uv run --with fastembed==0.9.1 python tools/bench/v12s21_visual_search_bench.py measure --confirm-idle
# 3. rapport (rejeu sans modèle)
uv run python tools/bench/v12s21_visual_search_bench.py report --write
```
