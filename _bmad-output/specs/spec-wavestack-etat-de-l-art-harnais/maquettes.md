# Maquettes (CAP-3 et CAP-5)

Maquettes de principe : composants, jetons de couleur et espacements suivent `DESIGN.md` (dialogue, `overflow-card`, `pane-text-action`). Textes en français, traduits en en et de.

## 1. Carte du harnais (CAP-3)

Ouverture : bouton « Carte du harnais » dans la consigne du scénario `harness_map` (dernier scénario du module 7 « Contexte long et carte ») et en pied du panneau des briques. Dialogue plein écran, fermeture par « Fermer » ou Échap, focus rendu au bouton d'origine.

```
┌─ Carte du harnais ─────────────────────────────────────────────── [Fermer] ┐
│ Les briques de WaveStack dans les 7 sous-systèmes d'un harnais.            │
│ Légende : ◆ guide   ◉ capteur calculé   ◎ capteur déduit   · capacité      │
│ Couleur de la pastille = discipline (prompt ⊂ contexte ⊂ harnais)          │
│                                                                            │
│ ┌ Boucle ───────────────┐ ┌ Intégration LLM ──────┐ ┌ Outils ───────────┐ │
│ │ cœur : appels bornés, │ │ · Raisonnement  [h]   │ │ · Outils natifs [h]│ │
│ │ relances bornées      │ │ cœur : moteur, gabarit│ │   search_documents │ │
│ └───────────────────────┘ └───────────────────────┘ └────────────────────┘ │
│ ┌ Mémoire et contexte ──────────────────────────┐ ┌ Sécurité ───────────┐ │
│ │ ◆ Prompt système [p]   ◆ Mémoire globale [c]  │ │ ◎ Garde-fous   [h]  │ │
│ │ · Mémoire courte [c]   · RAG [c]              │ └─────────────────────┘ │
│ │   (compaction, fenêtre glissante)             │ ┌ Orchestration ──────┐ │
│ │ · Compression [c]                             │ │ · Sous-agent   [h]  │ │
│ └───────────────────────────────────────────────┘ └─────────────────────┘ │
│ ┌ Extensibilité ────────────────────────────────────────────────────────┐ │
│ │ ◆ Skills [c]   · MCP [h]   ◆◉ Hooks [h]                               │ │
│ └───────────────────────────────────────────────────────────────────────┘ │
│ Briques éteintes : grisées, toujours placées.                              │
│ Non montré ici : plateformes (ACP, places de marché), bacs à sable du      │
│ système d'exploitation, modes de permission.                               │
│ Sources : Barbaste et al., arXiv 2609.00006 ; Böckeler (guides, capteurs). │
└────────────────────────────────────────────────────────────────────────────┘
```

- `[p]`, `[c]`, `[h]` : pastille de discipline, au jeton `--color-discipline-{d}` déjà utilisé par la jauge.
- Une brique éteinte reste placée, grisée : la carte décrit le harnais complet, pas la configuration courante.
- Un clic sur une brique ouvre sa carte dans le panneau des briques (facultatif, à confirmer au point de contrôle).
- Largeur de téléphone : les cases passent en une colonne, dans l'ordre du tableau de `carte-du-harnais.md`.

## 2. Débordement : choix de stratégie (CAP-5)

Dans l'Orchestration et la Vue humain, `overflowCard()` garde son message et gagne deux boutons quand la branche active a au moins un échange.

```
┌ ⚠ Contexte trop long ──────────────────────────────────────────────┐
│ 4 312 tokens pour 3 584 utilisables                                │
│ Le contexte compte 4 312 tokens pour 3 584 utilisables (fenêtre de │
│ 4 096 moins 512 réservés à la réponse). Cause : l'historique de la │
│ conversation occupe la plus grande part du contexte. …             │
│                                                                    │
│ Continuer avec :                                                   │
│ [ Compacter ]  résumer les 5 anciens échanges en quelques lignes   │
│                (un appel au modèle, ≈ 20 s en local)               │
│ [ Fenêtre glissante ]  ne garder que les échanges récents          │
│                (aucun appel ; les 3 plus anciens sont retirés)     │
│ Autres stratégies (non montrées ici) :                             │
│ • Retrait des anciens résultats d'outils.                          │
│ • Lazy loading : documentation des outils à la demande.            │
└────────────────────────────────────────────────────────────────────┘
```

- Un clic désactive les deux boutons, applique la stratégie, puis renvoie seul le message refusé, comme un nouveau tour.
- Sans échange à compacter (message seul trop long, résultat d'outil du tour) : pas de boutons, la carte reste celle d'aujourd'hui.
- Débordement du sous-agent ou d'un atelier : carte inchangée.
- Les chiffres « 5 anciens », « 3 plus anciens » et la durée estimée sont calculés, pas écrits en dur.

## 3. Bouton « Compacter » hors débordement (CAP-5)

```
 Conversation                       [ Compacter ▾ ]  [ Vider la conversation ]
                                    ┌──────────────────────────────────────┐
                                    │ Compaction : résumer les anciens      │
                                    │   échanges (un appel au modèle)       │
                                    │ Fenêtre glissante : ne garder que     │
                                    │   les 2 derniers échanges             │
                                    └──────────────────────────────────────┘
```

- Grisé, avec sa raison en infobulle, pendant un tour, sans conversation, ou quand la brique Mémoire courte est éteinte.
- Hors débordement, la fenêtre glissante garde les deux derniers échanges (valeur à confirmer au point de contrôle).

## 4. Après la stratégie : ce que voit la salle

```
Historique                       Jauge du contexte (avant → après)
┌───────────────────────────┐   ████████████████████░  4 312 → ███████░░░░ 1 980
│ 📝 Résumé (compaction)     │
│ « Nous avons parlé de … » │   Jauge du cache, appel suivant
│ ─ Échange 6 ─             │   [ lu 0 | écrit 1 980 ]  Cause : compaction
│ ─ Échange 7 ─             │
└───────────────────────────┘   Orchestration : étape « Résumé de compaction »
                                (modèle actif, tokens, durée, coût)
```

- Le résumé apparaît comme un échange marqué dans la conversation et dans le Contexte LLM, avec son propre libellé dans la jauge.
- Fenêtre glissante : pas d'étape de résumé ; la conversation affiche « 3 échanges retirés (fenêtre glissante) » à la place des échanges retirés ; cause « fenêtre glissante ».
