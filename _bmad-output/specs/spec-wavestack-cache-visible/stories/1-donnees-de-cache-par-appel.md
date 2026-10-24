---
title: 'Story 1 : données de cache par appel'
type: 'feature'
created: '2026-10-24'
status: 'ready-for-dev'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/brownfield.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les champs de cache d'un appel cloud ne sont émis que si l'entrée déclare un `pricing` (`cloud_base.py:1044-1048`) et seulement quand le cache a servi. Un appel local ne porte que `kv_cache_tokens` et `evaluated_tokens`, sans forme commune. Les stories 2 à 5 (jauge, bilan, vidage, cache Claude) n'ont donc pas de donnée uniforme à lire.

**Approach:** Fixer une fois, dans `ModelCallEndedPayload` (`trace/catalog.py`), un jeu de quatre champs de cache lu par toutes les stories du lot : trois cases de tokens et leur origine. Les remplir pour chaque appel, local ou cloud, avec ou sans prix. Une case que le fournisseur ne remonte pas vaut `None` (« non déclaré »), jamais 0. Les champs de coût existants ne changent pas.

## Boundaries & Constraints

**Contrat du lot (noms figés, stories 2 à 5) :**

| Champ | Type | Sens |
|---|---|---|
| `cache_read_tokens` | `int \| None` | Lecture cache : tokens du prompt repris du cache. |
| `cache_write_tokens` | `int \| None` | Écriture cache : tokens du prompt écrits dans le cache par cet appel. |
| `cache_uncached_tokens` | `int \| None` | Non caché : tokens du prompt ni lus ni écrits. |
| `cache_origin` | `Literal["local", "provider"] \| None` | Qui a mesuré : `local` (mémoire de contexte du moteur), `provider` (usage du fournisseur), `None` (appel antérieur au lot ou sans mesure). |

- Les trois cases sont des entiers positifs ou nuls, ou `None`. `None` signifie « non déclaré par le fournisseur » ; la jauge et le bilan l'affichent ainsi, jamais comme 0. Un `0` est une valeur déclarée.
- `cache_read_tokens` et `cache_write_tokens` existent déjà (`catalog.py:454-455`, « absents quand l'appel n'a ni lu ni écrit »). Ils changent de sémantique : présents sur chaque appel mesuré, 0 compris. Les lecteurs existants (`app.js` `cacheNode`, `record_spend`, `cache_savings`) sont réalignés pour ne pas confondre 0 et absent.
- Les autres champs de cache existants (`cache_full_usd`, `cache_write_usd`, `cache_saved_usd`, `cache_priced`, `cache_source`) restent émis comme aujourd'hui, uniquement quand l'entrée a un `pricing` et que le cache a servi.
- Invariant : quand les trois cases sont non `None`, leur somme égale `prompt_tokens`.

