# Proposition de changement : V1.4, état de l'art des harnais

- **Date** : 2026-10-24
- **Demandeur** : Anaël
- **Déclencheur** : audit état de l'art des harnais du 2026-10-24 (`research/audit-etat-de-l-art-harnais-2026-10-24.md`)
- **Mode de revue** : batch
- **Statut** : approuvée par Anaël le 2026-10-24, avec l'ordre V1.3 → V1.4 → suite de la V1.2
- **Portée** : modérée. Un nouveau lot de 4 stories, sans retour arrière ni changement des lots V1.2 et V1.3 au-delà d'un renvoi.

## 1. Résumé du problème

Anaël a demandé un audit : WaveStack est-il à l'état de l'art des harnais agentiques, sur le fond et sur la pédagogie ? La référence est le papier du Wavestone AI Lab (Barbaste et al., *Harness Engineering*, arXiv 2609.00006). Il étudie 11 harnais de code et définit le harnais par 7 sous-systèmes : boucle, intégration LLM, outils, mémoire et contexte, sécurité, orchestration, extensibilité. L'audit s'appuie aussi sur Böckeler (martinfowler.com), OCTO, walkinglabs et SFEIR.

Conclusion : WaveStack applique déjà l'essentiel des principes. On y trouve le contexte vu comme une ressource rare, le chargement progressif, l'hygiène du cache, des hooks déterministes, des bornes de boucle, un sous-agent isolé et des flux de données visibles. Cinq écarts restent :

| # | Écart | Nature | Constat dans le dépôt |
|---|---|---|---|
| 1 | Le RAG vectoriel injecté à chaque tour est présenté comme *la* brique de recherche. Aucun des 11 harnais n'utilise d'embeddings sur le code : ils cherchent à la demande avec des outils déterministes (grep, glob, lecture), comme Anthropic le recommande. | Fond | `content/bricks/rag.yaml` ne mentionne pas la recherche agentique. Le chat n'a aucun outil de recherche dans le corpus, seulement `read_file` (`content/tools.yaml`). |
| 2 | Aucune carte d'ensemble ne situe les briques dans les 7 sous-systèmes. | Pédagogie | Les 6 modules de `content/scenarios.yaml` avancent brique par brique, sans récapitulatif. |
| 3 | Les catégories des briques sont discutables. | Pédagogie | `reasoning.yaml` est classé « prompt engineering », alors que c'est une capacité du modèle que le harnais active. `guardrails.yaml` est classé « harnais », alors que les autres briques sont en « … engineering ». L'emboîtement prompt ⊂ contexte ⊂ harnais n'est dit nulle part. |
| 4 | La compaction est nommée, jamais montrée. Elle est devenue standard (7 harnais sur 11). | Fond et pédagogie | Au débordement, le harnais refuse l'appel et liste des stratégies (`content/messages.yaml:140-144`). |
| 5 | Des notions récentes manquent : fichiers de contexte hiérarchiques (AGENTS.md, CLAUDE.md, recommandation R6), guides et capteurs (Böckeler), échafaudage à alléger quand le modèle progresse (OCTO), skills tiers à traiter comme des paquets. | Pédagogie | Aucune mention dans `content/`. |

Type de changement : nouveau besoin, issu d'une veille. Ce n'est ni un échec ni un malentendu.

## 2. Analyse d'impact

### Lots et stories

- **V1.2 (atelier recherche documentaire)** : non remise en cause. Sa CAP-7 prévoit une architecture « recherche agentique » dans l'atelier. L'outil de recherche de la V1.4 (écart 1) pourra lui servir de brique. On ajoute un renvoi, sans changer la spec.
- **V1.3 (cache visible)** : non remise en cause. La story compaction de la V1.4 dépend de ses stories 1 à 3 (données de cache, jauge, nouvelle cause `PrefixCause`) : une compaction réécrit le début de la conversation, et la jauge doit le montrer.
- **V1.4 (nouveau lot)** : 4 stories, détaillées en section 4.
- **Aucun lot devenu inutile, aucun retour arrière.**

