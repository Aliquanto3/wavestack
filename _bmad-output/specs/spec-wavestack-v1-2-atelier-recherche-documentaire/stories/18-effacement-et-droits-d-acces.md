---
title: 'Story 18 : effacement de la sentinelle et droits d''accès (profils Tous et RH)'
type: 'feature'
created: '2026-10-25'
status: 'draft'
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

**Problem:** L'emplacement des cartes « Effacement » et « Droits d'accès » de l'onglet Attaquer affiche « à venir ». Le participant ne voit pas qu'effacer un document de la source ne l'efface pas de ses copies (chunks, index, résumés, graphe, wiki, cache), ni qu'un filtre de droits placé après la recherche laisse déjà passer un passage RH dans le pipeline, alors qu'un contrôle placé avant la recherche ne le peut pas.

**Approach:** Deux cartes, deux modules côté session (AD-1), sans modèle génératif.
- **Effacement (CAP-14)** : la sentinelle `projet_orion` (code `ORN-7731-QZ`, inactive dans `rag.yaml`) est activée **dans l'état de la page** (comme le document piégé de la story 17, jamais dans `content/`, l'index ou la copie de travail). Le participant la « construit » dans les copies de démonstration, la supprime, puis lit un tableau par architecture : chaque copie ou dérivé est « présent », « effacé » ou « à reconstruire ». Une question qui vise le code, posée après l'effacement, montre quelles copies répondent encore (sans génération : on affiche les passages remontés). Les copies de dense, hybride, reranking, CRAG, agentique et contexte long sont **mesurées** (copies en mémoire construites à l'étape, recherche du code dans leur contenu) ; celles de RAPTOR, PageIndex, GraphRAG, LLM Wiki et CAG sont des **données enregistrées ou construites** (`provenance`), les stories 12 et 13 n'existant pas encore.
- **Droits (CAP-15)** : profils « Tous » et « RH », modes « filtrage après la recherche » et « contrôle avant la recherche », sur une question du jeu qui fait remonter un passage RH. Le calcul est déterministe : BM25 sur le corpus en mémoire, puis filtre (après) ou index restreint au profil (avant). La carte montre ce que le pipeline a lu **avant** le filtre : c'est la fuite.

## Boundaries & Constraints

