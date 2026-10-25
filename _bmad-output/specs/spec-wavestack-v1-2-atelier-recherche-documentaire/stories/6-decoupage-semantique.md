---
title: 'Story 6 : découpage sémantique, parent-enfant et contextual retrieval'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/architectures.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/litterature.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'étape de découpage n'a qu'une option (`paragraphs`) et n'affiche que des chiffres (nombre, taille moyenne, plus long). Le participant ne voit pas les chunks, ni ce que changent un découpage par le sens, des enfants indexés avec leur parent renvoyé, ou un contexte ajouté à chaque chunk.

**Approach:** L'étape « Chunking » (CAP-4) gagne trois options : `semantic` (frontières là où la similarité entre phrases voisines chute, par l'embedding de la chaîne), `parent_child` (petits enfants indexés, le parent renvoyé au contexte) et `contextual` (un contexte court, précalculé, ajouté à chaque chunk avant l'embedding et la recherche lexicale). Le focus liste les chunks produits. Les contextes sont livrés précalculés sous `content/`, marqués comme tels avec la mesure et la méthode de leur construction ; un bouton « reconstruire » les refait par le modèle actif, comme le décrit le contextual retrieval (document entier + chunk → contexte). Le late chunking est reporté dans `_bmad-output/implementation-artifacts/deferred-work.md` (point ouvert 1). Chaque option a sa fiche composant (CAP-17) en fr, en et de.

## Boundaries & Constraints

**Always:**
- Les chiffres viennent de la session (AD-1) ; la page range, elle ne calcule rien.
- `paragraphs` reste l'option livrée et son comportement ne change pas : mêmes chunks, même clé de cache (`cache_key` appelée avec les mêmes arguments, rien d'ajouté), même ligne de séquence, même réutilisation de l'index de la brique. Le texte indexé d'un chunk (contexte compris) et le texte montré au participant sont deux choses : pour les autres options seulement, la clé de cache des vecteurs inclut l'option de découpage et, pour `contextual`, l'empreinte des contextes appliqués.
- `semantic` s'appuie sur l'embedding choisi par l'étape Embedding de la chaîne (`deps.embedder(option)`) ; sans embedding utilisable, repli sur `paragraphs` avec avertissement dit dans l'étape. La ligne `chunking` de `STEPS` ne change pas (les lignes de séquence sont par type, pas par option) : l'appel à l'embedding est dit dans les faits de l'étape. `parent_child` : seuls les enfants sont embeddés et cherchés ; l'étape de contexte reçoit le parent de chaque enfant retenu, dédoublonné. `contextual` : un chunk sans contexte valide est indexé tel quel et compté dans l'étape.
- Contextes précalculés : fichier `content/rag_contexts.yaml` (+ surcouches `content/i18n/{en,de}/`, résolues par `config.content_file`), une entrée par chunk (document, position, empreinte sha256 du texte du chunk, contexte), et en tête : l'auteur (`shipped` ou `rebuilt`), la méthode (`heuristic` ou `llm`), le modèle (`heuristic` pour la méthode heuristique), la taille de chunk et la mesure de construction (nombre de chunks, tokens écrits, durée). Le focus marque chaque contexte « précalculé » ou « reconstruit », et « heuristique, sans LLM » tant que la méthode est `heuristic`. Une entrée dont l'empreinte ne correspond plus au chunk est ignorée et comptée.
- « Reconstruire » passe par le modèle actif de l'atelier (même voie que la génération et la compréhension de la requête : `deps.generator(GenerationAsk)`, coût, empreinte, progression, « Arrêter »), avec une consigne propre (document entier en contexte, chunk en question), sans raisonnement, au plus 128 tokens par contexte, et écrit dans le dossier de données (jamais dans `content/`). Échec ou sortie vide : le chunk garde son ancien contexte, la reconstruction continue (échec doux). Sans modèle : bouton grisé, raison dite.
- Chaque option de `OPTIONS["chunking"]` a sa fiche dans `sheets` de `rag_lab.yaml`, en fr, en et de : cinq blocs, au moins une source, « ce qu'a mesuré le banc » vide. `SHEETED_KINDS` gagne `chunking`. La fiche de `contextual` dit que les contextes livrés sont heuristiques et que le contextual retrieval proprement dit demande un LLM (le bouton « reconstruire »).
- Textes en fr, en et de ; aucune couleur hors des jetons ; ajouts en fin de section dans les fichiers carrefour (`rag_lab.yaml` ×3, `ui.yaml`, `run_e2e.py`, `lab.py`, `rag.js`).

