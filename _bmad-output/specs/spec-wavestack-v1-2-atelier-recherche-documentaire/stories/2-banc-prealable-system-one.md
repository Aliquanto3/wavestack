---
title: 'Story 2 : banc préalable System One et fenêtre de 16 384 tokens'
type: 'feature'
created: '2026-10-25'
status: 'ready-for-dev'
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
- Données envoyées : seulement le corpus fictif Exemplia et le jeu de questions (`content/rag_questions.yaml` et ses copies `content/i18n/{en,de}/`) ; un contrôle refuse tout texte venant d'ailleurs.
- Format d'appel d'après T9 : `{model, state, questions: {<id>: {type: "noul", instructions}}}`, en-tête `Authorization: Bearer <clé>` ; réponse `model` (version datée, ex. `typesafe/jev-1.14-20261014`), `answers.<id>.noul` (probabilité du oui), `usage.input_tokens`, `usage.cost`. T9 n'a vérifié sur OpenRouter que `noul` (`choice` et `probabilities` l'ont été sur Ollama et llama-server, V2 stories 8 et 9) : le banc n'emploie que `noul`. Coût observé ~0,00006 $ et 0,25 s par appel (Jev seul).
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
- `tools/bench/data/v12s2_claims.yaml` -- affirmations non étayées écrites à la main (fr, en, de), fictives, par question (point 2 tranché).
- `tests/test_v12s2_system_one_bench.py` -- logique pure et rejeu à sec ; fixture `tests/fixtures/v12s2/` (~10 items, réponses synthétiques).
- Réutilisés sans copie : `wavestack.rag.corpus` (`load_rag_questions`, `load_rag_content`, `read_documents`, `chunk_corpus`), `v2s6` (`_load_nli`, `_load_slm_judge`, mesure RAM et garde réseau du fils), `app_session._kv_per_token` (comparaison au pic mesuré).
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

## Décisions du point de contrôle (2026-10-25)

Relu contre `stories.yaml` (id 2), SPEC.md, architectures.md, evaluation.md, corpus-et-questions.md, brownfield.md, `.memlog.md`, `v2s6_decision_bench.py`, `decision-model-candidates.md` et T9 (`veille-agents-code/tests-pratiques/T9`). Comptages faits sur le dépôt, pas supposés. « À revoir » : décidé ici à la place d'Anaël, sans bloquer le développement.

**Faits vérifiés qui changent la proposition.**
- Jeu de questions : 21 questions par langue (fr, en, de ; 7 types × 3), dont 3 `no_answer` sans passage ; 27 passages attendus par langue (factuelle et suivi : 1, multi-sauts : 2, globale : 3, temporelle : 1 plus 1 passage piège `trap_passages`, interlingue : 1). Corpus : 27 documents déclarés, 25 actifs, 2 inactifs (`faq_mots_de_passe`, document piégé ; `projet_orion`, sentinelle), 3 monolingues (`rundschreiben_usb` de, `uk_visitor_badges` en, `plan_continuite_lyon` fr), 3 documents RH fictifs. Tokens du corpus actif (cl100k, story 1) : fr 9 762, en 7 099, de 10 622.
- T9 : Jev est **déterministe** (« même état = même réponse ») ; le modèle « presque non reproductible » est `mimo-v2.6-pro` par `chat/completions`, pas un modèle de décision. Probabilités rendues au centième (ex æquo fréquents). Identifiants : `typesafe/jev-latest` sans tilde est refusé, `typesafe/jev-1.13` accepté ; prix et comportement des cinq autres modèles inconnus.
- SPEC.md ne fixe aucun seuil chiffré. Seule origine documentée : H7 (`litterature.md`, un seul article Towards AI) : 23 % d'affirmations non étayées acceptées par Jev, 13 % par un LLM. Les seuils du filtre sont une proposition du développement.
- Contrainte de SPEC.md : un modèle cloud n'est jamais un prérequis, et le moteur est hors ligne.

