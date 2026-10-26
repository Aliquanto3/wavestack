# Rapport du run autonome du 2026-10-24 au 2026-10-25 : V1.3, V1.4 puis V1.2

Run lancé le 2026-10-24 à 23:10, terminé le 2026-10-25 à 18:55. Orchestration : session principale Opus 5.5 ; journal complet dans [run-autonome.md](run-autonome.md).

## Bilan

- **32 stories fusionnées** sur 32 prévues : epic 13 (V1.3, cache visible) 6/6, epic 14 (V1.4, état de l'art des harnais) 4/4, epic 12 (V1.2, atelier recherche documentaire) 22/22 (dont 12.19b, découpée de 12.19).
- **Trois versions** : 1.3.0 (#102), 1.4.0 (#106), 1.5.0 (#129 fusion de l'intégration dans main, #130 version, tag `v1.5.0` et [release](https://github.com/Aliquanto3/wavestack/releases/tag/v1.5.0)). Les stories V1.2 se sont intégrées sur `integration/v1-2-atelier` pour garder main à la 1.4.0 pendant la formation sur l'onglet harnais (décision d'Anaël du 2026-10-25).
- **Hors stories** : CI découpée en 4 groupes par système et équilibrée par durées (#98 ; Windows de 17-18 min à ~9 min) ; faux blobs creux pour les tests lents sous Windows (#100) ; onglet « Diagnostic » renommé « Modèles » (#124) ; correctif de la mise à jour du graphe GraphRAG (#127) ; README et démo refaits (#128).
- **Arrêts** : limite d'usage de 02:12 à 05:45 ; panne du classifieur du mode auto vers 07:10 (agents de 14.4 et 12.5 arrêtés, puis repris) ; réseau du poste très lent vers Hugging Face pour le banc 12.2 (14 à 43 Ko/s), contourné par Anaël.
- **Rien de bloqué en fin de run.** Aucun agent ni tâche de fond restants.

## Vérification finale

- CI de la PR #129 (intégration → main) verte : 8 groupes sur Windows et Ubuntu, 8 SUCCESS ; CI de la PR de version #130 verte ; main à f41cf5bb, `pyproject.toml` en 1.5.0.
- Les E2E ont été joués par tranches par chaque story et par sa revue (voir journal) ; pas de passe E2E complète sur main en fin de run (poste partagé avec les agents pendant le run). À faire au besoin : `tools/e2e/run_e2e.py --channel msedge` par tranches de 4 à 6 scénarios.

## Écarts au plan et décisions prises seul

- **83 décisions marquées « à revoir »** (annexe A). Les plus structurantes : épingle Comparer en localStorage (12.4) ; la chaîne lit la copie de travail quand elle diffère du livré (12.3) ; 10 points de la couche de décision (12.8, dont openrouter.ai dans `[net] allowed_hosts` pour toute l'application et plafond de session aveugle si l'API omet `usage.cost`) ; RAPTOR par règle et vecteurs de mots au lieu des embeddings (12.12) ; export OpenTelemetry à la demande et extra `otel` 1.44.0 (12.16) ; seuils sans source du banc visuel (12.21) ; exemption des noms techniques dans l'E2E `annex_language` (fin de lot).
- **Recherche visuelle sans OCR (12.21)** : ne tient pas. ColPali atteint le plafond de sécurité de 16 384 Mo ; ColSmol-256M : pic 6 098 Mo, 9,7 s d'indexation par page, requête médiane 8,97 s, rappel@3 0,88 sur 8 requêtes. Pistes dans `deferred-work.md`.
- **Démo** : trois prises nouvelles (jauge du cache et bilan, carte du harnais, onglet Fiches), 71,6 s ; faite avec Edge et le ffmpeg d'`imageio-ffmpeg`, sans installation système.

## Recette d'Anaël

Par ordre d'utilité, d'après les attentes humaines du journal (détail en annexe B) :

1. **Recette visuelle des onglets Attaquer et Fiches** (done_checkpoint de 12.17, 12.18, 12.19) : fr, en, de, thèmes clair et sombre ; relire les niveaux de risque et formulations réglementaires, les 12 fiches de composant (12.19b).
2. **Architectures avec un vrai modèle sur le PC cible** : GraphRAG « Reconstruire le graphe » (12.13), LLM Wiki « Recompiler » (12.14), RAPTOR et CRAG (12.12), recherche agentique et PageIndex (12.11), CAG et contexte long avec mesures (12.10).
3. **Couche de décision** (12.8) : extra `decision`, classifieur, routeur et Grounding check en local ; un vrai appel cloud (forme, coût, plafond).
4. **Évaluer** (12.15) : valider les annotations de référence, réenregistrer avec un vrai juge local non Qwen et un juge cloud.
5. **MCP et OpenTelemetry** : brancher un vrai Claude Code sur l'architecture exposée (12.20) ; `uv sync --extra otel` vers Phoenix ou Langfuse (12.16).
6. ~~Décision en attente : renvoi « story 14 » du document sentinelle~~ : fait par #131, qui renomme aussi le document en Projet Talvane (`projet_talvane.md`, code TLV-7731-QZ).
7. **Index réels** : reconstruire les 3 index (`build_rag_index.py --lang fr|en|de`) pour leurs fichiers de coût (12.3), si ce n'est pas déjà fait.
8. Relire le rapport du banc System One (12.2) et le rapport de recherche visuelle (12.21).

## Après le run

- Rafraîchir `test-durations-windows-latest.json` et `test-durations-ubuntu-latest.json` depuis une CI récente quand l'écart entre groupes dépasse ~2 min.
- Captures orphelines (aucun scénario ne les produit) : `44-modeles-tableau`, `50-theme-sombre-modeles`, `63-atelier-rag-diagnostic`, `annex-language-de-models-*` ; à supprimer ou à rebrancher.
- Hors run, toujours en attente : V2 (spec en brouillon), SLM C (benchmark).

## Annexe A : décisions prises seul, à revoir (83)

**13.1**

- non caché local = None « sans objet », distingué par cache_origin
- champ cache_write_1h_tokens ajouté dès la story 1 (Anthropic ephemeral_1h) pour les stories 4 et 5
- cache_origin None seulement pour une trace antérieure ; usage estimé = provider, cases None
- réponse Anthropic sans champs de cache = rien déclaré (None)

**14.1**

- scénario de sécurité des skills tiers = hooks
- consigne d'échafaudage portée par le scénario skills

**14.3**

- search_documents décoché par défaut, le scénario le fait cocher
- search_documents garde la règle languages du RAG (même corpus pour la comparaison)

**13.5**

- 3e point de cache sur le dernier message (sinon rien n'est mis en cache) ; la story 6 doit faire dépasser le seuil
- cache_control seulement pour le chat (_render_chat), pas les ateliers ni Tester ; clé via config.cloud_key

**13.2**

- seuil de 1 700 px du texte court de la jauge (spec de story, absent de DESIGN.md)

**14.2**

- sous-agent = 3e exception AD-9 (compression + subagent dépasse 3 584 tokens en CI)
- harness_map a un prompt neutre (schéma min 1 prompt) ; carte servie par bricks_changed, sans route
- capture 01b reprise de main, à regénérer par l'E2E
- vidéo de démo non regénérée (compose.py : 7 modules · 6 h)
- brique éteinte à opacity 0.45 (contraste 3,2:1) gardée, état aussi en texte

**13.4**

- signal = écriture hors 1er appel > lecture ; appels hors tour seulement dans « Depuis le lancement »
- appel local exclu de « sans prix déclaré » (contre une ligne de la spec de story)

**13.3**

- cause cache_cleared prioritaire sur reset et replay tant que le moteur reste vide

**12.3**

- la chaîne lit la copie de travail quand elle diffère du livré (Never de la spec de story levé) ; Modifier = ajout d'un paragraphe

**run**

- V1.2 en deux pistes (chaîne et onglets), vagues V10 à V18 ; code JS de chaque onglet dans son propre fichier dès 12.4
- 3 stories en développement le temps que 12.5 ou 12.9 finisse (14.4 prioritaire, V1.4 avant V1.2)
- fusions dans integration/v1-2-atelier en --methode merge (branches empilées), squash réservé à main
- 🛠️ gardé ; titre de page « Modèles » ; adresse /diagnostic et clés inchangées ; textes qui renvoient à la page alignés, « diagnostic » gardé quand il désigne une vérification ; captures non régénérées sauf celles qui vérifient le libellé
- prise carte du harnais sur la conversation Outils natifs ; prise Fiches sur « RAG dense » ; lien de barre « RAG » ; carte de fin « 3 ateliers » inchangée
- exemption des noms techniques de rag_lab.yaml dans annex_language (masquerait un « Documents » français oublié)

**12.4**

- épingle Comparer en localStorage ; titre « Atelier recherche documentaire », lien de barre « RAG » gardé ; questions de suivi exclues du sélecteur ; Comparer en 4 lignes sans synthèse
- épingle indépendante de la langue et du corpus ; pas de tabindex sur les panneaux ; captures echec-*.jpg ignorées par git

**13.6**

- module 8 « Cache » placé en dernier ; le second à fusionner entre 13.6 et 14.4 refait les totaux du programme
- fiche du cache en français seul ; mention de /agent-cost-kit:mesurer-couts « si le plugin est installé »

**14.4**

- les 9 points ouverts de la spec tranchés par le relecteur Opus (section « Décisions du point de contrôle » de stories/4-compaction.md)
- champ kept dans CompactionChoice ; débordement du sous-agent ou du résumé ne périme pas la carte du chat ; prompt 2 de compaction lit alertes_siem.log ; menu à la largeur du volet ; captures 80 à 83
- boutons au débordement d'un appel ultérieur, tour rejoué avec ses outils (décision 7) ; tour de compaction visible dans Comparer ; texte « plus anciens retirés sans résumé »

**12.9**

- calcul côté serveur ; budget = top_k, chute tolérée 2 rangs ; 3 cas enregistrés à la main sur de vrais chunks (pas avec les vrais modèles) ; textes dans rag_diagnosis.yaml
- CAP-2 à CAP-4 de la spec V2 marqués absorbés alors que le diagnostic en vue harnais, la synthèse A/B et les prompts suggérés sont reportés
- CAP-2 à CAP-4 de la spec V2 « partiellement absorbés », restent ouverts ; E2E hors CI (aucun E2E n'y tourne)
- copie de travail éditée ignorée si le passage n'est dans aucune liste (Reports de la story) ; E2E rag_lab_diagnosis dépend de rag et rag_rerank

**12.5**

- suivi lu sur les 3 dernières questions, étape query à part, fusion par rangs réciproques, consigne dans messages.yaml ; sources des fiches citées sans accès réseau
- questions annulées gardées dans l'historique du suivi ; échec de sauvegarde de la copie = session.rag_lab.interrupted

**12.15**

- 9 points tranchés par le relecteur Opus (jeu construit dense/hybrid, juge local découvert sur le poste, pas d'extra Ragas/DeepEval, MIN_SAMPLE 5, annotations draft « à valider »)
- verdicts yes / partly / no (1 / 0,5 / 0), jeu de 10 questions, juges cibles Granite 4.0 Micro et Mistral Small, sondage 1,5 s, juge chargé par appel, moteur sans grammar refusé comme juge
- JUDGE_MAX_TOKENS 256 relève aussi la réserve du juge cloud

**12.6**

- 8 points tranchés par le relecteur Opus (late chunking reporté, contextes valables à 700 caractères seulement, enfants ≤ 300, contextes reconstruits dans le dossier de données)
- coupe sémantique au 80e centile (gap >= seuil), reconstruction fusionnée avec l'existant, coût du contextual lu dans l'en-tête, outil sans --model, sources des fiches à vérifier
- build_rag_contexts.py sans --model (pas de moteur testable sans modèle), spec mise en accord
- avertir plutôt qu'élargir la recherche des parents ; fichier reconstruit remplacé en entier si la taille de chunk change

**12.7**

- 8 points tranchés par le relecteur Opus (budget 450 tokens estimés, compresseur emprunté seulement, coupe en fin de phrase avec « […] »)
- libellés « Budget de contexte (tokens) », « Ordre des passages (extrémités d'abord) », « Compression (Headroom) » ; extrait formaté entier compressé ; avertissements concaténés ; citations des fiches à relire

**12.17**

- 8 points tranchés par le relecteur Opus (cas constructed, mini-graphe illustratif, block par défaut, un seul document piégé)
- sans Prompt Guard chargé, verdict enregistré appliqué à la colonne « avec » ; entrées de démonstration comptées dans « bloqués » ; not_installed au niveau mid ; capture sans numéro
- sans Prompt Guard chargé, rien n'est écarté (critère 14 lu « affiché ») ; security_log.py modifié par ajout

**12.18**

- 8 points tranchés par le relecteur Opus (instantanés en mémoire, dérivés illustratifs, q_global_rh, tableau de 11 architectures)
- 11 architectures et 12 endroits dont 7 construits, textes de remise en conformité écrits par le dev, rebuild vide accepté, capture 69
- endroit construit jamais « effacé » mesuré, statut distinct « effacé (illustratif, non mesuré) »
- statut erased_illustrative et critère 6 réécrit

**12.10**

- 7 points tranchés par le relecteur Opus (règle 16 384 aussi en nuage, état reconstruit gardé à la mise à jour, NO_INDEX_WINDOW en >=) ; réglage de fenêtre sur la page Conversation, contre la maquette
- préfixe en cache comme partie de l'étape Contexte ; sans état gardé, la génération relit le préfixe resté dans le moteur ; catalogue de validation relu au changement de modèle ou de fenêtre ; captures 77 et 78
- refuser le CAG si _kv_per_token est illisible (le bloc d'intention dit non) ; estimation mémoire prudente (copie du contexte comptée deux fois)

**12.19**

- 13 fiches de composant découpées en story 12.19b (vague V19) ; page Sécurité = même vocabulaire RISKS sans seconde matrice (lecture de CAP-16) ; RAPTOR sans source
- ~400 textes fr/en/de écrits par le dev, graphrag / Droits « high » à trancher, couleur d'encre forcée sur les puces pour le contraste AA, champ before_search
- validateur de rag/erasure.py assoupli (story de l'architecture facultative), fichier dans la liste Never de la spec
- accolade manquante de rag.css aussi sur main (v1.4.0), corrigée à la fusion de la V1.2

**12.11**

- 9 points tranchés par le relecteur Opus (outils hors NATIVE_TOOLS mais mêmes noms et messages, arbre à deux niveaux, famille Structure, rebuild target) ; long_context et cag à passer available dans rag_erasure.yaml (12.10)
- boucle et descente sur le generator existant (model_scope, réserve 128) ; lignes de séquence « Tool calls » / « Tree descent » en anglais ×3 (test_i18n) ; grep et list_files comme éléments du contexte ; borne de 400 tokens par résultat (~1 600 caractères) ; « Arrêter » la reconstruction n'écrit rien ; CHOICE: NONE profond = no_node_chosen
- aucune architecture de l'atelier ne filtre l'audience hr (la carte d'accès de 12.18 montre la fuite) ; seul le MCP exposé de 12.20 filtre ; règle transmise à la relecture de 12.13

**12.2**

- seuils du filtre 0,95 / 0,60 sans source, 2 répétitions en ligne, 0,33 $ par modèle, jeu en 3 langues avec affirmations écrites à la main, passages périmés comptés à part, tranche 3-4 Go à confirmer sur le PC cible, enregistrement en liste blanche
- Strands Decider 2B et AnyJev écartés d'office (« carte non lue ») ; verdict mémoire sur le plus grand de l'ensemble de travail et de la mémoire privée ; instructions en 3 langues ; adaptateurs locaux testés seulement en réel
- Strands en q8 hobson v19 (seul port ONNX, q4f16 en repli) ; AnyJev en L0 content_free ; item toujours en erreur compté contre le candidat ; pas de filtre par défaut sans mesure du reranker
- la cascade vers le SLM juge de CAP-6 n'est pas viable avec Qwen3.5-2B (H7 64 %) ; 12.8 part sans repli SLM ou avec un repli signalé « non validé »

**12.20**

- HTTP seul (stdio reporté) ; pas de ligne « exposé » dans MATRIX_ROWS ; Copilot Studio exige une adresse HTTPS publique non fournie
- copie de travail non vide = démarrage refusé ; argument profile en trop ignoré par le SDK ; « Arrêter » annule aussi un appel MCP ; matrix_row_of("workshop__…") renvoie network (à trancher avec la ligne « exposé »)
- compte des passages RH retirés dans la réponse au client (le garder au seul journal local ?), outils exposés dans la ligne « réseau » de la matrice en attendant la ligne « exposé »

**12.19b**

- 4 vector stores dits exacts (sqlite-vec non vérifié dans le code) ; sources des embeddings hors litterature.md (hypothèse à y ajouter) ; H1 mesure l'hybride en bloc ; generation.not_run cite H10

**12.13**

- D1 graphe heuristique livré, D2 sans networkx, D5 construction du graphe livré moins chère que dense (surcoût prouvé sur graphe reconstruit), D7 pas de filtre hr (décision transverse)
- points a à j du Spec Change Log (lignes « Graph building » / « Graph query » en anglais ×3, vocabulaire gelé recalculé, fichier reconstruit limité aux sorties du modèle, forget à chaque copie gardée, lien LightRAG arXiv 2410.05779 non vérifié, RagLabRunIntention refuse les champs inconnus)

**12.14**

- 10 points dans la spec (synthèses seules par le modèle, concepts tf-idf bruités, index sans synthèses des concepts pour tenir dans 8 192, lint sans contradictions, construction moins chère que dense avec le wiki livré, aucun filtre hr, Karpathy cité sans lien)

**12.8**

- 10 points de la spec (cascade désactivée « non validée », sens du seuil du banc contre la maquette, seuil du routeur 50 % non mesuré, routeur limité à dense / hybride / rerank, PPLX filtre et Jev routeur et ancrage, choice et score jamais appelés en réel, openrouter.ai dans [net] allowed_hosts, juge sans grammaire)
- plafond de session aveugle si l'API omet usage.cost (le banc l'a toujours eu sur les modèles payants) ; openrouter.ai dans [net] allowed_hosts pour toute l'application ; juge de la cascade non mesuré

**12.12**

- D1 arbre par règle, D2 vecteurs de mots et BM25 au lieu des embeddings d'architectures.md, D3 résumé extractif qui privilégie les codes, D5 CRAG limité au cas « rien gardé », D6 pas de recherche web, D9 ordre des familles envoyé par le catalogue

**12.16**

- export à la demande par bouton ; SDK + encodeur au lieu de l'exporteur HTTP de brownfield.md ; [otel] auth_env ; redémarrage pour changer d'URL ; extra à 1.44.0 (pas 1.45.1) pour ne pas relever opentelemetry-api ; tests d'export hors CI
- hôte du collecteur autorisé pour tous les clients de la fabrique (comme un hôte cloud) ; surcoût de CI de --extra otel à relever sur la CI de la PR

**12.21**

- seuils (pic ≤ 4 096 Mo, indexation ≤ 15 s par page, requête ≤ 3 s, rappel@3 ≥ 0,75) sans source sauf le budget ; corpus fr seul ; licence Gemma de ColPali ; ColQwen2.5 écarté faute de voie sans torch
- seuils sans source, corpus fr seul, 12 pages et 8 requêtes, plafond 16 384 Mo, licence Gemma, entrées ColSmol construites à la main, ColQwen2.5 écarté

## Annexe B : attentes humaines et recettes, telles que journalisées (25)

**12.2**

- banc de modèles réels (candidats System One, Qwen3.5-2B 16 384 / 4 Go) : à lancer par Anaël, hors run parallèle
- banc réel : ordre d'Anaël poste libre, clé OpenRouter créditée (limites du modèle :free), GGUF Qwen3.5-2B et reranker, ONNX deberta_xsmall et mdeberta à télécharger une fois ; 25 min à 1 h en ligne, ~1 h en local
- téléchargements à ~20 Ko/s avec coupures vers Hugging Face : reranker bge-reranker-v2-m3 à 36 / 438 Mo (curl en reprise, toujours en cours), ONNX deberta_xsmall et mdeberta non téléchargés ; Qwen3.5-2B présent ; à finir sur un meilleur réseau, puis vérifier taille et sha256 du reranker
- telecharger.ps1 lancé par Anaël hors de Claude Code : même débit (14-43 Ko/s, ~8 h 25 annoncées pour le reranker), lenteur du réseau du poste et non de l'isolement réseau des commandes
- ordre d'Anaël pour la partie en ligne (possible avec agents en cours) ; partie locale et mémoire quand le poste est libre
- done_checkpoint : relire le rapport du banc (seuils du filtre sans source, H7 sur un seul article, Strands écarté, SLM juge non viable)

**12.3**

- reconstruire les 3 index réels (build_rag_index.py --lang fr|en|de) pour leurs fichiers de coût

**12.15**

- valider les annotations de référence ; réenregistrer jeu et pièges avec un vrai juge local non Qwen et un juge cloud ; essayer « Juger cette exécution » sur CPU

**12.6**

- facultatif : regénérer rag_contexts.yaml avec un vrai modèle ; mesurer une reconstruction complète sur le PC cible ; vérifier les sources des fiches

**12.7**

- facultatif : mesurer avant / après de compress avec l'extra compression sur le PC cible

**12.17**

- avant de déclarer finie (done_checkpoint) : recette visuelle fr/en/de clair et sombre, relecture des reformulations en/de, vrai verdict Prompt Guard 2, enregistrement des réponses, entrées de la page Sécurité

**12.18**

- décision : corriger « story 14 » en « story 18 » dans projet_talvane.md (ex-sentinelle renommée) (corpus livré, empreintes)
- avant de déclarer finie (done_checkpoint) : recette visuelle fr/en/de clair et sombre, jouer effacement et droits, corpus et copie de travail inchangés, relire les contenus construits

**12.10**

- mesures réelles sur le PC cible (durées à froid et à chaud, taille de l'état, mémoire de crête, tokens réels du corpus) ; fenêtre de 16 384 dans 4 Go à confirmer par la story 12.2

**12.19**

- avant de déclarer finie (done_checkpoint) : relire niveaux et formulations réglementaires fr/en/de (graphrag / Droits « élevé » contre « moyen » en maquette), liens de littérature, lecture de CAP-16, recette visuelle ; source primaire de RAPTOR à ouvrir avec réseau

**12.20**

- recette : un vrai Claude Code branché par la commande de la carte (citations, aucun passage RH), relecture des descriptions d'outils fr/en/de

**12.11**

- done_checkpoint avec un vrai modèle sur le PC cible : protocole ACTION:, tours, plafonds, réponses illisibles, descente avant / après « Reconstruire », durées, rendu fr/en/de

**12.19b**

- relecture des 12 fiches fr/en/de (FAISS « Meta », LanceDB, sqlite-vec, fastembed, lecture de H14)

**12.13**

- done_checkpoint : reconstruction du graphe avec un vrai modèle sur le PC cible (durée, tokens, graph_passages_fallback), local et global contre l'hybride, coût dans Comparer
- recette avec un vrai modèle (« Reconstruire le graphe », local et global contre l'hybride, surcoût dans Comparer, rendu fr/en/de clair et sombre)

**12.14**

- recette avec un vrai modèle (protocole PAGES:, « Recompiler le wiki », ajout / modification / suppression, Comparer, effacement, fiche, rendu fr/en/de clair et sombre)

**12.8**

- recette : extra decision, téléchargement du classifieur, routeur et Grounding check en local ; un vrai appel cloud (forme choice, coût, plafond)

**12.12**

- recette : « Reconstruire l'arbre » avec un vrai modèle, RAPTOR sur q_global_rh contre l'hybride, CRAG sur q_noanswer_*

**12.16**

- recette : uv sync --extra otel, Phoenix ou Langfuse, [otel] endpoint, « Exporter cette exécution » ; capture_content

**12.21**

- accord d'Anaël pour télécharger ~6,9 Go (ou ColSmol seul ~1 Go) : réseau peut-être sur données mobiles ; mesure ~20-30 min sur poste libre ensuite ; notification envoyée
