---
id: SPEC-wavestack-retours-2026-10-27
companions:
  - brownfield.md
sources: []
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Retours du 27/10 : corrections de la barre et des six onglets

## Why

Douleur à corriger : en préparant ses formations sur la v1.6.2, Anaël bute sur des défauts qui gênent la démonstration. Certains chiffres manquent (montant du bilan, journal vide), des textes sont confus (fragment, couleurs, guide et capteurs) et des écrans sont encombrés (panneau des briques) ou trop bruts (Sécurité). Le schéma MCP est incohérent et des réglages sont introuvables là où on en a besoin (fenêtre de contexte, modèle du RAG). La pédagogie passe avant tout : chaque écran doit se lire sans l'aide d'Anaël.

## Capabilities

- **CAP-1**
  - **intent:** Le Bilan de la séance montre toujours un montant à côté de l'empreinte, et son texte tient dans la popup.
  - **success:** Après un appel à Gemma (sans prix), le Bilan affiche « 0 € » avec la mention d'offre gratuite. Après un appel à un modèle tarifé, il affiche le coût. À 360 px de large, aucun texte ne dépasse de la popup (E2E).
- **CAP-2**
  - **intent:** Le Journal de la barre liste chaque appel de modèle de tous les onglets, en plus des décisions de sécurité, avec un filtre « Sécurité seulement ».
  - **success:** Une génération RAG puis un appel MCP sans outil ajoutent chacun une entrée (onglet, modèle, tokens d'entrée et de sortie, coût, empreinte, durée). Le filtre ne laisse voir que les décisions de sécurité (test et E2E).
- **CAP-3**
  - **intent:** La carte du harnais a des boutons au style de l'application, des sources cliquables et des définitions de « guide », « capteur calculé » et « capteur déduit » ; « marketplace » n'est pas traduit en français.
  - **success:** Les deux boutons ont le style commun, chaque source ouvre son URL dans un nouvel onglet, les trois termes sont définis dans la carte et le glossaire (fr, en, de), et « place de marché » n'apparaît plus.
- **CAP-4**
  - **intent:** Le panneau des briques n'affiche plus que l'essentiel : pas de libellé « Éteinte », pas d'étiquettes « … engineering », et des explications repliées par défaut avec un aperçu d'une ou deux lignes qui se déplie au clic.
  - **success:** Au chargement, aucune explication n'est dépliée. Un clic sur l'aperçu d'Outils, MCP, Sous-agent, Garde-fous ou Compression la déplie, au clavier comme à la souris (E2E).
- **CAP-5**
  - **intent:** Les actions forcées disparaissent entièrement de l'application.
  - **success:** Plus aucune trace dans l'interface, les routes, la séance, les contenus fr, en et de, ni les tests. La suite complète et les E2E restent verts.
- **CAP-6**
  - **intent:** Dans l'Atelier LLM, le texte saisi sert à toutes les étapes qui le citent, et l'étape 6 montre ce qui part au modèle, explique les couleurs et le mot « fragment », et donne le coût et l'empreinte à côté du débit.
  - **success:** Un texte saisi est découpé et généré tel quel. L'étape 6 affiche le prompt envoyé, une légende, une définition de « fragment », ainsi que le coût et l'empreinte pour un modèle cloud, ou l'énergie locale pour un modèle local (E2E).
- **CAP-7**
  - **intent:** Dans l'Atelier RAG, l'utilisateur choisit et voit le modèle qui génère la réponse, règle la fenêtre de contexte depuis l'onglet pour débloquer Contexte long et CAG, et comprend pourquoi le CAG reste réservé aux modèles locaux.
  - **success:** Une génération RAG utilise le modèle choisi sans changer le modèle de la séance. Agrandir la fenêtre depuis l'onglet RAG rend Contexte long disponible. Le CAG grisé sous un modèle cloud en donne la raison (test et E2E).
- **CAP-8**
  - **intent:** Dans l'Atelier MCP, chaque serveur a son logo, la réponse finale se déplie dans Séquence et se lit sous « Envoyer au modèle », et le schéma Avant/Avec MCP compare les mêmes serveurs de manière lisible.
  - **success:** Les logos s'affichent hors ligne et la réponse est lisible en entier aux deux endroits. Dans le schéma, chaque source a sa forme, GitHub a sa ligne « Code pour l'API GitHub », aucune ligne n'est repliée en pointillés et le serveur MCP est un élément visible (E2E).
- **CAP-9**
  - **intent:** L'Atelier MCP propose un serveur distant public qui expose au moins une ressource et un prompt.
  - **success:** Une fois connecté, ce serveur liste au moins une ressource et un prompt. Les deux s'utilisent jusqu'à la réponse du modèle (test sur faux serveur, vérification manuelle sur le vrai).
- **CAP-10**
  - **intent:** L'onglet Sécurité est refondu pour être pédagogique, avec des éléments interactifs qu'on reconnaît comme tels.
  - **success:** Anaël valide une maquette HTML avant le code. L'onglet livré suit la maquette et chaque élément cliquable a une affordance visible (curseur, chevron, état au survol et au focus).

## Constraints

- Textes en français ; surcouches en et de sous `content/i18n/{en,de}/`, mêmes clés, dans la même story.
- Aucune ressource chargée d'internet par l'interface : logos en SVG locaux sous `static/`, le PC pro peut être hors ligne.
- Dépôt public : aucune clé ni aucun jeton commité. Le serveur de CAP-9 se passe d'authentification, ou bien la clé est saisie par l'utilisateur comme pour GitHub.
- `app_session.py`, `content/ui.yaml`, `app.js` et `pages.css` sont partagés : fusionner les stories l'une après l'autre et rebaser avant la revue.
- Pas de nouvelle dépendance Python ou JS sans accord d'Anaël.
- Le Journal reste borné en mémoire comme le journal de sécurité actuel. Une entrée d'appel ne stocke ni le prompt ni la réponse.
- Les sélecteurs E2E existants restent valides, ou bien la story réaligne les scénarios qu'elle casse.

## Non-goals

- Guider la recette des sous-onglets RAG : session dédiée après le lot.
- Refondre d'autres onglets que Sécurité.
- Persister le Journal sur disque ou l'exporter.
- Changer le modèle de la séance depuis l'onglet RAG.

## Success signal

- Anaël rejoue ses retours du 27/10 onglet par onglet sur la version livrée. Aucun ne se reproduit, et la version est publiée (tag et release).

## Assumptions

- Les couleurs vert et violet de la génération alternent sans porter de sens. On les garde pour séparer les tokens voisins et une légende l'explique.
- « Place de marché » devient « marketplace » en français.

## Open Questions

- Étape 1 du LLM : d'après le code, le découpage lit bien la saisie (`llm.js:462`). Reproduire le défaut en direct au début de la story ; s'il ne se reproduit pas, ne rien changer.
- Le retour sur la carte du harnais s'arrête sur « Peut-être » : qu'ajouter ?
- CAP-9 : la recherche web du 27/10 n'a trouvé aucun serveur public qui expose réellement une ressource et un prompt. DeepWiki et Context7 annoncent les deux mais renvoient des listes vides ; Hugging Face et modelcontextprotocol.io n'ont que des ressources. Deux choix : un serveur public à ressources seulement, ou un petit serveur maison en Streamable HTTP lancé en local. À trancher à la relecture de la spec de la story 6.
- CAP-8 : les logos sont des marques soumises à conditions (GitHub, Microsoft, Marianne réservée à l'État) et le dépôt est public. Vérifier ces conditions et préférer le logo propre du service à la Marianne.
