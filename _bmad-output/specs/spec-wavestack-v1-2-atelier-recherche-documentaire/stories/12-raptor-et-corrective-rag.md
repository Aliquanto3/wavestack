---
title: 'Story 12 : RAPTOR et Corrective RAG'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/architectures.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/litterature.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/vues.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/rapport-banc-system-one.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/stories/8-couche-de-decision-system-one.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/stories/11-recherche-agentique-et-pageindex.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/stories/13-graphrag-simplifie.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-7 compte huit architectures de plus ; après les stories 10, 11 et 13, deux manquent encore à l'atelier : RAPTOR (famille « Structure », un arbre de résumés hiérarchiques, `architectures.md` : « Regroupement des chunks et résumés récursifs · Résumés des branches touchées à refaire · Recherche sur tous les niveaux ») et Corrective RAG (famille « Recherche », « Filtre des passages, puis repli : réécriture et nouvelle recherche, ou je ne sais pas », qui réutilise le `passage_filter` de la story 8). Les endroits `raptor_summaries` de la story 18 sont écrits à la main (`constructed`, `story: 12`), les fiches `raptor` et `crag` de la story 19 portent `story: 12`, et la fiche RAPTOR dit n'avoir aucune source primaire.

**Approach:** Deux préréglages, sur les modèles des stories 11, 13 et 8.

- **RAPTOR** (`raptor`, famille `structure` entre PageIndex et GraphRAG, segment vide) : une option de Contexte, `raptor_search`, qui cherche sur **tous les nœuds** d'un arbre précalculé (« arbre aplati » de l'article : passages et résumés ensemble), livré dans `content/rag_raptor.yaml` ×3, construit par une règle déterministe sans modèle ; « Reconstruire l'arbre » fait écrire chaque résumé par le modèle actif ; « Rétablir » rend l'arbre livré.
- **Corrective RAG** (`crag`, famille `search` après le reranking) : la chaîne hybride (cosinus, BM25, RRF), le filtre de passages local de la story 8 (reranker livré, seuil du banc 2 %), puis un nouveau type d'étape `fallback` (« Repli correctif »), option `retry` : si le filtre n'a gardé aucun passage, le modèle actif réécrit la question (consigne `rewrite` de la story 5), la recherche et le filtre repassent une fois, et s'il ne reste rien l'atelier répond « je ne sais pas » sans appeler le modèle ; option `abstain` : « je ne sais pas » sans second essai. **Aucune recherche web** : le CRAG de l'article étend la recherche au web quand les passages sont jugés faux ; la démo est hors ligne, la fiche et l'étape le disent.

## Boundaries & Constraints

