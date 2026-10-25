---
title: 'WaveStack V1.4 (4) : compaction et fenêtre glissante'
type: 'feature'
created: '2026-10-25'
status: 'review'
baseline_revision: 'ff8c405'
spec_checkpoint: true
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-etat-de-l-art-harnais/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-etat-de-l-art-harnais/brownfield.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-etat-de-l-art-harnais/maquettes.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/stories/3-vider-le-cache.md'
---

<intent-contract>

## Intent

**Problem:** CAP-5. La compaction, standard dans 7 harnais sur 11, n'est que nommée : au débordement,
la carte `context_overflow` liste quatre stratégies en texte et le tour est refusé.

**Approach:** Deux stratégies cliquables sur la mémoire courte du chat principal, au débordement
(carte de débordement) ou sur demande (bouton « Compacter ») : la **compaction** résume les anciens
échanges par un appel ordinaire au modèle actif, la **fenêtre glissante** retire les plus anciens sans
appel. Au débordement, le message refusé repart seul, comme un nouveau tour (décision d'Anaël). L'appel
suivant réécrit le cache, avec la cause `compaction` ou `sliding_window`.

**Always:**
- Pas de nouvelle dépendance ; seulement des ajouts dans les fichiers carrefour (`ui.yaml`,
  `messages.yaml`, `scenarios.yaml`, `app.py`, `app.js`, `run_e2e.py`, `trace/catalog.py`).
- Textes fr, en et de. Les chiffres affichés (échanges résumés ou retirés, durée estimée) sont calculés.
- Le résumé est un appel au modèle actif par le chemin ordinaire : événements `model_call_*`, coût et
  temps comptés (`record_spend`), plafond `[finops] max_session_usd`, annulation par « Arrêter ».
- Faux moteur en test, aucun modèle réel dans la suite par défaut ; un E2E par élément visuel.

**Never:**
- Ne touche ni le sous-agent, ni les ateliers (LLM, MCP, RAG), ni la mémoire globale : leur carte de
  débordement reste celle d'aujourd'hui (`choices` vide).
- Ne retire ni `ContextOverflowPayload.strategies_text` ni les deux stratégies non cliquables (retrait
  des anciens résultats d'outils, lazy loading), qui restent du texte.
- Pas de rejeu via `_last` pour le renvoi : il rétablirait l'historique d'avant (piège de brownfield.md).
- Ne refait pas les totaux du programme (durée totale, nombre de modules ou de scénarios cités dans
  `docs/guide.md` et les tests de décompte) : la story 13.6 ajoute en parallèle un module 8 « Cache »,
  le second à fusionner refait ces totaux.

## Critères d'acceptation

1. Fenêtre de 4 096 tokens, chat principal, brique Mémoire courte allumée, au moins un échange dans la
   branche active : un débordement affiche, dans l'Orchestration (`overflowCard`) et sous la note de la
   Vue humain, « Continuer avec : » et deux boutons, « Compacter » et « Fenêtre glissante », chacun avec
   sa ligne calculée (maquette 2), puis « Autres stratégies (non montrées ici) : » et les deux textes
   restants.
2. Sans échange (premier tour, message seul trop long), Mémoire courte éteinte, débordement du
   sous-agent ou d'un atelier : la carte est celle d'aujourd'hui (quatre stratégies en texte, aucun bouton).
3. Un clic désactive les deux boutons des deux vues, applique la stratégie, puis renvoie seul le message
   refusé comme un nouveau tour (`turn_started.replay_of` nul) sur l'historique réécrit ; « Rejouer le
   dernier prompt » rejoue ensuite ce nouveau tour, sur l'historique réécrit.
4. Compaction : un tour du harnais (`turn_started.kind = "compaction"`) fait un seul appel au modèle
   actif, sans outils ni raisonnement, sortie bornée par `[context] compaction_max_tokens` ; l'Orchestration
   montre l'étape « Résumé de compaction » (modèle, tokens, durée, coût) ; le coût entre dans
   `turn_ended` et dans le bilan (V1.3). L'historique devient `[résumé] + échanges gardés`.
5. Fenêtre glissante : aucun appel au modèle, aucun tour ; l'historique perd ses plus anciens échanges.
6. La Vue humain et le Contexte LLM remplacent les échanges retirés par un marqueur : pour la compaction,
   la bulle « Résumé (compaction) » et son texte ; pour la fenêtre glissante, « 3 échanges retirés
   (fenêtre glissante) ». Dans le Contexte LLM et la jauge, le résumé a son propre libellé.
7. Mode local : le premier appel du tour suivant émet `prefix_not_reused` avec la cause `compaction` ou
   `sliding_window` ; la jauge du cache (V1.3 story 2) affiche « écrit » et la cause « compaction » ou
   « fenêtre glissante ».
8. Un bouton « Compacter ▾ » à gauche de « Vider la conversation » ouvre un menu de deux entrées
   (maquette 3), qui appliquent la stratégie sans renvoyer de message. Le bouton est désactivé, raison en
   infobulle et en nom accessible, pendant un tour, sans conversation, Mémoire courte éteinte ; une entrée
   est désactivée, avec sa raison, quand elle n'a rien à retirer.
9. Annulation, erreur du fournisseur ou plafond FinOps pendant le résumé : le tour de compaction finit
   avec son statut, l'historique est inchangé, aucun message n'est renvoyé.
10. Scénario `compaction` dans le module 7 « Contexte long et carte », entre `compression` et
    `harness_map` : sa conversation déborde au prompt prévu, la consigne fait choisir la compaction puis,
    après relance, la fenêtre glissante.
11. fr, en et de ; `test_i18n.py` vert ; chaque valeur de `PrefixCause` a son texte (test de la V1.3).

## Décisions de la spec

### Contrats

- **`PrefixCause`** (`trace/catalog.py:805`) : ajouter en fin de liste `"compaction"` puis
  `"sliding_window"`, chacune avec son commentaire `# V1.4 story 4: …`.
- **`CompactionChoice`** (nouveau, `trace/catalog.py`, près de `ContextOverflowPayload`) :
  `strategy: Literal["compaction", "sliding_window"]`, `available: bool`, `count: int` (échanges
  résumés ou retirés), `detail_text: str` (ligne de la maquette), `reason_text: str | None = None`
  (pourquoi indisponible).
- **`ContextOverflowPayload`** (`catalog.py:366`), en ajouts : `choices: list[CompactionChoice] = []`
  (vide hors chat principal, sans échange ou Mémoire courte éteinte) et
  `other_strategies_text: list[str] = []` (les textes de `old_tool_results` et `lazy_loading`, que le
  front affiche sous « Autres stratégies » quand `choices` n'est pas vide ; sinon `strategies_text`).
- **`CompactionStatePayload`** (nouvel événement `compaction_state`, ajouté au registre des
  événements) : `choices: list[CompactionChoice]`, valeurs hors débordement (garder
  `compaction_keep` échanges). Émis par `_refresh_preview()` (après un tour, un vidage, un scénario, un
  changement de brique), lu par le bouton « Compacter ▾ ».
- **`HistoryCompactedPayload`** (nouvel événement `history_compacted`) : `strategy`,
  `removed_turn_ids: list[str]` (échanges sortis de l'historique, résumés ou retirés),
  `summary_text: str | None` (compaction), `before_tokens: int`, `after_tokens: int` (aperçu du
  contexte avant et après), `message_text: str` (« 3 échanges retirés (fenêtre glissante) »,
  « 5 échanges résumés (compaction) »). Pour la compaction, émis dans le tour de compaction (son
  `turn_id`) ; pour la fenêtre glissante, hors tour (`turn_id` nul, `actor: "harness"`).
- **`TurnStartedPayload`** (`catalog.py:193`), en ajout : `kind: Literal["message", "compaction"] =
  "message"`. Un tour de compaction a pour `message` la demande de résumé (`session.compaction.request`)
  et `actor: "harness"`.
- **Intention** `POST /api/intentions/compact` (`web/app.py`, à côté de `clear_conversation`), corps
  `CompactIntention {strategy: Literal["compaction", "sliding_window"], resend_turn_id: str | None =
  None}` ; 409 avec la raison sur `SendRefused`, comme `clear_conversation` ; réponse `{"started": true}`.
- **Configuration** (`config.py`, `wavestack.toml` `[context]`, commentés en français) :
  `compaction_max_tokens = 256` (sortie du résumé, bornée 64 à 512) et `compaction_keep = 2` (échanges
  gardés hors débordement, borné 1 à 5).
- **`Exchange`** (`app_session.py:438`) : champ ajouté en dernier, `summary: bool = False`.
- **Composant** `short_memory.compaction` (`bricks/registry.py`, sous `short_memory`, `kind="memory"`,
  `hosting="local_process"`, `edges_to=["core.harness"]`) : composant de l'appel de résumé et des parts du
  résumé dans le contexte.

### Session (`session/app_session.py`)

- `_emit_overflow(payload, raw_used, main: bool = False)` : le seul appel du chat principal
  (`_turn`, `:7299`) passe `main=True`. Avec `main`, Mémoire courte effective et historique non vide,
  calcule `choices` (règles ci-dessous) et `other_strategies_text` ; retient
  `self._overflowed = turn_id` (nouveau, `None` à l'init). `_overflowed` repasse à `None` au début de
  tout tour, à `clear_conversation`, au lancement d'un scénario et à la réinitialisation.
- **Règles de calcul** (fonction pure `_compaction_plan(history, fits) -> dict[strategy, CompactionChoice]`,
  testable seule) :
  - *au débordement* : `k` = le plus grand nombre d'échanges récents gardés tel que le contexte de l'appel
    refusé (mêmes `state`, message et `steps`) tienne dans `usable`, rendu par `_render` sur
    `replace(state, history=history[-k:])` (et, pour la compaction, avec une place de
    `compaction_max_tokens` pour le résumé). Fenêtre glissante : retire `n - k` échanges, garde au moins le
    dernier (`k ≥ 1`) ; indisponible si `n == 1` (« un seul échange : rien à retirer »). Compaction : résume
    les `n - k` plus anciens (`k ≥ 0`, au moins un échange résumé). Si même `k` minimal ne tient pas, le
    choix reste disponible avec `k` minimal (le renvoi peut déborder à nouveau : la carte revient).
  - *hors débordement* : les deux gardent `compaction_keep` échanges ; indisponibles si
    `n ≤ compaction_keep` (« pas assez d'échanges »).
  - Le résumé déjà présent compte comme un échange : une nouvelle compaction le résume avec les autres, la
    fenêtre glissante peut le retirer.
- `compact(strategy, resend_turn_id)` (intention classe b, motif de `clear_conversation`) : sous
  `_memory_lock` et `_lock`, refus hors `idle` (`_refusal_reason()`), sans engin, Mémoire courte éteinte
  (`session.refused.compact_short_memory`), historique vide (`compact_empty`), choix indisponible
  (`reason_text`), `resend_turn_id` différent de `_overflowed` (`compact_stale`, carte périmée).
  Le message renvoyé est `self._last[1]` (le tour refusé est le dernier lancé, `_last[0] ==
  resend_turn_id`), comme le rejeu.
  - *Fenêtre glissante* : synchrone ; `_history[:] = history[n-k:]`, `_cache_cause = "sliding_window"`,
    `_last = None` si aucun renvoi, `_overflowed = None`, `_loaded_docs`/`_loaded_skills` recalculés
    (ci-dessous) ; puis `history_compacted`, `_emit_architecture()`, `_refresh_preview()` ; puis, si renvoi,
    `self._start(message)`.
  - *Compaction* : `_turns += 1`, état `turn` (comme `_start`, `CancelToken`, sans toucher `_last`), puis
    `_run_compaction(turn_id, strategy_plan, message | None, cancel)` sur le worker.
- `_run_compaction` : portée `turn_id`, `context_id="main"`, `trigger="user"` ; `turn_started`
  (`kind="compaction"`) ; une étape `component="short_memory.compaction"`, libellé de phase
  `session.compaction.phase` ; contexte du résumé construit comme `_rag_lab_generate` (`:10637`) :
  message système = `content/prompts/compaction.md` (langue de la session par `config.content_file`), un
  message `user` = transcription des échanges à résumer (`Utilisateur : …` / `Assistant : …`, réponses
  finales seulement, résultats d'outils remplacés par `[outil <nom> : <n> caractères]`, résumé précédent
  en tête) ; si la transcription ne tient pas, les plus anciens tombent de la transcription (pas de
  l'historique). Appel par `_call_model` (local) ou le chemin chat (`_call_model_chat`, `run_call` avec
  `max_session_usd`) : `tools=()`, `reasons=False`, `reserve=compaction_max_tokens`, sans hooks
  `before_model_call` ni garde-fous (comme la génération de l'Atelier RAG). Statut `completed` : sous
  `_lock`, `_history[:] = [Exchange(turn_id, request, summary, "", summary=True)] + kept`,
  `_cache_cause = "compaction"`, `_last = None` si aucun renvoi, docs et skills recalculés ;
  `history_compacted` ; `turn_ended` avec `_turn_cost()`/`_turn_impact()` ; aucun `Exchange` ordinaire
  ajouté. Puis, si renvoi, `_start(message)` lancé depuis le worker sans repasser par `idle`
  (paramètre interne `chained=True` qui accepte l'état `turn` du tour de compaction) ; sinon `idle`,
  `_emit_architecture()`, `_refresh_preview()`. Autre statut : historique inchangé, pas de renvoi, `idle`.
- `_last` : le renvoi passe par `_start(message)`, qui enregistre l'historique réécrit ; sans renvoi,
  `_last = None` (« Rejouer » désactivé, comme après « Vider la conversation »), sinon le rejeu
  rétablirait l'historique d'avant.
- **Rendu du résumé** (`_messages`, `:4525`) : un `Exchange` `summary` est rendu comme les autres
  (message `user` = la demande, message `assistant` = le résumé) avec `component="short_memory.compaction"`
  ; son segment porte `label_text` = `main.ctx.compaction_summary` (champ `label: str | None = None` ajouté
  en dernier à `Part`, recopié dans `Segment.label_text` au rendu ; à confirmer à l'implémentation).
- **Docs et skills chargés** : après la stratégie, `_loaded_docs` et `_loaded_skills` ne gardent que
  ceux dont le résultat de `load_tool_doc` / `load_skill` est encore dans les `steps` d'un échange gardé ;
  ceux des échanges résumés ou retirés sont déchargés (D16-b : en local, la documentation n'est lue que
  dans l'historique).
- **Cache** : `_cache_cause` posée sans `or` (dernier changement structurel, comme `reset`) ;
  `_check_reuse` (`:8424`) la consomme au premier appel du tour suivant, sans autre changement.
  `_main_cache` n'est pas remis à `None` (sinon aucun `prefix_not_reused`). Mode chat : pas de
  `prefix_not_reused` (`_check_reuse` ne vaut que pour `RenderedContext`) : voir Points ouverts.
- **Durée estimée** (ligne « ≈ 20 s en local ») : `(tokens de la transcription / débit de lecture mesuré)
  + (compaction_max_tokens / débit de génération mesuré)`, débits de `_emit_window_state` ; omise (texte
  sans durée) tant qu'aucun débit n'est mesuré et en cloud.

### Front (`web/static/app.js`, `index.html`, `app.css`)

- `overflowCard(overflow, turn)` : si `overflow.choices` n'est pas vide, « Continuer avec : », un bouton
  par choix (`pane-text-action`, `data-strategy`, désactivé si `!available`, raison en `title` et
  `aria-describedby`), sa `detail_text`, puis « Autres stratégies (non montrées ici) : » et
  `other_strategies_text` ; sinon le rendu d'aujourd'hui. La note de débordement de la Vue humain
  (`turnNote`, `:3328`) reçoit les mêmes deux boutons. Clic : `postIntention("/api/intentions/compact",
  {strategy, resend_turn_id: turn.id})`, tous les boutons de ce tour désactivés (`store.compactedTurns`) ;
  un 409 affiche sa raison sous les boutons et les réactive.
- `#compact-conversation` (`index.html:174`, avant `#clear-conversation`) : bouton « Compacter ▾ » et
  menu de deux entrées, sur le motif des menus déroulants déjà en place (`#display-menu-toggle`, `aria-haspopup`, `aria-expanded`, `aria-controls`) ; état tiré de
  `compaction_state` et de `session_state` ; Échap ferme le menu, focus rendu au bouton.
- `turn_started.kind === "compaction"` : pas de bulle utilisateur ; la bulle du tour est « 📝 Résumé
  (compaction) » puis `summary_text` à `history_compacted`. `history_compacted` : la Vue humain et le
  Contexte LLM masquent les tours de `removed_turn_ids` (liste `store.compactedOut`, comme `chatFrom`
  pour le vidage) ; la fenêtre glissante insère son marqueur `message_text` à la place du premier tour
  retiré. L'Orchestration garde tous les tours (trace de ce qui s'est passé) et affiche la ligne
  « Résumé de compaction » dans le tour de compaction.
- Jauge du cache : `PREFIX_CAUSES` lit les nouvelles clés de `main.orch.prefix_causes`, sans code.

### Textes (fr, en, de)

- `content/ui.yaml` (+ miroirs) :
  - `main.chat.compact` « Compacter » ; `main.chat.compact_menu.compaction` « Compaction : résumer les
    anciens échanges (un appel au modèle) » ; `main.chat.compact_menu.sliding_window` « Fenêtre glissante :
    ne garder que les {keep} derniers échanges » ; `main.chat.compact_disabled.{turn,empty,short_memory}` ;
  - `main.orch.overflow.continue` « Continuer avec : » ; `main.orch.overflow.others` « Autres stratégies
    (non montrées ici) : » ; `main.orch.overflow.buttons.{compaction,sliding_window}` « Compacter »,
    « Fenêtre glissante » ;
  - `main.orch.rows.compaction` « Résumé de compaction » ; `main.chat.compaction_title` « Résumé
    (compaction) » ; `main.ctx.compaction_summary` « Résumé (compaction) » ;
  - `main.orch.prefix_causes.compaction` « compaction », `.sliding_window` « fenêtre glissante ».
- `content/messages.yaml` (+ miroirs) :
  - `session.overflow.choices.compaction` « résumer les {count} anciens échanges en quelques lignes (un
    appel au modèle{duration}) » ; `.duration` « , ≈ {seconds} s en local » ;
    `.sliding_window` « ne garder que les échanges récents (aucun appel ; les {count} plus anciens sont
    retirés) » ; `.unavailable.{single,too_few}` ; formes `{one, other}` pour `{count}`, comme
    `declared` ;
  - `session.compaction.request` « Résume notre conversation jusqu'ici. » ; `.phase` « Résumé de
    compaction… » ; `.summarized` et `.removed` (formes `{one, other}`) ;
  - `session.prefix.causes.compaction` « Les anciens échanges ont été résumés (compaction) : l'historique
    a changé, le moteur relit le contexte à partir de l'historique. » ; `.sliding_window` « Les échanges les
    plus anciens ont été retirés (fenêtre glissante) : … » ;
  - `session.refused.{compact_empty,compact_short_memory,compact_stale}`.
- `content/prompts/compaction.md` + `content/i18n/{en,de}/prompts/compaction.md` : consigne du résumé
  (faits, décisions, fichiers et chiffres cités ; 120 mots au plus ; langue de la conversation).

### Scénario et programme

- `scenarios.py` `Scenario`, en ajout : `overflow_prompt: int | None = None` (numéro, à partir de 1, du
  prompt dont le tour déborde à cause de l'historique : exception AD-9 voulue, comme `expects_overflow`
  qui vaut pour le premier appel et ne laisse aucun échange à compacter). Validateur : `1 <
  overflow_prompt ≤ len(prompts)`.
- `content/scenarios.yaml` : module 7 `scenarios: [compression, compaction, harness_map]`,
  `duration_min: 60`. Scénario `compaction` (titre « Compaction et fenêtre glissante ») : briques et
  prompts calibrés (Points ouverts) ; consigne : envoyer les prompts, au débordement cliquer
  « Compacter », suivre l'étape « Résumé de compaction » dans l'Orchestration, la bulle du résumé, la
  jauge du cache (« écrit », cause « compaction ») ; relancer le scénario, refaire déborder et choisir
  « Fenêtre glissante » : aucun appel, « N échanges retirés », cause « fenêtre glissante » ; dire que le
  bouton « Compacter ▾ » fait de même hors débordement. Miroirs en et de.
- `harness_map` : sa consigne dit « comme au scénario précédent » ; à relire (le précédent devient
  `compaction`).
- `tests/test_program.py` : `test_every_scenario_fits…` traite `overflow_prompt` : les prompts avant lui
  tiennent ; lui déborde avec son historique simulé ; après lui, l'historique simulé repart de
  `compaction_max_tokens + EXCHANGE_TEMPLATE` et les prompts suivants tiennent. La ligne
  `assert not scenario.expects_overflow` reste.

## Plan de tests

- `tests/test_compaction.py` (nouveau, `booted_session(FakeEngine())`, faux fournisseur pour le cloud) :
  - `_compaction_plan` : `k` au débordement, `k ≥ 1` pour la fenêtre glissante, `n == 1`, hors débordement
    avec `compaction_keep`, résumé compté comme un échange ;
  - débordement avec historique : `choices` et `other_strategies_text` ; sans historique, Mémoire courte
    éteinte, sous-agent (`test_subagent.py`), atelier MCP : `choices == []` ;
  - fenêtre glissante avec renvoi : historique réduit, aucun `model_call_started` avant le tour renvoyé,
    `turn_started` du message sans `replay_of`, `_last[2]` = historique réduit, `prefix_not_reused.cause
    == "sliding_window"` ; « Rejouer » ensuite garde l'historique réduit ;
  - compaction avec renvoi : tour `kind="compaction"`, un appel `component="short_memory.compaction"`,
    `max_tokens == compaction_max_tokens`, sans outils ; `history_compacted.removed_turn_ids` ;
    historique `[summary=True] + gardés` ; contexte rendu suivant contenant le résumé avec son composant et
    `label_text` ; `prefix_not_reused.cause == "compaction"` ; coût du résumé dans `turn_ended` (cloud) ;
  - annulation, erreur du fournisseur, plafond FinOps pendant le résumé : historique inchangé, pas de
    renvoi, état `idle` ;
  - refus : hors `idle`, historique vide, Mémoire courte éteinte, `resend_turn_id` périmé (après un autre
    tour, un vidage, un scénario), choix indisponible ;
  - docs et skills chargés dans un échange retiré : déchargés ; dans un échange gardé : gardés ;
  - `compaction_state` émis après un tour et après un vidage, valeurs hors débordement.
- `tests/test_turn.py:97` et les tests qui lisent `context_overflow` : verts sans changement
  (`strategies_text` intact).
- `tests/test_scenarios.py` : nombre de scénarios + 1 (`compaction`) ; ne pas refaire les totaux si 13.6
  est fusionnée avant (le second à fusionner les refait).
- `tests/test_program.py` : règle `overflow_prompt` ci-dessus, et un test de `_verdict` qui la couvre.
- `tests/test_i18n.py`, test des causes de la V1.3 (`PREFIX_CAUSES` complet), `test_config` pour les deux
  réglages.
- `git grep -n "short_memory.history"` dans `tests/` et `tools/e2e/` : réaligner les tests qui comptent
  les composants de `short_memory` ou les nœuds du schéma.
- E2E (`tools/e2e/run_e2e.py`, faux moteur, débordement provoqué par des messages longs) :
  - `s_compaction` : trois messages longs, le troisième déborde ; boutons dans l'Orchestration et la Vue
    humain ; clic « Compacter » : boutons désactivés, ligne « Résumé de compaction », bulle « Résumé
    (compaction) », message renvoyé seul ; jauge du cache : « écrit », cause « compaction » ;
  - `s_sliding_window` : même débordement, clic « Fenêtre glissante » : aucun appel avant le renvoi,
    marqueur « N échanges retirés », cause « fenêtre glissante » ;
  - `s_compact_button` : bouton désactivé sans conversation et pendant un tour (infobulle), menu au clavier,
    entrée indisponible avec sa raison, compaction hors débordement sans renvoi ;
  - `s_scenarios` : le module 7 liste trois scénarios.

## Points ouverts

1. **Calibrage du scénario `compaction`.** Le débordement doit venir de l'historique avec le vrai
   modèle, et le renvoi tenir après compaction, alors que l'estimation de la CI (2 caractères par token)
   surestime d'environ 40 % et ne simule que l'échange précédent. **Recommandation :** briques allégées
   `[short_memory, system_prompt, tools]`, `tools: [read_file]` ; p1 « Appelle l'outil read_file sur
   journal_serveur.log, puis dis-moi quelle erreur grave la sauvegarde de cette nuit a rencontrée. », p2
   « Appelle l'outil read_file sur guide_harnais.md, puis cite les bornes que le harnais pose à la boucle. »,
   `overflow_prompt: 2`. Dans `test_program`, à l'estimation : p1 tient, p2 déborde avec l'historique ;
   avec la jauge exacte (`WAVESTACK_TEST_GGUF`) : en plus, p2 tient après compaction. Mesure réelle en
   recette (report).
2. **Cause du cache en mode chat.** `prefix_not_reused` n'existe qu'en local ; en cloud, la jauge montre
   l'écriture renvoyée par le fournisseur, sans cause. **Recommandation :** cause en local seulement dans
   cette story, la ligne `history_compacted` de l'Orchestration et le marqueur expliquent le reste en cloud ;
   report d'une cause côté cloud.
3. **Échanges gardés hors débordement.** **Recommandation :** `compaction_keep = 2` pour les deux
   stratégies (maquette 3), réglable ; entrée indisponible si la conversation n'a pas plus de 2 échanges.
4. **Où vit l'appel de résumé.** **Recommandation :** un tour du harnais (`turn_started.kind =
   "compaction"`), seule façon d'être dans l'Orchestration et de bénéficier de l'annulation, du coût par
   tour et de l'état `turn` ; le renvoi est un second tour. Alternative écartée : étape en tête du tour
   renvoyé (pas de chemin hors débordement, `_last` à corriger en cours de tour).
5. **Orchestration après compaction.** **Recommandation :** elle garde les tours retirés (trace), seules
   la Vue humain et le Contexte LLM les remplacent par le marqueur ; « Vider la conversation » garde son
   comportement.
6. **Hooks et garde-fous sur l'appel de résumé.** **Recommandation :** aucun (ni `before_model_call`, ni
   garde-fous), comme la génération de l'Atelier RAG ; plafond FinOps, annulation et sortie bornée
   s'appliquent. Le résumé n'est pas un tour de l'utilisateur.
7. **Débordement à un appel ultérieur du tour** (résultat d'outil du tour). **Recommandation :** les
   boutons s'affichent dès qu'il y a un échange ; `k` est calculé avec les `steps` de l'appel refusé
   (pire cas : le renvoi relance les mêmes outils). La maquette « résultat d'outil du tour : pas de
   boutons » vaut pour le premier tour, sans échange.
8. **Durée estimée.** **Recommandation :** calculée des débits mesurés, omise sans mesure et en cloud.
9. **Libellé du segment du résumé.** **Recommandation :** champ `label` ajouté à `Part` avec défaut `None`,
   recopié dans `Segment.label_text` ; à confirmer à l'implémentation si un mécanisme existant suffit.

## Reports

- Cause du cache côté cloud (point 2).
- Calibrage du scénario `compaction` avec le vrai modèle en recette (point 1).

</intent-contract>
