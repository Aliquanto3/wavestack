---
id: SPEC-wavestack-evaluer-l-agent
companions:
  - contrat-des-cas.md
  - brownfield.md
  - vues.md
  - ../spec-langues/i18n-conventions.md
sources:
  - ../../planning-artifacts/sprint-change-proposal-2026-10-25-evaluer-l-agent.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# WaveStack V1.5 : Évaluer l'agent (incrément 1)

## Why

Pédagogie et opportunité. WaveStack montre ce que fait un agent, tour par tour, mais pas comment vérifier qu'il se comporte comme prévu, ni comment voir qu'un changement de modèle, de prompt système ou de brique l'a dégradé. L'évaluation n'existe que pour le RAG (V1.2 story 15). Le cours « Building a Coding Agent From Scratch » (Decoding AI) consacre deux leçons sur huit à ce sujet : sans tests de régression, on a « peur de changer ses prompts ». C'est aussi le sujet qui manque le plus aux deux publics de la V2 (équipes techniques, gouvernance). Le journal d'événements porte déjà tout ce qu'il faut vérifier, et le rejeu, le changement de modèle et la comparaison existent : on peut enseigner l'évaluation d'agent sans GPU ni juge LLM.

## Capabilities

- **CAP-1** Contrat d'un cas et vérifications sur la trace
  - **intent:** Un cas d'agent est une donnée : un prompt, une configuration, un historique facultatif, une à trois vérifications lues dans le journal du tour, un symptôme, une assertion en une phrase, un plafond d'appels au modèle et une provenance (tour d'origine, date, modèle, « corrigé dans »).
  - **success:**
    - Le catalogue de vérifications est fermé (`contrat-des-cas.md`) : outil appelé (avec ordre facultatif), outil non appelé, argument jamais passé, appels au modèle sous le plafond, texte dans la réponse, hook qui bloque ou demande l'accord, sous-agent appelé, tour fini sans erreur.
    - Chaque vérification est une fonction pure du journal d'un cas, testée sur des journaux construits, dans les deux sens.
    - Une vérification qui ne trouve pas son événement échoue ; un journal sans fin de tour fait échouer toutes les vérifications (« tour incomplet »).
- **CAP-2** Suite de cas fournie
  - **intent:** Le formateur dispose d'environ 8 cas prêts, chacun lié à une brique du programme.
  - **success:**
    - Les cas visés sont ceux de `contrat-des-cas.md` (heure, chemin inventé, H1, mémoire globale, code `TLV-7731-QZ` après compaction en 4 096 tokens, sous-agent, `search_documents` avant `read_file`, H5 puis pas de rappel).
    - Au moins un cas vient d'une vraie défaillance relevée en recette, avec sa provenance.
    - Le plafond d'appels de chaque cas est mesuré (maximum de 3 exécutions sur le modèle local, plus 1), jamais deviné.
    - Un test joue chaque cas avec un faux moteur scripté pour réussir (il réussit) et avec un faux moteur qui ne fait rien (il échoue).
    - fr, en et de.
- **CAP-3** Du tour raté au cas
  - **intent:** Sur un tour du chat principal, le formateur fait « En faire un cas » : un formulaire pré-rempli (prompt, configuration, outils appelés) où il nomme le symptôme et choisit une ou deux vérifications.
  - **success:**
    - Le formulaire dit tout de suite, sans appel au modèle, si le tour d'origine échoue au cas. S'il réussit, il prévient « ce cas ne peut pas échouer sur ce tour ».
    - Le cas est enregistré dans les données de l'utilisateur, avec sa provenance, et survit à la réinitialisation.
    - fr, en et de, avec un E2E.
- **CAP-4** Vue « Évaluer l'agent »
  - **intent:** Le formateur lance la suite, ou un seul cas, sur le modèle courant ; il voit pour chaque cas « réussi », « échoué » ou « non lancé », la vérification fautive et la trace du tour ; il compare deux exécutions, par exemple avant et après un changement de modèle ou de prompt système.
  - **success:**
    - Exécution séquentielle, annulable, arrêtée par le plafond `[finops] max_session_usd` et soumise aux bornes de boucle.
    - k = 1 ou 3 essais sur un cas, avec réussites sur k, pass@k et pass^k.
    - Comparaison de deux exécutions, cas par cas (régressé, corrigé, inchangé, absent).
    - « Effacer mes cas » vide les cas de séance, sans toucher aux cas fournis.
    - Testé avec le faux moteur, avec un E2E.
- **CAP-5** Module 9 « Évaluer l'agent » et contenus
  - **intent:** Le participant fait échouer l'agent, transforme l'échec en cas, change de prompt système ou de modèle, relance la suite ; il apprend à rejouer une première fois sans rien changer avant de comparer.
  - **success:**
    - Un module de 45 min avec 3 ou 4 scénarios ; le programme passe à 9 modules et 7 h 45 partout où il est décrit (`brownfield.md`).
    - Les textes expliquent : démo, banc d'essai et régression ; un plafond d'appels observé, jamais deviné ; le rejeu témoin ; pourquoi le rejeu de WaveStack réexécute les outils, et ce que changeraient des outils figés ; pourquoi on évite ici le juge LLM.
    - L'accroche « l'agent tient en quelques lignes, le reste est le harnais » au module 1.
    - fr, en et de.
- **CAP-6** Glossaire du harnais
  - **intent:** Un glossaire de 40 à 60 termes, ouvert depuis l'interface, que les textes des briques et des scénarios peuvent citer.
  - **success:** fr, en et de ; un test de miroir i18n ; un test qui vérifie que chaque terme cité existe ; un E2E d'ouverture.

## Constraints

- Les vérifications lisent le journal d'événements, jamais la qualité de la réponse : aucun juge LLM, aucun appel au modèle, aucune I/O dans le moteur de vérification (même principe que les hooks, AD-13).
- Le catalogue de vérifications est fermé ; l'étendre est un changement de spec.
- Chaque cas fourni a au moins une vérification qui exige un événement présent ; sinon le faux moteur inactif le ferait réussir.
- Un seul moteur : exécution séquentielle, un cas à la fois, k = 3 seulement sur un cas, jamais sur la suite.
- Le modèle d'une exécution est toujours le modèle courant ; jamais de rechargement du modèle pendant une exécution (un cas qui exige une autre fenêtre est « non lancé »).
- Le prompt système d'une exécution est celui de la session, sauf s'il est figé dans le cas (case du formulaire, décochée par défaut) ; le cas fixe briques, sous-options, fenêtre et historique.
- L'ordre de deux outils se vérifie par l'option `before` de « outil appelé », pas par une vérification de plus.
- Les plafonds des cas fournis restent provisoires jusqu'à leur mesure par Anaël sur le PC cible (point de contrôle de la story 2) ; le cas issu de recette vient d'une recette antérieure au 2026-10-25 (D1).
- Les cas de séance sont des données utilisateur sous `data_dir()`, hors dépôt ; la réinitialisation n'y touche pas (D4).
- Les agrégats (n réussis sur m, pass@k, pass^k) ne s'affichent que dans la vue Évaluer l'agent, en plus de la vue Évaluer du RAG.
- Hors ligne, sur CPU, avec le modèle local ; aucune nouvelle dépendance.
- Textes d'interface et contenus en français, surcouches en et de sous `content/i18n/` (`i18n-conventions.md`).
- Un E2E par nouvel élément visuel (formulaire, vue, glossaire).
- La spec et la proposition se commitent sur une branche de documentation, jamais sur une branche de story.

## Non-goals

- Incrément 2 : planification, sous-agents à rôles, règles de permission, compaction par paliers, carte du harnais (D2, D5).
- Banc d'essai à vérificateur caché, juge LLM dans la régression, modes de permission, rejeu à outils figés, file de réorientation, Opik et Kitaru.
- Épingler un modèle dans un cas.
- Modifier un cas après sa création (on le supprime et on le recrée).
- Persister les résultats d'exécution après un redémarrage, exporter ou importer des cas.
- Évaluer les ateliers LLM, RAG et MCP : seul le chat principal produit et joue des cas.
- Traduire les cas de séance : ils restent dans la langue où ils ont été écrits.

## Success signal

- En formation, hors ligne, avec le modèle local, un participant transforme un tour raté en cas et voit que le tour d'origine y échoue ; change de prompt système ou de modèle, relance la suite et lit cas par cas ce qui a changé ; relance trois fois un même cas et voit que le petit modèle ne réussit pas à chaque fois.
- En CI, chaque cas fourni réussit avec le faux moteur scripté et échoue avec le faux moteur inactif.
