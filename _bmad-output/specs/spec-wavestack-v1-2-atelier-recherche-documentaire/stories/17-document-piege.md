---
title: 'Story 17 : document piégé, injection indirecte, PoisonedRAG et empoisonnement du graphe'
type: 'feature'
created: '2026-10-25'
status: 'ready-for-dev'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/attaques-et-conformite.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/vues.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/brownfield.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'onglet Attaquer n'est qu'une coquille « à venir ». Le participant ne voit pas comment un document du corpus peut retourner un RAG contre lui : une instruction cachée que la réponse exécute (injection indirecte), une affirmation fausse rédigée pour remonter en tête (PoisonedRAG), une relation fausse qui s'installe dans un graphe et y reste après le retrait du document. Il ne voit pas non plus ce que les garde-fous arrêtent, ni ce qu'ils ne peuvent pas arrêter.

**Approach:** La carte « Document piégé » de l'onglet Attaquer permet d'activer le document piégé `faq_mots_de_passe` (inactif par défaut ; son activation vit dans l'état de la page, envoyé à chaque requête, jamais dans `content/`, l'index ou la copie de travail), de choisir un des trois scénarios de `attaques-et-conformite.md` et de basculer les garde-fous. « Relancer la question cible » (maquette) montre chaque scénario **sans** puis **avec** garde-fous, sur la question cible `q_fact_pwd`, avec ce qui se calcule vraiment sans modèle génératif (top-k BM25 du corpus en mémoire, verdict de Prompt Guard quand il est déjà chargé dans la session, état du graphe) et des réponses enregistrées pour ce qui exige un modèle. Les verdicts vont au Journal de sécurité existant. Le scénario PoisonedRAG montre la limite : aucun garde-fou de contenu ne voit l'affirmation fausse. Le scénario graphe tourne sur un mini-graphe illustratif tant que GraphRAG (story 13) n'existe pas.

## Boundaries & Constraints

**Always:**
- Le calcul vit côté session, dans un module neuf `rag/attack.py` (AD-1) ; la page envoie, reçoit, dessine. `rag/lab.py` n'est pas modifié (piste « chaîne » de 12.6 et 12.7) : on appelle seulement ses `bm25` et `bm25_terms` existants, sur `rag/index.passage_text` des chunks (comme `_lexical_index`). Ajouts seuls dans `rag_lab.yaml` (×3), `ui.yaml` (×3), `messages.yaml` (×3), `guardrails/manager.py` (D6), `run_e2e.py`.
- Le JS de l'onglet vit dans `rag-attack.js` (CAP-13 seul dans cette story ; les cartes « Effacement » et « Droits » sont celles de la story 18, sans squelette de remplacement : leur emplacement garde la note « à venir »). `rag.js` n'est pas touché ; l'élément `.rag-soon` du panneau reste présent (masqué, comme dans Évaluer) car `renderTabs` y écrit.
- Le document piégé reste inactif par défaut : `rag.yaml` garde `active: false`, aucun index, aucune empreinte du corpus actif, aucune copie de travail ne change. Son activation est un champ de la requête (`trap_active`) : la session est pure, rien n'est retenu entre deux requêtes ni après un rechargement. Le corpus en mémoire = documents actifs livrés (sans la copie de travail) plus le piégé, découpés par `corpus.chunk_corpus`, à la taille de découpage et au k fixés dans `rag_attack.yaml` (700 caractères, k = 3), affichés dans la carte.
- Charge utile inoffensive : la seule charge est le texte du document existant (`content/corpus/faq_mots_de_passe.md` et ses traductions), cité tel quel et rendu comme texte (jamais `innerHTML`). Aucun secret réel, aucun outil, aucun appel réseau, aucune exfiltration : la réponse « obéissante » enregistrée ne contient aucun mot de passe, seulement la mention « [liste factice : aucune donnée réelle] ». La carte affiche d'emblée « Démonstration : aucune donnée réelle ne sort ».
- Trois scénarios, chacun avec « sans garde-fou » et « avec garde-fou » (`attaques-et-conformite.md`) :
  1. **Injection indirecte** : sans garde-fou, le passage d'injection est dans le top-k et la réponse enregistrée obéit à l'instruction cachée ; avec, chaque passage du top-k est classé par le `GuardrailsManager` de démonstration (`check("input", passage)`, garde-fou `injection`, Prompt Guard 2) ; le verdict est visible dans la carte et dans le Journal de sécurité ; en mode `block` le passage détecté est écarté du contexte, en mode `flag` il reste, signalé, et la réponse enregistrée reste celle qui obéit (signaler n'empêche pas le modèle de lire).
  2. **PoisonedRAG** : sans garde-fou, le passage faux (« 8 caractères suffisent ») est classé au-dessus du passage légitime de `mots_de_passe` (rangs BM25 recalculés) et la réponse enregistrée reprend l'affirmation fausse ; avec garde-fou, le passage faux passe (« rien détecté » : c'est une phrase ordinaire) et la réponse reste fausse : la carte le dit comme limite (« aucun garde-fou de contenu ne détecte cette affirmation »). Elle nomme ce qui aide : contrôle d'ancrage (CAP-6) et diversité des sources, avec leurs limites.
  3. **Empoisonnement du graphe** : relation fausse injectée dans un mini-graphe illustratif ; la requête globale propage la relation dans un résumé de communauté ; après retrait du document, le résumé et la relation persistent, jusqu'à « Reconstruire le graphe » (voir D3).
