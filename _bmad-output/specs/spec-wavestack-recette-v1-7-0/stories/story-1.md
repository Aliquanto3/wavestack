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

## Revue

### Passe 1 (2026-10-27, SHA revu 0f5ac3f6)

Rebasée sur origin/main (1b3e0c66). Mesures faites avec Edge headless sur `diagnostic.html` et la feuille réelle (pas d'E2E lancé).

- **Important**, high, reviewer + second avis 2 : (c) non corrigé. À 360 px, `.bar-flyout` (content-box : `width` + padding + bordure = 354 px) sortait de 19 px à gauche de la fenêtre, et `.site-nav` en `nowrap` faisait 710 px (page à 735 px de large) ; `_bar_overflows` ne comparait les enfants qu'au panneau et ne voyait rien. Corrigé : `box-sizing: border-box` sur `.bar-flyout`, et `.site-nav` passe à la ligne sous 640 px (mesuré : page 360 px, panneau 7-335 px). Assertion E2E ajoutée : panneau dans la fenêtre et barre commune sans débordement.
- **Important**, medium, second avis 1 : `s_gemini_shape` attendait « € au taux de » dans l'infobulle. Corrigé (« , soit » et aucun « € »), commentaire et libellé réalignés.
- **Important**, medium, second avis 3 : (b) sans garde de non-régression. Mesuré : bouton de 399 px avec l'ancienne phrase (page à 1275 px pour 1272), 196 px avec « Offre gratuite » (page à 1272 px). Ajout dans `s_bar_journal` d'une vérification à 1272 px sur `/diagnostic` après l'appel gratuit (aucun défilement horizontal). Pas de troncature CSS : les badges sont des textes courts bornés, une ellipse cacherait « Mehrkosten des Cache … ».
- **Nit**, low, second avis 4 : `eur()` d'`app.js` sans appelant (déjà avant la story) et clé `common.format.eur` orpheline : retirées (fr, en, de).
- **Nit**, low, second avis 5 et 6 : commentaires de `bar.js` (« 0 € », « like the button's own amount (`usd`) ») corrigés.
- **Nit**, low, reviewer : le panneau passe de 486 à 460 px de large au bureau (border-box) ; accepté.
- Report : E2E `bar_journal`, `bar_panels` à jouer par l'orchestrateur ; `gemini_shape` demande une clé Gemini réelle (service externe), à rejouer quand elle est disponible.
