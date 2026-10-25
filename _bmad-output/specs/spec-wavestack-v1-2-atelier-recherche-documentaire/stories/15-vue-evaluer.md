---
title: 'Story 15 : vue Évaluer, juges face à l''annotation humaine et quatre pièges'
type: 'feature'
created: '2026-10-25'
status: 'draft'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/evaluation.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/vues.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/brownfield.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'onglet Évaluer n'est qu'une coquille « à venir ». Le participant peut lire une réponse et le rang du passage attendu (stories 4 et 9), mais pas apprendre à évaluer : que dit un juge LLM, face à une annotation humaine, sur la fidélité, la pertinence ou l'exactitude ? Que valent les agrégats d'un petit échantillon ? Pourquoi deux juges, un même juge ou deux outils se contredisent-ils ?

**Approach:** L'onglet Évaluer affiche, par question préparée et par critère, le verdict de chaque juge d'un panel (un local, un cloud), l'annotation humaine et l'accord ou le désaccord. Il calcule ensuite, en interne, les agrégats de `evaluation.md` avec n et le bandeau « Démonstration, pas un banc ». Un panneau « Pièges » démontre les quatre pièges des juges sur des cas livrés, rejouables sans modèle : aucun affichage n'exige le cloud. C'est la seule vue autorisée à agréger (SPEC, contraintes).

## Boundaries & Constraints

**Always:**
- Le calcul vit côté session, dans un module neuf `rag/evaluation.py` (AD-1) ; la page envoie, reçoit, dessine. `rag/lab.py` n'est pas modifié (piste « chaîne » de 12.5 et suivantes) ; au besoin, des ajouts seuls.
- Le JS de l'onglet vit dans `rag-evaluate.js` (décision de 12.4) ; `rag.js` n'est touché que si l'enregistrement de l'onglet l'exige, par ajout.
- Mesures recalculées en interne, définitions de `evaluation.md` : rappel@k, MRR (sans modèle, depuis les listes de l'exécution et les passages attendus), précision du contexte, fidélité, pertinence, exactitude (juge), refus correct (règle sur une question `no_answer`, plus juge).
- Aucun score global par question : critère par critère. Une moyenne n'existe que dans cet onglet, toujours avec n et le bandeau permanent « Démonstration, pas un banc : n = … questions ».
- Panel de deux juges de familles différentes : un SLM local en GGUF à sortie contrainte par GBNF, un juge cloud pris parmi les `[[cloud.models]]`. Règle de famille : un juge n'évalue jamais un modèle de sa propre famille (le générateur par défaut est un Qwen, donc le juge local n'en est pas un) ; le juge écarté l'est avec sa raison affichée. La fiche de la vue cite le biais d'auto-préférence.
- Juge cloud : choisi par le participant, actif seulement avec sa clé, dépense affichée et plafonnée par `[finops] max_session_usd` (mécanisme FinOps existant, pas de second compteur). Sans clé ou plafond atteint : le cas est affiché depuis son résultat enregistré, marqué « enregistré le … avec … ».
- Les annotations humaines et les cas livrés sont des données (`content/rag_evaluation.yaml`, surcouches en, de) ; les verdicts sont communs aux trois langues, seuls les textes et justifications sont traduits.
- Adaptateurs Ragas et DeepEval dans l'extra `eval-adapters` seulement, jamais requis pour afficher la vue ; absents de l'installation par défaut. À écarter, avec la raison dans Reports, s'ils tirent torch ou un service.
- Aucune couleur hors des jetons ; textes en fr, en, de.