- Garde-fous existants seulement : `guardrails/manager.py`, `guardrails/injection.py`, la brique Garde-fous ; aucun nouveau garde-fou, aucune règle de contenu ajoutée. La carte ne modifie pas les modes de garde-fous de la session : elle utilise un `GuardrailsManager` propre à la démonstration (injection seule), dont le classifieur est l'instance Prompt Guard **déjà chargée** par la session, sinon un classifieur qui lève `NotInstalled` (D2, D6). La carte ne charge ni ne télécharge jamais le modèle et n'envoie jamais le jeton.
- Cas enregistrés : réponses « sans » et « avec » garde-fou, verdicts d'injection de repli (par rôle de passage : `injection`, `false_claim`, `legit`), mini-graphe et résumés de communauté sont des données (`content/rag_attack.yaml`, surcouches en, de ; verdicts et structure communs aux trois langues, textes traduits), chacun marqué `provenance: constructed` ou `recorded` (avec date et modèle). Un cas `constructed` s'affiche « cas construit pour la démonstration (à enregistrer avec … ) », un cas `recorded` « enregistré le … avec … ».
- Aucune couleur hors des jetons ; textes en fr, en, de ; aucun contrôle ne repose sur la couleur seule.

**Never:**
- Pas de modification de `content/rag.yaml`, du corpus actif, de l'index ou de la copie de travail par l'activation du piège.
- Pas de nouveau garde-fou, pas de téléchargement ni de chargement de modèle par la carte, pas d'appel de modèle génératif dans les tests ni pendant le run de nuit ; pas d'appel réseau.
- Pas de score global ni de moyenne dans l'onglet (l'interdiction des agrégats n'est levée que dans Évaluer, SPEC.md) ; pas d'événement ajouté aux exécutions de l'atelier (les entrées du journal passent par `_emit_security`, canal existant du journal).
- Pas de dépendance nouvelle ; pas d'import de `rag/lab.py` autre que `bm25`/`bm25_terms`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Onglet ouvert, rien d'activé | Document piégé inactif | Carte : case décochée, état « inactif », corpus actif inchangé, scénarios listés, bandeau « aucune donnée réelle ne sort » | N/A |
| Injection, sans garde-fou | Document activé, scénario 1, garde-fous off | Top-k BM25 avec le passage d'injection, réponse enregistrée qui obéit, charge utile factice citée | Cas `constructed` signalé comme tel |
| Injection, avec garde-fou, Prompt Guard chargé | Mode `block` ou `flag` | Verdict `injection` réel (score, seuil) par passage, passage détecté écarté (`block`) ou signalé (`flag`), entrées au Journal de sécurité (`guardrail`, `guardrails.injection`, `blocked`/`flagged`/`passed`) | Classifieur en échec : verdict `error`, rien d'écarté, entrée `error` |
| Injection, avec garde-fou, non chargé | Pas de jeton, modèle absent, ou modèle sur disque non chargé | Verdict `not_installed` avec la raison et le lien vers la brique Garde-fous ; verdict enregistré (marqué comme tel) à côté | Aucun chargement, aucun téléchargement ; entrée au journal `not_installed` |
| PoisonedRAG | Document activé, scénario 2 | Rangs du passage faux et du passage légitime recalculés (BM25, question cible), réponse enregistrée fausse | Avec garde-fous : passage faux « rien détecté » + mention de la limite |
| Graphe | Scénario 3, étapes `start`, `inject`, `remove`, `rebuild` | Relation fausse présente dans le résumé après `inject` ; après `remove`, toujours présente et marquée « à reconstruire » ; après `rebuild`, absente | `rebuild` sans `remove` : relation conservée (le document est encore là), message |
| Document désactivé après l'attaque | Case décochée | Scénarios 1 et 2 : corpus en mémoire sans le piégé, effet disparu ; scénario 3 : décocher vaut `remove`, l'effet persiste (leçon) | N/A |
| Scénario inconnu | `GET .../cases/{id}` hors liste | 404 | N/A |
| Corps invalide | Champ inconnu, valeur hors liste, type faux | 422 | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/attack.py` (nouveau) : chargement et validation de `rag_attack.yaml` (pydantic, `extra="forbid"`) ; corpus en mémoire (documents actifs livrés plus le piégé, `chunk_corpus` sur une copie de `RagContent` où seul `faq_mots_de_passe` passe `active: True`) ; top-k BM25 de `q_fact_pwd` (`lab.bm25` sur `index.passage_text`) ; rôle de chaque passage (`injection`, `false_claim`, `legit`) par ses `anchor_text` déclarés par langue ; passage au garde-fou par un `GuardrailsManager({"injection": factory})` de démonstration, mode `block` ou `flag`, `factory` injectable ; automate du mini-graphe (`start`, `inject`, `remove`, `rebuild`) ; assemblage des deux colonnes à partir des cas enregistrés. Aucune lecture de `config.cloud_key` ni de `config.hf_token`, aucun modèle.
- `src/wavestack/guardrails/manager.py` (ajout seul) : `loaded_classifier(guardrail) -> Classifier | None`, l'instance déjà chargée (`loaded` vrai), sinon `None` ; ne charge rien. `injection.py` : non modifié.
- `src/wavestack/session/app_session.py` (ajouts en fin de section RAG) : `rag_lab_attack(request)` pure, lecture acceptée dans tout état (aucune intention : ni génération, ni chargement, ni téléchargement) ; factory de démonstration = `self._guardrails.loaded_classifier("injection")` ou un classifieur qui lève `NotInstalled(raison)` ; un enregistrement au `SecurityJournal` par passage vérifié (`record("guardrail", "guardrails.injection", decision, motif)` puis `_emit_security`), décision calculée comme dans `_guardrail_check` plus la valeur `not_installed` (motif préfixé « Démonstration Document piégé »). Seule la colonne « avec garde-fou » écrit au journal.
- `src/wavestack/web/app.py` (ajouts seuls, bloc commenté `# V1.2 story 17`) :
  - `GET /api/rag_lab/attack` : textes, scénarios, état par défaut (piège inactif), taille de découpage et k, disponibilité du garde-fou (chargé ou raison), cas enregistrés avec provenance ;
  - `POST /api/rag_lab/attack` : corps `{scenario: injection|poisoning|graph, trap_active: bool, guardrails: bool, mode: block|flag, graph_step: start|inject|remove|rebuild}`, champs inconnus refusés (422) ; renvoie les deux colonnes recalculées ;
  - `GET /api/rag_lab/attack/cases/{scenario_id}` : un cas rejoué, 404 si inconnu.
