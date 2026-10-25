# Rapport du banc préalable System One et fenêtre de 16 384 tokens

V1.2, story 2. Généré par `tools/bench/v12s2_system_one_bench.py` ; le rejeu à sec régénère ce fichier à l'identique (aucune date de génération).

## 1. Statut

- Mesure : enregistrée du 2026-10-25 au 2026-10-25.
- Items : 450 (filtre 279, ancrage 171), en de, en, fr.
- Commit du lancement : e91bdca46179e9a9647cf4cbce14a20453b84209.
- Verdict : mesuré.

## 2. Choix

**Filtre de passages**
- Défaut local : bge-reranker-v2-m3 Q4_K_M de la brique (seuil sur le score) (`reranker_livre`).
- Repli : aucun (SLM juge si mesuré).
- Option cloud (à part, CAP-6) : PPLX Decider Flash 1.2 (`perplexity/pplx-decider-flash-v1.2`).

**Contrôle d'ancrage**
- Défaut local : deberta-v3-xsmall zero-shot NLI (ONNX) (`deberta_xsmall`).
- Repli : aucun (SLM juge si mesuré).
- Option cloud (à part, CAP-6) : Jev 1.14 (TypeSafe) (`typesafe/jev-1.14`).

Règles : le défaut est local. Filtre : au seuil de probabilité le plus haut qui garde un rappel du passage attendu >= 0,95, part des négatifs écartés >= 0,60 ; le reranker livré est la référence (un modèle de décision n'est choisi que s'il écarte plus de négatifs que lui au même rappel). Ancrage : au seuil qui garde un rappel des étayées >= 0,80, part des non étayées acceptées (H7) <= 0,13. Un candidat sans mesure H7 n'est jamais choisi pour l'ancrage ; un taux d'erreur > 5 % le met « à surveiller », jamais choisi. Seuils ajustés sur le jeu lui-même, donc optimistes : les chiffres au seuil fixe 0,5 sont donnés aussi. Les seuils du filtre sont une proposition du développement, sans source ; l'origine de H7 est un seul article (Towards AI : Jev 23 %, LLM 13 %).

## 3. Candidats

