---
title: 'Story 7 : construction du contexte (budget, ordre, compression, prompt final)'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/architectures.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/vues.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/stories/9-diagnostic-du-bon-extrait.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'étape « Contexte » n'a qu'une option (`excerpts`) : elle garde les `top_k` premiers passages, dans l'ordre de pertinence, et colle leur texte. Le participant ne voit ni la taille du contexte en tokens, ni ce qui se passe quand le budget manque, ni l'effet de l'ordre (les modèles lisent mieux les extrémités d'un contexte long que son milieu), ni ce que coûte ou gagne une compression. Et le prompt final n'est visible que dans l'étape de génération.

**Approach:** L'étape « Contexte » (CAP-5) gagne trois options cumulatives, nommées comme dans `architectures.md` : `budget` (le contexte tient dans un budget de tokens réglable ; les passages qui ne tiennent pas sont coupés ou écartés, et l'étape le dit), `order` (budget, puis ordre « extrémités d'abord » : le meilleur passage en tête, le deuxième en fin, le troisième en deuxième position, etc.) et `compress` (budget, ordre, puis compression par l'extra `compression` existant, Headroom : tokens avant et après). Les libellés de la maquette (« Context budget », « Passage ordering », « Compression ») sont ceux des options sur la ligne « Contexte » de la séquence, comme pour le découpage de la story 6. Le focus de l'étape montre le prompt final tel qu'il part au modèle (consigne, contexte construit, question), les tokens par partie, le budget et ce qui a été coupé. Les tokens sont ceux de l'estimation de la session (`deps.estimate_tokens`), dits « estimés ». La compression est empruntée au compresseur déjà chargé de la session ; absent, l'indisponibilité est dite avec sa raison et le contexte se construit sans compression. Chaque option du contexte, `excerpts` comprise, a sa fiche composant (CAP-17) en fr, en et de.

## Boundaries & Constraints

