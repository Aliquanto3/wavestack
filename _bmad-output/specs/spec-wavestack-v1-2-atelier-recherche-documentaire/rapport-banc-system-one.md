# Rapport du banc préalable System One et fenêtre de 16 384 tokens

V1.2, story 2. Généré par `tools/bench/v12s2_system_one_bench.py` ; le rejeu à sec régénère ce fichier à l'identique (aucune date de génération).

## 1. Statut

- Mesure : pas encore mesuré.
- Items : 450 (filtre 279, ancrage 171), en fr, en, de.
- Commit du lancement : pas encore mesuré.
- Verdict : pas encore mesuré.

## 2. Choix

Aucun choix : pas encore mesuré. Le défaut reste local ; un modèle en ligne n'est jamais un prérequis.

Règles : le défaut est local. Filtre : au seuil de probabilité le plus haut qui garde un rappel du passage attendu >= 0,95, part des négatifs écartés >= 0,60 ; le reranker livré est la référence (un modèle de décision n'est choisi que s'il écarte plus de négatifs que lui au même rappel). Ancrage : au seuil qui garde un rappel des étayées >= 0,80, part des non étayées acceptées (H7) <= 0,13. Un candidat sans mesure H7 n'est jamais choisi pour l'ancrage ; un taux d'erreur > 5 % le met « à surveiller », jamais choisi. Seuils ajustés sur le jeu lui-même, donc optimistes : les chiffres au seuil fixe 0,5 sont donnés aussi. Les seuils du filtre sont une proposition du développement, sans source ; l'origine de H7 est un seul article (Towards AI : Jev 23 %, LLM 13 %).

## 3. Candidats

| Candidat | Type | État | H7 (non étayées acceptées) | Version rendue / motif |
|---|---|---|---|---|
| Jev 1.14 (TypeSafe) (`typesafe/jev-1.14`) | en ligne | pas encore mesuré | — | pas encore mesuré |
| Microsoft Decision 1 (`microsoft/microsoft-decision-1`) | en ligne | pas encore mesuré | — | pas encore mesuré |
| GPT-6 Luna Decisions (`openai/gpt-6-luna-decisions`) | en ligne | pas encore mesuré | — | pas encore mesuré |
| PPLX Decider Flash 1.2 (`perplexity/pplx-decider-flash-v1.2`) | en ligne | pas encore mesuré | — | pas encore mesuré |
| Liquid D1 (`liquid/d1`) | en ligne | pas encore mesuré | — | pas encore mesuré |
| Mercury Decide (gratuit) (`inception/mercury-decide:free`) | en ligne | pas encore mesuré | — | pas encore mesuré |
| deberta-v3-xsmall zero-shot NLI (ONNX) (`deberta_xsmall`) | local | pas encore mesuré | — | pas encore mesuré |
| mDeBERTa-v3 xnli (petit NLI ONNX multilingue) (`nli_mdeberta`) | local | pas encore mesuré | — | pas encore mesuré |
| bge-reranker-v2-m3 Q4_K_M de la brique (seuil sur le score) (`reranker_livre`) | local | pas encore mesuré | — | pas encore mesuré |
| SLM juge Qwen3.5-2B + GBNF (référence et repli) (`slm_juge`) | local | pas encore mesuré | — | pas encore mesuré |
| Strands Decider 2B hobson v19 (port ONNX q8) (`strands_decider_2b`) | local | pas encore mesuré | — | pas encore mesuré |
| AnyJev 0.3.0 (commit 35311c5), lecture L0 du SLM Qwen3.5-2B (llama-cpp-python) (`anyjev`) | local | pas encore mesuré | — | pas encore mesuré |

## 4. Filtre de passages

pas encore mesuré

## 5. Contrôle d'ancrage

pas encore mesuré

## 6. Calibration, distribution et bascule vers le SLM juge

pas encore mesuré

## 7. Formulations exactes des `instructions`

- filter, fr : « Ce passage contient-il l'information qui permet de répondre à la question ? Réponds oui seulement si le passage suffit à répondre. »
- filter, en : « Does this passage contain the information needed to answer the question? Answer yes only if the passage is enough to answer. »
- filter, de : « Enthält dieser Abschnitt die Information, die zur Beantwortung der Frage nötig ist? Antworte nur dann mit ja, wenn der Abschnitt zur Antwort ausreicht. »
- grounding, fr : « L'affirmation est-elle entièrement étayée par les passages ? Réponds non si elle ajoute ou change un fait, un chiffre ou une condition. »
- grounding, en : « Is the claim fully supported by the passages? Answer no if it adds or changes a fact, a number or a condition. »
- grounding, de : « Wird die Aussage von den Abschnitten vollständig gestützt? Antworte mit nein, wenn sie eine Tatsache, eine Zahl oder eine Bedingung hinzufügt oder ändert. »

Requête : `{model, state, questions: {decision: {type: "noul", instructions}}}` ; état du filtre `{question, passage}`, de l'ancrage `{premise, claim}`.

## 8. Candidats locaux

- deberta-v3-xsmall zero-shot NLI (ONNX) : pas encore mesuré (pas encore mesuré).
- mDeBERTa-v3 xnli (petit NLI ONNX multilingue) : pas encore mesuré (pas encore mesuré).
- bge-reranker-v2-m3 Q4_K_M de la brique (seuil sur le score) : pas encore mesuré (pas encore mesuré).
- SLM juge Qwen3.5-2B + GBNF (référence et repli) : pas encore mesuré (pas encore mesuré).
- Strands Decider 2B hobson v19 (port ONNX q8) : pas encore mesuré (pas encore mesuré).
- AnyJev 0.3.0 (commit 35311c5), lecture L0 du SLM Qwen3.5-2B (llama-cpp-python) : pas encore mesuré (pas encore mesuré).

## 9. Budget

pas encore mesuré

## 10. Mémoire de la fenêtre de 16 384 tokens (Qwen3.5-2B)

pas encore mesuré. Seuils : <= 3072 Mo confirmé ; 3072 à 4096 Mo confirmé sur le poste de développement, confirmation sur le PC cible demandée ; au-delà, infirmé.

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
