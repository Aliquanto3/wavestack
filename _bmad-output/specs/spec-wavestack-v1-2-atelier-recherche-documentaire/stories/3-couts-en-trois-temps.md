---
title: 'Story 3 : coûts en trois temps et mesure de l''embedding, du reranking et de l''indexation'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/brownfield.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** FinOps et GreenOps ne comptent que la génération. L'embedding, le reranking et l'indexation de l'Atelier RAG n'ont aucun coût affiché (`docs/guide.md:750`), et rien ne sépare le coût de construire l'index, celui de mettre à jour un document et celui d'une requête. Les stories d'architecture suivantes (GraphRAG, décomposition, CAG) n'ont pas de base pour se comparer.

**Approach:** Chaque étage de l'atelier rend ses coûts (tokens, durée, dollars, énergie, gCO₂e) rangés par temps (`build`, `update`, `query`) dans `RagLabStageEndedPayload`, et chaque exécution en donne la somme par temps. Trois cartes sous la séquence les affichent. Trois boutons (Ajouter, Modifier, Supprimer un document) appliquent une opération à une copie de travail du corpus et mesurent la mise à jour de la chaîne. Un contenu précalculé montre le coût mesuré lors de sa construction, marqué comme tel.

## Boundaries & Constraints

**Always:**
- Les modèles d'embedding et de reranking et l'indexation sont locaux : 0 $, énergie par CodeCarbon (`LocalMeter`, extra `greenops`), tokens estimés par les caractères. Sans CodeCarbon, l'empreinte est « non mesurée », jamais inventée.
- Un contenu précalculé (index livré, vecteurs d'un cache de l'atelier) n'est pas recalculé : son coût est relu dans un fichier écrit à la construction (`rag_index.cost.json`, `build_costs.json`), marqué `measured_at_build`. Sans fichier, le coût est dit non enregistré.
- Ajouter, Modifier et Supprimer n'écrivent que dans la copie de travail, `config.rag_lab_dir()/work_corpus/{lang}.json` ; jamais `content/` du dépôt. « Revenir à l'état livré » supprime la copie.
- L'avertissement sur les deux périmètres de mesure (local : électricité seulement ; cloud : cycle de vie EcoLogits) reste affiché sous les cartes.
- La limite de `docs/guide.md:750` est retirée et remplacée par la description des trois temps.
- Textes en fr, en et de (`content/rag_lab.yaml`, `messages.yaml` et leurs surcouches).