### Artefacts

| Artefact | Impact | Action |
|---|---|---|
| PRD (2026-09-22) | Aucun conflit. Les lots récents sont cadrés par spec, sans mise à jour du PRD (même pratique qu'en V1.2 et V1.3). | N/A |
| Architecture (`ARCHITECTURE-SPINE.md`) | Deux points à décider : (a) la compaction réécrit la mémoire courte, ce qui touche l'historique de session ; (b) un outil natif de plus. Rien ne change dans les patterns existants. | À consigner dans `brownfield.md` de la spec V1.4, comme en V1.3. |
| UX (`DESIGN.md`, `EXPERIENCE.md`) | Deux nouveaux éléments visuels : la carte du harnais et le choix de stratégie au débordement. | Maquette dans la spec V1.4. Les gros documents UX ne sont pas modifiés. |
| Contenus `content/` et `content/i18n/{en,de}/` | Textes des briques, nouveaux scénarios, fiche de la carte. | Stories 1 à 4, en fr, en et de. |
| `docs/guide.md`, cahier de recette | De nouveaux parcours : recherche agentique, compaction, carte. | Dans les stories concernées. |
| Tests | Exhaustivité de la carte (chaque brique a son sous-système), outil de recherche, compaction sur faux moteur, un E2E par nouvel élément visuel. | Dans les stories. |
| CI, installation | Aucune nouvelle dépendance attendue. | N/A |
| Suivi | Le projet n'a pas de `sprint-status.yaml` : chaque lot suit ses stories dans le `stories.yaml` de sa spec. | Le `stories.yaml` de la V1.4 est créé par `bmad-spec`. |

### Numérotation

Les noms de lots ne suivent plus les versions publiées : le tag `v1.2.0` correspond à MiniCPM5-2B, et le lot V1.2 n'est pas livré. « V1.4 » est donc un nom de lot. Le dossier de spec est nommé par thème (`spec-wavestack-etat-de-l-art-harnais`), et le numéro SemVer sera attribué à la livraison.

## 3. Approche recommandée

**Ajustement direct : un nouveau lot V1.4**, exécuté après la V1.3 et avant la suite de la V1.2 (story 2 et suivantes).

- **Pourquoi un lot séparé ?** Il a un thème propre (l'état de l'art du harnais principal, pas le cache) et une valeur pédagogique immédiate. Il est surtout fait de contenus, donc peu risqué. Il évite de grossir la V1.3, déjà prête à lancer.
- **Pourquoi après la V1.3 ?** La démonstration de compaction réutilise la jauge du cache, et c'est le meilleur moment pour montrer qu'un résumé casse le préfixe.
- **Pourquoi avant la suite de la V1.2 ?** La V1.4 compte 4 stories et la V1.2 en compte 21. La V1.4 corrige le discours du chat principal, que chaque formation utilise. Et la recherche agentique de la V1.2 (CAP-7) pourra réutiliser son outil. *Ordre retenu par Anaël le 2026-10-24.*
- **Effort** : moyen. Deux stories de contenu (1, 2) et deux stories de code (3, 4).
- **Risques** :
  - fiabilité des appels d'outils des petits modèles pour l'écart 1 (atténuée par des prompts qui nomment l'outil, ce qui illustre justement l'écart 5 « échafaudage ») ;
  - durée de l'appel de résumé sur CPU pour l'écart 4 (atténuée par une fenêtre glissante sans appel, au choix) ;
  - E2E qui vérifient la couleur des disciplines dans la jauge, après le reclassement du raisonnement.

Options écartées : retour arrière (rien à défaire) ; revue du MVP (le MVP est livré, rien n'est réduit) ; fusion dans la V1.3 (choix initial d'Anaël, abandonné pour un lot séparé).

## 4. Propositions détaillées

### 4.1 Nouvelle spec : `_bmad-output/specs/spec-wavestack-etat-de-l-art-harnais/`

Contenu attendu de SPEC.md, à rédiger avec `bmad-spec` :

**Why.** L'audit du 2026-10-24 confirme que WaveStack applique l'essentiel des principes des harnais, et relève cinq écarts. Le lot les corrige, pour que WaveStack partage avec le papier du Wavestone AI Lab (arXiv 2609.00006) un vocabulaire et une carte communs.

**Capabilities (proposées)**

- **CAP-1 Disciplines revues** (écart 3)
  - intent : le participant comprend que prompt, contexte et harnais s'emboîtent, et chaque brique est classée selon la littérature.
  - success :
    - « Raisonnement » passe en harness engineering (sous-système intégration LLM) ;
    - « Garde-fous » affiche « harness engineering », comme les autres briques ;
    - le guide du harnais explique l'emboîtement prompt ⊂ contexte ⊂ harnais ;
    - fr, en et de ; les tests de miroir i18n et les E2E de la jauge sont verts.
- **CAP-2 Notions récentes** (écart 5)
  - intent : le participant rencontre quatre notions récentes là où elles ont du sens.
  - success :
    - la brique Prompt système cite les fichiers de contexte hiérarchiques (AGENTS.md, CLAUDE.md) ;
    - le guide du harnais présente les guides et les capteurs (Böckeler), contrôles calculés ou déduits par un modèle ;
    - une consigne de scénario explique que les prompts nomment l'outil parce que le petit modèle en a besoin, et qu'un modèle plus fort se passe de cet échafaudage ;
    - la brique Skills et un scénario de sécurité traitent les skills tiers comme des paquets à vérifier avant installation ;
    - un rappel d'une ligne liste ce que WaveStack ne montre pas : plateformes (ACP, places de marché), bacs à sable au niveau du système d'exploitation, modes de permission.
- **CAP-3 Carte du harnais** (écart 2)
  - intent : en fin de programme, le participant voit chaque brique placée dans les 7 sous-systèmes du papier, avec son rôle de guide ou de capteur.
  - success :
    - chaque brique déclare son sous-système et son rôle dans `content/bricks/*.yaml` ;
    - la carte est générée à partir de ces données et s'ouvre depuis le dernier module du programme ;
    - un test vérifie que chaque brique a un sous-système valide ;
    - la source est citée ;
    - fr, en et de, avec un E2E.
- **CAP-4 RAG injecté ou recherche agentique** (écart 1)
  - intent : le participant compare, sur la même question, le RAG qui injecte des extraits à chaque tour et un agent qui cherche dans le corpus avec un outil déterministe.
  - success :
    - un outil natif `search_documents` cherche par mots dans le corpus de démonstration et renvoie fichiers et lignes ; `read_file` lit ensuite le passage ;
    - la brique RAG gagne un paragraphe « RAG injecté ou recherche agentique » (coûts, cas d'usage, ce que font les harnais de code) ;
    - un scénario du module RAG fait la comparaison ;
    - testé avec le faux moteur, avec un E2E ;
    - aucune nouvelle dépendance.
- **CAP-5 Compaction et fenêtre glissante** (écart 4)
  - intent : au débordement, ou sur demande, le formateur choisit de résumer les anciens échanges (compaction) ou de ne garder que les derniers (fenêtre glissante). Il voit le contexte avant et après, et le cache qui repart en écriture.
  - success :
    - avec une fenêtre de 4 096 tokens, une conversation qui déborde propose les deux stratégies au lieu du seul refus ;
    - la compaction fait un appel de résumé au modèle actif, compté dans les coûts et visible dans l'orchestration ;
    - la fenêtre glissante ne fait aucun appel ;
    - la jauge du cache (V1.3) montre l'écriture, avec la cause « compaction » ou « fenêtre glissante » ;
    - testé avec le faux moteur, avec un E2E ;
    - un scénario dans le module « Sous-agent et compression ».

**Constraints.** Celles de la V1.3 s'appliquent :
- pas de nouvelle dépendance ;
- fichiers carrefour en ajouts seulement ;
- fr, en et de ;
- faux moteurs en test ;
- un E2E par nouvel élément visuel ;
- vocabulaire du papier pour les 7 sous-systèmes, traduit une fois pour toutes dans `ui.yaml`.

**Non-goals.** Les plateformes, les bacs à sable au niveau du système d'exploitation et les modes de permission (un simple rappel suffit). Les embeddings sur le code. La réécriture de la mémoire globale.

### 4.2 Stories proposées (pour `stories.yaml`)

| # | Story | Écarts | Dépend de | Agent conseillé |
|---|---|---|---|---|
| 1 | Disciplines revues et notions récentes (CAP-1, CAP-2) | 3, 5 | — | Sonnet, contenu |
| 2 | Carte du harnais (CAP-3) | 2 | 1 (catégories et rôles) | Sonnet |
| 3 | Outil `search_documents` et scénario RAG ou recherche agentique (CAP-4) | 1 | PR #79 fusionnée | Sonnet |
| 4 | Compaction et fenêtre glissante (CAP-5) | 4 | V1.3 stories 1 à 3 | Opus (session, historique, cache) |

Vagues :
- **V0** : 1 et 3, qui ne touchent pas les mêmes fichiers, sauf `scenarios.yaml` (ajouts seulement) ;
- **V1** : 2 ;
- **V2** : 4, une fois la V1.3 fusionnée.

Points de contrôle de spec (`spec_checkpoint`) : stories 2 et 4, qui demandent une maquette.

**Base vérifiée le 2026-10-24** : `main` = `origin/main` = `51d34f6` (#84). L'analyse porte sur ce contenu. La PR #79 (V1.2 story 1, corpus Exemplia enrichi, CI verte) reste ouverte. Elle modifie `content/bricks/rag.yaml` et `content/scenarios.yaml`, que touche aussi la story 3. Il faut la fusionner avant la V1.4 : `search_documents` cherchera ainsi dans le corpus enrichi, et on évite qu'une PR reste longtemps en conflit.

### 4.3 Renvoi dans la V1.2

```
Spec : spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md
Section : Assumptions

AJOUT :
- La recherche agentique de CAP-7 réutilise l'outil `search_documents` de la V1.4
  (état de l'art des harnais) si celle-ci est livrée avant la story qui la construit.
```

Raison : éviter deux outils de recherche différents.

### 4.4 Suivi et mémoire

- `deferred-work.md` : aucun ajout. Les sujets hors périmètre sont traités par le rappel d'une ligne de CAP-2.
- La mémoire du projet notera l'ordre des lots : V1.3, puis V1.4, puis la suite de la V1.2.

## 5. Passage de relais

- **Portée** : modérée (nouveau lot, ordre des lots revu).
- **Étape 1, spec (PM ou Architecte)** : `bmad-spec` crée `spec-wavestack-etat-de-l-art-harnais` à partir de la section 4. Il produit la maquette de la carte et du choix de stratégie, `brownfield.md` (compaction et historique de session, nouvel outil) et `stories.yaml`. Anaël valide la spec avant toute ligne de code.
- **Étape 2, développement** : chaîne agent-cost-kit par story (`dev-story` → `second-avis` → `reviewer`), après la V1.3.
- **Critères de réussite du lot** :
  - en formation, hors ligne, un participant compare RAG et recherche agentique sur une même question ;
  - il voit une compaction casser le cache ;
  - il finit le programme sur la carte des 7 sous-systèmes ;
  - aucune brique n'a plus une catégorie que la littérature contredit.
- **Contrainte d'exécution** : le run autonome SLM A/B est en cours sur `feat/slm-a-modeles-facultatifs`. La spec et cette proposition se commitent sur une branche de documentation à part, jamais sur une branche de story.
