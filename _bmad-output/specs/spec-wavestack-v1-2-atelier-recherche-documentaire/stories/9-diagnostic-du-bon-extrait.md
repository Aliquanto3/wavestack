---
title: 'Story 9 : diagnostic du bon extrait et « Où naît l''erreur »'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/evaluation.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/brownfield.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les questions préparées de la story 1 nomment le passage attendu, mais l'atelier ne dit pas où il se trouve dans la chaîne. Quand la réponse est mauvaise, le participant ne sait pas si le découpage l'a coupé, si la recherche l'a mal classé ou si le budget du contexte l'a écarté.

**Approach:** Pour une exécution terminée sur une question préparée, la session calcule le rang du passage attendu à chaque étape qui ordonne des passages (recherche vectorielle, BM25, fusion, reranking, contexte) et si le découpage l'a gardé entier. Elle désigne la première étape fautive et, le cas échéant, celle qui l'a rattrapé. Trois cas d'échec enregistrés, nés à trois étapes différentes, se rejouent en un clic depuis le même calcul, sans modèle. Cette story absorbe les CAP-2 à CAP-4 de la spec V2 (stories 2 à 4, en brouillon).

## Boundaries & Constraints

**Always:**
- Le calcul vit côté session (`rag/diagnosis.py`, AD-1) : la page envoie les listes de l'exécution terminée, reçoit rangs et verdict, et les dessine.
- Le passage attendu se repère par l'ancre de la question (story 1), dans le document attendu, espaces et casse repliés.
- Étape fautive : découpage si l'ancre n'est entière dans aucun chunk (`not_indexed`) ; recherche si le passage est absent de toutes les listes (`missing`) ou classé au-delà du budget du contexte (`ranked_low`) ; fusion ou reranking s'il est absent (`missing`) ou tombe de plus de N rangs (`fell`, N = 2, réglable par la requête) ; contexte s'il arrive au-delà du budget (`cut`). La première étape fautive gagne ; `rescued_by` nomme l'étape qui le ramène dans le budget.
- Un passage au milieu d'un contexte de trois extraits ou plus est noté (`middle`), jamais compté comme une faute.
- Une question par diagnostic, un passage attendu par verdict : aucune moyenne ni agrégat hors de l'onglet Évaluer.
- Les cas rejoués sont des références au corpus (document, n-ième passage attendu ou n-ième chunk sans passage attendu), relues avec le vrai découpage : un seul enregistrement sert les trois langues.
- Textes et cas dans `content/rag_diagnosis.yaml` et ses surcouches en, de ; aucune couleur hors des jetons.

**Never:**
- Pas d'appel au modèle, d'index ni de calcul de vecteurs pour rejouer un cas.
- Pas de diagnostic pour une question libre ni pour une question sans passage attendu (`no_answer`).
- Pas de diagnostic dans la vue harnais (Orchestration, Contexte LLM) : voir Reports.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Passage entier, en tête partout | Question préparée, exécution terminée | Rangs 1, aucune étape fautive | N/A |
| Ancre coupée par le découpage | Chunks de 200 caractères | Découpage fautif (`not_indexed`) | N/A |
| Mal classé puis repêché | Rang 6 en recherche, 1 au reranking | Recherche fautive (`ranked_low`), `rescued_by` reranking | N/A |
| Trouvé mais au-delà du budget | Rang 4 au reranking, budget 3 | Contexte fautif (`cut`) | N/A |
| Question libre | Texte saisi | « Question libre », pas de diagnostic | N/A |
| Question sans passage attendu | `no_answer` | « Rien à diagnostiquer » | N/A |
| Deux passages attendus | `multi_hop` | Un verdict par passage | N/A |
| Cas rejoué | Clic sur un des trois cas | Étape fautive désignée, mention « exécution enregistrée, aucun appel au modèle », aucun événement de l'atelier | Cas inconnu : 404 |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/diagnosis.py` -- règles, cas enregistrés, requête de la page.
- `src/wavestack/web/app.py` -- `GET /api/rag_lab/diagnosis`, `POST /api/rag_lab/diagnosis`, `GET /api/rag_lab/diagnosis/cases/{id}`.
- `src/wavestack/web/static/rag-diagnosis.js`, `rag.html` (section sous les vues de Construire), `rag.css`.
- `content/rag_diagnosis.yaml` et surcouches en, de.
- `tests/test_rag_diagnosis.py`, scénario E2E `rag_lab_diagnosis`.

## Tasks & Acceptance

