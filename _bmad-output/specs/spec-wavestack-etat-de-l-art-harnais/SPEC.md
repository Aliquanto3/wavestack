---
id: SPEC-wavestack-etat-de-l-art-harnais
companions:
  - brownfield.md
  - carte-du-harnais.md
  - maquettes.md
sources:
  - ../../planning-artifacts/sprint-change-proposal-2026-10-24-etat-de-l-art-harnais.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# WaveStack : état de l'art des harnais (lot V1.4)

## Why

L'audit du 2026-10-24 confronte WaveStack au papier du Wavestone AI Lab (Barbaste et al., *Harness Engineering*, arXiv 2609.00006 : 11 harnais de code, 7 sous-systèmes), à Böckeler, OCTO, walkinglabs et SFEIR. WaveStack applique déjà l'essentiel des principes, mais cinq écarts faussent ou appauvrissent le discours tenu à chaque formation :
1. le RAG injecté est présenté comme *la* brique de recherche, alors qu'aucun des 11 harnais n'utilise d'embeddings sur le code ;
2. aucune carte ne situe les briques dans les 7 sous-systèmes ;
3. des catégories de briques contredisent la littérature ;
4. la compaction, standard dans 7 harnais sur 11, est nommée sans être montrée ;
5. des notions récentes manquent.

Le lot corrige ces écarts pour que WaveStack partage avec le papier un vocabulaire et une carte communs.

## Capabilities

- **CAP-1** Disciplines revues (écart 3)
  - **intent:** Le participant comprend que prompt, contexte et harnais s'emboîtent, et voit chaque brique classée selon la littérature.
  - **success:**
    - « Raisonnement » passe en harness engineering (sous-système intégration LLM) ;
    - « Garde-fous » affiche « harness engineering », comme les autres briques ;
    - le guide du harnais explique l'emboîtement prompt ⊂ contexte ⊂ harnais ;
    - fr, en et de ; les tests de miroir i18n et les E2E de la jauge sont verts.
- **CAP-2** Notions récentes (écart 5)
  - **intent:** Le participant rencontre quatre notions récentes là où elles ont du sens.
  - **success:**
    - la brique Prompt système cite les fichiers de contexte hiérarchiques (AGENTS.md, CLAUDE.md) ;
    - le guide du harnais présente les guides et les capteurs (Böckeler), contrôles calculés ou déduits par un modèle ;
    - une consigne de scénario explique que les prompts nomment l'outil parce que le petit modèle en a besoin, et qu'un modèle plus fort se passe de cet échafaudage ;
    - la brique Skills et un scénario de sécurité traitent les skills tiers comme des paquets à vérifier avant installation ;
    - un rappel d'une ligne liste ce que WaveStack ne montre pas : plateformes (ACP, places de marché), bacs à sable au niveau du système d'exploitation, modes de permission.
- **CAP-3** Carte du harnais (écart 2)
  - **intent:** En fin de programme, le participant voit chaque brique placée dans les 7 sous-systèmes du papier, avec son rôle de guide ou de capteur.
  - **success:**
    - chaque brique déclare son sous-système et son rôle, et la carte est générée de ces déclarations ;
    - la carte s'ouvre depuis le scénario `harness_map`, dernier du programme, et depuis le panneau des briques ;
    - le module 6 « Sous-agent et compression » est scindé en « Sous-agent » et « Contexte long et carte » (compression, compaction, carte), chacun entre 30 et 60 min ;
    - un test vérifie que chaque brique a un sous-système et un rôle valides ;
    - la carte cite sa source (arXiv 2609.00006, Böckeler pour les rôles) ;
    - fr, en et de, avec un E2E.