**Always:**
- Les chiffres viennent de la session (AD-1) ; la page range, elle ne calcule rien.
- `excerpts` reste l'option livrée et son comportement ne change pas : mêmes éléments, même texte de contexte, mêmes faits. `STEPS["context"]` est inchangé et vaut pour les quatre options (les lignes de séquence sont par type). `cache_key` ne lit pas l'étape Contexte (phase run) et reste inchangée.
- Réglages : `top_k` (existant) fixe le nombre maximal de passages candidats, pour les quatre options ; `budget_tokens` (nouveau, dans `BOUNDS` à (100, 4000) et dans `PARAMS` des trois nouvelles options, unité « tokens (estimés) ») plafonne la taille du texte de contexte tout compris (introduction `content.intro_text`, séparateurs et extraits formatés). Son défaut, 450, vient d'une table `PARAM_DEFAULTS` lue par `param()` avant le repli `BOUNDS[name][0]` (sans elle, `param()` rendrait 100, la chaîne livrée n'ayant pas ce réglage) ; le catalogue (`params[].default`) le montre. L'ordre est porté par l'option, pas par un réglage (les réglages sont numériques).
- Budget : les passages, pris dans l'ordre de pertinence, entrent entiers tant que le total tient. Le premier qui déborde est coupé à la dernière fin de phrase qui tient (au besoin à la dernière limite de mot) et marqué « […] » ; les suivants sont écartés. Si même l'introduction et le meilleur passage ne tiennent pas, le meilleur passage est coupé quand même (le contexte n'est jamais vide si la liste classée ne l'est pas), avec un avertissement. Les tokens sont comptés par `deps.estimate_tokens` sur le texte de contexte final (après l'ordre), qui reste ≤ budget hors ce dernier cas. Le focus et les faits disent : passages entiers, coupé (de combien de tokens), écartés, tokens utilisés sur budget.
- Éléments : `items` de l'étape (et `chain.context`) ne contient que les passages présents dans le contexte (entiers et coupé), dans l'ordre de pertinence ; chacun porte `state` (`whole` ou `cut`), `placed` (sa position dans le contexte) et `tokens`. Les passages écartés vont dans une liste à part, `dropped`, de la charge utile de fin d'étape, montrée dans le focus avec l'indicateur « écarté ». Ainsi la vue Comparer (`rag-compare.js`), le diagnostic (`rag-diagnosis.js`) et le décompte « N extraits » de la génération lisent toujours les passages réellement envoyés, sans modification.
- Ordre `order` : appliqué aux passages retenus par le budget, après lui. Le passage de pertinence 1 est placé en tête, celui de rang 2 en dernière position, celui de rang 3 en deuxième, celui de rang 4 en avant-dernière, etc. L'élément garde son rang de pertinence (`rank`) et gagne sa position (`placed`) ; `content.excerpt(position, ...)` numérote par position dans le contexte. Avec moins de trois passages, l'ordre est celui de la pertinence et l'étape le dit (fait « ordre »).
- Compression : `compress` applique le compresseur de la session (port `Compressor`) au texte des extraits après budget et ordre, un extrait à la fois, jamais à l'introduction (comme `_transform_context` du chat). Le seuil `compression_min_chars` de la session s'applique (nouveau champ `LabDeps.compression_min_chars`, 300 par défaut) ; en dessous, l'extrait est « inchangé ». Les tokens sont recomptés après. Le focus montre, par extrait et au total, tokens avant et après, et les transformations (`Compressed.transforms`). Un échec de compression d'un extrait est doux (gardé tel quel, compté dans les faits et dans un avertissement). « Arrêter » est lu entre deux extraits. La compression peut ne rien changer sur de la prose : le dire, c'est le résultat honnête, pas un défaut. L'atelier n'émet aucun événement `compression_*` du chat et ne déclenche aucun chargement de Headroom : il emprunte le compresseur déjà chargé (carte « Compression » active), sans le fermer.
- Compresseur indisponible (extra absent, carte non active, chargement en cours, échec de chargement) : l'option `compress` reste choisissable mais l'étape se construit comme `order`, avec un avertissement portant la raison, et tokens avant = après. La raison est celle de `_compression_unavailable` ; comme elle vaut `None` quand la carte n'est pas voulue, un message nouveau `session.rag_lab.compress_not_wanted` (« activez la carte Compression ») la complète, en fr, en, de. L'éditeur de chaîne affiche la raison près de l'option par le `note_text` de son `OptionState` (`_rag_lab_catalog`), comme la génération sans modèle.
- Prompt final : le focus de l'étape Contexte (toutes options, `excerpts` compris) montre les parties du prompt dans l'ordre d'envoi : consigne système (si la génération l'enverrait : brique « Prompt système » active), contexte construit, question, avec les tokens estimés de chaque partie et leur total. Ces parties viennent d'une fonction unique de la session, extraite de `_rag_lab_generate` (les `messages` qu'elle construit aujourd'hui), appelée par la génération et par l'aperçu : pas de seconde construction qui puisse diverger. L'atelier la reçoit par `LabDeps.prompt_parts(context_text, question)` (défaut sans consigne système, pour les tests). Le prompt rendu par le gabarit du modèle (jetons spéciaux, compte exact) reste dans le focus de la génération, qui ne change pas : il demande un modèle chargé, l'aperçu non.
- Charge utile : `trace/catalog.py` gagne les champs de l'étape (`RagLabItem` : `placed`, `state`, `tokens`, `tokens_after`, `transforms`, `error_text` ; `RagLabStageEndedPayload` : `dropped`, `budget` (utilisés, budget), `prompt_parts`), tous optionnels avec défaut pour les autres étapes. C'est obligatoire : `_rag_lab_emit` valide la charge par `PAYLOAD_MODELS`, qui ignore en silence les champs inconnus.
- Les passages renvoyés par `parent_child` sont des parents : budget, ordre et compression s'appliquent après la déduplication des parents (`_context_parents` et `_context` partagent la même suite budget, ordre, compression). Un chunk contextualisé est montré sans son contexte d'indexation, comme aujourd'hui.
- Diagnostic (story 9, `rag/diagnosis.py`) : il lit les `items` de l'étape Contexte, donc les seuls passages présents. La règle `cut` est élargie : le passage présent dans la dernière liste classée et absent du contexte est `cut`, quel que soit son rang par rapport à `top_k` (aujourd'hui, seulement au-delà de `top_k`). Un passage écarté par le budget, ou dont l'ancre est tombée dans la partie coupée, est donc `cut` ; un passage coupé dont l'ancre reste dans le texte gardé n'est pas fautif. La note `middle` se lit sur la position dans le contexte : `LiveItem` gagne `placed` (optionnel), que `rag-diagnosis.js` envoie ; sans lui, la position dans la liste. Le cas enregistré `cut_by_budget` reste vrai.
- `SHEETED_KINDS` gagne `context` ; chaque option de `OPTIONS["context"]` a sa fiche dans `sheets` de `rag_lab.yaml` ×3 : cinq blocs, au moins une source, « ce qu'a mesuré le banc » vide. La fiche de l'ordre cite Liu et al., « Lost in the Middle » (2023, TACL 2024) ; celle de la compression dit que Headroom est conçu pour des sorties structurées (JSON, journaux) et réduit peu la prose ; celle du budget donne la fenêtre de 4 096 tokens par défaut du modèle de l'atelier comme repère.
- Textes en fr, en et de ; aucune couleur hors des jetons ; ajouts en fin de section dans les fichiers carrefour (`rag_lab.yaml` ×3, `messages.yaml` ×3, `ui.yaml`, `run_e2e.py`, `lab.py`, `rag.js`, `catalog.py`). Piste « chaîne » : pas de fichier `rag-<onglet>.js`.

