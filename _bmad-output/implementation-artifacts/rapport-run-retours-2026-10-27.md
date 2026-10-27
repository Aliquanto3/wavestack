# Rapport du run des retours du 27/10 (v1.7.0)

Run autonome du 2026-10-27, de 06:10 à environ 14:30, orchestré par Opus 5.5. Journal détaillé : [run-autonome.md](run-autonome.md). Spec : `_bmad-output/specs/spec-wavestack-retours-2026-10-27/`.

## Livré

| Story | Titre | PR | Commit |
|---|---|---|---|
| 16.1 | Bilan et Journal de la barre | #153 | b2e06428 |
| 16.2 | Atelier LLM, prompt envoyé, légende, fragment, coût et empreinte | #149 | 117863cb |
| 16.3 | Atelier MCP, logos, réponse en entier, schéma Avant/Avec | #150 | 72832fb8 |
| 16.4 | Maquette de l'onglet Sécurité (validée par Anaël) | #148 | 41ff7916 |
| 16.5 | Carte du harnais et panneau des briques | #151 | c8e2d116 |
| 16.7 | Onglet Sécurité refondu | #155 | b35ca5b2 |
| 16.8 | Retrait des actions forcées | #154 | 56b91cc3 |
| 16.9 | Atelier RAG, modèle de génération et fenêtre de contexte | #152 | 6ae6d8bf |

Annulée : 16.6 (serveur MCP avec ressource et prompt), aucun serveur public ne les expose réellement (DeepWiki et Context7 vérifiés le 27/10 : listes vides).

Chaque story : second avis Haiku, revue Opus (1 à 3 passes), CI verte sur 3 OS, E2E ciblés lancés un par un par l'orchestrateur.

## Décisions d'Anaël pendant le run

- Specs 16.1, 16.8, 16.9 : recommandations retenues, sauf 16.9 Q1 (un modèle local choisi dans le RAG change le modèle de toute l'application).
- Montants en dollars ; « — » pour le modèle des appels du diagnostic dans le Journal.
- g CO₂e affichés aussi pour un modèle local dans l'Atelier LLM.
- Logos : GitHub officiel (Invertocat noir et blanc) ; Microsoft Learn et data.gouv.fr en pictogramme neutre (licence requise, Marque d'État). Conditions dans `docs/logos-atelier-mcp.md`.
- Démo Caveman refaite par un second prompt qui fait charger le skill par le modèle.
- « Ruhe » pour l'état au repos de la légende allemande ; « Peut-être » de la carte du harnais sans suite.

## À revoir ou reporté

- Raison de Contexte long et du CAG grisés : le texte renvoie au sélecteur « Fenêtre » de la page Conversation, alors qu'il est aussi dans l'atelier RAG (fr, en, de).
- Séparateur « ; » des sources de la carte du harnais écrit à la française en anglais et en allemand.
- Journal de la barre : un appel qui se termine pendant une navigation entre pages est manqué ; les Journaux de deux navigateurs ouverts sur la même séance peuvent différer.
- Changement de langue : la reconnexion synchrone du serveur MCP local dépasse 10 s sur un poste saturé (échec E2E `content_language` sous charge).
- Démo Caveman : un petit modèle local peut ignorer la consigne de charger le skill ; les E2E passent avec un faux fournisseur.

## Tests manuels conseillés (recette)

1. Barre : Bilan et Journal sur chaque onglet, filtre « Sécurité seulement », « Voir plus », largeur 360 px.
2. Atelier LLM : étape 6 avec un modèle cloud puis local (prompt envoyé, légende, coût et empreinte).
3. Atelier MCP : logos en thème clair et sombre, réponse en entier, schéma Avant/Avec.
4. Atelier RAG (recette guidée dédiée prévue) : modèle cloud et local dans l'étape Génération, fenêtre réglée depuis l'onglet, raisons du CAG et de Contexte long.
5. Onglet Sécurité : cartes, chemin d'un message, filtres, dépli de la matrice au clavier, légende.
6. Démo Caveman avec un vrai modèle local.

## Enseignements du run

- 4 créneaux en parallèle saturent un poste de 16 Go : plusieurs E2E ont échoué sous charge sans défaut de code. Relancer seul, et comparer à main avant d'attribuer un échec.
- Les E2E partagent un port : un seul à la fois, y compris ceux des reviewers.
- `PYTHONUTF8=1` est obligatoire pour les E2E sous Windows.
- Défaut croisé trouvé seulement à l'E2E : plafond de termes du glossaire (16.2 + 16.5).