**Always:**
- Les chiffres viennent de la session (AD-1). Coûts : `StageCost`, mêmes temps `build`, `update`, `query`, mêmes sommes. Préréglages existants inchangés (chaînes, disponibilités) ; ajouts seulement dans les listes partagées (`OPTIONS`, `SEARCHLESS_OPTIONS`, `PRESETS`, `PRESET_CONTEXT`, `PRESET_FAMILIES`, `COMPONENTS`, `STEPS`, `MEASURED`, `TARGETS`, `Literal` de `target`), aucune égalité exacte dans les tests quand une inclusion suffit (la story 14 en ajoute aussi).
- **Arbre livré** : module pur `rag/raptor.py`. Feuilles = passages du découpage `paragraphs` à la taille livrée (`doc_id#rang`, sha256). Vecteurs de mots tf × idf (normalisation et mots vides de la story 13) ; vecteur d'un nœud = somme de ses feuilles. Regroupement agglomératif à lien moyen sur le cosinus, déterministe (paire la plus proche d'abord, égalités par ordre, similarités arrondies à 9 chiffres), au plus `MAX_CLUSTER = 4` enfants, jamais sous `MIN_SIMILARITY = 0,08` ; un groupe d'un seul n'a pas de parent ; `MAX_LEVELS = 3`. Résumé par la règle (extractif) : pour chaque enfant, sa phrase la plus proche du vecteur du nœud (une phrase qui cite un code d'abord), les plus proches d'abord dans `SUMMARY_MAX_CHARS = 400`, puis dans l'ordre du corpus. Fichier livré sans durée, reproductible octet par octet (`tools/build_raptor.py`, test de non-péremption sur les trois langues).
- **Lecture** : la structure du fichier lu (reconstruit, sinon livré) est gardée ; un passage parti quitte son nœud (un nœud vide part), un passage nouveau rejoint le nœud de premier niveau le plus proche ; un résumé vient du fichier reconstruit, sinon du livré, à empreinte égale de ses enfants, sinon de la règle (périmé s'il venait du modèle). Documents actifs de la chaîne seulement, copie de travail comprise.
- **Requête RAPTOR** : BM25 de l'atelier sur tous les nœuds (passages : titre et texte ; résumés : leur texte), `TOP_NODES = 5` nœuds de score positif, sans appel de modèle ; chaque élément dit son niveau, ses documents et son audience ; la génération reçoit le contexte (fonction de prompt de la story 7). Sans modèle : le Contexte se calcule, la génération est sautée.
- **Reconstruire / Rétablir l'arbre** : `target: raptor` de `rag_lab_rebuild` ; structure recalculée par la règle sur la copie, puis un appel par nœud, de bas en haut (le résumé d'un nœud lit les textes de ses enfants : passages au niveau 1, résumés du niveau inférieur au-dessus) ; écriture atomique en fin dans `rag_lab_dir()/raptor/{lang}.yaml` (`author: rebuilt`, `method: llm`, durée, tokens, appels). Une erreur du modèle = échec sans écriture (`raptor.rebuild_model_error`), une annulation n'écrit rien, une réponse vide laisse le résumé de la règle (comptée), aucun résumé lisible = échec sans écriture. Même refus sans modèle (`rebuild_no_model`). `POST /api/rag_lab/raptor/reset`.
- **Effacement** : `raptor.forget` retire du fichier reconstruit les passages d'un document supprimé et vide les résumés qui les lisaient ; appelé à chaque copie gardée, quel que soit le préréglage, avant le contrôle d'annulation (comme `graph.forget`), et par la mise à jour.
- **Mise à jour (U)** : trois parties « Découpage » (passages du document touché), « Placement » (passages placés, retirés), « Résumés » (nœuds dont les enfants ont changé, sur le total) ; par la règle (millisecondes, 0 token), ou, arbre reconstruit et modèle chargé, un appel par nœud touché (écrit dans le fichier reconstruit).
- **Coûts (D5 de la story 13)** : `build` = construction mesurée de l'arbre (règle : durée, 0 token ; reconstruit : en-tête) ; arbre livré : estimation étiquetée hors des sommes (« un appel par résumé », tokens des enfants). CRAG : coûts de l'hybride ; `query` = filtre + au besoin la réécriture et la seconde recherche + génération ; un « je ne sais pas » ne coûte aucune génération.
- **Corrective RAG** : `fallback` dans le segment, après un `passage_filter` (refus `fallback_after_filter` sinon) ; il lit la liste gardée par le filtre ; filtre absent de l'exécution (sauté, en erreur douce) : étape sautée, la chaîne continue. Seconde recherche : les étapes du segment entre la première recherche et le filtre, dans l'ordre de la chaîne (le filtre lit la question d'origine). Réécriture sans modèle : pas de second essai, « je ne sais pas ».
- Exposition MCP inchangée (règle de la story 20) : `raptor` refusé par `searches_itself`, `crag` par `model_stage`. Aucun filtre `hr` dans l'atelier (audience affichée). `RagLabRunIntention` strict (aucun champ inconnu).
- Fiches de composant `context.raptor_search`, `fallback.retry`, `fallback.abstain` (fr, en, de, sources `https://`) ; fiches d'architecture `raptor` et `crag` sans `story`, avec leur source primaire ouverte et lue (RAPTOR : arXiv 2401.18059 ; CRAG : arXiv 2401.15884), ajoutées à `litterature.md`.

**Never:**
- Aucun arbre ni résumé écrit à la main et prétendu mesuré ; aucune estimation dans une somme.
- Pas de dépendance nouvelle, pas de `torch`, pas d'embedding pour RAPTOR (D2), pas de recherche web pour CRAG (D6), pas de réglage utilisateur des constantes.
- Pas d'écriture hors de `rag_lab_dir()/raptor/` ; pas de changement des autres préréglages, de `NATIVE_TOOLS`, du chat, de `rag/exposed.py`.

</frozen-after-approval>

## I/O & Edge-Case Matrix

| Scénario | Entrée / état | Comportement attendu |
|---|---|---|
| RAPTOR, question globale | `q_global_rh`, corpus livré | 5 nœuds, au moins un résumé parmi eux, sans appel de modèle avant la génération |
| RAPTOR sans modèle | aucun moteur | Contexte `ok`, génération `skipped` |
| Document ajouté | copie de travail | passages placés, résumés des nœuds touchés seulement |
| Document supprimé, arbre reconstruit | sentinelle retirée | `forget` : aucun texte du document dans `raptor/{lang}.yaml` |
| Reconstruire, nominal | faux moteur | un appel par nœud, fichier écrit en fin, mesure en en-tête |
| Reconstruire, modèle en erreur | `status: error` | échec sans écriture, état précédent gardé |
| Reconstruire, annulé | « Arrêter » | rien d'écrit |
| CRAG, passages gardés | filtre garde ≥ 1 | repli `ok`, « pas de repli » |
| CRAG, rien gardé, `retry` | filtre à 99 % | 1 appel de réécriture, seconde recherche et filtre, puis « je ne sais pas » si toujours rien |
| CRAG sans modèle | aucun moteur | pas de réécriture, « je ne sais pas » |
| `fallback` sans filtre | chaîne dense + repli | refus `fallback_after_filter` |

## Code Map

- `src/wavestack/rag/raptor.py` (nouveau), `tools/build_raptor.py` (nouveau), `content/rag_raptor.yaml` ×3 (nouveau).
- `src/wavestack/rag/lab.py` -- registres, `_context_raptor`, `_fallback`, abstention de la génération, `UpdateRun._update_raptor`, `RebuildRun._rebuild_raptor`, `raptor_for` / `raptor_key` / `raptor_mark` / `raptor_estimate`.
- `src/wavestack/session/app_session.py` -- cache de l'arbre, carte « Arbre RAPTOR », `reset_rag_lab_raptor`, `forget` à la copie gardée, libellé de reconstruction, note du repli sans modèle.
- `src/wavestack/web/app.py` (`target`, route de rétablissement), `src/wavestack/trace/catalog.py` (`RagLabRaptor`, `RagLabFallback`).
- `src/wavestack/rag/erasure.py`, `content/rag_erasure.yaml` ×3 -- `raptor` et `crag` disponibles ; `raptor_summaries` mesuré.
- `content/rag_sheets.yaml` ×3, `content/rag_lab.yaml` ×3, `content/messages.yaml` ×3, `content/ui.yaml` ×3, `litterature.md`.
- `src/wavestack/web/static/rag-raptor.js` (nouveau), `rag.html`, `rag.js` (ordre des préréglages dans une famille, D9) ; `tools/e2e/run_e2e.py`, `fake_local_server.py`, `README.md`.
- Tests : `tests/test_rag_raptor.py`, `tests/test_rag_lab_raptor.py`, `tests/test_rag_lab_crag.py` (nouveaux) ; réalignés : `test_rag_lab_graphrag.py`, `test_rag_sheets.py`, `test_rag_erasure.py`. E2E `rag_lab_raptor_crag`.

## Tasks & Acceptance

- [x] Arbre RAPTOR : module, outil, fichiers livrés, test de non-péremption.
- [x] Préréglage `raptor`, option `raptor_search`, requête sur tous les nœuds, carte et focus.
- [x] Reconstruire / Rétablir, mise à jour en trois parties, `forget`.
- [x] Type d'étape `fallback`, préréglage `crag`, abstention.
- [x] Effacement, fiches, textes fr, en, de ; tests ; E2E.

**Acceptance Criteria:**
1. Given le catalogue, then les préréglages existants gardent chaînes et disponibilités ; `raptor` : segment vide, Contexte `raptor_search`, famille `structure` ; `crag` : cosinus, BM25, RRF, filtre local, repli `retry`, famille `search` ; chaque préréglage dans une seule famille.
2. Given le corpus livré en fr, en, de, then `build_tree` est déterministe et identique au fichier livré de la langue (`author: shipped`, `method: heuristic`, sans durée) ; au moins 15 nœuds et 2 niveaux par langue, aucun nœud de plus de `MAX_CLUSTER` enfants (mesures exactes écrites dans le test).
3. Given une question préparée, then `raptor_search` rend au plus `TOP_NODES` nœuds de tous niveaux par BM25, sans appel de modèle ; sur `q_global_rh` (fr) un résumé est parmi eux.
4. Given « Reconstruire l'arbre » avec un faux moteur, then un appel par nœud, fichier écrit en fin avec sa mesure, arbre lu ensuite reconstruit, « Rétablir » rend le livré ; erreur du modèle ou annulation : rien d'écrit ; sans modèle : `rebuild_no_model`.
5. Given une mise à jour (Ajouter, Supprimer), then les trois parties et leurs nombres ; résumés refaits < total ; après Supprimer, `forget` ne laisse aucune chaîne du document dans le fichier reconstruit.
6. Given les coûts, then `build` RAPTOR mesuré (0 token livré, en-tête reconstruit), estimation étiquetée hors des sommes ; CRAG avec réécriture : `query` = filtre + réécriture + seconde recherche + génération ; « je ne sais pas » : 0 token de génération.
7. Given CRAG, then filtre qui garde ≥ 1 passage : pas de repli ; rien gardé : réécriture (1 appel), second essai, puis « je ne sais pas » si toujours rien ; `abstain` : « je ne sais pas » sans appel ; sans modèle : « je ne sais pas » ; `fallback` sans filtre avant lui : refusé (fr, en, de).
8. Given l'effacement, then `raptor` et `crag` disponibles sans `story` ; `raptor_summaries` mesuré : sentinelle active, au moins un résumé qui cite `ORN-7731-QZ`, « présent », puis « présent · à reconstruire », puis « effacé » après « Reconstruire : RAPTOR ».
9. Given les fiches, then `raptor` et `crag` sans `story`, avec leur source primaire (dans `litterature.md`) ; fiches de composant des trois options en fr, en, de ; tests de la story 19b verts.
10. Given l'exposition MCP, then `raptor` refusé par `searches_itself`, `crag` par `model_stage`, sans changer `rag/exposed.py`.

## Verification

- `uv run pytest -q --tb=short tests/test_rag_raptor.py tests/test_rag_lab_raptor.py tests/test_rag_lab_crag.py` puis `test_rag_lab test_rag_lab_decision test_rag_sheets test_rag_erasure test_rag_mcp test_i18n test_ui_texts test_rag_lab_graphrag`, par deux ou trois fichiers.
- `uv run python .claude/cost-kit/controle_rapide.py`.
- E2E : `rag_lab_raptor_crag`, puis `rag rag_rerank rag_lab`, par tranches.

## Décisions (pas de point de contrôle de spec : à revoir par Anaël)

1. **D1, arbre livré par une règle, modèle à « Reconstruire » seulement.** Comme 11 et 13 : un arbre écrit par un vrai modèle ne sort ni de la CI ni d'un run de nuit. La carte dit « calculé par une règle, sans modèle » et affiche l'estimation étiquetée. *À revoir par Anaël.*
2. **D2, mots au lieu d'embeddings pour le regroupement et la recherche.** L'article embarque les passages (SBERT), les regroupe par mélange de gaussiennes sur UMAP et cherche par cosinus. Ici : vecteurs tf × idf, regroupement agglomératif déterministe, BM25 sur tous les nœuds. Motif : un arbre livré reproductible octet par octet sur les trois OS de la CI, sans modèle d'embedding à télécharger ; l'atelier reste comparable (le même BM25 que l'hybride). `architectures.md` dit « Réutilise : Embedding » : écart assumé, à trancher. *À revoir par Anaël.*
3. **D3, résumé de la règle extractif, phrase à code d'abord.** Sans bonus, aucune phrase citant `ORN-7731-QZ` n'entrait dans un résumé (mesuré : 0 résumé en fr, en, de) et l'endroit d'effacement mesuré tombait ; la règle des codes de la story 13 (codes gardés dès une mention) est reprise. Mesure avec la sentinelle : 3 résumés (fr, en), 2 (de), du niveau 1 à la racine. *À revoir par Anaël.*
4. **D4, structure gardée à la lecture.** Un passage nouveau rejoint le nœud de premier niveau le plus proche au lieu d'un regroupement refait : sinon une mise à jour changerait tout l'arbre et « les résumés des branches touchées » de `architectures.md` ne se lirait pas dans les chiffres. « Reconstruire » refait le regroupement.
5. **D5, CRAG : déclencheur et repli.** Déclencheur : aucun passage gardé par le filtre (l'« incorrect » de l'article) ; l'« ambigu » (gardés mais faibles) n'est pas traité. Repli : une réécriture (consigne `rewrite` de la story 5) et un seul second essai. Le filtre juge la question d'origine. *À revoir par Anaël.*
6. **D6, aucune recherche web.** L'article étend la recherche au web pour les passages jugés faux ; l'atelier est hors ligne et son corpus fictif : le repli cherche de nouveau dans le même corpus, et la fiche, l'option et le focus le disent. Une option web demanderait un fournisseur, une clé et une règle de sortie : Reports.
7. **D7, `fallback` est un type d'étape à part.** Il se voit dans la séquence et le focus, se compose à la main après n'importe quel filtre, et garde le filtre de la story 8 inchangé ; un réglage du filtre aurait caché le repli.
8. **D8, abstention sans modèle.** « Je ne sais pas » est la réponse de l'atelier, pas du modèle : 0 token, la génération le dit, le contrôle d'ancrage est sauté (pas de réponse à ancrer).
9. **D9, ordre dans les familles.** `PRESETS` ne grandit qu'à sa fin (raptor, crag après llm_wiki de la story 14) ; l'ordre de vues.md (RAPTOR entre PageIndex et GraphRAG, CRAG en dernier de Recherche) vient de `PRESET_FAMILIES`, que le catalogue envoie désormais (`preset_families[].presets`) et que `rag.js` suit pour dessiner chaque famille. *À revoir par Anaël.*
10. **D10, mise à jour avec modèle.** Arbre reconstruit et modèle chargé : un appel par nœud touché, écrit dans le fichier reconstruit (mesure ajoutée à l'en-tête) ; une erreur arrête les appels, le reste garde la règle. `forget` est appelé à la copie gardée (session) et par la mise à jour.

## Spec Change Log

- 2026-10-25 : rédaction et développement (statut `review`), empilée sur la story 8 (76f6a095), puis fusion d'`integration/v1-2-atelier` (12.8 revue, 12.14 LLM Wiki) : ajouts de la story 12 après ceux de la 14 dans les listes partagées ; tests de listes passés en inclusion.
- Mesures de l'arbre livré (règle telle qu'écrite, figées dans `tests/test_rag_raptor.py`) : passages fr 73, en 65, de 78 ; résumés 27, 27, 37 sur 3 niveaux ; fichiers 23, 22 et 28 Ko ; construction ≈ 60 ms (≈ 300 ms au premier appel, imports compris). Sentinelle active : 3, 3, 2 résumés citent `ORN-7731-QZ`. `q_global_rh` (fr) : un résumé de niveau 2 parmi les 5 nœuds.
- Écarts de forme assumés : aucune nouvelle règle CSS (le module `rag-raptor.js` reprend les styles de la carte du graphe) ; captures E2E `93-atelier-rag-raptor.jpg`, `94-atelier-rag-crag.jpg` (89 et 90 étaient prises). Sources primaires RAPTOR (arXiv 2401.18059) et CRAG (arXiv 2401.15884) ouvertes sur arXiv (titres et résumés lus) et ajoutées à `litterature.md`.

## Reports

- Option de recherche web pour CRAG (D6), cas « ambigu » et raffinement « decompose-then-recompose » de l'article.
- Embeddings pour RAPTOR (D2) : regroupement et recherche par le modèle d'embedding de la chaîne.
- Mesure réelle d'un arbre reconstruit par un vrai modèle sur le PC cible et éventuel remplacement de l'arbre livré : done_checkpoint d'Anaël.
- Exposition MCP de RAPTOR et de CRAG : demanderait d'étendre la règle D12 de la story 20.
