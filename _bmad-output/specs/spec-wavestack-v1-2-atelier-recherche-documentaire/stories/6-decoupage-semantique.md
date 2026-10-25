---
title: 'Story 6 : découpage sémantique, parent-enfant et contextual retrieval'
type: 'feature'
created: '2026-10-25'
status: 'draft'
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

**Approach:** L'étape « Chunking » (CAP-4) gagne trois options : `semantic` (frontières là où la similarité entre phrases voisines chute, par l'embedding de la chaîne), `parent_child` (petits enfants indexés, le parent renvoyé au contexte) et `contextual` (un contexte court, précalculé, ajouté à chaque chunk avant l'embedding et la recherche lexicale). Le focus liste les chunks produits. Les contextes sont livrés précalculés sous `content/`, marqués comme tels avec la mesure de leur construction ; un bouton « reconstruire » les refait par le modèle actif. Le late chunking est reporté dans `deferred-work.md` (point ouvert 1). Chaque option a sa fiche composant (CAP-17) en fr, en et de.

## Boundaries & Constraints

**Always:**
- Les chiffres viennent de la session (AD-1) ; la page range, elle ne calcule rien.
- `paragraphs` reste l'option livrée et son comportement ne change pas (mêmes chunks, même clé de cache). Le texte indexé d'un chunk (contexte compris) et le texte montré au participant sont deux choses : la clé de cache des vecteurs inclut l'option de découpage et l'empreinte des contextes.
- `semantic` s'appuie sur l'embedding de la chaîne (`calls=("embedding_model",)`) ; sans embedding utilisable, repli sur `paragraphs` avec avertissement dit dans l'étape. `parent_child` : seuls les enfants sont embeddés et cherchés ; l'étape de contexte reçoit le parent de chaque enfant retenu, dédoublonné. `contextual` : un chunk sans contexte précalculé est indexé tel quel et compté dans l'étape.
- Contextes précalculés : fichier `content/rag_contexts.yaml` (+ surcouches en/de), une entrée par chunk (document, position, empreinte sha256 du texte du chunk), l'auteur (`shipped` ou `rebuilt`), le modèle, et la mesure de construction (nombre de chunks, tokens, durée). Le focus marque chaque contexte « précalculé » ou « reconstruit ». Une entrée dont l'empreinte ne correspond plus au chunk est ignorée et comptée.
- « Reconstruire » passe par le modèle actif de l'atelier (même voie que la génération : événements `model_*`, coût, empreinte), avec une consigne propre, sans raisonnement, au plus 128 tokens par contexte, annulable (« Arrêter »), et écrit dans le dossier de données (jamais dans `content/`). Échec ou sortie vide : le chunk garde son ancien contexte, l'étape continue (échec doux). Sans modèle : bouton grisé, raison dite.
- Chaque option de `OPTIONS["chunking"]` a sa fiche dans `sheets` de `rag_lab.yaml`, en fr, en et de : cinq blocs, au moins une source, « ce qu'a mesuré le banc » vide. `SHEETED_KINDS` gagne `chunking`.
- Textes en fr, en et de ; aucune couleur hors des jetons ; ajouts en fin de section dans les fichiers carrefour (`rag_lab.yaml` ×3, `ui.yaml`, `run_e2e.py`, `lab.py`, `rag.js`).

**Never:**
- Aucune étape de la nuit ne demande un modèle réel ni une reconstruction d'index à Anaël : les tests utilisent un faux moteur et un faux embedding ; les contextes livrés sont fournis (point ouvert 2).
- Pas de réglage numérique nouveau : taille des enfants, seuil de similarité, longueur des contextes sont des constantes de `lab.py`.
- Pas de late chunking dans cette story, pas de lien « Fiche » dans le focus ni de contenu de l'onglet Fiches (autre story).
- Pas de découpage autre que `paragraphs` dans l'étape de mise à jour (`workcopy`, scénario « corpus modifié ») ni sur l'index de la brique RAG : l'index livré n'est réutilisé que pour `paragraphs`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Sémantique | `semantic`, embedding disponible | Chunks coupés aux chutes de similarité, bornés par `chunk_max_chars` ; focus : liste des chunks | N/A |
| Sémantique sans embedding | `semantic`, pas d'embedding | Chunks `paragraphs`, avertissement | Dit dans l'étape |
| Parent-enfant | `parent_child` | Enfants (≈300 car.) indexés ; le focus montre chaque enfant et son parent ; le contexte reçoit des parents sans doublon | N/A |
| Contextual | `contextual`, contextes livrés | Chaque chunk montré avec son contexte « précalculé » ; texte indexé = contexte + chunk | N/A |
| Contexte périmé | Taille changée, empreinte différente | Chunk indexé sans contexte, compte des contextes ignorés dans l'étape | Avertissement |
| Reconstruire | Modèle actif, clic | Contextes « reconstruits », mesure mise à jour, cache des vecteurs invalidé | Échec doux par chunk ; annulable |
| Reconstruire sans modèle | Aucun modèle | Bouton grisé, raison dite | N/A |
| Index de la brique | Option autre que `paragraphs` | Corpus rechunké, pas de réutilisation de l'index livré | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/lab.py` -- `OPTIONS["chunking"]`, constantes (`CHILD_MAX_CHARS`, `SEMANTIC_PERCENTILE`, `CONTEXT_MAX_CHARS`), `SHEETED_KINDS`, `SEQUENCE` (appels du découpage), `LabRun._chunking`, `_Chain` (parents, contextes), clé de cache, étape de contexte (parents), `SheetText`.
- `src/wavestack/rag/corpus.py` -- `chunk_semantic`, `chunk_parent_child`, `split_sentences` ; `Chunk` garde ses quatre champs (parents et contextes dans des tables à part, par id de chunk).
- `src/wavestack/rag/contexts.py` (nouveau) -- lecture et validation de `rag_contexts.yaml`, empreintes, `rebuild` (appel du modèle actif, écriture dans le dossier de données).
- `src/wavestack/session/app_session.py`, `web/app.py` -- commande « reconstruire », progression, annulation ; `trace/catalog.py` -- `chunks` (liste bornée) sur `RagLabStageEndedPayload`.
- `src/wavestack/web/static/rag.js`, `rag.css`, `rag.html` -- liste des chunks dans le focus (parent, contexte marqué), bouton « reconstruire ».
- `content/rag_contexts.yaml` (+ `content/i18n/{en,de}/`), `tools/build_rag_contexts.py` (construction hors ligne), `content/rag_lab.yaml` ×3, `content/messages.yaml` (+ surcouches), `content/ui.yaml`.
- `tests/test_rag_lab_chunking.py`, `tests/test_rag_contexts.py`, scénario E2E `rag_lab_chunking` (`tools/e2e/run_e2e.py`), `docs/guide.md`, `deferred-work.md`.

## Tasks & Acceptance

- [ ] Fonctions de découpage `semantic` et `parent_child` (déterministes à embedding donné), options, constantes, repli.
- [ ] Contextes : fichier livré avec sa mesure, lecture validée, option `contextual`, empreintes, clé de cache.
- [ ] Reconstruction par le modèle actif (faux moteur en test), bouton, annulation, échec doux.
- [ ] Focus : liste des chunks, parent, contexte marqué.
- [ ] Fiches composant des options du découpage, en fr, en et de ; late chunking reporté.
- [ ] Tests ciblés et scénario E2E `rag_lab_chunking`.

**Acceptance Criteria:**
1. Given `OPTIONS["chunking"]`, then elle vaut `("paragraphs", "semantic", "parent_child", "contextual")` et `paragraphs` produit exactement les chunks et la clé de cache d'avant la story.
2. Given `semantic` et un faux embedding où deux sujets alternent, then la frontière tombe au changement de sujet et aucun chunk ne dépasse `chunk_max_chars`.
3. Given `semantic` sans embedding, then les chunks sont ceux de `paragraphs` et l'étape porte un avertissement.
4. Given `parent_child`, then le nombre d'enfants dépasse celui des parents, seuls les enfants sont embeddés et cherchés, et le contexte reçoit des parents sans doublon.
5. Given `contextual` et le fichier livré, then chaque chunk du corpus actif a un contexte « précalculé » dans le focus et le texte embeddé commence par ce contexte.
6. Given une empreinte qui ne correspond pas, then le chunk est indexé sans contexte et le compte des ignorés figure dans l'étape.
7. Given `rag_contexts.yaml` (fr, en, de), then chaque entrée désigne un chunk existant du corpus actif de sa langue, avec empreinte exacte, auteur, modèle et mesure renseignés (test de cohérence).
8. Given « reconstruire » et un faux moteur, then les contextes passent à « reconstruits », la mesure est mise à jour, le fichier livré dans `content/` est inchangé et le cache des vecteurs est refait.
9. Given « reconstruire » et un échec sur un chunk, then ce chunk garde son contexte et la reconstruction continue ; « Arrêter » l'interrompt entre deux chunks.
10. Given aucun modèle, then « reconstruire » est grisé avec sa raison.
11. Given une option du découpage, then le focus de l'étape liste ses chunks (nombre borné, total dit), chacun avec document et position.
12. Given une option du découpage, then sa fiche existe en fr, en et de avec une source ; le late chunking figure dans `deferred-work.md` avec sa raison.
13. Given l'index de la brique ou l'étape de mise à jour, then les options autres que `paragraphs` ne réutilisent ni l'index livré ni `workcopy`.

## Verification

- `uv run pytest -q --tb=short tests/test_rag_lab_chunking.py tests/test_rag_contexts.py tests/test_rag_lab.py tests/test_rag_lab_query.py tests/test_i18n.py tests/test_web_tokens.py tests/test_annex_language.py` -- vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag rag_lab rag_lab_views rag_lab_query rag_lab_chunking` -- vert. Le scénario `rag_lab_chunking` choisit `parent_child` puis `contextual`, lit les chunks du focus, vérifie le marquage « précalculé », et clique « reconstruire » avec le faux moteur.

## Spec Change Log

## Reports

- Tâche humaine possible, non bloquante : regénérer `content/rag_contexts.yaml` avec un vrai modèle (`tools/build_rag_contexts.py`, ou le bouton « reconstruire »). Repli enregistré : voir point ouvert 2.
- Hors périmètre : late chunking (point 1) ; mise à jour de corpus et index de brique pour les nouvelles options ; rang du passage attendu (CAP-10) ; lien « Fiche » du focus.

## Points ouverts

1. Late chunking : le faire ou le reporter ? Il exige un embedding à contexte long que les modèles fastembed de l'atelier ne donnent pas. Recommandation : reporter dans `deferred-work.md` (CAP-4 l'autorise), avec la raison et le modèle candidat.
2. Qui produit les contextes livrés sans modèle réel la nuit ? Recommandation : un constructeur déterministe (titre du document + première phrase du passage, auteur `shipped`, modèle `heuristic`) livre un fichier valide et testé la nuit ; la regénération par un vrai modèle est une tâche humaine optionnelle, le fichier restant un repli enregistré. La fiche et le focus disent « contexte heuristique » tant que ce n'est pas un LLM.
3. Contextes liés à la taille de chunk : empreinte par texte de chunk, donc valables seulement à la taille livrée. Recommandation : accepter ; hors taille livrée, contextes ignorés et comptés, « reconstruire » les refait.
4. `semantic` embedde les phrases avec l'embedding de la chaîne, puis l'étape Embedding embedde les chunks (un calcul de plus). Recommandation : accepter et l'afficher dans les faits de l'étape (phrases embeddées, durée) plutôt que le cacher.
5. `parent_child` : taille des enfants et définition du parent. Recommandation : parent = chunk `paragraphs` à `chunk_max_chars`, enfants = groupes de phrases jusqu'à 300 caractères, constantes de `lab.py`.
6. Où écrire les contextes reconstruits ? Recommandation : le dossier de données (à côté du cache des vecteurs), lu en priorité sur `content/`, avec un bouton « rétablir les contextes livrés ».
7. Combien de chunks le focus montre-t-il ? Recommandation : les 20 premiers, total dit, texte tronqué à 300 caractères, contexte sur sa propre ligne.
