---
title: 'Story 8 : couche de décision System One (routeur, filtre de passages, contrôle d''ancrage)'
type: 'feature'
created: '2026-10-25'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/architectures.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/rapport-banc-system-one.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/litterature.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'atelier n'a aucune décision « System One » (CAP-6) : ni routeur de stratégie, ni filtre de passages, ni contrôle d'ancrage, et le participant ne voit jamais qui décide, avec quelle probabilité, ni ce que change le seuil ou la bascule vers un SLM juge.

**Approach:** Trois nouveaux types d'étape, aux libellés de la maquette : `router` (« Strategy router », dans le segment, avant les recherches), `passage_filter` (« Passage filter », dans le segment, après une recherche) et `grounding_check` (« Grounding check », seul type autorisé après la génération, `CHECKS`). Chacun a deux options : `local` (modèle choisi par le banc de la story 2) et `cloud` (API de décision d'OpenRouter, `/api/alpha/decisions`, celle du banc). Deux réglages par option : `decision_threshold` (1 à 99 %, défaut du banc) et `judge_cascade` (0 ou 1, défaut 0). Règle : au seuil ou au-dessus, le classifieur décide seul ; en dessous, il refuse (passage rejeté, phrase non ancrée, choix de stratégie gardé « sous le seuil ») ou, cascade active, le SLM juge (le modèle actif de l'atelier, une tâche courte « un seul mot : oui ou non ») décide. Chaque décision porte son auteur, sa probabilité et le seuil (`decisions` de `rag_lab_stage_ended`, focus par `rag-decision.js`).

## Boundaries & Constraints

**Always:**
- Modèles du banc : filtre local = reranker livré (seuil sur le score, défaut 2 %), cloud = PPLX Decider Flash 1.2 (13 %) ; ancrage local = deberta_xsmall (20 %), cloud = Jev 1.14 (59 %) ; routeur local = deberta_xsmall (NLI zero-shot, une hypothèse par stratégie, softmax des logits d'implication), cloud = Jev 1.14 en question `choice` (50 %). Formulations exactes du rapport (§ 7) dans `rag/decision.py`.
- deberta_xsmall déclaré dans `wavestack.toml` (`[rag_lab.decision.classifier]`, trois fichiers, URL épinglées à la révision 262ae02f…, tailles et sha256), téléchargé par « Télécharger » (`rag_lab_decision:<id>`), sha256 vérifié au chargement, chargé dans le budget mémoire (`Loans`, 351 Mo mesurés), fermé en fin d'exécution. Lu par l'extra nouveau `decision` (onnxruntime, tokenizers, mêmes versions que `guardrails`, sans Presidio ni spaCy), justifié dans `brownfield.md`. Sans l'extra ou sans les fichiers : option indisponible avec sa raison et l'offre de téléchargement ; l'étape est sautée, jamais une panne.
- Option cloud : clé `OPENROUTER_API_KEY` (variable, sinon `HKCU\Environment`), jamais affichée, écrite ni tracée (en-tête masqué par `net.factory`) ; sans clé, option grisée avec la variable nommée. Client tracé de l'application (`create_client`), hôte `openrouter.ai` seul (liste blanche du client et `[net] allowed_hosts`). Chaque appel refusé une fois `[finops] max_session_usd` atteint ; le coût rendu (`usage.cost`) entre dans la dépense de session (`consumption_updated`). Refus sur une copie de travail modifiée (seul le corpus fictif livré part au cloud).
- Un échec de décision (API, classifieur) est doux : la chaîne continue comme sans l'étape. Le routeur n'écarte que des étapes présentes (BM25, fusion, reranking) ; avec moins de deux stratégies possibles, il est sauté.
- Exposition MCP (12.20) : une chaîne avec une étape System One est refusée (`model_stage`) ; aucun filtre `hr` ajouté.
- Fiches des six options en fr, en, de (littérature H6 pour le routeur, H7 pour le filtre et l'ancrage, chiffres du banc dans « Ce qu'a mesuré le banc »).

**Never:**
- Aucun appel réseau dans les tests (fausse API `httpx.MockTransport`, faux classifieur, faux moteur en juge) ; le test du vrai ONNX saute sans l'extra ou les fichiers.
- Pas de torch, pas de lecture du cache du banc par l'application.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Filtre, cascade off | p < seuil | Rejeté par le classifieur, « sous le seuil » | N/A |
| Filtre, cascade on | p < seuil, juge « oui » | Gardé, auteur « SLM juge » | Juge illisible ou absent : refus du classifieur, dit |
| Baisser le seuil | 99 % puis 1 %, cascade on | L'auteur d'au moins une décision passe de juge à classifieur | N/A |
| Routeur | Chaîne dense + reranking | Stratégie choisie, étapes non utilisées « sautées » avec la raison | < 2 stratégies : étape sautée |
| Ancrage | Réponse de N phrases | 8 phrases au plus, ancrée / non ancrée | Pas de réponse : sautée |
| Cloud sans clé | — | Option grisée, raison `OPENROUTER_API_KEY` | N/A |
| Cloud, plafond atteint | — | Aucun appel, étape en erreur douce | N/A |
| API en erreur | HTTP 503 | Étape en erreur douce, chaîne continue | Clé jamais dans le message |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/decision.py` (nouveau) -- règle de cascade, juge, phrases, `NliClassifier` (ONNX), `DecisionApi` (noul, choice, score), `CappedApi`, clé.
- `src/wavestack/rag/lab.py` -- `KINDS`, `RETRIEVAL`, `CHECKS`, `DECISION_KINDS`, `OPTIONS`, `PARAMS`, `BOUNDS`, `OPTION_PARAM_DEFAULTS` (lu par `param()`), `STEPS`, `COMPONENTS` (`decision_model`), `SHEETED_KINDS`, `INSERT_AFTER`, `check_pipeline` (checks en fin, routeur avant, filtre après), `LabDeps` (`classifier`, `decision_api`, `decision_models`), `_Chain` (`routed_out`, `answer`), `_Result.decisions`, `_router`, `_passage_filter`, `_grounding`.
- `src/wavestack/session/app_session.py` -- états du catalogue, prêt du classifieur, API plafonnée, cible de téléchargement.
- `src/wavestack/config.py` -- `DecisionModel`, `rag_lab_decision_classifier`, `rag_lab_decision_models`.
- `src/wavestack/rag/exposed.py`, `src/wavestack/trace/catalog.py` (`RagLabDecision`), `web/static/rag-decision.js`, `rag.js` (palette, retrait d'un check), `rag.css`, `rag.html`.
- `content/{,i18n/en/,i18n/de/}{rag_lab,messages,ui}.yaml`, `wavestack.toml`, `pyproject.toml`, `uv.lock`, `docs/installation.md`, `brownfield.md`.
- `tests/test_rag_lab_decision.py` (nouveau), réalignés : `tests/test_rag_lab.py`, `tests/test_rag_sheets.py` ; E2E `rag_lab_decision`, faux modèle juge (`tools/e2e/fake_openai.py`).

## Tasks & Acceptance

- [x] Registres, réglages, règles de chaîne, fiches fr/en/de.
- [x] Filtre, routeur, ancrage ; cascade ; décisions dans la charge utile et le focus.
- [x] Classifieur local déclaré, téléchargeable, extra `decision`, repli sans lui.
- [x] API de décision (fausse API en test), clé, plafond, dépense, refus copie de travail.
- [x] Tests ciblés et E2E `rag_lab_decision`.

**Acceptance Criteria:**
1. Given une étape System One, then chaque décision affiche son auteur (classifieur ou juge), sa probabilité et le seuil.
2. Given le filtre avec la cascade, then passer le seuil de 99 % à 1 % change l'auteur d'au moins une décision sur une question du jeu (test et E2E).
3. Given aucune clé, then les options cloud sont grisées avec la variable nommée ; avec une clé et une fausse API, le filtre appelle l'API, la dépense est enregistrée et la clé n'apparaît nulle part.
4. Given le banc de la story 2, then les seuils par défaut sont les siens et la fiche dit qu'ils sont optimistes ; la cascade est désactivée par défaut et dite « non validée par le banc (H7 64 %) ».

## Décisions à revoir par Anaël

1. Cascade vers le SLM juge gardée comme réglage `judge_cascade`, désactivée par défaut, avertissement « non validée par le banc » à chaque exécution où elle est active (décision provisoire de l'orchestrateur).
2. Sens du seuil : celui du banc (« part des items sous le seuil : bascule vers le juge »), pas une zone de confiance autour de 0,5 comme la maquette le suggère (« p = 0,08 rejeté par le classifieur »). Sous le seuil, sans cascade, le classifieur refuse.
3. Seuil en pour cent entier (les réglages de l'atelier sont entiers) ; défauts du banc, routeur à 50 % (non mesuré).
4. Routeur : choix parmi les préréglages de recherche que la chaîne sait faire (dense, hybride, + reranking), effet = étapes non utilisées sautées ; hypothèses de routage écrites par le développement, non mesurées (H6).
5. Filtre local : relit les candidats avec le reranker de la brique, même après un Reranking (pas de réutilisation des scores arrondis).
6. Option cloud du filtre = PPLX Decider Flash 1.2 (choix du banc) ; Jev 1.14 pour le routeur et l'ancrage. Modèles réglables dans `[rag_lab.decision]`.
7. Forme des questions `choice` et `score` de l'endpoint alpha d'après architectures.md, jamais appelée par le banc : à vérifier lors d'un premier appel réel.
8. `openrouter.ai` ajouté à `[net] allowed_hosts` (sinon la garde réseau bloque l'option cloud).
9. Les fiches System One remplissent « Ce qu'a mesuré le banc » (les autres restent vides) ; le test des fiches est réaligné.
10. Le juge n'a pas de grammaire GBNF ici (tâche courte du modèle actif), ni de probabilité : sa décision n'a que son verdict.

## Verification

- `uv run pytest -q --tb=short tests/test_rag_lab_decision.py tests/test_rag_lab.py tests/test_rag_sheets.py tests/test_rag_erasure.py tests/test_rag_mcp.py tests/test_i18n.py tests/test_ui_texts.py` -- vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag rag_rerank rag_lab_decision`, puis `--only rag rag_rerank rag_lab` -- vert.

## Reports

- Diagnostic (story 9) : un passage attendu rejeté par le filtre est attribué au Contexte (`cut`), pas au filtre ; à ajouter à `diagnosis.RANKED`.
- Vue Comparer : la liste « Recherche » ne lit pas la sortie du filtre (`RETRIEVAL_KINDS` de `rag-compare.js`).
- Mesure sur le PC cible : latence et RAM de deberta_xsmall avec l'extra (tâche humaine), premier appel réel des formes `choice`/`score`.
- E2E : le poste de développement a une clé dans `HKCU\Environment` ; la branche « option cloud grisée » de `rag_lab_decision` n'est vérifiée que sans clé (la palette peut alors proposer l'option cloud par défaut pour le Grounding check quand le classifieur local manque).
- E2E `rag_lab_context` : liste des options du contexte réalignée en revue (neuf options, une option ajoutée ensuite, comme `wiki_pages` de 12.14, est tolérée en fin de liste).
- Premier appel réel : vérifier que `usage.cost` est rendu à chaque réponse de `/api/alpha/decisions` ; sans lui, l'appel est « non chiffré » et ne compte pas dans `[finops] max_session_usd` (même règle que le banc, qui le comptait 0).

## Revue

### Passe 1 (2026-10-25, SHA revu 76f6a095)

Branche à jour de `origin/integration/v1-2-atelier` (aucun écart).

- Important · high · second avis 1 · corrigé : la palette ajoutait l'option cloud quand le classifieur local manquait et que la clé était présente (`rag.js`). Une option `cloud` n'est plus jamais choisie par défaut : l'étape arrive en `local`, indisponible avec sa raison et « Télécharger » ; vérification E2E ajoutée dans `rag_lab_decision`.
- Important · high · revue · corrigé : `DecisionApi` créait un `httpx.Client` hors de `net.factory` (AD-15, `tests/test_net_single_factory.py` rouge). Le client par défaut vient maintenant de `create_client`.
- Important · medium · revue · corrigé : `tests/test_rag_lab_query.py` exigeait encore des fiches sans « Ce qu'a mesuré le banc » (rouge en fr, en, de) ; réaligné sur la décision 9.
- Important · medium · second avis 4 · corrigé (texte) : l'avertissement de la cascade et la fiche d'ancrage prêtaient au juge d'ici les 64 % / 49 % du juge du banc (Qwen3.5-2B, grammaire, probabilité). Les textes fr, en, de disent maintenant que ces chiffres viennent du juge du banc et que le juge d'ici (modèle actif, sans grammaire) n'a pas été mesuré. Implémenter le juge du banc (GBNF + probabilité) n'est pas « peu de code » : passe par le moteur et sort du périmètre de la story.
- Nit · medium · second avis 2 · rejeté, reporté : un appel sans `usage.cost` ne compte pas dans le plafond. Le banc suivait la même règle et rendait le coût ; un coût estimé serait un chiffre inventé (aucun tarif de l'endpoint alpha). L'étape le dit (« non chiffré ») ; vérification au premier appel réel en report.
- Nit · medium · second avis 3 · rejeté : `openrouter.ai` dans `[net] allowed_hosts` est exigé par la spec (liste du client et liste globale) ; la garde AD-15 est globale par conception (GitHub, Wikipédia), et `DecisionApi.check_host` restreint déjà son client. Un autre client vers cet hôte n'a pas la clé.
- Nit · low · second avis 5 · rejeté : une erreur en milieu de boucle du filtre cloud ne perd pas la dépense (chaque réponse est enregistrée dans la session par `CappedApi`) ; seul le tableau des coûts de l'étape, en erreur douce, ne la montre pas.
- Pre-existing · low · second avis 6 · non corrigé : `config._message` est annoté `-> str` ; `Message` hérite de `str`, aucun défaut à l'exécution.
- Pre-existing · medium · second avis 7 · corrigé (demande de l'orchestrateur) : l'E2E `rag_lab_context` attendait six options du contexte, il y en a neuf.
- Complexité : 0 constat (décisions bornées par les candidats, 8 phrases au plus, 3 stratégies).
