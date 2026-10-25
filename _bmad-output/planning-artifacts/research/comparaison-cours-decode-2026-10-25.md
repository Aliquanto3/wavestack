# Comparaison : cours « Building a Coding Agent From Scratch » et WaveStack

- **Date** : 2026-10-25
- **Source** : dépôt `decodingai-magazine/building-a-coding-agent-from-scratch-course` (agent « decode », Apache-2.0, créé en juin 2026, mis à jour le 2026-10-24), lu par `gh api` : README, ADR, `evals/`, `src/decode/`. Articles 4, 5 et 8 lus en partie ; articles 1 et 7 non lus.
- **Base WaveStack** : `main` = `fce4f8bb` (#131), après la livraison des lots V1.3, V1.4 et V1.2 (version 1.5.0).
- **Suite** : `../sprint-change-proposal-2026-10-25-evaluer-l-agent.md`.

## Verdict d'ensemble

decode est à l'état de l'art des harnais de code en 2026. Il couvre la boucle, la sécurité d'exécution et surtout l'évaluation, plus en profondeur que WaveStack. WaveStack est plus large : RAG, MCP, cache, compression, conformité, trois langues. Le cours n'a ni RAG, ni cache visible, ni garde-fous de contenu.

Trois réserves :
- les choix d'outillage suivent les sponsors (Modal, Opik, Kitaru) ;
- les auteurs disent s'être appuyés sur le code fuité de Claude Code : on cite leurs articles et leurs ADR, sans reprendre ce qui vient de la fuite ;
- le chiffre d'accroche (Terminal-Bench, de la 30e place au top 5 en changeant seulement de harnais) vient d'un billet de LangChain, non vérifié ici.

L'écart principal tient en une phrase : **WaveStack sait évaluer un RAG, il ne sait pas évaluer un agent.**

## Comparaison par sujet

Légende du verdict : **Lot** = retenu dans l'incrément 1, **Incr. 2** = retenu sous condition, **Contenu** = texte seulement, **Non** = écarté.

| # | Sujet | decode | WaveStack aujourd'hui | Écart | Faisable sur CPU avec un 2B ? | Verdict |
|---|---|---|---|---|---|---|
| 1 | Cas de régression d'agent | Un cas est une donnée (`RegressionCase`) : prompt, fixture, métriques, `max_requests`, `symptom`, `assertion`, provenance. 21 cas inventés et 2 extraits. 12 métriques déterministes lues dans l'historique des messages (outil appelé ou non, arguments, nombre d'appels, fichier, sortie), plus un juge G-Eval sur 3 cas seulement. | Seules des traces existent : environ 130 types d'événements (`trace/catalog.py`), dont `ToolStarted`, `HookDecided`, `ApprovalRequested`, `SubagentStarted` et `HistoryCompacted`. Aucun cas, aucun score sur la boucle de l'agent. | Total. | Oui. Les métriques déterministes ne demandent aucun modèle, et le journal d'événements les porte déjà. | **Lot** |
| 2 | De la trace ratée au cas | `evals mine` regroupe les traces en échec par signature (erreur, dernier outil, modèle). Un humain lit la trace et écrit le cas, avec sa trace d'origine et le commit qui le corrige. Le dossier `mining/NOTES.md` explique pourquoi des traces sont écartées : « un cas qui ne peut pas échouer ne prouve rien ». | Le rejeu du dernier prompt existe (story 9b). Le journal est en mémoire seulement (AD-2) : il n'est ni exporté, ni rechargé, pour le chat principal. | Total. | Oui : il suffit d'un bouton sur un tour et d'un fichier de cas. | **Lot** |
| 3 | Banc d'essai ou régression | Le banc mesure le résultat (19 tâches, vérificateur caché, pass@k). La régression vérifie le comportement voulu. « Les démos prouvent que ça impressionne, le banc que ça marche, les sondes que ça marche comme on l'a conçu. » Un contrôle sans clé vérifie que la solution de référence réussit et que « ne rien faire » échoue. | L'évaluation RAG existe (V1.2 story 15) : recall@k, MRR, juges, panel local et cloud, agrégats dans la vue Évaluer. | Notions absentes pour l'agent. | Le banc à vérificateur demande un bac à sable et git : trop lourd. Le contrôle dans les deux sens se fait avec le faux moteur. | **Lot** (contrôle dans les deux sens), **Contenu** (banc) |
| 4 | Plafond d'appels « observé, jamais deviné » | `max_requests` = maximum de 3 exécutions + 1. Un cas qui demande bien plus que ses voisins est cassé. | Bornes de boucle globales (`LimitReached`), aucune par cas. | Partiel. | Oui. | **Lot** (champ du cas et texte) |
| 5 | Non-déterminisme, pass@k | pass@k et pass^k sur k essais. Rejeu « témoin », sans changement, avant de changer de modèle : « trois exécutions, pas deux ». | Rejeu, changement de modèle à chaud (story 17) et comparaison côte à côte de deux tours : c'est déjà le geste manuel. Pas de k essais, pas de score. | Partiel. | k = 3 sur un cas court reste raisonnable sur CPU ; sur toute la suite, non. | **Lot** (k essais sur un cas, rejeu témoin dans un scénario) |
| 6 | Rejeu avec outils figés | Le rejeu Kitaru fige les observations des outils et ne fait varier que le modèle ou le prompt. Un nouvel essai, lui, réexécute les outils dans un monde qui a changé. | Le rejeu réexécute les outils (`get_datetime` change, une page web aussi). | Partiel. | Oui, mais c'est un mécanisme de plus dans `app_session.py`. | **Contenu** (la différence se dit). Le mécanisme est reporté. |
| 7 | Juge LLM | G-Eval, avec des critères rédigés en qualitatif : des ancres numériques « 1,0 / 0,0 » ont donné 0,1 à une réponse parfaite. Seuil de 0,7 pour les juges, de 0,8 pour les métriques déterministes. | Les juges RAG existent. Qwen3.5-2B n'est pas viable comme juge (H7 à 64 %, rapport du 2026-10-25). | Infrastructure déjà là. | Non en local ; oui avec un modèle cloud. | **Non** dans l'incrément 1. Le principe de la V2 s'applique : montrer l'erreur dans la trace, pas par la qualité de la réponse. |
| 8 | Porte de permissions | Modes (défaut, plan, édition, sans confirmation) × sortes d'outils, et règles `Outil(motif)` dans l'ordre refuser → autoriser → mode → demander. Pause pour accord, et réponse « toujours » enregistrée. | H5 met l'outil réseau en pause avec trois boutons (stories 8b et 8c). H1 est une règle codée en dur sur `confidentiel/`. Aucune règle configurable. Les modes de permission sont un non-objectif de la V1.4. | Les règles. Les modes n'ont pas de sens ici : aucun outil de WaveStack ne modifie quoi que ce soit (`content/tools.yaml`). | Oui, c'est du Python déterministe. | **Incr. 2** (règles seulement, décision d'Anaël sur le non-objectif) |
| 9 | Planification (`todo_write`) | Liste complète remplacée à chaque appel ; états à faire, en cours, fait ; affichée comme une liste à cocher. Le cas 08 vérifie que l'agent s'en sert. Mode plan lecture seule, avec sortie validée par l'humain. | Absente (aucune occurrence). | Total. | Inconnu : rien ne dit que Qwen3.5-2B appellera l'outil avant d'agir. decode n'a pas de mesure sur un petit modèle (le sien a 35B). | **Incr. 2**, après un test préalable |
| 10 | Sous-agents | Même boucle relancée avec des dépendances neuves et des outils en lecture seule. Lancement de 1 à 6 briefs en parallèle (4 au plus), concaténation sans appel de synthèse. Rapport refusé s'il est vide ou si l'enfant n'a appelé aucun outil, avec une seule relance. Catalogue d'agents en markdown (build, plan, explore, relecteur). | Un seul sous-agent `delegate(task)`, séquentiel, 4 appels au plus, sans rôle (story 19). | Partiel. | En séquence, oui. Le parallèle n'est pas possible avec un seul modèle chargé. Le point dur est que le parent doit écrire 3 briefs distincts. | **Incr. 2** |
| 11 | Compaction | Deux paliers : retrait des anciens résultats d'outils sans appel au modèle à environ 60 %, résumé structuré à environ 80 %. Résumé en sections : but, contraintes, avancement, décisions, suite. ADR-0018 : la jauge lisait une somme cumulée, et une coupure mal placée revenait à l'index 0. | Compaction et fenêtre glissante, au débordement ou à la demande (V1.4 story 4). Aucun seuil en pourcentage. Le retrait des résultats d'outils reste du texte (non-objectif de la V1.4). | Partiel. | Oui : le palier sans appel est le plus simple à porter. | **Incr. 2** (seuils et palier sans appel), **Contenu** (pourquoi pas à la limite) |
| 12 | Survie à la compaction | Cas 16 : un code posé au premier tour, une fenêtre forcée petite, une vérification « la réponse contient le code ». | Fenêtre de 4 096 tokens réglable. Un document sentinelle existe déjà (Projet Talvane, code `TLV-7731-QZ`). | Rien à construire en plus du cas. | Oui, et la petite fenêtre est notre réglage normal. | **Lot** (un cas de la suite fournie) |
| 13 | File de réorientation, mémoire de fin de session | Messages injectés entre deux appels au modèle ; à la sortie, une phrase datée ajoutée à `MEMORY.md`. | Mémoire globale (story 14), intentions refusées hors `idle` (AD-3). | Faible intérêt pédagogique ici. | — | **Non** |
| 14 | Bac à sable, LSP, essaim distant, Opik, Kitaru | Docker ou Modal, serveur LSP, Modal headless (CLI, webhook, cron), service sur H200. | Rappel d'une ligne (V1.4 CAP-2). | Hors contraintes. | Non (pas de droits administrateur, pas de GPU, hors ligne). | **Non** |
| 15 | Dispositifs pédagogiques | Un glossaire d'environ 90 termes ; un schéma par leçon montrant la pièce ajoutée ; « l'agent tient en 20 lignes, le reste est le harnais » ; des démos d'une touche ; chaque ADR se termine par « ce qui justifierait d'y revenir » ; un cas porte `symptom` et `assertion`. | Pas de glossaire d'application. La carte du harnais ne montre pas ce qu'ajoute le module en cours. Les scénarios jouent le rôle des démos. | Partiel. | Oui. | **Lot** (glossaire, accroche), **Incr. 2** (carte) |

## Ce que WaveStack a et que decode n'a pas

RAG et ses variantes, avec diagnostic du bon extrait avant la génération ; MCP au niveau du protocole ; cache visible et sa jauge ; compression (Headroom, Caveman) ; garde-fous de contenu ; données sortantes visibles ; FinOps et GreenOps ; trois langues ; un programme guidé de 7 h. Le lot proposé n'enlève rien à cela.

## Pièges documentés par decode, à reprendre

- Un cas doit pouvoir échouer : on le vérifie dans les deux sens, avant de le livrer.
- Une métrique absente d'une exécution n'est pas comptée comme réussie ; une suite vide ne doit pas passer en silence.
- Le plafond d'appels se mesure, il ne se devine pas.
- Un juge dont les critères portent des ancres numériques note n'importe quoi.
- Une compaction qui ne se déclenche jamais vient souvent d'un mauvais compte de tokens, pas du seuil.
