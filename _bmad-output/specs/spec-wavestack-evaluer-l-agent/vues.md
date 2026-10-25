# Vues : « En faire un cas » et « Évaluer l'agent » (CAP-3, CAP-4)

Maquette statique : `maquette-evaluer-l-agent.html` (vrais tokens du dépôt, données fictives, s'ouvre en `file://`). Elle fait foi pour la disposition ; ce fichier fait foi pour le comportement. Textes en français, clés dans `content/ui.yaml` (`main.agent_eval.*`), surcouches en et de.

## Formulaire « En faire un cas » (story 3)

- **Entrée** : « En faire un cas » dans les actions d'un tour terminé de la Vue humain (tour de message, pas de compaction, pas un tour joué par une exécution). Tiroir sur la Vue humain, comme le tiroir du prompt système.
- **Pré-rempli depuis le journal** (au `seq` du `turn_started` d'origine) :
  - prompt (modifiable) ;
  - configuration en lecture seule : briques, sous-options, fenêtre, modèle ;
  - « Reprendre l'historique (N échanges) », coché si le tour avait un historique ;
  - « Figer ce prompt système dans le cas », décoché ;
  - outils appelés, dans l'ordre, avec leurs arguments ;
  - plafond d'appels proposé : appels du tour d'origine, modifiable.
- **Saisie** : titre, symptôme (obligatoire), assertion (obligatoire), une ou deux vérifications. Chaque vérification : un type du catalogue puis ses paramètres, pré-remplis depuis le tour (outil ou hook vu dans le tour, argument et valeur).
- **Verdict immédiat** : à chaque changement, `verify` tourne côté serveur sur les enveloppes du tour d'origine, sans appel au modèle.
  - Le tour échoue au cas : « Le tour d'origine échoue bien à ce cas », la vérification fautive nommée.
  - Le tour réussit : avertissement « Ce cas ne peut pas échouer sur ce tour », enregistrement toujours possible.
  - Tour absent du journal (relance de WaveStack) : l'action n'est pas proposée.
- **Enregistrer** : écrit dans `agent_cases.json`, provenance `séance`, puis « Cas enregistré · Ouvrir Évaluer l'agent ». « Annuler » ferme sans écrire ; un tiroir modifié demande « Abandonner » comme le tiroir du prompt système.
- **E2E** : faux moteur ; un tour qui appelle un outil ; « En faire un cas » ; `tool_not_called` sur cet outil → « échoue bien » ; changer en `tool_called` → avertissement ; enregistrer ; le cas apparaît dans la vue.

## Vue « Évaluer l'agent » (story 4)

- **Entrée** : bouton « Évaluer l'agent » dans la barre du haut. Panneau sur Contexte LLM et Orchestration ; la Vue humain reste visible et montre les tours des cas en direct, chacun avec le badge « Cas : titre ».
- **En-tête** : modèle courant, prompt système (début, et « par défaut » ou « modifié »), bandeau « Démonstration, pas un banc : quelques cas, un petit modèle, des résultats qui varient ».
- **Liste des cas** : deux groupes, « Suite fournie » et « Mes cas ». Par cas : titre, brique, symptôme, plafond, « Lancer », et pour un cas de séance « Supprimer ». En bas de « Mes cas » : « Effacer mes cas », avec confirmation dans la page (« Effacer les N cas de séance ? Les cas fournis restent. »).
- **Lancer** :
  - « Lancer la suite » : tous les cas, dans l'ordre, k = 1.
  - « Lancer » sur un cas, avec le choix « 1 essai » ou « 3 essais ».
  - Avant le premier lancement de la séance : « La conversation sera vidée ; votre configuration est rétablie à la fin. » (une fois).
- **Pendant l'exécution** : barre « Cas 3 sur 8 », cas courant marqué « en cours », « Arrêter » (le bouton existant de la session l'arrête aussi). Les autres intentions sont refusées avec leur raison.
- **Résultat par cas** :
  - « Réussi » ou « Échoué » ; pour un échec, la vérification fautive et sa raison (« 4 appels au modèle pour un plafond de 3 ») ;
  - « Non lancé » avec sa raison : fenêtre exigée (« demande une fenêtre de 4 096 tokens »), arrêté, plafond de dépense atteint ;
  - « Voir le tour » déplie la trace du cas : messages, appels d'outil avec arguments, décisions de hook, validations, appels au modèle, réponse ; l'événement qui a fait échouer est encadré ;
  - k = 3 : « 2 réussis sur 3 · pass@3 : oui · pass^3 : non », un rond par essai.
- **Exécutions** : liste des exécutions de la séance (heure, modèle, prompt système, « 6 réussis sur 8 lancés »). Les agrégats ne s'affichent qu'ici.
- **Comparer** : choisir deux exécutions A et B. Tableau cas par cas : A, B, et « régressé », « corrigé », « inchangé » ou « absent d'une exécution ». En tête : ce qui diffère entre A et B (modèle, prompt système). Deux exécutions sans changement entre elles : « Rejeu témoin : ce qui change ici vient du modèle, pas de vous. »
- **Vide** : aucune exécution : « Lancez la suite pour obtenir une première exécution. »
- **E2E** : faux moteur ; lancer la suite (au moins un réussi, un échoué, un non lancé pour la fenêtre) ; « Voir le tour » sur l'échec ; 3 essais sur un cas ; changer de prompt système, relancer, comparer ; arrêter une exécution ; « Effacer mes cas ».
