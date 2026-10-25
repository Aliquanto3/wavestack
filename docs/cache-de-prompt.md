# Fiche : le cache de prompt, du bilan d'agent-cost-kit à WaveStack

[← Retour au guide](guide.md#cache-de-prompt) · module 8 « Cache » du programme de formation.

À chaque appel, un agent renvoie au modèle tout son contexte : prompt système, outils,
historique. Le fournisseur (ou le moteur local) garde en cache le début de ce contexte déjà lu,
et ne recalcule que la fin. Le cache est la première ligne de dépense d'un agent : c'est ce que
montre le bilan tokens d'agent-cost-kit, que WaveStack reproduit avec les mêmes mots.

## Les trois cases

| Case du bilan | Ce que c'est | Où la voir dans WaveStack |
|---|---|---|
| **Lecture cache** | Tokens du début du contexte retrouvés dans le cache. Facturés une fraction de l'entrée (un dixième chez Claude). | Jauge « Cache du dernier appel » (« lu »), bilan « Dépense », ligne « Lecture cache » |
| **Écriture cache** (5 min ou 1 h) | Tokens nouveaux mis en cache pour les appels suivants. Facturés plus que l'entrée : ×1,25 pour 5 min, ×2 pour 1 h. | Jauge (« écrit »), lignes « Écriture cache 5 min » et « Écriture cache 1 h » |
| **Non caché** | Tokens d'entrée payés plein tarif, que rien ne met en cache (sous le seuil du fournisseur, ou hors point de cache). | Jauge (« non caché »), ligne « Non caché ». Sans objet en local : le moteur garde tout. |

La sortie (« Sortie ») est à part : le cache ne la touche pas.

## Ce qui se lit comme un cache sain

- La lecture domine l'écriture : chaque appel relit un contexte déjà vu.
- L'écriture ne grossit que du message ajouté.
- Une écriture qui dépasse la lecture signale un cache perdu. WaveStack l'indique dans
  « Cette conversation » (« beaucoup d'écriture : le cache se perd ») en retirant l'écriture
  d'amorçage du premier appel.

## Ce qui casse un cache

Le cache ne réutilise que le **début** du contexte, tant qu'il reste identique octet pour octet.
Tout changement au début réécrit tout ce qui suit. WaveStack nomme la cause (« Cache non
réutilisé » dans Orchestration) : message système modifié (prompt système, mémoire globale,
description d'outil, skill chargé), historique réécrit, brique activée ou désactivée, conversation
vidée, atelier qui a pris le cache du moteur. Règle : le stable d'abord, le variable en dernier.

## Durée de vie

- **En local**, le moteur garde ce qu'il a évalué tant qu'il reste chargé et que personne ne
  l'occupe : pas de « non caché », pas de durée de vie. Le bouton « Vider le cache » (en haut
  du volet « Vue humain ») le fait oublier à la demande, pour montrer l'expiration.
- **Chez Claude**, le cache expire sans lecture : 5 minutes (écriture ×1,25) ou 1 heure
  (écriture ×2). Chaque lecture le prolonge. Le bouton est grisé en cloud, le cache ne se purge pas.
  Réglage dans « Fenêtre », « Cache de prompt de Claude » (désactivé par défaut, grisé sans clé
  Claude). Sous un seuil de tokens propre à chaque modèle, rien n'est mis en cache : tout reste
  « Non caché ». Pour le dépasser dans la démonstration, collez un texte long dans le message.
- Un cache ne vaut que s'il est relu : l'écriture est plus chère que l'entrée, une seule lecture
  ne la paie pas toujours (« surcoût du cache » dans le bilan).

## Lire un bilan d'agent-cost-kit

Lancez `/agent-cost-kit:mesurer-couts` sur un projet, puis comparez case par case avec le
module : lecture très grosse et écriture faible, c'est sain ; écriture proche de la lecture, un
préfixe change ou le cache expire entre deux appels (pause de plus de 5 minutes, sous-agent qui
repart d'un contexte neuf) ; « Non caché » élevé, un contexte trop court pour le seuil.

## Limite

Un tour très long en appels d'outils peut repartir en écriture : le fournisseur ne cherche un
préfixe déjà écrit que sur un nombre limité de blocs avant chaque point de cache.