**Never:**
- Aucun modèle réel, aucun téléchargement, aucun chargement de Headroom dans les tests unitaires : ils utilisent un faux compresseur (le port `Compressor`, comme `FakeCompressor` de `tests/test_compression.py`) et le faux moteur existant. Le test du chemin réel de Headroom saute si l'extra est absent (`pytest.importorskip`) ; le chemin « indisponible » est testé partout.
- Pas de réglage d'ordre numérique ni de budget par passage ; pas de résumé par LLM, pas de réécriture du contenu des passages autre que la coupure et la compression.
- Pas de décision System One (story 8), pas de lien « Fiche » dans le focus ni de contenu de l'onglet Fiches (autre story), pas de changement de la génération elle-même (l'extraction de la fonction des parties garde ses messages à l'identique).
- Pas de modification de la compression du chat (`app_session` : `_transform_context`, `rag_compressed`, cartes) : l'atelier lit le compresseur, ne le pilote pas.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Livré | `excerpts` | Identique à avant la story ; prompt final ajouté au focus | N/A |
| Budget suffisant | `budget`, tous les passages tiennent | Tous entiers, tokens utilisés/budget dits | N/A |
| Budget serré | `budget`, le 3e passage déborde | 3e coupé à une fin de phrase, « […] », 4e et suivants dans `dropped`, indicateurs et décompte | Avertissement dans l'étape |
| Budget minuscule | Budget < introduction + 1er passage | 1er passage coupé quand même, contexte non vide | Avertissement |
| Extrémités | `order`, 5 passages | Positions 1, 3, 5, 4, 2 (rangs de pertinence) | N/A |
| Peu de passages | `order`, 2 passages | Ordre de pertinence, dit | N/A |
| Compression | `compress`, faux compresseur | Tokens avant/après par extrait et total | Échec doux par extrait |
| Compresseur absent | `compress`, extra absent, carte inactive ou non chargée | Contexte comme `order`, avertissement avec raison, `note_text` de l'option | Dit dans l'étape |
| Parent-enfant | `parent_child` + `order` | Parents dédoublonnés puis budget et ordre | N/A |
| Diagnostic | Passage attendu écarté par le budget (rang ≤ `top_k`) | Étape fautive « Contexte », cause `cut` | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/lab.py` -- `OPTIONS["context"]` (`excerpts`, `budget`, `order`, `compress`), `PARAMS` (`top_k`, `budget_tokens` pour les trois nouvelles), `BOUNDS["budget_tokens"]`, `PARAM_DEFAULTS` lu par `param()` (:928), constantes (marque de coupe « […] »), `SHEETED_KINDS` (:119), `LabDeps.compressor` (rappel rendant le `Compressor` emprunté ou la raison de l'indisponibilité), `LabDeps.compression_min_chars`, `LabDeps.prompt_parts`, `Item.placed` / `state` / `tokens` et son `payload`, `_Result.dropped` / `budget` / `prompt_parts`, `_context` (:3061) et `_context_parents` (:3101) refactorés autour d'une suite partagée (sélection, budget, ordre, compression, aperçu du prompt).
- `src/wavestack/rag/diagnosis.py` -- règle `cut` élargie (:141-145), `LiveItem.placed` (:356) et note `middle` (:155) sur la position.
- `src/wavestack/session/app_session.py` -- extraction des parties du prompt de `_rag_lab_generate` (:10782) en une fonction appelée par la génération et par `LabDeps.prompt_parts` ; `_rag_lab_deps` (:10732) : `compressor=` (lit `self._compressor` sous le verrou, sinon la raison de `_compression_unavailable` ou `compress_not_wanted`), `compression_min_chars=self.cfg.compression_min_chars`, `prompt_parts=` ; `_rag_lab_catalog` : `note_text` de `compress`. Pas de nouvelle intention.
- `src/wavestack/compression/` -- lecture seule (`Compressor`, `Compressed`).
- `src/wavestack/trace/catalog.py` -- `RagLabItem` (:1486) et `RagLabStageEndedPayload` (:1548) : champs listés plus haut.
- `src/wavestack/web/static/rag.js`, `rag.css`, `rag.html` -- focus de l'étape Contexte : jauge de budget, éléments avec indicateurs (coupé, écarté, position), tokens avant/après, parties du prompt final. `rag-diagnosis.js` : envoie `placed`.
- `content/rag_lab.yaml` ×3 (options, réglage `budget_tokens`, faits, messages, fiches des quatre options), `content/messages.yaml` ×3 (`session.rag_lab.compress_not_wanted`), `content/ui.yaml` (libellés du focus si hors `rag_lab.yaml`).
- `tests/test_rag_lab_context.py` (nouveau), `tests/test_rag_diagnosis.py` (cas écarté, coupé, `placed`), `tests/test_rag_lab_generation.py` (messages inchangés après l'extraction), `tests/test_i18n.py`, scénario E2E `rag_lab_context` (`tools/e2e/run_e2e.py`, table des scénarios), `docs/guide.md`, `_bmad-output/implementation-artifacts/deferred-work.md` si report.

## Tasks & Acceptance

- [x] Options `budget`, `order`, `compress`, réglage `budget_tokens`, bornes, `PARAM_DEFAULTS`.
- [x] Sélection par budget (coupe à la phrase, marque, `dropped`, décompte) ; ordre `order` ; position `placed`.
- [x] Compression par le port `Compressor` emprunté à la session ; indisponibilité dite (`note_text`, avertissement) ; échec doux.
- [x] Fonction unique des parties du prompt (session), aperçu dans le focus du Contexte, tokens par partie.
- [x] Champs de charge utile dans `trace/catalog.py`.
- [x] Diagnostic : règle `cut` élargie, `placed` pour `middle`.
- [x] Fiches des quatre options en fr, en, de ; `SHEETED_KINDS`.
- [x] Tests ciblés et scénario E2E `rag_lab_context`.

**Acceptance Criteria:**
1. Given `OPTIONS["context"]`, then elle vaut `("excerpts", "budget", "order", "compress")` et `excerpts` produit exactement les éléments, le texte de contexte et les faits d'avant la story (non-régression sur un texte figé), `STEPS["context"]` inchangé.
2. Given `budget` et un budget qui laisse tout passer, then tous les passages sont `whole`, `dropped` est vide, et `deps.estimate_tokens(context_text)` ≤ budget.
3. Given `budget` et un budget qui ne laisse passer que deux passages et demi, then le troisième est `cut`, coupé à une fin de phrase et terminé par « […] », les suivants sont dans `dropped` et absents de `items`, `deps.estimate_tokens(context_text)` ≤ budget, et les faits disent entiers, coupé (tokens retirés) et écartés avec leurs nombres.
4. Given un budget plus petit que l'introduction et le premier passage, then le contexte contient le premier passage coupé et l'étape porte un avertissement.
5. Given `order` et cinq passages de rangs de pertinence 1 à 5, then l'ordre dans le texte de contexte est 1, 3, 5, 4, 2 ; `rank` reste le rang de pertinence, `placed` la position, `items` reste dans l'ordre de pertinence ; avec deux passages l'ordre est celui de la pertinence et l'étape le dit.
6. Given `order` et un budget qui écarte les passages 4 et 5, then l'ordre est appliqué aux seuls passages 1 à 3 (1, 3, 2).
7. Given `compress` et un faux compresseur qui raccourcit chaque extrait, then chaque extrait au-dessus de `compression_min_chars` et le total portent tokens avant et après (après < avant), l'introduction n'est pas compressée, un extrait sous le seuil est « inchangé », le texte de contexte est celui d'après, et les parties du prompt montrent ce texte.
8. Given `compress` et un compresseur qui lève sur un extrait, then cet extrait est gardé tel quel, l'échec est compté dans l'étape (fait et avertissement) et les autres extraits sont compressés.
9. Given `compress` sans compresseur (extra absent, carte non active, non chargée), then le contexte est identique à celui de `order`, l'étape porte un avertissement avec la raison, tokens avant = après, et le catalogue donne cette raison en `note_text` de l'option, en fr, en et de (message `compress_not_wanted` quand la carte n'est pas active).
10. Given `compress` et Headroom réellement installé, then l'adaptateur réel compresse un extrait du corpus et l'étape porte des tokens avant et après (test sauté si l'extra est absent ; aucune exigence que après < avant).
11. Given une option du contexte et une génération lancée avec un faux moteur, then les parties du prompt du focus du Contexte (consigne si envoyée, contexte, question) sont égales octet pour octet aux contenus des messages que la génération construit dans la même exécution (même fonction, testée par la session), avec les tokens estimés par partie et leur total ; sans modèle chargé (génération sautée ou `not_run`), l'aperçu est montré quand même.
12. Given `parent_child` avec `order`, then budget et ordre s'appliquent aux parents distincts, au plus `top_k`.
13. Given un passage attendu écarté par le budget alors que son rang est ≤ `top_k`, then le diagnostic désigne l'étape Contexte avec la cause `cut` ; idem si son ancre est dans la partie coupée ; un passage coupé dont l'ancre reste dans le texte n'est pas fautif ; avec `order`, la note `middle` suit `placed` ; les tests existants de `tests/test_rag_diagnosis.py` restent verts.
14. Given une option du contexte, then sa fiche existe en fr, en et de avec une source ; celle de `order` cite « Lost in the Middle » ; celle de `compress` dit que Headroom réduit peu la prose.
15. Given le catalogue, then `budget_tokens` est réglable dans (100, 4000), de défaut 450, pour les trois nouvelles options, absent d'`excerpts`, et une valeur hors bornes est refusée comme les autres réglages.
16. Given une exécution `compress` émise par `_rag_lab_emit`, then l'événement `rag_lab_stage_ended` du journal garde `placed`, `state`, `tokens`, `tokens_after`, `dropped`, `budget` et `prompt_parts` (pas de perte silencieuse par `PAYLOAD_MODELS`).

## Verification

- `uv run pytest -q --tb=short tests/test_rag_lab_context.py tests/test_rag_lab.py tests/test_rag_diagnosis.py tests/test_rag_lab_generation.py tests/test_rag_lab_chunking.py tests/test_rag_lab_query.py tests/test_rag_lab_costs.py tests/test_rag_lab_views.py tests/test_compression.py tests/test_i18n.py` -- vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag rag_lab rag_lab_chunking rag_lab_context`, puis la même avec `--no-headroom --only rag_lab_context` -- vert. Le scénario `rag_lab_context` choisit `budget` avec un budget serré (indicateurs « coupé » et « écarté » dans le focus), `order` (positions lues dans le focus), vérifie les parties du prompt final ; puis `compress` : sans l'extra (`--no-headroom` ou extra absent), la raison près de l'option et dans l'étape ; avec l'extra, la carte « Compression » activée comme dans `s_compression`, tokens avant et après dans le focus. La pile E2E n'a pas de compresseur factice : c'est le vrai Headroom, local et hors ligne, ou la branche « sans l'extra ».

