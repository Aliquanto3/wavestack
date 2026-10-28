# Rapport du run : corrections de la recette v1.7.0 (v1.7.1)

Run du 2026-10-27 15:27 au 2026-10-28 08:00, en pause pendant la démo d'Anaël. Journal et décisions : [run-autonome.md](run-autonome.md). Spec : `_bmad-output/specs/spec-wavestack-recette-v1-7-0/`.

## Livré

| Story | PR | Contenu |
|---|---|---|
| 17.1 | #159 | Barre en dollars, Bilan et Journal lisibles à 360 px, badge offre gratuite |
| 17.2 | #160 | Atelier LLM : « 0 $, offre gratuite » pour un modèle cloud sans prix |
| 17.3 | #161 | Atelier MCP : logos en thème sombre, colonne Modèle qui suit l'hébergement du modèle actif |
| 17.4 | #164 | Atelier RAG : « Contexte long » se libère après « Appliquer » sans recharger, la raison d'un grisé renvoie au bon réglage |
| 17.5 | #162 | Sécurité : règle en pastille, message quand le filtre ne laisse rien |

CI 8/8 sur chaque PR. E2E lancés par l'orchestrateur, un par un : bar_journal bar_panels (35), llm_screen (66), mcp_lab mcp_lab_page (55), security_page (43), rag rag_rerank rag_lab_no_index (90).

## Décisions à revoir

- 17.2 : un modèle gratuit affiche « 0 $, offre gratuite » au lieu de l'empreinte seule.
- 17.3 : libellé cloud « LLM cloud » ; robot sans nom du fournisseur en cloud.
- 17.4 : revue par l'agent `reviewer` (protocole du run) au lieu des trois couches de `bmad-build`.

## Reports

- À 360 px, la page Harnais fait 646 px de large (contenu de la page, hors barre).
- L'Atelier RAG n'indique pas l'offre gratuite (règle propre dans `rag/lab.py`).
- Vue en cartes sous 560 px de la maquette Sécurité absente depuis 16.7.
- CT-06 (Caveman avec un vrai modèle local) : hors run.

## Recette proposée

Rejouer CT-01 à CT-05 sur la v1.7.1 ; vérifier en particulier l'Atelier RAG (fenêtre 4 096 → 16 384 depuis l'onglet, sans recharger) et l'Atelier MCP avec un modèle cloud.
