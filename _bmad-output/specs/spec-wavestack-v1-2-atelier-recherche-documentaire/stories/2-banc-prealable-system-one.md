---
title: 'Story 2 : banc préalable System One et fenêtre de 16 384 tokens'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/architectures.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/evaluation.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/corpus-et-questions.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/decision-model-candidates.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-6 (filtre de passages, contrôle d'ancrage) et CAP-7 (contexte long, CAG) reposent sur deux inconnues. Quel modèle de décision filtre les passages et contrôle l'ancrage sans laisser passer d'affirmation non étayée (H7 : Jev en accepte 23 % contre 13 % pour un LLM, non démontré sur un pipeline) ? Et Qwen3.5-2B avec une fenêtre de 16 384 tokens tient-il dans 4 Go ?

**Approach:** Un banc `tools/bench/v12s2_system_one_bench.py`, sur le modèle de `v2s6_decision_bench.py`, mesure les candidats locaux (sans torch, sans service) et six modèles de décision en ligne, tous par OpenRouter (`POST https://openrouter.ai/api/alpha/decisions`), sur le corpus fictif Exemplia et le jeu de questions. Le banc a deux modes : « à sec », rejoué sans réseau depuis des réponses enregistrées, et « réel », lancé à part. Le rapport versionné choisit les modèles du filtre et de l'ancrage et confirme ou infirme l'hypothèse mémoire dans `.memlog.md`.

## Boundaries & Constraints

**Always:**
- Candidats en ligne, via OpenRouter : `typesafe/jev-1.14`, `microsoft/microsoft-decision-1`, `openai/gpt-6-luna-decisions`, `perplexity/pplx-decider-flash-v1.2`, `liquid/d1`, `inception/mercury-decide:free`. Un modèle absent de ce point d'accès (réponse refusée ou inconnue) garde ses chiffres publiés, marqués « publié, non mesuré ».
- Candidats locaux de `stories.yaml` et `architectures.md` : `deberta_xsmall`, Strands Decider 2B, AnyJev, reranker livré comme filtre (seuil sur son score), petit NLI ONNX, SLM juge Qwen3.5-2B + GBNF (référence et repli). Ni torch ni service en local ; les paquets de mesure viennent de `uv run --with ...`, jamais du projet. Un candidat local qui ne tourne pas sans torch ou sans binaire à installer est « écarté », avec la raison.
- Clé lue dans `OPENROUTER_API_KEY` ou, à défaut, `HKCU\Environment` ; jamais affichée, journalisée ni écrite (ni dans le rapport, ni dans les cas enregistrés, ni dans les en-têtes enregistrés). Pas de clé de l'éditeur ni d'OpenAI. Sans clé, le mode réel refuse de partir ; le mode à sec n'en a pas besoin.
- Données envoyées : seulement le corpus fictif Exemplia et le jeu de questions (`content/rag_questions.yaml`) ; un contrôle refuse tout texte venant d'ailleurs.
- Format d'appel d'après T9 : `{model, state, questions}` ; réponse `answers.<question>.noul` (probabilité du oui), `choice` avec `probabilities`, `usage.input_tokens`, `usage.cost`. Coût observé ~0,00006 $ et 0,25 s par appel.
- Mode à sec : rejoue les réponses enregistrées dans `tools/bench/results/<date>-v12s2/recorded/` (JSONL : requête sans clé, réponse brute, latence, coût), calcule métriques et rapport à l'identique, sans réseau ni modèle.
- Le lancement réel est séparé et ne part que sur ordre d'Anaël, quand aucun autre agent ne tourne sur le poste ; il vérifie le budget plafond avant chaque appel et s'arrête au plafond.
- Mesure mémoire de Qwen3.5-2B à 16 384 tokens : pic de RSS du processus de génération (cache KV compris) sur un prompt de ~12 k tokens + question, consigné avec la RAM totale du poste. Verdict dans `.memlog.md` : confirmé si le pic ≤ 4 096 Mo. Le PC cible a 16 Go, le poste de développement 32 Go : si la mesure ne vaut pas pour le PC cible (point ouvert 8), le dire (attente humaine).
- Rapport versionné : `_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/rapport-banc-system-one.md` ; JSON agrégés dans `tools/bench/results/<date>-v12s2/`.

**Never:**
- Pas de code de banc exécuté en réel, d'appel réseau ni de téléchargement dans la phase de spec.
- Pas de modèle à poids ouverts hors liste (Kev 4B, Clef Flash : story ultérieure).
- Pas d'appel réseau en CI, pas de clé en CI, pas de dépendance ajoutée au projet.
- Pas d'intégration d'un candidat dans l'application : la story choisit, les stories suivantes intègrent.
- Pas de données de l'utilisateur, de l'entreprise ou de l'atelier envoyées en ligne.

## I/O & Edge-Case Matrix

| Scénario | Entrée / état | Comportement attendu | Gestion d'erreur |
|----------|--------------|---------------------|------------------|
| Mode à sec | Cas enregistrés, pas de réseau ni de clé | Mêmes métriques et même rapport que le réel | Cas manquant : erreur nommant le modèle et l'item |
| Lancement réel sans clé | Variable et registre vides | Refus avant tout appel | Message sans valeur de clé |
| Modèle absent du point d'accès | Réponse 4xx « unknown model » | Candidat « publié, non mesuré », autres poursuivis | Une seule tentative, pas de relance |
| Plafond atteint | Coût ou appels cumulés au plafond | Arrêt propre, résultats partiels marqués | Rapport « incomplet », jamais de choix |
| Réponse invalide ou délai dépassé | JSON incomplet, 429, 5xx | Item compté en erreur, une relance, puis abandon | Taux d'erreur par modèle dans le rapport |
| Poste occupé | Autre agent actif | Le banc réel n'est pas lancé | N/A |
| Mesure faite sur 32 Go | Poste de développement | Verdict donné avec la mention « valable pour le PC cible 16 Go : à confirmer par Anaël » | Attente humaine si le pic dépasse 3 Go |

</frozen-after-approval>

## Code Map

- `tools/bench/v12s2_system_one_bench.py` -- banc : jeu d'items, appels, métriques, rapport, mode à sec ; réutilise `story12_bench.py` et `v2s6_decision_bench.py` comme `v2s6` le fait.
- `tools/bench/results/<date>-v12s2/` -- agrégats JSON et `recorded/` (cas enregistrés).
- `_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/rapport-banc-system-one.md` -- rapport versionné.
- `tests/test_v12s2_system_one_bench.py` -- logique pure et rejeu à sec.
- `tools/bench/README.md` -- commandes.

## Tasks & Acceptance

- [ ] Critère 1 : construire le jeu d'items depuis les questions et le corpus : couples (question, passage) pour le filtre, couples (passage, affirmation) pour l'ancrage, étiquetés par construction.
- [ ] Critère 2 : adaptateur du point d'accès alpha (requête, réponse, coût, latence), clé lue sans fuite.
- [ ] Critère 3 : adaptateurs locaux sans torch ; candidat non exécutable : « écarté » motivé.
- [ ] Critère 4 : enregistrement de chaque réponse brute (sans clé) et rejeu à sec identique.
- [ ] Critère 5 : métriques par candidat et par tâche (voir points ouverts), avec n et intervalle de confiance.
- [ ] Critère 6 : taux d'affirmations non étayées acceptées (H7), par candidat, comparé au SLM juge.
- [ ] Critère 7 : budget plafond en dollars et en appels, arrêt propre, compteur dans le rapport.
- [ ] Critère 8 : mesure du pic de RSS de Qwen3.5-2B à 16 384 tokens et verdict dans `.memlog.md`.
- [ ] Critère 9 : rapport versionné : tableau des candidats (mesuré ou publié), choix du filtre et de l'ancrage, repli, limites, commandes.
- [ ] Critère 10 : tests en CI sans réseau : construction du jeu, métriques, rejeu à sec, absence de fuite de clé, arrêt au plafond.

**Acceptance Criteria:**
- Given aucun réseau ni clé, when on lance le mode à sec sur les cas enregistrés, then le rapport et les métriques sortent à l'identique de ceux du réel.
- Given le rapport, then chaque ligne est marquée « mesuré » ou « publié, non mesuré » et indique le taux d'affirmations non étayées acceptées.
- Given le rapport, then un filtre et un contrôle d'ancrage sont désignés, avec leur repli, ou la story dit pourquoi aucun candidat ne passe.
- Given `.memlog.md`, then l'hypothèse 16 384 tokens / 4 Go est confirmée ou infirmée avec le pic mesuré et la RAM du poste.

## Points ouverts (proposition ; le relecteur tranche)

1. **Métriques et seuils.** Filtre : rappel du passage attendu >= 0,95 (ne jamais perdre le bon extrait) et part des passages hors-sujet écartés >= 0,60. Ancrage : taux d'affirmations non étayées acceptées (H7) <= 0,13 (niveau du LLM de la littérature, à comparer au SLM juge mesuré) avec rappel des affirmations étayées >= 0,80. Latence : médiane et maximum ; local <= 1 000 ms / 3 000 ms comme `decision-model-candidates.md`, en ligne : informatif. Aussi : AUC, calibration (probabilité moyenne contre taux observé), reproductibilité entre répétitions, taux d'erreur. Un candidat sans mesure H7 n'est jamais choisi.
2. **Taille du jeu.** Filtre : les 21 questions en fr, chacune avec son passage attendu et 3 passages négatifs (même document, document voisin, hors-sujet dont la version périmée) soit environ 84 items ; en et de en échantillon de 7 questions (environ 28 items chacune) pour l'interlingue. Ancrage : par réponse attendue, une affirmation étayée et deux non étayées (chiffre modifié, fait inventé), plus les `no_answer` : environ 63 items en fr, 21 en en et en de. Total environ 240 items.
3. **Répétitions.** 3 par item et par modèle en ligne (T9 a vu un modèle presque non reproductible) ; 1 pour les candidats locaux déterministes.
4. **Budget plafond.** 6 modèles x 240 items x 3 répétitions = environ 4 300 appels, environ 0,26 $ et 18 min à 0,25 s. Plafond proposé : 2,00 $ et 6 000 appels, arrêt dur.
5. **Format et emplacement du rapport.** Markdown dans le dossier de la spec (`rapport-banc-system-one.md`), tableaux par tâche, agrégats JSON sous `tools/bench/results/<date>-v12s2/` ; identifiants d'items seulement, pas de texte de document.
6. **Enregistrement des réponses.** JSONL committé (réponses brutes sans clé, environ 1 Mo), seul moyen de rejouer sans réseau ; contenu Exemplia fictif uniquement. Compression gzip au-delà de 2 Mo.
7. **Ce qui est testé en CI.** Rien de réseau ni de modèle : construction et étiquetage du jeu, métriques sur cas synthétiques, rejeu à sec sur un petit lot (environ 10 items) livré en fixture, masquage de la clé (la valeur d'une fausse clé n'apparaît dans aucune sortie), arrêt au plafond avec un faux transport, cohérence du rapport avec le JSON. Les adaptateurs réels sont marqués et sautés sans clé ni binaire.
8. **Représentativité mémoire.** Le pic de RSS mesuré sur 32 Go vaut pour le PC cible si `n_ctx` est fixé, le modèle chargé en mmap et que le pic ne dépend pas de la RAM libre ; sinon, attente humaine pour une mesure sur le PC 16 Go.

## Verification

- `uv run pytest -q --tb=short tests/test_v12s2_system_one_bench.py tests/test_v2s6_decision_bench.py tests/test_story12_bench.py` -- vert, sans réseau.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `uv run python tools/bench/v12s2_system_one_bench.py dry-run` -- rapport régénéré à l'identique.

## Spec Change Log

- 2026-10-25 : spec rédigée avec les décisions d'Anaël (modèles OpenRouter, clé, données, mode à sec) ; points ouverts proposés.

## Reports

- Modèles à poids ouverts (Kev 4B, Clef Flash) : story ultérieure.
- Lancement réel du banc et mesure mémoire : ressource d'Anaël (poste libre de tout autre agent, clé disponible, GGUF Qwen3.5-2B et binaire llama-server épinglés comme pour `v2s6`).
- Mesure mémoire sur le PC cible 16 Go si le point ouvert 8 ne la valide pas.
