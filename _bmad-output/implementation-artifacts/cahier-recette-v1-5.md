# Cahier de recette V1.5 « Évaluer l'agent », incrément 1 (1.6.2)

Préparé le 2026-10-26 à partir de [rapport-run-v1-5.md](rapport-run-v1-5.md). Il couvre ce que les tests automatiques ne couvrent pas : un modèle réel, le réseau, un fournisseur cloud et la lecture humaine. Pour chaque test, cocher la case et noter l'écart constaté. Un écart devient un correctif 1.6.x.

## Décisions « à revoir » tranchées par Anaël (2026-10-26)

| # | Story | Décision du run | Verdict |
|---|---|---|---|
| D1 | 15.2 à 15.4 | Le reviewer tranche les points de contrôle de spec et journalise « à revoir » | Gardée, règle conservée pour les prochains runs |
| D2 | 15.2 | Cas issu de recette : boucle de `get_datetime` (R22, Mistral), gardé comme cas de régression | Gardée |
| D3 | 15.3 | Tout tour de message fini est éligible à « En faire un cas », annulé ou arrêté compris (« tour non abouti ») | Gardée |
| D4 | 15.4 | En 3 essais, « Réussi » à la majorité stricte (2 sur 3), pass@3 et pass^3 affichés à côté | Gardée |
| D5 | 15.4 | Un id de configuration inconnu est ignoré et montré (« Joué sans : … »), sans raison `config` | Gardée |
| D6 | 15.4 | Un cas « Non lancé » des deux côtés compte comme « inchangé » dans la comparaison | Gardée |
| D7 | 15.5 | Libellé allemand « Agent bewerten öffnen » sans guillemets internes | **Changée** : „Agent bewerten“ öffnen |