**Règles par source :**
- **Local** (`cache_origin: "local"`) : lu = `kv_cache_tokens`, écrit = `evaluated_tokens`, non caché = `0` (il n'y a pas de « non caché » en local : tout ce qui est évalué est conservé). Si le moteur ne dit ni l'un ni l'autre (pas de `timings`), les trois valent `None`.
- **Anthropic** (`cache_origin: "provider"`) : lu = `cache_read_input_tokens`, écrit = `cache_creation_input_tokens`, non caché = `input_tokens`. Les trois sont déclarés, 0 compris.
- **Compatible OpenAI** (`openai_chat`, `openai_responses`) : lu = `cached_tokens` (0 si l'usage est présent sans ce champ), écrit = `None` (non déclaré), non caché = `prompt_tokens − lu`. Cette dernière case inclut une éventuelle écriture non déclarée.
- **Usage absent ou estimé** (`usage_source: "estimate"`, appel en erreur sans usage) : `cache_origin: "provider"`, les trois cases à `None`.
- Le prix n'entre pas en jeu : les cases sont émises sans `pricing`, y compris pour Groq, Mistral, Gemini et Gemma.

**Never:**
- Pas de rendu, de jauge ni de bouton (stories 2 et 3), pas de changement de `record_spend` ni de `ConsumptionUpdatedPayload` (story 4), pas de `cache_control` (story 5).
- Pas de nouvelle dépendance, pas de renommage des champs existants.
- Pas de mesure côté harnais à la place de celle du moteur ou du fournisseur.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Local, cache réutilisé | `kv_cache_tokens=900`, `evaluated_tokens=100` | read 900, write 100, uncached 0, origin `local` | N/A |
| Local, premier appel | `kv_cache_tokens=0`, `evaluated_tokens=1000` | read 0, write 1000, uncached 0 | N/A |
| Local sans mesure | pas de `timings` du moteur | trois cases `None`, origin `local` | N/A |
| Anthropic, lecture et écriture | `cache_read=800`, `cache_creation=150`, `input_tokens=50` | read 800, write 150, uncached 50 | N/A |
| Anthropic, rien de caché | `cache_*=0`, `input_tokens=1000` | read 0, write 0, uncached 1000 (déclarés) | N/A |
| Compatible OpenAI, lecture | `prompt_tokens=1000`, `cached_tokens=600` | read 600, write `None`, uncached 400 | N/A |
| Compatible OpenAI, sans détail | usage sans `prompt_tokens_details` | read 0, write `None`, uncached = `prompt_tokens` | N/A |
| Entrée sans `pricing` | Groq ou Mistral, usage présent | cases remplies comme ci-dessus ; aucun champ de coût de cache | N/A |
| Usage estimé | pas d'usage dans la réponse | trois cases `None`, origin `provider` | N/A |
| Valeur illisible | `cached_tokens` = `NaN`, négatif ou booléen | traité comme 0 (comportement de `_cached_tokens`) | Aucune exception |
| Appel refusé avant sortie | erreur HTTP sans usage | trois cases `None` | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/trace/catalog.py:427-474` `ModelCallEndedPayload` -- ajouter `cache_uncached_tokens` et `cache_origin` ; commenter `cache_read_tokens` et `cache_write_tokens` (nouvelle sémantique, `None` = non déclaré). Seul endroit où les noms sont définis.
- `src/wavestack/models/cloud_base.py:1025-1070` -- lever la condition `pricing is not None` pour les trois cases ; garder `call_cost` et `cache_savings` sous `pricing`. `:362-378` `_cached_tokens` : distinguer « absent » de 0.
- `src/wavestack/models/cloud_base.py:325-359` `cache_savings` -- ne plus porter `cache_read_tokens` ni `cache_write_tokens` en doublon (les cases viennent de la nouvelle fonction), ou les garder égales.
- Nouvelle fonction pure `cache_tokens(api, usage, prompt_tokens, usage_source)` dans `cloud_base.py`, qui renvoie les quatre champs ; testable sans réseau.
- `src/wavestack/models/anthropic_messages.py:47-59` `pivot_usage` -- ajouter `input_tokens` (non caché) au pivot (`prompt_tokens_details.uncached_tokens`) pour que `cache_tokens` n'ait pas à le déduire.
- `src/wavestack/session/app_session.py:8578, 8788` `_kv_fields` -- ajouter les quatre champs locaux à partir de `kv_reuse` et `evaluated`. Voir aussi `:4884` et tout autre émetteur local de `model_call_ended` (`git grep '"model_call_ended"'`).
- Lecteurs à réaligner : `src/wavestack/web/static/app.js:2577-2610` `cacheNode` (0 et `None` différents), `cloud_base.py:1062-1070` (`cache_saved_usd`).

## Tasks & Acceptance

**Execution:**
- [ ] `trace/catalog.py` -- champs `cache_uncached_tokens`, `cache_origin` ; commentaire du contrat.
- [ ] `models/cloud_base.py` -- `cache_tokens()` pure, émission sans `pricing`, `_cached_tokens` qui sait « absent ».
- [ ] `models/anthropic_messages.py` -- non caché dans le pivot.
- [ ] `session/app_session.py` -- champs locaux dans `_kv_fields` et les autres émetteurs.
- [ ] `app.js` `cacheNode` et autres lecteurs -- réaligner sur la nouvelle sémantique (rendu inchangé pour l'utilisateur).
- [ ] `tests/test_cache_per_call.py` -- cas de la matrice avec un faux moteur local, une fausse réponse Anthropic (lecture et écriture) et une fausse réponse compatible OpenAI (lecture seule), sur des entrées avec et sans `pricing` ; invariant de somme ; usage estimé.
- [ ] Tests existants sur `cache_read_tokens` / `cache_write_tokens` (`git grep -n "cache_read_tokens\|cache_write_tokens" tests tools`) -- réaligner, E2E compris.

**Acceptance Criteria:**
- Given un faux moteur local avec réutilisation du cache, when l'appel se termine, then `model_call_ended` porte read, write, uncached et `cache_origin: "local"` selon la matrice.
- Given une fausse réponse Anthropic avec lecture et écriture, when l'appel se termine, then les trois cases sont déclarées et leur somme égale `prompt_tokens`.
- Given une fausse réponse compatible OpenAI sans prix déclaré, when l'appel se termine, then `cache_write_tokens` vaut `None` et les deux autres cases sont renseignées.
- Given un usage estimé, then les trois cases valent `None`.
- Given une entrée avec prix, when la suite ciblée tourne, then les champs de coût de cache sont inchangés.

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_cache_per_call.py` plus les tests existants touchés (cache, finops, anthropic) -- expected : vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected : vert.

## Spec Change Log

## Review Triage Log