**Always:**
- Calcul côté session, modules neufs `rag/erasure.py` et `rag/access.py` ; la page envoie son état, reçoit, dessine (AD-1). Le contrôle avant recherche est déterministe et sans LLM : aucun appel de modèle, aucun réseau, aucune clé. On n'appelle de `rag/lab.py` que `bm25` et `bm25_terms` (comme `rag/attack.py`), sur `rag/index.passage_text`. `rag/attack.py` n'est pas modifié.
- Sentinelle et état : `rag.yaml` garde `active: false` pour `projet_orion` ; l'activation est un champ de requête (`sentinel_active`), recalculée à chaque requête, rien n'est retenu par la session ni après un rechargement. Corpus en mémoire = documents actifs livrés plus la sentinelle, via une copie de `RagContent` où seul `projet_orion` passe `active: True` (méthode de `attack.memory_corpus`, à factoriser en ajoutant une fonction, sans modifier l'existante). **Aucun fichier du corpus livré, aucun index, aucune copie de travail n'est créé ou modifié** ; la sentinelle livrée suffit (contenu unique, code `ORN-7731-QZ`, trois langues), aucun document neuf.
- Étapes de l'effacement, tenues par la page : `start` (sentinelle active, copies construites : tout « présent »), `erase` (le document quitte la source), `rebuild` (reconstruction d'une architecture à la fois, `rebuilt: [ids]`). Les copies sont des **instantanés en mémoire** construits à l'étape `start` à partir du corpus avec sentinelle ; `erase` n'agit que sur la source et sur ce qui s'efface sur place ; `rebuild` reconstruit l'instantané depuis la source sans la sentinelle.
- Règle d'état d'un endroit (déclarée en données, `erase_mode`) : `delete` (supprimable sur place par identifiant de document : chunks et vecteurs, index BM25) devient « effacé » après `erase`, le contenu étant réellement filtré puis recherché ; `rebuild` (contenu dérivé qu'on ne peut pas réécrire sur place : résumés, arbre, graphe, wiki, contextes précalculés) reste « présent · à reconstruire » tant qu'il contient le code, et devient « effacé » après `rebuild` ; `reload` (cache de prompt ou KV du CAG) reste « présent · à recharger » ; `none` (agentique, contexte long : aucune copie persistante, le contenu est relu de la source) est « aucune copie » et la recherche du code échoue dès `erase`. Le statut affiché d'un endroit mesuré est **calculé** : présent si la recherche du code dans son contenu trouve au moins une occurrence, sinon effacé.
- Droits : profils `all` et `hr` ; `all` ne voit que `audience: all`, `hr` voit tout. Mode `after` : top-k BM25 sur tout le corpus, puis retrait des passages interdits ; la carte donne l'ensemble lu par le pipeline avant le filtre (`seen_before_filter`), l'ensemble rendu, la liste des passages RH lus (`leaked`), et le nombre rendu inférieur à k (« le nombre de résultats trahit l'existence du document »). Mode `before` : on interroge seulement l'index des documents autorisés ; `seen_before_filter` = rendu, `leaked` vide, k atteint par les passages suivants. Profil `hr` : les passages RH sont autorisés, donc jamais comptés comme fuite, dans les deux modes. L'étape de réécriture de requête qui « a lu » le passage en mode `after` est une donnée enregistrée (`provenance: constructed`), non un appel.
- Question du droits : `q_global_rh` (audience `hr`, `rag_questions.yaml`) si son passage RH remonte dans le top-k (D3) ; sinon une question propre à la carte, déclarée dans le fichier de données de la carte, sans toucher `rag_questions.yaml`. Rang et k mesurés à la main au développement, écrits dans les tests, par langue.
- Données dans `content/rag_erasure.yaml` et `content/rag_access.yaml` (surcouches `content/i18n/{en,de}/`, mêmes clés, structure et verdicts communs aux trois langues, textes traduits) : textes, liste des architectures et des endroits (`erase_mode`, `measured` ou `provenance`), contenu enregistré des dérivés non implémentés (résumé de communauté, page de wiki, nœud d'arbre, cache : chacun cite le code), question et k, notes par architecture (GraphRAG : un résumé de communauté peut mêler des profils). Un dérivé `constructed` s'affiche « cas construit pour la démonstration (à enregistrer avec … ) ».
- Chaque dérivé non implémenté cite en données la story qui le remplacera (13 pour GraphRAG, 12 pour RAPTOR, le wiki, PageIndex et le CAG selon la numérotation de `stories.yaml`) ; les cinq lignes concernées sont marquées « illustratif » à l'écran.
- Onglet Attaquer, piste « onglets » : nouveaux fichiers `rag-attack-erasure.js` et `rag-attack-access.js` (une carte chacun, `registerTab` non redéclaré : ils s'accrochent à l'onglet par `store` et au panneau `rag-panel-attack`), balises `<script type="module">` ajoutées dans `rag.html`. Dans `rag-attack.js`, **une seule ligne retirée** : l'écriture de `story18_text` dans `rag-atk-soon` (l'élément disparaît). `.rag-soon` du panneau reste présent, masqué. Les textes d'une page se dessinent par `textContent`, jamais `innerHTML`.
- Ajouts seuls dans `app.py` (bloc `# V1.2 story 18`), `app_session.py` (fin de section RAG), `rag.html`, `rag.css`, `ui.yaml`, `messages.yaml` (×3), `run_e2e.py`, README E2E. Aucune couleur hors des jetons ; textes fr, en, de ; état jamais porté par la couleur seule (texte « présent », « effacé », « à reconstruire », « fuite »).
- Charge inoffensive : le code `ORN-7731-QZ` est fictif (texte livré). Aucune donnée réelle ; les passages RH sont ceux du corpus fictif.

**Never:**
- Pas de modification du corpus livré (`content/corpus/**`, `content/i18n/**/corpus/**`), de `rag.yaml`, de l'index, de la copie de travail ou de `rag_questions.yaml` ; pas d'activation persistante de la sentinelle.
- Pas d'appel de modèle (génératif, embedding, reranking), pas de téléchargement, pas de réseau ; pas de GraphRAG, RAPTOR, PageIndex, wiki ni CAG construits ici.
- Pas de filtre de droits appliqué au chat ni à l'atelier (Construire, Comparer, Évaluer) : la démonstration vit dans la carte seulement.
- Pas de score global ni de moyenne dans l'onglet (SPEC.md) ; pas de nouvel événement des exécutions de l'atelier ni de ligne au Journal de sécurité.
- Pas de dépendance nouvelle.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Onglet ouvert, rien d'activé | `sentinel_active` faux | Carte Effacement : sentinelle « inactive », bouton « Construire les copies » ; corpus livré inchangé | N/A |
| Copies construites | `start`, sentinelle active | Tableau par architecture : tous les endroits « présent » (mesuré pour dense, hybride, reranking, CRAG ; `none` pour agentique et contexte long) | N/A |
| Après suppression | `erase` | Chunks et BM25 « effacé » (recherche du code vide) ; dérivés « présent · à reconstruire » ; CAG « présent · à recharger » ; la requête sur le code remonte le passage dans les dérivés encore présents | N/A |
| Reconstruction d'une architecture | `rebuild` + `rebuilt: [graphrag]` | Les endroits de cette architecture passent « effacé » ; les autres restent ; coût de remise en conformité affiché (donnée, `constructed`) | Id inconnu : 422 |
| Suppression avant construction | `erase` sans `start` | Garde : message « rien à effacer, construisez d'abord » ; aucun statut changé | 200 avec message |
| Sentinelle désactivée | case décochée | Retour à `start` vide ; corpus en mémoire sans la sentinelle | N/A |
| Droits, Tous, après | profil `all`, mode `after` | `seen_before_filter` contient le passage RH, `leaked` non vide, rendu < k, note « fuite » | N/A |
| Droits, Tous, avant | profil `all`, mode `before` | `leaked` vide, `seen_before_filter` = rendu, aucun passage RH, k atteint | N/A |
| Droits, RH | profil `hr`, deux modes | passages RH rendus, aucune fuite comptée | N/A |
| Question absente de la langue | `question_id` inconnu dans la langue | 500 évité : données validées au chargement (erreur claire) | Refus au chargement |
| Corps invalide | champ inconnu, valeur hors liste | 422 | N/A |
| Aucune requête hors poste | install par défaut | Cartes jouées intégralement sans modèle, index ni clé | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/erasure.py` (nouveau) : chargement et validation de `rag_erasure.yaml` (pydantic `extra="forbid"`, comme `attack.py`) ; corpus en mémoire avec la sentinelle ; instantanés des copies mesurées (liste de passages par endroit) ; recherche du code (`bm25` et correspondance exacte sur le texte replié) ; automate `start`, `erase`, `rebuild` ; tableau par architecture ; requête sur le code par architecture ; provenance des dérivés enregistrés.
- `src/wavestack/rag/access.py` (nouveau) : chargement et validation de `rag_access.yaml` ; corpus en mémoire (documents actifs, `audience` par passage via `RagContent`) ; top-k BM25 sur tout le corpus ou sur l'index restreint ; filtre ; calcul de `seen_before_filter`, `leaked`, `returned`, nombre rendu contre k.
- `src/wavestack/session/app_session.py` (fin de section RAG) : `rag_lab_erasure_texts`, `rag_lab_erasure(request)`, `rag_lab_access_texts`, `rag_lab_access(request)` ; pures, acceptées dans tout état.
- `src/wavestack/web/app.py` (ajouts, `# V1.2 story 18`) : `GET` et `POST /api/rag_lab/erasure`, `GET` et `POST /api/rag_lab/access` ; corps fermés (422 sur champ inconnu ou valeur hors liste).
- `src/wavestack/web/static/rag-attack-erasure.js`, `rag-attack-access.js` (nouveaux), `rag-attack.js` (une ligne retirée), `rag.html` (deux cartes à la place de `rag-atk-soon-box`, scripts), `rag.css`.
- `content/rag_erasure.yaml`, `content/rag_access.yaml` et leurs surcouches `content/i18n/{en,de}/` ; `ui.yaml`, `messages.yaml` : ajouts seuls ×3.
- `tests/test_rag_erasure.py`, `tests/test_rag_access.py` (nouveaux) ; `tools/e2e/run_e2e.py` (scénario `rag_lab_rights`, ajout seul) ; `tools/e2e/README.md`.

## Tasks & Acceptance

- [ ] Mesure à la main (fr, en, de) : rang BM25 des passages RH pour la question de la carte Droits, rang du passage de la sentinelle pour la question sur le code ; écrire les valeurs dans les tests.
- [ ] `rag/erasure.py` et données `rag_erasure.yaml` ×3 (architectures, endroits, dérivés enregistrés, provenance).
- [ ] `rag/access.py` et données `rag_access.yaml` ×3.
- [ ] Session, points d'accès GET/POST, corps fermés.
- [ ] Cartes Effacement et Droits (JS, HTML, CSS), une ligne retirée de `rag-attack.js`.
- [ ] Scénario E2E `rag_lab_rights` ; tests ciblés ; réalignement des tests qui lisent la structure de l'onglet Attaquer (`git grep` `rag-atk-soon`, `story18_text`).

**Acceptance Criteria:**
1. Given l'onglet Attaquer ouvert sans action, then la sentinelle est inactive, `rag.yaml` garde `active: false` pour `projet_orion`, et `chunk_corpus(load_rag_content(lang), …)` ainsi que `index.corpus_digest` sont identiques avant et après un `GET` et un `POST` des deux cartes.
2. Given l'activation puis l'effacement puis la reconstruction (POST successifs), then les octets de `content/rag.yaml`, de `content/corpus/**`, de `content/i18n/**/corpus/**` et du dossier de données isolé de `tests/conftest.py` (index, copie de travail) ne changent pas, et `workcopy.load(lang)` rend la même copie.
3. Given `start`, then chaque endroit mesuré (chunks et vecteurs, index BM25) de dense, hybride, reranking et CRAG contient le code `ORN-7731-QZ` dans au moins un passage (statut « présent » calculé, nombre d'occurrences affiché), dans les trois langues.
4. Given `erase`, then ces mêmes endroits ne contiennent plus aucun passage avec le code (recherche vide, statut « effacé » calculé), et la source n'a plus la sentinelle.
5. Given `erase`, then chaque endroit `rebuild` (résumés, arbre, graphe, wiki, contextes) garde le code et s'affiche « présent · à reconstruire », le cache du CAG « présent · à recharger », l'agentique et le contexte long « aucune copie » ; la question sur le code remonte, pour chaque endroit encore présent, le texte qui le contient (aucune génération).
6. Given `rebuild` pour une architecture, then seuls ses endroits passent « effacé » (recherche du code vide dans l'instantané reconstruit) ; les autres architectures gardent leur statut ; un id inconnu répond 422 ; `erase` sans `start` renvoie le message de garde sans changer de statut.
7. Given les lignes des dérivés non implémentés (RAPTOR, PageIndex, GraphRAG, LLM Wiki, CAG), then chacune porte `provenance: constructed` ou `recorded` et l'écran la présente comme illustrative ; un cas `recorded` sans date ou sans modèle est refusé au chargement ; aucun cas `constructed` n'est présenté comme enregistré.
8. Given le profil « Tous » et le mode « après la recherche », then `leaked` contient au moins un passage `audience: hr`, présent dans `seen_before_filter`, absent du rendu, et le nombre rendu est inférieur à k ; la note de fuite est affichée. Vérifié par pytest et par E2E (SPEC.md, CAP-15).
9. Given le profil « Tous » et le mode « avant la recherche », then `leaked` est vide, aucun passage RH n'est dans `seen_before_filter` ni dans le rendu, le nombre rendu vaut k, et le code ne fait appel à aucun modèle (les fonctions de modèle, d'embedding et de génération sont remplacées par des fonctions qui échouent si elles sont appelées, la garde réseau de `conftest.py` reste active).
10. Given le profil « RH », then les passages RH sont rendus dans les deux modes et `leaked` est vide (autorisation, pas fuite).
11. Given les trois langues, then `rag_erasure.yaml` et `rag_access.yaml` fr, en, de ont les mêmes architectures, endroits, `erase_mode`, provenances, ids et placeholders ; seuls les textes diffèrent ; chaque `doc_id` et `question_id` cités existe dans `rag.yaml` et `rag_questions.yaml` ; le code de la sentinelle est présent dans le fichier de chaque langue.
12. Given un corps POST avec un champ inconnu ou une valeur hors liste (profil, mode, étape, architecture), then 422 ; le GET renvoie textes et état par défaut sans calcul de modèle.
13. Given l'installation par défaut sans réseau, sans modèle, sans index, then les deux cartes se jouent intégralement ; E2E : aucune requête hors `127.0.0.1`.
14. Given l'onglet Attaquer, then aucune moyenne ni agrégat n'y apparaît : `test_no_average_in_the_other_tabs_of_the_page` passe avec les deux nouveaux fichiers JS (ajoutés à sa liste si elle est explicite), et les clés JSON des quatre points d'accès ne contiennent aucun mot de son motif.
15. Given la carte « Document piégé » de la story 17, then elle fonctionne comme avant (tests de la story 17 inchangés et verts) et l'élément `.rag-soon` du panneau est toujours présent, masqué.
16. Given les textes de l'écran, then ils se dessinent par `textContent`, aucune couleur n'est codée hors jetons, et le statut d'un endroit comme la fuite se lisent en texte (« présent », « effacé », « à reconstruire », « fuite »).

## Verification

- `uv run pytest -q --tb=short tests/test_rag_erasure.py tests/test_rag_access.py tests/test_rag_attack.py tests/test_rag.py tests/test_rag_questions.py tests/test_rag_lab_views.py tests/test_rag_evaluation.py tests/test_i18n.py tests/test_annex_language.py` -- vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag_lab_rights,rag_lab_attack` -- vert, tranche courte.

## Plan de tests

- **pytest, `tests/test_rag_erasure.py`**, `tmp_path` et dossier de données isolé, aucun modèle ni réseau :
  - sentinelle ajoutée au corpus en mémoire sans toucher `rag.yaml`, empreinte, corpus livré ni copie de travail ; octets avant et après (critères 1, 2) ;
  - automate `start`, `erase`, `rebuild` : statuts attendus écrits à la main par endroit, `erase` sans `start`, double `erase`, `rebuild` d'une architecture sans effet sur les autres (critères 3 à 6) ;
  - requête sur le code : rang de la sentinelle écrit à la main, trois langues ; passage remonté depuis chaque endroit encore présent (critère 5) ;
  - données : miroir fr, en, de, provenance (cas `recorded` incomplet refusé), code présent dans chaque langue, références vers le corpus (critères 7, 11) ;
  - points d'accès : GET, POST, 422 (critère 12) ; clés sans motif d'agrégat (critère 14).
- **pytest, `tests/test_rag_access.py`** :
  - profil Tous, après : passage RH dans `seen_before_filter` et `leaked`, absent du rendu, rendu < k ; rangs écrits à la main, trois langues (critère 8) ;
  - profil Tous, avant : `leaked` vide, rendu = k, aucun passage RH ; fonctions de modèle remplacées par des fonctions qui échouent (critère 9) ;
  - profil RH, deux modes (critère 10) ; propriété : pour tout profil `all` et toute question du jeu, le mode `before` n'a jamais de `leaked` non vide ;
  - données et points d'accès (critères 11, 12).
- **pytest existants à relancer** : `test_rag_attack.py` (critère 15), `test_rag_lab_views.py` (onglets), `test_rag_evaluation.py` (agrégats), `test_rag.py`, `test_rag_questions.py` (sentinelle inactive), `test_i18n.py`. Chercher par `git grep` les tests ou scénarios E2E qui lisent `rag-atk-soon` ou `story18_text`, et les réaligner.
- **E2E `rag_lab_rights`** : ouvrir Attaquer, activer la sentinelle, construire les copies, supprimer, lire le tableau (chunks « effacé », résumés « à reconstruire », CAG « à recharger »), poser la question sur le code, reconstruire GraphRAG et voir son statut changer ; Droits : profil Tous en mode après, lire la fuite (passage RH lu avant le filtre, rendu < k), passer en mode avant et constater l'absence de fuite, passer en RH ; vérifier qu'aucune requête ne sort de `127.0.0.1`, que la carte « Document piégé » fonctionne et que le corpus de Construire n'a pas changé.

## Points ouverts (à trancher au point de contrôle de spec)

1. **Copies mesurées en mémoire ou index réel dans le dossier de données** : recommandation, instantanés en mémoire (rapide, sans écriture, sans modèle ni extension SQLite) ; l'index SQLite réel avec vecteurs part en Reports.
2. **Dérivés non implémentés** (RAPTOR, PageIndex, GraphRAG, wiki, CAG) : recommandation, contenu `constructed` au format des futurs dérivés, marqué illustratif, remplacé par la mesure réelle à la livraison des stories 12 et 13.
3. **Question de la carte Droits** : recommandation, `q_global_rh` si le passage RH est dans le top-k BM25 (à mesurer) ; sinon une question propre à la carte dans son fichier de données (pas d'ajout à `rag_questions.yaml`, dont les comptes servent à d'autres stories).
4. **Fuite « avant le filtre »** : recommandation, la fuite est l'ensemble lu avant le filtre plus le nombre rendu inférieur à k ; la réécriture de requête qui a lu le passage est un texte enregistré (`constructed`), le live part en Reports.
5. **Contextes précalculés livrés** (`rag_contexts.yaml`, story 12.6) : recommandation, une ligne « Contenu précalculé livré » mesurée en cherchant le code dans le fichier livré (attendu : absent, la sentinelle étant inactive), sans jamais modifier ce fichier ni les empreintes de chunks.
6. **Corpus du piège** : `faq_mots_de_passe.md` reformulé par 12.17 n'est pas utilisé ici ; recommandation, la carte Effacement ne dépend d'aucun chunk de ce document et le test de non-régression des empreintes (critère 1) reste la garde.
7. **Une ligne retirée de `rag-attack.js`** (fichier de 12.17) : recommandation, accepter ce retrait unique, et supprimer `story18_text` des trois `rag_attack.yaml` seulement si 12.17 est déjà fusionnée (sinon le laisser, inoffensif).
8. **Nombre de colonnes du tableau d'effacement** : recommandation, une ligne par architecture et par endroit (11 architectures), regroupées par endroit pour rester lisibles ; les architectures sans copie pour un endroit n'y figurent pas.

## Spec Change Log

- 2026-10-25 : rédaction (draft), points ouverts à trancher au point de contrôle de spec.

## Reports

- Tâche humaine (Anaël), à faire avant de déclarer la story finie (`done_checkpoint`) :
  - ouvrir l'onglet Attaquer en fr, en, de, thèmes clair et sombre : cartes Effacement et Droits lisibles, mentions « illustratif » et « cas construit » visibles, statuts lisibles sans la couleur ;
  - jouer la suppression de la sentinelle : chunks et BM25 « effacé », dérivés « à reconstruire », CAG « à recharger » ; poser la question sur le code et vérifier ce qui fuit encore ; reconstruire une architecture ;
  - jouer les droits : profil Tous en mode après (fuite visible), puis en mode avant (aucune fuite), puis profil RH ; relire la note de fuite en en et de ;
  - vérifier que les corpus livrés et la copie de travail de Construire n'ont pas changé après ces démonstrations ;
  - relire les contenus de dérivés construits (résumé, page de wiki, cache) : ils ne contiennent que le code fictif.
- Reprise après la story 13 (GraphRAG) et la story 12 (RAPTOR, PageIndex, wiki, CAG) : brancher les lignes illustratives sur les vrais dérivés (recherche du code dans le graphe, les résumés de communautés, les pages du wiki, le cache), mesurer le coût et la durée de remise en conformité, et reporter le résultat dans la fiche conformité (axe Effacement, story 19) et `brownfield.md`.
- Index SQLite réel avec vecteurs : suppression par `doc_id` puis vérification que la table `chunks_vec` ne contient plus le code (point ouvert 1) : story ultérieure.
- Fuite réelle par la réécriture de requête et le contexte du modèle actif, avec un modèle enregistré : story ultérieure (live, AD-3).
- Pré-existant, hors story : `projet_orion.md` cite « story 14 » pour les démonstrations d'effacement (c'est la story 18) ; le corriger demande de modifier le corpus livré, donc empreinte et miroirs i18n : à traiter séparément.
