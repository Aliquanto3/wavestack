# Corrections de la recette v1.7.0

Source : cahier `docs/recette/runs/cahier-2026-10-27-1257.html` (CT-01 à CT-05), constats précisés par Anaël le 2026-10-27.
Objectif : corriger les défauts relevés, une story par écran, puis publier la v1.7.1 (correctifs seulement, pas de fonction nouvelle).

Stories : `stories.yaml` (17.N = id N). Specs de story écrites par `dev-story` dans `stories/story-N.md`.

Contraintes communes :
- Textes en fr, surcouches en et de sous `content/i18n/{en,de}/`.
- Montants en dollars partout, sans taux de change.
- Pas de régression à 360 px ni dans les deux thèmes.
- Tests ciblés et ruff en local ; les E2E nommés dans le rapport sont lancés par l'orchestrateur, un à la fois.