**Never:**
- Pas de moyenne, d'agrégat ni de classement hors de l'onglet Évaluer.
- Pas d'appel cloud sans clé ni sans action explicite du participant ; aucun juge de la famille du modèle jugé.
- Pas de nouvelle dépendance dans l'installation par défaut ; pas de torch.
- Pas d'événement ajouté aux exécutions de l'atelier : un jugement est un appel à part, compté à part.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Tableau sans rien lancer | Aucune exécution de la session | Jeu enregistré livré : tableau questions × critères, agrégats, n | N/A |
| Exécutions de la session | Exécutions terminées sur des questions préparées | Leurs lignes s'ajoutent, n croît | Question libre : exclue, n'entre pas dans n |
| Accord / désaccord | Verdict d'un juge et annotation différents | Cellule marquée « désaccord » (texte et motif, pas la couleur seule) | Pas d'annotation : « non annoté », hors des taux d'accord |
| Juge de même famille | Juge Qwen face à un générateur Qwen | Juge écarté, raison affichée | Aucun juge local admissible : message, cas enregistrés seuls |
| Cloud sans clé | Juge cloud choisi, clé absente | Cas affichés depuis l'enregistrement, mention « enregistré le … avec … » | Aucun appel réseau |
| Plafond FinOps atteint | Dépense cloud >= `max_session_usd` | Appel refusé avant envoi, repli sur l'enregistrement | Message avec le plafond |
| Question sans réponse | `no_answer` | Seul « refus correct » s'applique ; rappel@k, MRR et fidélité marqués « sans objet » | N/A |
| Échantillon minuscule | n < 5 | Agrégats affichés avec n et mention « trop peu pour conclure » | N/A |
| Sortie de juge invalide | GBNF contournée ou JSON illisible | Verdict « illisible », compté à part, hors des agrégats | Pas de relance silencieuse |
| Piège ouvert | Clic sur l'un des quatre pièges | Cas rejoué depuis l'enregistrement, aucun appel au modèle | Piège inconnu : 404 |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/evaluation.py` (nouveau) : critères, métriques, règle de famille, protocole de juge (faux juges en test), invites et grammaire GBNF, agrégats, cas des pièges.
- `src/wavestack/web/app.py` : `GET /api/rag_lab/evaluation` (critères, juges admissibles et écartés, annotations, jeu enregistré, pièges, plafond et dépense) ; `POST /api/rag_lab/evaluation/judge` (juger une exécution terminée) ; `GET /api/rag_lab/evaluation/traps/{id}`. Ajouts seuls (piste « onglets »).
- `src/wavestack/web/static/rag-evaluate.js`, `rag.html` (panneau `rag-panel-evaluate`), `rag.css`.
- `content/rag_evaluation.yaml` et surcouches `content/i18n/{en,de}/` : textes, annotations humaines, jeu enregistré, quatre cas, fiche de la vue.
- `pyproject.toml` : extra `eval-adapters` (ragas, deepeval), épinglé ; adaptateurs dans `rag/evaluation_adapters.py`, importés paresseusement.
- `tests/test_rag_evaluation.py`, `tools/e2e/run_e2e.py` (scénario `rag_lab_evaluate`), `tools/e2e/README.md`.

## Tasks & Acceptance

- [ ] Métriques et agrégats sans modèle, avec n et cas « sans objet ».
- [ ] Panel : règle de famille, juge local non Qwen, juge cloud, clé et plafond, repli sur l'enregistré.
- [ ] Juge : invite par critère, sortie GBNF, verdict + justification, protocole remplaçable par un faux juge.
- [ ] Annotations humaines et jeu enregistré (deux architectures, 10 à 12 questions des quatre types) en fr, en, de.
- [ ] Les quatre pièges, en données et en calcul (fidélité selon deux définitions recalculée depuis des affirmations étiquetées ; classement recalculé depuis les verdicts).
- [ ] Onglet : bandeau, choix des juges, tableau, agrégats, panneau « Pièges », fiche.
- [ ] Extra `eval-adapters` et recoupement facultatif, ou retrait motivé.
- [ ] Tests ciblés et E2E.

**Acceptance Criteria:**
1. Given l'onglet Évaluer ouvert, then le bandeau « Démonstration, pas un banc : n = N questions » est visible en permanence, N valant le nombre de questions réellement comptées.
2. Given le jeu enregistré, then le tableau montre, par question et par critère, le verdict de chaque juge, l'annotation humaine et l'accord ou le désaccord, sans score global par question.
3. Given un désaccord, then la cellule le dit par un texte, pas par la couleur seule.
4. Given des listes de recherche et des passages attendus, then rappel@k et MRR sont ceux des définitions de `evaluation.md`, vérifiés sur des cas calculés à la main (dont rang absent et deux passages attendus).
5. Given une question `no_answer`, then seul « refus correct » est évalué et les autres critères sont « sans objet », hors des agrégats.
6. Given les agrégats, then chaque valeur porte son n ; sous n = 5 s'affiche « trop peu pour conclure » ; les verdicts « illisible » en sont exclus et comptés à part.
7. Given un juge de la famille du modèle jugé, then il est écarté avec sa raison ; le panel proposé compte un juge local non Qwen et un juge cloud de famille différente du générateur.
8. Given aucune clé cloud, then aucun appel réseau n'est tenté et les cas qui exigent le cloud s'affichent « enregistré le … avec … ».
9. Given la dépense cloud au plafond `max_session_usd`, then l'appel est refusé avant envoi et la dépense est affichée.
10. Given un faux juge dans les tests, then la sortie contrainte est lue en verdict et justification, une sortie illisible devient « illisible ».
11. Given le piège « deux juges, deux verdicts », then les deux verdicts et leurs deux justifications s'affichent pour la même question et la même réponse.
12. Given le piège « variance d'un même juge », then deux passages du même juge sur le même cas montrent deux verdicts, avec la cause nommée (température, ordre des passages).
13. Given le piège « deux outils, deux définitions », then la fidélité selon Ragas (affirmations soutenues) et selon DeepEval (absence de contradiction) sont recalculées en interne, avec leur définition côte à côte, et diffèrent sur le cas livré.
14. Given le piège « le juge change le classement », then deux architectures sont classées A > B par le juge local et B > A par le juge cloud, classement recalculé depuis les verdicts enregistrés et marqué comme tel.
15. Given une installation sans l'extra `eval-adapters`, then la vue s'affiche intégralement et ni ragas ni deepeval ne sont importés ; l'extra n'introduit pas torch (sinon retiré, voir Reports).
16. Given les autres onglets et vues, then aucune moyenne, aucun agrégat n'y apparaît (test sur les modules JS et les points d'accès).

## Verification

- `uv run pytest -q --tb=short tests/test_rag_evaluation.py tests/test_rag_questions.py tests/test_i18n.py tests/test_web_tokens.py tests/test_annex_language.py` -- vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag_lab_evaluate` -- vert (le jeu enregistré ne suppose aucun index).

