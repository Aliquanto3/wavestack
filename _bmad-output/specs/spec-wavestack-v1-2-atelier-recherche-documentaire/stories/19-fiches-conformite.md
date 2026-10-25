---
title: 'Story 19 : fiches conformité par architecture et onglet Fiches'
type: 'feature'
created: '2026-10-25'
status: 'ready-for-dev'
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

**Approach:** Des données déclarées dans `content/`, servies par la session (AD-1), dessinées par `rag-sheets.js` :
1. les fiches de **composant** déjà livrées (`query.*`, `chunking.*` de `rag_lab.yaml`, 8 fiches), lues pour la première fois à l'écran ; les fiches des autres familles sont **reportées à la story 19b** (décision 1) ;
2. les fiches d'**architecture** (les 11 de la story 18), chacune en cinq blocs (comme un composant) plus la **fiche conformité sur sept axes** (CAP-16). Chaque axe à niveau porte un niveau au format de la matrice des risques de la page Sécurité (`mcp/policy.py` `RISKS` : `low`, `mid`, `high`), un texte, et, quand elle existe, un lien vers la démonstration de l'onglet Attaquer (CAP-13 à CAP-15). Un test d'exhaustivité fait échouer la suite quand un préréglage ou une architecture n'a pas sa fiche, ou quand une famille d'options n'est ni fichée ni explicitement en attente.

Aucun modèle, aucun réseau, aucun calcul : les fiches sont du contenu déclaré. Le bloc « ce qu'a mesuré le banc » reste vide et dit « pas encore mesuré ».

## Boundaries & Constraints

