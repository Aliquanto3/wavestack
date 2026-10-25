---
title: 'WaveStack V1.4 (4) : compaction et fenêtre glissante'
type: 'feature'
created: '2026-10-25'
status: 'ready-for-dev'
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
- Ne refait pas les totaux du programme (durée totale « 6 h au total », nombre de modules ou de scénarios
  cités dans `docs/guide.md` et les tests de décompte) : la story 13.6 ajoute en parallèle un module 8
  « Cache », le second à fusionner refait ces totaux. La ligne du module 7 du tableau de `docs/guide.md`
  (durée, scénarios) est en revanche mise à jour par cette story.

## Critères d'acceptation

1. Fenêtre de 4 096 tokens, chat principal, brique Mémoire courte allumée, au moins un échange dans la
   branche active : un débordement affiche, dans l'Orchestration (`overflowCard`) et sous la note de la
   Vue humain, « Continuer avec : » et deux boutons, « Compacter » et « Fenêtre glissante », chacun avec
   sa ligne calculée (maquette 2), puis « Autres stratégies (non montrées ici) : » et les deux textes
   restants. Un choix indisponible (un seul échange pour la fenêtre glissante, ou message et étapes du
   tour qui ne tiennent pas même avec le minimum d'historique) a son bouton désactivé, sa raison en
   infobulle et en nom accessible.
2. Sans échange (premier tour, message seul trop long), Mémoire courte éteinte, débordement du
   sous-agent ou d'un atelier : la carte est celle d'aujourd'hui (quatre stratégies en texte, aucun bouton).
3. Un clic désactive les deux boutons des deux vues, applique la stratégie, puis renvoie seul le message
   refusé comme un nouveau tour (`turn_started.replay_of` nul) sur l'historique réécrit ; « Rejouer le
   dernier prompt » rejoue ensuite ce nouveau tour, sur l'historique réécrit. Un clic sur une carte
   périmée (un autre tour, un vidage ou un scénario depuis) affiche la raison du refus sous les boutons.
4. Compaction : un tour du harnais (`turn_started.kind = "compaction"`) fait un seul appel au modèle
   actif, sans outils ni raisonnement, sortie bornée par `[context] compaction_max_tokens` ; l'Orchestration
   montre l'étape « Résumé de compaction » (modèle, tokens, durée, coût) ; le coût entre dans
   `turn_ended` et dans le bilan (V1.3), dont la colonne « Cette conversation » n'est pas remise à zéro.
   L'historique devient `[résumé] + échanges gardés`.
5. Fenêtre glissante : aucun appel au modèle, aucun tour ; l'historique perd ses plus anciens échanges.
6. La Vue humain et le Contexte LLM remplacent les échanges retirés par un marqueur : pour la compaction,
   la bulle « Résumé (compaction) » et son texte ; pour la fenêtre glissante, « 3 échanges retirés
   (fenêtre glissante) ». Le marqueur prend la place du premier échange retiré, dans l'ordre de
   l'historique (maquette 4). Dans le Contexte LLM et la jauge, le résumé a son propre libellé
   « Résumé (compaction) ».
7. Mode local : le premier appel du tour suivant émet `prefix_not_reused` avec la cause `compaction` ou
   `sliding_window` ; la jauge du cache (V1.3 story 2) affiche une part « écrit » non nulle et la cause
   « compaction » ou « fenêtre glissante ». Le préfixe commun (message système) peut rester « lu » : le
   critère ne demande pas « lu 0 ».
8. Un bouton « Compacter ▾ » à gauche de « Vider la conversation » ouvre un menu de deux entrées
   (maquette 3), qui appliquent la stratégie sans renvoyer de message. Le bouton est désactivé, raison en
   infobulle et en nom accessible, pendant un tour, sans conversation, Mémoire courte éteinte ; une entrée
   est désactivée, avec sa raison, quand elle n'a rien à retirer.
9. Annulation, erreur du fournisseur ou plafond FinOps pendant le résumé : le tour de compaction finit
   avec son statut, l'historique est inchangé, aucun message n'est renvoyé.
10. Scénario `compaction` dans le module 7 « Contexte long et carte », entre `compression` et
    `harness_map` : sa conversation déborde au troisième prompt (`overflow_prompt: 3`, deux échanges dans
    l'historique, pour que la fenêtre glissante ait un échange à retirer), la consigne fait choisir la
    compaction puis, après relance, la fenêtre glissante. La consigne de `harness_map` ne renvoie plus
    au « scénario précédent » (le précédent devient `compaction`, sans compression).
11. fr, en et de ; `test_i18n.py` vert ; chaque valeur de `PrefixCause` a son texte (test de la V1.3).

## Décisions de la spec

### Contrats

- **`PrefixCause`** (`trace/catalog.py:805`) : ajouter en fin de liste `"compaction"` puis
  `"sliding_window"`, chacune avec son commentaire `# V1.4 story 4: …`.
- **`CompactionChoice`** (nouveau, `trace/catalog.py`, près de `ContextOverflowPayload`) :
  `strategy: Literal["compaction", "sliding_window"]`, `available: bool`, `count: int` (échanges
  résumés ou retirés), `detail_text: str` (ligne de la maquette), `reason_text: str | None = None`
  (pourquoi indisponible).
- **`ContextOverflowPayload`** (`catalog.py:366`), en ajouts avec défaut (les traces et tests existants
  valident toujours) : `choices: list[CompactionChoice] = []` (vide hors chat principal, sans échange ou
  Mémoire courte éteinte) et `other_strategies_text: list[str] = []` (les textes de `old_tool_results`
  et `lazy_loading`, que le front affiche sous « Autres stratégies » quand `choices` n'est pas vide ;
  sinon `strategies_text`, inchangé).
- **`CompactionStatePayload`** (nouvel événement `compaction_state`, ajouté à `PAYLOAD_MODELS`) :
  `choices: list[CompactionChoice]`, valeurs hors débordement (garder `compaction_keep` échanges). Émis
  hors tour (`turn_id` nul, `actor: "harness"`) par `_emit_compaction_state()` (nouveau), appelé à la fin
  de `_run_turn` (à côté de `_emit_window_state()`, `:7228` : `_refresh_preview()` n'est pas appelé après
  un tour), à la fin d'une stratégie, et depuis `_emit_preview()` (vidage, scénario, changement de
  brique). Calcul sans rendu (comparaison de `n` à `compaction_keep`). Lu par le bouton « Compacter ▾ ».
- **`HistoryCompactedPayload`** (nouvel événement `history_compacted`) : `strategy`,
  `removed_turn_ids: list[str]` (échanges sortis de l'historique, résumés ou retirés),
  `summary_text: str | None` (compaction), `before_tokens: int`, `after_tokens: int` (aperçu du
  contexte avant et après), `message_text: str` (« 3 échanges retirés (fenêtre glissante) »,
  « 5 échanges résumés (compaction) »). Pour la compaction, émis dans le tour de compaction (son
  `turn_id`) ; pour la fenêtre glissante, hors tour (`turn_id` nul, `actor: "harness"`).
- **`TurnStartedPayload`** (`catalog.py:193`), en ajout : `kind: Literal["message", "compaction"] =
  "message"` (le front lit `kind ?? "message"`). Un tour de compaction a pour `message` la demande de
  résumé (`session.compaction.request`) et `actor: "harness"`.
- **Intention** `POST /api/intentions/compact` (`web/app.py`, modèle `CompactIntention` à côté de
  `SendIntention`, route à côté de `clear_conversation`), corps `{strategy: Literal["compaction",
  "sliding_window"], resend_turn_id: str | None = None}` ; 409 avec la raison sur `SendRefused`, comme
  `clear_conversation` ; réponse `{"started": true}`.
- **Configuration** (`config.py`, `wavestack.toml` `[context]`, commentés en français) :
  `compaction_max_tokens = 256` (sortie du résumé, bornée 64 à 512) et `compaction_keep = 2` (échanges
  gardés hors débordement, borné 1 à 5).
- **`Exchange`** (`app_session.py:438`, `NamedTuple`) : champ ajouté en dernier, `summary: bool = False`.
  Vérifié : une seule construction positionnelle (`:7200`), aucun dépaquetage ni sérialisation de
  `Exchange` ; `_last` garde des tuples d'`Exchange` en mémoire seulement.
- **`Part`** (`context/segments.py:47`, `NamedTuple`) : champ ajouté en dernier, `label: str | None =
  None`, recopié en `label_text=parts[owner].label` au seul point de création des segments
  (`context/render.py:354`), commun au local et au mode chat (`_attribute`). `Segment.label_text` existe
  déjà et la jauge le lit (`window.py:92`, `:284`).
- **Composant** `short_memory.compaction` (`bricks/registry.py`, sous `short_memory`, `kind="memory"`,
  `hosting="local_process"`, `edges_to=["core.harness"]`) : composant de l'appel de résumé et des parts du
  résumé dans le contexte.

### Session (`session/app_session.py`)

- `_emit_overflow(payload, raw_used, main: tuple[TurnState, str, list[dict]] | None = None)` : le seul
  appel du chat principal (`_turn`, `:7300`) passe `main=(shown, message, steps)`, ce qu'il faut pour
  rejouer le rendu de l'appel refusé ; celui du sous-agent (`:5583`) ne change pas. Avec `main`, Mémoire
  courte effective et historique non vide, calcule `choices` (règles ci-dessous) et
  `other_strategies_text` ; retient `self._overflowed = turn_id` (nouveau, `None` à l'init).
  `_overflowed` repasse à `None` au début de tout tour, à `clear_conversation`, au lancement d'un
  scénario et à la réinitialisation.
- **Règles de calcul** (fonction pure `_compaction_plan(n, fits, keep, overflow) -> dict[strategy,
  CompactionChoice]`, testable seule) :
  - `fits(k, compacted)` : rendu à blanc par `_render(replace(state, history=…), message, None, steps)`
    (`call_id=None`, aucun `context_rendered` émis), vrai si `payload["overflow"]` est faux (en mode
    chat, la somme brute des estimations, règle d'AD-4 qui a refusé l'appel). `compacted` : l'historique
    rendu est `[résumé fictif (demande, texte vide)] + history[-k:]`, et il faut en plus
    `used + compaction_max_tokens ≤ usable`.
  - *au débordement* : `k` = le plus grand nombre d'échanges récents gardés qui tient, cherché par
    dichotomie (`fits` est monotone en `k` : O(log n) rendus, pas n). Fenêtre glissante : `k ≥ 1`,
    retire `n - k` ; indisponible si `n == 1` (« un seul échange : rien à retirer »). Compaction :
    `k ≥ 0`, résume les `n - k` plus anciens. Si même le `k` minimal ne tient pas (message ou étapes du
    tour trop lourds), le choix est **indisponible** (`session.overflow.choices.unavailable.still_too_long`,
    « même ainsi, le message et les résultats du tour ne tiendraient pas ») : pas d'appel payant ni de
    boucle de débordement.
  - *hors débordement* : les deux gardent `compaction_keep` échanges ; indisponibles si
    `n ≤ compaction_keep` (« pas assez d'échanges »).
  - Le résumé déjà présent compte comme un échange : une nouvelle compaction le résume avec les autres, la
    fenêtre glissante peut le retirer.
- `compact(strategy, resend_turn_id)` (intention classe b, motif de `clear_conversation`) : d'abord
  `_wait_mcp_connections()` hors verrou (comme `_start`, jamais sur le worker) ; puis sous
  `_memory_lock` et `_lock`, refus hors `idle` (`_refusal_reason()`), sans engin, Mémoire courte éteinte
  (`session.refused.compact_short_memory`), historique vide (`compact_empty`), choix indisponible
  (`reason_text`), `resend_turn_id` différent de `_overflowed` (`compact_stale`, carte périmée). Le
  message renvoyé est `self._last[1]` (le message brut : le renvoi repasse les garde-fous d'entrée), le
  tour refusé étant le dernier lancé (`_last[0] == resend_turn_id`).
  - *Fenêtre glissante* : sous les mêmes verrous, `_history[:] = history[n-k:]`,
    `_cache_cause = "sliding_window"`, `_last = None` si aucun renvoi, `_overflowed = None`,
    `_loaded_docs` recalculés (ci-dessous) ; avec renvoi, l'état passe à `turn` dans la même section
    (`_lock` n'est pas réentrant : sans cela un `send` concurrent passerait entre la réécriture et le
    renvoi). Hors verrou : `history_compacted`, `_emit_architecture()`, `_refresh_preview()`,
    `_emit_compaction_state()` ; puis, si renvoi, `self._start(message, chained=True)`.
  - *Compaction* : `_turns += 1`, état `turn` (comme `_start`, `CancelToken` dans `self._cancel`, sans
    toucher `_last`), puis `_run_compaction(turn_id, plan, message | None, cancel)` sur le worker.
- `_start(message, chained=False)` : `chained=True` (interne) accepte l'état `turn` posé par `compact`
  ou par le tour de compaction et saute `_wait_mcp_connections()` (déjà fait par `compact`, et interdit
  sur le worker, qui applique les connexions : il bloquerait jusqu'au délai). Le reste de `_start`
  (nouveau `turn_id`, `_last` sur l'historique réécrit, soumission de `_run_turn`) est inchangé.
- `_run_compaction` : portée `turn_id`, `context_id="main"`, `trigger="user"` ; `turn_started`
  (`kind="compaction"`) ; une étape `component="short_memory.compaction"`, libellé de phase
  `session.compaction.phase` ; contexte du résumé construit comme `_rag_lab_generate` (`:10637`) :
  message système = `content/prompts/compaction.md` (langue de la session par `config.content_file`), un
  message `user` = transcription des échanges à résumer (`Utilisateur : …` / `Assistant : …`, réponses
  finales seulement, résultats d'outils remplacés par `[outil <nom> : <n> caractères]`, résumé précédent
  en tête) ; la transcription vient de `Exchange.user`, déjà masqué par les garde-fous (`_turn_input`),
  jamais du message brut ; si elle ne tient pas, les plus anciens tombent de la transcription (pas de
  l'historique).
  - *Local* : `saved = self._save_main_state()`, `_call_model(rendered, cancel, (), compaction_max_tokens,
    False, …)`, puis `_lab_restore(saved, "compaction")` en `finally`, comme l'Atelier RAG ; jamais
    `_keep_cache` : `_main_cache` garde les ids du contexte principal, et la comparaison du tour suivant
    reste vraie (le moteur a retrouvé ce contexte).
  - *Chat* : `_call_model_chat` (chemin du tour : coût dans `_turn_costs`, `record_spend`,
    `max_session_usd`, `context_reconciled` sous l'id de son propre appel).
  - Ni hooks `before_model_call` ni garde-fous, outils `()`, raisonnement éteint.
  - Statut `completed` : sous `_lock`, `_history[:] = [Exchange(turn_id, request, summary, "",
    summary=True)] + kept`, `_cache_cause = "compaction"` (sans `or`, après `_lab_restore`), `_last = None`
    si aucun renvoi, docs recalculés ; `history_compacted` ; `turn_ended` avec
    `_turn_cost()`/`_turn_impact()` ; aucun `Exchange` ordinaire ajouté. Puis, si renvoi,
    `_start(message, chained=True)` depuis le worker (le `_run_turn` soumis passe après la tâche en
    cours : l'exécuteur a un seul worker, `:858`) ; sinon `idle`, `_emit_architecture()`,
    `_refresh_preview()`, `_emit_compaction_state()`. Autre statut : historique inchangé, pas de renvoi,
    `idle`.
- `_last` : le renvoi passe par `_start`, qui enregistre l'historique réécrit ; sans renvoi,
  `_last = None` (« Rejouer » désactivé, comme après « Vider la conversation »), sinon le rejeu
  rétablirait l'historique d'avant.
- **Rendu du résumé** (`_messages`, `:4502`) : un `Exchange` `summary` est rendu comme les autres
  (message `user` = la demande, message `assistant` = le résumé), ses parts avec
  `("short_memory", "short_memory.compaction")` et `label` = `main.ctx.compaction_summary`.
- **Docs et skills chargés** : seules les documentations du mode local (`_loaded_docs`, D16-b : lues
  dans l'historique, `build_turn_state` `:4190`) sont recalculées : ne restent que celles dont le résultat
  de `load_tool_doc` est encore dans les `steps` d'un échange gardé. Les skills (corps dans le message
  système) et les documentations du mode chat (dans `tools`) ne vivent pas dans l'historique : gardées.
- **Cache** : `_cache_cause` posée sans `or` (dernier changement structurel, comme `reset`) ;
  `_check_reuse` (`:8422`) la consomme au premier appel du tour suivant, sans autre changement.
  `_main_cache` n'est pas remis à `None` (sinon aucun `prefix_not_reused`). Mode chat : pas de
  `prefix_not_reused` (`_check_reuse` ne vaut que pour `RenderedContext`), cause reportée.
- **Durée estimée** (ligne « ≈ 20 s en local ») : `tokens de la transcription / _read_tps[modèle] +
  compaction_max_tokens / _gen_tps[modèle]`. `_gen_tps` (nouveau, `dict[str, float]`) est noté à côté de
  `_note_read_rate` (`:2782`), depuis l'`output_tps` d'un appel local (le débit de génération n'est mesuré
  nulle part aujourd'hui). Durée omise (texte sans `{duration}`) tant que l'un des deux débits manque, et
  en cloud.

### Front (`web/static/app.js`, `index.html`, `app.css`)

- `overflowCard(overflow, turn)` (`:5155`, paramètre `turn` ajouté) : si `overflow.choices` n'est pas
  vide, « Continuer avec : », un bouton par choix (`pane-text-action`, `data-strategy`, désactivé si
  `!available`, raison en `title` et `aria-describedby`), sa `detail_text`, puis « Autres stratégies (non
  montrées ici) : » et `other_strategies_text` ; sinon le rendu d'aujourd'hui. La note de débordement de
  la Vue humain (`turnNote`, `:3326`) reçoit les mêmes deux boutons. Clic :
  `postIntention("/api/intentions/compact", {strategy, resend_turn_id: turn.id})`, tous les boutons de ce
  tour désactivés (`store.compactedTurns`, un `Set`) ; un 409 affiche sa raison sous les boutons et les
  réactive.
- `#compact-conversation` (`index.html:174`, avant `#clear-conversation`) : bouton « Compacter ▾ » et
  menu de deux entrées, sur le motif de `#display-menu-toggle` (`aria-haspopup`, `aria-expanded`,
  `aria-controls`) ; état tiré de `compaction_state` et de `session_state` ; Échap ferme le menu, focus
  rendu au bouton.
- `turn_started.kind === "compaction"` : pas de bulle utilisateur. `history_compacted` : la Vue humain et
  le Contexte LLM masquent les tours de `removed_turn_ids` (`store.compactedOut`, un `Set` : test en
  O(1) par tour à chaque rendu, comme `chatFrom` pour le vidage) ; le marqueur (bulle « 📝 Résumé
  (compaction) » et `summary_text`, ou ligne `message_text` de la fenêtre glissante) s'affiche à la place
  du premier tour retiré. L'Orchestration garde tous les tours (trace) et affiche la ligne « Résumé de
  compaction » dans le tour de compaction.
- Jauge du cache : `PREFIX_CAUSES` (`:5620`) lit les nouvelles clés de `main.orch.prefix_causes`, sans
  code.

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
    retirés) » ; `.unavailable.{single,too_few,still_too_long}` ; formes `{one, other}` pour `{count}`,
    comme `declared` ;
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
  qui vaut pour le premier appel et ne laisse aucun échange à compacter). Validateur :
  `2 ≤ overflow_prompt ≤ len(prompts)`, et jamais avec `expects_overflow`.
- `content/scenarios.yaml` : module 7 `scenarios: [compression, compaction, harness_map]`,
  `duration_min: 60`. Scénario `compaction` (titre « Compaction et fenêtre glissante ») : briques
  `[short_memory, system_prompt, tools]` (sans compression, qui réduirait les résultats et empêcherait le
  débordement), `tools: [read_file]`, trois prompts, `overflow_prompt: 3` (calibrage : Décisions du point
  de contrôle, point 1) ; consigne : envoyer les prompts, au débordement cliquer « Compacter », suivre
  l'étape « Résumé de compaction » dans l'Orchestration, la bulle du résumé, la jauge du cache (« écrit »,
  cause « compaction ») ; relancer le scénario, refaire déborder et choisir « Fenêtre glissante » : aucun
  appel, « N échanges retirés », cause « fenêtre glissante » ; dire que le bouton « Compacter ▾ » fait de
  même hors débordement, et rappeler l'exception AD-9 (ce scénario déborde exprès). Miroirs en et de.
- `harness_map` : sa consigne dit « Les briques de compression restent actives, comme au scénario
  précédent » ; après l'insertion, le précédent est `compaction`, sans compression. Réécrire en « comme au
  scénario « Compression » » (fr, en, de), ou faire réactiver la compression par les briques de
  `harness_map` si elles ne la contiennent pas.
- `docs/guide.md` (+ miroirs s'ils existent) : ligne « 7. Contexte long et carte » à 60 min, scénarios
  « compression du contexte, compaction et fenêtre glissante, carte du harnais » ; pas la phrase des
  totaux.
- `tests/test_program.py` : `test_every_scenario_fits…` traite `overflow_prompt` : les prompts avant lui
  tiennent (règle d'aujourd'hui) ; lui déborde, avec l'historique **entier** des prompts précédents
  (prompt + résultat compté + `EXCHANGE_TEMPLATE`, réponses à 0 : borne basse, quel que soit le mode de
  simulation) ; avec la jauge exacte (`WAVESTACK_TEST_GGUF`), il tient en plus après compaction
  (historique = `compaction_max_tokens + EXCHANGE_TEMPLATE`) et après fenêtre glissante (dernier échange
  seul). La ligne `assert not scenario.expects_overflow` reste.

## Plan de tests

- `tests/test_compaction.py` (nouveau, `booted_session(FakeEngine())`, faux fournisseur pour le cloud) :
  - `_compaction_plan` : `k` au débordement (dichotomie : nombre d'appels à `fits` en O(log n), compté
    par une doublure de `fits`), `k ≥ 1` pour la fenêtre glissante, `n == 1`, `k` minimal qui ne tient
    pas → indisponible `still_too_long`, hors débordement avec `compaction_keep`, résumé compté comme un
    échange ;
  - débordement avec historique : `choices` et `other_strategies_text`, `ContextOverflowPayload` validé
    par `PAYLOAD_MODELS` ; sans historique, Mémoire courte éteinte, sous-agent, atelier MCP :
    `choices == []` ;
  - débordement à un appel ultérieur du tour (résultat d'outil) avec historique : `k` calculé avec les
    `steps` de l'appel refusé ;
  - fenêtre glissante avec renvoi : historique réduit, aucun `model_call_started` avant le tour renvoyé,
    `turn_started` du message sans `replay_of`, `_last[2]` = historique réduit, `prefix_not_reused.cause
    == "sliding_window"` ; « Rejouer » ensuite garde l'historique réduit ; un `send` concurrent pendant la
    stratégie est refusé (état `turn`) ;
  - compaction avec renvoi : tour `kind="compaction"`, un appel `component="short_memory.compaction"`,
    `max_tokens == compaction_max_tokens`, sans outils ; `history_compacted.removed_turn_ids` ;
    historique `[summary=True] + gardés` ; contexte rendu suivant contenant le résumé avec son composant et
    `label_text` ; `prefix_not_reused.cause == "compaction"` et `again_tokens > 0` ; coût du résumé dans
    `turn_ended` (cloud) ; la transcription ne contient que les textes masqués de l'historique ;
  - renvoi depuis le worker avec une connexion MCP en attente : aucune attente de
    `_wait_mcp_connections` (durée du tour sous le délai de connexion) ;
  - annulation, erreur du fournisseur, plafond FinOps pendant le résumé : historique inchangé, pas de
    renvoi, état `idle` ;
  - refus : hors `idle`, historique vide, Mémoire courte éteinte, `resend_turn_id` périmé (après un autre
    tour, un vidage, un scénario), choix indisponible ;
  - documentation locale chargée dans un échange retiré : déchargée ; dans un échange gardé : gardée ;
    skill chargée et documentation du mode chat : gardées ;
  - `compaction_state` émis après un tour (fin de `_run_turn`), après une stratégie et après un vidage,
    valeurs hors débordement ;
  - durée estimée : omise sans débit mesuré et en cloud, calculée avec `_read_tps` et `_gen_tps` posés.
- `tests/test_turn.py:97` et les tests qui lisent `context_overflow` : verts sans changement
  (`strategies_text` intact).
- `tests/test_compression.py:795` (`test_scenario_compression_opens_the_last_module`) : son ancre
  `scenarios: [compression, harness_map]\n\ntransverse:` devient `[compression, compaction, harness_map]`
  (le second à fusionner avec 13.6 réaligne aussi `\n\ntransverse:`).
- `tests/test_scenarios.py` : nombre de scénarios + 1 (`compaction`) ; ne pas refaire les totaux si 13.6
  est fusionnée avant (le second à fusionner les refait) ; validateur de `overflow_prompt`.
- `tests/test_program.py` : règle `overflow_prompt` ci-dessus, et un test de `_verdict` qui la couvre.
- `tests/test_i18n.py`, `tests/test_cache_gauge_texts.py` (`PREFIX_CAUSES` complet), `test_config` pour
  les deux réglages et leurs bornes.
- `git grep -n "short_memory.history"` dans `tests/` et `tools/e2e/` (`test_bricks.py:301`,
  `test_trace_architecture.py:81`) : réaligner les tests qui comptent les composants de `short_memory` ou
  les nœuds du schéma.
- E2E (`tools/e2e/run_e2e.py`, faux moteur, débordement provoqué par des messages longs), un par élément
  visuel :
  - `s_compaction` : trois messages longs, le troisième déborde ; boutons dans l'Orchestration et la Vue
    humain, « Autres stratégies » et ses deux textes ; clic « Compacter » : boutons désactivés dans les deux
    vues, ligne « Résumé de compaction », bulle « Résumé (compaction) » à la place du premier échange
    retiré, message renvoyé seul ; Contexte LLM : tours retirés masqués, segment du résumé avec son
    libellé dans la jauge ; jauge du cache : « écrit », cause « compaction » ;
  - `s_sliding_window` : même débordement, clic « Fenêtre glissante » : aucun appel avant le renvoi,
    marqueur « N échanges retirés », cause « fenêtre glissante » ; clic sur la carte d'un débordement
    précédent (périmée) : raison du refus sous les boutons, boutons réactivés ;
  - `s_compact_button` : bouton désactivé sans conversation et pendant un tour (infobulle), menu au clavier
    (Échap, focus rendu), entrée indisponible avec sa raison, compaction hors débordement sans renvoi ;
    premier message trop long sans historique : carte sans boutons (critère 2) ;
  - `s_programme` (`:5834`, il n'existe pas de `s_scenarios`) : le module 7 liste trois scénarios.

## Décisions du point de contrôle

Point de contrôle du 2026-10-25, relecteur à la place d'Anaël (règle du run). Chaque décision est à
revoir par Anaël.

1. **Calibrage du scénario `compaction`** · décision · à revoir. Modifié : **trois prompts,
   `overflow_prompt: 3`**, pas deux. Raison : au débordement de p2, l'historique n'a qu'un échange, et la
   fenêtre glissante, qui garde au moins le dernier (SPEC.md:107), n'aurait rien à retirer : le critère 10
   (choisir ensuite la fenêtre glissante) serait impossible. Briques `[short_memory, system_prompt,
   tools]`, `tools: [read_file]` gardées ; p1 et p2 lisent chacun un fichier de `content/demo_files/`
   (au choix du développeur, `journal_serveur.log` en premier ; `guide_harnais.md`, 8,6 Ko, seulement si
   p2 tient encore avec p1 dans l'historique), p3 est une question sans outil qui s'appuie sur les deux
   lectures (le débordement vient de l'historique, au premier appel, cas de la maquette 2 ; après
   compaction, le résumé porte les faits utiles). Test : borne basse de l'historique entier à l'estimation,
   jauge exacte avec `WAVESTACK_TEST_GGUF`. Mesure réelle en recette (report).
2. **Cause de cache côté cloud** · décision · à revoir. Acceptée : cause en local seulement. Raison :
   `prefix_not_reused` n'existe que pour `RenderedContext` ; en cloud, la jauge montre déjà l'écriture
   renvoyée par le fournisseur, et `history_compacted` et le marqueur disent pourquoi. Report gardé.
3. **`compaction_keep = 2`** · décision · à revoir. Acceptée, pour les deux stratégies, entrée
   indisponible avec 2 échanges ou moins. Raison : valeur de la maquette 3 ; la même règle pour les deux
   entrées garde le menu lisible ; réglable de 1 à 5.
4. **Tour du harnais `kind="compaction"` puis renvoi chaîné** · décision · à revoir. Acceptée, avec deux
   corrections : `_start(message, chained=True)` saute `_wait_mcp_connections()` (documentée « never on
   the worker » : depuis le worker elle attendrait le délai de connexion sans que les connexions soient
   appliquées), que `compact` appelle avant ses verrous ; la fenêtre glissante avec renvoi passe aussi par
   `chained=True`, l'état `turn` posé sous le verrou (`_lock` n'est pas réentrant, un `send` concurrent
   passerait sinon). `_last = None` sans renvoi. Raison : seul chemin qui donne l'Orchestration,
   l'annulation, le coût par tour et l'état `turn` ; le rejeu reste juste parce que `_start` enregistre
   l'historique réécrit.
5. **Orchestration garde les tours retirés** · décision · à revoir. Acceptée. Raison : l'Orchestration
   est la trace de ce qui s'est passé ; la Vue humain et le Contexte LLM montrent ce que lit le modèle.
   Précision ajoutée : le marqueur prend la place du premier échange retiré (ordre de la maquette 4).
6. **Ni hook ni garde-fou sur l'appel de résumé** · décision · à revoir. Acceptée. Raison : comme la
   génération de l'Atelier RAG ; la transcription vient de l'historique déjà masqué (`_turn_input`), et le
   message renvoyé repasse tous les garde-fous et hooks comme un tour ordinaire. Plafond FinOps,
   annulation et sortie bornée s'appliquent. Précision : en local, l'état du moteur est sauvé et restauré
   autour de l'appel (`_save_main_state` / `_lab_restore`), sans `_keep_cache`, pour que la jauge du cache
   du tour suivant dise vrai.
7. **Débordement à un appel ultérieur du tour** · décision · à revoir. Acceptée, modifiée : les boutons
   s'affichent dès qu'il existe un échange, `k` est calculé avec les `steps` de l'appel refusé (pire
   cas), mais un choix dont le `k` minimal ne tient toujours pas est **indisponible** avec sa raison, au
   lieu de rester disponible. Raison : sinon un clic paie un appel de résumé pour un renvoi qui débordera
   à coup sûr, et la carte revient en boucle ; la maquette 2 (« résultat d'outil du tour : pas de
   boutons ») est respectée dans l'esprit, la raison renvoyant aux autres stratégies.
8. **Durée estimée** · décision · à revoir. Acceptée, corrigée : aucun débit de génération n'est mesuré
   aujourd'hui (`_window_state` n'a que `_read_tps`). Ajout de `_gen_tps[modèle]`, noté depuis
   l'`output_tps` des appels locaux à côté de `_note_read_rate` ; durée omise tant qu'un des deux débits
   manque, et en cloud. Raison : la maquette demande une durée calculée, jamais écrite en dur.
9. **Champ `label` sur `Part`** · décision · à revoir. Confirmée : aucun mécanisme existant ne porte un
   libellé d'une part vers son segment ; `Segment.label_text` existe et la jauge le lit déjà ; un seul
   point de recopie (`render.py:354`) sert le local et le mode chat. Ajout en dernier avec défaut `None` :
   les constructions positionnelles existantes ne changent pas.

Note sur la story 13.6 (module 8 « Cache ») : décision · à revoir. Cette story passe le module 7 à
60 min et met à jour sa ligne du guide ; le second à fusionner refait les totaux (durée, nombre de
modules et de scénarios) et l'ancre `\n\ntransverse:` de `test_compression.py`.

### Corrections apportées à la spec au point de contrôle

- `_emit_overflow` reçoit `main=(state, message, steps)` : sans eux, le calcul de `k` était impossible.
- `fits` défini (rendu à blanc, règle d'AD-4 en chat, place du résumé) et recherche par dichotomie.
- `compaction_state` émis par `_emit_compaction_state()` en fin de tour : `_refresh_preview()` n'est pas
  appelé après un tour.
- Docs et skills : seules les documentations locales sont recalculées (skills et docs du mode chat ne
  sont pas dans l'historique).
- Appel local du résumé entre `_save_main_state` et `_lab_restore`, sans `_keep_cache` ; critère 7 sans
  « lu 0 ».
- `harness_map` : consigne « comme au scénario précédent » devenue fausse ; ligne du module 7 du guide.
- Tests ajoutés : `test_compression.py:795`, `test_cache_gauge_texts.py`, débordement en cours de tour,
  renvoi sans attente MCP, `send` concurrent, transcription masquée ; E2E : Contexte LLM et libellé du
  résumé, carte périmée (409), carte sans boutons ; `s_programme` au lieu de `s_scenarios`, inexistant.
- Numéros de ligne réalignés sur `ff8c405` (`:4502`, `:7300`, `:8422`, `:3326`, `:5155`).

## Reports

- Cause du cache côté cloud (point 2).
- Calibrage du scénario `compaction` avec le vrai modèle en recette (point 1) : vérifier sur le PC cible
  que p1 et p2 tiennent, que p3 déborde, et que p3 tient après compaction et après fenêtre glissante.

</intent-contract>