**Correctif D7, livré en 1.6.2** (PR #146) :
- `content/i18n/de/ui.yaml:607` : `open_view: "„Agent bewerten“ öffnen"` ;
- `content/i18n/de/scenarios.yaml:603` : citation du libellé. Imbriqué dans des guillemets allemands, le nom s'écrit avec des guillemets simples : „‚Agent bewerten‘ öffnen“. Vérifier ce qu'accepte le décompte des libellés cités ;
- `uv run pytest -q --tb=short tests/test_content_language.py tests/test_agent_eval_ui.py`, puis le scénario E2E `agent_case_form` (tiroir en allemand).

---

## A. Sur ce poste (poste de développement)

Prérequis : WaveStack 1.6.2 lancé depuis `main`, un modèle local chargé, le réseau ouvert et une clé d'API cloud valide pour A3.

### A1. Glossaire depuis les six pages
- [ ] Ouvrir « Glossaire » depuis chacune des six pages : principale, Diagnostic, Atelier LLM, MCP, RAG, Sécurité.
- Attendu : le panneau « Glossaire du harnais » s'ouvre sur chaque page. « Chercher un terme » filtre la liste, et un terme absent affiche « Aucun terme ne correspond. ». « Fermer » et Échap le ferment, et le focus revient au bouton.
- [ ] Refaire le test sur deux pages en anglais et en allemand.
- Écart constaté :

### A2. Citations cliquables du module 9
- [ ] Dans le programme, module « Évaluer l'agent », ouvrir les quatre scénarios et cliquer sur chaque terme lié : harnais, démo, banc d'essai, régression, journal, cas d'agent, vérification, verdict, plafond d'appels, provenance, rejeu témoin, pass@3, pass^3, rejeu, déterministe, juge LLM.
- Attendu : chaque clic ouvre le glossaire sur le bon terme, et aucun lien n'est mort.
- [ ] Faire de même en allemand, correctif D7 compris : le bouton du tiroir s'appelle „Agent bewerten“ öffnen, et le texte du scénario le cite à l'identique.
- Écart constaté :

### A3. Plafond `max_session_usd` atteint au milieu d'un cas (modèle cloud)
1. [ ] Avec le plafond par défaut (5 $), choisir un modèle cloud et lancer une fois le cas `delegation_sous_agent` (5 appels au plus). Relever le coût d'un appel dans FinOps.
2. [ ] Arrêter WaveStack. Dans `settings.json` du dossier de données, poser `"finops": {"max_session_usd": X}`, avec X compris entre le coût d'un appel et celui de deux. Relancer WaveStack, puis reprendre le même modèle cloud.
3. [ ] Dans « Évaluer l'agent », lancer ce cas seul, puis lancer la suite.
- Attendu : le premier appel part et l'appel qui dépasse le plafond n'est pas envoyé. Le cas est « Non lancé » avec la raison « plafond de dépense atteint (X) », jamais « Échoué ». La ligne de l'exécution affiche « · plafond de dépense atteint ». FinOps ne montre aucun appel payant après le refus, et la configuration de la séance est rétablie à la fin.
- À noter : ce qui arrive aux cas suivants de la suite (non lancés ou lancés).
4. [ ] Remettre `max_session_usd` à sa valeur et relancer WaveStack.
- Écart constaté :

### A4. Cas en `approval: approve` (H5 accepté, réseau ouvert)
1. [ ] Allumer Outils (`get_datetime`, `public_holidays`) et Hooks (H1, H2, H5). Envoyer « Quels sont les jours fériés en France en 2026 ? » et accepter la validation H5.
2. [ ] Sous le tour, cliquer « En faire un cas ». Attendu : « Validation humaine (H5) pendant l'exécution » est pré-réglé sur « accepter », comme le dit le journal.
3. [ ] Poser les deux vérifications (le tiroir en accepte deux au plus) : « Hook qui décide » (H5, demande l'accord) et « Outil appelé » (`public_holidays`). Le verdict ne doit pas dire « Le tour d'origine échoue bien à ce cas. », car le tour d'origine réussit. Enregistrer.
4. [ ] Lancer le cas dans « Évaluer l'agent ».
- Attendu : aucune demande de validation n'apparaît pendant l'exécution, puisque le harnais accepte H5 à la place du formateur. `public_holidays` part sur le réseau et le cas est « Réussi ». « Voir le tour » montre la décision H5, puis l'appel de l'outil.
5. [ ] Contre-épreuve : passer le cas sur « refuser » et le relancer. Attendu : « Échoué » sur « Outil appelé ».
- Écart constaté :

### A5. Cas Talvane et fenêtre de contexte
1. [ ] Choisir 8 192 dans « Fenêtre ▾ » (le modèle se recharge), puis lancer la suite.
- Attendu : `code_talvane_apres_compaction` est « Non lancé », avec « demande une fenêtre de 4096 tokens (fenêtre courante : 8192) » et la consigne « Pour le jouer, choisissez cette fenêtre dans « Fenêtre ▾ »… ». L'exécution ne recharge pas le modèle d'elle-même.
2. [ ] Relancer la suite sans rien changer, puis « Comparer A et B ». Attendu (D6) : la ligne Talvane est « inchangé ».
3. [ ] Revenir à 4 096 et relancer ce cas seul. Attendu : il est joué, avec une compaction visible dans « Voir le tour ».
- Écart constaté :

### A6. Tour arrêté et « En faire un cas » (D3)
- [ ] Envoyer un prompt, cliquer « Arrêter » pendant le tour, puis cliquer « En faire un cas ».
- Attendu : le bouton est proposé. Le tiroir affiche « Ce tour s'est terminé sans aboutir (« … ») : sur lui, toutes les vérifications échouent (« tour incomplet »)… », et la première vérification proposée est « Tour fini sans erreur ».
- Écart constaté :

---

## B. Sur le PC cible (16 Go, CPU seul)

Prérequis : WaveStack 1.6.1 installé comme chez un stagiaire, le modèle local par défaut, la fenêtre par défaut (4 096).

### B1. Mesure des plafonds des 8 cas fournis
1. [ ] Fermer WaveStack, pour ne pas charger deux modèles sur 16 Go.
2. [ ] Lancer `uv run python tools/eval/measure_cases.py --runs 3 --json mesures-pc-cible.json`. Un essai peut durer jusqu'à 15 minutes : prévoir la durée en conséquence.
3. [ ] Lire le tableau. Attendu : un plafond proposé (max des essais réussis + 1) pour 7 cas. `h5_refuse_sans_rappel` reste à 2 (plafond fixé par le contrat), et aucun cas n'est « non mesurable ici » (la fenêtre est à 4 096).
4. [ ] Pour un cas sans essai réussi, noter ses appels et ses erreurs, sans recopier de plafond : c'est un constat de recette.
5. [ ] Recopier les lignes `max_model_calls: N` dans `content/agent_cases.yaml`, `content/i18n/en/agent_cases.yaml` et `content/i18n/de/agent_cases.yaml`, sauf H5. Retirer la mention « PLAFONDS PROVISOIRES » de l'en-tête, puis lancer `uv run pytest -q --tb=short tests/test_agent_cases_provided.py`.

| Cas | Appels (essais 1/2/3) | Réussis | Plafond fichier | Plafond proposé | Retenu |
|---|---|---|---|---|---|
| heure_get_datetime | | | 3 | | |
| chemin_invente | | | 4 | | |
| h1_bloque_confidentiel | | | 3 | | |
| memoire_globale_prenom | | | 2 | | |
| code_talvane_apres_compaction | | | 3 | | |
| delegation_sous_agent | | | 5 | | |
| recherche_avant_lecture | | | 4 | | |
| h5_refuse_sans_rappel | | | 2 | — (contrat) | 2 |

### B2. Parcours du module 9 avec le modèle local
Jouer les quatre scénarios dans l'ordre depuis le programme, comme un stagiaire, chronomètre en main (durée prévue : 45 minutes).

1. [ ] **Faire échouer l'agent** (`eval_fail`). Envoyer les deux prompts. Attendu : le premier tour échoue de façon visible (chemin inventé ou réponse sans lecture), le deuxième réussit. Noter le comportement observé. Si le premier tour réussit, relancer jusqu'à trois fois et noter le nombre d'essais.
2. [ ] **Transformer l'échec en cas** (`eval_case`). Cliquer « En faire un cas », remplir le Symptôme et l'Assertion, et poser les deux vérifications du scénario. Attendu : « Le tour d'origine échoue bien à ce cas. ». Retirer la première vérification : « Ce cas ne peut pas échouer sur ce tour. » apparaît si le tour a lu un chemin inventé. La remettre, cliquer « Enregistrer », puis « Ouvrir Évaluer l'agent ». Le cas est dans « Mes cas », mis en évidence.
3. [ ] **Lancer la suite** (`eval_suite`). La page prévient que la conversation sera vidée, puis on clique « Lancer ». Attendu : huit cas fournis et le cas de séance, chacun avec son badge dans la Vue humain. Relever le temps total et le nombre de « Réussi », d'échecs et de « Non lancé ». Pour un échec, cliquer « Voir le tour » : l'événement fautif doit être encadré.
4. [ ] **Rejeu témoin**. Relancer la suite sans rien changer, puis « Comparer A et B ». Attendu : l'en-tête annonce le rejeu témoin (rien ne diffère). Noter le nombre de cas « corrigé » ou « régressé » : c'est le bruit du modèle.
5. [ ] **Trois essais d'un même cas**. Choisir un cas instable vu à l'étape 4 (sinon `chemin_invente`), puis « 3 essais » et « Lancer ». Attendu (D4) : « N réussis sur 3 · pass@3 : … · pass^3 : … », et « Réussi » seulement si au moins 2 essais sur 3 réussissent. Relever le temps.
6. [ ] **Changer, relancer, comparer** (`eval_compare`). Dans le tiroir du prompt système, ajouter « Liste toujours le dossier avant de lire un fichier. », relancer la suite, puis comparer la référence (A) et la nouvelle exécution (B). Attendu : « Diffère : prompt système. ». Chaque ligne est « corrigé », « régressé » ou « inchangé ». Comparer l'écart au bruit de l'étape 4.
7. [ ] **Effacer mes cas**. Attendu : une confirmation dans la page, « Mes cas » vide, et les cas fournis toujours là.
8. [ ] **Lecture pédagogique**. Les textes du module se comprennent-ils sans formateur ? La durée de 45 minutes tient-elle avec les temps d'exécution relevés aux étapes 3 à 6 ?
- Écarts constatés :

| Mesure | Valeur |
|---|---|
| Durée d'une suite (étape 3) | |
| Bruit du rejeu témoin (corrigés + régressés) | |
| Durée de 3 essais d'un cas | |
| Durée totale du module | |

---

## Après la recette
- Consigner les résultats dans `resultats-recette-v1-5-2026-10.md`, puis ouvrir un correctif 1.6.x pour les écarts.
- Commiter les plafonds mesurés sur une branche de story, et publier la version suivante avec ses notes.
- Ensuite seulement, Anaël décide s'il rouvre l'incrément 2.
