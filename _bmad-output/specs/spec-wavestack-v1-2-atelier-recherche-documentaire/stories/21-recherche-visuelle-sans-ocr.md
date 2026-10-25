---
title: 'Story 21 : optionnel, recherche visuelle sans OCR (ColPali, ColQwen)'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/stories/2-banc-prealable-system-one.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/corpus-et-questions.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-19 demande si un retriever visuel (ColPali, ColQwen) tient dans le budget du CPU : 4 Go pour tout le processus, aucun GPU, un seul modèle génératif chargé à la fois, hors ligne, sans droits administrateur, sans torch dans l'application. Aucun chiffre n'existe : les cartes de modèles annoncent des tailles, pas ce qu'un PC de 16 Go dépense.

**Approach:** Un banc `tools/bench/v12s21_visual_search_bench.py`, sur le modèle des bancs `v12s2` et `v2s6`, dessine des pages du corpus fictif Exemplia en images (pas d'OCR), les indexe une à une avec chaque candidat exécutable sans torch, puis cherche les questions du jeu préparé (MaxSim). Il mesure le pic de mémoire, la latence d'indexation par page et par requête, la qualité de la recherche, les dépendances et leur taille. Une note mesurée (`rapport-recherche-visuelle.md`) conclut ; l'écart éventuel va dans `deferred-work.md`. La story ne livre aucune fonction de l'application : le lot dit si la fonction est possible, pas comment on l'intègre.

## Boundaries & Constraints

**Always:**
- Les paquets de mesure viennent de `uv run --with fastembed==0.9.1` (onnxruntime, tokenizers, numpy, pillow en dépendances) ; ni `pyproject.toml` ni `uv.lock` ne changent. Torch n'est jamais dans l'environnement de mesure : le banc vérifie son absence (`torch`, `torchvision`, `transformers`) et la consigne ; sa présence rend le candidat « ne tient pas ».
- Données : seulement le corpus fictif Exemplia (`content/corpus/`, documents actifs, langue `fr` par défaut) et les questions de `content/rag_questions.yaml`. Aucune donnée d'utilisateur.
- Le téléchargement est une commande séparée (`download`), la seule qui touche le réseau : hôtes `huggingface.co` et `*.hf.co`, révisions épinglées par commit (40 caractères). `measure` tourne hors ligne (`HF_HUB_OFFLINE=1`) dans un processus enfant neuf sous la garde réseau du projet, sans hôte autorisé ; toute tentative réseau est consignée.
- Mesure ordonnée seulement avec `--confirm-idle` (poste libre de tout autre agent). Un arrêt de sécurité (watchdog, 16 384 Mo par défaut) coupe l'enfant si le modèle explose la RAM du poste de développement : ce plafond n'est pas le verdict, le verdict compare le pic au budget de 4 096 Mo.
- Chaque mesure est enregistrée (`tools/bench/results/<date>-v12s21/<candidat>.json` : latences, matrice de scores, pages, requêtes, mémoire, dépendances) ; `report` régénère le rapport à l'identique depuis ces fichiers, sans modèle ni réseau (aucune date de génération).
- Une entrée non exécutable (le graphe refuse l'entrée construite) est enregistrée « non exécutable » avec le message ; jamais de chiffre inventé ni de repli silencieux.

**Never:**
- Pas de téléchargement de poids ni de mesure dans la phase de spec et de développement du script ; le lancement est une ressource d'Anaël.
- Pas de torch, de `colpali-engine`, de `transformers` dans l'application ni dans le banc ; pas de binaire modifié (fork de llama.cpp) ni de compilation (Rust, cargo) à demander à l'utilisateur.
- Aucun changement de l'application : ni `lab.py`, ni interface, ni catalogue de modèles, ni `wavestack.toml`.
- Pas d'appel réseau en CI.

## I/O & Edge-Case Matrix

| Scénario | Entrée / état | Comportement attendu | Gestion d'erreur |
|----------|--------------|---------------------|------------------|
| `measure` sans `--confirm-idle` | Aucun drapeau | Refus avant tout chargement | Message nommant le drapeau |
| Poids absents | Snapshot incomplet | Refus, liste des fichiers manquants, renvoi à `download` | Aucune tentative réseau |
| Page dont l'ancre couvre deux pages | Passage à cheval | Question écartée et listée (`skipped_questions`) | Compte dans le rapport |
| Plafond d'indexation atteint | > 12 min d'indexation | Résultat « partiel » ; requêtes seulement sur les pages indexées | Marqué « (partiel) » |
| Le graphe refuse l'entrée | Forme ou noms d'entrée inattendus | Candidat « non exécutable », message conservé | Autres candidats poursuivis |
| Pic au plafond de sécurité | RSS > plafond | Enfant arrêté, candidat « ne tient pas », pic = RSS à l'arrêt | Rapport indique « arrêté au plafond » |
| Poste de 32 Go | Poste de développement | Verdict avec la mention « durées à confirmer sur le PC cible 16 Go » | Attente humaine si le pic est entre 3 072 et 4 096 Mo |
| Rejeu | `report` sans résultat | Gabarit « pas encore mesuré » | N/A |

</frozen-after-approval>

## Candidats (cartes lues par le réseau le 2026-10-25, aucun poids téléchargé)

Recherche sur l'API du Hub (`colpali`, `colqwen`, `colsmol`, `colnomic`, `* onnx`, `* gguf`), cartes et fichiers lus ; révisions = commits renvoyés par l'API.

**Retenus pour la mesure (voie sans torch).**

| Id | Dépôt @ révision | Poids | Licence | Voie | Source |
|---|---|---|---|---|---|
| `colpali_v13_fp16` | `Qdrant/colpali-v1.3-fp16` @ `e69c27e8e2e50f62a2f76d8c6f693d21d53804a7` | `model.onnx` 2 Mo + `model.onnx_data` 5 849 Mo (fp16) + tokenizer 35 Mo, ~5,9 Go ; fastembed annonce 6,5 Go ; ~2,9 Md de paramètres | Conditions d'utilisation de Gemma (modèle dérivé) ; adaptateur MIT | fastembed 0.9.1 (`LateInteractionMultimodalEmbedding`, onnxruntime), sans torch ; image 448x448, 1 030 vecteurs de 128 par page, requête tronquée à 50 jetons | carte du dépôt et `fastembed/late_interaction_multimodal/colpali.py` (v0.9.1) |
| `colsmol_256m_onnx` | `onnx-community/colSmol-256M-ONNX` @ `12022f0630b795c229e85cd4af33e288fef124f0` | `onnx/model.onnx` 953,5 Mo (fp32) + tokenizer, ~0,96 Go ; ~256 M de paramètres | MIT | onnxruntime + tokenizers + pillow, entrées construites à la main (13 tuiles de 512, 64 jetons par tuile) ; graphe tracé à 13 tuiles | carte (licence seule) ; entrées d'après la carte jumelle `guyettinger/colSmol-256M-dynamic-onnx` et le prétraitement Idefics3 |

**Écartés ou en réserve** (motifs complets dans le rapport, section 2) :
- ColQwen2.5 v0.2 (`vidore/colqwen2.5-v0.2` @ `dcbe8d9c`, MIT, 3B) : adaptateur PEFT, torch et `colpali-engine`, aucun port ONNX ou GGUF trouvé. C'est le plus multilingue du lot : le motif d'écart est la voie d'exécution, pas la qualité.
- ColQwen2 GGUF f16 (`odellus/colqwen2-v1.0-gguf` @ `8b4ff3b7`, Apache-2.0) : 3 094 + 1 332 Mo = 4,4 Go, au-delà du budget, et fork `crow-cli/llama.cpp` obligatoire.
- Ops-Colqwen3-4B Q4_K_M (`takenoko-gohan/Ops-Colqwen3-4B-GGUF` @ `463a43c1`, Apache-2.0) : 3 311 Mo pour le seul LLM, exécution par un exemple Rust Candle (compilation).
- ColSmol-500M (`vidore/colSmol-500M` @ `0aaa9726`), ColPali torch (`vidore/colpali-v1.3`), ColNomic 3B : adaptateurs PEFT (torch) ; aucun port ONNX.
- ColSmol-256M ONNX à tuiles dynamiques (`guyettinger/colSmol-256M-dynamic-onnx` @ `93956db0`, MIT) : réserve. Sortie de `n*64+2` vecteurs, disposition des `input_ids` non documentée ; l'auteur annonce ~5,0 s par image à 7 tuiles (fp32, CPU), chiffre publié non vérifié.

**Hypothèses de modèle à connaître.** ColPali et ColSmol sont entraînés sur des données anglaises (« training set is fully English by design », cartes vidore) ; le corpus Exemplia est en français, la qualité mesurée vaut pour ce corpus. fastembed passe, pour une requête, une image vide dans tout le graphe ColPali : la latence d'une requête est celle d'un passage complet (carte Qdrant : « `pixel_values` is an all-zero image »).

## Protocole de mesure

1. **Pages sans OCR.** Les documents actifs du corpus (`read_documents`, titre inclus) sont paginés en lignes de 70 caractères, 44 lignes par page, puis dessinés avec Pillow en PNG A4 150 dpi (1240 x 1754), police Consolas (repli DejaVu Sans Mono, puis police de Pillow), texte noir sur fond blanc. Le corpus `fr` donne 26 pages. Aucun moteur de texte n'est employé pour la recherche : seuls les pixels sont indexés.
2. **Jeu.** 12 pages par défaut (`--pages`) : les pages « bonnes » de toutes les questions éligibles (types `factual`, `temporal`, `cross_lingual`, un seul passage attendu tenant sur une seule page), complétées par des pages tirées avec la graine 12021. 8 requêtes par défaut (`--queries`) : le texte de la question, la page bonne étant celle qui contient l'ancre du passage attendu.
3. **Mesures par candidat** (enfant neuf, une seule instance de modèle) :
   - **mémoire** : pic de l'ensemble de travail (`peak_wset` sous Windows, `VmHWM` sous Linux), pic de mémoire privée et pic de mémoire validée relevés après chargement, après indexation, après recherche ; pic retenu = le plus grand ; RAM totale du poste consignée ;
   - **latence** : chargement ; indexation page par page (prétraitement de l'image compris), médiane et maximum ; requête (encodage + MaxSim sur toutes les pages), médiane et maximum ; plafonds de 12 min d'indexation et 5 min de requêtes (résultat « partiel » au-delà) ;
   - **qualité** : rappel@1, rappel@3, MRR sur les requêtes dont la page bonne est indexée (les égalités comptent contre le modèle) ;
   - **index** : vecteurs par page, taille de l'index du corpus entier en fp16, durée d'indexation extrapolée au corpus entier (médiane x 26 pages) ;
   - **dépendances** : fermeture des paquets du candidat, taille sur disque, licences ; torch présent ou absent ; tentatives réseau de l'enfant.
4. **Durée visée** : ≤ 30 min sur ce poste (32 Go ; le PC cible a 16 Go) : ColPali ~15 min avec ses plafonds, ColSmol ~3 min, plus le chargement.

## Seuils de conclusion

Un candidat « tient » si toutes les conditions sont vraies ; « tient de justesse » si le pic dépasse 3 072 Mo sans dépasser 4 096 Mo ; sinon « ne tient pas » avec les motifs.

| Critère | Seuil | Origine |
|---|---|---|
| Mémoire | pic ≤ 4 096 Mo (« tient » ≤ 3 072 Mo) | SPEC.md (budget) ; 3 072 Mo comme `.memlog.md` de la story 2 |
| Indexation | médiane ≤ 15 s par page | ~26 pages d'Exemplia : indexation du corpus en ≤ 7 min, tenable pour une démonstration (proposition du développement) |
| Requête | médiane ≤ 3 000 ms | comme le maximum local de `decision-model-candidates.md` |
| Qualité | rappel@3 ≥ 0,75 sur ≥ 6 requêtes | proposition du développement, sans source |
| Torch | absent | SPEC.md |

Conclusion du lot : « tient » si au moins un candidat tient (avec les réserves de langue et de licence), « ne tient pas » sinon, avec le candidat qui s'en est approché le plus et ce qui manque. « Pas encore mesuré » tant qu'aucun résultat n'est enregistré.

## Forme de la note et de l'entrée de report

- **Note** : `_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/rapport-recherche-visuelle.md`, générée par `report --write` : 1 statut et conclusion, 2 candidats (retenus, écartés, motifs), 3 mémoire et latence, 4 qualité et taille de l'index, 5 dépendances, 6 seuils et réserves, 7 commandes.
- **Entrée de report** : un bloc `source_spec / summary / evidence` dans `_bmad-output/implementation-artifacts/deferred-work.md`. Livrée maintenant en « pas encore mesuré » ; à compléter après la mesure avec le bloc que le rapport propose (« Écart à consigner »), puis à clore si le verdict est « tient » et qu'Anaël décide de ne pas intégrer (CAP-19 est optionnel).

## Code Map

- `tools/bench/v12s21_visual_search_bench.py` -- banc : pagination, rendu, sélection, adaptateurs fastembed et ONNX Idefics3, enfant de mesure, agrégation, verdict, rapport ; réutilise `v2s6_decision_bench.py` / `story12_bench.py` (garde réseau, pic de RSS, watchdog, fermeture des paquets), sans copie.
- `tools/bench/results/<date>-v12s21/` -- enregistrements (une fois mesuré).
- `tests/test_v12s21_visual_search_bench.py` -- logique pure, faux modèle, rejeu, rapport.
- `_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/rapport-recherche-visuelle.md` -- gabarit « pas encore mesuré ».
- `tools/bench/README.md` -- commandes.

## Tasks & Acceptance

- [x] Critère 1 : recenser les candidats, voie d'exécution sans torch, taille, licence, révision, d'après les cartes.
- [x] Critère 2 : pages-images du corpus sans OCR, jeu de pages et de requêtes déterministe.
- [x] Critère 3 : adaptateurs sans torch (fastembed ; ONNX Idefics3 à la main), enfant sous garde réseau, watchdog.
- [x] Critère 4 : mesures (mémoire, latence, qualité, index, dépendances), enregistrement et rejeu.
- [x] Critère 5 : verdict par seuils, rapport, bloc de report ; tests sans réseau ni modèle.
- [ ] Critère 6 : lancement réel (`download`, `measure`), conclusion de la note et entrée de `deferred-work.md` : ressource d'Anaël.

**Acceptance Criteria:**
- Given aucun résultat enregistré, when on lance `report`, then le rapport « pas encore mesuré » sort à l'identique du fichier versionné.
- Given des résultats enregistrés, when on relance `report`, then le rapport est identique à l'octet.
- Given un candidat dont le graphe refuse l'entrée, then il est « non exécutable » avec le message, et les autres sont mesurés.
- Given la mesure faite, then la note donne le pic de mémoire, les latences, le rappel, les dépendances et une conclusion « tient » ou « ne tient pas » qui renvoie à `deferred-work.md`.

## Verification

- `uv run pytest -q --tb=short tests/test_v12s21_visual_search_bench.py` -- vert, sans réseau ni modèle (le test de rendu Pillow est sauté sans Pillow : `uv run --with pillow pytest ...`).
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `uv run python tools/bench/v12s21_visual_search_bench.py report` -- gabarit identique au fichier versionné.

## Spec Change Log

- 2026-10-25 : spec rédigée, banc et gabarit livrés ; mesure non lancée (aucun poids téléchargé).

## Reports

- Lancement réel : ordre d'Anaël, poste libre. `download` ~6,9 Go (ColPali ~5,9 Go, ColSmol ~0,96 Go) plus ~120 Mo de paquets ; `measure` ~20 à 30 min.
- Décisions prises sans Anaël, à revoir : seuils d'indexation (15 s par page), de requête (3 s) et de qualité (rappel@3 ≥ 0,75 sur ≥ 6 requêtes) ; corpus `fr` seul (le français est la langue par défaut ; des modèles anglais y sont jugés sur du français) ; 12 pages et 8 requêtes ; plafond de sécurité de 16 384 Mo ; ColPali v1.3 retenu malgré les conditions d'utilisation de Gemma (à faire valider avant toute intégration) ; les entrées ColSmol sont construites sans pouvoir être validées avant le téléchargement (échec enregistré, non masqué) ; ColQwen2.5, le plus multilingue, écarté faute de voie sans torch.
- Si ColSmol est « non exécutable » : essayer le port à tuiles dynamiques (`guyettinger/...`) ou une conversion ONNX dédiée, dans une story ultérieure.
- Intégration à l'application (catalogue, `lab.py`, interface) : hors lot, à décider après la note.

## Revue

### Passe 1 (2026-10-25, SHA revu 56c95cfe)

Base : fusion de `origin/integration/v1-2-atelier` (12.12, 12.14) dans la branche, sans conflit. La mesure n'a pas été relancée. Un seul appel de requête ColSmol réel a été fait, sur le modèle en cache, pour prouver le correctif.

- Important, high, second avis 1 : `test_template_report_is_the_committed_one` comparait le rapport versionné au gabarit et échouait depuis 78ca191c. Corrigé : un test compare le rapport au rejeu des derniers résultats, un autre vérifie le gabarit sans résultat.
- Important, medium, second avis 4 : la requête ColSmol passait une image factice nulle, qu'Idefics3 retire comme remplissage, d'où l'échec `Split` sur 0 image. Corrigé avec `colsmol_query_feeds` : image factice non nulle (1,0) sur 13 tuiles, aucun jeton `<image>` dans la requête (colpali-engine n'en met pas). Preuve par un appel réel (31 jetons) : sortie (1, 31, 128), normes de 1, ~8,3 s. Test de la forme des entrées sans modèle. Rappel et latence : remesure reportée.
- Important, medium, second avis 3 : le pic retenu était le pic de mémoire validée (6 130 Mo). Corrigé : `memory_peak` prend le plus grand de l'ensemble de travail et de la mémoire privée, comme `v12s2.memory_peak`. Résultat : 6 118 Mo, marge de -2 022 Mo. Le rapport affiche aussi l'ensemble de travail (4 244 Mo) et la mémoire validée. Le verdict ne change pas : ne tient pas.
- Important, medium, revue : un candidat arrêté au plafond de sécurité sortait « non exécutable » et « pas encore mesuré », contrairement à la matrice de la spec (« ne tient pas »). Corrigé : enregistrement `stopped_at_ceiling`, `ceiling_mb` et `rss_at_stop_mb`, et verdict « ne tient pas ». `colpali_v13_fp16.json` a été réécrit au nouveau format, avec les mêmes faits (plafond de 16 384 Mo confirmé par le watchdog de ColSmol dans la même mesure).
- Important, medium, second avis 2 : l'entrée de `deferred-work.md` affichait « pas encore mesuré ». Corrigé : verdict mesuré, défaut du banc, commande de remesure et pistes (également au §6 et dans le bloc « Écart »).
- Nit, medium, second avis 5 : l'index et la durée du corpus entier sont désormais marqués « extrapolé », avec la formule. Corrigé.
- Nit, low, second avis 6 : le libellé du plafond était faux. Il donne maintenant le plafond (16 384 Mo) et le RSS à l'arrêt (18 750 Mo). Corrigé.
- Nit, low, second avis 7 : le §6 liste désormais les décisions « à revoir par Anaël ». Corrigé.
- Nit, low, second avis 8 : la fermeture était déjà complète (27 paquets, 146 Mo) ; le rapport la nomme désormais et détaille les paquets de 1 Mo ou plus. La phrase sur onnxruntime a été corrigée (déjà dans les extras `decision` et `guardrails`). Corrigé.
- Reporté : remesure de ColSmol seul sur poste libre, `uv run --with fastembed==0.9.1 python tools/bench/v12s21_visual_search_bench.py measure --confirm-idle --only colsmol_256m_onnx --results-dir tools/bench/results/2026-10-25-v12s21`, puis `report --write`. À vérifier : 8 requêtes exécutées, rappel@3 et latence de requête (au-delà de 3 s attendu, d'après l'appel unique).
- Complexité : 0 constat (listes bornées par 12 pages et 8 requêtes).
