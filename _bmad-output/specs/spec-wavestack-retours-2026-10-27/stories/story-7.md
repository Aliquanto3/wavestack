---
title: 'Story 16.7 : Onglet Sécurité refondu'
type: 'feature'
created: '2026-10-27'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-retours-2026-10-27/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-retours-2026-10-27/ux-securite.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-retours-2026-10-27/maquette-securite.html'
---

## Intent

CAP-10, seconde moitié : implémenter la maquette de la story 16.4 (validée par Anaël), par les
tokens de DESIGN.md et les composants déjà dans `pages.css` (disclosure-row, status-chip,
button-primary/secondary). Vague V1, après 16.1 (barre, Journal) et 16.4 (maquette).

## Ce qui a été fait

1. **`security_state()`** (`app_session.py`) : chaque ligne de `risk_matrix` gagne `tools`
   (`id`, `label_text`, `rule`), tiré de `row["rules"]` de `ToolPolicy.matrix()` ; vide pour
   la ligne « network » (aucun outil nommé).
2. **`security.html` / `security.js`** : les 4 cartes-questions deviennent des boutons qui
   défilent vers leur section, y posent le filtre utile (matrice « écriture », journal
   « autorisés »/« refusés ») et donnent le focus au titre de la section (`tabindex="-1"` sur
   les `<h2>`) ; le schéma « Le chemin d'un message » (5 étapes, `#sec-path`) ; les filtres en
   pastille de la matrice (`#sec-matrix-filters`) et du journal (`#sec-matrix-filters`,
   `#sec-journal-filters`, comptes dynamiques) ; chaque ligne de la matrice se déplie sur ses
   outils et « Pourquoi ce risque » ; la légende « Ce qui se clique », repliée par défaut
   (`#sec-legend`). Les id `#sec-questions`, `#sec-matrix-body`, `#sec-controls`,
   `#sec-journal`, `#sec-limits` sont gardés, l'E2E existant (`s_security_page`) n'a rien à
   réaligner.
3. **`pages.css`** : les états `:hover`/`:focus-visible` du motif disclosure-row, portés sur
   `.bar-log-row` et `.sec-row` (jamais sur le seul `.disclosure-row`, que les `<details>`
   FinOps de `app.js` portent aussi, sans le motif bouton+chevron) ; `.disclosure-row-label
   small` pour le sous-texte (« ce que fait ce contrôle ») des lignes de « Contrôles actifs ».
   Les classes propres à la page (`filter-chip`, `call-path`, `call-step`, `sec-why`,
   `mx-toggle`) restent dans `security.html`, comme les styles déjà propres à cette page.
4. **Textes** (fr, en, de) : `security.path.*`, `security.{matrix,controls,journal}.why`,
   `security.matrix.why_label`, `security.matrix.{id}.why` (7 lignes), `security.controls.what.*`
   (7 contrôles), `security.journal.filters.*`, `security.matrix.filter_*`,
   `security.legend.*`, `security.questions.go_*` ; `security.questions.not_covered`
   (`messages.yaml`) devient « à dire au client ».
5. **Accessibilité** : `aria-expanded`/`aria-controls` sur chaque ligne dépliable (matrice et
   disclosure-row), `aria-pressed` sur les filtres, focus qui suit le défilement déclaré par
   une carte ou une étape du chemin, aucun survol sans son équivalent au focus clavier.

## Écarts avec la maquette

- La légende « Ce qui se clique » n'a pas repris la démonstration à trois états (repos,
  survol, focus) de la maquette (flourish de revue de design) : une liste de phrases décrit
  chaque affordance, plus courte, dans la même ligne dépliable.
- Les textes `reason_text` du journal restent ceux déjà produits par le serveur
  (`security_log.py`, `guardrails.decisions.*`) : la maquette les marquait « texte d'exemple ».

## Tests

- `tests/test_security_page.py` : le champ `tools` de chaque ligne de la matrice (présence,
  vide pour « network »).
- Suite ciblée relancée : sécurité, `test_ui_texts`, `test_i18n`, `test_content_language`,
  `test_web_app`.

## E2E à rejouer (non lancé par cette story, poste partagé du run)

`uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only glossary security_page`
