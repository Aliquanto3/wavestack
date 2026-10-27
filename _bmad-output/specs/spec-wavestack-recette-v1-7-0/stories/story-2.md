---
title: 'Story 2 : Atelier LLM, coût d''un modèle gratuit'
type: 'fix'
created: '2026-10-27'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** À l'étape 6 (Génération) de l'Atelier LLM, `renderImpact(p)` (`llm.js:2030-2051`)
ne montre un coût que si `p.cost_in_usd`/`p.cost_out_usd` sont non nuls. Pour un modèle sans
`pricing` déclaré (offre gratuite, ex. `gemma` dans `wavestack.toml:546-561`), `cloud_base.py`
ne calcule ni ne transmet jamais `cost_in_usd`/`cost_out_usd` (`ended()`, gardé par
`if pricing is not None`) : le bloc coût disparaît en silence. Comme `gemma` déclare des
`impacts` (EcoLogits), seule l'empreinte s'affiche, sans jamais dire que l'appel est gratuit —
contrairement à la barre (`bar.js:230-242`), qui affiche toujours un montant (« 0 $, offre
gratuite ») grâce à `unpriced_calls`. Un modèle sans `pricing` ET sans `impacts` n'affiche
alors rien du tout à l'étape 6.

**Approach:** Porter la même classification que la barre (`unpriced_calls` / `calls`, issue de
`_add_cells` dans `cloud_base.py:538-547`) jusqu'au payload par appel, sans dupliquer le calcul
du coût : dans `ended()`, quand l'entrée est un `CloudModel`, l'appel a produit une réponse et
`pricing is None`, marquer `payload["unpriced"] = True`. Porter ce booléen dans
`ModelCallEndedPayload` et `LlmGenerationEndedPayload` (lu tel quel, comme `cost_in_usd`), puis
dans `renderImpact` : si `unpriced`, afficher « Coût estimé : 0 $, offre gratuite (aucun prix
déclaré). » à la place du bloc coût absent. Un modèle local n'est jamais `unpriced` (il garde
son empreinte en g CO₂e, affichage inchangé).

## Boundaries & Constraints

**Always:**
- `unpriced` à `False` par défaut (jamais pour un modèle local, jamais pour un appel tarifé).
- Aucune formule de prix dupliquée : `unpriced` est un simple booléen de classification
  (`pricing is None`), pas un recalcul de `cost_in_usd`.
- Montants en dollars (comme la barre et le reste de l'Atelier LLM), jamais en euros.
- Textes ajoutés déclinés en fr/en/de (`content/ui.yaml`, `content/i18n/{en,de}/ui.yaml`).

**Never:**
- Ne pas changer `cost_in_usd`/`cost_out_usd` ni la logique des appels tarifés.
- Ne pas toucher à l'affichage d'un modèle local (`CloudModel` seulement).
- Ne pas dupliquer la règle `unpriced_calls` de `bar.js`/`cloud_base.py` : lecture seule du
  même classement, porté par le payload existant.

## Code Map

- `src/wavestack/models/cloud_base.py:1269-1314` (`ended()`) — `payload["unpriced"] = True`
  quand `isinstance(entry, CloudModel)`, `produced` et `pricing is None`.
- `src/wavestack/trace/catalog.py` (`ModelCallEndedPayload`, `LlmGenerationEndedPayload`) —
  nouveau champ `unpriced: bool = False`.
- `src/wavestack/session/app_session.py:10489-10498` — `ended["unpriced"]` reporté depuis
  `model_call_ended`, comme les champs de coût et d'empreinte voisins.
- `src/wavestack/web/static/llm.js:2026-2053` (`renderImpact`) — branche `else if (p.unpriced)`.
- `content/ui.yaml`, `content/i18n/{en,de}/ui.yaml` (`main.cost.free_text`).

## Tests et E2E à réaligner

- `tests/test_llm_lab.py` : nouveau test (modèle `gemma`, sans `pricing`) vérifiant
  `cost_in_usd`/`cost_out_usd` absents mais `unpriced` vrai, sur `model_call_ended` et
  `llm_generation_ended` ; test local existant complété par `unpriced is False`.
- E2E (non lancés ici, RAM limitée) : `tools/e2e/` — chercher les scénarios de l'Atelier LLM
  qui couvrent l'étape 6 (génération, `generation-impact`) ; à lancer avec un modèle cloud
  gratuit (ou à ajouter un scénario `llm_generation_free_model_shows_no_cost_as_paid` si aucun
  scénario existant ne couvre un modèle sans `pricing`) une fois la RAM disponible.

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_llm_lab.py tests/test_cloud.py`
- `uv run python .claude/cost-kit/controle_rapide.py`

</frozen-after-approval>
