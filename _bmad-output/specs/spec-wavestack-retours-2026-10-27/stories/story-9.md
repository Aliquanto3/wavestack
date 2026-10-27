---
title: 'Story 16.9 : Atelier RAG, modèle de génération et fenêtre de contexte'
type: 'feature'
created: '2026-10-27'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-retours-2026-10-27/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-retours-2026-10-27/brownfield.md'
---

## Intent

CAP-7 : dans l'Atelier RAG, l'utilisateur choisit le modèle qui génère la réponse, sans changer celui de la séance ; il règle la fenêtre de contexte depuis l'onglet pour débloquer Contexte long et CAG ; il lit pourquoi le CAG est grisé sous un modèle cloud. Vague V2, en parallèle de 16.8.

## 1. Modèle de génération

**Où vit le choix : dans la chaîne, comme les modèles d'embedding.** Pas d'état de séance nouveau. L'étape `generation` a aujourd'hui deux options fixes, `active` et `not_run` (`rag/lab.py:130`). La séance y ajoute une option par modèle déclaré, comme elle ajoute déjà les embeddings de `[[rag_lab.embeddings]]` (`kind_options`, `rag/lab.py:1031`, via `Catalog.options`). Le choix est donc sauvegardé avec la chaîne côté navigateur (`saveChains`) et envoyé à chaque exécution. Le modèle de la séance ne bouge pas, et le non-goal de SPEC.md est tenu.

- Identifiants des options : `active` reste le défaut, avec le libellé « Modèle actif de l'atelier : {model} » (`app_session.py:11024-11031`) ; `model:<id>` pour chaque modèle cloud déclaré (`cfg` des `CloudModel`). L'option est indisponible, avec sa `reason_text`, quand la clé manque (reprendre le message existant de la barre des modèles). Pour les modèles locaux, voir Q1.
- Sélecteur : aucun code nouveau. `optionSelect` (`rag.js:241-262`) dessine déjà toute étape à plusieurs options, avec la raison d'une option indisponible (`rag.js:252`, `:278-282`).
- Validation de contenu : `rag_lab.yaml` exige les mêmes options statiques que `OPTIONS` (`lab.py:848`). Les options `model:*` sont dynamiques, et leurs libellés viennent de la séance, comme pour les embeddings.
- Génération : `_rag_lab_generate` (`app_session.py:12547`) lit aujourd'hui `self._engine` / `self._cloud`. Pour `model:<id>`, résoudre le `CloudModel` et appeler `_lab_cloud_call(..., cloud=<choisi>, ...)` (`:10899`, qui prend déjà le modèle en argument), avec `chat_fields(<choisi>, …)`. La garde `engine is None` (`:12562`) ne vaut plus que pour `active`. Coût, empreinte et événements `model_*` passent par le même chemin, donc le Journal de 16.1 les reçoit avec le bon modèle.
- Affichage : le sous-titre de la tuile Génération (`rag.js:787-790`) nomme le modèle choisi ; l'événement de fin d'étape porte le libellé du modèle effectif.
- Interaction avec le CAG : le CAG exige un moteur local. Une chaîne `cached_corpus` + `model:<cloud>` est refusée à la validation de chaîne, avec la raison `cag_local_only` (mécanisme `store.refusals`, `rag.js:544-573`).

## 2. Fenêtre de contexte depuis l'onglet RAG

**Extraction sans duplication** : nouveau module `web/static/window-picker.js` (ES module, comme `panes.js`), qui exporte `createWindowPicker({ mount, getSessionState, onStatus })` et `handleWindowState(payload)`.
- Y déplacer `app.js:2946-3142` : `bindWindowPicker`, `placeWindowPanel`, `open`/`closeWindowPanel`, `windowApplyReason`, `renderWindowPicker`, `windowChoiceNode`, `applyClaudeCache`, `applyWindow`, et l'état `windowState`, `windowPick`, `windowError`, `windowApplying`, `claudeCache*`. Les dépendances à `store` deviennent des paramètres : `store.sessionState` devient `getSessionState()` et `store.topStatus` devient `onStatus(text)`.
- Balisage : le panneau `index.html:290-314` est construit par le module dans `mount` (Q2), et les deux pages n'ont qu'un `<div id="window-picker">`.
- `app.js` importe le module et appelle `handleWindowState` dans `case "context_window_state"` (:360) ; l'appel de rendu de :1167 passe par le module. `rag.js` importe le même module, monte le bouton dans l'en-tête de l'atelier, près du bouton Exécuter, et le nourrit dans son `case "context_window_state"` (:1422), qui recharge déjà le catalogue à chaque changement. Ainsi Contexte long devient disponible sans recharger la page.
- État initial de la page RAG : lire `context_window_state` de l'état rechargé (`web/app.py:1132-1149`) au chargement.
- CSS : déplacer les règles `.window-*` de `app.css` vers `pages.css`, chargé par les deux pages.
- `POST /api/intentions/context_window` (`set_context_window`, `app_session.py:2769`) et la règle « entre deux tours » restent inchangés. Côté RAG, l'état occupé est `store.session.state`.

