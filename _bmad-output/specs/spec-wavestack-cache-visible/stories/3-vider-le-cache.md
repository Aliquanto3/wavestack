---
title: 'Story 3 : vider le cache'
type: 'feature'
created: '2026-10-24'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/brownfield.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/stories/2-jauge-du-cache.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le formateur ne peut pas montrer ce que fait une expiration du cache sans attendre (CAP-4).

**Approach:** Un bouton « Vider le cache » à côté des actions de conversation vide la mémoire de contexte du moteur local, sans recharger le modèle ni toucher à la conversation. L'appel suivant relit tout (écriture complète) et `prefix_not_reused` porte la nouvelle cause `cache_cleared` (« cache vidé »), que la jauge de la story 2 affiche.

## Boundaries & Constraints

- Moteur intégré : `kv_cache_clear` puis `Llama.reset`, modèle gardé. llama-server : `POST /slots/0?action=erase`, serveur non redémarré. Un moteur sans `clear_cache` (Ollama, cloud) ou un serveur sans l'API des slots : refus 409 avec la raison.
- Cloud : bouton grisé, infobulle « le cache d'un fournisseur ne se purge pas » ; refusé aussi côté serveur. Grisé pendant un tour (comme « Vider la conversation »).
- `PrefixCause` reçoit `cache_cleared` en fin de liste ; texte dans `main.orch.prefix_causes` (fr, en, de) et message du journal dans `session.prefix.causes`. L'événement est émis même si le préfixe de l'appel suivant aurait été réutilisable.
- Faux moteur de l'E2E : le faux llama-server vide vraiment son prompt gardé sur la route des slots.
- Fichiers carrefour : ajouts seulement.

**Never:** pas de nouvel événement, pas de changement de payload, pas de purge côté fournisseur.

</frozen-after-approval>

## Code Map

- `models/engine.py` `LlamaCppEngine.clear_cache` ; `models/servers.py` `LlamaServerEngine.clear_cache` ; `session/app_session.py` `AppSession.clear_cache`, `_check_reuse` ; `web/app.py` `/api/intentions/clear_cache` ; `index.html` `#clear-cache`, `app.js` `clearCache`, `renderComposer` ; `content/{,i18n/en/,i18n/de/}{ui,messages}.yaml`.
- `tools/e2e/fake_local_server.py` route `/slots/{id}` ; `run_e2e.py` `_cache_clear` (scénario `local_server`) ; `tests/test_turn_cache.py`, `tests/test_model_servers.py`, `tests/fake_engine.py`.

## Verification

- `uv run pytest -q --tb=short tests/test_turn_cache.py tests/test_cache_gauge_texts.py tests/test_ui_texts.py tests/test_i18n.py tests/test_model_servers.py`
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only local_server` : vert (lecture non nulle, clic, puis lecture 0, écriture = prompt, cause `cache_cleared` citée par la jauge).

## Reports

- `LlamaCppEngine.clear_cache` n'a pas de test automatique (pas de GGUF en CI) ; le repli (`kv_cache_clear` absent) renvoie `False` et le bouton affiche le refus.
- Le grisé en cloud et pendant un tour n'a pas d'E2E propre (même logique que « Vider la conversation »).
- Ollama (moteur brut) n'a pas de `clear_cache` : refus avec raison.