**Never:**
- Aucune étape de la nuit ne demande un modèle réel ni une reconstruction d'index à Anaël : les tests utilisent un faux moteur et un faux embedding ; les contextes livrés sont fournis par un constructeur déterministe (point ouvert 2).
- Pas de réglage numérique nouveau : taille des enfants, seuil de similarité, longueur des contextes sont des constantes de `lab.py`.
- Pas de late chunking dans cette story, pas de lien « Fiche » dans le focus ni de contenu de l'onglet Fiches (autre story).
- Pas de découpage autre que `paragraphs` dans l'étape de mise à jour (`rag_lab_update`, scénario « corpus modifié ») ni sur l'index de la brique RAG : l'index livré n'est réutilisé que pour `paragraphs`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Sémantique | `semantic`, embedding disponible | Chunks coupés aux chutes de similarité, bornés par `chunk_max_chars` ; focus : liste des chunks ; faits : phrases embeddées, durée | N/A |
| Sémantique sans embedding | `semantic`, pas d'embedding | Chunks `paragraphs`, avertissement | Dit dans l'étape |
| Parent-enfant | `parent_child` | Enfants (≤ 300 car.) indexés ; le focus montre chaque enfant et son parent ; le contexte reçoit `top_k` parents distincts | N/A |
| Contextual | `contextual`, contextes livrés | Chaque chunk montré avec son contexte « précalculé · heuristique » ; texte indexé = contexte + titre + chunk | N/A |
| Contexte périmé | Taille changée, copie de travail, empreinte différente | Chunk indexé sans contexte, compte des contextes ignorés dans l'étape | Avertissement |
| Reconstruire | Modèle actif, clic | Contextes « reconstruits » (méthode `llm`), mesure mise à jour, cache des vecteurs refait | Échec doux par chunk ; annulable |
| Reconstruire sans modèle | Aucun modèle | Bouton grisé, raison dite | N/A |
| Rétablir | Contextes reconstruits présents, clic « rétablir les contextes livrés » | Fichier du dossier de données supprimé, contextes livrés relus | N/A |
| Index de la brique | Option autre que `paragraphs` | Corpus rechunké, pas de réutilisation de l'index livré | N/A |
| Mise à jour | Chaîne dont le découpage n'est pas `paragraphs` | Mise à jour refusée, raison dite | `UpdateRefused` |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/lab.py` -- `OPTIONS["chunking"]`, `PARAMS` (les trois options gardent `chunk_max_chars`), constantes (`CHILD_MAX_CHARS`, `SEMANTIC_PERCENTILE`, `CONTEXT_MAX_TOKENS`, `FOCUS_CHUNKS_MAX`, `FOCUS_CHUNK_CHARS`), `SHEETED_KINDS`, `LabRun._chunking`, `_uses_brick_index` (ajoute : découpage `paragraphs`), `_Chain` (table des parents et des contextes par indice de chunk), `cache_key` (parties ajoutées hors `paragraphs` seulement), `_context` (parents), mise à jour (`_update_chunking` : refus hors `paragraphs`), `SheetText`. `STEPS` inchangé.
- `src/wavestack/rag/index.py` -- `passage_text` (ou une variante) : `contexte\ntitre\ntexte` quand un contexte s'applique ; c'est ce texte qu'embeddent l'étape Embedding et l'index BM25 (`_lexical_index`), et que compte l'estimation de tokens.
- `src/wavestack/rag/corpus.py` -- `chunk_semantic`, `chunk_parent_child`, `split_sentences` (sur `_SENTENCE_END`), et un lecteur des textes des documents actifs partagé avec `chunk_corpus` ; `Chunk` garde ses quatre champs (parents et contextes dans des tables à part, par indice de chunk).
- `src/wavestack/rag/contexts.py` (nouveau) -- modèle et validation de `rag_contexts.yaml`, empreintes, lecture (dossier de données d'abord, `content/` ensuite, entrée par entrée), constructeur heuristique (utilisé par `tools/build_rag_contexts.py`), écriture des contextes reconstruits sous `config.rag_lab_dir() / "contexts" / f"{lang}.yaml"`, remise aux livrés.
- `src/wavestack/session/app_session.py`, `src/wavestack/web/app.py` -- intention `POST /api/intentions/rag_lab_rebuild` (classe (b), acceptée en `idle` seulement, comme `rag_lab_update`), route `POST /api/rag_lab/contexts/reset` (comme `/api/rag_lab/copy/reset`) ; `trace/catalog.py` -- `chunks` (liste bornée) et `chunks_total` sur `RagLabStageEndedPayload`.
- `src/wavestack/web/static/rag.js`, `rag.css`, `rag.html` -- liste des chunks dans le focus (parent, contexte marqué), boutons « reconstruire » et « rétablir les contextes livrés » dans le focus de l'étape `contextual`.
- `content/rag_contexts.yaml` (+ `content/i18n/{en,de}/`), `tools/build_rag_contexts.py` (construction hors ligne, heuristique seulement : l'option `--model` est retirée, écart accepté à la revue, voir Reports), `content/rag_lab.yaml` ×3, `content/messages.yaml` (+ surcouches), `content/ui.yaml`.
- `tests/test_rag_lab_chunking.py`, `tests/test_rag_contexts.py`, scénario E2E `rag_lab_chunking` (`tools/e2e/run_e2e.py`), `docs/guide.md`, `_bmad-output/implementation-artifacts/deferred-work.md`.

## Tasks & Acceptance

- [x] Fonctions de découpage `semantic` et `parent_child` (déterministes à embedding donné), options, constantes, repli.
- [x] Contextes : constructeur heuristique, fichiers livrés (fr, en, de) avec leur mesure, lecture validée, option `contextual`, empreintes, clé de cache.
- [x] Reconstruction par le modèle actif (faux moteur en test), intention, bouton, annulation, échec doux, remise aux livrés.
- [x] Focus : liste des chunks, parent, contexte marqué.
- [x] Mise à jour refusée hors `paragraphs` ; index de la brique limité à `paragraphs`.
- [x] Fiches composant des options du découpage, en fr, en et de ; late chunking reporté.
- [x] Tests ciblés et scénario E2E `rag_lab_chunking`.

**Acceptance Criteria:**
1. Given `OPTIONS["chunking"]`, then elle vaut `("paragraphs", "semantic", "parent_child", "contextual")` et `paragraphs` produit exactement les chunks, la clé de cache (valeur figée dans le test, calculée avant la story) et les lignes `STEPS` d'avant la story.
2. Given `semantic` et un faux embedding où deux sujets alternent, then la frontière tombe au changement de sujet et aucun chunk ne dépasse `chunk_max_chars` ; les faits disent le nombre de phrases embeddées.
3. Given `semantic` sans embedding, then les chunks sont ceux de `paragraphs` et l'étape porte un avertissement.
4. Given `parent_child`, then le nombre d'enfants dépasse celui des parents, aucun enfant ne dépasse `CHILD_MAX_CHARS`, seuls les enfants sont embeddés et cherchés, et l'étape de contexte reçoit au plus `top_k` parents, sans doublon.
5. Given `contextual` et le fichier livré, then chaque chunk du corpus actif à la taille livrée a un contexte marqué « précalculé » et « heuristique » dans le focus, et le texte embeddé et indexé par BM25 commence par ce contexte ; le contexte n'est pas une simple copie du titre ni du début du chunk.
6. Given une empreinte qui ne correspond pas (taille changée ou copie de travail), then le chunk est indexé sans contexte et le compte des ignorés figure dans l'étape.
7. Given `rag_contexts.yaml` (fr, en, de), then chaque entrée désigne un chunk existant du corpus actif de sa langue à la taille déclarée, avec empreinte exacte, chaque chunk de ce corpus a une entrée, et l'en-tête renseigne auteur, méthode, modèle, taille et mesure (test de cohérence) ; relancer `tools/build_rag_contexts.py` sans modèle redonne le même fichier.
8. Given « reconstruire » et un faux moteur, then les contextes passent à « reconstruits » (méthode `llm`, modèle du faux moteur), la mesure est mise à jour, le fichier livré dans `content/` est inchangé (octets identiques) et la clé de cache des vecteurs change.
9. Given « reconstruire » et un échec sur un chunk, then ce chunk garde son contexte et la reconstruction continue ; « Arrêter » l'interrompt entre deux chunks, les contextes déjà refaits sont gardés.
10. Given aucun modèle, then « reconstruire » est grisé avec sa raison.
11. Given une option du découpage, then le focus de l'étape liste ses chunks (au plus `FOCUS_CHUNKS_MAX`, total dit), chacun avec document et position.
12. Given une option du découpage, then sa fiche existe en fr, en et de avec une source ; la fiche de `contextual` dit que les contextes livrés sont heuristiques ; le late chunking figure dans `deferred-work.md` avec sa raison et le modèle candidat.
13. Given l'index de la brique, then les options autres que `paragraphs` ne le réutilisent pas ; given une mise à jour de corpus sur une chaîne dont le découpage n'est pas `paragraphs`, then elle est refusée avec sa raison.
14. Given des contextes reconstruits et « rétablir les contextes livrés », then le fichier du dossier de données est supprimé et le focus remarque les contextes « précalculé ».

## Verification

- `uv run pytest -q --tb=short tests/test_rag_lab_chunking.py tests/test_rag_contexts.py tests/test_rag.py tests/test_rag_lab.py tests/test_rag_lab_query.py tests/test_rag_lab_costs.py tests/test_rag_lab_embeddings.py tests/test_rag_lab_views.py tests/test_rag_questions.py tests/test_i18n.py tests/test_web_tokens.py tests/test_annex_language.py` -- vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag rag_lab rag_lab_views rag_lab_query rag_lab_chunking` -- vert. Le scénario `rag_lab_chunking` choisit `parent_child` puis `contextual`, lit les chunks du focus, vérifie le marquage « précalculé » et « heuristique », clique « reconstruire » avec le faux modèle, vérifie « reconstruit », puis « rétablir les contextes livrés ».

## Décisions du point de contrôle

Prises le 2026-10-25 à la place d'Anaël, sous les contraintes du projet (SLM sur CPU, sans GPU ni droits admin, pédagogie d'abord, rien qui exige la nuit un modèle réel, un téléchargement ou une annotation).

1. **Late chunking : reporté.** Il faut un embedding à contexte long (8 k tokens et plus, sorties par token) que les modèles fastembed de l'atelier ne donnent pas, et son téléchargement ne peut se faire la nuit. Entrée dans `_bmad-output/implementation-artifacts/deferred-work.md` : raison, modèle candidat (jina-embeddings-v2-small-en, 8 192 tokens, à vérifier sur CPU), et la vérification à faire. CAP-4 l'autorise (« fait ou explicitement reporté »).
2. **Contextes livrés : constructeur déterministe, honnête sur sa nature.** Le titre étant déjà embeddé avec chaque chunk (`passage_text` = titre + texte), un contexte « titre + première phrase du passage » n'ajouterait rien. Le constructeur `heuristic` écrit donc ce que le chunk ne dit pas : « Extrait {position}/{total} de « {titre} ». Le document commence par : {première phrase du document}. » (première phrase du document, hors titre et commentaire ; pour l'extrait 1, la deuxième phrase). Méthode `heuristic`, modèle `heuristic`, auteur `shipped`. Le focus affiche « précalculé · heuristique, sans LLM », la fiche dit que le contextual retrieval proprement dit (Anthropic, 2024) fait écrire ce contexte par un LLM qui lit le document entier, ce que fait le bouton « reconstruire ». Tâche humaine optionnelle en Reports.
3. **Contextes liés à la taille livrée : accepté.** Empreinte sha256 du texte du chunk, appariement par (document, empreinte) et non par position. Hors taille livrée (700) ou sur une copie de travail, les contextes sans correspondance sont ignorés et comptés ; c'est aussi une leçon (un contexte précalculé périme quand le découpage change), et « reconstruire » les refait à la taille courante.
4. **`semantic` embedde les phrases : accepté et affiché.** Faits de l'étape : modèle, phrases embeddées, durée ; pas de mise en cache des vecteurs de phrases (corpus d'environ 37 ko, quelques secondes sur CPU). La ligne de séquence ne change pas (point corrigé, voir Spec Change Log).
5. **`parent_child` : parent = chunk `paragraphs` à `chunk_max_chars`, enfants = phrases groupées jusqu'à `CHILD_MAX_CHARS = 300`** (une phrase plus longue coupée à la limite). L'étape de contexte parcourt la liste classée et garde les `top_k` premiers parents distincts ; les faits disent combien d'enfants ont été lus. Le passage attendu d'une question (ancre de `rag_questions.yaml`) se cherche dans le parent.
6. **Contextes reconstruits : `rag_lab_dir()/contexts/{lang}.yaml`**, lus d'abord, entrée par entrée (un chunk sans entrée reconstruite valide prend le contexte livré). La reconstruction est une exécution de l'atelier à part (`rag_lab_rebuild`), qui réutilise progression, « Arrêter » et coûts (`StageCost` de phase `build`) ; elle écrit le fichier à la fin ou à l'arrêt (contextes faits gardés). Bouton « rétablir les contextes livrés » : supprime ce fichier. La durée attendue (environ 73 chunks en fr à la taille livrée, quelques secondes chacun sur CPU) est dite avant le clic ; le document entier (2,3 ko au plus) tient dans la fenêtre de 4 096 ; `too_long` reste un échec doux par chunk.
7. **Focus : `FOCUS_CHUNKS_MAX = 20` premiers chunks, total dit, texte tronqué à `FOCUS_CHUNK_CHARS = 300`**, contexte sur sa ligne avec son marquage, parent sous l'enfant (tronqué pareil). La liste bornée part dans `RagLabStageEndedPayload.chunks` ; le journal ne grossit donc pas avec le corpus.
8. **Hors points ouverts.** `Chunk` garde ses quatre champs (tables à part dans `_Chain`). Dans une exécution, les trois options lisent les mêmes documents que `paragraphs` (corpus livré ou copie de travail) ; seules la mise à jour (`rag_lab_update`, refusée) et l'index de la brique restent limités à `paragraphs`.

## Spec Change Log

- 2026-10-25 (point de contrôle de spec) : `calls=("embedding_model",)` sur la ligne de séquence du découpage retiré (les lignes `STEPS` sont par type ; il aurait changé la vue de `paragraphs`, contre le critère 1) ; clé de cache : parties ajoutées hors `paragraphs` seulement ; `SEQUENCE` (inexistant) remplacé par `STEPS` ; chemin réel de `deferred-work.md` ; `passage_text` (index.py) et `_uses_brick_index` ajoutés au Code Map ; constructeur heuristique repensé (le titre est déjà embeddé) et mention « heuristique, sans LLM » exigée au focus et dans la fiche ; méthode `heuristic|llm` dans l'en-tête du fichier ; intention `rag_lab_rebuild` et route de remise aux livrés nommées ; comportement de la mise à jour hors `paragraphs` (refus) et de la copie de travail fixé ; critères 1, 4, 5, 7, 8, 9, 12, 13 précisés, critère 14 ajouté ; liste des tests ciblés complétée (`test_rag.py`, `test_rag_lab_costs.py`, `test_rag_lab_embeddings.py`, `test_rag_lab_views.py`, `test_rag_questions.py`). Décisions prises à la place d'Anaël, à revoir (voir Reports).

## Reports

- Tâche humaine optionnelle, non bloquante : regénérer `content/rag_contexts.yaml` (et en, de) avec un vrai modèle local (bouton « reconstruire » puis copie du fichier du dossier de données `rag_lab_dir()/contexts/{lang}.yaml` vers `content/`, en remettant `author: shipped` ; `tools/build_rag_contexts.py` n'a pas d'option `--model`, écart à la spec accepté par l'orchestrateur à la revue : aucun moteur testable la nuit sans modèle, la voie du bouton couvre le besoin), relire quelques contextes, et vérifier que la méthode passe à `llm` dans l'en-tête et au focus. Repli enregistré : contextes heuristiques (décision 2).
- Vérification à faire sur le PC cible, modèle réel : durée d'une reconstruction complète (environ 73 chunks en fr) et qualité des contextes avec Qwen3.5 2B ; elle n'est pas mesurée la nuit.
- Décisions à revoir par Anaël : décisions 1 à 8 ci-dessus, en particulier la forme du contexte heuristique (2) et le refus de la mise à jour hors `paragraphs` (8).
- Sources des fiches (Anthropic « Introducing Contextual Retrieval » 2024 ; Kamradt « 5 levels of text splitting » ou LangChain SemanticChunker ; LangChain ParentDocumentRetriever ; Günther 2409.04701 pour le late chunking reporté) citées sans accès réseau, à ouvrir et vérifier (`litterature.md` demande une source primaire ouverte).
- Hors périmètre : late chunking (décision 1) ; mise à jour de corpus et index de brique pour les nouvelles options ; combinaison de `contextual` avec `semantic` ou `parent_child` ; rang du passage attendu (CAP-10) ; lien « Fiche » du focus.

## Points ouverts

Tranchés : voir « Décisions du point de contrôle ».

1. Late chunking : le faire ou le reporter ? Il exige un embedding à contexte long que les modèles fastembed de l'atelier ne donnent pas. Recommandation : reporter dans `deferred-work.md` (CAP-4 l'autorise), avec la raison et le modèle candidat.
2. Qui produit les contextes livrés sans modèle réel la nuit ? Recommandation : un constructeur déterministe (titre du document + première phrase du passage, auteur `shipped`, modèle `heuristic`) livre un fichier valide et testé la nuit ; la regénération par un vrai modèle est une tâche humaine optionnelle, le fichier restant un repli enregistré. La fiche et le focus disent « contexte heuristique » tant que ce n'est pas un LLM.
3. Contextes liés à la taille de chunk : empreinte par texte de chunk, donc valables seulement à la taille livrée. Recommandation : accepter ; hors taille livrée, contextes ignorés et comptés, « reconstruire » les refait.
4. `semantic` embedde les phrases avec l'embedding de la chaîne, puis l'étape Embedding embedde les chunks (un calcul de plus). Recommandation : accepter et l'afficher dans les faits de l'étape (phrases embeddées, durée) plutôt que le cacher.
5. `parent_child` : taille des enfants et définition du parent. Recommandation : parent = chunk `paragraphs` à `chunk_max_chars`, enfants = groupes de phrases jusqu'à 300 caractères, constantes de `lab.py`.
6. Où écrire les contextes reconstruits ? Recommandation : le dossier de données (à côté du cache des vecteurs), lu en priorité sur `content/`, avec un bouton « rétablir les contextes livrés ».
7. Combien de chunks le focus montre-t-il ? Recommandation : les 20 premiers, total dit, texte tronqué à 300 caractères, contexte sur sa propre ligne.

## Revue

### Passe 1 (2026-10-25, SHA revu f2b6040)

Base : origin/main fusionnée (#104), #105 (12.5) pas encore fusionnée. Conflit sur une capture E2E (01b) résolu côté main.

- Important, medium, second avis 1 : l'en-tête des contextes reconstruits ne décrivait que le dernier run alors que les entrées fusionnent les précédentes (coût et compte faux). Corrigé : `write_rebuilt` cumule tokens et durée, compte toutes les entrées, nomme chaque modèle (`a + b`) ; un fichier à une autre taille est remplacé entier. `rebuild_expected` lit le compte du fichier livré (taille livrée), plus celui du fichier reconstruit. Test `test_a_rebuilt_header_covers_every_entry_kept`.
- Important, medium, second avis 2 : `parent_child` peut rendre moins de `top_k` parents quand les meilleurs enfants partagent un parent, sans le dire. Corrigé : avertissement `context.parents_short` (fr, en, de) avec le conseil d'augmenter les candidats ; pas d'élargissement implicite de la recherche (la page montre ce que la recherche a rendu). Avec la chaîne livrée (8 candidats, `top_k` 3), le cas reste rare.
- Nit, low, second avis 3 : test parent-enfant renforcé (borne `top_k` lue de la chaîne, avertissement sinon) et test dédié au cas des parents partagés (20 candidats, `top_k` 20). Corrigé.
- Nit, low, second avis 4 : `tools/build_rag_contexts.py` sans `--model`. Spec mise en accord (Code Map, Reports), écart accepté par l'orchestrateur.
- Nit, low, second avis 5 : repli de `semantic` sur `paragraphs` gardait la clé de cache `semantic` (vecteurs en double). Corrigé : clé de `paragraphs`.
- Nit, low, second avis 6 : `gap >= threshold` coupe davantage sur distances égales au seuil. Rejeté : avec des vecteurs réels les égalités exactes sont exceptionnelles, et `gap > floor` évite déjà de tout couper quand toutes les distances sont égales.
- Complexité : 0 constat (liste du focus bornée à `FOCUS_CHUNKS_MAX`, fusion des entrées par dictionnaire).

