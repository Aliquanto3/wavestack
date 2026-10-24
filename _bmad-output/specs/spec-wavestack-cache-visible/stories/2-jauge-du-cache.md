---
title: 'Story 2 : jauge du cache'
type: 'feature'
created: '2026-10-24'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/brownfield.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/stories/1-donnees-de-cache-par-appel.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les cases de cache de chaque appel existent (story 1) mais rien ne les montre à côté de la barre de contexte (CAP-2).

**Approach:** Une jauge `#cache-gauge` dans `.top-bar`, juste après `#gauge`, pour le dernier appel : une barre lu / écrit / non caché (largeurs = tokens reçus), un texte court, et le détail complet (cases, cause, note locale) en infobulle et nom accessible. Mise en forme seule : aucun calcul de cache côté page.

## Boundaries & Constraints

- Lecture de `None` (contrat de la story 1) : jamais affiché ni dessiné comme 0. `provider` : « non déclaré par le fournisseur » ; `local` : « sans objet en local » pour le non caché, « non mesuré » pour lu et écrit. En local, la jauge dit qu'il n'y a ni « non caché » ni durée de vie.
- Cause : `prefix_not_reused.cause` qui précède l'appel, texte de `main.orch.prefix_causes` (fr, en, de). Une valeur inconnue s'affiche telle quelle, sans erreur ; un test échoue tant qu'une valeur de `PrefixCause` (celle de la story 3) n'a pas son texte.
- Masquée tant qu'aucun appel ne porte `cache_origin` (trace antérieure au lot).
- Fichiers carrefour : ajouts seulement. Jetons de couleur de DESIGN.md (`state-ok`, `warning`, `muted`) ; sur téléphone, la barre reste (40 px), le texte court part sous 1700 px.

**Never:** pas de bouton de vidage (story 3), pas de bilan (story 4), pas de changement de payload.

</frozen-after-approval>

## Code Map

- `web/static/index.html` `#cache-gauge` ; `app.js` `store.cacheGauge`, `store.cachePrefix`, `renderCacheGauge()` ; `app.css` `.cache-gauge*` ; `content/{,i18n/en/,i18n/de/}ui.yaml` `main.cache_gauge.*`.
- `tools/e2e/fake_local_server.py` : le faux llama-server garde le prompt précédent et n'évalue que la part nouvelle (sans `cache_n`), comme un cache de préfixe.
- `tools/e2e/run_e2e.py` `_cache_gauge` (scénario `local_server`) ; `tests/test_cache_gauge_texts.py`.

## Verification

- `uv run pytest -q --tb=short tests/test_cache_gauge_texts.py tests/test_ui_texts.py tests/test_i18n.py`
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only local_server` : vert (deux questions, lecture non nulle, puis prompt système changé : écriture en hausse, cause citée, barre du haut sans débordement).

## Reports

- Le cas cloud n'a pas d'E2E propre (« non déclaré par le fournisseur » est couvert par la logique de `cacheCellMissing`, sans test navigateur).
- Appels de sous-agent exclus de la jauge (dernier appel du tour principal).
