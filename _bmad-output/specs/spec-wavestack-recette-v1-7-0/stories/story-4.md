---
title: 'Story 17.4 : Atelier RAG, Contexte long après Appliquer et renvoi au bon réglage'
type: 'fix'
created: '2026-10-27'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/src/wavestack/web/static/rag.js'
  - '{project-root}/src/wavestack/web/static/window-picker.js'
  - '{project-root}/content/messages.yaml'
  - '{project-root}/_bmad-output/specs/spec-wavestack-retours-2026-10-27/stories/story-9.md'
---

## Intent

CT-04 : deux défauts de recette sur le réglage de la fenêtre de contexte depuis l'onglet RAG
(ajouté par la story 16.9).

**(a) Pas de rafraîchissement sans recharger.** La page RAG ne recalcule son catalogue (donc
l'état grisé de « Contexte long » et du CAG) qu'au changement de clé `configured/window/
model_label` de l'événement `context_window_state` (`rag.js:1475-1481`,
`store.windowSeen !== undefined && store.windowSeen !== key`). Cette clé de référence
(`store.windowSeen`) n'est posée qu'au premier événement reçu en direct par le flux `/api/
stream` : au chargement de la page, l'état initial est lu par un `fetch("/api/state")` à part
(`rag.js:2429-2432`, `handleWindowState(state.context_window_state)`) qui ne pose jamais
`store.windowSeen`. Si l'utilisateur clique « Appliquer » peu après l'ouverture de l'onglet, le
tout premier `context_window_state` reçu en direct est celui de son propre changement : la
garde `!== undefined` est fausse, le catalogue n'est pas relu, et seul un rechargement de page
(qui repasse par `/api/rag_lab`, toujours recalculé à la demande) montre le nouvel état. Cause
confirmée en lisant le code (pas de modèle serveur-session en cause : `test_rag_lab_no_index.py`
montre déjà que `set_context_window` puis une relecture du catalogue donnent l'état à jour côté
session ; le trou est uniquement la valeur de référence posée côté navigateur).

**(b) Raison incomplète.** Les raisons de « Contexte long » et du CAG grisés par une fenêtre
trop petite (`session.rag_lab.window_needed`, via `session.rag_lab.window_set`,
`messages.yaml:587`) ne nomment que « le sélecteur « Fenêtre » de la barre de la page
Conversation », alors que la story 16.9 a ajouté ce même sélecteur (même composant, même état)
dans l'onglet RAG — déjà noté en fin de revue de 16.9 et reporté ici. Nommer les deux endroits.

## Given/When/Then

- **(a)** Given l'onglet RAG ouvert avec un modèle dont la fenêtre effective est sous 16 384
  tokens (« Contexte long » et le CAG grisés), When l'utilisateur règle la fenêtre à 16 384
  (ou plus) depuis le sélecteur « Fenêtre » de l'onglet et clique « Appliquer », Then les deux
  boutons (et leur raison affichée) se mettent à jour sans recharger la page, dès le premier
  réglage de la séance.
- **(b)** Given « Contexte long » ou le CAG grisés faute de fenêtre, When la raison s'affiche
  (sous le bouton, en infobulle, au clavier), Then elle nomme le sélecteur « Fenêtre » de la
  page Conversation et celui de l'onglet RAG.

## Tâches

1. `src/wavestack/web/static/rag.js` : poser `store.windowSeen` dès la lecture de l'état
   initial (`fetch("/api/state")`, ~ligne 2429-2432), avec la même clé que le `case
   "context_window_state"` du flux (`${configured}/${window}/${model_label ?? ""}`), pour que
   le premier événement reçu en direct soit comparé à l'état réellement affiché, pas à
   `undefined`.
2. `content/messages.yaml` (`session.rag_lab.window_set`, fr) + `content/i18n/en/messages.yaml`
   et `content/i18n/de/messages.yaml` (même clé) : ajouter la mention de l'onglet RAG, en
   gardant les sous-textes déjà vérifiés par les tests (fr : « sélecteur « Fenêtre » » et
   « page Conversation » ; en : « “Window” selector » ; de : « Auswahl „Fenster“ »).
3. `tests/test_rag_lab_no_index.py` : compléter l'assertion de
   `test_a_small_window_greys_both_and_the_api_refuses_them` pour vérifier que la raison nomme
   aussi l'atelier RAG (fr).

## Tests

- `uv run pytest -q --tb=short tests/test_rag_lab_no_index.py tests/test_i18n.py -k rag_lab or messages`
- `uv run python .claude/cost-kit/controle_rapide.py`

## E2E à rejouer (non lancé par cette story, poste partagé du run)

`uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag rag_rerank rag_lab_no_index`

- `s_rag_lab_no_index` couvre déjà, sans recharger, le passage d'un grisé à un autre grisé
  (fenêtre bornée par `llama-server`, raison mise à jour) ; il faudrait y ajouter une vérification
  du passage grisé → disponible (le scénario (3) applique 16 384 depuis la page Conversation,
  pas depuis l'onglet RAG, puis revient sur `/rag` — ce qui recharge la page et ne prouve pas
  (a) pour cette transition). Proposé : dans ce même scénario, remplacer l'appel à
  `_apply_window(r, 16384)` du bloc (3) par un réglage fait depuis le panneau de l'onglet RAG
  lui-même (page déjà sur `/rag`, `page_idle=True`), et vérifier `long_context.available`
  (DOM) sans `r.goto_app()` intermédiaire.
- `s_rag_lab_no_index` vérifie aussi, textuellement, la raison du grisé : réaligner la chaîne
  attendue (« sélecteur « Fenêtre » ») avec le nouveau texte (b), déjà fait ici par substring.

## Choix faits à la place d'Anaël

- (a) corrigé uniquement en posant la référence manquante (`store.windowSeen`), sans changer le
  mécanisme de rafraîchissement existant (clé, garde, `reloadCatalog`) : il est correct, seule
  son amorçage manquait.
- (b) le texte nomme les deux endroits plutôt que de remplacer la mention de la page
  Conversation par celle de l'onglet RAG : la page Conversation garde son propre sélecteur, et
  l'utilisateur peut lire cette raison depuis l'un ou l'autre.
- L'E2E demandé par la story n'est pas réécrit ici (RAM limitée, pas de lancement local) : son
  adaptation exacte (bloc (3) de `s_rag_lab_no_index`) est proposée ci-dessus pour
  l'orchestrateur ou une story suivante.
