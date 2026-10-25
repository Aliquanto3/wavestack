# Rapport du banc préalable System One et fenêtre de 16 384 tokens

V1.2, story 2. Généré par `tools/bench/v12s2_system_one_bench.py` ; le rejeu à sec régénère ce fichier à l'identique (aucune date de génération).

> **DONNÉES SYNTHÉTIQUES DE FIXTURE : ce ne sont pas des mesures.** Réponses fabriquées pour tester le rejeu en CI.

## 1. Statut

- Mesure : enregistrée du 2000-01-01 au 2000-01-01.
- Items : 10 (filtre 6, ancrage 4), en fr.
- Commit du lancement : fixture.
- Verdict : mesuré.

## 2. Choix

**Filtre de passages**
- Défaut local : deberta-v3-xsmall zero-shot NLI (ONNX) (`deberta_xsmall`).
- Repli : aucun (SLM juge si mesuré).
- Option cloud (à part, CAP-6) : aucune.

**Contrôle d'ancrage**
- Défaut local : aucun candidat ne passe.
- Repli : aucun (SLM juge si mesuré).
- Option cloud (à part, CAP-6) : aucune.

Règles : le défaut est local. Filtre : au seuil de probabilité le plus haut qui garde un rappel du passage attendu >= 0,95, part des négatifs écartés >= 0,60 ; le reranker livré est la référence (un modèle de décision n'est choisi que s'il écarte plus de négatifs que lui au même rappel). Ancrage : au seuil qui garde un rappel des étayées >= 0,80, part des non étayées acceptées (H7) <= 0,13. Un candidat sans mesure H7 n'est jamais choisi pour l'ancrage ; un taux d'erreur > 5 % le met « à surveiller », jamais choisi. Seuils ajustés sur le jeu lui-même, donc optimistes : les chiffres au seuil fixe 0,5 sont donnés aussi. Les seuils du filtre sont une proposition du développement, sans source ; l'origine de H7 est un seul article (Towards AI : Jev 23 %, LLM 13 %).

## 3. Candidats

| Candidat | Type | État | H7 (non étayées acceptées) | Version rendue / motif |
|---|---|---|---|---|
| Jev 1.14 (TypeSafe) (`typesafe/jev-1.14`) | en ligne | mesuré | 50 % [0,09 ; 0,91] | synthetic-fixture-20000101 |
| Liquid D1 (`liquid/d1`) | en ligne | publié, non mesuré | aucun chiffre publié connu | modèle refusé par le point d'accès |
| deberta-v3-xsmall zero-shot NLI (ONNX) (`deberta_xsmall`) | local | mesuré | 100 % [0,34 ; 1,00] |  |
| bge-reranker-v2-m3 Q4_K_M de la brique (seuil sur le score) (`reranker_livre`) | local | mesuré | — |  |

## 4. Filtre de passages

| Candidat | n | AUC [IC 95 %] | Seuil | Rappel | Écartés | Périmés écartés | Écartés à 0,5 | Latence méd./max (ms) | k=3 / k=8 (ms) | Erreurs | Écart répét. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Jev 1.14 (TypeSafe) | 6 | 0,56 [0,00 ; 1,00] | 0,21 | 1,00 | 33 % | — | 100 % | 252 / 252 | 754 / 2012 | 0 % | 0,00 |
| deberta-v3-xsmall zero-shot NLI (ONNX) | 6 | 0,89 [0,56 ; 1,00] | 0,71 | 1,00 | 67 % | — | 67 % | 120 / 120 | 360 / 960 | 0 % | 0,00 |
| bge-reranker-v2-m3 Q4_K_M de la brique (seuil sur le score) | 6 | 0,78 [0,33 ; 1,00] | 0,16 | 1,00 | 33 % | — | 100 % | 120 / 120 | 360 / 960 | 0 % | 0,00 |

Par langue (au seuil retenu) : Jev 1.14 (TypeSafe) fr écartés 33 % ; deberta-v3-xsmall zero-shot NLI (ONNX) fr écartés 67 % ; bge-reranker-v2-m3 Q4_K_M de la brique (seuil sur le score) fr écartés 33 %.

## 5. Contrôle d'ancrage

| Candidat | n | AUC [IC 95 %] | Seuil | Rappel étayées | H7 [IC 95 %] | H7 à 0,5 | Latence méd./max (ms) | Erreurs | Écart répét. |
|---|---|---|---|---|---|---|---|---|---|
| Jev 1.14 (TypeSafe) | 4 | 0,50 [0,00 ; 1,00] | 0,67 | 1,00 | 50 % [0,09 ; 0,91] | 50 % | 252 / 252 | 0 % | 0,00 |
| deberta-v3-xsmall zero-shot NLI (ONNX) | 4 | 0,50 [0,00 ; 1,00] | 0,24 | 1,00 | 100 % [0,34 ; 1,00] | 0 % | 120 / 120 | 0 % | 0,00 |

Par langue (au seuil retenu) : Jev 1.14 (TypeSafe) fr H7 50 % ; deberta-v3-xsmall zero-shot NLI (ONNX) fr H7 100 %.

H7 est décidé sur les trois langues regroupées. Les items sont des traductions les uns des autres, donc non indépendants : les intervalles sont optimistes.

## 6. Calibration, distribution et bascule vers le SLM juge

