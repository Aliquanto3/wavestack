---
title: 'Story 5 : compréhension de la requête (réécriture, décomposition, suivi, HyDE)'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/brownfield.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/litterature.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les recherches de l'atelier cherchent la question telle qu'elle est tapée. Le participant ne peut pas voir ce que change une requête réécrite, découpée, rendue autonome ou remplacée par une réponse hypothétique, ni ce que cela coûte.

**Approach:** Un nouveau type d'étape, « Query understanding », ouvre le segment de recherche (après le Vector store, avant les recherches). Quatre options, toutes par le modèle actif de l'atelier : `rewrite` (une requête), `decompose` (jusqu'à quatre sous-requêtes), `follow_up` (une question autonome, d'après les questions posées plus tôt dans la session), `hyde` (un document hypothétique). Les recherches cherchent les requêtes produites à la place de la question ; plusieurs requêtes donnent plusieurs listes, fusionnées par rangs réciproques. Les requêtes produites s'affichent dans le focus de l'étape. Chaque option a sa fiche composant (CAP-17) en fr, en et de.

## Boundaries & Constraints

**Always:**
- Les chiffres viennent de la session (AD-1) ; la page range, elle ne calcule rien.
- Le modèle est l'actif de l'atelier ; l'appel passe par la même voie que la génération (événements `model_*`, coût, empreinte), avec sa consigne propre (jamais le prompt système de la brique), sans raisonnement et au plus 256 tokens.
- Sans modèle, sans question précédente (`follow_up`) ou si le modèle ne donne rien d'exploitable, la question est cherchée telle quelle et l'étape le dit (sautée, ou avertissement). Un appel en échec est un échec doux : la chaîne continue.
- Chaque option de `OPTIONS["query"]` a sa fiche dans `sheets` de `rag_lab.yaml`, en fr, en et de : cinq blocs, au moins une source, « ce qu'a mesuré le banc » vide.
- Textes en fr, en et de ; aucune couleur hors des jetons ; ajouts en fin de section dans les fichiers carrefour.