- [x] Règles de rang et d'étape fautive, sans moyenne.
- [x] Trois cas enregistrés (`not_indexed`, `ranked_low`, `cut_by_budget`), en fr, en, de.
- [x] Points d'accès et section de la page, sans toucher `rag.js` ni `lab.py`.
- [x] CAP-2 à CAP-4 de la spec V2 marqués partiellement absorbés, restes listés, statut ouvert (décision de l'orchestrateur à la revue).
- [x] Tests ciblés et E2E `rag_lab_diagnosis`.

**Acceptance Criteria:**
- Given une exécution terminée sur une question préparée, then la section montre le rang du passage attendu à chaque étape et désigne l'étape fautive.
- Given les trois cas d'échec, then chacun s'ouvre en un clic, désigne une étape différente et n'émet aucun événement de l'atelier.

## Verification

- `uv run pytest -q --tb=short tests/test_rag_diagnosis.py tests/test_rag_lab_views.py tests/test_rag_questions.py tests/test_i18n.py tests/test_web_tokens.py tests/test_annex_language.py` -- vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag rag_rerank rag_lab rag_lab_views rag_lab_diagnosis` -- vert.

## Spec Change Log

- 2026-10-25 : décisions prises à la place d'Anaël, à revoir (voir Reports).

## Reports

- Décisions à revoir : seuils par défaut (budget = `top_k` du contexte, chute tolérée N = 2) ; le milieu du contexte est une note, pas une faute ; le cas « coupé par le budget » prend le sens « au-delà de `top_k` », le contexte de l'atelier ne tronquant pas le texte d'un extrait ; trois cas enregistrés à la main, sur des chunks réels du corpus, et non relevés avec les vrais modèles d'embedding et de reranking (à refaire au passage manuel d'Anaël si l'on veut des rangs mesurés) ; la présence entière de l'ancre est acquise dès qu'une liste de l'exécution contient le passage (un extrait listé est un chunk réellement indexé) ; sinon seulement, elle est recalculée avec le découpage livré à la taille du run, ce qui ne tient pas compte d'une copie de travail éditée.
- Non fait : le diagnostic dans la vue harnais (CAP-2 de la V2 : Orchestration, Contexte LLM, événement au catalogue, tokens du contexte) ; la synthèse A/B nommant la meilleure chaîne (CAP-3 : l'A/B est retiré, la comparaison est celle de l'onglet Comparer, qui ne montre pas encore le rang du passage attendu) ; le rattachement des prompts suggérés aux questions et le module de scénarios `scenarios.yaml` (CAP-4).
- Le diagnostic n'est pas relu dans `rag.js` (focus par étape) pour laisser la story 12.5 seule sur ce fichier.

## Revue

### Passe 1 (2026-10-25, SHA revu 027c807)

Base : origin/main fusionnée (#98, #100, #101, #102 = 1.3.0), sans conflit.

- Important, medium, second avis : découpage jugé sur le corpus livré, un passage retrouvé pouvait être déclaré `not_indexed`. Corrigé : un passage présent dans une liste de l'exécution est entier dans l'index ; repli sur le découpage livré sinon (test ajouté).
- Important, medium, second avis : sans étape de recherche, aucune faute. Corrigé à deux endroits : la page envoyait seulement les listes non vides (`runLists`), elle envoie maintenant toute étape classante terminée, même vide ; le serveur rend `context:missing` quand aucune étape classante n'est transmise (tests ajoutés).
- Important, medium, second avis : budget et taille de chunk lus dans la chaîne courante. Corrigé : lus dans `store.run.stages[].params` (`rag_lab_run_started`), la chaîne éditée seulement en repli.
- Important, medium, second avis : `top_k` borné à 10 contre 20 dans le lab (422). Corrigé : `le=20` pour la requête et les cas (test ajouté).
- Important, medium, second avis : CAP-2 à CAP-4 de la V2 fermés à tort. Corrigé selon la décision de l'orchestrateur : « partiellement absorbé », restes listés, statut `draft`.
- Nit, medium, second avis : JS testé seulement par chaînes du HTML, pas d'E2E en CI. Rejeté : la CI ne lance aucun E2E (hors périmètre) ; E2E `rag rag_rerank rag_lab_diagnosis` vert en local. Le scénario seul échoue (il suppose l'index de `rag`, comme documenté).
- Nit, low, second avis : `lexical_search` masquée quand vide. Corrigé avec le constat 2 (une liste vide est envoyée et dessinée « absent »).
- Nit, low, second avis : cas dupliqués par langue dans `rag_diagnosis.yaml`. Rejeté : les références sont des positions dans le corpus, identiques dans les trois fichiers, et `test_i18n` impose leur égalité ; seuls titres et explications sont traduits.
- Nit, low, second avis : `test_i18n` ne vérifiait pas les placeholders. Corrigé : mêmes placeholders par texte dans les trois langues.
- Nit, low, second avis : collisions probables avec 12.5 (`run_e2e.py` SCENARIOS, fin de `tools/e2e/README.md`, `rag.html`). Reporté à l'intégration : conflits textuels d'ajout, à résoudre en gardant les deux blocs.
- Complexité : 0 constat (listes bornées à 50 items et 12 étapes ; `resolve` parcourt le corpus par item, sur trois cas fixes).

