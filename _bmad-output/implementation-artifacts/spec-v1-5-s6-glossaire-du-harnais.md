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

## Revue

### Passe 1 (2026-10-25, SHA revu de484e94)

- Important · medium · second avis 1 · corrigé : `yaml.YAMLError` ne dérive pas de `ValueError`, une traduction au YAML mal formé donnait un 500. `load_terms` la convertit en `GlossaryError` ; test de la route (repli sur le français, 200), qui échoue sur l'ancien code.
- Nit · low · second avis 2 · corrigé : `term`/`definition` non textuels (`404`, liste) étaient acceptés, puis `localeCompare` plantait côté JS. Le chargeur exige des `str` ; cas ajoutés au test de refus.
- Nit · low · second avis 3 · rejeté : la branche `glossary.yaml` de `test_translated_file_mirrors_the_french_one` est vivante (`_translations()` parcourt `content/i18n/{en,de}`, 4 cas collectés).
- Nit · low · second avis 4 · corrigé : le test de la clé inconnue n'exécutait pas le contrôle. Contrôle extrait dans `_unknown_citations`, testé sur un fichier temporaire.
- Nit · low · second avis 5 · rejeté : panneau non modal (`aria-modal=false`), Échap hors du panneau n'a pas à le fermer ; le focus est posé après `hidden = false`.
- Nit · low · second avis 6 · corrigé : l'exclusion ne regardait que le parent direct (bouton imbriqué dans `<button>` ou `<a>`, citation dans `<pre><span>`). `closest()` sur une liste élargie à `button, a`. E2E `glossary` : 50/50.
- Nit · low · second avis 7 · laissé : E2E dépendant du contenu et du libellé français, cohérent avec les autres scénarios E2E.
- Complexité : 0 constat (observateur du DOM en O(nœuds ajoutés), 58 termes).
