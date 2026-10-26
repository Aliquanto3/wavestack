# Rapport du run V1.5 « Évaluer l'agent » (incrément 1)

Run du 2026-10-25 20:50 au 2026-10-26 04:57, journal complet dans [run-autonome.md](run-autonome.md). Spec : `_bmad-output/specs/spec-wavestack-evaluer-l-agent/`. Version publiée : **1.6.0**.

## Fusionné

| Story | Titre | PR | Commit |
|---|---|---|---|
| — | Spec du lot | #134 | 3214fec5 |
| 15.6 | Glossaire du harnais | #135 | 23108ae2 |
| — | Précision de contrat-des-cas.md (témoin non `completed`, cas fourni sans vérification positive) | #136 | 85534df4 |
| 15.1 ★ | Contrat d'un cas et moteur de vérification | #137 | a1f970bc |
| 15.2 | Suite de cas fournie et contrôle dans les deux sens | #138 | f29058e1 |
| 15.3 | « En faire un cas » depuis un tour | #139 | ffd2d60e |
| 15.4 ★ | Vue « Évaluer l'agent », partie 4a (exécuteur et API) | #140 | dd66ed03 |
| 15.4 ★ | Vue « Évaluer l'agent », partie 4b (vue) | #141 | ba5ecfa0 |
| 15.5 | Module 9 « Évaluer l'agent » et contenus | #142 | 64d50dc8 |
| — | Version 1.6.0 (tag annoté v1.6.0, release GitHub) | #143 | bd1dcc11 |

Bloqué : rien. Reporté : rien hors de l'incrément 2 (hors périmètre).

## À faire par Anaël

1. **Mesurer les plafonds** des 8 cas fournis sur le PC cible : `uv run python tools/eval/measure_cases.py --runs 3`, puis recopier les plafonds proposés dans `content/agent_cases.yaml` et ses surcouches `en` et `de` (sauf H5, qui reste à 2).
2. **Décisions prises à ta place, à confirmer** :
   - Points de contrôle de spec (15.2, 15.3, 15.4) tranchés par le reviewer, comme au run précédent.
   - 15.2 : le cas de recette est la boucle de `get_datetime` (R22, Mistral, corrigée R23/R25), avec la brique Raisonnement ; c'est un cas de régression, qui ne se reproduit pas en local. Alternative : une défaillance locale sans correctif (K3, SOC).
   - 15.3 : tout tour de message fini est éligible à « En faire un cas », annulé ou arrêté compris (note « tour non abouti »).
   - 15.4 : un cas à 3 essais est « Réussi » à la majorité stricte (2 sur 3), pass@3 et pass^3 affichés à côté.
   - 15.4 : un id de configuration inconnu dans un cas de séance est ignoré et montré (« Joué sans : … ») ; le contrat n'a pas de raison « non lancé » `config`.
   - 15.4 : dans la comparaison, un cas « non lancé » des deux côtés compte comme « inchangé ».
   - 15.5 : libellé allemand « Agent bewerten öffnen » sans guillemets internes.
3. **Tests manuels de recette** (non couverts par les tests automatiques) :
   - plafond `max_session_usd` atteint au milieu d'un cas, avec un modèle cloud ;
   - cas en `approval: approve` (H5 accepté), réseau ouvert ;
   - parcours du module 9 avec le modèle local : faire échouer, « En faire un cas », rejeu témoin, changer de prompt système, relancer, comparer ; trois essais d'un même cas ;
   - glossaire ouvert depuis les six pages, citations cliquables dans le module 9 ;
   - cas Talvane « Non lancé » quand la fenêtre n'est pas 4 096, puis lancé après le changement de fenêtre.

## Constats du run

- **Second avis Haiku utile** : il a trouvé un défaut grave dans 15.3 (tiroir qui ne se fermait plus) et dans 15.5 (scénario sans l'outil `get_datetime`), et des défauts moyens dans chaque story, tous corrigés à la revue.
- **Point de contrôle de spec utile** : il a fait remonter l'usage d'attributs privés de session par 15.2, remplacés par une API publique dans 15.4, et le découpage de 15.4 en 4a et 4b.
- **Consigne erronée de l'orchestrateur, corrigée en cours** : jouer les cas sur leur fenêtre déclarée cassait le test au faux moteur (1 token par octet) ; les tests restent en 16 384, avec une option réservée aux tests.
- **Piège de l'outil E2E** : `--only` prend des scénarios séparés par des espaces ; avec une virgule, seul le diagnostic tourne et la commande sort en 0.
- **Mémoire du poste** : la surveillance des CI a été arrêtée par Claude Code à 1,1 Go de RAM libre pendant un benchmark ; reprise sur accord d'Anaël.
- Spec commitée sur une branche de story par un reviewer : sortie vers une PR docs (#136).