## 3. Raison du CAG grisé

La raison existe déjà : `cag_local_only` (`messages.yaml:621`, posée en `app_session.py:11127-11131`), affichée en `<p class="rag-chain-unavailable">` sous le sélecteur (`rag.js:280`) et en infobulle de l'option. Commencer par reproduire le retour dans l'app (modèle cloud, onglet Composer et vues de familles/préréglages) pour trouver l'écran où la raison manque, puis l'y afficher **en texte visible**, jamais en infobulle seule. Le texte : « Indisponible avec un modèle cloud : le CAG garde le corpus dans la mémoire (cache KV) d'un modèle local, et l'atelier ne pilote pas le cache d'un fournisseur. Choisissez un modèle local. » (fr, en, de).

## Tests et E2E

- Créer, dans `tests/test_rag_lab_generation.py` : options `model:<id>` présentes pour chaque cloud déclaré, indisponibles sans clé avec la raison exacte ; génération `model:<id>` sous séance locale qui appelle le faux serveur OpenAI (`tools/e2e/fake_openai.py`) avec cet id, sans changer `active_model()` ; `active` inchangé ; refus `cached_corpus` + cloud avec le texte exact.
- `tests/test_rag_lab_context.py` : après `set_context_window(16384)`, `full_corpus` devient disponible dans le catalogue.
- Réaligner : `tests/test_ui_texts.py` (`PAGES`, si le module doit y figurer), `tests/test_context_window_setting.py`, `tests/test_claude_cache.py` s'ils lisent le DOM d'index, `tests/test_web_app.py` si des règles CSS déménagent.
- E2E : réaligner `s_context_window` (:11040) ; étendre `s_rag_lab_context` (:14799) : choisir un modèle cloud factice, générer, vérifier le nom dans la tuile et le modèle de la barre inchangé ; régler 16384 depuis l'onglet RAG et vérifier Contexte long disponible ; vérifier le texte du CAG grisé. Aussi `s_rag_lab_no_index` (:18576).

## Zones de app.js (parallèle avec 16.8)

16.9 : seulement le bloc :2946-3142 (retiré), l'import en tête, `case "context_window_state"` (:360) et l'appel de :1167. 16.8 : :112-138, :374, :1201-1446 (après 16.5), :1764-2160, :3802-3844, :5739-6242 (badge), :7041, :7979, :8100. Aucun bloc commun ; seuls les imports en tête et le `switch` des événements peuvent entrer en conflit textuel, à résoudre au rebase. app.css : 16.9 déplace `.window-*`, 16.8 retire `.force-*` / `.armed-*`, sur des sections distinctes.

## Questions pour Anaël

1. **Modèles locaux dans le sélecteur** : un second GGUF chargé en même temps coûte de la RAM (16 Go). Recommandation : ne proposer que le modèle actif plus les modèles cloud déclarés ; un autre modèle local reste accessible en changeant le modèle de la séance.
2. **Balisage du panneau** : le construire en JS dans le module (une seule source) ou le garder en HTML dans index.html et le copier dans rag.html ? Recommandation : JS dans le module ; la copie HTML contredit « sans dupliquer ».
3. **Cache de prompt de Claude** dans le panneau côté RAG : le montrer aussi ? Recommandation : oui, c'est le même composant, et il ne s'affiche déjà que pour Claude.
4. **Fenêtre pour un modèle de génération cloud choisi dans le RAG** : la disponibilité de Contexte long suit la fenêtre de la séance, pas celle du modèle choisi. Recommandation : garder cette règle et la dire dans la note de l'étape ; l'ajuster au modèle choisi passe en report.

## Décisions d'Anaël (2026-10-27)

- Q1 : le sélecteur propose aussi les autres modèles locaux, comme le sélecteur de la séance. Choisir un modèle local change le modèle chargé en RAM pour toute l'application (même effet et même chemin que le changement de modèle de séance) ; choisir un modèle cloud ne change pas le modèle de la séance. Cela amende le non-goal de SPEC.md « Changer le modèle de la séance depuis l'onglet RAG » pour les seuls modèles locaux. Réutiliser le chemin existant du changement de modèle, sans le dupliquer, et le dire dans l'interface (« change le modèle de toute l'application »).
- Q2 à Q4 : recommandations retenues.
