# Proposition de changement : V1.5, évaluer l'agent

- **Date** : 2026-10-25
- **Demandeur** : Anaël
- **Déclencheur** : lecture du cours « Building a Coding Agent From Scratch » (Decoding AI), comparé à WaveStack dans `research/comparaison-cours-decode-2026-10-25.md`
- **Mode de revue** : batch
- **Statut** : approuvée par Anaël le 2026-10-25 : incrément 1 seul, développement lancé dès la spec validée, sans attendre la recette du 2026-10-25 ; incrément 2 revu plus tard (décisions en section 6)
- **Portée** : modérée. Un nouveau lot en deux incréments : 6 stories à spécifier tout de suite, 5 pistes à spécifier ensuite sous condition. Aucun retour arrière ; deux non-objectifs de la V1.4 seraient revus dans l'incrément 2.

## 1. Résumé du problème

WaveStack montre ce que fait un agent, tour par tour. Il ne montre pas comment on vérifie qu'un agent se comporte comme prévu, ni comment on s'aperçoit qu'un changement (de modèle, de prompt système, de brique) l'a dégradé. L'évaluation existe, mais seulement pour le RAG (V1.2 story 15).

decode consacre deux leçons sur huit à ce sujet. Son argument : les tests de régression sont « la partie la plus importante des évaluations d'une application d'IA », et sans eux on a « peur de changer ses prompts ». C'est aussi le sujet qui manque le plus aux deux publics de la V2 en brouillon : les équipes techniques et la gouvernance.

| # | Écart | Nature | Constat dans le dépôt |
|---|---|---|---|
| 1 | Aucun cas de test d'agent, aucune vérification du comportement (bon outil, nombre d'appels, hook respecté). | Fond | `trace/catalog.py` trace tout ; rien ne le lit pour juger un tour. |
| 2 | Un tour raté ne peut pas devenir un test. | Fond et pédagogie | Le journal est en mémoire (AD-2), sans export pour le chat principal. Seul le dernier prompt se rejoue (story 9b). |
| 3 | Les notions de régression, banc d'essai, essais multiples et rejeu témoin ne sont pas enseignées. | Pédagogie | Le rejeu, le changement de modèle et la comparaison existent (stories 9b et 17), mais aucun scénario ne s'en sert pour évaluer. |
| 4 | Pas de glossaire d'application. | Pédagogie | Seul le serveur MCP de démonstration a un glossaire (`content/mcp_local/glossary.yaml`). |
| 5 | Planification, sous-agents à rôles, règles de permission et seuils de compaction absents ou partiels. | Fond | Détail dans la comparaison, lignes 8 à 11. |

Type de changement : nouveau besoin, issu d'une veille. Ce n'est ni un échec ni un malentendu.

## 2. Analyse d'impact

### Lots et stories

- **V1.2, V1.3, V1.4** : livrés, non remis en cause. Le lot réutilise le journal d'événements, le rejeu, le changement de modèle à chaud, la fenêtre de 4 096 tokens, H1, H5, le sous-agent, `search_documents` et le document sentinelle.
- **Recettes du 2026-10-25** : la recette d'Anaël et les 83 décisions « à revoir » sont en attente. Le lot n'en dépend pas. Anaël a choisi de lancer le développement sans attendre la recette (décision D1). Le risque d'empiler du neuf sur du non recetté est accepté ; un défaut trouvé en recette dans le rejeu, le journal ou les hooks peut toucher les stories 1 et 4.
- **V2 (brouillon, non déclenchée)** : l'incrément 1 en partage le principe (montrer l'erreur dans la trace, jamais par la qualité de la réponse). Sa CAP-1 (jeu de questions avec réponses attendues) est voisine des cas d'agent. On ajoute un renvoi, sans changer la spec.

### Artefacts

| Artefact | Impact | Action |
|---|---|---|
| PRD | Aucun conflit. Lot cadré par spec, comme en V1.2 à V1.4. | N/A |
| Architecture | Deux points à décider : (a) les cas créés en séance sont des données utilisateur persistées (où, et que fait la réinitialisation de la story 10) ; (b) le moteur de vérification lit le journal d'événements et doit rester une fonction pure, comme un hook (AD-13). | Dans `brownfield.md` de la spec. |
| UX | Deux nouveaux éléments visuels : le formulaire « En faire un cas » et la vue « Évaluer l'agent ». | Maquettes dans la spec, points de contrôle des stories 3 et 4. |
| Règle des agrégats | Les moyennes ne sont permises que dans la vue Évaluer du RAG (V1.2). | Les étendre à la vue Évaluer l'agent, et nulle part ailleurs. |
| `content/` et `content/i18n/{en,de}/` | Suite de cas fournie, module 9, glossaire, textes des briques. | Stories 2, 5 et 6. |
| Programme | Un module de plus. Le programme passe de 7 h à 7 h 45 ou 8 h (décision D3). | Mettre à jour `docs/guide.md:80`, le README, `tools/demo/compose.py` et les tests du programme. |
| Tests | Chaque cas fourni est vérifié dans les deux sens avec le faux moteur. Un E2E par nouvel élément visuel. | Dans les stories. |
| CI, installation | Aucune nouvelle dépendance. | N/A |

