---
title: 'Story 19 : fiches conformité par architecture et onglet Fiches'
type: 'feature'
created: '2026-10-25'
status: 'draft'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/attaques-et-conformite.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/architectures.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/litterature.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/vues.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/brownfield.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'onglet Fiches de l'atelier affiche « à venir ». Les fiches de composant (CAP-17) existent dans `rag_lab.yaml` pour deux familles d'options seulement (`query`, `chunking`), sans lecteur à l'écran, et aucune architecture n'a de fiche. Le participant ne peut pas lire, pour une architecture, à quoi elle sert, ce qu'elle coûte, ce que dit la littérature, ni ses risques de conformité (où transitent les données, quelles copies elle crée, ce qu'il faut reconstruire pour effacer, si les droits passent avant la recherche, sa surface d'injection, sa traçabilité, le cadre réglementaire à examiner).

**Approach:** Deux jeux de données déclarés dans `content/`, servis par la session (AD-1), dessinés par `rag-sheets.js` :
1. les fiches de **composant** (option de `OPTIONS`), complétées pour toutes les familles restantes et lues pour la première fois à l'écran ;
2. les fiches d'**architecture** (les 11 de la story 18), chacune en cinq blocs (comme un composant) plus la **fiche conformité sur sept axes** (CAP-16). Chaque axe porte un niveau au format de la matrice des risques de la page Sécurité (`mcp/policy.py` `RISKS` : `low`, `mid`, `high`), un texte, et, quand il existe, un lien vers la démonstration de l'onglet Attaquer (CAP-13 à CAP-15). Un test d'exhaustivité fait échouer la suite quand une option ou une architecture n'a pas sa fiche.

Aucun modèle, aucun réseau, aucun calcul : les fiches sont du contenu déclaré. Le bloc « ce qu'a mesuré le banc » reste vide et dit « pas encore mesuré ».

## Boundaries & Constraints