- **CAP-4** RAG injecté ou recherche agentique (écart 1)
  - **intent:** Le participant compare, sur la même question, le RAG qui injecte des extraits à chaque tour et un agent qui cherche dans le corpus avec un outil déterministe, puis lit le passage trouvé.
  - **success:**
    - un outil natif `search_documents` cherche par mots dans le corpus Exemplia et renvoie fichiers et lignes ;
    - `read_file` lit ensuite le document trouvé dans ce corpus ;
    - la brique RAG gagne un paragraphe « RAG injecté ou recherche agentique » (coûts, cas d'usage, ce que font les harnais de code) ;
    - un scénario du module RAG fait la comparaison ; le module passe à 60 min ;
    - testé avec le faux moteur, avec un E2E ;
    - aucune nouvelle dépendance.
- **CAP-5** Compaction et fenêtre glissante (écart 4)
  - **intent:** Au débordement, ou sur demande, le formateur choisit de résumer les anciens échanges (compaction) ou de ne garder que les derniers (fenêtre glissante). Il voit le contexte avant et après, et le cache qui repart en écriture.
  - **success:**
    - avec une fenêtre de 4 096 tokens, une conversation qui déborde propose les deux stratégies au lieu du seul refus ; la stratégie appliquée, le message refusé repart seul ;
    - un bouton « Compacter » propose les mêmes stratégies hors débordement ;
    - la compaction fait un appel de résumé au modèle actif, compté dans les coûts et visible dans l'orchestration ;
    - la fenêtre glissante ne fait aucun appel ;
    - la jauge du cache (V1.3) montre l'écriture, avec la cause « compaction » ou « fenêtre glissante » ;
    - testé avec le faux moteur, avec un E2E ;
    - un scénario dans le module « Contexte long et carte ».

## Constraints

- Pas de nouvelle dépendance.
- Les fichiers carrefour (`ui.yaml`, `messages.yaml`, `scenarios.yaml`, `app.py`, `app.js`, `run_e2e.py`, `trace/catalog.py`) ne reçoivent que des ajouts.
- Textes en fr, en et de.
- Faux moteurs en test, aucun modèle réel dans la suite par défaut ; un E2E par nouvel élément visuel.
- Vocabulaire du papier pour les 7 sous-systèmes, traduit une fois pour toutes dans `ui.yaml`.
- La recherche agentique est déterministe et sans index : aucun embedding, aucun fichier dérivé du corpus.
- `read_file` reste en lecture seule et confiné ; l'ouverture au corpus Exemplia passe par le même hook H1 que les autres chemins.
- La compaction ne touche que la mémoire courte du chat principal : sous-agent, ateliers et mémoire globale gardent leur comportement au débordement.
- Le résumé de compaction est un appel ordinaire au modèle actif : plafond `[finops] max_session_usd`, annulation et bornes de boucle s'y appliquent.
- `content/demo_files/guide_harnais.md` est lu par le modèle dans les scénarios sous-agent et compression : après ajout, ces scénarios tiennent encore dans la fenêtre de 4 096 tokens.

## Non-goals

- Montrer les plateformes (ACP, places de marché), les bacs à sable au niveau du système d'exploitation ou les modes de permission : un rappel d'une ligne suffit (CAP-2).
- Des embeddings sur le code ou un index pour la recherche agentique.
- Réécrire ou compacter la mémoire globale.
- Compacter le contexte du sous-agent ou des ateliers.
- Rendre cliquables le retrait des anciens résultats d'outils et le lazy loading au débordement : ils restent du texte.

## Success signal

En formation, hors ligne, avec le modèle local, un participant :
1. pose la même question au RAG puis à l'agent qui cherche avec `search_documents` et lit avec `read_file`, et compare les deux contextes ;
2. fait déborder une conversation, choisit la compaction, voit l'appel de résumé et la jauge du cache repartir en écriture avec la cause « compaction » ;
3. finit le programme sur la carte des 7 sous-systèmes, où chaque brique est placée.

Aucune brique n'affiche plus une catégorie que la littérature contredit.

## Assumptions

- Le lot passe après la V1.3 et avant la story 2 de la V1.2 (décision d'Anaël du 2026-10-24). La PR #79 (corpus Exemplia enrichi) est fusionnée avant la story 3.
- Sous-système et rôle sont déclarés dans le registre des briques (`bricks/registry.py`), comme `category`, et non dans `content/bricks/*.yaml` : donnée structurelle non traduite. Les libellés vont dans `ui.yaml`.
- Le placement des briques et leurs rôles (`carte-du-harnais.md`) sont validés au point de contrôle de la story 2 (revue du 2026-10-24).
- Le résumé de compaction est stocké comme un échange marqué en tête de l'historique ; la fenêtre glissante retire les échanges les plus anciens jusqu'à tenir, en gardant au moins le dernier. À trancher au point de contrôle de la story 4.
- Les causes `compaction` et `sliding_window` s'ajoutent à `PrefixCause` après celles de la V1.3.
- Les stratégies cliquables n'apparaissent que si la branche active du chat principal a au moins un échange.

## Open Questions

Aucune.