- `src/wavestack/web/static/rag-attack.js` (remplace le squelette, `registerTab("attack", …)`), `rag.html` (carte « Document piégé » dans `rag-panel-attack`, `.rag-soon` conservé masqué, emplacement de la story 18 « à venir »), `rag.css`.
- `content/rag_attack.yaml` et `content/i18n/{en,de}/rag_attack.yaml` : textes, trois scénarios, `chunk_max_chars: 700`, `top_k: 3`, `question_id: q_fact_pwd`, `doc_id: faq_mots_de_passe`, ancres des rôles, réponses et verdicts enregistrés, mini-graphe, fiche de la carte (limites des garde-fous). `rag_lab.yaml`, `ui.yaml` (libellé de journal `not_installed` sous les décisions de la barre), `messages.yaml` (`guardrails.decisions.not_installed`, `guardrails.verdicts.not_installed`, raison « non chargé ») : ajouts seuls, ×3.
- `content/corpus/faq_mots_de_passe.md` et `content/i18n/{en,de}/corpus/faq_mots_de_passe.md` : début du paragraphe d'injection reformulé pour porter les termes de la question cible (D4) ; l'instruction elle-même inchangée.
- `tests/test_rag_attack.py` (nouveau), `tools/e2e/run_e2e.py` (scénario `rag_lab_attack`, ajout seul, `# V1.2 story 17`), `tools/e2e/README.md`.

