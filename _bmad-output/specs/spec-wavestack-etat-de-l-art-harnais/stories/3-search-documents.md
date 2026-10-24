---
title: 'WaveStack V1.4 (3) : outil search_documents et scénario RAG ou recherche agentique'
type: 'feature'
created: '2026-10-24'
status: 'review'
baseline_commit: '72cfdf0'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-etat-de-l-art-harnais/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-etat-de-l-art-harnais/brownfield.md'
---

## Intent

**Problem:** CAP-4. Le RAG injecte des extraits à chaque tour ; WaveStack ne montre pas l'autre
approche, celle des harnais de code : chercher par mots, puis lire le fichier trouvé.

**Approach:** Outil natif `search_documents` (mots de la requête, corpus Exemplia), et `read_file`
ouvert à `corpus/<doc>.md` par la résolution partagée (`native.py`, jugée par H1 via `demo_relative`).

## Décisions

- **Résolution partagée** : `resolve_demo_path` choisit la racine (`content/` pour un chemin `corpus/…`,
  sinon `demo_files/`) ; `demo_relative` renvoie `corpus/<doc>` ou le chemin relatif habituel. H1 n'est
  pas modifié : il juge ce chemin relatif. `corpus/../confidentiel/…` sort des deux racines, refusé.
- **Documents inactifs** : `corpus_files()` ne retient que les documents `active` de `content/rag.yaml`
  (règle de `chunk_corpus`). Ni `search_documents` ni `read_file` n'atteignent le document piégé ni la
  sentinelle (`read_file` répond « fichier absent » avec la liste des actifs). `audience: hr` n'est pas
  filtrée (le RAG ne la filtre pas non plus).
- **Recherche** : insensible à la casse et aux accents (`unicodedata`), mots de 3 lettres au moins,
  lignes classées par nombre de mots trouvés puis ordre des documents, 5 lignes de 120 caractères au
  plus, `corpus/<doc>.md:<ligne>: texte` (numérotation de ce que `read_file` renvoie), commentaires
  HTML ignorés, langue de la session fichier par fichier (`config.content_file`).
- **Hors lancement** : `ToolSpec.default_enabled=False` ; l'outil est décoché au lancement (le catalogue
  des autres scénarios, déjà serré dans 4 096 tokens, ne change pas) et se coche sur la carte Outils.
- **Description de `read_file`** inchangée (le module MCP complet est à la limite de la fenêtre) ;
  le listage « . » annonce le préfixe `corpus/` dans son en-tête.
- **Scénario** `rag_agentic` (module RAG, 60 min) : même question avec la brique RAG, puis avec l'outil,
  qui est nommé dans le prompt.

## Vérification

`tests/test_search_documents.py` (recherche, bornes, langues, documents inactifs, H1, cycle chercher puis
lire sur faux moteur), E2E `rag_agentic` sur le faux moteur.

## Reports

- Dans la fenêtre de 4 096 tokens, chercher puis lire un document entier est serré avec le moteur local
  (la lecture du document est bornée par `tool_result_max_tokens`) : à mesurer en recette avec le vrai modèle.
- Graphe d'architecture : `tools.search_documents` n'a pas de nœud fichier propre pour le corpus.
