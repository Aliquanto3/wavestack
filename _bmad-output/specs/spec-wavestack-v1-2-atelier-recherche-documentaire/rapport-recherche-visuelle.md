# Rapport de la recherche visuelle sans OCR (ColPali, ColQwen)

V1.2, story 21, CAP-19. Généré par `tools/bench/v12s21_visual_search_bench.py report` ; il se régénère à l'identique depuis `tools/bench/results/<date>-v12s21/` (aucune date de génération).

## 1. Statut

- Mesure enregistrée le 2026-10-25 sur Windows-11-10.0.26300-SP0 (12 CPU, 31861 Mo de RAM).
- Corpus : fr, 12 pages tirées de 26 (rendu A4 150 dpi, police consola.ttf), 8 requêtes ; commit e647ad100ae229a3da1c4fb58e30354cf0ec0674.
- La mesure vaut pour le poste de développement (32 Go) : la mémoire est un pic de processus, indépendant de la RAM libre, mais les durées ne valent pas pour le PC cible (16 Go, i5) sans confirmation.

**Conclusion : ne tient pas.** Aucun candidat mesuré ne tient. ColPali v1.3, ONNX fp16 (Qdrant, fastembed) : arrêté au plafond de sécurité (18750 Mo); ColSmol-256M, ONNX fp32 (onnx-community) : mémoire : pic 6130 Mo > 4096 Mo ; requêtes non exécutables : le graphe refuse l'entrée : Fail("[ONNXRuntimeError] : 1 : FAIL : Non-zero status code returned while running Split node. Name:'/model/model/vision_model/embeddings/Split' Status Message: Cannot split using values in 'split' attribute. Axis=0 Input shape={0,32,32} NumOutputs=13 Num entries in 'split ; qualité non jugeable : 0 requêtes < 6.

## 2. Candidats

| Candidat | Dépôt @ révision | Poids | Licence | Voie d'exécution | Langue | État |
|---|---|---|---|---|---|---|
| ColPali v1.3, ONNX fp16 (Qdrant, fastembed) | `Qdrant/colpali-v1.3-fp16` @ `e69c27e8` | 5890 Mo, ~2,9 Md (PaliGemma 3B) | Gemma Terms of Use (modèle dérivé de Gemma ; adaptateur ColPali MIT) | fastembed 0.9.1 (onnxruntime), sans torch | anglais (entraînement 100 % anglais, généralisation non anglaise non garantie) | mesuré : non exécutable |
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

| Candidat | Pic (Mo) | Budget 4 096 Mo | Chargement (s) | Indexation médiane / max (s par page) | Requête médiane / max (ms) | Pages indexées | Vecteurs par page |
|---|---|---|---|---|---|---|---|
| ColPali v1.3, ONNX fp16 (Qdrant, fastembed) | pas encore mesuré (arrêté au plafond de sécurité (18750 Mo)) | | | | | | |
| ColSmol-256M, ONNX fp32 (onnx-community) | 6130 | non | 1,7 | 9,6 / 10,9 | n/d / n/d | 12 | 871 |

## 4. Qualité de la recherche et taille de l'index

| Candidat | Requêtes | Rappel@1 | Rappel@3 | MRR | Index du corpus entier (Mo, fp16) | Indexation du corpus entier (min) |
|---|---|---|---|---|---|---|
| ColPali v1.3, ONNX fp16 (Qdrant, fastembed) | pas encore mesuré | | | | | |
| ColSmol-256M, ONNX fp32 (onnx-community) | 0 | n/d | n/d | n/d | 5,5 (26 pages) | 4,2 |

## 5. Dépendances

| Candidat | Paquets à installer (Mo sur disque) | Torch | Réseau pendant la mesure |
|---|---|---|---|
| ColPali v1.3, ONNX fp16 (Qdrant, fastembed) | pas encore mesuré | | |
| ColSmol-256M, ONNX fp32 (onnx-community) | 146 Mo (onnxruntime, tokenizers, numpy, pillow) | absent | aucune tentative |

Aucune dépendance n'est ajoutée au projet : `pyproject.toml` et `uv.lock` ne changent pas ; la mesure vient de `uv run --with fastembed==0.9.1`. Une fonction de l'application ajouterait onnxruntime (déjà employé par le banc des modèles de décision), numpy, pillow et fastembed, plus un modèle de 0,96 à 5,9 Go à télécharger.

## 6. Seuils, réserves et décisions

- Seuils : pic <= 4096 Mo (<= 3072 Mo : « tient », au-dessus : « tient de justesse ») ; indexation médiane <= 15 s par page ; requête médiane <= 3000 ms ; rappel@3 >= 0.75 sur au moins 6 requêtes ; pas de torch.
- Les deux modèles sont entraînés sur des données anglaises : le corpus Exemplia est français, la qualité mesurée vaut pour ce corpus et cette langue, pas pour le multilingue.
- ColPali v1.3 ONNX est sous les conditions d'utilisation de Gemma (restrictions d'usage, à transmettre en cas de redistribution) : à faire valider avant tout téléchargement par l'application.
- Les requêtes de ColPali (fastembed) font passer une image vide dans tout le graphe : leur latence est celle d'un passage complet du modèle, pas d'un encodeur de texte seul.
- Les entrées du graphe ColSmol sont construites à la main d'après la carte d'Idefics3 / ColIdefics3 ; si le graphe les refuse, la mesure l'enregistre (« non exécutable ») sans chiffre inventé.
- Pages de test : rendu de texte sur fond blanc, sans mise en page riche : une borne optimiste pour la lecture, pessimiste pour l'intérêt du visuel (pas de schémas ni de scans).

### Écart à consigner dans `deferred-work.md`

```yaml
- source_spec: `_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/stories/21-recherche-visuelle-sans-ocr.md`
  summary: CAP-19, recherche visuelle sans OCR : ne tient pas. Aucun candidat mesuré ne tient. ColPali v1.3, ONNX fp16 (Qdrant, fastembed) : arrêté au plafond de sécurité (18750 Mo); ColSmol-256M, ONNX fp32 (onnx-community) : mémoire : pic 6130 Mo > 4096 Mo ; requêtes non exécutables : le graphe refuse l'entrée : Fail("[ONNXRuntimeError] : 1 : FAIL : Non-zero status code returned while running Split node. Name:'/model/model/vision_model/embeddings/Split' Status Message: Cannot split using values in 'split' attribute. Axis=0 Input shape={0,32,32} NumOutputs=13 Num entries in 'split ; qualité non jugeable : 0 requêtes < 6.
  evidence: rapport-recherche-visuelle.md ; décision d'intégration (ou non) à prendre par Anaël.
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
