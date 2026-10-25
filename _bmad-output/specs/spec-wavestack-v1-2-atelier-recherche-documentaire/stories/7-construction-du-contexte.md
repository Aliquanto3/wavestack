---
title: 'Story 7 : construction du contexte (budget, ordre, compression, prompt final)'
type: 'feature'
created: '2026-10-25'
status: 'draft'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/architectures.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/vues.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'étape « Contexte » n'a qu'une option (`excerpts`) : elle garde les `top_k` premiers passages, dans l'ordre de pertinence, et colle leur texte. Le participant ne voit ni la taille du contexte en tokens, ni ce qui se passe quand le budget manque, ni l'effet de l'ordre (les modèles lisent mieux les extrémités d'un contexte long que son milieu), ni ce que coûte ou gagne une compression. Et le prompt final n'est visible que dans l'étape de génération.

**Approach:** L'étape « Contexte » (CAP-5) gagne trois options cumulatives : `budget` (le contexte tient dans un budget de tokens réglable ; les passages qui ne tiennent pas sont coupés ou écartés, et l'étape le dit), `edges` (budget, puis ordre « extrémités d'abord » : le meilleur passage en tête, le deuxième en fin, le troisième en deuxième position, etc.) et `compressed` (budget, ordre, puis compression par l'extra `compression` existant, Headroom : tokens avant et après). Le focus de l'étape montre le prompt final tel qu'il part au modèle (consigne, contexte construit, question), les tokens par partie, le budget et ce qui a été coupé. Les tokens sont ceux de l'estimation de la session (`deps.estimate_tokens`), dits « estimés ». La compression est empruntée au compresseur déjà chargé de la session ; absent, l'indisponibilité est dite avec sa raison et le contexte se construit sans compression. Chaque option a sa fiche composant (CAP-17) en fr, en et de.

## Boundaries & Constraints

