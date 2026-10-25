---
title: 'V1.5 story 6 : glossaire du harnais'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: ''
review_loop_iteration: 0
context: ['_bmad-output/specs/spec-wavestack-evaluer-l-agent/SPEC.md']
---

## Intent

CAP-6 de la V1.5. 58 termes du harnais et de l'évaluation d'agent, ouverts depuis le bouton « Glossaire » de la navigation commune des six pages, citables depuis les textes des briques et des scénarios.

## Réalisation

- `content/glossary.yaml` (`terms: {clé: {term, definition}}`, clés en anglais `snake_case`) et surcouches `content/i18n/{en,de}/glossary.yaml` (mêmes clés, même ordre). `content/mcp_local/glossary.yaml` inchangé.
- `src/wavestack/glossary.py` (chargeur validé, `CITATION`, `cited_keys`) ; route `GET /api/glossary` (langue de la séance, repli sur le français si la traduction est invalide).
- `web/static/glossary.js` (panneau, recherche, citations), chargé par les six pages ; textes de l'interface dans `common.glossary` de `ui.yaml` ; styles dans `pages.css`.
- Syntaxe de citation : `[[g:clé]]` ou `[[g:clé|texte affiché]]`. Le préfixe `g:` évite les liens `[[page]]` du wiki RAG. Rendue en bouton `.glossary-cite` partout où le texte apparaît (observateur du DOM) ; une clé inconnue reste du texte.

## Vérification

`tests/test_glossary.py` (40 à 60 termes, miroir fr/en/de, syntaxe, même motif en Python et en JS, toute clé citée dans `content/` existe dans les trois langues, route, pages), `test_i18n` (parité du fichier) ; E2E `glossary` (50 vérifications).

## Reports

Aucune citation réelle n'est encore posée dans `content/` : la story 5 cite les termes dans le module 9.