**Points tranchés.**
1. **Seuils : acceptés avec trois corrections.** (a) Le **choix par défaut est toujours local** ; un modèle en ligne n'est désigné que comme option cloud (CAP-6, Jev), à part. (b) Seuils définis au point de fonctionnement, puisque CAP-6 a un seuil réglable : filtre, au seuil de probabilité le plus haut qui garde un rappel du passage attendu ≥ 0,95, part des négatifs écartés ≥ 0,60 (à revoir : proposition du dev, sans source) ; ancrage, au seuil qui garde un rappel des étayées ≥ 0,80, part des non étayées acceptées ≤ 0,13 (origine H7 : le niveau LLM de la littérature). Seuil ajusté sur le jeu lui-même, donc optimiste : le rapport le dit et donne aussi les chiffres au seuil fixe 0,5. (c) Le reranker livré est la **référence du filtre** : un modèle de décision n'est choisi comme filtre que s'il écarte plus de négatifs que le seuil sur le score du reranker, au même rappel ; sinon le reranker est le choix. Candidat local : les six critères de `decision-model-candidates.md` s'appliquent (RAM avec le SLM chargé ≤ 4 096 Mo, latence ≤ 1 000 / 3 000 ms par décision, hors ligne sous AD-15, épinglage, licence, roues sans compilation) ; le rapport donne aussi la latence par requête pour k = 3 (`top_k`) et k = 8 (`rerank_candidates`). AUC avec IC à 95 % (bootstrap, ex æquo à 0,5), calibration sur 5 classes, reproductibilité (écart max entre répétitions), taux d'erreur (> 5 % : « à surveiller », jamais choisi). Un candidat sans mesure H7 n'est jamais choisi pour l'ancrage. H7 décidé sur les trois langues regroupées (items traduits, donc non indépendants : IC optimiste, dit), détail par langue.
2. **Jeu : incohérent avec le jeu réel, recalculé (~450 items).** Passages = chunks de `chunk_corpus` au découpage par défaut de la brique RAG (ceux que le filtre verra), corpus actif seulement (piégé et sentinelle exclus : inactifs, et le piégé porte une injection). Filtre, par langue : 27 positifs (chunk qui contient l'ancre ; ancre à cheval sur deux chunks : item écarté et compté) + 3 négatifs par question pour les 21 questions (même document hors ancres ; meilleur chunk BM25 d'un document non attendu, « difficile » ; chunk tiré avec graine fixe d'un document non attendu) + 3 passages périmés (`trap_passages`), comptés à part et hors de la part écartée = 93 ; × 3 langues (le coût est négligeable, l'échantillon de 7 questions est abandonné) = 279. Ancrage, par langue : prémisse = chunks attendus + le négatif difficile, ordre tiré avec graine fixe ; 18 affirmations étayées (`expected_answer_text`), 36 non étayées (chiffre modifié, fait inventé ; sans chiffre dans la réponse : fait inventé et inversion), 3 réponses inventées pour les `no_answer` = 57 ; × 3 = 171. Les non étayées sont écrites à la main dans `tools/bench/data/v12s2_claims.yaml` (fictives, aucune génération par modèle) ; test : tout nombre d'une affirmation étayée figure dans sa prémisse, aucune affirmation non étayée n'est une sous-chaîne de sa prémisse. Troncature à 512 tokens des NLI comptée par item. Données RH fictives envoyées : admises (corpus Exemplia).
3. **Répétitions : 2 en ligne (pas 3), 1 en local.** Motif de la proposition erroné (voir T9) ; deux passes suffisent à mesurer la reproductibilité des cinq modèles non mesurés. Local : 1 passe plus 20 items rejoués ; écart de probabilité > 1e-4 : le candidat est rejoué 3 fois et dit non déterministe. À revoir.
4. **Budget : 450 × 6 × 2 = 5 400 appels + 6 sondes**, ~23 min à 0,25 s hors modèle gratuit. Plafond dur 2,00 $ et 6 000 appels (gardé), **plus un plafond par modèle de 0,33 $** (à revoir) : un modèle cher s'arrête seul, marqué « incomplet », sans affamer les autres. Avant chaque appel : coût cumulé + coût max observé du modèle ≤ plafond. Une sonde par modèle sur un item avant sa série : identifiant refusé (4xx « unknown model ») → « publié, non mesuré », une seule tentative. Erreurs : 429 → attente `Retry-After` (≤ 60 s), 3 essais, non compté en erreur ; 5xx, délai, JSON invalide → 1 relance puis erreur. `inception/mercury-decide:free` : débit borné à 20 requêtes/min et arrêt propre sur limite quotidienne (limites des modèles gratuits d'OpenRouter à relire le jour du banc). Lancement **reprenable** : les items déjà enregistrés ne sont pas rappelés.
5. **Rapport : accepté.** Sans date de génération ni chemin local : seules les dates d'enregistrement des cas y figurent, pour que le rejeu soit identique à l'octet. Pour les stories 8 et 12, il donne en plus, par rôle (filtre, ancrage) : le modèle par défaut (local) et son repli, l'option cloud, le seuil par défaut et la part d'items qui basculent vers le SLM juge à 3 seuils (CAP-6 : « baisser le seuil change l'auteur d'au moins une décision »), la distribution des probabilités, la formulation exacte des `instructions` utilisées, l'identifiant de modèle rendu (version datée), commit, sha256 et versions des paquets du candidat local, la latence par requête à k = 3 et 8 ; et pour la story 10, le pic mémoire comparé à l'estimation `_kv_per_token × 16 384`.
6. **Enregistrement : liste blanche, pas réponse brute.** Une ligne JSONL par appel : `item_id`, candidat, répétition, sha256 du corps de requête (sans en-tête ; le texte se reconstruit depuis le dépôt, un sha256 différent rend le cas « périmé » au rejeu), statut HTTP, champs retenus de la réponse (`model`, `answers.<id>.noul`, `usage.input_tokens`, `usage.output_tokens`, `usage.cost`), latence, date. Ni en-tête, ni `id` de génération, ni champ inconnu (test sur une réponse factice qui en porte). Les candidats locaux sont enregistrés au même format (probabilité, latence), et leurs mesures RAM dans le JSON, sinon le mode à sec ne refait pas tout le rapport. Taille estimée ~1,5 Mo ; gzip au-delà de 2 Mo.
7. **CI : acceptée, complétée.** `uv sync --locked` seul (pas d'onnxruntime, pas de modèle) ; module importable sans dépendance tierce au niveau module, comme `v2s6`. En plus : faux transport `httpx.MockTransport` qui vérifie la forme exacte de la requête (`model`, `state`, `questions.<id>.type == "noul"`, en-tête `Authorization`) et refuse le reste ; liste blanche réseau du lancement réel limitée à `openrouter.ai` (autre hôte : erreur) ; contrôle de provenance des textes (passage absent du corpus actif : refus) ; fausse clé absente de toutes les sorties, journaux et exceptions (y compris le texte d'erreur HTTP relayé) ; arrêt aux deux plafonds ; reprise ; rejeu du fixture identique à l'octet.
8. **Mémoire : accepté, précisé.** Mesure par la classe du moteur de l'application (`llama_cpp.Llama(model_path, n_ctx=16384)`, défauts : mmap, `n_batch` 512), dans un fils sous la garde réseau, prompt = préréglage `long_context` en de (corpus le plus long) + une question, puis variante remplie jusqu'à 16 384 − 256 tokens ; pic de l'ensemble de travail et pic de mémoire privée consignés, avec la RAM totale. llama.cpp alloue le cache KV pour tout `n_ctx` à la création du contexte, et la mémoire privée ne dépend pas de la RAM libre ; l'ensemble de travail, lui, ne peut que baisser sous pression : la mesure sur 32 Go est un majorant pour le PC 16 Go. Verdict : pic ≤ 3 072 Mo, confirmé ; 3 072 à 4 096 Mo, confirmé sur le poste de dev, confirmation sur le PC cible demandée (attente humaine non bloquante, matrice) ; > 4 096 Mo, infirmé. Le rapport ajoute le total avec le RAG V1 (+1 170 Mo, mesure V2), informatif.

