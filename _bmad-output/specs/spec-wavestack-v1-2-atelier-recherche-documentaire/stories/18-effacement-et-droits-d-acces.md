---
title: 'Story 18 : effacement de la sentinelle et droits d''accès (profils Tous et RH)'
type: 'feature'
created: '2026-10-25'
status: 'ready-for-dev'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/attaques-et-conformite.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/architectures.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/vues.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/brownfield.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'emplacement des cartes « Effacement » et « Droits d'accès » de l'onglet Attaquer affiche « à venir ». Le participant ne voit pas qu'effacer un document de la source ne l'efface pas de ses copies (chunks, index, contextes, résumés, graphe, wiki, cache), ni qu'un filtre de droits placé après la recherche laisse déjà passer un passage RH dans le pipeline, alors qu'un contrôle placé avant la recherche ne le peut pas.

**Approach:** Deux cartes, deux modules côté session (AD-1), sans modèle génératif ni d'embedding.
- **Effacement (CAP-14)** : la sentinelle `projet_talvane` (code `TLV-7731-QZ`, inactive dans `rag.yaml`) est activée **dans l'état de la requête** (comme le document piégé de la story 17, jamais dans `content/`, l'index ou la copie de travail). Le participant « construit » les copies de démonstration, supprime la sentinelle, puis lit un tableau par endroit et par architecture (les endroits et leurs architectures sont ceux de `attaques-et-conformite.md`) : chaque copie est « présent », « effacé », « à reconstruire », « à recharger », « absent » ou « aucune copie ». Une question sur le code, posée après l'effacement, montre quelles copies le contiennent encore (sans génération : on affiche le texte qui le contient).
- **Ce qui est mesuré, ce qui est illustratif.** Seuls dense, hybride et reranking existent dans l'atelier (`lab.PRESETS`) ; les huit autres architectures arrivent avec les stories 10 (contexte long, CAG), 11 (agentique, PageIndex), 12 (RAPTOR, CRAG), 13 (GraphRAG) et 14 (LLM Wiki). Un endroit est **mesuré** quand son contenu peut être reconstruit ici sans modèle : texte des chunks, index BM25 (`lab.lexical_index`), contextes du découpage contextuel (`contexts.heuristic_entries`, story 6), fichier de contextes livré, source relue. Les endroits produits par un modèle (résumés, arbre, graphe, wiki, cache de prompt) sont des **cas construits** (`provenance: constructed`), marqués « illustratif » à l'écran. Les vecteurs ne sont pas calculés (pas de modèle d'embedding) : la ligne « Chunks et vecteurs » mesure le texte des chunks et dit que le vecteur part avec son chunk (vérification sur un index réel en Reports).
- **Droits (CAP-15)** : profils « Tous » et « RH », modes « filtrage après la recherche » et « contrôle avant la recherche », sur `q_global_rh`. Le calcul est déterministe : BM25 sur le corpus en mémoire, puis filtre (après) ou index restreint au profil (avant). La carte montre ce que le pipeline a lu **avant** le filtre : c'est la fuite.

## Boundaries & Constraints

**Always:**
- Calcul côté session, modules neufs `rag/erasure.py` et `rag/access.py` ; la page envoie son état, reçoit, dessine (AD-1). Aucun appel de modèle, aucun réseau, aucune clé. Imports permis : `config`, `rag.corpus`, `rag.index.passage_text`, de `rag.lab` seulement `bm25`, `bm25_terms`, `lexical_index`, de `rag.contexts` seulement `heuristic_entries` et `load_book` (lecture), de `rag.attack` seulement `Provenance` et `provenance_text`. `rag/attack.py`, `rag/lab.py`, `rag/contexts.py` et `rag.js` ne sont pas modifiés ; le corpus avec sentinelle est une fonction propre à `rag/erasure.py` (même méthode que `attack.memory_corpus` : copie de `RagContent` où seul `projet_talvane` passe `active: True`).
- Sentinelle et état : `rag.yaml` garde `active: false` pour `projet_talvane` ; l'activation est un champ de requête (`sentinel_active`), recalculée à chaque requête, rien n'est retenu par la session ni après un rechargement. Corpus = documents actifs **livrés** (pas la copie de travail de Construire) plus la sentinelle, découpés à `chunk_max_chars: 700` (valeur de `rag_attack.yaml` et `rag_contexts.yaml`, déclarée dans `rag_erasure.yaml`). **Aucun fichier du corpus livré, aucun index, aucune copie de travail, aucun fichier de contextes n'est créé ou modifié** ; la sentinelle livrée suffit (code présent dans les deux chunks de la sentinelle et dans aucun autre document, fr, en, de, mesuré au point de contrôle).
- Requête de l'effacement : `sentinel_active` (bool), `step` ∈ `idle`, `start`, `erase`, `rebuild`, `rebuilt` (liste d'ids d'architecture, non vide seulement à `rebuild`). Les copies ne se construisent que si `sentinel_active` ; `erase` ou `rebuild` sans sentinelle active rend le message de garde « rien à effacer, construisez d'abord les copies » (200) et aucun statut. `start` : instantanés en mémoire construits depuis le corpus avec sentinelle. `erase` : la sentinelle quitte la source ; les endroits `delete` sont filtrés par `doc_id`. `rebuild` (implique `erase`) : les endroits des architectures de `rebuilt` sont reconstruits depuis la source sans la sentinelle.
- Règle d'état d'un endroit (déclarée en données, `erase_mode`) : `delete` (chunks et vecteurs, index BM25) devient « effacé » après `erase` ; `rebuild` (contextes du découpage contextuel, résumés, arbre, graphe, wiki) reste « présent · à reconstruire » tant qu'il contient le code, « effacé » après `rebuild` ; `reload` (cache de prompt ou KV : CAG, préfixe en cache du contexte long) reste « présent · à recharger », « effacé » après `rebuild` ; `none` (source relue à chaque requête : agentique, contexte long) est « aucune copie », et la recherche du code dans la source échoue dès `erase`. Le fichier de contextes livré (`rag_contexts.yaml`) est mesuré tel quel : « absent » (construit sans la sentinelle), jamais modifié. Le statut est **toujours calculé** par la recherche du code dans le contenu courant de l'endroit (mesuré ou construit) : correspondance exacte de `TLV-7731-QZ` dans le texte, et pour l'index BM25 présence des trois termes `bm25_terms(code)` (`orn`, `7731`, `qz`) dans les comptes d'un même document de l'index.
- Un endroit partagé par plusieurs architectures (le fichier de contextes est un seul fichier par langue) passe « effacé » dès qu'une de ses architectures est dans `rebuilt`, et le tableau le dit (« copie partagée »).
- Droits : profils `all` et `hr` ; `all` ne voit que `audience: all`, `hr` voit tout ; audience d'un passage = celle de son document dans `RagContent`. Corpus = documents actifs livrés, sans sentinelle ni piège, `chunk_max_chars: 700`, `k: 3`. Mode `after` : top-k BM25 sur tout le corpus, puis retrait des passages interdits ; la carte donne l'ensemble lu avant le filtre (`seen_before_filter`), le rendu, les passages RH lus (`leaked`), et le nombre rendu inférieur à k (« le nombre de résultats trahit l'existence du document »). Mode `before` : BM25 sur l'index des seuls documents autorisés (l'idf aussi est calculé sans eux) ; `seen_before_filter` = rendu, `leaked` vide, k atteint. Profil `hr` : les passages RH sont autorisés, jamais comptés comme fuite. L'étape de réécriture de requête qui « a lu » le passage en mode `after` est un texte construit (`provenance: constructed`), non un appel ; il cite le titre d'un document de `leaked` mesuré dans chaque langue (`entretiens_annuels`, rang 2 en fr, en et de), vérifié par test.
- Données dans `content/rag_erasure.yaml` et `content/rag_access.yaml` (surcouches `content/i18n/{en,de}/`, mêmes clés, structure et verdicts communs aux trois langues, textes traduits) : textes, architectures (11), endroits (`erase_mode`, `measured` ou `provenance`, architectures concernées), contenu construit des endroits non implémentés (`text` qui cite le code, `rebuilt_text` qui ne le cite pas), story qui le remplacera, ce que coûte la remise en conformité en mots (colonne « Mise à jour (U) » de `architectures.md`, aucun chiffre inventé), question et k, notes (GraphRAG : un résumé de communauté peut mêler des profils). Un endroit `constructed` s'affiche « illustratif · cas construit pour la démonstration (à enregistrer avec …, story N) ». Une architecture absente de l'atelier dont un endroit est mesuré (CRAG sur l'index de l'hybride, agentique et contexte long sur la source) le dit : « architecture à venir (story N), endroit mesuré sur … ».
- Onglet Attaquer : nouveaux fichiers `rag-attack-erasure.js` et `rag-attack-access.js`, chacun enregistré par `registerTab` sous sa propre clé (`attack_erasure`, `attack_access`, absentes de `TAB_IDS`) avec un seul crochet `mount` (GET des textes et de l'état par défaut, aucun calcul) : `registerTab("attack", …)` n'est jamais rappelé (il remplacerait les crochets de la story 17), et aucun crochet `render` (appelé à chaque événement de l'atelier). Balises `<script type="module">` ajoutées dans `rag.html`. Dans `rag-attack.js`, **une seule ligne retirée** : l'écriture de `story18_text` dans `rag-atk-soon` (l'élément et sa section `rag-atk-soon-box` disparaissent) ; la clé `story18_text` est retirée des trois `rag_attack.yaml` (plus aucun lecteur). `.rag-soon` du panneau reste présent, masqué. Les textes d'une page se dessinent par `textContent`, jamais `innerHTML`.
- Ajouts seuls dans `app.py` (bloc `# V1.2 story 18`), `app_session.py` (fin de section RAG), `rag.html`, `rag.css`, `run_e2e.py`, README E2E, et `OTHER_TABS` de `tests/test_rag_evaluation.py` ; `ui.yaml` et `messages.yaml` seulement si un texte hors des deux fichiers de données est nécessaire (×3). Aucune couleur hors des jetons ; textes fr, en, de ; état jamais porté par la couleur seule.
- Charge inoffensive : le code `TLV-7731-QZ` est fictif (texte livré). Aucune donnée réelle ; les passages RH sont ceux du corpus fictif.

**Never:**
- Pas de modification du corpus livré (`content/corpus/**`, `content/i18n/**/corpus/**`), de `rag.yaml`, de `rag_contexts.yaml`, de l'index, de la copie de travail ou de `rag_questions.yaml` ; pas d'activation persistante de la sentinelle.
- Pas d'appel de modèle (génératif, embedding, reranking), pas de téléchargement, pas de réseau ; pas de GraphRAG, RAPTOR, PageIndex, wiki, CAG ni contexte long construits ici ; aucun chiffre de coût ou de durée inventé.
- Pas de filtre de droits appliqué au chat ni à l'atelier (Construire, Comparer, Évaluer) : la démonstration vit dans la carte seulement.
- Pas de score global ni de moyenne dans l'onglet (SPEC.md) ; pas de nouvel événement des exécutions de l'atelier ni de ligne au Journal de sécurité.
- Pas de dépendance nouvelle.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Onglet ouvert, rien d'activé | `sentinel_active` faux, `idle` | Carte Effacement : sentinelle « inactive », bouton « Construire les copies » ; corpus livré inchangé | N/A |
| Copies construites | `start`, sentinelle active | Endroits mesurés et construits « présent » (chunks : 2 passages avec le code ; contextes : 1 entrée sur 2) ; contextes livrés « absent » ; agentique et contexte long, source « aucune copie » (code trouvé dans la source) | N/A |
| Après suppression | `erase` | Chunks et BM25 « effacé » ; contextes, résumés, arbre, graphe, wiki « présent · à reconstruire » ; caches « présent · à recharger » ; source : code introuvable ; la question sur le code remonte le texte de chaque endroit encore présent | N/A |
| Reconstruction | `rebuild` + `rebuilt: [graphrag]` | Les endroits de GraphRAG passent « effacé » ; les autres restent ; ce que coûte la remise en conformité, en mots | Id inconnu : 422 |
| Suppression sans copies | `erase` ou `rebuild`, sentinelle inactive | Message de garde « rien à effacer, construisez d'abord les copies » ; aucun statut | 200 avec message |
| `rebuilt` hors `rebuild` | `start` ou `erase` avec `rebuilt` non vide | Refus | 422 |
| Sentinelle désactivée | case décochée | Retour à `idle` ; corpus en mémoire sans la sentinelle | N/A |
| Droits, Tous, après | profil `all`, mode `after` | `seen_before_filter` contient un passage RH (fr, en : 2 sur 3 ; de : 1 sur 3), `leaked` non vide, rendu < k, note « fuite » | N/A |
| Droits, Tous, avant | profil `all`, mode `before` | `leaked` vide, `seen_before_filter` = rendu, aucun passage RH, k atteint | N/A |
| Droits, RH | profil `hr`, deux modes | passages RH rendus, aucune fuite comptée | N/A |
| Question absente de la langue | `question_id` inconnu dans la langue | données refusées au chargement (erreur claire) | Refus au chargement |
| Corps invalide | champ inconnu, valeur hors liste | 422 | N/A |
| Aucune requête hors poste | install par défaut | Cartes jouées intégralement sans modèle, index ni clé | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/erasure.py` (nouveau) : chargement et validation de `rag_erasure.yaml` (pydantic `extra="forbid"`, `Provenance` de `attack.py`) ; corpus en mémoire avec la sentinelle ; instantanés par endroit (texte des chunks, `lexical_index`, `heuristic_entries` avec la phrase `rag_lab.contexts.heuristic` de la langue, `load_book(lang).shipped` (le fichier livré seul, jamais la reconstruction du dossier de données), source, contenus construits) ; recherche du code ; automate `idle`, `start`, `erase`, `rebuild` ; tableau ; texte remonté par la question sur le code.
- `src/wavestack/rag/access.py` (nouveau) : chargement et validation de `rag_access.yaml` ; corpus en mémoire, `audience` par passage ; top-k BM25 sur tout le corpus ou sur l'index restreint ; filtre ; `seen_before_filter`, `leaked`, `returned`, nombre rendu contre k ; texte construit de la réécriture.
- `src/wavestack/session/app_session.py` (fin de section RAG) : `rag_lab_erasure_texts`, `rag_lab_erasure(request)`, `rag_lab_access_texts`, `rag_lab_access(request)` ; pures, acceptées dans tout état, sans entrée au Journal de sécurité.
- `src/wavestack/web/app.py` (ajouts, `# V1.2 story 18`) : `GET` et `POST /api/rag_lab/erasure`, `GET` et `POST /api/rag_lab/access` ; corps fermés (422 sur champ inconnu ou valeur hors liste).
- `src/wavestack/web/static/rag-attack-erasure.js`, `rag-attack-access.js` (nouveaux, `registerTab("attack_erasure" | "attack_access", { mount })`), `rag-attack.js` (une ligne retirée), `rag.html` (deux cartes à la place de `rag-atk-soon-box`, scripts), `rag.css`.
- `content/rag_erasure.yaml`, `content/rag_access.yaml` et leurs surcouches `content/i18n/{en,de}/` ; `story18_text` retiré des trois `rag_attack.yaml`.
- `tests/test_rag_erasure.py`, `tests/test_rag_access.py` (nouveaux) ; `tests/test_rag_evaluation.py` (`OTHER_TABS` : deux noms ajoutés) ; `tools/e2e/run_e2e.py` (scénario `rag_lab_rights`, ajout seul, sans prérequis d'index) ; `tools/e2e/README.md`.

## Tasks & Acceptance

- [ ] Reprendre les valeurs mesurées au point de contrôle (section « Mesures ») dans les tests, en les recontrôlant ; toute différence est un défaut de la story, pas une valeur à réécrire.
- [ ] `rag/erasure.py` et données `rag_erasure.yaml` ×3 (architectures, endroits, contenus construits, provenance).
- [ ] `rag/access.py` et données `rag_access.yaml` ×3.
- [ ] Session, points d'accès GET/POST, corps fermés.
- [ ] Cartes Effacement et Droits (JS, HTML, CSS), une ligne retirée de `rag-attack.js`, `story18_text` retiré ×3.
- [ ] Scénario E2E `rag_lab_rights` ; tests ciblés ; `OTHER_TABS` complété ; réalignement de ce qui lit `rag-atk-soon` ou `story18_text` (`git grep` : seuls `rag-attack.js` et `rag.html` au point de contrôle).

**Acceptance Criteria:**
1. Given l'onglet Attaquer ouvert sans action, then la sentinelle est inactive, `rag.yaml` garde `active: false` pour `projet_talvane`, et `chunk_corpus(load_rag_content(lang), …)` ainsi que `index.corpus_digest` sont identiques avant et après un `GET` et un `POST` des deux cartes.
2. Given l'activation puis l'effacement puis la reconstruction (POST successifs), then les octets de `content/rag.yaml`, de `content/rag_contexts.yaml` et de ses surcouches, de `content/corpus/**`, de `content/i18n/**/corpus/**` et du dossier de données isolé de `tests/conftest.py` (index, copie de travail, contextes reconstruits) ne changent pas, et `workcopy.load(lang)` rend la même copie.
3. Given `start`, then le texte des chunks (dense, hybride, reranking, CRAG, feuilles de RAPTOR) contient le code dans 2 passages, l'index BM25 (hybride, CRAG) dans 2 documents, les contextes heuristiques dans 1 entrée, le fichier de contextes livré dans aucune (« absent »), la source le contient ; statuts calculés, nombre d'occurrences affiché, dans les trois langues.
4. Given `erase`, then chunks et index BM25 ne contiennent plus le code (statut « effacé » calculé), la source non plus, et le fichier de contextes livré reste « absent ».
5. Given `erase`, then les contextes heuristiques (mesurés) et les résumés, arbre, graphe, wiki (construits) gardent le code et s'affichent « présent · à reconstruire », les caches du CAG et du contexte long « présent · à recharger », l'agentique et le contexte long « aucune copie » pour la source ; la question sur le code remonte, pour chaque endroit encore présent, le texte qui le contient (aucune génération).
6. Given `rebuild` pour une architecture, then seuls ses endroits (et les copies partagées qu'elle porte, signalées) passent « effacé » (recherche du code vide dans le contenu reconstruit : `heuristic_entries` sur la source sans sentinelle) ; un endroit construit (`rebuilt_text`) ne prend jamais le statut mesuré « effacé » mais « effacé (illustratif, non mesuré) » (`erased_illustrative`), distinct à l'écran et expliqué, fr, en, de (décision de l'orchestrateur à la revue, 2026-10-25) ; `rebuild` avec une liste vide répond 422 ; les autres architectures gardent leur statut ; un id inconnu répond 422 ; `erase` ou `rebuild` sans sentinelle active renvoie le message de garde sans statut ; `rebuilt` non vide hors `rebuild` répond 422.
7. Given les endroits construits (résumés de RAPTOR, arbre de PageIndex, communautés et entités de GraphRAG, pages du LLM Wiki, caches du CAG et du contexte long), then chacun porte `provenance: constructed` (ou `recorded` avec date et modèle, refusé au chargement sans eux), sa story de remplacement (10 à 14, selon `stories.yaml`), un `text` qui contient le code et un `rebuilt_text` qui ne le contient pas (validé au chargement) ; l'écran les présente « illustratif · cas construit » ; aucun n'est présenté comme mesuré ou enregistré ; aucun chiffre de coût n'est affiché pour une remise en conformité.
8. Given le profil « Tous » et le mode « après la recherche » sur `q_global_rh` (k = 3), then `leaked` contient les passages RH mesurés (fr et en : `entretiens_annuels` rang 2 et `grille_remunerations` rang 3 ; de : `entretiens_annuels` rang 2), présents dans `seen_before_filter`, absents du rendu, et le nombre rendu (fr, en : 1 ; de : 2) est inférieur à k ; la note de fuite et la réécriture construite, qui cite le titre d'un document de `leaked`, sont affichées. Vérifié par pytest et par E2E (SPEC.md, CAP-15).
9. Given le profil « Tous » et le mode « avant la recherche », then `leaked` est vide, aucun passage RH n'est dans `seen_before_filter` ni dans le rendu, le nombre rendu vaut k, et le code ne fait appel à aucun modèle : `rag/access.py` et `rag/erasure.py` n'importent que les noms permis (test AST), les fabriques de la session (`_engine_factory`, `_embedder_factory`, `_reranker_factory`) sont remplacées par des fonctions qui lèvent, la garde réseau de `conftest.py` reste active.
10. Given le profil « RH », then les passages RH sont rendus dans les deux modes et `leaked` est vide (autorisation, pas fuite).
11. Given les trois langues, then `rag_erasure.yaml` et `rag_access.yaml` fr, en, de ont les mêmes architectures, endroits, `erase_mode`, provenances, stories, ids et placeholders ; seuls les textes diffèrent ; chaque `doc_id` et `question_id` cités existe dans `rag.yaml` et `rag_questions.yaml` de la langue ; le code de la sentinelle est présent dans le `text` de chaque endroit construit de chaque langue.
12. Given un corps POST avec un champ inconnu ou une valeur hors liste (profil, mode, étape, architecture), then 422 ; le GET renvoie textes et état par défaut sans calcul.
13. Given l'installation par défaut sans réseau, sans modèle, sans index, then les deux cartes se jouent intégralement ; E2E : aucune requête hors `127.0.0.1`.
14. Given l'onglet Attaquer, then aucune moyenne ni agrégat n'y apparaît : `rag-attack-erasure.js` et `rag-attack-access.js` sont ajoutés à `OTHER_TABS` et `test_no_average_in_the_other_tabs_of_the_page` passe, et les clés JSON des quatre points d'accès ne contiennent aucun mot du motif `AVERAGE`.
15. Given la carte « Document piégé » de la story 17, then elle fonctionne comme avant (tests de la story 17 et scénario `rag_lab_attack` inchangés et verts), ses crochets `attack` ne sont pas remplacés, et l'élément `.rag-soon` du panneau est toujours présent, masqué.
16. Given les textes de l'écran, then ils se dessinent par `textContent`, aucune couleur n'est codée hors jetons, et le statut d'un endroit comme la fuite se lisent en texte (« présent », « effacé », « à reconstruire », « à recharger », « absent », « aucune copie », « illustratif », « fuite »).

## Verification

- `uv run pytest -q --tb=short tests/test_rag_erasure.py tests/test_rag_access.py tests/test_rag_attack.py tests/test_rag.py tests/test_rag_questions.py tests/test_rag_contexts.py tests/test_rag_lab_views.py tests/test_rag_evaluation.py tests/test_i18n.py tests/test_annex_language.py` -- vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag_lab_rights,rag_lab_attack` -- vert, tranche courte.

## Plan de tests

- **pytest, `tests/test_rag_erasure.py`**, dossier de données isolé, aucun modèle ni réseau :
  - sentinelle ajoutée au corpus en mémoire sans toucher `rag.yaml`, empreinte, corpus livré, contextes livrés ni copie de travail ; octets avant et après (critères 1, 2) ;
  - automate : statuts attendus écrits à la main par endroit et par langue (valeurs de « Mesures »), garde sans sentinelle, double `erase`, `rebuilt` hors `rebuild` (422), `rebuild` d'une architecture sans effet sur les autres, copie partagée des contextes (critères 3 à 6) ;
  - question sur le code : la sentinelle aux rangs 1 et 2 (position 2 puis 1) avant `erase`, absente après ; texte remonté depuis chaque endroit encore présent (critère 5) ;
  - données : miroir fr, en, de, provenance (`recorded` incomplet refusé, `constructed` sans story refusé), `text` avec le code et `rebuilt_text` sans, références vers le corpus (critères 7, 11) ;
  - points d'accès : GET, POST, 422 (critère 12) ; clés sans motif d'agrégat (critère 14) ; imports permis par AST (critère 9).
- **pytest, `tests/test_rag_access.py`** :
  - profil Tous, après : `leaked`, rangs et nombre rendu écrits à la main, trois langues (critère 8) ; la réécriture construite cite le titre d'un document de `leaked` mesuré, dans chaque langue ;
  - profil Tous, avant : `leaked` vide, rendu = k, aucun passage RH ; fabriques de la session qui lèvent (critère 9) ;
  - profil RH, deux modes (critère 10) ; garde : pour toute question du jeu et chaque langue, le mode `before` du profil `all` n'a jamais de passage RH lu ;
  - données et points d'accès (critères 11, 12, 14).
- **pytest existants à relancer** : `test_rag_attack.py` (critère 15), `test_rag_lab_views.py` (onglets), `test_rag_evaluation.py` (agrégats, `OTHER_TABS`), `test_rag.py`, `test_rag_questions.py` (sentinelle inactive), `test_rag_contexts.py` (fichier livré), `test_i18n.py` (parité des `rag_attack.yaml` après retrait de `story18_text`).
- **E2E `rag_lab_rights`** : ouvrir Attaquer, activer la sentinelle, construire les copies, supprimer, lire le tableau (chunks « effacé », contextes et résumés « à reconstruire », CAG « à recharger », mentions « illustratif »), poser la question sur le code, reconstruire GraphRAG et voir ses endroits passer « effacé » ; Droits : profil Tous en mode après, lire la fuite (passage RH lu avant le filtre, rendu < k), passer en mode avant et constater l'absence de fuite, passer en RH ; vérifier qu'aucune requête ne sort de `127.0.0.1` et que la carte « Document piégé » répond encore.

## Mesures du point de contrôle (2026-10-25, sans modèle, sur af49d59)

- Sentinelle active, `chunk_max_chars: 700` : 2 chunks de `projet_talvane`, tous deux avec `TLV-7731-QZ` (fr, en, de) ; corpus 75 / 67 / 80 chunks (73 / 65 / 78 sans elle). Le code n'apparaît dans aucun autre fichier de `content/`, ni dans les trois `rag_contexts.yaml`.
- Contextes heuristiques recalculés avec la sentinelle : l'entrée de la position 1 cite le code (« … identifié par le code unique TLV-7731-QZ »), celle de la position 2 non, trois langues.
- Requête BM25 « TLV-7731-QZ » (termes `orn`, `7731`, `qz`) : `projet_talvane` position 2 au rang 1, position 1 au rang 2, puis score 0, trois langues.
- `q_global_rh`, k = 3, profil Tous, après : fr `formation_securite`, `entretiens_annuels` (hr), `grille_remunerations` (hr) ; en idem ; de `prestataires`, `entretiens_annuels` (hr), `deplacements`. Avant (index restreint) : fr et en `formation_securite`, `ia_generative`, `teletravail` ; de `prestataires`, `deplacements`, `registre_sous_traitants` ; k atteint.

## Décisions du point de contrôle (2026-10-25)

1. Copies mesurées : instantanés en mémoire (texte des chunks, `lexical_index`, contextes heuristiques, source) ; l'index SQLite réel avec vecteurs part en Reports. Les vecteurs ne sont pas dits mesurés.
2. Dérivés produits par un modèle (RAPTOR, PageIndex, GraphRAG, wiki, CAG, préfixe du contexte long) : `constructed`, `text` avec le code et `rebuilt_text` sans, marqués illustratifs, story de remplacement 10 à 14 ; coût de remise en conformité en mots seulement.
3. Question de la carte Droits : `q_global_rh` (passage RH au rang 2 dans les trois langues, k = 3) ; aucune question propre à la carte.
4. Fuite en mode après : ensemble lu avant le filtre plus nombre rendu < k ; la réécriture est un texte construit qui cite `entretiens_annuels`, vérifié contre `leaked` ; le live part en Reports.
5. Contextes : deux lignes, les contextes heuristiques recalculés en mémoire (mesurés, mode `rebuild`, copie partagée) et le fichier livré mesuré tel quel (« absent »), jamais modifié.
6. `faq_mots_de_passe` n'est pas utilisé ; la garde reste l'empreinte du corpus actif (critère 1).
7. Retrait accepté : une ligne de `rag-attack.js`, la section `rag-atk-soon-box` de `rag.html` et `story18_text` des trois `rag_attack.yaml` (la branche contient déjà la story 17).
8. Tableau : regroupé par endroit (ordre de `attaques-et-conformite.md` et de la maquette), une ligne par architecture concernée, 11 architectures ; une architecture sans copie pour un endroit n'y figure pas.

## Spec Change Log

- 2026-10-25 : rédaction (draft), points ouverts à trancher au point de contrôle de spec.
- 2026-10-25, revue (passe 1), décision de l'orchestrateur à confirmer par Anaël : un endroit construit reconstruit prend le statut `erased_illustrative` (« effacé (illustratif, non mesuré) »), jamais « effacé » ; `rebuild` sans architecture répond 422 ; la ligne Source dit si le code y est encore lu ; critère 6 réécrit en conséquence.
- 2026-10-25, point de contrôle : numérotation des stories corrigée (10 contexte long et CAG, 11 agentique et PageIndex, 12 RAPTOR et CRAG, 13 GraphRAG, 14 LLM Wiki ; CRAG, agentique et contexte long n'existent pas dans l'atelier) ; endroits alignés sur `attaques-et-conformite.md` (BM25 pour hybride et CRAG seulement, préfixe en cache du contexte long, feuilles de RAPTOR, contenu précalculé livré) ; vecteurs non mesurés dits tels ; contextes heuristiques mesurés ajoutés ; « factoriser `memory_corpus` » retiré (contredisait « `attack.py` non modifié ») ; accroche JS corrigée (`registerTab("attack")` remplacerait les crochets de la story 17) ; requête de l'effacement précisée (garde, 422 de `rebuilt`) ; valeurs mesurées écrites dans les critères 3 et 8 ; `OTHER_TABS` explicite ; test d'imports permis ; aucun chiffre de coût inventé ; statut ready-for-dev.

## Reports

- Tâche humaine (Anaël), à faire avant de déclarer la story finie (`done_checkpoint`) :
  - ouvrir l'onglet Attaquer en fr, en, de, thèmes clair et sombre : cartes Effacement et Droits lisibles, mentions « illustratif » et « cas construit » visibles, statuts lisibles sans la couleur ;
  - jouer la suppression de la sentinelle : chunks et BM25 « effacé », contextes et dérivés « à reconstruire », CAG « à recharger » ; poser la question sur le code et vérifier ce qui fuit encore ; reconstruire une architecture ;
  - jouer les droits : profil Tous en mode après (fuite visible), puis en mode avant (aucune fuite), puis profil RH ; relire la note de fuite en en et de ;
  - vérifier que les corpus livrés et la copie de travail de Construire n'ont pas changé après ces démonstrations ;
  - relire les contenus construits (résumé, page de wiki, cache) : ils ne contiennent que le code fictif.
- Reprise après les stories 10 à 14 : brancher les lignes illustratives sur les vrais dérivés (recherche du code dans le cache, l'arbre, les résumés, le graphe, le wiki), mesurer le coût et la durée de remise en conformité, et reporter le résultat dans la fiche conformité (axe Effacement, story 19) et `brownfield.md`.
- Index SQLite réel avec vecteurs : suppression par `doc_id` puis vérification que la table des vecteurs ne contient plus de ligne de la sentinelle (décision 1) : story ultérieure.
- Fuite réelle par la réécriture de requête et le contexte du modèle actif, avec un modèle enregistré : story ultérieure (live, AD-3).
- Pré-existant, hors story (décision d'Anaël) : `projet_talvane.md` cite « story 14 » pour les démonstrations d'effacement (c'est la story 18) ; le corriger demande de modifier le corpus livré, donc empreinte, contextes et miroirs i18n : à traiter séparément.

## Revue

### Passe 1 (2026-10-25, SHA revu 64bdd4d)

- Important · medium · second avis · corrigé : un endroit construit passait « effacé » sur la foi de `rebuilt_text`, écrit à la main (« aucun effacé sans mesure »). Statut `erased_illustrative` (« effacé (illustratif, non mesuré) », en, de), bordure pointillée et note explicative (`status_note_text`), critère 6 mis à jour.
- Important · low · second avis · corrigé : Source (`none`) toujours « aucune copie », alors que le code y est lu (1) puis plus (0). Le statut reste `no_copy` (spec), le texte ajoute « le code est lu dans la source » ou « le code n'est plus dans la source ».
- Important · low · second avis · corrigé : `rebuild` avec `rebuilt` vide était accepté (tableau identique à `erase`). Refusé en 422 ; la page n'envoie jamais `rebuild` sans architecture.
- Important · low · second avis · corrigé : allemand fautif après « mit » (« das aktive Modell », et aussi « den echten … », « das echte … » des sept endroits construits) → datif ; parenthèses imbriquées (`to_record_with` des Droits, `upcoming_text`) retirées, fr, en, de.
- Important · low · second avis · corrigé : `texts: dict[str, Any]` non validé (clé manquante = 500 au rendu). Liste `REQUIRED_TEXTS` vérifiée au chargement dans `erasure.py` et `access.py`, tests de refus ajoutés.
- Pre-existing · low · revue · reporté : `rag_attack.yaml` (de, story 17) écrit aussi « mit den Standardgenerator », « mit den echten GraphRAG-Index » (datif attendu « dem ») ; à corriger dans la story 17 ou à part.
- Complexité : 0 constat (structures bornées, recalculées à chaque requête, corpus de 65 à 80 passages).