- Jev 1.14 (TypeSafe), filter : calibration 0.0-0.2 : prob. 0,08 / observé 0,00 (n=1); 0.2-0.4 : prob. 0,28 / observé 0,75 (n=4); 0.4-0.6 : prob. 0,40 / observé 0,00 (n=1). Distribution (10 classes) : [1, 0, 2, 2, 1, 0, 0, 0, 0, 0]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 50 %, seuil 0.5 : 100 %, seuil 0.7 : 100 %.
- Jev 1.14 (TypeSafe), grounding : calibration 0.0-0.2 : prob. 0,08 / observé 0,00 (n=1); 0.6-0.8 : prob. 0,69 / observé 1,00 (n=2); 0.8-1.0 : prob. 0,94 / observé 0,00 (n=1). Distribution (10 classes) : [1, 0, 0, 0, 0, 0, 1, 1, 0, 1]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 25 %, seuil 0.5 : 25 %, seuil 0.7 : 50 %.
- deberta-v3-xsmall zero-shot NLI (ONNX), filter : calibration 0.0-0.2 : prob. 0,14 / observé 0,00 (n=1); 0.2-0.4 : prob. 0,21 / observé 0,00 (n=1); 0.6-0.8 : prob. 0,73 / observé 0,50 (n=2); 0.8-1.0 : prob. 0,88 / observé 1,00 (n=2). Distribution (10 classes) : [0, 1, 1, 0, 0, 0, 0, 2, 1, 1]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 33 %, seuil 0.5 : 33 %, seuil 0.7 : 33 %.
- deberta-v3-xsmall zero-shot NLI (ONNX), grounding : calibration 0.2-0.4 : prob. 0,29 / observé 0,50 (n=2); 0.4-0.6 : prob. 0,43 / observé 0,00 (n=1); 0.8-1.0 : prob. 0,85 / observé 1,00 (n=1). Distribution (10 classes) : [0, 0, 1, 1, 1, 0, 0, 0, 1, 0]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 25 %, seuil 0.5 : 75 %, seuil 0.7 : 75 %.
- bge-reranker-v2-m3 Q4_K_M de la brique (seuil sur le score), filter : calibration sans objet. Distribution (10 classes) : [0, 2, 2, 0, 0, 1, 1, 0, 0, 0]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 67 %, seuil 0.5 : 67 %, seuil 0.7 : 100 %.

## 7. Formulations exactes des `instructions`

- filter, fr : « Ce passage contient-il l'information qui permet de répondre à la question ? Réponds oui seulement si le passage suffit à répondre. »
- filter, en : « Does this passage contain the information needed to answer the question? Answer yes only if the passage is enough to answer. »
- filter, de : « Enthält dieser Abschnitt die Information, die zur Beantwortung der Frage nötig ist? Antworte nur dann mit ja, wenn der Abschnitt zur Antwort ausreicht. »
- grounding, fr : « L'affirmation est-elle entièrement étayée par les passages ? Réponds non si elle ajoute ou change un fait, un chiffre ou une condition. »
- grounding, en : « Is the claim fully supported by the passages? Answer no if it adds or changes a fact, a number or a condition. »
- grounding, de : « Wird die Aussage von den Abschnitten vollständig gestützt? Antworte mit nein, wenn sie eine Tatsache, eine Zahl oder eine Bedingung hinzufügt oder ändert. »

Requête : `{model, state, questions: {decision: {type: "noul", instructions}}}` ; état du filtre `{question, passage}`, de l'ancrage `{premise, claim}`.

## 8. Candidats locaux

- deberta-v3-xsmall zero-shot NLI (ONNX) : RAM avec le SLM chargé 2300 Mo (budget 4096), ajoutée 90 Mo ; versions {'onnxruntime': 'synthetic'} ; révisions {} ; sha256 — ; déterministe : True ; probabilité : oui ; troncature à 512 tokens : 0 items.
- bge-reranker-v2-m3 Q4_K_M de la brique (seuil sur le score) : RAM avec le SLM chargé 2300 Mo (budget 4096), ajoutée 90 Mo ; versions {'onnxruntime': 'synthetic'} ; révisions {} ; sha256 — ; déterministe : True ; probabilité : oui ; troncature à 512 tokens : 0 items.

## 9. Budget

- Dépensé 0.0012 $ sur un plafond de 2,00 $ ; 20 appels sur 6000 ; plafond par modèle 0,33 $.
- typesafe/jev-1.14 : 0.0012 $, 20 appels.

## 10. Mémoire de la fenêtre de 16 384 tokens (Qwen3.5-2B)

- Pic de l'ensemble de travail 2900 Mo, pic de mémoire privée 2800 Mo ; n_ctx 16384, prompt de 16128 tokens ; RAM du poste 32000 Mo.
- Estimation `_kv_per_token` x 16 384 : 700 Mo.
- Verdict : confirmé. Le pic mesuré sur un poste de 32 Go est un majorant pour le PC cible de 16 Go (cache KV alloué pour tout n_ctx, mmap).
- Avec le RAG V1 (+1170 Mo, mesure V2), informatif : 4070 Mo.

## 11. Limites

- Jeu fictif Exemplia (corpus et questions du dépôt), affirmations non étayées écrites à la main : petites tailles, IC larges, items traduits non indépendants.
- Seuils ajustés sur le jeu : optimistes. Probabilités des modèles en ligne rendues au centième (ex æquo fréquents).
- Mesure mémoire sur 32 Go : majorant pour le PC cible 16 Go (point 8 de la spec).
- Un modèle en ligne n'est jamais un prérequis (SPEC.md) ; données envoyées : corpus fictif et jeu de questions seulement.

## 12. Commandes

- Rejeu à sec (sans réseau) : `uv run python tools/bench/v12s2_system_one_bench.py dry-run`.
- Réel en ligne : `uv run python tools/bench/v12s2_system_one_bench.py online --confirm-idle`.
- Réel local : `uv run --with onnxruntime --with tokenizers --with huggingface-hub python tools/bench/v12s2_system_one_bench.py local --confirm-idle --download`.
- Mémoire : `uv run python tools/bench/v12s2_system_one_bench.py memory --confirm-idle`.
