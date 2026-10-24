---
title: 'Story 1 : données de cache par appel'
type: 'feature'
created: '2026-10-24'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/brownfield.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les champs de cache d'un appel cloud ne sont émis que si l'entrée déclare un `pricing` (`cloud_base.py:1029-1048`) et seulement quand le cache a servi. Un appel local ne porte que `kv_cache_tokens` (moteur `llama-server` seulement) et `evaluated_tokens`, sans forme commune. Les stories 2 à 5 (jauge, vidage, bilan, cache Claude) n'ont donc pas de donnée uniforme à lire.

**Approach:** Fixer une fois, dans `ModelCallEndedPayload` (`trace/catalog.py`), un jeu de champs de cache lu par toutes les stories du lot : trois cases de tokens, la part d'écriture à 1 h et l'origine de la mesure. Les remplir pour chaque appel, local ou cloud, avec ou sans prix. Les champs de coût existants ne changent pas.

## Boundaries & Constraints

**Contrat du lot (noms figés, stories 2 à 5) :**

| Champ | Type | Sens |
|---|---|---|
| `cache_origin` | `Literal["local", "provider"] \| None` | Qui a mesuré : `local` (mémoire de contexte du moteur), `provider` (usage du fournisseur). `None` seulement pour une trace antérieure au lot. |
| `cache_read_tokens` | `int \| None` | Lecture cache : tokens du prompt repris du cache. |
| `cache_write_tokens` | `int \| None` | Écriture cache : tokens du prompt écrits dans le cache par cet appel, toutes durées confondues. |
| `cache_write_1h_tokens` | `int \| None` | Part de `cache_write_tokens` écrite pour 1 h (Claude). Le reste est écrit pour 5 min. `None` si le fournisseur ne détaille pas. |
| `cache_uncached_tokens` | `int \| None` | Non caché : tokens du prompt ni lus ni écrits. |