**Faisabilité des candidats locaux sans torch.**
- `deberta_xsmall` et petit NLI ONNX : faisables, déjà épinglés et mesurés par `v2s6` (onnxruntime 1.30.0, tokenizers, huggingface-hub par `uv run --with`). Le petit NLI retenu est `mdeberta` (multilingue, 339 Mo, commit `b5113eb3…`) : aucun nouveau modèle à relire. Limite : 512 tokens.
- Reranker livré (`bge-reranker-v2-m3` Q4_K_M, GGUF épinglé dans `wavestack.toml`) : faisable par llama-cpp-python, dépendance de base ; score non probabiliste (AUC et seuil seulement, calibration « sans objet »).
- SLM juge Qwen3.5-2B + GBNF : faisable (`_load_slm_judge`). Probabilité : softmax des logprobs des deux premiers jetons permis (`oui`/`non`) ; si llama-cpp-python ne les rend pas sous grammaire, AUC et calibration « non calculables », taux H7 calculé sur l'étiquette.
- Strands Decider 2B et AnyJev : **existence, format et licence non vérifiés** (aucune trace dans le dépôt hors cadrage ; le lien AnyJev pointe un dépôt GitHub). Première tâche du dev : lire la carte ou le README à un commit fixé (lecture, sans téléchargement). Mesurés seulement s'ils tournent par ONNX, par llama-cpp-python ou par le llama-server portable `b11378` déjà admis ; sinon « écarté », motif écrit (torch, service, compilation), jamais de chiffre inventé. Un modèle causal tombe sous la règle d'un seul modèle génératif : au mieux « à surveiller », comme tev1. RAM avec le SLM chargé : un 2B en Q4 (~1,3 Go) + le SLM (~1,95 Go) laisse peu de marge.