### Numérotation

« V1.5 » est un nom de lot. Le dossier de spec est nommé par thème (`spec-wavestack-evaluer-l-agent`). Le numéro SemVer est attribué à la livraison (probablement 1.6.0).

## 3. Approche recommandée

**Un nouveau lot V1.5 « Évaluer l'agent », en deux incréments.**

- **Incrément 1 : évaluer l'agent.** C'est l'écart le plus net, il est faisable sans modèle et il sert directement la V2. Tout s'appuie sur ce qui existe : le journal d'événements porte déjà ce qu'il faut vérifier, et le rejeu, le changement de modèle et la comparaison sont déjà là.
- **Incrément 2 : quatre briques à compléter.** Planification, sous-agents à rôles, règles de permission, seuils de compaction, plus la carte qui montre ce qu'ajoute chaque module. Chaque piste a une condition préalable (test d'un modèle, ou revue d'un non-objectif de la V1.4). Elle n'est spécifiée qu'une fois sa condition levée.

**Pourquoi pas une spec story par story, au fil de l'eau ?** Les stories de l'incrément 1 partagent un contrat : la forme d'un cas et la liste des vérifications. Les runs précédents ont appris qu'il faut décider ces contrats tôt, sinon les stories parallèles divergent. On spécifie donc l'incrément 1 en entier avant le code. L'incrément 2 attend ses conditions.

- **Effort** : moyen pour l'incrément 1 (deux stories de contenu, quatre de code dont deux à risque modéré).
- **Risques** :
  - **Durée sur CPU** : une suite de 8 cas avec le 2B peut prendre plusieurs minutes. La suite est donc courte, chaque cas est lançable seul, l'exécution s'annule, et k = 3 essais ne s'applique qu'à un cas.
  - **Cas qui ne peuvent pas échouer** : chaque cas fourni est vérifié dans les deux sens avec le faux moteur (règle reprise de decode).
  - **Résultats instables avec un petit modèle** : c'est le sujet même du module. On le montre avec k essais au lieu de le cacher.

