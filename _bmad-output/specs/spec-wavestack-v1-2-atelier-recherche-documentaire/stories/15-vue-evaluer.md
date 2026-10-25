---
title: 'Story 15 : vue Évaluer, juges face à l''annotation humaine et quatre pièges'
type: 'feature'
created: '2026-10-25'
status: 'review'
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

Les décisions du point de contrôle (plus bas) priment sur la rédaction initiale.

- `src/wavestack/rag/evaluation.py` (nouveau) : critères et échelles de verdict, métriques sans modèle (rappel@k, MRR, refus correct par règle), agrégats avec n, règle de famille, protocole `Judge` (faux juges en test), invites par critère et grammaire GBNF, lecture d'une sortie de juge, cas des pièges, chargement de `rag_evaluation.yaml`. Réutilise `rag/diagnosis.py` (`holds`, `rank_in`, `folded`) pour reconnaître un passage attendu dans une liste, sans dupliquer la règle de l'ancre ; `rag/diagnosis.py` et `rag/lab.py` ne sont pas modifiés.
- `src/wavestack/models/catalog.py` : `publisher_for` (existant, non modifié) donne la famille d'un modèle local ou cloud (D3).
- `src/wavestack/models/engine.py` et `src/wavestack/models/servers.py` : ajout d'un argument nommé facultatif `grammar: str | None = None` à `complete` (moteur intégré : `llama_cpp.LlamaGrammar.from_string`, passé à `generate` ; llama-server : champ `grammar` du corps). Un moteur sans cet argument reste valide (même contrat que `sampling`, story 29) ; Ollama n'est pas un juge local admissible (D2).
- `src/wavestack/session/app_session.py` (ajouts) : mémoire bornée `run_id -> modèle génératif` des exécutions de l'atelier terminées ; méthode de jugement d'une exécution (charge le juge local via `LoadRegistry` ou appelle le juge cloud via `run_call` avec `max_session_usd`), verdicts gardés en mémoire de session par `run_id`, juge et critère.
- `src/wavestack/web/app.py` (ajouts seuls, piste « onglets ») :
  - `GET /api/rag_lab/evaluation` : textes, critères, panel (juges admissibles et écartés avec leur raison, présence de clé), plafond et dépense FinOps, jeu enregistré déjà calculé (tableau et agrégats), liste des pièges ;
  - `POST /api/rag_lab/evaluation` : corps borné comme `diagnosis.LiveRequest` (exécutions terminées de la page : `run_id`, `question_id`, préréglage, listes, contexte, réponse) ; renvoie tableau et agrégats du jeu enregistré plus ces exécutions, avec les verdicts déjà obtenus. Pur, sans modèle ;
  - `POST /api/intentions/rag_lab_judge` : juger une exécution avec un juge (classe (b) de la story 30 : acceptée en `idle` seulement, 409 avec la raison sinon, ou si le juge est écarté, sans clé ou au plafond) ;
  - `GET /api/rag_lab/evaluation/traps/{trap_id}` : un piège rejoué, 404 s'il est inconnu.
- `src/wavestack/web/static/rag-evaluate.js` (remplace le squelette), `rag.html` (contenu de `rag-panel-evaluate`, sans la note « à venir »), `rag.css`.
- `content/rag_evaluation.yaml` et `content/i18n/{en,de}/rag_evaluation.yaml` : textes, échelles, annotations, jeu enregistré, quatre pièges, fiche de la vue.
- `content/rag_questions.yaml` (fr, en, de) et `rag/corpus.py` : seul le commentaire du champ `annotation` change (« obsolète, voir `rag_evaluation.yaml` ») ; le champ reste (D4).
- `pyproject.toml` : inchangé, pas d'extra `eval-adapters` dans cette story (D7).
- `tests/test_rag_evaluation.py` (nouveau), `tools/e2e/run_e2e.py` (scénario `rag_lab_evaluate`), `tools/e2e/README.md`.

## Tasks & Acceptance