**Always:**
- Données côté session, module neuf `rag/sheets.py` (chargement, validation pydantic `extra="forbid"`, liste, fiche) ; la page envoie le choix de la fiche, reçoit, dessine. Aucune moyenne ni agrégat de niveaux (pas de « score de conformité »).
- **Niveaux.** Le champ `level` d'un axe est validé contre `mcp.policy.RISKS` (importé, jamais recopié) ; la page l'affiche avec les libellés et puces de la page Sécurité (clés `mcp.policy.risk.*`, états lisibles en texte, jamais par la couleur seule). Le niveau dit une **exposition** (`low` : peu exposée, `high` : très exposée), jamais un verdict de conformité.
- **Pas un avis juridique.** Un bandeau fixe en tête de l'onglet et de chaque fiche conformité le dit (« grille pédagogique, pas un avis juridique ; à examiner avec le juriste ou le DPO de votre organisation »). Aucun texte n'affirme qu'une architecture « est conforme » ou « n'est pas conforme » au RGPD, à l'AI Act, à DORA ou à NIS2 : l'axe « Cadre réglementaire » liste les **questions à poser** (RGPD : base légale, minimisation, droit à l'effacement sur les copies et dérivés ; AI Act : classification selon l'usage ; DORA ou NIS2 : selon le secteur ; dépendance fournisseur). Il porte un texte et pas de niveau (`level` interdit sur cet axe, validé au chargement).
- **Littérature.** Les hypothèses sont celles de `litterature.md`, avec leurs liens **tels quels** (même libellé, même URL) ; l'état est dit « soutenue », « partiellement » ou « non étudiée » comme le cadrage. Aucune source n'est inventée ni ajoutée de mémoire : sans accès réseau, une source absente de `litterature.md` et des fiches déjà livrées est refusée par le test (critère 9). Sans source ouverte, la fiche l'indique (`no_source_text`), conformément à `litterature.md`.
- **Architectures non implémentées.** Les 11 architectures de la story 18 ont une fiche écrite ; `dense`, `hybrid`, `rerank` sont implémentées (`lab.PRESETS`), les huit autres (`long_context`, `cag` : story 10 ; `agentic`, `pageindex` : story 11 ; `raptor`, `crag` : story 12 ; `graphrag` : story 13 ; `llm_wiki` : story 14) portent `available: false`, la story qui les livre, et l'étiquette « architecture à venir dans l'atelier (story N) ». Leur fiche reste complète et lisible ; l'étiquette dit seulement que l'atelier ne sait pas encore l'exécuter. Les coûts sont des mots (colonnes B, U, Q de `architectures.md`), aucun chiffre inventé.
- **Liens vers les démonstrations.** Les axes « Effacement » et « Droits d'accès » renvoient aux cartes Effacement et Droits d'accès de l'onglet Attaquer (story 18) ; l'axe « Injection et outils » renvoie à la carte Document piégé (story 17). Le lien ouvre l'onglet Attaquer sur la carte (ancre), sans calcul. Un axe sans démonstration n'a pas de lien.
- **Cohérence avec la story 18.** L'axe Effacement d'une architecture reprend en mots ses endroits de `rag_erasure.yaml` (même liste d'endroits, même coût de remise en conformité en mots) ; un test compare les ids d'architecture et vérifie que chaque endroit cité existe. L'axe Droits reprend le verdict de `rag_access.yaml` (contrôle avant possible ou non). Pas de recopie de statuts mesurés : la fiche renvoie à la carte.
- **Localisation des données.** Déclarative, par composant de l'architecture, en quatre classes (`local`, `cloud_eu`, `secnumcloud`, `outside_eu`). La configuration du dépôt ne porte ni région ni qualification du fournisseur cloud : la fiche déclare `local` pour ce qui tourne dans l'atelier (SLM, embeddings, index) et, pour un composant qui peut appeler un modèle cloud (génération, juge, Jev, export OTel), la valeur `depends_on_provider` (hors des quatre classes, affichée « à vérifier auprès du fournisseur »). Jev est dit propriétaire, sans hébergement local (`architectures.md`).
- **Données** dans `content/rag_sheets.yaml` (architectures, axes) et `content/rag_lab.yaml` (fiches de composant manquantes, clé `sheets`) avec surcouches `content/i18n/{en,de}/` : mêmes ids, niveaux, classes, liens, `available`, stories ; seuls les textes diffèrent. Les fiches des familles ajoutées (`SHEETED_KINDS`) suivent le format de `SheetText` existant.
- **Page.** `rag-sheets.js` (clé `sheets` déjà dans `TAB_IDS`) : liste des composants et des architectures, fiche en cinq blocs, fiche conformité en tableau de sept lignes (axe, niveau en texte et puce, texte, lien). Le texte « à venir » du panneau est retiré par cette story. Tout texte se dessine par `textContent`, aucune couleur hors jetons, contraste AA clair et sombre, sélecteurs E2E des lots précédents conservés. Le lien « Fiche » du focus (vues.md) n'est pas dans cette story (point ouvert 4).
- **Bloc banc.** `bench_text` vide pour toutes les fiches, affiché « Pas encore mesuré » (clé de texte commune) ; aucun chiffre du banc.

**Never:** modifier `mcp/policy.py` (importé seulement), `rag/erasure.py`, `rag/access.py`, `rag/attack.py`, le corpus livré ou `rag.js` ; ajouter un modèle, un téléchargement ou un appel réseau ; afficher un niveau comme une conformité.

## I/O & Edge-Case Matrix

| Cas | Entrée | Sortie |
|---|---|---|
| Liste | `GET /api/rag_lab/sheets` | composants (option de `OPTIONS`, famille, libellé), architectures (id, libellé, `available`, story), textes, ordre fixe ; aucun calcul |
| Fiche de composant | `GET /api/rag_lab/sheets/component/{kind}.{option}` | 5 blocs + sources ; `bench_text` vide rendu « pas encore mesuré » |
| Fiche d'architecture | `GET /api/rag_lab/sheets/architecture/{id}` | 5 blocs + sources + 7 axes (niveau, texte, lien) + bandeau |
| Id inconnu | `kind.option` ou `id` hors liste | 404 |
| Architecture à venir | `cag`, `graphrag`… | fiche complète + étiquette « à venir dans l'atelier (story N) » |
| Axe réglementaire | axe `regulatory` | texte et questions, pas de niveau, bandeau « pas un avis juridique » |
| Langue en/de | surcouche | mêmes ids, niveaux, liens ; textes traduits ; pas de repli silencieux sur le français (test de parité) |
| Option ajoutée plus tard | une story ajoute une option à `OPTIONS` sans fiche | le test d'exhaustivité échoue |

## Code Map

- `src/wavestack/rag/sheets.py` (nouveau) : modèles pydantic (`ArchitectureSheet`, `Axis`, `Source`), chargement de `rag_sheets.yaml`, validation (niveaux contre `RISKS`, classes de localisation, axe réglementaire sans niveau, sources non vides ou `no_source_text`), `listing(lang)`, `component(lang, key)`, `architecture(lang, id)`.
- `src/wavestack/rag/lab.py` : `SHEETED_KINDS` étendu à toutes les familles de `OPTIONS` (une constante ; la validation `sheets` existante fait le reste). Aucun autre changement.
- `src/wavestack/session/app_session.py` (fin de section RAG) : `rag_lab_sheets`, `rag_lab_sheet_component`, `rag_lab_sheet_architecture` (pures, sans entrée au Journal de sécurité).
- `src/wavestack/web/app.py` (ajouts, `# V1.2 story 19`) : trois `GET` ; 404 sur id inconnu.
- `src/wavestack/web/static/rag-sheets.js` (code de l'onglet), `rag.html` (contenu du panneau `rag-panel-sheets`), `rag.css` (ajouts) ; `ui.yaml` et `messages.yaml` ×3 seulement pour un texte hors des deux fichiers de données.
- `content/rag_sheets.yaml`, `content/rag_lab.yaml` (fiches `embedding.*`, `vector_store.*`, `vector_search.cosine`, `lexical_search.bm25`, `fusion.rrf`, `rerank.declared`, `context.excerpts`, `generation.*` : 13 fiches, selon `OPTIONS` au moment de la story) et surcouches `content/i18n/{en,de}/`.
- `tests/test_rag_sheets.py` (nouveau), `tests/test_rag_evaluation.py` (`OTHER_TABS` : `rag-sheets.js`), `tools/e2e/run_e2e.py` (scénario `rag_lab_sheets`, ajout seul), `tools/e2e/README.md`.

## Niveaux proposés (à relire par Anaël, voir Reports)

Exposition sur les axes à niveau (`L` low, `M` mid, `H` high). Localisation : `L` partout tant que tout tourne en local, le texte dit ce qui change avec un modèle cloud. Ce sont des **propositions** tirées de `architectures.md` et `attaques-et-conformite.md`, sans mesure.

| Architecture | Copies | Effacement | Droits | Injection et outils | Traçabilité |
|---|---|---|---|---|---|
| dense, rerank | M | M | M | M | L |
| hybrid | M | M | M | M | L |
| crag | M | M | M | M (repli : réécriture, nouvelle recherche) | L |
| long_context | L | L | H (tout le corpus dans le prompt) | H | M |
| cag | M (cache) | H (recharger tout) | H | H | M |
| agentic | L | L | M (permissions des outils) | H (outils, exfiltration) | L |
| pageindex | M (arbre) | M | M | M | L |
| raptor | H (résumés récursifs) | H | H (un résumé mêle des documents) | M | M |
| graphrag | H | H | H | H (relations empoisonnées) | M |
| llm_wiki | H | H | H | H | M |

## Tasks & Acceptance

- [ ] Rédiger `rag_sheets.yaml` ×3 (11 architectures × 5 blocs × 7 axes) et les 13 fiches de composant manquantes ×3.
- [ ] `rag/sheets.py`, session, points d'accès GET.
- [ ] `rag-sheets.js`, `rag.html`, `rag.css` ; retrait du texte « à venir ».
- [ ] Étendre `SHEETED_KINDS`.
- [ ] Tests (pytest, E2E), `OTHER_TABS`, README E2E.

**Acceptance Criteria:**
1. Given `OPTIONS`, then `SHEETED_KINDS` couvre toutes ses familles et `rag_lab.yaml` a exactement une fiche `kind.option` par option, dans les trois langues (le chargement échoue sinon ; test d'exhaustivité dérivé de `OPTIONS`, jamais d'une liste écrite en dur).
2. Given les 11 ids de `rag_erasure.yaml` (dense, hybrid, rerank, long_context, cag, agentic, pageindex, raptor, graphrag, llm_wiki, crag), then `rag_sheets.yaml` a exactement une fiche par id, dans les trois langues, et l'ensemble d'ids est égal à celui de `rag_erasure.yaml` et `rag_access.yaml`.
3. Given une fiche d'architecture, then elle a cinq blocs (usage, quand l'utiliser ou l'éviter, coût en B, U et Q en mots, littérature, banc) et exactement les sept axes `location`, `copies`, `erasure`, `rights`, `injection`, `traceability`, `regulatory` ; un axe manquant ou en trop échoue au chargement.
4. Given un axe autre que `regulatory`, then son `level` appartient à `mcp.policy.RISKS` (test qui compare à l'import, pas à une copie) ; `regulatory` avec un `level` est refusé.
5. Given l'axe `location`, then chaque composant porte une classe parmi `local`, `cloud_eu`, `secnumcloud`, `outside_eu`, `depends_on_provider` ; aucune classe n'affirme une région non déclarée ; Jev est dit propriétaire sans hébergement local.
6. Given les axes `erasure`, `rights`, `injection`, then leur lien pointe vers une carte existante de l'onglet Attaquer (ancre vérifiée dans `rag.html`) ; `erasure` ne cite que des endroits présents dans `rag_erasure.yaml` de la langue.
7. Given les huit architectures non implémentées, then `available: false` et `story` valent ceux de `rag_erasure.yaml`, la fiche est complète, et l'écran affiche « architecture à venir dans l'atelier (story N) » ; pour dense, hybrid, rerank, `available: true` et l'id est dans `lab.PRESETS` (test).
8. Given le bloc « ce qu'a mesuré le banc », then `bench_text` est vide dans chaque fiche et l'écran affiche « Pas encore mesuré » (en et de traduits).
9. Given les sources des fiches d'architecture, then chaque fiche a au moins une source `https://` ou un `no_source_text` non vide ; toute URL citée figure dans `litterature.md` ou dans une fiche de composant déjà livrée (test qui lit `litterature.md`, sauté avec un marqueur explicite si le fichier du dossier de specs est absent) ; une fiche qui reprend une hypothèse (H1 à H15) cite ses liens avec l'état « soutenue », « partiellement » ou « non étudiée » du cadrage.
10. Given les textes de conformité, then aucun ne contient une formule de conformité affirmée (motifs interdits testés : « est conforme », « conforme au RGPD », « garantit la conformité » et équivalents en, de) ; le bandeau « pas un avis juridique » est présent dans les trois langues, sur l'onglet et sur chaque fiche conformité.
11. Given les trois langues, then ids, niveaux, classes de localisation, liens, `available`, stories, nombres d'axes et de sources, placeholders sont identiques ; seuls les textes diffèrent.
12. Given `GET /api/rag_lab/sheets`, `.../component/{kind}.{option}`, `.../architecture/{id}`, then les réponses suivent la matrice ci-dessus, sans calcul, 404 sur id inconnu ; aucune clé JSON ne contient le motif `AVERAGE` ni un champ de score global.
13. Given l'onglet Fiches ouvert sans réseau, sans modèle, sans index, then la liste, une fiche de composant et une fiche d'architecture (implémentée et à venir) s'affichent ; E2E : aucune requête hors `127.0.0.1`.
14. Given l'onglet, then les niveaux se lisent en texte (« faible », « moyen », « élevé » via `mcp.policy.risk.*`), pas par la couleur seule ; thèmes clair et sombre au contraste AA ; textes dessinés par `textContent`.
15. Given `rag-sheets.js`, then il est ajouté à `OTHER_TABS` de `tests/test_rag_evaluation.py` et `test_no_average_in_the_other_tabs_of_the_page` passe.
16. Given les stories 17 et 18, then leurs cartes, scénarios (`rag_lab_attack`, `rag_lab_rights`) et tests restent verts et inchangés ; `rag/erasure.py`, `rag/access.py`, `mcp/policy.py` ne sont pas modifiés.
17. Given une story ultérieure qui ajoute une option à `OPTIONS` ou un préréglage à `PRESETS` sans fiche, then `tests/test_rag_sheets.py` échoue avec un message qui nomme l'option ou le préréglage manquant.

## Verification

- `uv run pytest -q --tb=short tests/test_rag_sheets.py tests/test_rag_lab.py tests/test_rag_lab_views.py tests/test_rag_evaluation.py tests/test_rag_erasure.py tests/test_rag_access.py tests/test_i18n.py tests/test_annex_language.py` -- vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag_lab_sheets,rag_lab_rights` -- vert, tranche courte.

## Plan de tests

- **pytest, `tests/test_rag_sheets.py`**, sans modèle ni réseau :
  - exhaustivité (critères 1, 2, 17) : composants dérivés de `OPTIONS`, architectures dérivées de `rag_erasure.yaml` et de `PRESETS` ; message d'échec nommant l'élément manquant ;
  - structure et validation (critères 3 à 5) : sept axes exacts, niveaux contre `RISKS`, `regulatory` sans niveau, classes de localisation ; cas refusés au chargement (axe manquant, niveau inconnu, classe inconnue, `no_source_text` et `sources` tous deux vides) ;
  - liens et cohérence avec la story 18 (critères 6, 7) : ancres présentes dans `rag.html`, endroits cités présents dans `rag_erasure.yaml`, `available` et `story` égaux ;
  - sources (critère 9) : URL présentes dans `litterature.md` ou les fiches livrées ; états de littérature ; saut avec marqueur si le fichier de specs est absent ;
  - motifs de conformité interdits, bandeau présent ×3 langues (critère 10) ;
  - parité fr, en, de (critère 11) ;
  - points d'accès : GET, 404, clés sans agrégat (critère 12).
- **pytest existants à relancer** : `test_rag_lab.py` (validation `sheets` après extension de `SHEETED_KINDS`), `test_rag_lab_views.py` (onglets), `test_rag_evaluation.py` (`OTHER_TABS`), `test_rag_erasure.py`, `test_rag_access.py`, `test_i18n.py`.
- **E2E `rag_lab_sheets`** (aucun prérequis d'index) : ouvrir Fiches, voir la liste (au moins 21 composants, 11 architectures), ouvrir une fiche de composant (cinq blocs, « Pas encore mesuré »), ouvrir `hybrid` (sept axes, niveaux en texte, bandeau « pas un avis juridique »), suivre le lien de l'axe Droits vers la carte Droits d'accès de l'onglet Attaquer, ouvrir `graphrag` (étiquette « à venir dans l'atelier »), repasser en en puis de ; aucune requête hors `127.0.0.1`. Capture clair et sombre.

## Spec Change Log

- 2026-10-25 : création (phase 1, point de contrôle de spec).

## Points ouverts (recommandation)

1. **Fiches de composant des autres familles** : le test d'exhaustivité du critère 1 impose 13 fiches nouvelles (embedding, vector_store, vector_search, lexical_search, fusion, rerank, context, generation) en plus des 8 livrées. Recommandation : les écrire ici (CAP-17 le demande), en citant H1 (fusion, rerank), H14 (vector_store), H10 (generation) ; sinon la fin de CAP-17 reste ouverte.
2. **Sources de RAPTOR et de CRAG** : `litterature.md` n'a pas de source primaire pour RAPTOR (CRAG n'a que H7) et il n'y a pas d'accès réseau pour en ouvrir une. Recommandation : `no_source_text` explicite pour RAPTOR (H7 seule pour CRAG) ; l'article d'origine est ajouté par Anaël ou par une session avec réseau, source ouverte et lue ; ne pas écrire un identifiant arXiv de mémoire.
3. **Niveau sur l'axe « Cadre réglementaire »** : recommandation, aucun niveau (texte et questions seulement), pour éviter un pseudo-verdict juridique ; l'axe garde sa ligne dans le tableau.
4. **Lien « Fiche » du focus** (vues.md) : recommandation, hors story (touche `rag.js`, partagé) ; reporté, l'onglet Fiches se suffit.
5. **Affichage sur la page Sécurité** : `attaques-et-conformite.md` dit qu'elle « peut » afficher ces données. Recommandation : seulement le format partagé (`RISKS`) et un lien vers l'onglet Fiches ; pas de seconde matrice sur la page Sécurité dans cette story (`security.js` et son endpoint ne bougent pas).
6. **Localisation des données** : la configuration n'a ni région ni qualification du fournisseur. Recommandation : classes déclaratives dans les données, `depends_on_provider` pour tout composant cloud ; une lecture réelle de `[[cloud.models]]` attend un champ dédié, en report.
7. **Niveaux des axes** : le tableau ci-dessus est une proposition sans mesure. Recommandation : Anaël le relit avant le code ; les cases `mid` de l'axe Droits reposent sur H12 et H14, à confirmer.
8. **Coûts de remise en conformité** : l'axe Effacement reprend les mots de la story 18 ; une durée ou un coût mesuré attend les stories 10 à 14. Recommandation : mots seulement, mention « pas encore mesuré ».

## Reports

- Tâche humaine (Anaël), avant de déclarer la story finie (`done_checkpoint`) :
  - relire **tous les contenus de conformité** en fr, puis en et de : niveaux des 11 × 5 axes, formulations de l'axe réglementaire (RGPD, AI Act, DORA, NIS2) ; aucune phrase ne doit se lire comme un avis juridique ni comme une conformité affirmée ;
  - vérifier chaque lien de littérature ouvert (états « soutenue », « partiellement », « non étudiée » cohérents avec `litterature.md`) et décider des sources de RAPTOR et de CRAG (point ouvert 2) ;
  - ouvrir l'onglet Fiches en fr, en, de, thèmes clair et sombre : liste, fiche de composant, fiche d'architecture implémentée et « à venir », lien vers les cartes Attaquer, niveaux lisibles sans la couleur ;
  - vérifier le bandeau « pas un avis juridique » sur l'onglet et sur chaque fiche conformité.
- Reprise après les stories 10 à 14 : brancher le bloc « ce qu'a mesuré le banc » dès que le projet de banc publie, reporter les coûts et durées de remise en conformité mesurés (axe Effacement), retirer l'étiquette « à venir » à la livraison de chaque architecture (le champ `available` se lit de `lab.PRESETS`, à brancher).
- Lecture réelle de la localisation depuis la configuration cloud : attend un champ région ou qualification (hors lot).
- Lien « Fiche » du focus vers la fiche du composant : story ultérieure.