**Never:**
- Pas de changement de `record_spend`, `_spend` ni `ConsumptionUpdatedPayload` (V1.3 story 4, bilan de la séance) : les coûts de l'atelier n'entrent pas dans le total de la séance.
- Pas de nouveau genre d'événement du journal : une mise à jour émet les événements d'une exécution, sous l'identifiant `upd{n}`.
- Les exécutions de la chaîne continuent de lire le corpus livré (la copie ne sert qu'à mesurer une mise à jour).
- Pas de nouvelle dépendance.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Exécution, index livré | Index sans fichier de coût | Construction : coût `measured_at_build`, sans chiffres, avec sa note | N/A |
| Exécution, index avec fichier de coût | `rag_index.cost.json` présent | Construction : tokens, durée, énergie relus, marqués | Fichier abîmé : traité comme absent |
| Exécution, vecteurs calculés puis relus | Chaîne à 300 caractères | 1re fois : coût mesuré ; 2e fois : même coût, `measured_at_build` | N/A |
| Requête | Embedding de la question, reranking, génération | Trois parties au temps `query`, 0 $ en local | Génération cloud sans tarif : dollars `None` + note |
| Somme avec une partie sans empreinte | Pas de CodeCarbon | `partial: true` (somme minorante) | N/A |
| Modifier | Texte ajouté au document | Seuls les passages nouveaux ou modifiés sont vectorisés ; index vectoriel et BM25 reconstruits | Texte vide : refus 409 |
| Supprimer | Document connu | 0 token d'embedding, index reconstruits | Document inconnu : refus 409 |
| Ajouter | Identifiant libre, titre, texte | Passages du document vectorisés | Identifiant pris ou invalide : refus 409 |
| Mise à jour en erreur | Une partie échoue | Parties suivantes `skipped`, copie inchangée | Erreur dite dans l'étape |
| Session occupée | État autre que `idle` | Refus 409 avec la raison | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/greenops.py` -- `StageCost` (un coût, son enregistrement), `summarize`, `Probe` (chronomètre et suivi CodeCarbon autour d'une partie).
- `src/wavestack/trace/catalog.py` -- `RagLabCost`, `RagLabCostSummary`, champs `costs` (étape) et `cost_summary` (fin d'exécution), tous facultatifs.
- `src/wavestack/rag/lab.py` -- coûts par étage ; `write_build_cost` / `recorded_cost` / `brick_costs_path` ; `UpdateRun` ; `last_update` ; `CostTexts`.
- `src/wavestack/rag/workcopy.py` -- copie de travail (ajout, ajout d'un paragraphe, suppression, découpage, remise à zéro).
- `src/wavestack/session/app_session.py` -- `_rag_lab_deps`, `update_rag_lab`, `reset_rag_lab_copy`, coûts de l'appel de génération, coût de « Construire l'index ».
- `src/wavestack/web/app.py` -- `POST /api/intentions/rag_lab_update`, `POST /api/rag_lab/copy/reset`.
- `src/wavestack/web/static/rag.{html,js,css}` -- trois cartes, boutons, formulaire.
- `scripts/build_rag_index.py` -- écrit le coût de la construction à côté de l'index.
- `content/rag_lab.yaml`, `content/messages.yaml` et surcouches -- textes.
- `docs/guide.md` -- les trois temps, la copie de travail.

## Tasks & Acceptance

**Execution:**
- [x] `greenops.py`, `catalog.py` -- fondation des coûts et des charges utiles.
- [x] `lab.py`, `workcopy.py` -- coûts de l'embedding (construction et question), de la base vectorielle, de l'index BM25, du reranking, de la génération ; `UpdateRun`.
- [x] `app_session.py`, `app.py`, `build_rag_index.py` -- intention de mise à jour, remise à zéro, enregistrement des coûts de construction.
- [x] `rag.{html,js,css}`, textes fr/en/de, `guide.md`, README E2E.
- [x] `tests/test_rag_lab_costs.py` et E2E `_rag_lab_costs` (scénario `rag_lab`).

**Acceptance Criteria:**
- Given une exécution, when elle se termine, then chaque étage a ses coûts par temps et `rag_lab_run_ended` porte la somme de la construction et de la requête.
- Given un index précalculé, when on lance la chaîne, then la carte Construction porte « mesuré à la construction ».
- Given un document modifié, ajouté ou supprimé, when on mesure, then la carte Mise à jour donne les cinq chiffres et `content/` du dépôt est intact.
- Given « Revenir à l'état livré », when on le clique, then la copie de travail n'existe plus.

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_rag_lab_costs.py tests/test_rag_lab.py tests/test_rag_lab_alt.py tests/test_rag_lab_generation.py tests/test_i18n.py` -- expected : vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected : vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag rag_rerank rag_lab` -- expected : vert (le scénario `rag_lab` suppose `rag` et `rag_rerank` avant lui).

## Implementation Notes

- Où vit la copie : `{données}/rag_lab/work_corpus/{lang}.json` (une par langue), listée par `GET /api/rag_lab` (`work_copy.path`).
- Modifier = ajouter le texte saisi comme dernier paragraphe (pas de remplacement du document).
- Mise à jour : les vecteurs inchangés sont ceux du corpus livré (cache, ou calculés d'abord et enregistrés comme coût de construction, hors coût de la mise à jour). Les index sont reconstruits en entier : aucun des stores de l'atelier ne s'étend vecteur par vecteur.
- Coûts de construction enregistrés : `{cache}/build_costs.json` (clés `embedding`, `vector_store:<option>`) et `rag_index*.cost.json` pour l'index de la brique (écrit par le script et par « Construire l'index »). Les index livrés dans `data/` n'ont pas encore de fichier de coût (reconstruction avec le vrai modèle non faite ici) : leur carte dit « non enregistré ».
- Interface avec la V1.3 story 4 : aucun appel à `record_spend` ; les coûts d'embedding, de reranking et d'indexation restent dans les cartes de l'atelier et n'entrent pas dans le bilan de la séance (la génération y entre déjà par `_call_model`).

## Spec Change Log

- 2026-10-25, revue (décision de l'orchestrateur, **à revoir par Anaël**) : le « Never » « Les exécutions de la chaîne continuent de lire le corpus livré » est levé. Tant que la copie de travail diffère du corpus livré, la chaîne la lit (`LabDeps.work_copy`), l'étape Chunking le dit (« la copie de travail du corpus ») et l'index précalculé de la brique n'est pas utilisé. Motif : CAP-8 demande de voir ce que coûte une mise à jour et son effet ; sans cela, un document ajouté n'était jamais retrouvé. Les vecteurs de la copie sont calculés à la première exécution (coût de construction de la copie, mesuré).
- 2026-10-25, revue : « Modifier un document » s'affiche « Modifier un document (ajouter un paragraphe) », fidèle à l'opération (ajout d'un dernier paragraphe, pas de remplacement).

## Reports

- Reconstruire les trois index livrés (`scripts/build_rag_index.py --lang …`) avec le vrai modèle pour qu'ils portent leur fichier `rag_index*.cost.json`.
- Intégrer les coûts d'embedding, de reranking et d'indexation dans le bilan de la séance (V1.3 story 4) si on le décide : demande un changement de `record_spend`.
- Mise à jour incrémentale réelle (sans reconstruction complète des index) : stories d'architecture.

## Revue

### Passe 1 (2026-10-25, SHA revu 6a1b3d3)

Base : origin/main 5c677fb, à jour (pas de rebase nécessaire).

- Important, medium, second avis 1 : « Construire l'index » démarrait le suivi CodeCarbon avant le contrôle du modèle refusé, sans l'arrêter. Corrigé : `Probe` démarrée une fois le modèle chargé ; test `test_a_refused_build_starts_no_tracker`.
- Important, medium, second avis 2 : tokens estimés (caractères ÷ 4, occurrences BM25) affichés « Tokens ». Corrigé : libellé « Tokens (estimés) » en fr, en et de.
- Important, medium, second avis 3 : `store.costs` gardait les chiffres de l'exécution précédente (exécution en erreur ou sans temps). Corrigé dans `rag.js` : remis à zéro au `rag_lab_run_started`, remplacé en entier à la fin.
- Important, medium, second avis 4 : génération annulée ou en erreur sans coût, somme non marquée partielle. Corrigé : le coût de l'appel est posé avant `LabCancelled`/`StageFailed` ; une exécution qui ne finit pas `ok` a des sommes `partial` ; assertion ajoutée à `test_stop_during_the_generation_keeps_the_partial_answer`.
- Important, medium, second avis 5 : les index livrés n'ont pas de `rag_index*.cost.json`, la carte Construction dit « mesuré à la construction » + « non enregistré ». Reporté (attente humaine) : le fichier ne se produit pas sans mesurer le vrai modèle (le fabriquer serait inventer un chiffre) et reconstruire modifie les index binaires suivis par git. Vérification : `uv run python scripts/build_rag_index.py --lang fr|en|de` avec le vrai modèle, commiter les trois `.cost.json`, puis la carte affiche les chiffres.
- Important, medium, second avis 6 (décision de l'orchestrateur, à revoir par Anaël) : après une mise à jour, la chaîne lisait toujours le corpus livré. Corrigé : `LabDeps.work_copy`, la chaîne lit la copie tant qu'elle diffère, Chunking dit sa source, l'index de la brique n'est pas utilisé ; test `test_after_an_update_the_chain_reads_the_work_copy_and_says_so` et vérification E2E. Voir le Spec Change Log.
- Nit, low, second avis 7 : libellé « Modifier » trompeur. Corrigé : « Modifier un document (ajouter un paragraphe) ».
- Nit, low, second avis 8 : copie lue hors verrou (mise à jour perdue possible). Corrigé : lecture et application sous le verrou, après le contrôle `idle`.
- Nit, low, second avis 9 : JSON abîmé lu comme copie vide sans signal. Corrigé : avertissement journalisé (« Copie de travail illisible »).
- Nit, low, second avis 10 : `write_build_cost(reset=True)` effaçait les coûts `vector_store:*` du même cache. Corrigé : `reset` retiré des appels (la clé du cache fixe le modèle et le corpus, les autres enregistrements restent valides).
- Nit, low, second avis 11 : `FakeMeter` remplaçait `session._local_meter`. Corrigé : double à la frontière (`OfflineEmissionsTracker` de CodeCarbon via `_load_codecarbon`), le vrai `LocalMeter` tourne.
- Pre-existing, low, second avis 12 : le scénario E2E `rag_lab` dépend de `rag` et `rag_rerank` (déjà documenté avant la story, `tools/e2e/README.md`). Rejeté pour cette story.
- Nit, low, second avis 13 : un document supprimé ne pouvait pas être réajouté. Corrigé : son identifiant redevient libre ; le refus E2E « existe déjà » utilise désormais `doc_atelier`.
- Nit, low, revue : les parties sans empreinte propre (recherche, fusion, contexte : durée seule) rendent toute somme `partial`, si bien que la mention s'affiche presque toujours. Reporté : décider si ces parties comptent dans `partial`.
- Nit, low, revue : `test_an_update_that_ends_in_error_leaves_the_copy_as_it_was` remplace `UpdateRun._update_embedding` (module interne). Reporté : le faire échouer par un faux modèle d'embedding.
- Complexité : 0 constat (sommes calculées une fois en fin d'exécution, `last_update` une fois par `GET /api/rag_lab`).