## Plan de tests

- **pytest, `tests/test_rag_evaluation.py`**, faux juges, aucun modèle ni réseau :
  - métriques : rappel@k, MRR, refus correct, agrégats avec n, « sans objet », « illisible » ;
  - règle de famille : Qwen écarté face à un générateur Qwen, panel admissible sinon ;
  - cloud : sans clé, aucun appel (transport factice qui échoue s'il est touché) ; plafond atteint ; seule la frontière réseau est doublée ;
  - sortie GBNF : verdict valide, JSON invalide ;
  - pièges : fidélité Ragas différente de DeepEval sur le cas livré, classement inversé recalculé, variance ;
  - données : mêmes verdicts et annotations dans fr, en, de ; mêmes placeholders ; chaque question annotée existe dans le jeu de questions ;
  - points d'accès : formes de réponse, 404 d'un piège inconnu ;
  - garde-fou : aucun mot d'agrégat dans les autres `rag-*.js` ni dans les points d'accès de diagnostic et de comparaison ;
  - adaptateurs : test marqué `skipif` si ragas ou deepeval est absent.
- **E2E `rag_lab_evaluate`** : ouvrir Évaluer sans exécution, lire le bandeau et n, trouver un désaccord, ouvrir les quatre pièges, vérifier la mention « enregistré le … avec … », aucune requête réseau sortante, aucune moyenne dans l'onglet Comparer.

## Spec Change Log

- 2026-10-25 : rédaction (draft), points ouverts à trancher à la relecture.

## Points ouverts

1. **Quoi évaluer.** Évaluer n questions par une chaîne vivante coûte n exécutions de SLM. Recommandation : jeu enregistré livré (deux architectures, 10 à 12 questions) pour que l'onglet marche sans rien lancer, auquel s'ajoutent les exécutions terminées de la session ; pas de bouton « tout évaluer ».
2. **Juge local.** Modèle précis non Qwen. Recommandation : choisir au développement dans le catalogue déjà livré (GGUF, famille connue, capable de GBNF) ; si aucun n'est présent, proposer le téléchargement habituel et afficher les cas enregistrés en attendant.
3. **Famille d'un modèle cloud.** `CloudModel` n'a pas de champ famille. Recommandation : table `id ou fournisseur -> famille` dans `rag_evaluation.yaml`, sans toucher `config.py` ; famille inconnue = juge refusé par prudence.
4. **Où loger l'annotation humaine.** `RagQuestion.annotation` est une chaîne facultative réservée à cette story, insuffisante par critère. Recommandation : annotations par critère dans `rag_evaluation.yaml`, champ `annotation` de `rag_questions.yaml` laissé tel quel et noté obsolète.
5. **Traduction des justifications des juges.** Texte généré, enregistré dans une langue. Recommandation : justifications livrées traduites en fr, en, de dans le YAML avec la mention « traduit de l'enregistrement » ; jugements live dans la langue de l'interface.
6. **Piège « variance » en direct.** Recommandation : cas enregistré seul par défaut ; bouton « rejouer avec le juge local » facultatif, hors des critères d'acceptation et sans E2E.
7. **Adaptateurs Ragas et DeepEval.** Recommandation : tenter l'extra épinglé et mesurer la résolution `uv` ; au moindre torch ou service, retirer l'extra, le noter dans Reports et laisser le piège 3 sur le recalcul interne seul.
8. **Seuil « trop peu pour conclure ».** Recommandation : n < 5, constante unique dans `evaluation.py`.
9. **Fusion avec 12.17 à 12.19** (`rag.html`, `rag.css`, `app.py`, `run_e2e.py`, README E2E). Recommandation : blocs d'ajout isolés, conflits d'ajout résolus à l'intégration en gardant les deux blocs.

## Reports

- À remplir au développement.
