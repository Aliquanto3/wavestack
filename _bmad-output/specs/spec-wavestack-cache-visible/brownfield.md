# Existant à réutiliser (relevé du 2026-10-23, `main` à `be6124d`)

## Barre de contexte

- **DOM** : `#gauge` (`#gauge-bar`, `#gauge-threshold`, `#gauge-legend`, `#gauge-figures`), dans `.top-bar`, entre `#scenario-picker` et `#window-picker` (`web/static/index.html:260-270`).
- **Rendu** : `renderGauge()` (`app.js:2474-2529`) et `renderGaugeLegend` (`:2534`). Le store (`store.gauge`) se remplit sur `context_preview`, `context_rendered` et `context_reconciled` (`app.js:338, 449, 456`).
- **Payload** : `ContextWindowPayload` (`trace/catalog.py:281-310`), qui n'a aucun champ de cache. `seen_tokens` (`:306`) est une mesure côté harnais du préfixe déjà lu dans le tour.

## Cache par appel

| Source | Champs | Où |
|---|---|---|
| Cloud | `cache_read_tokens`, `cache_write_tokens`, `cache_full_usd`, `cache_write_usd`, `cache_saved_usd`, `cache_priced`, `cache_source` | `ModelCallEndedPayload` (`catalog.py:427`, champs :448-460), calculés par `cache_savings()` (`models/cloud_base.py:325-359`) |
| Anthropic | lecture et écriture (`cache_read_input_tokens`, `cache_creation_input_tokens`) | `models/anthropic_messages.py:47-59` |
| openai_chat, openai_responses | lecture seule (`cached_tokens`) | `cloud_base.py:318-322, 362-378` |
| Local | `kv_cache_tokens`, `kv_prompt_per_second`, `evaluated_tokens` | `catalog.py:442, 470-474` |
| Préfixe cassé | `PrefixNotReusedPayload` (`common_tokens`, `again_tokens`, `cause`) ; causes : `PrefixCause` | `catalog.py:724-744`, émis par `session/app_session.py:8257, 8335` |
| Préremplissage | `ContextPrefillStarted/Ended` | `catalog.py:750-768` |

- **Piège** : les champs de cache cloud ne sont émis que si l'entrée a un `pricing` (`cloud_base.py:1044-1048`). CAP-1 doit les émettre dans tous les cas.
- **Rendu actuel** : `cacheNode()` (`app.js:2577-2610`) et `kvCacheNode()` (`:2651-2683`), dans le compteur de l'appel. Textes : `ui.yaml` `cache.*` (:642-651) et `kv.*` (:652).
- **`cache_control`** : jamais envoyé (`wavestack.toml:518-520`). Le `system` Anthropic part en une seule chaîne (`context/render.py:472-520`).

## Bilan de la séance

- **Calcul** : `record_spend()` (`cloud_base.py:432-471`), avec un dict `_spend` global au processus (:386-406). Il cumule en dollars et en secondes, sans tokens, depuis le lancement.
- **Payload** : `ConsumptionUpdatedPayload` (`catalog.py:477-503`).
- **Alimentation** : cloud (`cloud_base.py:1057`), KV local (`app_session.py:8584-8590`), compression (`:7423`).
- **Rendu** : `renderSpendPanel()` (`web/static/bar.js:154-197`), textes `ui.yaml` `common.bar.spend.summary*` (:118-121).
- **Par tour** : `TurnEndedPayload` (`catalog.py:200-213`), en coût et empreinte seulement.

## Prix du cache (`wavestack.toml`)

| Modèle | Lecture / écriture ($/Mtok) |
|---|---|
| `claude_haiku` (:557) | 0,10 / 1,25 |
| `claude_sonnet` (:586) | 0,20 / 2,50 |
| `openai_luna` (:656) | 0,01 / — |
| groq, mistral, gemini, gemma | non déclaré |

- **Écriture 1 h** : le prix d'écriture déclaré est celui de 5 min (×1,25). CAP-5 ajoute ×2 pour 1 h, à déclarer ou à dériver.
- **Définition des champs** : `config.py:165-171`.

## Scénarios

- **Modèles** : `src/wavestack/scenarios.py` (`Scenario` :19-37, `extra="forbid"` ; `Module` :40-45).
- **Contenu** : `content/scenarios.yaml`, dont l'en-tête :1-40 documente les clés. On y trouve `program` (modules de 30 à 60 min), `transverse` et `scenarios`.
- **Pas d'action scriptée** : les gestes (vider la conversation, changer le prompt système) s'écrivent dans `description_text`, et le participant les fait à la main.
- **Préfixe dynamique** :
  - le hook H3 injecte la date avant le message, hors du prompt système (`hooks.py:280-285`) ;
  - les gabarits locaux reçoivent `strftime_now` (`context/render.py:81-94`).