**Never:**
- Pas de nouvel onglet ni de lien « Fiche » dans le focus (onglet Fiches : autre story).
- Pas d'historique de conversation dans l'atelier ni de réponses dans `follow_up` : seulement les questions précédentes.
- Pas de réglage numérique (les bornes sont des constantes de `lab.py`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Décomposition | Question multi-sauts, `decompose` | Au moins deux sous-requêtes dans le focus ; une liste par requête, fusionnée ; chaque extrait donne son rang par requête | N/A |
| Réécriture, HyDE | `rewrite`, `hyde` | Une requête ; HyDE la vectorise comme un passage | N/A |
| Suivi sans passé | `follow_up`, première question de la session | Étape sautée, question cherchée telle quelle | Raison dite dans l'étape |
| Suivi | `follow_up`, questions précédentes | Question autonome ; son prompt cite les questions précédentes | N/A |
| Sortie vide | Le modèle ne dit rien d'utilisable | Question cherchée telle quelle, avertissement | N/A |
| Pas de modèle | Aucun modèle chargé | Étape sautée, note sur les options | N/A |
| Étape après une recherche | Chaîne composée à la main | Refus, ligne de l'étape en cause | `409` si postée |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/lab.py` -- type `query`, `OPTIONS`, `RETRIEVAL`, `STEPS`, `SHEETED_KINDS`, `SheetText`, `LabRun._query`, `parse_queries`, recherches multi-requêtes (`_merged`).
- `src/wavestack/session/app_session.py` -- `GenerationAsk.instruction` dans `_rag_lab_generate`, historique des questions de l'atelier, note « pas de modèle ».
- `src/wavestack/trace/catalog.py` -- `queries` sur `RagLabStageEndedPayload`.
- `src/wavestack/web/static/rag.js`, `rag.css` -- liste des requêtes dans le focus ; ajout d'une étape qui ouvre le segment.
- `content/rag_lab.yaml`, `content/messages.yaml` et surcouches en, de -- textes, consignes, fiches.
- `tests/test_rag_lab_query.py`, scénario E2E `rag_lab_query`, `docs/guide.md`.

## Tasks & Acceptance

- [x] Type d'étape `query` et ses quatre options, registres, séquence, règle d'ordre.
- [x] `LabRun._query` par le modèle actif (faux moteur en test), recherches multi-requêtes, requêtes dans le focus.
- [x] Fiches composant des quatre options, en fr, en et de, validées (clés exhaustives, une source au moins).
- [x] Tests ciblés et scénario E2E `rag_lab_query` (décomposition en au moins deux sous-requêtes).

**Acceptance Criteria:**
- Given une question multi-sauts et `decompose`, then le focus de « Query understanding » liste au moins deux sous-requêtes et la recherche vectorielle les compte.
- Given une option de `query`, then sa fiche existe en fr, en et de avec une source.

## Verification

- `uv run pytest -q --tb=short tests/test_rag_lab_query.py tests/test_rag_lab.py tests/test_i18n.py tests/test_web_tokens.py tests/test_annex_language.py` -- vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag rag_rerank rag_lab rag_lab_views rag_lab_query` -- vert.

## Spec Change Log

- 2026-10-25 : décisions prises à la place d'Anaël, à revoir (voir Reports).

## Reports

- Décisions à revoir : la question de suivi lit les trois dernières questions posées dans la session (sans les réponses), l'atelier n'ayant pas de conversation ; les questions de suivi préparées (avec historique) restent hors du sélecteur ; l'étape est un type à part (`query`), placé après le Vector store, et non une option d'un type existant ; la question tapée est encore vectorisée par l'étape Embedding (un calcul de trop quand une requête la remplace) ; les requêtes d'une décomposition sont fusionnées par rangs réciproques (le score affiché est alors celui de la fusion) ; consigne de chaque option écrite dans `messages.yaml` (`rag_lab.query.instruction`), dans la langue de la session.
- Sources des fiches (Ma 2305.14283, Press 2210.03350, Anantha 2010.04898, Gao 2212.10496) citées sans accès réseau, à ouvrir et vérifier : `litterature.md` demande une source primaire ouverte. MultiHop-RAG et H10 viennent de `litterature.md`.
- Hors périmètre : lien « Fiche » dans le focus et contenu de l'onglet Fiches ; fiches des options des autres types (`SHEETED_KINDS` s'étend story par story) ; rang du passage attendu (CAP-10) ; coût en dollars de l'embedding des sous-requêtes (compté dans la durée de la recherche).

## Revue

### Passe 1 (2026-10-25, SHA revu 6c28e42)

- Important, medium, second avis : `rag_lab_run_ended` d'une mise à jour émis avant `workcopy.save` (préexistant, révélé par l'E2E « Modifier »). Corrigé : `UpdateRun.keep` sauve la copie avant la fin ; un échec de sauvegarde termine en erreur et la session le dit. Tests `test_the_copy_is_saved_before_the_update_says_it_ended` (rouge sur l'ancien code) et `test_an_update_whose_copy_cannot_be_saved_ends_in_error`. L'E2E attend aussi le rechargement de la copie par la page (fetch asynchrone après l'événement), autre cause de l'échec intermittent.
- Important, medium, second avis : `parse_queries` prenait le préambule du modèle (« Voici la question reformulée : ») pour une requête. Corrigé : ligne finissant par « : » écartée, « … : « requête » » réduit à la requête ; cas ajoutés aux tests (dont une vraie requête avec deux-points, conservée).
- Nit, low, second avis : faux modèle E2E limité à la consigne fr de décomposition. Corrigé (en, de reconnus).
- Nit, low, second avis : `_embed_queries` sans embedder lève `vector_search.no_store`. Rejeté : inatteignable, `embedder` et `query_vector` sont posés ensemble et `query_vector is None` est testé avant.
- Nit, low, second avis : historique `_rag_lab_asked` non vidé à la remise à zéro. Corrigé (`reset` l'oublie, test ajouté). Garder les questions des exécutions annulées ou en erreur : rejeté, ce sont des questions posées dans la session, ce que lit `follow_up`.
- Complexité : 0 constat (historique borné à `HISTORY_MAX`, au plus quatre requêtes par recherche).
