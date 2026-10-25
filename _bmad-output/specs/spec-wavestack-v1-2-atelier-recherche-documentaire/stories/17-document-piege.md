---
title: 'Story 17 : document piégé, injection indirecte, PoisonedRAG et empoisonnement du graphe'
type: 'feature'
created: '2026-10-25'
status: 'draft'
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

**Approach:** La carte « Document piégé » de l'onglet Attaquer permet d'activer le document piégé `faq_mots_de_passe` (inactif par défaut, dans l'état de la page et de la session, jamais dans `content/` ni dans la copie de travail), de choisir un des trois scénarios de `attaques-et-conformite.md` et de basculer les garde-fous. Chaque scénario s'affiche **sans** puis **avec** garde-fous, sur la question cible `q_fact_pwd`, avec ce qui se calcule vraiment sans modèle (rang BM25 du passage piégé, verdict du garde-fou d'injection quand il est installé, état du graphe) et des réponses enregistrées pour ce qui exige un modèle. Les verdicts vont au Journal de sécurité existant. Le scénario PoisonedRAG montre la limite : aucun garde-fou de contenu ne voit l'affirmation fausse. Le scénario graphe tourne sur un mini-graphe illustratif tant que GraphRAG (story 13) n'existe pas.

## Boundaries & Constraints

**Always:**
- Le calcul vit côté session, dans un module neuf `rag/attack.py` (AD-1) ; la page envoie, reçoit, dessine. `rag/lab.py` n'est pas modifié (piste « chaîne » de 12.6 et 12.7) : on appelle seulement son `bm25` et `bm25_terms` existants. Ajouts seuls dans `rag_lab.yaml` (×3), `ui.yaml`, `run_e2e.py`.
- Le JS de l'onglet vit dans `rag-attack.js` (CAP-13 seul dans cette story ; les cartes « Effacement » et « Droits » restent pour les stories 18 et 19, sans squelette de remplacement : leurs emplacements portent la note « à venir »). `rag.js` n'est pas touché sauf ajout.
- Le document piégé reste inactif par défaut : `rag.yaml` garde `active: false`, aucun index, aucune empreinte du corpus actif, aucune copie de travail ne change. Son activation vit dans l'état d'attaque de la session (mémoire) et agit sur un corpus en mémoire (documents actifs plus le piégé), jamais sur le disque ni sur l'index de la page Construire.
- Charge utile inoffensive : la seule charge est le texte du document existant (`content/corpus/faq_mots_de_passe.md`, visible dans la page, citée telle quelle). Aucun secret réel, aucun outil, aucun appel réseau, aucune exfiltration : la « liste de mots de passe » qu'une réponse obéissante produit est factice, marquée comme telle, et vient des cas enregistrés. La page affiche d'emblée « Démonstration : aucune donnée réelle ne sort ».
- Trois scénarios, chacun avec « sans garde-fou » et « avec garde-fou » (`attaques-et-conformite.md`) :
  1. **Injection indirecte** : sans garde-fou, la réponse enregistrée obéit à l'instruction cachée ; avec, le passage piégé est classé par `GuardrailsManager.check("input", texte du passage)` (garde-fou `injection`, Prompt Guard 2), son verdict est visible dans la carte et dans le Journal de sécurité, et le passage est écarté du contexte quand le mode est `block`.
  2. **PoisonedRAG** : sans garde-fou, le passage faux (« 8 caractères suffisent ») remonte en tête (rang BM25 recalculé) et la réponse enregistrée reprend l'affirmation fausse ; avec garde-fou, **aucun** verdict ne se déclenche (le texte est une phrase ordinaire) et la réponse reste fausse : la carte le dit comme limite (« aucun garde-fou de contenu ne détecte cette affirmation »). Elle nomme ce qui aide : contrôle d'ancrage (CAP-6) et diversité des sources, avec leurs limites.
  3. **Empoisonnement du graphe** : relation fausse injectée dans un mini-graphe illustratif ; la requête globale propage la relation dans un résumé de communauté ; après retrait du document, le résumé et la relation persistent, jusqu'à « Reconstruire le graphe » (voir D3).
- Garde-fous existants seulement : `guardrails/manager.py`, `guardrails/injection.py`, la section « Garde-fous » de la page ; aucun nouveau garde-fou, aucune règle de contenu ajoutée. L'état des modes de garde-fous de la session n'est pas modifié par la carte : elle utilise un `GuardrailsManager` propre à la démonstration, sur le même `PromptGuardGuardrail`/même modèle chargé quand il l'est (voir D2).
- Cas enregistrés : réponses « sans garde-fou », verdict d'injection de repli, mini-graphe et résumés de communauté sont des données (`content/rag_attack.yaml`, surcouches en, de ; verdicts communs aux trois langues, textes traduits), chacun marqué `provenance: constructed` ou `recorded` avec date et modèle. Un cas `constructed` s'affiche « cas construit pour la démonstration (à enregistrer avec … ) », un cas `recorded` « enregistré le … avec … ».
- Aucune couleur hors des jetons ; textes en fr, en, de ; aucun contrôle ne repose sur la couleur seule.

**Never:**
- Pas de modification de `content/rag.yaml`, du corpus actif, de l'index ou de la copie de travail par l'activation du piège.
- Pas de nouveau garde-fou, pas de téléchargement de modèle ni d'appel de modèle génératif dans les tests ni pendant le run de nuit ; pas d'appel réseau (le jeton Hugging Face n'est jamais lu par cette carte : l'état « non installé » vient du manager).
- Pas de score global ni de moyenne dans l'onglet ; pas d'événement ajouté aux exécutions de l'atelier.
- Pas de dépendance nouvelle ; pas d'import de `rag/lab.py` autre que `bm25`/`bm25_terms`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Onglet ouvert, rien d'activé | Document piégé inactif | Carte : case décochée, état « inactif », corpus actif inchangé, scénarios listés | N/A |
| Injection, sans garde-fou | Document activé, scénario 1, garde-fous off | Passage piégé dans le contexte, réponse enregistrée qui obéit, charge utile factice citée | Cas `constructed` signalé comme tel |
| Injection, avec garde-fou, Prompt Guard installé | Mode `block` | Verdict `injection` réel (score, seuil) sur le passage, passage écarté, entrée au Journal de sécurité (`guardrail`, `blocked`) | N/A |
| Injection, avec garde-fou, non installé | Pas de jeton ou modèle absent | Verdict `not_installed` honnête, lien vers la brique Garde-fous, et le verdict enregistré (marqué « enregistré ») s'affiche à côté | Aucun téléchargement, entrée au journal « non installé » |
| PoisonedRAG | Document activé, scénario 2 | Rang du passage piégé et du passage légitime recalculés (BM25, question cible), réponse enregistrée fausse | Garde-fous : verdict « passé » (rien détecté) + mention de la limite |
| Graphe | Scénario 3, étapes « injecter », « retirer le document » | Relation fausse présente dans le résumé ; après retrait, toujours présente et marquée « à reconstruire » ; après reconstruction, absente | « Reconstruire » sans retrait préalable : sans effet, message |
| Document désactivé après l'attaque | Case décochée | Scénarios 1 et 2 : corpus en mémoire sans le piégé, effet disparu ; scénario 3 : l'effet persiste (leçon) | N/A |
| Scénario inconnu | Identifiant hors liste | 404 | N/A |
| Corps trop grand | Texte de requête hors borne | 422 | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/attack.py` (nouveau) : chargement de `rag_attack.yaml`, état d'attaque (activé, scénario, garde-fous, étape du graphe), corpus en mémoire (documents actifs plus piégé, découpés avec le découpeur existant de `rag/corpus.py`), rang BM25 de la question cible (appel de `lab.bm25`), passage au garde-fou (un `GuardrailsManager` de démonstration, classifieur injectable), automate du mini-graphe (injecter, résumer, retirer le document, reconstruire), assemblage de la réponse à partir du cas enregistré. Aucune lecture de `config.cloud_key`, aucun modèle.
- `src/wavestack/guardrails/manager.py`, `injection.py` : réutilisés, non modifiés. Si la page doit partager l'instance déjà chargée de Prompt Guard (RAM, 22 M), accès par `app_session` aux instances du manager de la session, en lecture (D2).
- `src/wavestack/session/app_session.py` (ajouts en fin de section RAG) : méthode `rag_lab_attack(request)` pure (état envoyé par la page, renvoyé recalculé), enregistrement des verdicts au `SecurityJournal` de la session (`record("guardrail", "guardrails.injection", decision, motif)`), comme `_guardrail_check`.
- `src/wavestack/web/app.py` (ajouts seuls, piste « onglets », bloc commenté `# V1.2 story 17`) :
  - `GET /api/rag_lab/attack` : textes, scénarios, état du document piégé, état des garde-fous (installé ou non), cas enregistrés avec provenance ;
  - `POST /api/rag_lab/attack` : corps borné `{scenario, trap_active, guardrails, graph_step}`, renvoie le résultat recalculé des deux colonnes « sans » et « avec » ; pas d'appel de modèle donc pas d'intention ;
  - `GET /api/rag_lab/attack/cases/{scenario_id}` : un cas rejoué, 404 si inconnu.
- `src/wavestack/web/static/rag-attack.js` (remplace le squelette, enregistre l'onglet), `rag.html` (carte « Document piégé » dans `rag-panel-attack`, emplacements des cartes 18 et 19 conservés), `rag.css`.
- `content/rag_attack.yaml` et `content/i18n/{en,de}/rag_attack.yaml` : textes, trois scénarios, réponses et verdicts enregistrés, mini-graphe, fiche de la carte (limites des garde-fous). `content/rag_lab.yaml` ×3 et `ui.yaml` : ajouts seuls (libellés de l'onglet), si nécessaire.
- `content/corpus/faq_mots_de_passe.md` (fr, en, de) : inchangé sauf si le rang BM25 du piège n'est pas 1 (D4).
- `tests/test_rag_attack.py` (nouveau), `tools/e2e/run_e2e.py` (scénario `rag_lab_attack`, ajout seul), `tools/e2e/README.md`.

## Tasks & Acceptance

- [ ] Module `rag/attack.py` : corpus en mémoire, rang BM25, garde-fou injectable, automate du mini-graphe, cas enregistrés.
- [ ] Données `rag_attack.yaml` (fr, en, de) : trois scénarios, réponses « sans » et « avec », verdicts de repli, provenance.
- [ ] Journal de sécurité : un verdict par passage vérifié, motif lisible.
- [ ] Points d'accès GET/POST/cas, formes bornées, 404 et 422.
- [ ] Onglet : carte « Document piégé », comparaison sans / avec, rang des passages, journal, étapes du graphe, bandeau « Démonstration : aucune donnée réelle ne sort ».
- [ ] Scénario E2E `rag_lab_attack` ; tests ciblés.

**Acceptance Criteria:**
1. Given l'onglet Attaquer ouvert sans action, then le document piégé est inactif, `rag.yaml` garde `active: false`, les chunks du corpus actif et l'empreinte du corpus sont identiques à ceux d'avant l'ouverture (test sur `corpus.load_chunks`), et le bandeau « Démonstration : aucune donnée réelle ne sort » est visible.
2. Given l'activation du piège puis sa désactivation, then ni `rag.yaml`, ni les fichiers de `content/`, ni la copie de travail, ni l'index de la page Construire ne changent (test sur les octets du dossier temporaire utilisé et sur `workcopy.load`).
3. Given le scénario Injection indirecte sans garde-fou, then le passage piégé est dans le contexte affiché, la réponse enregistrée obéit à l'instruction cachée, et la charge utile affichée est le texte du document, factice et bornée (aucune chaîne ne ressemble à un secret réel : test sur un motif de secrets).
4. Given le scénario Injection indirecte avec garde-fou et un faux classifieur (frontière du modèle, injecté dans le manager de démonstration) qui détecte, then le verdict `injection` (détecté, score, seuil) est affiché, le passage piégé est écarté du contexte en mode `block` et reste visible mais signalé en mode `flag`, et une entrée du `SecurityJournal` (source `guardrail`, nom `guardrails.injection`, décision `blocked` ou `flagged`) est créée.
5. Given le même scénario avec le garde-fou non installé (manager sans modèle, vrai `NotInstalled` du manager), then le verdict affiché est `not_installed` avec la raison, aucun téléchargement ni appel réseau n'est tenté (transport factice qui échoue s'il est touché), le verdict enregistré s'affiche à côté avec sa provenance, et le journal reçoit une entrée « non installé ».
6. Given le scénario PoisonedRAG, then le rang BM25 du passage piégé et celui du passage légitime pour `q_fact_pwd` sont recalculés par `lab.bm25` sur le corpus en mémoire (valeurs de rang écrites à la main dans le test, pas recalculées par la même formule), le passage piégé est de rang 1 ou, sinon, la story corrige le texte du piège (D4), et la réponse enregistrée sans garde-fou reprend « 8 caractères ».
7. Given PoisonedRAG avec garde-fous actifs (faux classifieur d'injection qui ne détecte pas le passage faux), then le verdict affiché est « passé », la réponse reste fausse, et la carte affiche le texte de limite « aucun garde-fou de contenu ne détecte cette affirmation » avec les deux pistes (contrôle d'ancrage CAP-6, diversité des sources).
8. Given le scénario Empoisonnement du graphe, then l'automate suit les étapes injecter, résumer, retirer le document, reconstruire : après « injecter » la relation fausse est dans le résumé de communauté ; après « retirer le document » elle y est encore, marquée « à reconstruire » ; après « reconstruire » elle disparaît ; vérifié étape par étape sur les valeurs du mini-graphe écrites à la main.
9. Given le scénario graphe, then la carte indique que le graphe est illustratif et que la démonstration sur l'index GraphRAG réel est reportée à la livraison de la story 13 ; le cas porte `provenance: constructed`.
10. Given un cas enregistré, then sa provenance est affichée (« enregistré le … avec … » ou « cas construit pour la démonstration (à enregistrer avec … ) ») ; aucun cas `constructed` n'est présenté comme enregistré.
11. Given les trois langues, then `rag_attack.yaml` fr, en, de ont les mêmes scénarios, verdicts, rangs et placeholders ; seuls les textes diffèrent ; chaque `doc_id` et `question_id` cités existent dans `rag.yaml` et `rag_questions.yaml`.
12. Given un scénario inconnu, then `GET .../attack/cases/{id}` répond 404 ; un corps POST hors bornes répond 422.
13. Given les modes de garde-fous de la session (page Garde-fous), then la carte ne les modifie pas : les modes lus avant et après une démonstration sont identiques (test sur `app_session`).
14. Given l'installation par défaut sans réseau, then la carte s'affiche et se rejoue intégralement (scénarios 1 à 3, sans et avec garde-fou en repli) sans modèle, sans index et sans clé ; E2E : aucune requête hors `127.0.0.1`.
15. Given les autres onglets, then aucune moyenne ni agrégat n'y apparaît et l'onglet Attaquer n'en contient aucun (test sur `rag-attack.js` et les clés JSON des points d'accès, comme le garde-fou de la story 15).

## Verification

- `uv run pytest -q --tb=short tests/test_rag_attack.py tests/test_rag.py tests/test_rag_questions.py tests/test_rag_lab_views.py tests/test_guardrails_manager.py tests/test_i18n.py tests/test_web_tokens.py tests/test_annex_language.py` -- vert (nom exact des tests de garde-fous à confirmer au développement).
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag_lab_attack,rag_lab_views` -- vert, en tranche courte.

## Plan de tests

- **pytest, `tests/test_rag_attack.py`**, faux classifieurs aux frontières du modèle, `tmp_path` pour tout fichier, aucun modèle ni réseau :
  - corpus en mémoire : le piégé s'ajoute sans toucher le corpus actif ni `rag.yaml` ; retrait symétrique ;
  - rang BM25 sur valeurs de rang écrites à la main, piège et légitime (question cible) ;
  - garde-fou : faux classifieur qui détecte (modes `block` et `flag`), qui ne détecte pas (PoisonedRAG), manager sans modèle (`not_installed`), classifieur qui échoue (`error`, sans blocage) ; entrées du `SecurityJournal` vérifiées par source, nom, décision ;
  - réseau : transport factice qui échoue s'il est touché, en toutes branches ;
  - graphe : automate étape par étape, reconstruire sans retrait, double retrait ;
  - données : miroir fr, en, de, placeholders, provenance, références vers le corpus et les questions, charge utile sans motif de secret ;
  - points d'accès : formes de GET et POST, 404 d'un cas inconnu, 422 d'un corps trop grand ;
  - session : modes de garde-fous inchangés (critère 13) ;
  - garde-fou des agrégats (critère 15).
- **pytest existants à relancer** : `test_rag.py` et `test_rag_questions.py` (le piégé reste inactif), `test_rag_lab_views.py` (onglets), tests du manager de garde-fous, `test_i18n.py`.
- **E2E `rag_lab_attack`** : ouvrir Attaquer, lire le bandeau et l'état inactif, activer le piège, jouer les trois scénarios sans puis avec garde-fous (repli « non installé » acceptable), lire le rang du passage piégé, lire la limite PoisonedRAG, parcourir les étapes du graphe jusqu'à la persistance puis la reconstruction, ouvrir le Journal de sécurité et y trouver les entrées, vérifier qu'aucune requête ne sort de `127.0.0.1`, que le corpus actif de Construire n'a pas changé et que Comparer ne contient aucune moyenne.

## Spec Change Log

- 2026-10-25 : rédaction (draft), points ouverts à trancher au point de contrôle de spec.

## Points ouverts

1. **Génération live ou cas enregistrés ?** « Relancer la question cible » avec le modèle actif (comme la maquette) exige un modèle et rend la réponse variable. Recommandation : cas enregistrés par défaut dans cette story (déterministes, testables, aucun modèle la nuit), le live en report avec tâche humaine ; le rang BM25 et le verdict de garde-fou, eux, sont réels.
2. **Garde-fou d'injection réel ou de repli ?** Prompt Guard 2 exige jeton Hugging Face et licence, donc souvent « non installé » sur le poste de démonstration. Recommandation : utiliser le manager réel (verdict honnête `not_installed`), avec le verdict enregistré à côté et un lien vers la brique Garde-fous pour l'installer ; ne pas écrire de détecteur à mots-clés de remplacement.
3. **Empoisonnement du graphe sans GraphRAG (story 13 absente).** Recommandation : mini-graphe illustratif en données (une poignée d'entités et de relations, un résumé de communauté), avec automate injecter, retirer, reconstruire, marqué `constructed` ; report de la version sur le vrai index GraphRAG quand la story 13 sera livrée (la démonstration de persistance y est vraie). L'alternative, tout reporter, ferait manquer le critère de succès de CAP-13 (trois scénarios).
4. **Le passage faux remonte-t-il en tête ?** Le texte actuel de `faq_mots_de_passe.md` n'a pas été classé contre `q_fact_pwd`. Recommandation : mesurer le rang BM25 au développement ; si le piège n'est pas de rang 1, ajuster sa formulation dans les trois langues (fichiers de la story 1, modification minime, tests de corpus relancés), sans toucher l'instruction cachée.
5. **Un seul document pour deux pièges.** Le même fichier porte l'affirmation fausse et l'instruction cachée. Recommandation : le garder tel quel, la page cite la phrase concernée par scénario ; le découper en deux documents serait un changement de corpus hors périmètre.
6. **Partage de l'instance Prompt Guard.** Un manager de démonstration séparé évite de changer les modes de la session mais pourrait recharger le modèle (22 M, RAM faible). Recommandation : manager propre à la démonstration, réutilisant l'instance de la session quand elle est chargée (lecture seule), sinon rien de plus ; modes de la page Garde-fous jamais modifiés (critère 13).
7. **Filtrage avec garde-fous : bloquer ou signaler.** Recommandation : l'utilisateur choisit `block` ou `flag` dans la carte (deux boutons radio), `block` par défaut, comme la brique Garde-fous.
8. **Fusion avec les stories 12.18 et 12.19** (mêmes onglet, `rag.html`, `rag.css`, `app.py`). Recommandation : blocs d'ajout isolés et commentés `# V1.2 story 17`, emplacements des cartes Effacement et Droits intacts, conflits d'ajout résolus en gardant tous les blocs.

## Reports

- Tâche humaine (Anaël) : enregistrer les réponses « sans garde-fou » et « avec garde-fou » des scénarios 1 et 2 avec un vrai modèle (le générateur par défaut), puis passer `provenance` à `recorded` avec date et modèle ; installer Prompt Guard 2 (jeton et licence) et enregistrer le vrai verdict.
- Reprise après la story 13 (GraphRAG) : brancher le scénario 3 sur le vrai index (entités, relations, résumés de communautés) à la place du mini-graphe, vérifier que l'effet persiste après retrait du document tant que le graphe n'est pas reconstruit, et mettre à jour `brownfield.md` ainsi que la fiche conformité GraphRAG (axe Injection, CAP-16).
- Relance live de la question cible avec le modèle actif (intention de classe (b)), si le point ouvert 1 est tranché dans ce sens.