## Décisions du point de contrôle

1. Modélisation : trois options cumulatives, ids alignés sur `architectures.md` (`budget`, `order`, `compress`) plutôt que `edges` / `compressed`. Les réglages restent numériques ; combiner budget et compression sans ordre n'est pas demandé par CAP-5.
2. Budget : bornes 100 à 4 000 tokens, défaut 450 par `PARAM_DEFAULTS`. Mesuré sur le corpus fr livré (73 chunks à 700 caractères) : extrait formaté médian 599 caractères (~150 tokens), introduction 200 (~50) ; trois extraits font ~505 tokens, le troisième se coupe donc au défaut, sans réglage.
3. Unité : tokens estimés par `deps.estimate_tokens` (la session y met `chars_per_token`), dits « estimés » ; pas de tokenizer du modèle actif.
4. Compresseur : emprunté seulement (lu sous le verrou, jamais chargé ni fermé par l'atelier) ; sinon repli `order` avec raison. Faux `Compressor` dans les tests unitaires ; test réel sauté sans l'extra ; E2E sur le vrai Headroom quand il est installé, branche « sans l'extra » sinon. Aucun téléchargement.
5. Prose : livrée telle quelle ; « inchangé » est un résultat, expliqué dans la fiche. Mesure réelle sur le corpus : tâche humaine optionnelle, non bloquante.
6. Prompt final : dans le focus de l'étape Contexte, sous forme de parties (consigne, contexte, question) avec tokens estimés, produites par la fonction de la session que la génération utilise. Le rendu du gabarit (jetons spéciaux) reste dans le focus de la génération : il exige un modèle chargé.
7. Diagnostic : oui, cause `cut`, avec la règle élargie (présent dans la dernière liste, absent du contexte). `placed` ne fausse pas le rang : `items` reste dans l'ordre de pertinence et le diagnostic n'en lit que la position pour `middle`, par `placed`.
8. Coupe : fin de phrase d'abord, limite de mot sinon, marque « […] » visible.

## Spec Change Log

- 2026-10-25, point de contrôle : ids `order` et `compress` (contradiction avec `architectures.md`) ; défaut du budget par `PARAM_DEFAULTS` (`param()` rendait 100) ; écartés dans `dropped`, hors `items` (Comparer, diagnostic et décompte de la génération lisaient sinon des passages non envoyés) ; règle `cut` du diagnostic élargie et `LiveItem.placed` (un passage écarté de rang ≤ `top_k` n'avait aucune cause) ; champs de `trace/catalog.py` obligatoires (perte silencieuse par `PAYLOAD_MODELS`) ; raison « carte non active » ajoutée (`_compression_unavailable` rend `None`) ; `compression_min_chars` passé à `LabDeps` ; affichage de la raison par `note_text` ; prompt final par une fonction extraite de `_rag_lab_generate` et `LabDeps.prompt_parts`, critère 11 rendu vérifiable sans modèle ; E2E sans compresseur factice (il n'existe pas), branche `--no-headroom` ; mention de la clé de cache précisée ; plan de tests complété (`test_rag_lab_query.py` pour les fiches, `test_rag_lab_costs.py`, critère 16).

## Reports

- Tâche humaine optionnelle, non bloquante : avec l'extra `compression` sur le PC cible, mesurer les tokens avant/après de `compress` sur le corpus Exemplia et reporter le constat dans la fiche (repli enregistré : faux compresseur en test, indisponibilité dite sinon).
- Hors périmètre : routeur, filtre de passages, contrôle d'ancrage (story 8) ; lien « Fiche » du focus et contenu de l'onglet Fiches ; tokenizer du modèle actif pour le budget ; ordre ou budget par passage.