**Always:**
- Les chiffres viennent de la session (AD-1) ; la page range, elle ne calcule rien.
- `excerpts` reste l'option livrée et son comportement ne change pas : mêmes éléments, même texte de contexte, mêmes faits, même clé de cache. `STEPS["context"]` est inchangé et vaut pour les quatre options (les lignes de séquence sont par type).
- Réglages : `top_k` (existant) fixe le nombre maximal de passages candidats ; `budget_tokens` (nouveau, dans `BOUNDS` et `PARAMS`, unité « tokens ») plafonne la taille du texte de contexte tout compris (consigne d'introduction et passages). L'ordre est porté par l'option, pas par un réglage (les réglages sont numériques).
- Budget : les passages, pris dans l'ordre de pertinence, entrent entiers tant que le total tient. Le premier qui déborde est coupé à la dernière fin de phrase qui tient (au besoin à la dernière limite de mot) et marqué « […] » ; les suivants sont écartés. Si même la consigne et le meilleur passage ne tiennent pas, le meilleur passage est coupé quand même (le contexte n'est jamais vide si la liste classée ne l'est pas). Le focus et les faits disent : passages entiers, coupé (de combien de tokens), écartés, tokens utilisés sur budget. Chaque élément porte un indicateur « coupé » ou « écarté ».
- Ordre `edges` : appliqué aux passages retenus par le budget, après lui. Le passage de pertinence 1 est placé en tête, celui de rang 2 en dernière position, celui de rang 3 en deuxième, celui de rang 4 en avant-dernière, etc. L'élément garde son rang de pertinence (`rank`) et gagne sa position dans le contexte (`placed`) ; `excerpt(position, ...)` numérote par position dans le contexte. Avec moins de trois passages, l'ordre est celui de la pertinence et l'étape le dit.
- Compression : `compressed` applique le compresseur de la session (port `Compressor`, `content/compression.yaml`) au texte des passages après budget et ordre, un passage à la fois (le seuil `compression_min_chars` de la session s'applique ; en dessous, le passage est « inchangé »), puis recompte les tokens. Le focus montre, par passage et au total, tokens avant et après, et les transformations. Un échec de compression d'un passage est doux (passage gardé tel quel, compté). La compression peut ne rien changer sur de la prose : le dire, c'est le résultat honnête, pas un défaut. Aucun chargement de Headroom n'est déclenché par l'atelier : il emprunte le compresseur déjà chargé de la session (carte « compression » active).
- Compresseur indisponible (extra absent, brique non voulue, non chargée, échec de chargement) : l'option `compressed` reste choisissable mais l'étape se construit comme `edges`, avec un avertissement portant la raison (celle de `_compression_unavailable`, dite en fr, en, de), et tokens avant = après. L'éditeur de chaîne affiche la raison près de l'option.
- Prompt final : le focus de l'étape Contexte (toutes options, `excerpts` compris) montre le prompt tel que la génération l'envoie : consigne système de l'atelier, contexte construit, question, avec les tokens estimés de chaque partie et leur total. Le texte vient de la même fonction que la génération (pas de seconde construction qui puisse diverger). Le focus de la génération ne change pas.
- Les passages renvoyés par `parent_child` sont des parents : budget, ordre et compression s'appliquent après la déduplication des parents. Un chunk contextualisé est montré sans son contexte d'indexation, comme aujourd'hui.
- Le diagnostic « Où naît l'erreur » (story 9) lit les éléments de l'étape Contexte par rang de pertinence ; un passage écarté par le budget compte comme « coupé » à l'étape Contexte (cause `cut`) ; un passage coupé mais présent n'est pas fautif.
- `SHEETED_KINDS` gagne `context` ; chaque option de `OPTIONS["context"]` a sa fiche dans `sheets` de `rag_lab.yaml` ×3 : cinq blocs, au moins une source, « ce qu'a mesuré le banc » vide. La fiche de l'ordre cite Liu et al., « Lost in the Middle » (2023) ; celle de la compression dit que Headroom est conçu pour des sorties structurées (JSON, journaux) et réduit peu la prose.
- Textes en fr, en et de ; aucune couleur hors des jetons ; ajouts en fin de section dans les fichiers carrefour (`rag_lab.yaml` ×3, `ui.yaml`, `run_e2e.py`, `lab.py`, `rag.js`). Piste « chaîne » : pas de fichier `rag-<onglet>.js`.

**Never:**
- Aucun modèle réel, aucun téléchargement, aucun chargement de Headroom la nuit : les tests utilisent un faux compresseur (le port `Compressor`) et le faux moteur existant. Le test du chemin réel de Headroom porte le marqueur de saut si l'extra est absent ; le chemin « indisponible » est testé partout.
- Pas de réglage d'ordre numérique ni de budget par passage ; pas de résumé par LLM, pas de réécriture du contenu des passages autre que la coupure et la compression.
- Pas de décision System One (story 8), pas de lien « Fiche » dans le focus ni de contenu de l'onglet Fiches (autre story), pas de changement de la génération elle-même.
- Pas de modification de la compression du chat (`app_session` : `rag_compressed`, cartes) : l'atelier lit le compresseur, ne le pilote pas.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Livré | `excerpts` | Identique à avant la story ; prompt final ajouté au focus | N/A |
| Budget suffisant | `budget`, tous les passages tiennent | Tous entiers, tokens utilisés/budget dits | N/A |
| Budget serré | `budget`, le 3e passage déborde | 3e coupé à une fin de phrase, « […] », 4e et suivants écartés, indicateurs et décompte | Avertissement dans l'étape |
| Budget minuscule | Budget < consigne + 1er passage | 1er passage coupé quand même, contexte non vide | Avertissement |
| Extrémités | `edges`, 5 passages | Positions 1, 3, 5, 4, 2 (rangs de pertinence) | N/A |
| Peu de passages | `edges`, 2 passages | Ordre de pertinence, dit | N/A |
| Compression | `compressed`, faux compresseur | Tokens avant/après par passage et total | Échec doux par passage |
| Compresseur absent | `compressed`, extra absent ou non chargé | Contexte comme `edges`, avertissement avec raison | Dit dans l'étape |
| Parent-enfant | `parent_child` + `edges` | Parents dédoublonnés puis budget et ordre | N/A |
| Diagnostic | Passage attendu écarté par le budget | Étape fautive « Contexte », cause « coupé » | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/lab.py` -- `OPTIONS["context"]` (`excerpts`, `budget`, `edges`, `compressed`), `PARAMS` (`budget_tokens` pour les trois nouvelles), `BOUNDS`, constantes (marque de coupe, ordre des extrémités), `SHEETED_KINDS`, `LabDeps.compressor` (rappel rendant un `Compressor` ou la raison de l'indisponibilité, comme `reranker`), `Item.placed` et son `payload`, `_context` et `_context_parents` (refactor : sélection, budget, ordre, compression, partagés), fonction du prompt final commune avec la génération (`_generation_context`, `generation.input`), charge utile du focus (prompt, tokens par partie, budget).
- `src/wavestack/rag/diagnosis.py` -- lecture des éléments du contexte : passage écarté = cause `cut` (vérifier que `placed` ne fausse pas le rang calculé).
- `src/wavestack/session/app_session.py` -- `_rag_lab_deps` : `compressor=` (le compresseur chargé de la session, ou la raison de `_compression_unavailable`) ; `_rag_lab_catalog` expose cette raison pour `compressed`. Pas de nouvelle intention.
- `src/wavestack/compression/` -- lecture seule (`Compressor`, `Compressed`).
- `src/wavestack/trace/catalog.py` -- champs du prompt final et des tokens sur la charge utile de fin d'étape (comme `chunks` en story 6), si absents.
- `src/wavestack/web/static/rag.js`, `rag.css`, `rag.html` -- focus de l'étape Contexte : jauge de budget, éléments avec indicateurs (coupé, écarté, position), tokens avant/après, prompt final.
- `content/rag_lab.yaml` ×3 (options, réglage `budget_tokens`, étapes, faits, messages, fiches), `content/messages.yaml` ×3 si message de session, `content/ui.yaml` (libellés du focus).
- `tests/test_rag_lab_context.py` (nouveau), `tests/test_rag_diagnosis.py` (cas du passage écarté), `tests/test_i18n.py`, scénario E2E `rag_lab_context` (`tools/e2e/run_e2e.py`, entrée dans la table des scénarios), `docs/guide.md`, `_bmad-output/implementation-artifacts/deferred-work.md` si report.

## Tasks & Acceptance

- [ ] Options `budget`, `edges`, `compressed`, réglage `budget_tokens`, bornes, défaut.
- [ ] Sélection par budget (coupe à la phrase, marque, écartés, décompte) ; ordre `edges` ; position `placed`.
- [ ] Compression par le port `Compressor` emprunté à la session ; indisponibilité dite ; échec doux.
- [ ] Prompt final et tokens par partie dans le focus, depuis la fonction de la génération.
- [ ] Diagnostic : passage écarté = cause `cut`.
- [ ] Fiches des quatre options en fr, en, de ; `SHEETED_KINDS`.
- [ ] Tests ciblés et scénario E2E `rag_lab_context`.

**Acceptance Criteria:**
1. Given `OPTIONS["context"]`, then elle vaut `("excerpts", "budget", "edges", "compressed")` et `excerpts` produit exactement les éléments, le texte de contexte et la ligne `STEPS` d'avant la story (non-régression sur un texte figé).
2. Given `budget` et un budget qui laisse tout passer, then tous les passages sont entiers, sans indicateur de coupe, et les tokens utilisés (estimés) ne dépassent pas le budget.
3. Given `budget` et un budget qui ne laisse passer que deux passages et demi, then le troisième est coupé à une fin de phrase et terminé par « […] », les suivants sont écartés, le total en tokens est ≤ budget, et les faits disent entiers, coupé et écartés avec leurs nombres.
4. Given un budget plus petit que la consigne et le premier passage, then le contexte contient le premier passage coupé et un avertissement.
5. Given `edges` et cinq passages de rangs de pertinence 1 à 5, then l'ordre dans le contexte est 1, 3, 5, 4, 2 ; `rank` reste le rang de pertinence, `placed` la position ; avec deux passages l'ordre est celui de la pertinence et l'étape le dit.
6. Given `edges` et un budget qui écarte les passages 4 et 5, then l'ordre est appliqué aux seuls passages 1 à 3 (1, 3, 2).
7. Given `compressed` et un faux compresseur qui raccourcit chaque passage, then chaque passage et le total portent tokens avant et après (après < avant), le texte de contexte est celui d'après, et le prompt final montre ce texte.
8. Given `compressed` et un compresseur qui échoue sur un passage, then ce passage est gardé tel quel, l'échec est compté dans l'étape et les autres passages sont compressés.
9. Given `compressed` sans compresseur chargé (extra absent, brique non voulue ou non chargée), then le contexte est celui de `edges`, l'étape porte un avertissement avec la raison, tokens avant = après, et l'éditeur de chaîne montre la raison près de l'option, en fr, en et de.
10. Given `compressed` et Headroom réellement installé et chargé, then le chemin réel s'exécute sur un passage (test marqué de saut si l'extra est absent) et le focus montre des tokens avant et après.
11. Given une option du contexte, then le focus de l'étape montre le prompt final (consigne, contexte, question) identique octet pour octet à celui que la génération envoie dans la même exécution, avec les tokens estimés par partie et leur total.
12. Given `parent_child` avec `edges`, then budget et ordre s'appliquent aux parents distincts, au plus `top_k`.
13. Given un passage attendu écarté par le budget, then le diagnostic désigne l'étape Contexte avec la cause `cut` ; un passage coupé mais présent n'est pas fautif.
14. Given une option du contexte, then sa fiche existe en fr, en et de avec une source ; celle de `edges` cite « Lost in the Middle » ; celle de `compressed` dit que Headroom réduit peu la prose.
15. Given le catalogue, then `budget_tokens` est réglable dans ses bornes pour les trois nouvelles options, absent d'`excerpts`, et une valeur hors bornes est refusée comme les autres réglages.

## Verification

- `uv run pytest -q --tb=short tests/test_rag_lab_context.py tests/test_rag_lab.py tests/test_rag_diagnosis.py tests/test_rag_lab_generation.py tests/test_rag_lab_chunking.py tests/test_rag_lab_views.py tests/test_compression.py tests/test_i18n.py` -- vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag rag_lab rag_lab_chunking rag_lab_context` -- vert. Le scénario `rag_lab_context` choisit `budget` avec un budget serré (indicateurs « coupé » et « écarté » dans le focus), `edges` (positions lues dans le focus), puis `compressed` avec le compresseur factice de la pile E2E (tokens avant et après), vérifie le prompt final, puis une chaîne sans compresseur (raison affichée).

## Points ouverts

1. Modélisation : trois options cumulatives (`budget`, `edges`, `compressed`) ou un réglage « ordre » ? Recommandation : options cumulatives, les réglages étant numériques et l'éditeur déjà fait pour des options ; le prix est qu'on ne combine pas `budget` + compression sans ordre (inutile pour CAP-5).
2. Budget par défaut et bornes. Recommandation : bornes 100 à 4 000 tokens, défaut 450 (trois extraits de 700 caractères tiennent à peine, la coupe se voit sans réglage), fenêtre de 4 096 du modèle de l'atelier en repère dans la fiche.
3. Unité du budget. Recommandation : tokens estimés par `deps.estimate_tokens` (même estimation que les coûts de la story 3), dits « estimés » ; pas de tokenizer du modèle actif (ni chargé, ni exact d'un modèle à l'autre).
4. Compresseur : emprunter celui de la session ou le charger dans l'atelier ? Recommandation : emprunter seulement (aucun chargement de Headroom ni téléchargement la nuit ; l'utilisateur active la carte « compression »), avec repli visible.
5. Utilité de la compression sur de la prose française. Recommandation : livrer tel quel et l'écrire dans la fiche ; un résultat « inchangé » est pédagogique. Mesure réelle sur le corpus en tâche humaine optionnelle.
6. Portée du prompt final : seulement le focus de l'étape Contexte, ou un affichage dédié ? Recommandation : le focus de l'étape (vues.md), avec les tokens par partie, produit par la fonction de la génération pour éviter toute divergence.
7. Diagnostic : passage écarté par le budget = cause `cut`. Recommandation : oui ; vérifier dans `diagnosis.py` que `placed` ne fausse pas le rang (le rang de pertinence reste la référence).
8. Passage coupé : coupe à la phrase avec « […] » ou coupe brute ? Recommandation : phrase d'abord, mot sinon, marque visible, pour que la perte soit lisible.

## Reports

- Tâche humaine optionnelle, non bloquante : activer l'extra `compression` sur le PC cible et mesurer les tokens avant/après de `compressed` sur le corpus Exemplia (repli enregistré : compresseur factice en test, indisponibilité dite sinon).
- Hors périmètre : routeur, filtre de passages, contrôle d'ancrage (story 8) ; lien « Fiche » du focus et contenu de l'onglet Fiches ; tokenizer du modèle actif pour le budget ; ordre ou budget par passage.
