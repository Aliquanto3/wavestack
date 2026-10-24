---
title: 'V1.4 story 1 : disciplines revues et notions récentes'
type: 'feature'
created: '2026-10-24'
status: 'review'
route: ''
review_loop_iteration: 0
context: ['_bmad-output/specs/spec-wavestack-etat-de-l-art-harnais/SPEC.md']
---

## Intent

CAP-1 et CAP-2 de la V1.4. « Raisonnement » passe en harness engineering (`bricks/registry.py`, `category_text` fr/en/de) ; « Garde-fous » affiche « harness engineering » comme les autres briques. `guide_harnais.md` (fr/en/de) gagne la section 10 : emboîtement prompt ⊂ contexte ⊂ harnais, guides et capteurs (Böckeler), calculé ou déduit, rappel d'une ligne de ce que WaveStack ne montre pas.

## Réalisation

- Brique Prompt système : paragraphe sur les fichiers de contexte hiérarchiques (AGENTS.md, CLAUDE.md). Brique Skills : paragraphe sur les skills tiers, paquets à vérifier avant installation.
- Scénario `hooks` (garde-fou) : phrase sur les skills et plugins tiers à vérifier avant installation. Scénario `skills` (dont le prompt nomme le skill et l'outil) : la consigne qualifie ce nommage d'échafaudage pour le petit modèle.
- `docs/guide.md` : renvoi vers la section 10. Test `test_bricks` réaligné (catégorie du raisonnement). Captures `28` à `33-disciplines-*` refaites.

## Vérification

Tests ciblés (bricks, i18n, scénarios, sous-agent, compression, programme, faux moteur en 4 096 tokens) verts ; E2E `disciplines` : 52 vérifications réussies (`PYTHONUTF8=1` nécessaire sous Windows).

## Reports

Programme, durées et carte du harnais : stories 2 et 4.

## Revue

### Passe 1 (2026-10-24, SHA revu f916b57)

- Important, medium, second avis : la consigne de `native_tools` disait que les prompts nomment l'outil, faux pour ce scénario. Corrigé : `native_tools` rendu à l'identique (fr/en/de), la notion d'échafaudage portée par la consigne `skills`, dont le prompt nomme vraiment le skill et l'outil (CAP-2).
- Nit, low, second avis : réécritures de lignes existantes dans `scenarios.yaml` (vague V0 en ajouts). Corrigé en partie : `native_tools` n'est plus touché ; `hooks` et `skills` gardent une phrase ajoutée en fin de ligne, nécessaire à CAP-2, loin du module RAG de la story 3.
- Nit, low, second avis : commentaire « ≈ 7 000 bytes » de `tests/test_subagent.py`. Corrigé (≈ 8 600).
- Nit, low, second avis : commentaire « The categories do not change » de `tests/test_bricks.py`. Corrigé.
- Rejeté, second avis (5 et 6) : débordement E2E par le guide plus long. E2E `compression` (avec `--extra compression`, 43 vérifications, guide à 2 055 tokens, inchangé) et `subagent` (58 vérifications) verts.