**Always:**
- Données côté session, module neuf `rag/sheets.py` (chargement, validation pydantic `extra="forbid"`, liste, fiche) ; la page envoie le choix de la fiche, reçoit, dessine. Aucune moyenne ni agrégat de niveaux (pas de « score de conformité »).
- **Une seule source par donnée.** `rag_sheets.yaml` ne recopie pas ce que la story 18 déclare : le libellé de l'architecture, ses endroits d'effacement (les `places` de `rag_erasure.yaml` dont la liste `architectures` contient l'id, avec leurs `label_text`) et son coût de remise en conformité en mots (`update_text`) sont lus par `rag/sheets.py` via `rag.erasure.load_erasure(lang)` (importé, non modifié) et joints à la réponse. `available` n'est pas déclaré : il vaut `id in lab.PRESETS`. Seul `story` (la story qui livrera l'architecture) est déclaré, requis si et seulement si l'id n'est pas dans `PRESETS`.
- **Niveaux.** Le champ `level` d'un axe est validé contre `mcp.policy.RISKS` (importé, jamais recopié) ; la page l'affiche avec les libellés de la page Sécurité (`t("mcp.policy.risk.<level>")`, `rag.js` importe déjà `t` d'`i18n.js`) et la puce `status-chip` / `status-chip-<level>` de `pages.css` (déjà chargé par `rag.html`), le mot toujours écrit, jamais la couleur seule. Le niveau dit une **exposition** (`low` : peu exposée, `high` : très exposée), jamais un verdict de conformité ; les niveaux sont affichés avec la mention « proposition, à relire » (`texts.levels_note_text`, décision 7).
- **Pas un avis juridique.** Un bandeau fixe en tête de l'onglet et de chaque fiche conformité le dit (« grille pédagogique, pas un avis juridique ; à examiner avec le juriste ou le DPO de votre organisation »). Aucun texte n'affirme qu'une architecture « est conforme » ou « n'est pas conforme » au RGPD, à l'AI Act, à DORA ou à NIS2 : l'axe « Cadre réglementaire » liste les **questions à poser** (RGPD : base légale, minimisation, droit à l'effacement sur les copies et dérivés ; AI Act : classification selon l'usage ; DORA ou NIS2 : selon le secteur ; dépendance fournisseur). Il porte un texte et pas de niveau (`level` interdit sur cet axe, validé au chargement). Écart assumé avec la maquette, qui montre « moyen » sur cet axe (décision 3).
- **Littérature.** Chaque fiche d'architecture déclare `hypotheses` (ids `H1`…`H15` de `litterature.md`, hors H8, H16, H17) et cite, dans `sources`, **tous** les liens de chaque hypothèse déclarée **tels quels** (même libellé, même URL) ; son `literature_text` dit l'état avec le mot du cadrage (« soutenue », « partiellement », « non étudiée », « non démontrée », « contredite »). Correspondance attendue, dérivée de la colonne « Fiches » de `litterature.md` : dense, hybrid, rerank ← H1 ; graphrag ← H2, H13 ; llm_wiki ← H3, H13 ; pageindex ← H4 ; agentic ← H5 ; crag ← H7 ; long_context, cag ← H11 ; **toutes** ← H12 (« fiches conformité »). Toute fiche a donc au moins une source (CAP-17). Aucune source n'est inventée ni ajoutée de mémoire : sans accès réseau, une URL absente de `litterature.md` est refusée par le test (critère 9). RAPTOR n'a pas d'hypothèse propre : son `literature_text` le dit et `no_source_text` (non vide) dit qu'aucune source primaire n'a encore été ouverte (décision 2).
- **Architectures non implémentées.** Les 11 architectures de la story 18 ont une fiche écrite ; `dense`, `hybrid`, `rerank` sont dans `lab.PRESETS`, les huit autres (`long_context`, `cag` : story 10 ; `agentic`, `pageindex` : story 11 ; `raptor`, `crag` : story 12 ; `graphrag` : story 13 ; `llm_wiki` : story 14) portent `story` et l'étiquette « architecture à venir dans l'atelier (story N) ». Leur fiche reste complète et lisible ; l'étiquette dit seulement que l'atelier ne sait pas encore l'exécuter. Les coûts sont des mots (colonnes B, U, Q de `architectures.md`), aucun chiffre inventé.
- **Liens vers les démonstrations.** Les axes « Effacement » et « Droits d'accès » renvoient aux cartes `rag-erasure-card` et `rag-access-card` de l'onglet Attaquer (story 18) ; l'axe « Injection et outils » renvoie à la carte Document piégé (story 17, titre `rag-atk-title`). Le champ `demo` d'un axe vaut un de ces trois ids d'élément de `rag.html`. Comme `rag.js` choisit l'onglet d'après `location.hash` (`tabFromHash`, une ancre `#rag-access-card` ramènerait sur Construire), le lien est `href="#attack"` : `rag-sheets.js` laisse le `hashchange` ouvrir l'onglet, puis fait `scrollIntoView` sur l'élément `demo` et y place le focus ; aucun changement de `rag.js`. Un axe sans démonstration n'a pas de lien.
- **Cohérence avec la story 18.** L'axe Effacement n'a pas de liste d'endroits propre : la session joint celle de `rag_erasure.yaml` (voir « une seule source ») ; son texte ne cite aucun endroit absent de cette liste. L'axe Droits dit en mots si un contrôle avant la recherche est possible pour l'architecture (déclaré dans `rag_sheets.yaml` : `rag_access.yaml` ne porte pas d'architectures, la carte Droits ne démontre que le RAG lexical) et renvoie à la carte. Pas de recopie de statuts mesurés : la fiche renvoie à la carte.
- **Localisation des données.** Déclarative, par composant de l'architecture (`components: [{id, class}]`, ids parmi `documents`, `index`, `derived`, `cache`, `generation`, `judge`, `trace_export`), classes `local`, `cloud_eu`, `secnumcloud`, `outside_eu`, `depends_on_provider`. La configuration du dépôt ne porte ni région ni qualification du fournisseur cloud : les données de cette story n'utilisent que `local` (ce qui tourne dans l'atelier : documents, index, dérivés, cache) et `depends_on_provider` (composant qui peut appeler un modèle cloud : génération par le modèle actif, juge, Jev pour CRAG, export OTel), affiché « à vérifier auprès du fournisseur ». Jev est dit propriétaire, sans hébergement local (`architectures.md`).
- **Données** dans `content/rag_sheets.yaml` (architectures, axes, textes de l'onglet) avec surcouches `content/i18n/{en,de}/rag_sheets.yaml` résolues par `config.content_file` : mêmes ids, niveaux, classes, `demo`, `story`, `hypotheses`, URL ; seuls les textes diffèrent (les libellés de source restent ceux de `litterature.md` dans les trois langues). `rag_lab.yaml` n'est pas modifié dans cette story.
- **Page.** `rag-sheets.js` (squelette existant, clé `sheets` déjà dans `TAB_IDS`, déjà chargé par `rag.html`, déjà dans `OTHER_TABS`) : liste des composants fichés et des architectures, fiche en cinq blocs, fiche conformité en tableau de sept lignes (axe, niveau en mot et puce, texte, lien). Le panneau `rag-panel-sheets` garde son `<p class="rag-note rag-soon">` avec l'attribut `hidden` (comme les panneaux Évaluer et Attaquer : `renderTabs` de `rag.js` y écrit toujours, le retirer casserait la page). Tout texte se dessine par `textContent`, aucune couleur hors jetons, contraste AA clair et sombre, sélecteurs E2E des lots précédents conservés. Le lien « Fiche » du focus (vues.md) n'est pas dans cette story (décision 4).
- **Bloc banc.** `bench_text` vide pour toutes les fiches, affiché « Pas encore mesuré » (`texts.bench_empty_text` de `rag_sheets.yaml`) ; aucun chiffre du banc.

**Never:** modifier `mcp/policy.py`, `rag/erasure.py`, `rag/access.py`, `rag/attack.py`, `rag/lab.py`, `content/rag_lab.yaml` (et surcouches), `content/rag_erasure.yaml`, le corpus livré ou `rag.js` ; ajouter un modèle, un téléchargement ou un appel réseau ; afficher un niveau comme une conformité ; écrire une URL ou un identifiant arXiv de mémoire.

## I/O & Edge-Case Matrix

| Cas | Entrée | Sortie |
|---|---|---|
| Liste | `GET /api/rag_lab/sheets` | composants fichés (`kind.option` des familles de `SHEETED_KINDS`, famille, libellé), architectures (id, libellé de `rag_erasure.yaml`, `available`, `story`), familles en attente (`PENDING_SHEET_KINDS`, mention « fiches à venir (story 19b) »), textes, ordre fixe ; aucun calcul |
| Fiche de composant | `GET /api/rag_lab/sheets/component/{kind}.{option}` | 5 blocs + sources de `rag_lab.yaml` ; `bench_text` vide rendu « pas encore mesuré » |
| Fiche d'architecture | `GET /api/rag_lab/sheets/architecture/{id}` | 5 blocs + sources + 7 axes (niveau, texte, `demo`) + endroits et `update_text` joints de `rag_erasure.yaml` + bandeau |
| Id inconnu | `kind.option` hors familles fichées ou `id` hors liste | 404 |
| Architecture à venir | `cag`, `graphrag`… | fiche complète + étiquette « à venir dans l'atelier (story N) » |
| Axe réglementaire | axe `regulatory` | texte et questions, pas de niveau, bandeau « pas un avis juridique » |
| Langue en/de | surcouche | mêmes ids, niveaux, liens ; textes traduits ; pas de repli silencieux sur le français (test de parité) |
| Option ou famille ajoutée plus tard | option ajoutée à une famille fichée ; famille ajoutée à `OPTIONS` | la validation existante de `rag_lab.yaml` échoue (option) ; le test de partition échoue (famille) |
| Préréglage ajouté plus tard | id ajouté à `PRESETS` sans fiche d'architecture | le test d'exhaustivité échoue en nommant l'id |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/sheets.py` (nouveau) : `PENDING_SHEET_KINDS` (familles d'`OPTIONS` dont les fiches viennent en story 19b : `embedding`, `vector_store`, `vector_search`, `lexical_search`, `fusion`, `rerank`, `generation` ; `context` est fiché depuis la story 7, ses six options depuis la story 10) ; modèles pydantic (`ArchitectureSheet`, `Axis`, `LocatedComponent`, réutilise `lab.SourceText`), chargement de `rag_sheets.yaml`, validation (sept axes exacts, niveaux contre `RISKS`, `regulatory` sans niveau, classes de localisation, `demo` parmi les trois ids, `story` requis hors `PRESETS`, au moins une source), `listing(lang)`, `component(lang, key)`, `architecture(lang, id)` ; jointure via `rag.erasure.load_erasure(lang)`.
- `src/wavestack/session/app_session.py` (fin de section RAG, après `rag_lab_access`) : `rag_lab_sheets`, `rag_lab_sheet_component`, `rag_lab_sheet_architecture` (pures, sans entrée au Journal de sécurité).
- `src/wavestack/web/app.py` (après `/api/rag_lab/access`, `# V1.2 story 19`) : trois `GET` ; 404 sur id inconnu.
- `src/wavestack/web/static/rag-sheets.js` (code de l'onglet), `rag.html` (contenu du panneau `rag-panel-sheets`, `.rag-soon` passé en `hidden`), `rag.css` (ajouts).
- `content/rag_sheets.yaml` et `content/i18n/{en,de}/rag_sheets.yaml` (nouveaux).
- `tests/test_rag_sheets.py` (nouveau), `tools/e2e/run_e2e.py` (scénario `rag_lab_sheets` ajouté ; dans `_rag_lab_tabs`, la boucle `for tab in ("sheets",)` qui attend « à venir » dans `#rag-panel-sheets .rag-soon` est retirée et remplacée par une vérification que le panneau Fiches montre sa liste, seule modification d'un scénario existant), `tools/e2e/README.md`.

## Niveaux proposés (proposition, à relire par Anaël, voir Reports)

Exposition sur les axes à niveau (`L` low, `M` mid, `H` high). Localisation : `L` partout tant que tout tourne en local, le texte dit ce qui change avec un modèle cloud (`depends_on_provider`). Ce sont des **propositions** tirées de `architectures.md` et `attaques-et-conformite.md`, sans mesure ; le dev les écrit telles quelles, l'écran les marque « proposition, à relire ».

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
| graphrag | H | H | H (la maquette montre « moyen » : à trancher à la relecture) | H (relations empoisonnées) | M |
| llm_wiki | H | H | H | H | M |

## Tasks & Acceptance

- [ ] Rédiger `rag_sheets.yaml` ×3 (11 architectures × 5 blocs × 7 axes, textes de l'onglet).
- [ ] `rag/sheets.py`, session, points d'accès GET.
- [ ] `rag-sheets.js`, `rag.html`, `rag.css` ; `.rag-soon` du panneau Fiches en `hidden`.
- [ ] Tests (pytest, E2E), README E2E.

**Acceptance Criteria:**
1. Given `OPTIONS`, then ses familles sont exactement partagées entre `lab.SHEETED_KINDS` et `sheets.PENDING_SHEET_KINDS` (disjointes, union égale à `set(OPTIONS)` ; message d'échec qui nomme la famille), et la liste sert une fiche pour chaque `kind.option` des familles fichées (dérivé d'`OPTIONS` et de `SHEETED_KINDS`, jamais d'une liste écrite en dur).
2. Given les 11 ids de `architectures` de `rag_erasure.yaml`, then `rag_sheets.yaml` a exactement une fiche par id, dans les trois langues, et `set(lab.PRESETS)` est inclus dans cet ensemble (message d'échec qui nomme l'id manquant).
3. Given une fiche d'architecture, then elle a cinq blocs (usage, quand l'utiliser ou l'éviter, coût en B, U et Q en mots, littérature, banc) et exactement les sept axes `location`, `copies`, `erasure`, `rights`, `injection`, `traceability`, `regulatory` ; un axe manquant ou en trop échoue au chargement.
4. Given un axe autre que `regulatory`, then son `level` appartient à `mcp.policy.RISKS` (test qui compare à l'import, pas à une copie) ; `regulatory` avec un `level` est refusé.
5. Given l'axe `location`, then chaque composant porte une classe parmi `local`, `cloud_eu`, `secnumcloud`, `outside_eu`, `depends_on_provider` (autre valeur refusée) ; les données livrées n'utilisent que `local` et `depends_on_provider` (test) ; `generation` est `depends_on_provider` partout ; la fiche `crag` dit Jev propriétaire sans hébergement local.
6. Given les axes `erasure`, `rights`, `injection`, then leur `demo` vaut respectivement `rag-erasure-card`, `rag-access-card`, `rag-atk-title`, chaque id est présent dans `rag.html` (test qui lit le fichier), et les autres axes n'ont pas de `demo` ; la réponse de l'axe `erasure` porte les endroits de `rag_erasure.yaml` de la langue dont la liste `architectures` contient l'id, et son `update_text`.
7. Given les huit architectures hors `PRESETS`, then `available` est faux, `story` égale celle de `rag_erasure.yaml`, la fiche est complète, et l'écran affiche « architecture à venir dans l'atelier (story N) » ; pour dense, hybrid, rerank, `available` est vrai et `story` absent ; `available` égale aussi celui de `rag_erasure.yaml` (signal de mise à jour quand une story ajoute un préréglage).
8. Given le bloc « ce qu'a mesuré le banc », then `bench_text` est vide dans chaque fiche servie (architecture et composant) et l'écran affiche « Pas encore mesuré » (en et de traduits).
9. Given les sources des fiches d'architecture, then chaque fiche a au moins une source `https://` ; chaque id de `hypotheses` est une ligne du tableau de `litterature.md` (hors H8, H16, H17) ; pour chaque ligne, toute architecture que sa colonne « Fiches » nomme la déclare (table nom → id écrite dans le test, colonne lue du fichier) ; tous les liens Markdown de la ligne figurent dans `sources` avec le même libellé et la même URL ; aucune URL de `rag_sheets.yaml` n'est absente de `litterature.md` ; `literature_text` contient le mot d'état de chaque hypothèse ; `raptor` a un `no_source_text` non vide. Le test lit `litterature.md` et se saute avec un marqueur explicite si le dossier de specs est absent (précédent : `tests/test_recette_docs.py`).
10. Given les textes de `rag_sheets.yaml` ×3, then aucun ne contient une formule de conformité affirmée (motifs interdits, insensibles à la casse : fr « est conforme », « conforme au RGPD », « garantit la conformité », « assure la conformité » ; en « is compliant », « compliant with », « ensures compliance », « guarantees compliance » ; de « ist konform », « DSGVO-konform », « gewährleistet die Konformität », « garantiert die Konformität ») ; le bandeau « pas un avis juridique » est présent dans les trois langues, sur l'onglet et sur chaque fiche conformité (test de réponse et E2E).
11. Given les trois langues, then ids, niveaux, classes de localisation, `demo`, `story`, `hypotheses`, URL, nombres d'axes, de composants et de sources, placeholders sont identiques ; seuls les textes diffèrent ; aucune surcouche n'est absente.
12. Given `GET /api/rag_lab/sheets`, `.../component/{kind}.{option}`, `.../architecture/{id}`, then les réponses suivent la matrice ci-dessus, sans calcul, 404 sur id inconnu (dont un `kind.option` d'une famille en attente) ; aucune clé JSON ne correspond au motif `AVERAGE` de `tests/test_rag_evaluation.py` ni à un champ de score global (`score`, `total`, `overall`).
13. Given l'onglet Fiches ouvert sans réseau, sans modèle, sans index, then la liste, une fiche de composant et une fiche d'architecture (implémentée et à venir) s'affichent ; E2E : aucune requête hors `127.0.0.1`.
14. Given l'onglet, then les niveaux se lisent en mot (« faible », « moyen », « élevé » via `mcp.policy.risk.*`) dans une `status-chip`, avec la mention « proposition, à relire », pas par la couleur seule ; thèmes clair et sombre au contraste AA ; textes dessinés par `textContent`.
15. Given `rag-sheets.js` (déjà dans `OTHER_TABS` de `tests/test_rag_evaluation.py`), then `test_no_average_in_the_other_tabs_of_the_page` passe ; `renderTabs` ne lève pas d'erreur (le `.rag-soon` du panneau existe, `hidden`).
16. Given les stories 17 et 18, then leurs cartes, scénarios (`rag_lab_attack`, `rag_lab_rights`) et tests restent verts et inchangés ; aucun fichier de la liste Never n'est modifié (`git diff --stat` de la story).
17. Given une story ultérieure qui ajoute une famille à `OPTIONS` ou un préréglage à `PRESETS` sans fiche, then `tests/test_rag_sheets.py` échoue avec un message qui nomme la famille ou le préréglage ; une option ajoutée à une famille fichée fait déjà échouer le chargement de `rag_lab.yaml` (validation existante).
18. Given le lien d'un axe, then un clic ouvre l'onglet Attaquer (`#attack`) et amène la carte visée à l'écran avec le focus ; la page n'arrive pas sur Construire (E2E).

## Verification

- `uv run pytest -q --tb=short tests/test_rag_sheets.py tests/test_rag_lab.py tests/test_rag_lab_views.py tests/test_rag_evaluation.py tests/test_rag_erasure.py tests/test_rag_access.py tests/test_i18n.py tests/test_annex_language.py` -- vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag_lab_sheets,rag_lab_views,rag_lab_rights` -- vert, tranche courte.

## Plan de tests

- **pytest, `tests/test_rag_sheets.py`**, sans modèle ni réseau :
  - exhaustivité (critères 1, 2, 17) : partition des familles d'`OPTIONS` ; architectures dérivées de `rag_erasure.yaml` et de `PRESETS` ; message d'échec nommant l'élément manquant ; cas forgés (`OPTIONS` ou `PRESETS` augmentés par `monkeypatch`) qui font échouer la vérification ;
  - structure et validation (critères 3 à 5) : sept axes exacts, niveaux contre `RISKS`, `regulatory` sans niveau, classes de localisation, `story` requis hors `PRESETS` ; cas refusés au chargement (axe manquant, axe en trop, niveau inconnu, `level` sur `regulatory`, classe inconnue, `sources` vide, `demo` inconnu) ;
  - liens et cohérence avec la story 18 (critères 6, 7) : ids `demo` présents dans `rag.html`, endroits joints égaux à ceux de `rag_erasure.yaml` pour chaque id et langue, `available` et `story` égaux ;
  - sources (critère 9) : lecture du tableau de `litterature.md` (ids, colonne « Fiches », liens `[libellé](url)`, mot d'état) ; saut avec marqueur si le fichier est absent ;
  - motifs de conformité interdits, bandeau présent ×3 langues (critère 10) ;
  - parité fr, en, de (critère 11) ;
  - points d'accès par le client de test de `web/app.py` : GET, 404 (id inconnu, famille en attente), clés sans agrégat (critère 12).
- **E2E existant à relancer** : `rag_lab_views` (fonction `_rag_lab_tabs`) (sa vérification « à venir » de l'onglet Fiches est remplacée, voir Code Map).
- **pytest existants à relancer** : `test_rag_lab.py`, `test_rag_lab_views.py` (onglets), `test_rag_evaluation.py` (`OTHER_TABS`), `test_rag_erasure.py`, `test_rag_access.py`, `test_i18n.py`, `test_annex_language.py`.
- **E2E `rag_lab_sheets`** (aucun prérequis d'index) : ouvrir Fiches, voir la liste (14 composants fichés : `query`, `chunking`, `context` ; 11 architectures, mention des familles en attente), ouvrir `chunking.semantic` (cinq blocs, « Pas encore mesuré »), ouvrir `hybrid` (sept axes, niveaux en mot, mention « proposition, à relire », bandeau « pas un avis juridique »), suivre le lien de l'axe Droits jusqu'à `#rag-access-card` visible dans l'onglet Attaquer (critère 18), revenir, ouvrir `graphrag` (étiquette « à venir dans l'atelier (story 13) »), repasser en en puis de ; aucune requête hors `127.0.0.1`. Capture clair et sombre.

## Spec Change Log

- 2026-10-25 : création (phase 1, point de contrôle de spec).
- 2026-10-25 : point de contrôle de spec (reviewer). `rag_access.yaml` n'a pas d'architectures (critère 2 et axe Droits corrigés) ; endroits, `update_text`, libellé et `available` lus de la story 18 et de `PRESETS` au lieu d'être recopiés ; lien vers les cartes par `#attack` puis `scrollIntoView` (une ancre de carte ramenait sur Construire via `tabFromHash`) ; `.rag-soon` gardé `hidden` (`renderTabs` y écrit) ; `rag-sheets.js` déjà dans `OTHER_TABS` ; critère 9 rendu vérifiable (champ `hypotheses`, correspondance dérivée de la colonne « Fiches ») et CAP-17 « au moins une source » tenu par H12 sur toutes les fiches ; motifs interdits en et de explicités ; écart maquette (niveau réglementaire) consigné ; fiches de composant restantes reportées en story 19b ; critère 18 ajouté (lien) ; E2E `rag_lab_views` (`_rag_lab_tabs`) à adapter (attendait « à venir » sur Fiches) ; statut ready-for-dev.

## Décisions du point de contrôle

1. **Fiches de composant des autres familles** : reportées à la **story 19b « Fiches de composant des familles restantes (fin de CAP-17) »**. Motif : 13 fiches × 5 blocs × 3 langues (~200 textes) s'ajoutent aux ~400 textes des fiches d'architecture, doublent la relecture humaine du `done_checkpoint`, et `embedding.*` n'a aucune source dans `litterature.md` alors que `SheetText` exige une source (il faut soit une source primaire ouverte avec réseau, soit un `no_source_text` dans `SheetText`, décision de 19b). Cette story pose la partition `SHEETED_KINDS` / `PENDING_SHEET_KINDS` ; 19b vide `PENDING_SHEET_KINDS`, ce qui clôt CAP-17. Sources attendues en 19b : H1 (vector_search, lexical_search, fusion, rerank), H14 (vector_store), H9 (context), H10 (generation).
2. **RAPTOR** : pas d'identifiant arXiv ni d'URL de mémoire. La fiche cite H12 (au titre de la fiche conformité) et `no_source_text` dit qu'aucune source primaire sur RAPTOR n'a été ouverte. CRAG cite H7 et H12. Source primaire de RAPTOR : report à une session avec réseau.
3. **Axe « Cadre réglementaire »** : aucun niveau (validé au chargement), texte et questions seulement ; la ligne reste dans le tableau. Écart assumé avec la maquette (« moyen »).
4. **Lien « Fiche » du focus** : hors story (touche `rag.js`, partagé) ; report à une story ultérieure.
5. **Page Sécurité** : CAP-16 « mêmes données que la matrice » est tenu par le vocabulaire importé de `RISKS`, les libellés `mcp.policy.risk.*` et la puce `status-chip` ; pas de seconde matrice ni de lien ajouté sur la page Sécurité (`security.js` et `/api/security` ne bougent pas). Lecture à confirmer par Anaël au `done_checkpoint`.
6. **Localisation** : classes déclaratives, seulement `local` et `depends_on_provider` dans les données ; lecture réelle de `[[cloud.models]]` en report (attend un champ région ou qualification).
7. **Niveaux** : ne bloque pas la nuit. Le dev écrit les niveaux du tableau ci-dessus, affichés « proposition, à relire » ; la relecture d'Anaël est une vérification du `done_checkpoint` (Reports), après laquelle il retire ou garde la mention (`levels_note_text`).
8. **Coûts de remise en conformité** : en mots seulement, `update_text` de `rag_erasure.yaml` joint par la session, mention « pas encore mesuré » ; durée et coût mesurés après les stories 10 à 14.

## Reports

- Tâche humaine (Anaël), avant de déclarer la story finie (`done_checkpoint`) :
  - relire **tous les contenus de conformité** en fr, puis en et de : niveaux proposés des 11 × 5 axes (dont graphrag / Droits, H contre « moyen » dans la maquette), formulations de l'axe réglementaire (RGPD, AI Act, DORA, NIS2) ; aucune phrase ne doit se lire comme un avis juridique ni comme une conformité affirmée ; décider du sort de la mention « proposition, à relire » ;
  - vérifier chaque lien de littérature ouvert (états cohérents avec `litterature.md`) ;
  - confirmer la lecture de CAP-16 « mêmes données que la matrice des risques » (décision 5) ;
  - ouvrir l'onglet Fiches en fr, en, de, thèmes clair et sombre : liste, fiche de composant, fiche d'architecture implémentée et « à venir », lien vers les cartes Attaquer, niveaux lisibles sans la couleur, bandeau « pas un avis juridique ».
- Story 19b (à ajouter à `stories.yaml` et au run par l'orchestrateur) : fiches de composant `embedding.*`, `vector_store.*`, `vector_search.cosine`, `lexical_search.bm25`, `fusion.rrf`, `rerank.declared`, `context.excerpts`, `generation.*` ×3 langues, `SHEETED_KINDS` étendu, `PENDING_SHEET_KINDS` vidé ; décider `no_source_text` pour `SheetText` ou une source primaire ouverte pour les embeddings.
- Source primaire de RAPTOR : session avec réseau, source ouverte et lue, ajoutée à `litterature.md` puis à la fiche.
- Reprise après les stories 10 à 14 : brancher le bloc « ce qu'a mesuré le banc » dès que le projet de banc publie, reporter les coûts et durées de remise en conformité mesurés ; l'étiquette « à venir » tombe d'elle-même quand l'id entre dans `PRESETS` (mettre aussi `available` de `rag_erasure.yaml` à jour, le critère 7 le signale).
- Lecture réelle de la localisation depuis la configuration cloud : attend un champ région ou qualification (hors lot).
- Lien « Fiche » du focus vers la fiche du composant : story ultérieure.

## Revue

### Passe 1 (2026-10-25, SHA revu 52a673e)

Branche fusionnée avec `origin/integration/v1-2-atelier` (story 12.10, #113) avant la revue ; conflit sur la capture 57 résolu par celle de l'intégration. Écarts du texte gelé avec le code, consignés ici sans toucher l'intention : 14 fiches de composant (et non 8 : `context` est fiché depuis la story 7, six options depuis la story 10) ; `long_context` et `cag` sont dans `PRESETS` depuis la story 10, donc disponibles et sans `story`.

- Important · high · contrat 12.10 / 12.19 · corrigé : `long_context` et `cag` entrés dans `PRESETS` faisaient échouer le chargement de `rag_sheets.yaml` (22 tests rouges). `story: 10` retiré des deux fiches ×3 langues ; `rag_erasure.yaml` ×3 passé à `available: true` sans `story` ; `erasure.py` : un endroit construit garde sa story 10 quand son architecture est entrée dans l'atelier (validation assouplie, seul écart à la liste Never, imposé par le contrat) ; tests `test_rag_erasure.py` (IN_WORKSHOP, plus d'« à venir » sur la ligne source de `long_context`) et `test_rag_sheets.py` (story retirée sur `graphrag`) ajustés.
- Important · medium · E2E après fusion · corrigé : `rag_lab_sheets` et `_rag_lab_tabs` attendaient 23 entrées ; 25 après la story 10 (14 composants + 11 architectures). README E2E aligné.
- Important · medium · second avis · corrigé : l'accolade fermée après `#rag-case` réactive 70 règles qui n'étaient actives que dans `#rag-case` (imbrication CSS depuis la story 9). Seul conflit réel : la règle `.rag-badge` de la story 7 écrasait la bordure primaire de la story 4 sur tous les badges ; portée restreinte à `.rag-badge[data-state]` (états de passage, seuls à porter `data-state`). Les autres règles réactivées n'ont pas de doublon antérieur (script de comparaison des sélecteurs) ; captures 55 à 70 refaites.
- Pre-existing · medium · revue · reporté : l'accolade manquante de `#rag-case` (story 9, déjà sur `main` v1.4.0) a laissé les styles des stories 6 à 18 inactifs hors `#rag-case` ; corrigée ici pour l'intégration, `main` reste à corriger à la fusion V1.2.
- Nit · low · second avis · corrigé : `missing_sheets()` signale aussi une famille en attente absente d'`OPTIONS`.
- Nit · low · second avis · rejeté : `PENDING_SHEET_KINDS` en dur est exigé par la spec (constante vidée par la story 19b), la partition est testée dans les deux sens.
- Nit · low · second avis · corrigé : spec périmée (Code Map, plan E2E) mise en accord ; texte gelé laissé tel quel, écarts consignés ci-dessus.
- Nit · low · second avis · reporté : `load()` de `rag-sheets.js` n'affiche rien si `/api/rag_lab/sheets` échoue (pas de clé de texte hors du YAML servi) ; l'onglet réessaie à la réouverture. À traiter en 19b avec un texte `ui.yaml` ×3.
- Nit · low · second avis · rejeté : pas de test JS hors E2E, comme les autres onglets de l'atelier ; `rag_lab_sheets` couvre liste, fiches, lien, langues et contraste.
- Pre-existing · low · revue · reporté : `rag_lab_views` dépend de `rag_lab` (mode Composer mémorisé, `#rag-reset-chain` caché sinon), alors que le README dit « après `rag` et `rag_rerank` ».
- Complexité : 0 constat (contenu déclaré, lu à la requête, aucune structure qui grossit).

