---
title: 'Story 19b : fiches de composant des familles restantes (fin de CAP-17)'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/litterature.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/stories/19-fiches-conformite.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'onglet Fiches (story 19) ne sert que les fiches des familles `query`, `chunking` et `context` ; sept familles d'`OPTIONS` (`embedding`, `vector_store`, `vector_search`, `lexical_search`, `fusion`, `rerank`, `generation`, 12 options) sont en attente (`sheets.PENDING_SHEET_KINDS`), donc CAP-17 (« une fiche par composant ») n'est pas tenue. Les embeddings n'ont aucune source dans `litterature.md`.

**Approach:** 12 fiches de composant dans `rag_lab.yaml` (×3 langues), dans le format de `SheetText` (cinq blocs, sources), `lab.SHEETED_KINDS` étendu à toutes les familles, `PENDING_SHEET_KINDS` vidé. Sources : H1 (`vector_search.cosine`, `lexical_search.bm25`, `fusion.rrf`, `rerank.declared`), H14 (les quatre `vector_store.*`), H10 (les deux `generation.*`), liens de `litterature.md` repris tels quels. Embeddings : deux sources primaires ouvertes, vérifiées par lecture réseau (décision 1). Reprise du low reporté de la story 19 : l'onglet dit quand `/api/rag_lab/sheets` échoue.

## Boundaries & Constraints

**Always:** aucune référence écrite de mémoire (chaque URL est dans `litterature.md` ou a été ouverte et lue) ; `bench_text` vide ; aucun chiffre qui ne vienne pas d'une source citée ou du code ; le texte de H14 dit que les quatre vector stores de l'atelier cherchent de façon exhaustive (les pertes de rappel des études portent sur des index approchés) ; fr, en, de mêmes ids et mêmes URL ; `SheetText` et le validateur de `rag_lab.yaml` ne changent pas ; compte de l'E2E lu de `/api/rag_lab/sheets`, pas figé.

**Never:** modifier `rag_sheets.yaml`, les fiches d'architecture, `rag_erasure.yaml`, `litterature.md` ; ajouter un modèle, un téléchargement ou un appel réseau à l'exécution.

## I/O & Edge-Case Matrix

| Cas | Entrée | Sortie |
|---|---|---|
| Liste | `GET /api/rag_lab/sheets` | tous les `kind.option` d'`OPTIONS` ; `pending` = `[]`, `pending_text` = `""` |
| Fiche d'une famille restante | `.../component/vector_store.faiss` | 5 blocs, sources H14, `bench_text` vide |
| Option inconnue | `.../component/embedding.unknown` | 404 |
| API en échec | `/api/rag_lab/sheets` ne répond pas | l'onglet affiche `rag.sheets_error` (ui.yaml ×3) ; la réouverture réessaie |

</frozen-after-approval>

## Code Map

- `content/rag_lab.yaml`, `content/i18n/{en,de}/rag_lab.yaml` : 12 entrées de `sheets`, avant celles du contexte (ajouts seulement).
- `src/wavestack/rag/lab.py` : `SHEETED_KINDS` = les dix familles d'`OPTIONS`.
- `src/wavestack/rag/sheets.py` : `PENDING_SHEET_KINDS = ()` ; `pending_text` vide sans famille en attente.
- `src/wavestack/web/static/rag-sheets.js` : message d'échec de `load()`, note « en attente » omise si vide.
- `content/ui.yaml` ×3 : `rag.sheets_error`.
- `tests/test_rag_sheets.py` ; `tools/e2e/run_e2e.py` (`_sheet_entries`, `s_rag_lab_sheets`, `_rag_lab_tabs`), `tools/e2e/README.md`, captures `70-atelier-rag-fiches*.jpg`.

## Acceptance Criteria

1. Chaque `kind.option` d'`OPTIONS` a une fiche servie ×3 langues ; la partition `SHEETED_KINDS` / `PENDING_SHEET_KINDS` tient (la seconde est vide) ; une famille ajoutée plus tard sans fiche fait échouer `missing_sheets()`.
2. Chaque fiche de composant a au moins une source `https://` ; les sources de `vector_search.cosine`, `lexical_search.bm25`, `fusion.rrf`, `rerank.declared` (H1), des `vector_store.*` (H14) et des `generation.*` (H10) sont exactement les liens de la ligne de `litterature.md` (test, saute si le dossier de specs est absent).
3. Les fiches `embedding.*` citent Sentence-BERT (arXiv 1908.10084) et DPR (arXiv 2004.04906) ; `embedding.fastembed` ajoute le dépôt `qdrant/fastembed` ; aucune n'est dans `litterature.md` et le texte dit que le cadrage ne couvre pas les embeddings.
4. `GET /api/rag_lab/sheets` : `pending` vide, aucun message « à venir (story 19b) » à l'écran ; 404 sur une option inconnue d'une famille.
5. Une panne de `/api/rag_lab/sheets` affiche un texte (3 langues) au lieu d'un panneau vide.
6. E2E `rag_lab_sheets` et `rag_lab_views` : le compte des entrées vient de l'API et passe quand 12.11 ajoute des options.

## Verification

- `uv run pytest -q --tb=short tests/test_rag_sheets.py tests/test_i18n.py tests/test_rag_lab_query.py tests/test_rag_lab_context.py tests/test_rag_lab.py` : 371 passed, 1 skipped.
- `uv run python .claude/cost-kit/controle_rapide.py`.
- E2E `rag rag_rerank rag_lab rag_lab_sheets rag_lab_views` : 172 vérifications, 0 échec.

## Décisions

1. **Embeddings : sources primaires, pas de `no_source_text`.** `SheetText` garde `sources` obligatoire (min 1). Sentence-BERT et DPR ont été ouverts sur arXiv (titre, auteurs, résumé lus) ; les chiffres cités (65 h → 5 s ; 9 à 19 points au top 20) viennent de leurs résumés. `fastembed` cite en plus le dépôt `github.com/qdrant/fastembed` (ouvert, HTTP 200). Ces trois URL ne sont pas dans `litterature.md` : à y ajouter (hypothèse « embeddings ») à la prochaine révision du cadrage.
2. **Les littératures H1 et H14 décrivent des mesures de chaînes ou d'index approchés** : les fiches le disent (`hybrid + reranker` mesuré en bloc ; recall ANN sans objet pour les quatre vector stores exhaustifs de l'atelier). Aucune source ajoutée pour BM25, RRF ou le reranker seul (pas de référence ouverte).
3. **`generation.not_run`** cite H10 pour justifier de mesurer la recherche sans générer ; le texte dit que les hypothèses ne couvrent pas l'option.
4. **Pas de `no_source_text` générique** : le champ n'existe que pour les fiches d'architecture (RAPTOR).

## Reports

- Relecture humaine (Anaël) des 12 fiches en fr, en, de : exactitude des formulations sur FAISS, LanceDB, sqlite-vec, fastembed ; lecture de H14 (« exhaustif, pas approché »).
- Ajouter à `litterature.md` une hypothèse « embeddings » avec Sentence-BERT et DPR.
- Source primaire pour BM25, RRF et le reranking seul : session avec accès aux articles d'origine.
- Rebaser sur l'intégration après 12.11 : refusion de `rag_lab.yaml` ×3 (ajouts seulement, deux entrées `context.*`), compte E2E déjà dérivé de l'API.