Options écartées :
- un banc d'essai à vérificateur caché (il faut un bac à sable et git) ;
- un juge LLM dans la régression (Qwen3.5-2B n'est pas viable comme juge, H7 à 64 %) ;
- les modes de permission (aucun outil de WaveStack ne modifie quoi que ce soit, ils n'auraient rien à interdire) ;
- le rejeu à outils figés (reporté) ;
- la file de réorientation ;
- Opik et Kitaru.

## 4. Propositions détaillées

### 4.1 Incrément 1 : nouvelle spec `_bmad-output/specs/spec-wavestack-evaluer-l-agent/`

- **CAP-1 Contrat d'un cas et vérifications sur la trace** (écart 1)
  - **intent:** Un cas d'agent est une donnée : un prompt, une configuration (briques, hooks, prompt système, fenêtre), un historique pré-rempli facultatif, et une à trois vérifications lues dans le journal du tour. Il porte aussi un symptôme, une assertion en une phrase, un plafond d'appels au modèle et une provenance (tour d'origine, date, modèle, « corrigé dans »).
  - **success:**
    - Le catalogue de vérifications est fermé. On peut vérifier :
      - qu'un outil est appelé, ou n'est pas appelé ;
      - qu'un argument n'est jamais passé ;
      - que le nombre d'appels au modèle reste sous le plafond ;
      - que la réponse contient un texte ;
      - qu'un hook a bloqué ou demandé l'accord ;
      - que le sous-agent a été appelé ;
      - que le tour finit sans erreur.
    - Chaque vérification est une fonction pure du journal d'un tour, testée sur des journaux construits.
    - Une vérification qui ne trouve pas son événement échoue : elle n'est pas comptée comme réussie.
- **CAP-2 Suite de cas fournie** (écarts 1 et 3)
  - **intent:** Le formateur dispose d'environ 8 cas prêts, chacun lié à une brique du programme.
  - **success:**
    - Les cas visés, transposés de decode et ancrés dans WaveStack :
      - l'heure avec `get_datetime` en deux appels au plus ;
      - pas de chemin inventé pour `read_file` ;
      - H1 bloque `confidentiel/` ;
      - la consigne de la mémoire globale est suivie ;
      - le code `TLV-7731-QZ` survit à une compaction dans une fenêtre de 4 096 tokens ;
      - la délégation au sous-agent ;
      - `search_documents` avant `read_file` ;
      - l'outil réseau refusé par H5, puis non rappelé.
    - Au moins un cas extrait d'une vraie défaillance relevée en recette, avec sa provenance.
    - Le plafond d'appels de chaque cas est mesuré (maximum de 3 exécutions + 1), pas deviné.
    - Chaque cas réussit avec un faux moteur scripté pour réussir et échoue avec un faux moteur qui ne fait rien.
    - fr, en et de.
- **CAP-3 Du tour raté au cas** (écart 2)
  - **intent:** Sur un tour du chat principal, « En faire un cas » ouvre un formulaire pré-rempli : prompt, configuration, outils appelés. Le formateur y nomme le symptôme et choisit une ou deux vérifications.
  - **success:**
    - Le formulaire dit tout de suite, sans appel au modèle, si le tour d'origine échoue bien au cas. S'il réussit, il prévient : « ce cas ne peut pas échouer sur ce tour ».
    - Le cas est enregistré dans les données de l'utilisateur, avec sa provenance.
    - fr, en et de, avec un E2E.
- **CAP-4 Vue « Évaluer l'agent »** (écarts 1 et 3)
  - **intent:** Le formateur lance la suite, ou un seul cas, sur le modèle et la configuration courants. Il voit pour chaque cas « réussi » ou « échoué », la vérification fautive et un lien vers le tour. Il compare ensuite deux exécutions, par exemple avant et après un changement de modèle ou de prompt système.
  - **success:**
    - Exécution séquentielle, annulable, soumise au plafond `[finops] max_session_usd` et aux bornes de boucle.
    - k = 1 ou 3 essais sur un cas, avec réussites sur k affichées (pass@k, pass^k).
    - Comparaison de deux exécutions, cas par cas.
    - Les agrégats ne sont affichés que dans cette vue.
    - Testé avec le faux moteur, avec un E2E.
- **CAP-5 Module 9 « Évaluer l'agent » et contenus** (écart 3)
  - **intent:** Le participant fait échouer l'agent, transforme l'échec en cas, change de prompt système ou de modèle, relance la suite. Il apprend à rejouer une première fois sans rien changer avant de comparer.
  - **success:**
    - Un module de 45 à 60 min, avec 3 ou 4 scénarios.
    - Les textes expliquent :
      - démo, banc d'essai et régression ;
      - un plafond d'appels observé, jamais deviné ;
      - le rejeu témoin ;
      - pourquoi le rejeu de WaveStack réexécute les outils, et ce que changerait des outils figés ;
      - pourquoi on évite ici le juge LLM.
    - L'accroche « l'agent tient en quelques lignes, le reste est le harnais » au module 1.
    - fr, en et de.
- **CAP-6 Glossaire du harnais** (écart 4)
  - **intent:** Un glossaire de 40 à 60 termes, ouvert depuis l'interface, que les textes des briques et des scénarios peuvent citer.
  - **success:** fr, en et de, avec un test de miroir i18n et un E2E d'ouverture.

### 4.2 Stories proposées (incrément 1)

| # | Story | CAP | Dépend de | Agent conseillé |
|---|---|---|---|---|
| 1 | Contrat d'un cas et moteur de vérification sur le journal | 1 | — | Opus (contrat partagé par toutes les stories) |
| 2 | Suite de cas fournie et contrôle dans les deux sens | 2 | 1 | Sonnet |
| 3 | « En faire un cas » depuis un tour | 3 | 1 | Sonnet |
| 4 | Vue « Évaluer l'agent » : lancer, k essais, comparer | 4 | 1 | Opus (états de session, annulation, coûts) |
| 5 | Module 9 et contenus | 5 | 2, 4 | Sonnet, contenu |
| 6 | Glossaire du harnais | 6 | — | Sonnet, contenu |

Vagues :
- **V0** : 1 et 6 ;
- **V1** : 2 et 3 ;
- **V2** : 4 (seule, car elle partage `app.js` avec la story 3) ;
- **V3** : 5.

Points de contrôle de spec (`spec_checkpoint`) : stories 3 et 4 (maquettes), et story 2 (liste finale des cas, après mesure des plafonds sur le PC cible).

### 4.3 Incrément 2 : pistes sous condition

| # | Piste | Condition avant la spec | Module touché |
|---|---|---|---|
| A | Planification : outil de liste de tâches, affichée comme une liste à cocher, avec un cas de la suite | Test préalable : Qwen3.5-2B et les autres modèles locaux appellent-ils l'outil avant d'agir ? | 6, qui deviendrait « Planifier et déléguer » |
| B | Sous-agents à rôles : catalogue en markdown (explorer, relecteur), plusieurs briefs lancés en séquence, rapport refusé s'il est vide ou sans appel d'outil, une seule relance | Même test préalable : le parent sait-il écrire plusieurs briefs distincts ? | 6 |
| C | Règles de permission : H1 et H5 réécrits en une table `Outil(motif)`, dans l'ordre refuser → autoriser → demander, visible dans la brique Hooks | Anaël revoit le non-objectif « modes de permission » de la V1.4. Les modes restent exclus, seules les règles entrent. | 5 |
| D | Compaction par paliers : jauge de contexte colorée à 60 et 80 %, retrait des anciens résultats d'outils sans appel au modèle, résumé en sections | Anaël revoit le non-objectif « retrait des anciens résultats d'outils » de la V1.4. | 7 |
| E | Carte du harnais : mise en évidence de ce qu'ajoute le module courant | Aucune ; petite story, à joindre à A ou D. | Tous |

### 4.4 Renvoi dans la V2

```
Spec : spec-wavestack-v2/SPEC.md
Section : Capabilities, CAP-1

AJOUT :
- Voisine des cas d'agent de la V1.5 (spec-wavestack-evaluer-l-agent, CAP-1 et CAP-2) :
  réutiliser leur contrat si la V2 est déclenchée après la V1.5.
```

## 5. Passage de relais

- **Étape 1, spec** : `bmad-spec` crée `spec-wavestack-evaluer-l-agent` à partir de la section 4.1. Il produit les maquettes du formulaire et de la vue, `brownfield.md` (persistance des cas, réinitialisation, moteur de vérification) et `stories.yaml`. Anaël valide la spec avant toute ligne de code.
- **Étape 2, développement** : dès la spec validée, sans attendre la recette du 2026-10-25 (D1). Chaîne agent-cost-kit par story (`dev-story` → `second-avis` → `reviewer`), en run autonome avec `run-autonome.md`.
- **Étape 3, incrément 2** : après la recette de l'incrément 1, test préalable des pistes A et B, décisions sur C et D, puis une proposition courte et une spec.
- **Critères de réussite du lot** : en formation, hors ligne, avec le modèle local, un participant :
  - transforme un tour raté en cas et voit que le tour d'origine y échoue ;
  - change de prompt système ou de modèle, relance la suite et lit ce qui a changé, cas par cas ;
  - relance trois fois un même cas et voit que le petit modèle ne réussit pas à chaque fois.
- **Contrainte d'exécution** : cette proposition et la spec se commitent sur une branche de documentation, jamais sur une branche de story.

## 6. Décisions demandées à Anaël

Décisions prises par Anaël le 2026-10-25.

| # | Décision | Recommandation | Décidé |
|---|---|---|---|
| D1 | Quand lancer le développement : avant ou après la recette du 2026-10-25 ? | Spec tout de suite, développement après la recette. | **Développement dès la spec validée**, sans attendre la recette. |
| D2 | Périmètre : l'incrément 1 seul, ou avec une ou plusieurs pistes de l'incrément 2 ? | L'incrément 1 seul. Lancer en parallèle le test préalable de A et B, qui ne coûte pas de développement. | Incrément 1 seul ; incrément 2 revu plus tard. |
| D3 | Durée du module 9 : 45 ou 60 min (programme à 7 h 45 ou 8 h) ? Ou bien raccourcir un autre module ? | 45 min. | 45 min, programme à 7 h 45. |
| D4 | Les cas créés en séance survivent-ils à la réinitialisation de la story 10 ? | Oui, avec un bouton « effacer mes cas » à part. | Oui, avec « effacer mes cas » à part. |
| D5 | Pistes C et D : revoir les non-objectifs de la V1.4 ? | À trancher à l'étape 3, pas maintenant. | À l'étape 3. |