- [ ] Métriques et agrégats sans modèle, avec n et cas « sans objet ».
- [ ] Panel : règle de famille par `publisher_for`, juge local non Qwen à grammaire GBNF, juge cloud, clé et plafond, repli sur l'enregistré.
- [ ] Juge : invite par critère, argument `grammar` des moteurs, verdict + justification, protocole remplaçable par un faux juge ; intention `rag_lab_judge`.
- [ ] Annotations de référence et jeu enregistré (préréglages `dense` et `hybrid`, 10 à 12 questions préparées dont au moins une `factual`, une `multi_hop`, une `temporal` et une `no_answer`) en fr, en, de, avec leur provenance (D1, D4).
- [ ] Les quatre pièges, en données et en calcul (fidélité selon deux définitions recalculée depuis des affirmations étiquetées ; classement recalculé depuis les verdicts).
- [ ] Onglet : bandeau, choix des juges, tableau, agrégats par architecture, panneau « Pièges », fiche.
- [ ] Pas d'extra `eval-adapters` : retrait motivé dans Reports (D7).
- [ ] Tests ciblés et E2E.

**Acceptance Criteria:**
1. Given l'onglet Évaluer ouvert, then le bandeau « Démonstration, pas un banc : n = N questions, A architectures, J juges » est visible en permanence (hors de tout volet repliable), N valant le nombre de questions préparées distinctes réellement comptées (jeu enregistré plus exécutions de la session ; une question libre n'y entre pas).
2. Given le jeu enregistré, then le tableau montre, par question, architecture et critère, le verdict de chaque juge, l'annotation de référence et l'accord ou le désaccord, sans score global par question.
3. Given un désaccord, then la cellule le dit par un texte (« désaccord : juge X, référence Y »), pas par la couleur seule ; sans annotation, « non annoté », hors des taux d'accord.
4. Given des rangs de passages attendus et k, then rappel@k (part des passages attendus de rang ≤ k) et MRR (moyenne sur les questions de 1/rang du premier passage attendu, 0 s'il est absent) sont ceux de `evaluation.md`, vérifiés sur des valeurs écrites à la main dans le test (pas recalculées par la même formule) : rang absent, deux passages attendus dont un seul trouvé, passage au-delà de k. Pour une exécution de la session, la liste lue est la dernière liste ordonnée avant `context` (`rerank`, sinon `fusion`, sinon le meilleur rang des recherches, comme `diagnosis.py`) et k est son `top_k`, affiché (« rappel@3 »).
5. Given une question `no_answer`, then seul « refus correct » est évalué (règle : la réponse contient une formule de refus listée dans `rag_evaluation.yaml`, plus les juges) et les autres critères sont « sans objet », hors des agrégats.
6. Given les agrégats, par architecture et par critère, then chaque valeur porte son n ; sous n = 5 (`MIN_SAMPLE`) s'affiche « trop peu pour conclure » ; les verdicts « illisible » en sont exclus et comptés à part.
7. Given un juge de la famille (éditeur selon `publisher_for`) du modèle jugé, then il est écarté avec sa raison ; une famille inconnue (« Autres éditeurs ») est écartée aussi ; le panel proposé compte au plus un juge local (fichier GGUF ou llama-server, éditeur ≠ celui du générateur) et un juge cloud d'éditeur différent du générateur. Sans juge local admissible sur le poste, un message le dit et les cas enregistrés restent affichés.
8. Given aucune clé cloud, then aucun appel réseau n'est tenté (`config.cloud_key` est `None`, l'intention répond 409) et les cas qui exigent le cloud s'affichent avec leur provenance : « enregistré le … avec … » pour un résultat réel, « cas construit pour la démonstration (à enregistrer avec …) » tant qu'il ne l'est pas (D1).
9. Given la dépense cloud au plafond `max_session_usd`, then l'appel est refusé avant envoi (`session_cap_error`, cause `max_session_usd`), le transport n'est pas touché, et la dépense et le plafond sont affichés.
10. Given un faux juge dans les tests, then une sortie conforme à la grammaire est lue en verdict et justification ; une sortie illisible (JSON invalide, verdict hors échelle) devient « illisible », sans relance.
11. Given le piège « deux juges, deux verdicts », then les deux verdicts et leurs deux justifications s'affichent pour la même question et la même réponse.
12. Given le piège « variance d'un même juge », then deux passages du même juge sur le même cas montrent deux verdicts, avec la cause nommée (température, ordre des passages).
13. Given le piège « deux outils, deux définitions », then la fidélité au sens de Ragas (affirmations soutenues / affirmations) et au sens de DeepEval (affirmations non contredites / affirmations) sont recalculées en interne depuis des affirmations étiquetées `supported`, `unsupported` ou `contradicted`, avec leur définition côte à côte, et diffèrent sur le cas livré (valeurs attendues écrites dans le test).
14. Given le piège « le juge change le classement », then les préréglages `dense` et `hybrid` sont classés dans un ordre par le juge local et dans l'ordre inverse par le juge cloud, classement recalculé depuis les verdicts enregistrés et marqué comme tel.
15. Given l'installation par défaut, then la vue s'affiche intégralement et ni `ragas` ni `deepeval` ne sont importés (test sur `sys.modules` après import de `wavestack.rag.evaluation` et appel des points d'accès) ; `pyproject.toml` ne déclare aucun des deux.
16. Given les autres onglets et vues, then aucune moyenne, aucun agrégat n'y apparaît : test sur `rag.js`, `rag-build.js`, `rag-compare.js`, `rag-diagnosis.js`, `rag-attack.js`, `rag-sheets.js` (commentaires retirés, motif `\b(mean|average|avg|mrr|recall_at_k|aggregates?)\b`, insensible à la casse) et sur les clés JSON de `GET /api/rag_lab` et des points d'accès de diagnostic.
17. Given une annotation de référence, then sa provenance est affichée (« annotation proposée, à valider » ou « annotée par … le … ») ; aucune annotation rédigée par un agent n'est présentée comme humaine (D4).

## Verification

- `uv run pytest -q --tb=short tests/test_rag_evaluation.py tests/test_rag_diagnosis.py tests/test_rag_questions.py tests/test_rag_lab_views.py tests/test_llama_engine.py tests/test_model_servers.py tests/test_cloud_cap.py tests/test_i18n.py tests/test_web_tokens.py tests/test_annex_language.py` -- vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag_lab_evaluate,rag_lab_diagnosis` -- vert (le jeu enregistré ne suppose aucun index ni modèle).

## Plan de tests

- **pytest, `tests/test_rag_evaluation.py`**, faux juges et faux moteurs (`tests/fake_engine.py`), aucun modèle ni réseau :
  - métriques : rappel@k et MRR sur valeurs écrites à la main (rang absent, deux passages, au-delà de k), refus correct par règle, agrégats avec n, « sans objet », « illisible », seuil `MIN_SAMPLE` (4 et 5) ;
  - règle de famille : Qwen écarté face à un générateur Qwen ; famille inconnue écartée ; Ollama écarté (pas de GBNF) ; Mistral, Gemini, Claude admis face à Qwen ; un juge cloud Mistral écarté face à un générateur Mistral ;
  - cloud : sans clé, aucun appel (transport factice qui échoue s'il est touché) ; plafond atteint, refus avant envoi ; seule la frontière réseau est doublée, `run_call` et `session_cap_error` tournent vraiment ;
  - sortie de juge : verdict valide, JSON invalide, verdict hors échelle ; la grammaire GBNF livrée est acceptée par `llama_cpp.LlamaGrammar.from_string` (sans modèle) ;
  - moteurs : `grammar` transmis par le moteur intégré (moteur llama factice) et par llama-server (corps envoyé contient `grammar`) ; un moteur sans l'argument reste appelable ;
  - pièges : fidélité Ragas ≠ DeepEval sur le cas livré (valeurs écrites), classement inversé recalculé, variance (deux verdicts, cause) ;
  - données : mêmes verdicts, étiquettes d'affirmations, rangs et annotations dans fr, en, de ; mêmes placeholders ; chaque question annotée existe dans `rag_questions.yaml` ; chaque préréglage cité existe dans `lab.PRESETS` ; chaque provenance est `constructed` ou `recorded` avec date et modèle ;
  - points d'accès : formes de réponse de GET et POST, 404 d'un piège inconnu, corps POST borné (422 au-delà), intention 409 hors `idle`, 409 sans clé, 409 juge écarté ;
  - session : la mémoire `run_id -> générateur` et les verdicts gardés restent bornés (plus ancien retiré) ;
  - garde-fou des agrégats (critère 16) et absence d'import de ragas et deepeval (critère 15).
- **pytest existants à relancer** : `test_rag_diagnosis.py` (réutilisation de `rank_in`, son garde-fou « no mean » reste vert), `test_rag_lab_views.py` (onglets), `test_llama_engine.py`, `test_model_servers.py`, `test_cloud_cap.py`.
- **E2E `rag_lab_evaluate`** : ouvrir Évaluer sans exécution, lire le bandeau et n, trouver un désaccord écrit, lire « trop peu pour conclure » si n < 5, ouvrir les quatre pièges, lire la provenance « cas construit… » ou « enregistré le … avec … », vérifier qu'aucune requête ne sort de `127.0.0.1`, puis ouvrir Comparer et n'y trouver aucune moyenne. Le bouton « Juger » n'est pas exercé en E2E (il exige un modèle) ; son refus sans clé l'est.

## Spec Change Log

- 2026-10-25 : rédaction (draft), points ouverts à trancher à la relecture.
- 2026-10-25 : point de contrôle de spec. Corrections : intention `rag_lab_judge` au lieu d'un `POST` de jugement (un appel de modèle est une intention de classe (b)) ; famille par `catalog.publisher_for` existant ; argument `grammar` à ajouter aux moteurs (aucun moteur ne prend de grammaire aujourd'hui) ; les exécutions de la session sont tenues par la page (la session ne garde pas les runs), envoyées comme dans la story 9 ; jeu enregistré sur les préréglages existants `dense` et `hybrid` (la maquette cite GraphRAG, story 13) ; définitions exactes de rappel@k, MRR, k et des deux fidélités ; provenance des cas et des annotations ; garde-fou des agrégats rendu testable (les commentaires de `rag-diagnosis.js` contiennent « mean ») ; plan de tests complété (moteurs, intention, bornes, tests existants). Statut `ready-for-dev`.
- 2026-10-25 : implémentation (phase 2), statut `review` ; écarts et choix dans Reports.

## Décisions du point de contrôle

1. **Quoi évaluer** : jeu enregistré livré (préréglages `dense` et `hybrid`, 10 à 12 questions préparées des types `factual`, `multi_hop`, `temporal`, `no_answer`), plus les exécutions terminées de la session sur une question préparée, envoyées par la page (dernière exécution par question et préréglage) ; métriques sans modèle calculées d'office, verdicts de juge seulement sur « Juger cette exécution », une exécution à la fois ; pas de bouton « tout évaluer ». Les exécutions de la session sont perdues au rechargement (mémoire de la page). Le jeu enregistré est **construit** par le développeur (rangs, réponses et verdicts plausibles, cohérents avec le corpus) et marqué `provenance: constructed` ; Anaël le réenregistre plus tard (Reports).
2. **Juge local** : aucun modèle génératif n'est téléchargeable par WaveStack (seuls embeddings et rerankers le sont) ; le juge local est donc pris parmi les modèles génératifs découverts sur le poste (fichier GGUF ou llama-server, qui acceptent une grammaire GBNF ; Ollama écarté avec la raison « pas de grammaire GBNF »), d'éditeur différent du générateur, le plus petit d'abord. Aucun admissible : message « aucun juge local admissible sur ce poste » et cas enregistrés seuls. Le jeu construit nomme un juge local cible non Qwen reconnu par `publisher_for` (au choix du développeur, par exemple Granite ou Gemma), sans le télécharger.
3. **Famille d'un modèle** : `models/catalog.publisher_for` sur `publishers.yaml` (existant, local et cloud via `model`), sans table nouvelle ni changement de `config.py` ; l'éditeur est la famille ; « Autres éditeurs » = famille inconnue = juge écarté par prudence. Gemma et Gemini restent deux familles distinctes (éditeurs distincts de la table) ; la fiche le signale comme limite.
4. **Annotation** : annotations par critère dans `rag_evaluation.yaml` ; `RagQuestion.annotation` reste (pas de rupture de schéma) et son commentaire le dit obsolète. Les annotations livrées sont rédigées par le développeur, marquées `annotated_by: draft` et affichées « annotation de référence proposée, à valider » ; elles deviennent « humaines » quand Anaël les valide (Reports). La colonne s'intitule « Référence », pas « Humain », tant qu'elles ne le sont pas.
5. **Traduction des justifications** : justifications du jeu enregistré livrées en fr, en, de, avec la mention « traduit de l'enregistrement » hors de sa langue d'origine (champ `source_lang`) ; jugements en direct demandés dans la langue de l'interface et non traduits.
6. **Variance en direct** : cas enregistré seul ; pas de bouton « rejouer » dans cette story (rien hors critères, rien à tester sans modèle).
7. **Ragas et DeepEval** : pas d'extra `eval-adapters` dans cette story, retrait motivé (Reports) : les deux calculent la fidélité en appelant leur propre client LLM (OpenAI par défaut), donc un recoupement exige un appel de modèle ou un adaptateur vers nos moteurs ; les deux envoient une télémétrie par défaut, contraire à « rien ne sort du poste » ; leur arbre de dépendances est lourd pour un recoupement facultatif. Le piège 3 repose sur le recalcul interne, qui suffit à la pédagogie. Aucune résolution `uv` ni téléchargement à faire pendant le run.
8. **Seuil « trop peu pour conclure »** : n < 5, constante `MIN_SAMPLE = 5` unique dans `rag/evaluation.py`, exposée par `GET /api/rag_lab/evaluation`.
9. **Fusion avec les stories 17 à 19 de la V1.2** : blocs d'ajout isolés et commentés (`# V1.2 story 15`) dans `app.py`, `rag.html`, `rag.css`, `run_e2e.py`, README E2E ; conflits d'ajout résolus à l'intégration en gardant les deux blocs ; `app_session.py` et les moteurs : ajouts en fin de section, sans réordonner.

## Reports

- Tâche humaine (Anaël) : valider ou corriger les annotations de référence de `rag_evaluation.yaml` (fr, puis vérifier en et de), puis passer `annotated_by` à son nom et sa date.
- Tâche humaine (Anaël) : réenregistrer le jeu et les pièges avec un vrai juge local non Qwen et un vrai juge cloud (clé), puis passer `provenance` à `recorded` avec date et modèles ; vérifier que les pièges 1, 2 et 4 se produisent encore, sinon ajuster les cas.
- Tâche humaine (Anaël) : essai du bouton « Juger cette exécution » avec un modèle local réel (temps de chargement via `LoadRegistry`, qualité de la sortie GBNF sur CPU).
- Retrait de l'extra `eval-adapters` (D7) ; à reprendre seulement si un recoupement réel est voulu : mesurer la résolution `uv` des versions épinglées (ni torch ni service), couper leur télémétrie, brancher leur LLM sur nos moteurs. Mettre à jour `brownfield.md` (ligne `eval-adapters`) à l'intégration.
- Si la story 13 (GraphRAG) est livrée, ajouter une architecture `graphrag` au jeu enregistré comme dans la maquette.
- Développement (2026-10-25), écarts et choix à revoir :
  - Justifications du jeu enregistré : un gabarit par critère et par verdict (`texts.why`), pas une phrase propre à chaque cellule ; seuls les quatre pièges portent leurs justifications écrites. Anaël les réécrit en réenregistrant le jeu.
  - Précision du contexte : un verdict `yes | partly | no` par exécution (non par passage) ; moyenne : oui = 1, en partie = 0,5, non = 0 ; accord = égalité stricte avec la référence.
  - Le panel de la page (GET) suit le modèle qui génère maintenant ; le jugement d'une exécution vérifie la famille du générateur de cette exécution (mémoire `run_id -> modèle`, enregistrée au lancement de l'exécution, 50 entrées au plus).
  - Jugement : l'intention renvoie `judgment_id` ; la page interroge `POST /api/rag_lab/evaluation` toutes les 1,5 s jusqu'à `judging: false`. Un échec du fournisseur ou de la mémoire est dit dans l'onglet (`judge_error`), sans verdict « illisible » (qui reste réservé à une sortie illisible).
  - Un moteur sans l'argument `grammar` (fichier ou llama-server l'ont ; Ollama non) est refusé comme juge avec la raison « pas de grammaire GBNF ».
  - Cloud sans clé, jeu construit : `rag_lab_evaluate` n'exerce pas « Juger » (modèle requis) ; le refus 409 est vérifié par l'API.
  - `rag.html` garde la note `.rag-soon` de l'onglet Évaluer, masquée, car `rag.js` (`renderTabs`) y écrit son texte ; `rag.js` n'est pas modifié. `_rag_lab_tabs` (scénario `rag_lab_views`) ne cherche plus « à venir » dans Évaluer.
  - `rag_lab` (E2E) vérifie un dépôt intact par `git status` : il échoue tant que le worktree a des changements non commités, sans lien avec cette story.