**Lecture de `None` (règle unique pour les stories 2 à 4) :**
- Un entier, 0 compris, est une valeur mesurée. `None` n'est jamais affiché ni sommé comme 0.
- `None` se lit avec `cache_origin` :
  - `provider` : « non déclaré par le fournisseur » ;
  - `local` + `cache_uncached_tokens` : « sans objet en local » (le moteur conserve tout ce qu'il évalue) ;
  - `local` + `cache_read_tokens` ou `cache_write_tokens` : « non mesuré » (le moteur n'a rien dit).
- Invariant : quand `cache_read_tokens` et `cache_write_tokens` sont non `None`, `read + write + (uncached or 0) == prompt_tokens`. En local, `read + write == prompt_tokens`.

**Changement de sémantique :** `cache_read_tokens` et `cache_write_tokens` existent déjà (`catalog.py:454-455`, « absents quand l'appel n'a ni lu ni écrit », remplis par `cache_savings`). Ils deviennent présents sur chaque appel mesuré, 0 compris, et ne viennent plus que de la nouvelle fonction `cache_tokens()`. `cache_savings()` ne les renvoie plus : sinon `payload |= cache` écraserait le `None` de l'écriture OpenAI par 0. Les autres champs de cache (`cache_full_usd`, `cache_write_usd`, `cache_saved_usd`, `cache_priced`, `cache_source`) restent émis comme aujourd'hui, seulement avec un `pricing` et un cache qui a servi.

**Règles par source :**
- **Local** (`cache_origin: "local"`, `app_session.py`, première génération de l'appel, comme `_kv_fields`) :
  - lu = `kv_cache_tokens` si le moteur le donne (`llama-server`), sinon `prompt_tokens − evaluations[0]` (`n_p_eval` de llama.cpp pour le moteur intégré et le faux moteur, qui n'ont pas `last_cache_reuse`) ;
  - écrit = `prompt_tokens − lu`, borné à `[0, prompt_tokens]` ;
  - non caché = `None` (sans objet en local) ; `cache_write_1h_tokens` = `None` ;
  - si le moteur ne donne ni `kv_cache_tokens` ni `evaluations[0]` : lu et écrit valent `None`.
  - Ce sont des comptes du moteur, pas une mesure du harnais. Un préremplissage (E122) avant l'appel compte comme une lecture de cet appel.
- **Fournisseur, usage présent** (`cache_origin: "provider"`, `cloud_base.py`), à partir du pivot (`prompt_tokens_details`) :
  - lu = `cached_tokens` du pivot s'il y figure, 0 compris ; `None` s'il est absent ou illisible (`NaN`, booléen), car le fournisseur ne l'a pas déclaré (Mistral, Groq… sans `prompt_tokens_details`). Les adaptateurs Anthropic et Responses ne posent `cached_tokens` et `cache_write_tokens` dans le pivot que si la réponse porte le compte correspondant (revue, passe 1). Le coût (`_cached_tokens`, `call_cost`) garde 0 pour un absent ;
  - écrit = `cache_write_tokens` du pivot s'il y figure (seul l'adaptateur Anthropic le pose, 0 compris), sinon `None` ;
  - `cache_write_1h_tokens` = `cache_write_1h_tokens` du pivot s'il y figure, sinon `None`. L'adaptateur Anthropic le pose depuis `usage.cache_creation.ephemeral_1h_input_tokens` quand ce détail existe ;
  - non caché = `prompt_tokens − lu − (écrit or 0)`, `None` si lu est `None`. Pour Anthropic, c'est `input_tokens` par construction du pivot. Pour les autres, la case inclut une éventuelle écriture non déclarée ;
  - les valeurs sont bornées comme dans `cache_savings` : lu ≤ `prompt_tokens`, écrit ≤ `prompt_tokens − (lu or 0)`, négatif → 0.
- **Fournisseur, usage absent ou inutilisable** (`usage_source: "estimate"`, appel en erreur sans usage, ou pivot sans `prompt_tokens` > 0) : `cache_origin: "provider"`, toutes les cases à `None`.
- Le prix n'entre pas en jeu : les cases sont émises sans `pricing`, y compris pour Groq, Mistral, Gemini et Gemma. La règle dépend du pivot, pas du nom de l'API : un fournisseur compatible OpenAI qui poserait `cache_write_tokens` dans le pivot serait déclaré.

**Never:**
- Pas de rendu, de jauge ni de bouton (stories 2 et 3), pas de changement de `record_spend` ni de `ConsumptionUpdatedPayload` (story 4), pas de `cache_control` ni de prix 1 h (story 5).
- Pas de nouvelle dépendance, pas de renommage des champs existants.
- Pas de mesure côté harnais à la place de celle du moteur ou du fournisseur.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Local `llama-server`, cache réutilisé | prompt 1000, `cache_n=900` | read 900, write 100, uncached `None`, origin `local` | N/A |
| Local intégré ou faux moteur, cache réutilisé | prompt 1000, `last_evaluated=100`, pas de `last_cache_reuse` | read 900, write 100, uncached `None` | N/A |
| Local, premier appel | prompt 1000, évalué 1000 | read 0, write 1000, uncached `None` | N/A |
| Local sans mesure | ni `last_evaluated` ni `last_cache_reuse` | read, write, uncached `None`, origin `local` | N/A |
| Anthropic, lecture et écriture | `cache_read=800`, `cache_creation=150`, `input_tokens=50` | read 800, write 150, uncached 50, origin `provider` | N/A |
| Anthropic, écriture 1 h détaillée | `cache_creation={ephemeral_5m: 100, ephemeral_1h: 50}` | write 150, write_1h 50 | N/A |
| Anthropic, rien de caché | `cache_*=0`, `input_tokens=1000` | read 0, write 0, uncached 1000 (déclarés) | N/A |
| Compatible OpenAI, lecture | `prompt_tokens=1000`, `cached_tokens=600` | read 600, write `None`, uncached 400 | N/A |
| Compatible OpenAI, sans détail | usage sans `prompt_tokens_details` (ou sans `cached_tokens`) | read, write, uncached `None` (non déclaré) ; `cached_tokens: 0` déclaré → read 0, uncached = `prompt_tokens` | N/A |
| Entrée sans `pricing` | Groq ou Mistral, usage présent | cases remplies comme ci-dessus ; aucun champ de coût de cache | N/A |
| Entrée avec `pricing`, cache servi | Gemini, `cached_tokens=800` | champs de coût de cache inchangés ; `cache_write_tokens` `None` (plus 0) | N/A |
| Usage estimé | pas d'usage dans la réponse | toutes les cases `None`, origin `provider` | N/A |
| Valeur illisible ou hors bornes | `cached_tokens` `NaN` ou booléen ; négatif ; > `prompt_tokens` | `None` (non déclaré) ; 0 ; borné à `prompt_tokens` | Aucune exception |
| Appel refusé avant sortie | erreur HTTP sans usage | toutes les cases `None` | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/trace/catalog.py:427-474` `ModelCallEndedPayload` -- ajouter `cache_origin`, `cache_write_1h_tokens`, `cache_uncached_tokens` ; réécrire le commentaire de `cache_read_tokens` et `cache_write_tokens` (contrat ci-dessus, lecture de `None`). Seul endroit où les noms sont définis.
- `src/wavestack/models/cloud_base.py:362-378` `_cached_tokens` -- distinguer « absent » (`None`) de 0 pour l'écriture ; `call_cost` reçoit `or 0`, son résultat ne change pas.
- Nouvelle fonction pure `cache_tokens(usage, prompt_tokens, usage_source)` dans `cloud_base.py`, qui renvoie les cinq champs ; testable sans réseau. Appelée dans `ended()` (`:1000-1055`) hors de la condition `pricing is not None`, et sous `produced` (sinon cases `None`).
- `src/wavestack/models/cloud_base.py:325-359` `cache_savings` -- retirer `cache_read_tokens` et `cache_write_tokens` de son dict (collision avec `cache_tokens`) ; garder ses entrées et ses autres clés.
- `src/wavestack/models/anthropic_messages.py:45-60` `pivot_usage` -- ajouter `cache_write_1h_tokens` à `prompt_tokens_details` quand `usage.cache_creation.ephemeral_1h_input_tokens` est un entier. Pas besoin d'y mettre le non caché : `prompt − read − write` vaut `input_tokens` par construction.
- `src/wavestack/session/app_session.py:8546-8583` `end()` et `:8781` `_kv_fields` -- ajouter les champs locaux depuis `kv_reuse`, `evaluations[0]` et `len(rendered.ids)`. Seuls émetteurs de `model_call_ended` : `cloud_base.py:1055` et `app_session.py:8564` (vérifier par `git grep '"model_call_ended"' src`).
- Lecteurs existants, vérifiés : `app.js:2577` `cacheNode` reste conditionné à `cache_saved_usd` (émis comme avant) et teste `cache_write_tokens` en vérité : `None` et 0 donnent tous deux « aucune écriture », rendu inchangé. Le libellé « non déclaré » pour OpenAI revient à la story 2. `kvCacheNode` lit `kv_cache_tokens`, inchangé. `bar.js`, `llm.js`, `mcp.js` ne lisent pas ces champs. `record_spend` reçoit `cache_saved_usd` comme avant.

## Tasks & Acceptance

**Execution:**
- [ ] `trace/catalog.py` -- trois nouveaux champs ; commentaire du contrat.
- [ ] `models/cloud_base.py` -- `cache_tokens()` pure, émission sans `pricing`, `_cached_tokens` qui sait « absent », `cache_savings` sans les deux champs de tokens.
- [ ] `models/anthropic_messages.py` -- `cache_write_1h_tokens` dans le pivot.
- [ ] `session/app_session.py` -- champs locaux dans `end()`.
- [ ] `tests/test_cache_per_call.py` -- cas de la matrice : faux moteur local (`tests/fake_engine.py`, sans `last_cache_reuse`) sur deux appels d'affilée, faux `llama-server` (`cache_n`), fausse réponse Anthropic (lecture, écriture, détail 1 h), fausse réponse compatible OpenAI (lecture seule), avec et sans `pricing` ; invariant de somme ; usage estimé ; erreur sans usage.
- [ ] Tests existants à réaligner : `tests/test_cloud_cap.py:372` (`cache_savings` ne renvoie plus les tokens : lire les cases dans `model_call_ended`) ; `:473` reste vrai (le pivot y porte `cache_write_tokens`) ; `tests/test_anthropic_messages.py` (pivot). Puis `git grep -n "cache_read_tokens\|cache_write_tokens\|pivot_usage" tests tools` pour le reste, E2E compris.

**Acceptance Criteria:**
- Given le faux moteur local (sans `last_cache_reuse`) et deux questions d'affilée, when le second appel se termine, then `model_call_ended` porte `cache_read_tokens > 0`, `read + write == prompt_tokens`, `cache_uncached_tokens is None` et `cache_origin == "local"`.
- Given un faux `llama-server` qui renvoie `cache_n`, then `cache_read_tokens == kv_cache_tokens`.
- Given une fausse réponse Anthropic avec lecture et écriture, when l'appel se termine, then les trois cases sont déclarées et leur somme égale `prompt_tokens` ; avec `cache_creation` détaillé, `cache_write_1h_tokens` est renseigné.
- Given une fausse réponse compatible OpenAI sans prix déclaré, when l'appel se termine, then `cache_write_tokens` vaut `None` et les deux autres cases sont renseignées.
- Given un usage estimé ou une erreur sans usage, then toutes les cases valent `None` et `cache_origin == "provider"`.
- Given une entrée avec prix, when la suite ciblée tourne, then `cost_*`, `cache_full_usd`, `cache_write_usd`, `cache_saved_usd`, `cache_priced`, `cache_source` et le `consumption_updated` émis sont inchangés.

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_cache_per_call.py tests/test_cloud_cap.py tests/test_anthropic_messages.py tests/test_model_servers.py tests/test_turn_cache.py` -- expected : vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected : vert.

## Spec Change Log

- 2026-10-24, revue de spec (point de contrôle tenu pour Anaël) :
  - Local : non caché `None` (sans objet), et non plus 0, qui est une valeur mesurée. La jauge distingue « sans objet » de « non déclaré » par `cache_origin`.
  - Local : lu dérivé de `prompt_tokens − evaluations[0]` quand le moteur n'a pas `last_cache_reuse`. Le moteur intégré et le faux moteur n'en ont pas : sans cette règle, la jauge de la story 2 et son E2E n'auraient rien eu à lire en local.
  - Écriture déclarée d'après le pivot, et non d'après le nom de l'API, ce qui garde vert `test_cloud_cap.py:444`.
  - `cache_savings` ne renvoie plus les tokens, pour éviter que son 0 écrase le `None`.
  - Nouveau champ `cache_write_1h_tokens`, pour les colonnes « Écriture cache 5 min » et « 1 h » du bilan (stories 4 et 5).
  - Usage présent sans `prompt_tokens` : cases `None`, et non un non-caché estimé.
  - `pivot_usage` n'a pas besoin du non caché.

## Review Triage Log

## Revue

### Passe 1 (2026-10-24, SHA revu ab89fb3)

- Important, medium, second avis (2) : un usage compatible OpenAI sans `prompt_tokens_details` (Mistral, Groq) donnait lu = 0 « mesuré », contraire à CAP-1. Corrigé : lu et non caché `None` quand `cached_tokens` est absent ou illisible, 0 gardé s'il est déclaré ; les pivots Anthropic et Responses n'inventent plus de 0 pour un compte absent. Contrat mis à jour ci-dessus, tests ajoutés.
- Pre-existing, low, second avis (1) : un moteur local qui échoue avant d'appeler sa génération laisserait `last_evaluated` de l'appel précédent ; les moteurs le remettent à `None` en tête de génération, et `evaluated_tokens` partage déjà cette source. Non corrigé.
- Nit, low, second avis (7) : imports de helpers d'autres modules de test. Rejeté : pratique établie du dépôt (50 fichiers).