## Verification

- `uv run pytest -q --tb=short tests/test_v12s2_system_one_bench.py tests/test_v2s6_decision_bench.py tests/test_story12_bench.py` -- vert, sans réseau.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `uv run python tools/bench/v12s2_system_one_bench.py dry-run` -- rapport régénéré à l'identique (comparaison à l'octet : `git diff --exit-code` sur le rapport et les JSON).

## Spec Change Log

- 2026-10-25 : spec rédigée avec les décisions d'Anaël (modèles OpenRouter, clé, données, mode à sec) ; points ouverts proposés.
- 2026-10-25, point de contrôle de spec (`ready-for-dev`) : points ouverts tranchés (section dédiée). Corrections dans le bloc d'intention, faits seulement : copies i18n du jeu de questions ; format T9 (`noul` seul vérifié sur OpenRouter, `choice` non employé, version datée rendue). Code Map : fichier d'affirmations, fixture, fonctions réutilisées.

## Reports

- Modèles à poids ouverts (Kev 4B, Clef Flash) : story ultérieure.
- Lancement réel du banc et mesure mémoire : ressource d'Anaël (poste libre de tout autre agent, clé disponible, GGUF Qwen3.5-2B et binaire llama-server épinglés comme pour `v2s6`).
- Mesure mémoire sur le PC cible 16 Go si le pic mesuré sur 32 Go est entre 3 072 et 4 096 Mo (point 8 tranché).
- Ressources du banc réel : ordre d'Anaël, poste libre ; clé OpenRouter avec crédit (limites quotidiennes du modèle `:free` à relire) ; GGUF Qwen3.5-2B par défaut et reranker de la brique déjà téléchargés ; snapshots ONNX `deberta_xsmall` et `mdeberta` (`--download`, une fois) ; llama-server `b11378` seulement si Strands Decider 2B ou AnyJev passent par lui. Durée estimée : ~25 min à 1 h en ligne, ~1 h en local (SLM juge, ~450 décisions), ~10 min pour la mémoire.
