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

## Revue

### Passe 1 (2026-10-25, SHA revu ad695c8)

Rebasée sur origin/main 8b1245f (story 2 fusionnée).

- Important, medium, second avis 1 : course entre `clear_cache` et `send` (vidage hors verrou pendant une génération). Corrigé : le vidage est mis en file sur le worker (`_run_clear_cache`) sous `_memory_lock` et `_lock`, comme `_start`. Il passe donc avant tout tour envoyé ensuite et jamais pendant une génération.
- Important, medium, second avis 2 : un préremplissage en cours continuait pendant le vidage. Corrigé par le même mécanisme : un worker unique, donc le vidage attend la fin du lot en cours (préremplissage annulé après la mise en file).
- Important, low, second avis 3 : dans l'ordre « vider le cache » puis « vider la conversation », la cause `reset` écrasait la cause et aucun `prefix_not_reused` n'était émis (`_main_cache == []`). Corrigé : drapeau `_cache_cleared`, consommé au premier appel du tour. Si le moteur est toujours vide, la cause est `cache_cleared` dans les deux ordres. Si un préremplissage l'a rempli entre-temps, c'est la règle normale. Test `test_a_cleared_cache_stays_the_cause_after_a_cleared_conversation`.
- Important, medium, second avis 4 : seul le slot 0 était effacé. Or WaveStack ne lance pas llama-server, et les builds récents ouvrent plusieurs slots par défaut (`-np`). Corrigé : `GET /slots`, puis effacement de chaque slot listé, avec repli sur le slot 0. Le faux serveur liste son slot. Test `test_llama_server_clear_cache_erases_every_slot_it_lists`. `n_erased` n'est pas vérifié : 0 est légitime pour un slot vide.
- Nit, low, second avis 5 : après un échec ou un `False`, la session gardait `_main_cache`. Corrigé : sur `False` (ids oubliés), `_main_cache = None`, sans comparaison ni fausse cause. Sur une exception (serveur sans l'API des slots, mémoire intacte), il est gardé. Test `test_a_refused_clear_names_no_cleared_cache`.
- Nit, low, second avis 6 : `sys.modules` modifié sans nettoyage dans le nouveau test. Corrigé (`monkeypatch.setitem`). Le test voisin plus ancien a le même motif (Pre-existing, non corrigé).
- Nit, low, second avis 7 : trois captures binaires régénérées hors périmètre. Corrigé : rétablies à leur version d'origin/main.
- Report : la course vidage et génération sur `LlamaCppEngine` réel n'a pas de test automatique (pas de GGUF en CI). Vérification à faire à la main : cliquer « Vider le cache » pendant le préremplissage d'un scénario, puis envoyer un message.
