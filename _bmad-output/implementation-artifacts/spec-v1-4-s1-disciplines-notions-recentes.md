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
- Scénario `hooks` (garde-fou) : phrase sur les skills et plugins tiers à vérifier avant installation. Scénario `native_tools` : la consigne explique que les prompts nomment l'outil par échafaudage pour le petit modèle.
- `docs/guide.md` : renvoi vers la section 10. Test `test_bricks` réaligné (catégorie du raisonnement). Captures `28` à `33-disciplines-*` refaites.

## Vérification

Tests ciblés (bricks, i18n, scénarios, sous-agent, compression, programme, faux moteur en 4 096 tokens) verts ; E2E `disciplines` : 52 vérifications réussies (`PYTHONUTF8=1` nécessaire sous Windows).

## Reports

Programme, durées et carte du harnais : stories 2 et 4.