| Candidat | Type | État | H7 (non étayées acceptées) | Version rendue / motif |
|---|---|---|---|---|
| Jev 1.14 (TypeSafe) (`typesafe/jev-1.14`) | en ligne | mesuré | 0 % [0,00 ; 0,03] | typesafe/jev-1.14-20261014 |
| Microsoft Decision 1 (`microsoft/microsoft-decision-1`) | en ligne | mesuré | 1 % [0,00 ; 0,05] | microsoft/microsoft-decision-1-20261009 |
| GPT-6 Luna Decisions (`openai/gpt-6-luna-decisions`) | en ligne | mesuré | 3 % [0,01 ; 0,07] | openai/gpt-6-luna-decisions-20261006 |
| PPLX Decider Flash 1.2 (`perplexity/pplx-decider-flash-v1.2`) | en ligne | mesuré | 0 % [0,00 ; 0,03] | perplexity/pplx-decider-flash-v1.2-20261016 |
| Liquid D1 (`liquid/d1`) | en ligne | mesuré | 2 % [0,00 ; 0,06] | liquid/d1-20260930 |
| Mercury Decide (gratuit) (`inception/mercury-decide:free`) | en ligne | mesuré | 1 % [0,00 ; 0,05] | inception/mercury-decide-20260930 |
| deberta-v3-xsmall zero-shot NLI (ONNX) (`deberta_xsmall`) | local | mesuré | 9 % [0,05 ; 0,16] |  |
| mDeBERTa-v3 xnli (petit NLI ONNX multilingue) (`nli_mdeberta`) | local | mesuré | 41 % [0,33 ; 0,50] |  |
| bge-reranker-v2-m3 Q4_K_M de la brique (seuil sur le score) (`reranker_livre`) | local | mesuré | — |  |
| SLM juge Qwen3.5-2B + GBNF (référence et repli) (`slm_juge`) | local | mesuré | — |  |
| Strands Decider 2B hobson v19 (port ONNX q8) (`strands_decider_2b`) | local | écarté | — | Fail('[ONNXRuntimeError] : 1 : FAIL : Load model from C:\\Users\\Utilisateur\\.cache\\wavestack-bench\\hf\\models--onnx-community--strands-decider-2B-hobson-v19-ONNX\\snapshots\\31a83e0244b26d939ae33f87189d6c8204003e53\\onnx\\model_quantized.onnx failed:Fatal error: com.microsoft:CausalConvWithState |
| AnyJev 0.3.0 (commit 35311c5), lecture L0 du SLM Qwen3.5-2B (llama-cpp-python) (`anyjev`) | local | mesuré | 1 % [0,00 ; 0,05] |  |

## 4. Filtre de passages

| Candidat | n | AUC [IC 95 %] | Seuil | Rappel | Écartés | Périmés écartés | Écartés à 0,5 | Latence méd./max (ms) | k=3 / k=8 (ms) | Erreurs | Écart répét. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Jev 1.14 (TypeSafe) | 279 | 0,90 [0,87 ; 0,93] | 0,10 | 0,95 | 71 % | 0 % | 83 % | 246 / 1019 | 738 / 1968 | 0 % | 0,16 |
| Microsoft Decision 1 | 279 | 0,90 [0,87 ; 0,93] | 0,03 | 0,95 | 70 % | 11 % | 86 % | 396 / 1101 | 1188 / 3168 | 0 % | 0,12 |
| GPT-6 Luna Decisions | 279 | 0,84 [0,79 ; 0,89] | 0,07 | 0,95 | 38 % | 11 % | 78 % | 418 / 1526 | 1254 / 3344 | 0 % | 0,00 |
| PPLX Decider Flash 1.2 | 279 | 0,92 [0,89 ; 0,95] | 0,13 | 0,95 | 79 % | 22 % | 86 % | 249 / 2185 | 747 / 1992 | 0 % | 0,00 |
| Liquid D1 | 279 | 0,91 [0,88 ; 0,94] | 0,01 | 0,95 | 66 % | 0 % | 88 % | 265 / 1622 | 795 / 2120 | 0 % | 0,64 |
| Mercury Decide (gratuit) | 279 | 0,89 [0,85 ; 0,92] | 0,00 | 0,95 | 69 % | 0 % | 90 % | 496 / 11214 | 1486 / 3964 | 0 % | 0,36 |
| deberta-v3-xsmall zero-shot NLI (ONNX) | 279 | 0,81 [0,77 ; 0,86] | 0,04 | 0,95 | 38 % | 0 % | 85 % | 28 / 104 | 84 / 224 | 0 % | 0,00 |
| mDeBERTa-v3 xnli (petit NLI ONNX multilingue) | 279 | 0,73 [0,66 ; 0,80] | 0,06 | 0,95 | 14 % | 11 % | 100 % | 63 / 270 | 189 / 504 | 0 % | 0,00 |
| bge-reranker-v2-m3 Q4_K_M de la brique (seuil sur le score) | 279 | non calculable | 0,02 | 0,95 | 64 % | 0 % | 92 % | 141 / 192 | 423 / 1128 | 0 % | 0,00 |
| SLM juge Qwen3.5-2B + GBNF (référence et repli) | 0 | non calculable | — | — | — | — | 0 % | 0 / 1 | 0 / 0 | 100 % (à surveiller) | 0,00 |
| AnyJev 0.3.0 (commit 35311c5), lecture L0 du SLM Qwen3.5-2B (llama-cpp-python) | 279 | 0,83 [0,77 ; 0,88] | 0,35 | 0,95 | 38 % | 0 % | 67 % | 2619 / 6787 | 7857 / 20952 | 0 % | 0,00 |

Par langue (au seuil retenu) : Jev 1.14 (TypeSafe) fr écartés 68 % ; Jev 1.14 (TypeSafe) en écartés 73 % ; Jev 1.14 (TypeSafe) de écartés 71 % ; Microsoft Decision 1 fr écartés 67 % ; Microsoft Decision 1 en écartés 73 % ; Microsoft Decision 1 de écartés 71 % ; GPT-6 Luna Decisions fr écartés 25 % ; GPT-6 Luna Decisions en écartés 30 % ; GPT-6 Luna Decisions de écartés 57 % ; PPLX Decider Flash 1.2 fr écartés 78 % ; PPLX Decider Flash 1.2 en écartés 79 % ; PPLX Decider Flash 1.2 de écartés 79 % ; Liquid D1 fr écartés 68 % ; Liquid D1 en écartés 62 % ; Liquid D1 de écartés 68 % ; Mercury Decide (gratuit) fr écartés 63 % ; Mercury Decide (gratuit) en écartés 71 % ; Mercury Decide (gratuit) de écartés 71 % ; deberta-v3-xsmall zero-shot NLI (ONNX) fr écartés 37 % ; deberta-v3-xsmall zero-shot NLI (ONNX) en écartés 54 % ; deberta-v3-xsmall zero-shot NLI (ONNX) de écartés 24 % ; mDeBERTa-v3 xnli (petit NLI ONNX multilingue) fr écartés 8 % ; mDeBERTa-v3 xnli (petit NLI ONNX multilingue) en écartés 16 % ; mDeBERTa-v3 xnli (petit NLI ONNX multilingue) de écartés 19 % ; bge-reranker-v2-m3 Q4_K_M de la brique (seuil sur le score) fr écartés 60 % ; bge-reranker-v2-m3 Q4_K_M de la brique (seuil sur le score) en écartés 63 % ; bge-reranker-v2-m3 Q4_K_M de la brique (seuil sur le score) de écartés 68 % ; SLM juge Qwen3.5-2B + GBNF (référence et repli) fr écartés — ; SLM juge Qwen3.5-2B + GBNF (référence et repli) en écartés — ; SLM juge Qwen3.5-2B + GBNF (référence et repli) de écartés — ; AnyJev 0.3.0 (commit 35311c5), lecture L0 du SLM Qwen3.5-2B (llama-cpp-python) fr écartés 43 % ; AnyJev 0.3.0 (commit 35311c5), lecture L0 du SLM Qwen3.5-2B (llama-cpp-python) en écartés 37 % ; AnyJev 0.3.0 (commit 35311c5), lecture L0 du SLM Qwen3.5-2B (llama-cpp-python) de écartés 35 %.

## 5. Contrôle d'ancrage

| Candidat | n | AUC [IC 95 %] | Seuil | Rappel étayées | H7 [IC 95 %] | H7 à 0,5 | Latence méd./max (ms) | Erreurs | Écart répét. |
|---|---|---|---|---|---|---|---|---|---|
| Jev 1.14 (TypeSafe) | 171 | 1,00 [1,00 ; 1,00] | 0,59 | 0,81 | 0 % [0,00 ; 0,03] | 0 % | 246 / 1019 | 0 % | 0,16 |
| Microsoft Decision 1 | 171 | 1,00 [0,99 ; 1,00] | 0,47 | 0,81 | 1 % [0,00 ; 0,05] | 0 % | 396 / 1101 | 0 % | 0,12 |
| GPT-6 Luna Decisions | 171 | 0,99 [0,97 ; 1,00] | 0,21 | 0,81 | 3 % [0,01 ; 0,07] | 2 % | 418 / 1526 | 0 % | 0,00 |
| PPLX Decider Flash 1.2 | 171 | 1,00 [0,99 ; 1,00] | 0,84 | 0,81 | 0 % [0,00 ; 0,03] | 0 % | 249 / 2185 | 0 % | 0,00 |
| Liquid D1 | 171 | 0,98 [0,96 ; 1,00] | 0,69 | 0,81 | 2 % [0,00 ; 0,06] | 6 % | 265 / 1622 | 0 % | 0,64 |
| Mercury Decide (gratuit) | 171 | 0,99 [0,99 ; 1,00] | 0,73 | 0,81 | 1 % [0,00 ; 0,05] | 1 % | 496 / 11214 | 0 % | 0,36 |
| deberta-v3-xsmall zero-shot NLI (ONNX) | 171 | 0,96 [0,93 ; 0,98] | 0,20 | 0,81 | 9 % [0,05 ; 0,16] | 3 % | 28 / 104 | 0 % | 0,00 |
| mDeBERTa-v3 xnli (petit NLI ONNX multilingue) | 171 | 0,78 [0,71 ; 0,85] | 0,09 | 0,81 | 41 % [0,33 ; 0,50] | 0 % | 63 / 270 | 0 % | 0,00 |
| SLM juge Qwen3.5-2B + GBNF (référence et repli) | 0 | non calculable | — | — | — | 100 % | 0 / 1 | 100 % (à surveiller) | 0,00 |
| AnyJev 0.3.0 (commit 35311c5), lecture L0 du SLM Qwen3.5-2B (llama-cpp-python) | 171 | 0,98 [0,96 ; 1,00] | 0,81 | 0,81 | 1 % [0,00 ; 0,05] | 50 % | 2619 / 6787 | 0 % | 0,00 |

Par langue (au seuil retenu) : Jev 1.14 (TypeSafe) fr H7 0 % ; Jev 1.14 (TypeSafe) en H7 0 % ; Jev 1.14 (TypeSafe) de H7 0 % ; Microsoft Decision 1 fr H7 0 % ; Microsoft Decision 1 en H7 3 % ; Microsoft Decision 1 de H7 0 % ; GPT-6 Luna Decisions fr H7 3 % ; GPT-6 Luna Decisions en H7 3 % ; GPT-6 Luna Decisions de H7 3 % ; PPLX Decider Flash 1.2 fr H7 0 % ; PPLX Decider Flash 1.2 en H7 0 % ; PPLX Decider Flash 1.2 de H7 0 % ; Liquid D1 fr H7 0 % ; Liquid D1 en H7 5 % ; Liquid D1 de H7 0 % ; Mercury Decide (gratuit) fr H7 0 % ; Mercury Decide (gratuit) en H7 3 % ; Mercury Decide (gratuit) de H7 0 % ; deberta-v3-xsmall zero-shot NLI (ONNX) fr H7 13 % ; deberta-v3-xsmall zero-shot NLI (ONNX) en H7 5 % ; deberta-v3-xsmall zero-shot NLI (ONNX) de H7 10 % ; mDeBERTa-v3 xnli (petit NLI ONNX multilingue) fr H7 33 % ; mDeBERTa-v3 xnli (petit NLI ONNX multilingue) en H7 41 % ; mDeBERTa-v3 xnli (petit NLI ONNX multilingue) de H7 49 % ; SLM juge Qwen3.5-2B + GBNF (référence et repli) fr H7 — ; SLM juge Qwen3.5-2B + GBNF (référence et repli) en H7 — ; SLM juge Qwen3.5-2B + GBNF (référence et repli) de H7 — ; AnyJev 0.3.0 (commit 35311c5), lecture L0 du SLM Qwen3.5-2B (llama-cpp-python) fr H7 0 % ; AnyJev 0.3.0 (commit 35311c5), lecture L0 du SLM Qwen3.5-2B (llama-cpp-python) en H7 3 % ; AnyJev 0.3.0 (commit 35311c5), lecture L0 du SLM Qwen3.5-2B (llama-cpp-python) de H7 0 %.

H7 est décidé sur les trois langues regroupées. Les items sont des traductions les uns des autres, donc non indépendants : les intervalles sont optimistes.

## 6. Calibration, distribution et bascule vers le SLM juge

- Jev 1.14 (TypeSafe), filter : calibration 0.0-0.2 : prob. 0,04 / observé 0,07 (n=153); 0.2-0.4 : prob. 0,29 / observé 0,37 (n=19); 0.4-0.6 : prob. 0,49 / observé 0,52 (n=21); 0.6-0.8 : prob. 0,69 / observé 0,38 (n=24); 0.8-1.0 : prob. 0,95 / observé 0,71 (n=62). Distribution (10 classes) : [137, 16, 11, 8, 10, 11, 15, 9, 9, 53]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 59 %, seuil 0.5 : 65 %, seuil 0.7 : 75 %.
- Jev 1.14 (TypeSafe), grounding : calibration 0.0-0.2 : prob. 0,04 / observé 0,02 (n=117); 0.2-0.4 : prob. 0,24 / observé 0,33 (n=3); 0.4-0.6 : prob. 0,53 / observé 1,00 (n=8); 0.6-0.8 : prob. 0,70 / observé 1,00 (n=19); 0.8-1.0 : prob. 0,88 / observé 1,00 (n=24). Distribution (10 classes) : [113, 4, 3, 0, 3, 5, 7, 12, 16, 8]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 70 %, seuil 0.5 : 72 %, seuil 0.7 : 79 %.
- Microsoft Decision 1, filter : calibration 0.0-0.2 : prob. 0,02 / observé 0,06 (n=162); 0.2-0.4 : prob. 0,30 / observé 0,40 (n=25); 0.4-0.6 : prob. 0,50 / observé 0,77 (n=13); 0.6-0.8 : prob. 0,71 / observé 0,67 (n=9); 0.8-1.0 : prob. 0,96 / observé 0,64 (n=70). Distribution (10 classes) : [153, 9, 13, 12, 6, 7, 3, 6, 15, 55]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 63 %, seuil 0.5 : 69 %, seuil 0.7 : 73 %.
- Microsoft Decision 1, grounding : calibration 0.0-0.2 : prob. 0,02 / observé 0,02 (n=117); 0.2-0.4 : prob. 0,29 / observé 0,86 (n=7); 0.4-0.6 : prob. 0,50 / observé 0,89 (n=9); 0.6-0.8 : prob. 0,77 / observé 1,00 (n=9); 0.8-1.0 : prob. 0,92 / observé 1,00 (n=29). Distribution (10 classes) : [113, 4, 4, 3, 4, 5, 0, 9, 11, 18]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 71 %, seuil 0.5 : 75 %, seuil 0.7 : 78 %.
- GPT-6 Luna Decisions, filter : calibration 0.0-0.2 : prob. 0,06 / observé 0,09 (n=122); 0.2-0.4 : prob. 0,29 / observé 0,24 (n=37); 0.4-0.6 : prob. 0,48 / observé 0,14 (n=22); 0.6-0.8 : prob. 0,70 / observé 0,18 (n=17); 0.8-1.0 : prob. 0,97 / observé 0,68 (n=81). Distribution (10 classes) : [90, 32, 18, 19, 15, 7, 7, 10, 6, 75]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 50 %, seuil 0.5 : 62 %, seuil 0.7 : 67 %.
- GPT-6 Luna Decisions, grounding : calibration 0.0-0.2 : prob. 0,01 / observé 0,08 (n=124); 0.2-0.4 : prob. 0,28 / observé 0,75 (n=4); 0.4-0.6 : prob. 0,52 / observé 1,00 (n=4); 0.6-0.8 : prob. 0,69 / observé 1,00 (n=2); 0.8-1.0 : prob. 0,97 / observé 0,95 (n=37). Distribution (10 classes) : [119, 5, 3, 1, 2, 2, 1, 1, 4, 33]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 74 %, seuil 0.5 : 76 %, seuil 0.7 : 78 %.
- PPLX Decider Flash 1.2, filter : calibration 0.0-0.2 : prob. 0,03 / observé 0,04 (n=165); 0.2-0.4 : prob. 0,28 / observé 0,56 (n=9); 0.4-0.6 : prob. 0,50 / observé 0,44 (n=16); 0.6-0.8 : prob. 0,71 / observé 0,70 (n=23); 0.8-1.0 : prob. 0,94 / observé 0,70 (n=66). Distribution (10 classes) : [151, 14, 5, 4, 8, 8, 9, 14, 17, 49]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 61 %, seuil 0.5 : 65 %, seuil 0.7 : 71 %.
- PPLX Decider Flash 1.2, grounding : calibration 0.0-0.2 : prob. 0,02 / observé 0,02 (n=119); 0.4-0.6 : prob. 0,45 / observé 1,00 (n=4); 0.6-0.8 : prob. 0,74 / observé 1,00 (n=2); 0.8-1.0 : prob. 0,94 / observé 1,00 (n=46). Distribution (10 classes) : [113, 6, 0, 0, 3, 1, 1, 1, 9, 37]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 70 %, seuil 0.5 : 71 %, seuil 0.7 : 73 %.
- Liquid D1, filter : calibration 0.0-0.2 : prob. 0,02 / observé 0,07 (n=167); 0.2-0.4 : prob. 0,32 / observé 0,21 (n=14); 0.4-0.6 : prob. 0,51 / observé 0,40 (n=15); 0.6-0.8 : prob. 0,70 / observé 0,55 (n=22); 0.8-1.0 : prob. 0,96 / observé 0,79 (n=61). Distribution (10 classes) : [157, 10, 5, 9, 6, 9, 11, 11, 8, 53]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 62 %, seuil 0.5 : 67 %, seuil 0.7 : 74 %.
- Liquid D1, grounding : calibration 0.0-0.2 : prob. 0,05 / observé 0,00 (n=88); 0.2-0.4 : prob. 0,29 / observé 0,07 (n=14); 0.4-0.6 : prob. 0,48 / observé 0,31 (n=16); 0.6-0.8 : prob. 0,70 / observé 0,78 (n=18); 0.8-1.0 : prob. 0,91 / observé 0,97 (n=35). Distribution (10 classes) : [72, 16, 8, 6, 13, 3, 8, 10, 15, 20]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 56 %, seuil 0.5 : 67 %, seuil 0.7 : 74 %.
- Mercury Decide (gratuit), filter : calibration 0.0-0.2 : prob. 0,01 / observé 0,17 (n=207); 0.2-0.4 : prob. 0,25 / observé 0,43 (n=7); 0.4-0.6 : prob. 0,51 / observé 0,00 (n=2); 0.6-0.8 : prob. 0,67 / observé 0,40 (n=5); 0.8-1.0 : prob. 0,98 / observé 0,71 (n=58). Distribution (10 classes) : [198, 9, 5, 2, 1, 1, 3, 2, 3, 55]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 76 %, seuil 0.5 : 77 %, seuil 0.7 : 78 %.
- Mercury Decide (gratuit), grounding : calibration 0.0-0.2 : prob. 0,00 / observé 0,04 (n=120); 0.2-0.4 : prob. 0,24 / observé 0,67 (n=3); 0.4-0.6 : prob. 0,53 / observé 1,00 (n=2); 0.6-0.8 : prob. 0,74 / observé 1,00 (n=3); 0.8-1.0 : prob. 0,97 / observé 0,98 (n=43). Distribution (10 classes) : [120, 0, 3, 0, 1, 1, 0, 3, 5, 38]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 72 %, seuil 0.5 : 73 %, seuil 0.7 : 73 %.
- deberta-v3-xsmall zero-shot NLI (ONNX), filter : calibration 0.0-0.2 : prob. 0,05 / observé 0,11 (n=140); 0.2-0.4 : prob. 0,30 / observé 0,38 (n=42); 0.4-0.6 : prob. 0,49 / observé 0,41 (n=22); 0.6-0.8 : prob. 0,70 / observé 0,38 (n=26); 0.8-1.0 : prob. 0,90 / observé 0,63 (n=49). Distribution (10 classes) : [115, 25, 21, 21, 15, 7, 10, 16, 24, 25]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 58 %, seuil 0.5 : 71 %, seuil 0.7 : 77 %.
- deberta-v3-xsmall zero-shot NLI (ONNX), grounding : calibration 0.0-0.2 : prob. 0,04 / observé 0,09 (n=115); 0.2-0.4 : prob. 0,26 / observé 0,36 (n=11); 0.4-0.6 : prob. 0,52 / observé 0,80 (n=5); 0.6-0.8 : prob. 0,71 / observé 0,86 (n=7); 0.8-1.0 : prob. 0,94 / observé 0,91 (n=33). Distribution (10 classes) : [100, 15, 9, 2, 2, 3, 4, 3, 6, 27]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 73 %, seuil 0.5 : 75 %, seuil 0.7 : 79 %.
- mDeBERTa-v3 xnli (petit NLI ONNX multilingue), filter : calibration 0.0-0.2 : prob. 0,11 / observé 0,20 (n=211); 0.2-0.4 : prob. 0,28 / observé 0,53 (n=62); 0.4-0.6 : prob. 0,46 / observé 1,00 (n=5); 0.6-0.8 : prob. 0,63 / observé 1,00 (n=1). Distribution (10 classes) : [80, 131, 40, 22, 4, 1, 1, 0, 0, 0]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 90 %, seuil 0.5 : 99 %, seuil 0.7 : 100 %.
- mDeBERTa-v3 xnli (petit NLI ONNX multilingue), grounding : calibration 0.0-0.2 : prob. 0,09 / observé 0,21 (n=135); 0.2-0.4 : prob. 0,28 / observé 0,66 (n=29); 0.4-0.6 : prob. 0,46 / observé 0,80 (n=5); 0.6-0.8 : prob. 0,68 / observé 1,00 (n=2). Distribution (10 classes) : [86, 49, 20, 9, 4, 1, 1, 1, 0, 0]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 91 %, seuil 0.5 : 98 %, seuil 0.7 : 99 %.
- bge-reranker-v2-m3 Q4_K_M de la brique (seuil sur le score), filter : calibration sans objet. Distribution (10 classes) : [165, 11, 9, 7, 7, 3, 2, 11, 15, 49]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 66 %, seuil 0.5 : 71 %, seuil 0.7 : 73 %.
- SLM juge Qwen3.5-2B + GBNF (référence et repli), filter : calibration . Distribution (10 classes) : [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : —, seuil 0.5 : —, seuil 0.7 : —.
- SLM juge Qwen3.5-2B + GBNF (référence et repli), grounding : calibration . Distribution (10 classes) : [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : —, seuil 0.5 : —, seuil 0.7 : —.
- AnyJev 0.3.0 (commit 35311c5), lecture L0 du SLM Qwen3.5-2B (llama-cpp-python), filter : calibration 0.0-0.2 : prob. 0,15 / observé 0,03 (n=37); 0.2-0.4 : prob. 0,32 / observé 0,12 (n=64); 0.4-0.6 : prob. 0,50 / observé 0,22 (n=91); 0.6-0.8 : prob. 0,68 / observé 0,54 (n=68); 0.8-1.0 : prob. 0,86 / observé 0,79 (n=19). Distribution (10 classes) : [7, 30, 22, 42, 42, 49, 43, 25, 16, 3]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 21 %, seuil 0.5 : 51 %, seuil 0.7 : 84 %.
- AnyJev 0.3.0 (commit 35311c5), lecture L0 du SLM Qwen3.5-2B (llama-cpp-python), grounding : calibration 0.0-0.2 : prob. 0,12 / observé 0,00 (n=4); 0.2-0.4 : prob. 0,34 / observé 0,00 (n=31); 0.4-0.6 : prob. 0,49 / observé 0,00 (n=39); 0.6-0.8 : prob. 0,69 / observé 0,16 (n=49); 0.8-1.0 : prob. 0,88 / observé 0,96 (n=48). Distribution (10 classes) : [1, 3, 6, 25, 23, 16, 30, 19, 31, 17]. Part des items sous le seuil (bascule vers le SLM juge) : seuil 0.3 : 6 %, seuil 0.5 : 34 %, seuil 0.7 : 61 %.

## 7. Formulations exactes des `instructions`

- filter, fr : « Ce passage contient-il l'information qui permet de répondre à la question ? Réponds oui seulement si le passage suffit à répondre. »
- filter, en : « Does this passage contain the information needed to answer the question? Answer yes only if the passage is enough to answer. »
- filter, de : « Enthält dieser Abschnitt die Information, die zur Beantwortung der Frage nötig ist? Antworte nur dann mit ja, wenn der Abschnitt zur Antwort ausreicht. »
- grounding, fr : « L'affirmation est-elle entièrement étayée par les passages ? Réponds non si elle ajoute ou change un fait, un chiffre ou une condition. »
- grounding, en : « Is the claim fully supported by the passages? Answer no if it adds or changes a fact, a number or a condition. »
- grounding, de : « Wird die Aussage von den Abschnitten vollständig gestützt? Antworte mit nein, wenn sie eine Tatsache, eine Zahl oder eine Bedingung hinzufügt oder ändert. »

Requête : `{model, state, questions: {decision: {type: "noul", instructions}}}` ; état du filtre `{question, passage}`, de l'ancrage `{premise, claim}`.

## 8. Candidats locaux

- deberta-v3-xsmall zero-shot NLI (ONNX) : RAM avec le SLM chargé 1935 Mo (budget 4096), ajoutée 351 Mo ; versions {'huggingface-hub': '1.33.0', 'llama-cpp-python': '0.3.35', 'onnxruntime': '1.23.2', 'tokenizers': '0.22.1'} ; révisions {'MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33': '262ae02f29173eec1c250f90804dc7edc677dcff'} ; sha256 — ; déterministe : True ; probabilité : oui ; troncature à 512 tokens : 34 items.
- mDeBERTa-v3 xnli (petit NLI ONNX multilingue) : RAM avec le SLM chargé 1933 Mo (budget 4096), ajoutée 783 Mo ; versions {'huggingface-hub': '1.33.0', 'llama-cpp-python': '0.3.35', 'onnxruntime': '1.23.2', 'tokenizers': '0.22.1'} ; révisions {'MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7': 'b5113eb38ab63efdd7f280f8c144ea8b13f978ce'} ; sha256 — ; déterministe : True ; probabilité : oui ; troncature à 512 tokens : 31 items.
- bge-reranker-v2-m3 Q4_K_M de la brique (seuil sur le score) : RAM avec le SLM chargé 1934 Mo (budget 4096), ajoutée 758 Mo ; versions {'llama-cpp-python': '0.3.35'} ; révisions {'bge-reranker-v2-m3-q4_k_m': 'reranker/bge-reranker-v2-m3-Q4_K_M.gguf'} ; sha256 — ; déterministe : True ; probabilité : non (étiquette seule) ; troncature à 512 tokens : 0 items.
- SLM juge Qwen3.5-2B + GBNF (référence et repli) : RAM avec le SLM chargé 1933 Mo (budget 4096), ajoutée 5 Mo ; versions {'llama-cpp-python': '0.3.35'} ; révisions {} ; sha256 — ; déterministe : True ; probabilité : oui ; troncature à 512 tokens : 0 items.
- Strands Decider 2B hobson v19 (port ONNX q8) : écarté (Fail('[ONNXRuntimeError] : 1 : FAIL : Load model from C:\\Users\\Utilisateur\\.cache\\wavestack-bench\\hf\\models--onnx-community--strands-decider-2B-hobson-v19-ONNX\\snapshots\\31a83e0244b26d939ae33f87189d6c8204003e53\\onnx\\model_quantized.onnx failed:Fatal error: com.microsoft:CausalConvWithState).
- AnyJev 0.3.0 (commit 35311c5), lecture L0 du SLM Qwen3.5-2B (llama-cpp-python) : RAM avec le SLM chargé 1934 Mo (budget 4096), ajoutée 1938 Mo ; versions {'anyjev': '0.3.0', 'llama-cpp-python': '0.3.35'} ; révisions {'anyjev': '35311c58955716cb8955ce1368a665988bc63735', 'slm': 'Qwen3.5-2B-Q4_K_M.gguf'} ; sha256 — ; déterministe : True ; probabilité : oui ; troncature à 512 tokens : 0 items.

## 9. Budget

- Dépensé 0.0761 $ sur un plafond de 2,00 $ ; 5403 appels sur 6000 ; plafond par modèle 0,33 $.
- inception/mercury-decide:free : 0.0000 $, 902 appels.
- liquid/d1 : 0.0053 $, 900 appels.
- microsoft/microsoft-decision-1 : 0.0104 $, 900 appels.
- openai/gpt-6-luna-decisions : 0.0363 $, 901 appels.
- perplexity/pplx-decider-flash-v1.2 : 0.0031 $, 900 appels.
- typesafe/jev-1.14 : 0.0210 $, 900 appels.

## 10. Mémoire de la fenêtre de 16 384 tokens (Qwen3.5-2B)

- Pic de l'ensemble de travail 2519 Mo, pic de mémoire privée 2767 Mo ; n_ctx 16384, prompt de 16128 tokens ; RAM du poste 31861 Mo.
- Estimation `_kv_per_token` x 16 384 : 192 Mo.
- Verdict : confirmé. Le pic mesuré sur un poste de 32 Go est un majorant pour le PC cible de 16 Go (cache KV alloué pour tout n_ctx, mmap).
- Avec le RAG V1 (+1170 Mo, mesure V2), informatif : 3937 Mo.

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
