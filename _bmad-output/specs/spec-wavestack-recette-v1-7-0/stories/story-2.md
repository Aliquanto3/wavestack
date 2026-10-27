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

## Revue

### Passe 1 (2026-10-27, SHA revu 98d68532)

Rebasée sur origin/main (1b3e0c66). Branchement vérifié : `run_call` → `model_call_ended.unpriced`
→ `app_session` → `llm_generation_ended.unpriced` → `renderImpact`. Même règle que la barre
(`_add_cells` : sans prix et hors local).

- **Important**, medium, second avis (1) affiné, corrigé : le faux cloud A de l'E2E (`fake`,
  `tools/e2e/stack.py`, sans `pricing`) EST un modèle sans prix ; `_generation_extras`
  (`llm_screen`) attendait `#generation-impact` masqué et sans « Coût » : il aurait échoué
  avec le correctif. Le contrôle couvre désormais le cas gratuit (`unpriced` → visible,
  « Coût » et « offre gratuite »), sans nouveau modèle factice.
- **Nit**, low, reviewer, corrigé : `en` affichait « 0 $ » alors que `common.format.usd` en
  anglais donne « $0 » (barre) : texte aligné « Estimated cost: $0, free offer… ».
- **Nit**, low, second avis (2), reporté : l'Atelier RAG (`rag/lab.py`) a sa propre règle de
  coût et ne dit pas « offre gratuite » pour un modèle sans prix ; hors périmètre, à traiter
  dans une story de l'Atelier RAG.
- **Pre-existing**, low, reviewer, noté : `main.consumption.free_sentence` dit « 0 € » alors
  que le montant de la barre est en dollars (`shortUsd(0)` → « 0 $ ») ; non corrigé ici.
- Second avis 3 à 8 confirmés : classification identique à la barre, schémas
  (`unpriced: bool = False`) rétrocompatibles, clé présente en fr/en/de, pas de brouillon.
  Lisibilité : « Coût estimé : 0 $, offre gratuite (aucun prix déclaré). » cohérent avec
  « 0 $ » et « Offre gratuite » de la barre.
- Complexité : 0 constat (un champ par appel, aucun parcours ajouté).

E2E à jouer : `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only llm_screen`.
