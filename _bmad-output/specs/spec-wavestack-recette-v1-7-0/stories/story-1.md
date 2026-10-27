---
title: 'Story 17.1 : Barre, montants en dollars et largeur'
type: 'fix'
created: '2026-10-27'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/src/wavestack/web/static/bar.js'
  - '{project-root}/content/ui.yaml'
---

## Intent

Correctifs de recette v1.7.0 (CAP épuisée) sur la barre commune (« Dépense » et « Journal »,
`bar.js`) : trois défauts relevés par Anaël. (a) Le Bilan de la Dépense mélange dollars (coût
par appel, plafond) et une conversion en euros (`spend_sentence`, `free_sentence`) : tout
passer en dollars, sans taux de change. (b) À 1272 px, la page Modèles déborde de 7 px : le
bouton « Dépense » s'élargit à 393 px quand la mention d'offre gratuite (longue phrase) se
glisse dans son badge, en `white-space: nowrap`. (c) À 360 px, les panneaux Bilan et Journal ne
doivent pas déborder horizontalement (déjà testé par `s_bar_journal`, à revérifier après (a)
et (b)).

## Given/When/Then

- **(a)** Given une séance avec au moins un appel payant, When le panneau « Dépense » affiche
  sa phrase détaillée, Then elle ne montre qu'un total en dollars (`usd`), sans taux ni signe
  €, comme le montant du bouton.
- **(a)** Given une séance sans appel payant mais avec des appels à un modèle sans prix
  déclaré, When le panneau affiche `free_sentence`, Then elle dit « 0 $ », jamais « 0 € ».
- **(b)** Given un appel à un modèle sans prix déclaré, When le bouton « Dépense » affiche son
  badge, Then le badge reste court (« Offre gratuite », pas la phrase complète) et le bouton ne
  dépasse plus la largeur d'un bouton normal ; le détail complet reste accessible dans l'info-
  bulle du bouton (`title`) et dans le panneau ouvert (`#bar-spend-detail`).
- **(c)** Given la fenêtre à 360 px de large, When les panneaux Bilan et Journal s'ouvrent (et
  leurs lignes dépliées), Then rien n'en dépasse horizontalement.

## Tâches

1. `content/ui.yaml` (+ `content/i18n/en`, `content/i18n/de`) : `main.consumption.spend_sentence`
   perd `{rate}` et le signe € (le total vient de `usd`, pas de `eur`) ; `free_sentence` dit
   « 0 $ » (« $0 » en anglais) au lieu de « 0 € » ; `common.bar.spend.free_tier` raccourci à
   « Offre gratuite » (« Free offer », « Kostenloses Angebot »), le détail restant dans
   `free_sentence` (tooltip + panneau).
2. `src/wavestack/web/static/bar.js` : `detailSentence` passe `total: usd(c.total_eur)` →
   `usd(c.total_usd)`, retire `rate`, retire la fonction `eur()` (devenue sans appelant dans ce
   fichier). Les champs `total_eur` / `eur_per_usd` du payload (`cloud_base.py`,
   `config.py`, `catalog.py`) gardent d'autres appelants (tests, GreenOps, `app_session.py`) :
   ne pas y toucher (hors périmètre de cette story).
3. Pas de changement CSS : le badge raccourci suffit à tenir dans `.bar-button`
   (`white-space: nowrap`) ; les panneaux (`.bar-flyout`) étaient déjà en `white-space: normal`.

## Tests

- `uv run pytest -q --tb=short tests/test_i18n.py tests/test_ui_texts.py tests/test_web_app.py`
  (textes fr/en/de complets et cohérents ; le payload `spend`/`consumption` backend inchangé).
- Contrôle visuel non automatisé : aucun test Python ne lit `bar.js` ni le rendu DOM ; c'est
  l'E2E qui couvre le rendu (voir ci-dessous).

## E2E à rejouer (non lancé par cette story, poste partagé du run)

`uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only bar_panels bar_journal`

- `s_bar_panels` : ouverture/fermeture des deux boutons, montant et badge "économisé" en
  dollars (déjà en dollars, non affecté).
- `s_bar_journal` : `bar_spend_shows_amount_without_pricing` vérifie `"Offre gratuite" in
  saved` (la story garde ce sous-texte, raccourci) ; `bar_spend_popup_no_overflow_360px`
  revérifie (c) après les textes raccourcis.
- Aucun scénario E2E existant ne couvre 1272 px précisément (le signalement d'Anaël) ; le
  raccourci du badge (b) est la correction, à confirmer visuellement par Anaël à la recette.

## Choix faits à la place d'Anaël

- Backend (`total_eur`, `eur_per_usd`) conservé : ces champs ont d'autres appelants
  (`app_session.py`, `catalog.py`, GreenOps, `wavestack.toml`, tests dédiés) ; les retirer serait
  un refactor FinOps plus large, hors périmètre de cette story de recette.
- Badge « Offre gratuite » raccourci plutôt que mis en info-bulle dédiée : le bouton
  (`#bar-spend-toggle`) porte déjà son `title` avec la phrase complète (`detailSentence`), et le
  panneau ouvert la redonne en texte visible (`#bar-spend-detail`) — ajouter une seconde
  info-bulle aurait dupliqué un mécanisme déjà accessible.