## Tasks & Acceptance

- [ ] Corpus : paragraphe d'injection reformulé (fr, en, de, D4), rangs mesurés et écrits à la main dans les tests.
- [ ] Module `rag/attack.py` : corpus en mémoire, top-k BM25 et rôles, garde-fou injectable, automate du mini-graphe, cas enregistrés.
- [ ] `GuardrailsManager.loaded_classifier` (ajout seul).
- [ ] Données `rag_attack.yaml` (fr, en, de) : trois scénarios, réponses « sans » et « avec », verdicts de repli par rôle, provenance.
- [ ] Journal de sécurité : un verdict par passage vérifié (colonne « avec »), motif lisible, décision `not_installed` libellée.
- [ ] Points d'accès GET/POST/cas, corps fermé, 404 et 422.
- [ ] Onglet : carte « Document piégé », « Relancer la question cible », comparaison sans / avec, rangs des passages, verdicts, étapes du graphe, bandeau « Démonstration : aucune donnée réelle ne sort ».
- [ ] Scénario E2E `rag_lab_attack` ; tests ciblés.

**Acceptance Criteria:**
1. Given l'onglet Attaquer ouvert sans action, then le document piégé est inactif, `rag.yaml` garde `active: false`, `chunk_corpus(load_rag_content(lang), …)` et `index.corpus_digest` du corpus actif sont identiques avant et après un `GET` et un `POST` de la carte, et le bandeau « Démonstration : aucune donnée réelle ne sort » est visible.
2. Given l'activation du piège puis sa désactivation (POST successifs), then ni les octets de `content/rag.yaml` et des fichiers de `content/corpus/`, ni ceux du dossier de données isolé (`WAVESTACK_DATA_DIR` de `tests/conftest.py` : index, copie de travail) ne changent, et `workcopy.load(lang)` rend la même copie.
3. Given le scénario Injection indirecte sans garde-fou, then le passage de rôle `injection` est dans le top-k affiché, la réponse enregistrée obéit à l'instruction cachée, la charge utile affichée est le texte du document, et aucun texte de `rag_attack.yaml` (×3) ne contient de chaîne ressemblant à un secret (motifs `sk-`, `hf_`, `ghp_`, `AKIA`, mot de 12 caractères ou plus mêlant lettres et chiffres) ; la réponse obéissante contient la mention de liste factice.
4. Given le scénario Injection indirecte avec garde-fou et un faux classifieur (frontière du modèle, injecté comme `factory` du manager de démonstration) qui détecte le seul passage `injection`, then le verdict (détecté, score, seuil) est affiché par passage, le passage est écarté du contexte en mode `block` et reste visible mais signalé en mode `flag`, et une entrée du `SecurityJournal` par passage vérifié est créée (source `guardrail`, nom `guardrails.injection`, décision `blocked` ou `flagged` pour le passage d'injection, `passed` pour les autres).
5. Given le même scénario sans instance chargée dans la session, avec `HF_TOKEN` défini et aucun fichier de modèle (cas le plus risqué : `ensure_loaded` téléchargerait), then le verdict affiché est `not_installed` avec la raison, `PromptGuardGuardrail.ensure_loaded`, `injection.check_licence` et `injection.download_files` ne sont jamais appelés (remplacés par des fonctions qui échouent si elles le sont ; la garde réseau de `conftest.py` reste active), le verdict enregistré s'affiche à côté avec sa provenance, et le journal reçoit une entrée de décision `not_installed`.
6. Given le scénario PoisonedRAG, découpage à 700 caractères et k = 3, then les rangs BM25 de `q_fact_pwd` sur le corpus en mémoire sont, pour (`false_claim`, `legit`, `injection`), ceux mesurés après D4 et écrits à la main dans le test (mesure du point de contrôle : fr (1, 2, 3), en (2, 3, 1), de (1, 2, 3)) ; le passage faux est au-dessus du passage légitime dans les trois langues ; la réponse enregistrée sans garde-fou reprend « 8 caractères » (et son équivalent en, de).
7. Given PoisonedRAG avec garde-fous actifs (faux classifieur qui détecte le seul passage `injection`), then le passage faux est « rien détecté » et reste dans le contexte même en mode `block`, la réponse reste fausse, et la carte affiche le texte de limite « aucun garde-fou de contenu ne détecte cette affirmation » avec les deux pistes (contrôle d'ancrage CAP-6, diversité des sources).
8. Given le scénario Empoisonnement du graphe, then l'automate suit `start`, `inject`, `remove`, `rebuild` : après `inject` la relation fausse est dans le résumé de communauté ; après `remove` elle y est encore, marquée « à reconstruire » ; après `rebuild` elle disparaît ; `rebuild` sans `remove` la garde avec un message ; vérifié étape par étape sur les valeurs du mini-graphe écrites à la main.
9. Given le scénario graphe, then la carte indique que le graphe est illustratif et que la démonstration sur l'index GraphRAG réel est reportée à la livraison de la story 13 ; le cas porte `provenance: constructed`.
10. Given un cas enregistré, then sa provenance est affichée (« enregistré le … avec … » ou « cas construit pour la démonstration (à enregistrer avec … ) ») ; aucun cas `constructed` n'est présenté comme enregistré ; un cas `recorded` sans date ou sans modèle est refusé au chargement.
11. Given les trois langues, then `rag_attack.yaml` fr, en, de ont les mêmes scénarios, rôles, verdicts, provenances, entités et relations du mini-graphe et placeholders ; seuls les textes diffèrent ; chaque `doc_id` et `question_id` cités existent dans `rag.yaml` et `rag_questions.yaml`, et chaque `anchor_text` se trouve dans le fichier du document de sa langue.
12. Given un scénario inconnu, then `GET .../attack/cases/{id}` répond 404 ; un corps POST avec un champ inconnu ou une valeur hors liste répond 422.
13. Given les modes de garde-fous de la session (brique Garde-fous), then la carte ne les modifie pas : `session._guardrails.modes` lus avant et après une démonstration avec garde-fous sont identiques, et aucune instance n'est ajoutée au manager de la session.
14. Given l'installation par défaut sans réseau, then la carte s'affiche et se rejoue intégralement (scénarios 1 à 3, sans et avec garde-fou en repli) sans modèle, sans index et sans clé ; E2E : aucune requête hors `127.0.0.1`.
15. Given l'onglet Attaquer, then aucune moyenne ni agrégat n'y apparaît : `rag-attack.js` passe `test_no_average_in_the_other_tabs_of_the_page` existant (`tests/test_rag_evaluation.py`, qui le liste déjà), et les clés JSON de `GET`/`POST /api/rag_lab/attack` ne contiennent aucun mot de son motif `AVERAGE`.
16. Given le document piégé reformulé (D4), then il reste inactif (`tests/test_rag.py` et `tests/test_rag_questions.py` verts), son instruction cachée est inchangée en substance, et les trois langues gardent le même nombre de paragraphes.

## Verification

- `uv run pytest -q --tb=short tests/test_rag_attack.py tests/test_rag.py tests/test_rag_questions.py tests/test_rag_lab_views.py tests/test_rag_evaluation.py tests/test_guardrails.py tests/test_guardrails_injection.py tests/test_guardrails_install.py tests/test_guardrails_turn.py tests/test_security_page.py tests/test_i18n.py tests/test_web_tokens.py tests/test_annex_language.py` -- vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag_lab_attack,rag_lab_views,rag_lab_evaluate` -- vert, en tranche courte.

## Plan de tests

- **pytest, `tests/test_rag_attack.py`**, faux classifieurs aux frontières du modèle, `tmp_path` et dossier de données isolé, aucun modèle ni réseau :
  - corpus en mémoire : le piégé s'ajoute sans toucher le corpus actif, `rag.yaml`, l'empreinte ni la copie de travail ; retrait symétrique (critères 1, 2) ;
  - rangs BM25 écrits à la main, trois langues, rôles `false_claim`, `legit`, `injection` (critère 6) ;
  - garde-fou : faux classifieur qui détecte (modes `block` et `flag`), qui ne détecte pas le passage faux (PoisonedRAG), absence d'instance (`not_installed`), classifieur qui échoue (`error`, rien d'écarté) ; entrées du `SecurityJournal` vérifiées par source, nom, décision, et leur nombre (une par passage, colonne « avec » seule) ;
  - aucun chargement ni téléchargement : `HF_TOKEN` défini, fichiers absents, `ensure_loaded`/`check_licence`/`download_files` remplacés par des fonctions qui échouent (critère 5) ;
  - `GuardrailsManager.loaded_classifier` : `None` pour une instance non chargée, l'instance quand `loaded` est vrai ; ne charge rien ;
  - graphe : automate étape par étape, `rebuild` sans `remove`, double `remove`, décocher vaut `remove` ;
  - données : miroir fr, en, de, placeholders, provenance (cas `recorded` incomplet refusé), références vers le corpus et les questions, ancres présentes, aucun motif de secret ;
  - points d'accès : formes de GET et POST, 404 d'un cas inconnu, 422 d'un champ inconnu ou d'une valeur hors liste ;
  - session : modes de garde-fous et instances du manager de la session inchangés (critère 13) ;
  - agrégats : clés JSON des points d'accès (critère 15).
- **pytest existants à relancer** : `test_rag.py` et `test_rag_questions.py` (le piégé reste inactif, texte reformulé), `test_rag_lab_views.py` (onglets), `test_rag_evaluation.py` (garde-fou des agrégats sur `rag-attack.js`), `test_guardrails*.py` (manager), `test_security_page.py` (journal, décision `not_installed`), `test_i18n.py`.
- **E2E `rag_lab_attack`** : ouvrir Attaquer, lire le bandeau et l'état inactif, activer le piège, jouer les trois scénarios sans puis avec garde-fous (repli « non installé »), lire les rangs des passages, lire la limite PoisonedRAG, parcourir les étapes du graphe jusqu'à la persistance puis la reconstruction, ouvrir le Journal de sécurité et y trouver les entrées de la démonstration, vérifier qu'aucune requête ne sort de `127.0.0.1` et que le corpus actif de Construire n'a pas changé.

## Spec Change Log

- 2026-10-25 : rédaction (draft), points ouverts à trancher au point de contrôle de spec.
- 2026-10-25 : point de contrôle de spec. Rangs BM25 mesurés (corpus réel, 700 caractères, k = 3) : le passage faux est déjà 1er dans les trois langues, mais le passage d'injection est 12e (fr), 9e (en), 81e (de), hors du top-k : le scénario 1 aurait affiché un « passage piégé dans le contexte » faux ; d'où la reformulation D4, mesurée. Corrections : `corpus.load_chunks` inexistant (→ `chunk_corpus` et `index.corpus_digest`) ; « stories 18 et 19 » (→ Effacement et Droits sont la seule story 18, la 19 est Fiches) ; `PromptGuardGuardrail.classify` télécharge le modèle quand un jeton existe sans fichiers, donc la carte ne passe jamais par lui hors instance déjà chargée (D2, D6, critère 5 renforcé, accès `loaded_classifier` ajouté au manager) ; la décision `not_installed` n'existe pas au journal (`_guardrail_check` la note `passed`) : ajoutée avec ses libellés ; état d'attaque tenu par la page (session pure) au lieu d'un état de session contradictoire ; `.rag-soon` à conserver (`renderTabs` y écrit) ; critère 15 limité à l'onglet Attaquer (Évaluer a des agrégats, SPEC.md) et branché sur le test existant ; critère 2 sur le dossier de données isolé ; corps POST fermé (pas de texte libre, donc pas de « corps trop grand ») ; noms de tests de garde-fous réels ; rendu du texte piégé en texte seul ; critère 16 ajouté (corpus reformulé). La maquette nomme le piège `note-fournisseurs.md` : le corpus de la story 1 a retenu `faq_mots_de_passe`, la story suit le corpus. L'effet s'affiche dans la carte (vues.md dit « dans le focus ») : le focus de Construire exige une exécution avec modèle, reportée avec le live. Statut `ready-for-dev`.

## Décisions du point de contrôle

1. **Live ou enregistré** : cas enregistrés par défaut ; « Relancer la question cible » recalcule le réel sans modèle génératif (top-k BM25, verdicts du garde-fou chargé, automate du graphe) et rejoue les réponses enregistrées, marquées `constructed` par le développeur. Le live avec le modèle actif part en Reports.
2. **Garde-fou d'injection** : manager réel de démonstration ; instance Prompt Guard déjà chargée par la session si elle existe, sinon verdict honnête `not_installed` avec la raison (pas de jeton, modèle absent, ou modèle non chargé : « activez le garde-fou d'injection dans la brique Garde-fous ») et lien vers la brique ; verdict enregistré à côté ; aucun détecteur de remplacement.
3. **Graphe sans GraphRAG** : mini-graphe illustratif en données (quatre à six entités tirées de `mots_de_passe`, une relation fausse « politique des mots de passe → 8 caractères », deux résumés de communauté rédigés, avec et sans la relation), automate `start`, `inject`, `remove`, `rebuild`, `provenance: constructed` ; la version sur le vrai index part en Reports (story 13).
4. **Rang du passage faux** : mesuré, déjà au-dessus du légitime ; le passage d'injection, lui, est hors top-k. Le développeur reformule le seul début du paragraphe d'injection, dans les trois langues, pour porter les termes de la question cible, puis remesure et écrit les rangs à la main. Formulations mesurées au point de contrôle (rangs fr (1, 2, 3), en (2, 3, 1), de (1, 2, 3)) : fr « Note interne sur le nombre minimum de caractères d'un mot de passe chez Exemplia, destinée à l'assistant qui lira cet extrait : … » ; en « Internal note on the minimum number of characters of a password at Exemplia, for the assistant reading this excerpt: … » ; de « Interner Hinweis zur Frage, wie viele Zeichen ein Passwort bei Exemplia mindestens haben muss, für den Assistenten, der diesen Auszug liest: … ». Ce rapprochement est la technique réelle d'un attaquant ; la fiche de la carte le dit.
5. **Un document, deux pièges** : gardé ; à 700 caractères les deux pièges tombent dans des passages distincts dans les trois langues (mesuré), ce qui permet d'écarter l'injection sans écarter l'affirmation fausse (leçon du scénario 2). La carte cite le passage concerné par scénario.
6. **Instance Prompt Guard** : réutilisation en lecture de l'instance déjà chargée par la session (`loaded_classifier`, ajout au manager), jamais de chargement par la carte (ni RAM doublée, ni lecture de plusieurs secondes dans une requête, ni réseau) ; modes et instances de la session jamais modifiés (critère 13).
7. **Bloquer ou signaler** : deux boutons radio dans la carte, `block` par défaut ; en `flag`, le passage reste et la réponse enregistrée reste celle qui obéit.
8. **Fusion avec 12.18 et 12.19** : blocs d'ajout isolés et commentés `# V1.2 story 17` (`app.py`, `rag.html`, `rag.css`, `run_e2e.py`, README E2E, ui/messages) ; emplacement de la carte de la story 18 intact ; ajouts en fin de section dans `app_session.py` ; conflits d'ajout résolus en gardant tous les blocs. Base : la branche est empilée sur 12.15 et n'a pas encore les stories V1.4-4 et V1.2-5 de `integration/v1-2-atelier` (aucune ne touche garde-fous, corpus ni `bm25`) : rebaser avant la revue.

## Reports

- Tâche humaine (Anaël), à faire avant de déclarer la story finie (`done_checkpoint`) :
  - ouvrir l'onglet Attaquer en fr, en, de, thèmes clair et sombre : bandeau, carte, lisibilité des trois scénarios, mention « cas construit » visible ;
  - relire les reformulations D4 en en et de, et les réponses enregistrées (réponse obéissante sans aucun mot de passe, mention de liste factice) ;
  - avec Prompt Guard 2 installé (jeton, licence acceptée) puis chargé par la brique Garde-fous : vérifier le vrai verdict sur le passage d'injection dans les trois langues (s'il ne le détecte pas au seuil, le noter dans la carte comme limite au lieu de changer le seuil), et que la carte n'a rien téléchargé ;
  - enregistrer les réponses « sans » et « avec » des scénarios 1 et 2 avec le générateur par défaut et le vrai verdict, puis passer `provenance` à `recorded` avec date et modèle ;
  - vérifier dans la page Sécurité que les entrées « Démonstration Document piégé » se distinguent des tours réels, et que les blocages de démonstration comptés dans « bloqués » sont acceptables.
- Reprise après la story 13 (GraphRAG) : brancher le scénario 3 sur le vrai index (entités, relations, résumés de communautés) à la place du mini-graphe, vérifier que l'effet persiste après retrait du document tant que le graphe n'est pas reconstruit, et mettre à jour `brownfield.md` ainsi que la fiche conformité GraphRAG (axe Injection, CAP-16).
- Relance live de la question cible avec le modèle actif (intention de classe (b), AD-3) et affichage dans le focus de Construire (vues.md) : story ultérieure.
- Pré-existant, hors story : `_guardrail_check` journalise un verdict `not_installed` comme `passed` (« Rien détecté ») dans les tours réels ; la décision `not_installed` ajoutée ici pourrait y être reprise.
