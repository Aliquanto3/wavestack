---
title: 'V1.5 story 4 : vue « Évaluer l''agent » (lancer, k essais, comparer)'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: ''
review_loop_iteration: 0
context: ['_bmad-output/specs/spec-wavestack-evaluer-l-agent/SPEC.md', '_bmad-output/specs/spec-wavestack-evaluer-l-agent/vues.md', '_bmad-output/specs/spec-wavestack-evaluer-l-agent/brownfield.md', '_bmad-output/specs/spec-wavestack-evaluer-l-agent/contrat-des-cas.md']
---

## Intent

CAP-4 de la V1.5. Le formateur ouvre « Évaluer l'agent » depuis la barre du haut. Il lance la suite (tous les cas, un essai chacun) ou un seul cas (1 ou 3 essais), sur le modèle courant, sans rechargement. Les cas passent l'un après l'autre et restent annulables. La Vue humain les montre en direct, chacun avec son badge. Pour chaque cas, la vue affiche « Réussi », « Échoué » ou « Non lancé », la vérification fautive et la trace du tour. Avec 3 essais, elle affiche aussi les réussites sur 3, pass@3 et pass^3. Les exécutions de la séance restent en mémoire, sans persistance après un redémarrage. On en compare deux, cas par cas. « Effacer mes cas » vide les cas de séance.

**Base.** Le développement part d'`origin/main` après la fusion des stories 1, 2 et 3. Il en a besoin :
- story 1 : `AgentCase`, `verify`, `store.*` ;
- story 2 : `content/agent_cases.yaml`, `tools/eval/`, `tests/test_agent_cases_provided.py` ;
- story 3 : `agent-case-form.js`, `agent-case-form.css`, les clés `main.agent_case.*` et `GET /draft`.

Si l'une n'est pas fusionnée, le dev rebase sur sa branche et le signale dans son rapport. Le contrat (`contrat-des-cas.md`) ne change pas.

Disposition : maquette, section 2. Comportement : `vues.md`. Lancement : `brownfield.md`, « Lancer un cas ».

## Choix : un nouvel état de session, `agent_eval`

**Décision.** `SessionState` gagne la valeur `agent_eval` : c'est l'état de repos de la session pendant une exécution. Les tours des cas passent par les états habituels, `turn` et `awaiting_human`. À la fin d'un tour, la session revient à `agent_eval` au lieu de `idle`. Elle ne revient à `idle` qu'une fois l'exécution finie et la configuration rétablie.

**Pourquoi pas un simple verrou :**
1. **Pas de fenêtre entre deux cas.** Avec un verrou, la session repasserait par `idle` après chaque cas. Tous les points qui testent `state != "idle"` (envoi, scénario, réinitialisation, fenêtre, modèle, ateliers, téléchargements, compaction, cache) accepteraient alors une intention pendant ce bref instant, sauf à ajouter le verrou à chacun. Avec un état, ces points refusent déjà, avec `_refusal_reason()`, sans changer de code.
2. **Le front suit déjà l'état.** L'événement `session_state` désactive le compositeur et affiche la raison. Il ne manque que le bouton « Arrêter », qui doit rester visible en `agent_eval`. C'est ainsi que les états `llm_lab`, `rag_lab` et `mcp_lab` ont été ajoutés.
3. **Un état se trace.** L'Orchestration et le journal montrent `session_state: agent_eval` ; un verrou serait invisible.

**Coût, assumé :** une valeur de plus dans `SessionState` (une structure partagée). Le dev cherche avec `git grep` les tests et le front qui énumèrent les états, et les réaligne dans le même commit.

**Complément : un garde HTTP pour les intentions de classe (a).** Ces intentions sont acceptées à tout moment : brique, sous-option, outil, hook, compétence, serveur MCP, prompt système, mémoire, langue. Pendant une exécution, elles changeraient la configuration qu'on rétablira ensuite. Les modifier une à une toucherait une vingtaine de méthodes d'`app_session.py`. À la place, `register_agent_eval_routes` installe un *middleware*. Pendant une exécution, il refuse en 409 toute requête `POST`, `PUT`, `PATCH` ou `DELETE` sous `/api/`, avec le texte `agent_eval.refused.running`, sauf :
- `POST /api/intentions/stop` ;
- les routes `GET`.

La validation humaine (`/api/intentions/approval`) est elle aussi refusée : c'est le harnais qui répond pendant une exécution. Les appels faits directement à la session (dans les tests) ne passent pas par ce garde, mais les intentions de classe (b) restent refusées par l'état.

## Exécuteur

### Fichiers et responsabilités

- `src/wavestack/agent_eval/runs.py` : **pur**, sans I/O, sans session ni horloge. Contient les modèles des exécutions, le classement d'un essai, les agrégats (pass@k et pass^k), la comparaison et la trace (`trace_items`).
- `src/wavestack/session/agent_eval_runner.py` : classe `AgentEvalRunner(session)`, attribut `session.agent_eval` créé dans `AppSession.__init__`. Elle porte le fil de l'exécution, les exécutions en mémoire, les enveloppes de chaque essai et le chargement des cas (fournis dans la langue de la session, cas de séance par `store.read_session_cases()`).
- `app_session.py` : seulement les points d'accroche listés plus bas. Pas de logique d'évaluation.

### API de l'exécuteur

```python
class AgentEvalRunner:
    def cases(self) -> CasesListing                   # fournis + séance, erreur de fichier comprise
    def start(self, case_ids: list[str] | None, k: Literal[1, 3]) -> str   # run_id
    def wait(self, run_id: str, timeout: float | None = None) -> Run     # tests et outil de mesure
    def state(self) -> EvalState                      # en-tête, progression, exécutions (résumés)
    def run(self, run_id: str) -> Run                 # KeyError si inconnu
    def trace(self, run_id: str, case_id: str, trial: int) -> TrialTrace   # KeyError
    def compare(self, a: str, b: str) -> Comparison   # KeyError
    def delete_case(self, case_id: str) -> None       # SendRefused : en cours, cas fourni ; KeyError
    def clear_cases(self) -> int                      # SendRefused pendant une exécution
    @property
    def running(self) -> bool
```

`start` :
- `case_ids=None` veut dire la suite : les cas fournis dans leur ordre, puis les cas de séance dans l'ordre du fichier. Un fichier de séance illisible ne bloque pas la suite, qui part avec les seuls cas fournis.
- `k=3` exige exactement un cas (`ValueError` → 422 `refused.k_suite`). Un `k` autre que 1 ou 3 est rejeté par la validation de la route.
- Un id inconnu lève `KeyError`. Une liste vide lève `SendRefused(refused.no_case)`.
- Refus hors de `idle` : `SendRefused` avec `_refusal_reason()`.
- Sous `session._lock`, `start` vérifie `idle`, prend l'instantané de la configuration, passe à l'état `agent_eval` (raison `session.state.agent_eval`), puis lance un `threading.Thread(daemon=True, name="wavestack-agent-eval")`. Il n'utilise pas `session._executor`, le seul fil de travail des tours : il attend des tours, il ne peut donc pas tourner sur ce fil.
- `case_ids` explicites : c'est la voie des tests et de l'outil de mesure. La route ne propose que la suite ou un cas.

### Les états d'une exécution

```
idle ──start──▶ agent_eval ──(cas i)──▶ turn ⇄ awaiting_human ──fin du tour──▶ agent_eval
                    │ ▲                                                         │
                    │ └──────────── on_overflow : compact(by_run) ──────────────┘
                    └── plus de cas, arrêt, plafond, erreur ──▶ rétablissement ──▶ idle
```

`Run.status` : `running`, `done`, `cancelled` (arrêt demandé), `budget` (plafond atteint) ou `error` (exception inattendue, `error_text` rempli). Les cas pas encore joués d'une exécution `cancelled` ou `error` passent `not_run` (`cancelled`), ceux d'une exécution `budget` passent `not_run` (`budget`).

### Boucle, cas par cas puis essai par essai

Pour chaque cas, puis pour chacun de ses `k` essais :

1. **Arrêt demandé** (`run.stop_requested`) : l'essai et tous les suivants passent `not_run` (`cancelled`).
2. **Plafond de dépense** : on reprend le calcul de `_rag_finops()` (`spent_usd >= max_session_usd`), extrait en `AppSession._finops_capped() -> tuple[bool, float]` et partagé par les deux appelants. Plafond atteint : l'essai et tous les suivants passent `not_run` (`budget`). La raison donne le plafond, en monnaie formatée comme `usd_price_fr`.
3. **Fenêtre** : si `case.window` n'est pas `None` et diffère de `session._window_state()["configured"]` (décision 7 de la story 3 : ce champ, et aucun autre), tous les essais du cas passent `not_run` (`window`). La raison est « demande une fenêtre de {window} tokens (fenêtre courante : {current}) », avec les nombres formatés dans la langue. On passe au cas suivant. **`set_context_window` n'est jamais appelé.**
4. **Configuration du cas** : `session._apply_case(case, run)`, voir « Points d'accroche ».
5. **Envoi** : `mark = journal.last_seq()`, puis `session._start(case.prompt, by_run=True)`. Les `turn_started` émis pendant que l'exécution désigne ce cas portent `case_id` et `run_id` : le tour du prompt, le tour de compaction et le message renvoyé.
6. **Attente** : voir « Attente et validation H5 ».
7. **Débordement** : si le dernier `turn_ended` principal vaut `overflow` et si `case.on_overflow != "none"`, l'exécuteur appelle `session.compact(case.on_overflow, resend_turn_id=<tour refusé>, by_run=True)`, puis attend de nouveau. Un `SendRefused`, par exemple quand la stratégie n'est pas disponible, est ignoré : le verdict lira le débordement.
8. **Enveloppes de l'essai** : `journal.events_since(mark)`, filtrées sur les `turn_id` dont le `turn_started` porte ce `run_id` et ce `case_id` (tous contextes, `sub{n}` compris). Comme l'exécution est séquentielle, ce sont les tours de l'essai, au sens de `contrat-des-cas.md` (`verdict_turn_ids`). L'exécuteur garde la liste (des références aux enveloppes du `Journal`, sans copie) sous la clé `(run_id, case_id, trial)`.
9. **Classement** (`runs.classify_trial`, pur) :
   - si l'arrêt a été demandé pendant l'essai, l'essai est `not_run` (`cancelled`). Ses enveloppes restent visibles par « Voir le tour » : un cas interrompu par le formateur n'est pas un échec de l'agent ;
   - si l'essai contient un `harness_error` de `cause == "max_session_usd"` (appel cloud refusé en cours de cas), l'essai est `not_run` (`budget`), et l'exécution s'arrête en `budget` ;
   - sinon, `verify(case, envelopes, session.language)` donne `passed` ou `failed`.
10. **Bornes de boucle** : `[tools] max_calls`, `max_retries` et `subagent_max_calls` s'appliquent sans changement, par le tour lui-même. Un tour fini en `limit` donne un échec « tour incomplet (fini en « limit ») », et l'exécution continue.

**Fin de l'exécution, dans un `finally`** :
- la configuration d'avant est rétablie (`_restore_after_run`) et la conversation est vidée ;
- `run.status` et `ended_at` sont fixés ;
- l'exécution est désignée comme finie ;
- `_set_state("idle")`.

Une exception inattendue est tracée par `session._error(...)`, comme pour une stratégie, et l'exécution passe en `error`. La session finit toujours en `idle`.

### Attente et validation H5

Avant chaque essai, l'exécuteur s'abonne au journal (`Journal.subscribe`) et se désabonne dans un `finally`. Le rappel ne fait que déposer dans une `queue.Queue` les enveloppes de type `approval_requested`, `turn_ended` du contexte principal et `session_state`. Le fil de l'exécution les lit :
- **`approval_requested`** d'un tour de l'essai : `session.answer_approval(id, approved=(case.approval == "approve"), disable_hook=False)`. Un `SendRefused` (validation déjà tranchée) est ignoré. L'`approval_resolved` émis par la session trace la décision. Le formateur ne répond jamais.
- **`session_state` à `agent_eval`** : le tour ou la stratégie est fini, on passe à l'étape suivante.

On ne répond pas depuis le rappel : il tourne dans le fil qui émet, sous le verrou du journal. Il n'y a pas de délai d'expiration, puisque les bornes de boucle et « Arrêter » terminent tout tour. `wait(run_id, timeout)` est le seul délai, pour les tests et l'outil de mesure.

### Arrêt

Les deux boutons appellent `stop()` : « Arrêter » de la vue et le bouton existant du compositeur (`/api/intentions/stop`). `AppSession.stop()` gagne une branche en tête, juste après `_mcp_lab_stop()` : si une exécution est en cours, elle fixe `run.stop_requested`, puis :
- en `turn` ou `awaiting_human` : la logique existante annule le tour, et une validation en attente est tranchée `cancelled` ;
- en `agent_eval` (entre deux cas) : elle renvoie `True`, et l'exécuteur verra la demande à l'étape 1.

## Points d'accroche dans `app_session.py`

Chaque point est petit et nommé, pour limiter les conflits avec le fichier de 15 000 lignes :

1. `self.agent_eval = AgentEvalRunner(self)` dans `__init__`, et `self._eval_run: Run | None = None`. L'exécution courante est lue sous `_lock`.
2. **`_rest_state()`** : rend `("agent_eval", <raison>)` pendant une exécution, `("idle", None)` sinon. Elle remplace `_set_state("idle")` partout où un tour ou une stratégie se termine : fin de `_run_turn` (vers la l. 7767), `finally` de `_run_strategy` (vers la l. 6677), et tout autre retour à `idle` atteint depuis un tour (le dev les relève avec `git grep '_set_state("idle")'`). Les retours à `idle` du chargement de modèle, du téléchargement et des ateliers ne changent pas.
3. **`_start(message, chained=False, *, by_run=False)`** et **`compact(strategy, resend_turn_id=None, *, by_run=False)`** : avec `by_run`, l'état de départ accepté est `agent_eval` au lieu de `idle`. L'appelant de l'API ne passe jamais `by_run`. Avec `by_run`, `reason_text` pendant le tour vaut `session.state.agent_eval` (pas `_TURN_FR`).
4. **`_refusal_reason()`** : pendant une exécution, et quel que soit l'état (`turn`, `awaiting_human` ou `agent_eval`), elle rend `Message("agent_eval.refused.running")`.
5. **`turn_started`** (les deux sites d'émission : tour de message et tour de compaction, vers les l. 6755 et 7703) : `| self._case_tag()`, qui vaut `{"case_id": …, "run_id": …}` pendant un essai et `{}` sinon. `TurnStartedPayload` (`trace/catalog.py:194`) gagne `case_id: str | None = None` et `run_id: str | None = None`.
6. **`_apply_case(case, run)`** : la configuration d'un cas, en `agent_eval` seulement (`SendRefused` sinon). C'est une variante de `_reconfigure`. Elle reprend sa partie commune, que le dev extrait sans changer le comportement de `reset()` ni de `launch_scenario()` :
   - conversation vidée (`_history`, `_last`, documents et compétences chargés, actions armées, `_overflowed`) ;
   - `_apply_launch_config()`, puis la configuration du cas comme `launch_scenario.apply` : `_wanted = set(case.bricks)`, et `tools`, `hooks`, `skills`, `mcp_servers` quand ils ne sont pas `None`. Les ids inconnus de la session sont ignorés (voir « Points ouverts ») ;
   - `_mcp_lazy` et `_rag_rerank` gardent les valeurs de lancement (le contrat ne les porte pas, story 3) ;
   - `_custom_prompt = case.system_prompt` s'il est figé, sinon le prompt de la session pris dans l'instantané : `_apply_launch_config` le remet à zéro, il faut donc le remettre ;
   - `_history[:] = [Exchange(...)]` depuis `case.history`, comme le fait `case_player._apply` ;
   - émet `conversation_cleared`, jamais `harness_reset` ;
   - **ne restaure pas la mémoire de démonstration** : le cas « mémoire globale » lit celle de la séance, et l'exécution ne doit pas effacer la mémoire du formateur ;
   - pas de pré-remplissage de scénario ; `_active_scenario = None` pendant l'exécution ;
   - les connexions et déconnexions MCP, `_request_rag_sync`, `_request_compression_sync`, `_emit_bricks`, `_emit_architecture` et l'aperçu restent comme dans `_reconfigure`. Les chargements partent sur le fil de travail, avant le tour du cas, qui y est mis en file après eux.
7. **`_restore_after_run(snapshot)`** : même chemin que `_apply_case`, avec l'instantané pris par `start` : `_wanted`, `_tools_enabled`, `_mcp_enabled`, `_skills_enabled`, `_hooks_enabled`, `_mcp_lazy`, `_rag_rerank`, `_custom_prompt` et `_active_scenario`. Sans historique, sans pré-remplissage, sans restauration de mémoire. Un seul `conversation_cleared`, un `bricks_changed` final égal à celui d'avant l'exécution.
8. **`stop()`** : la branche décrite plus haut.
9. **`_emit_state`** : `stoppable = True` en `agent_eval`.
10. **`_start_way_back`** (E119, rechargement vers un autre modèle après une architecture refusée) : pendant une exécution, il n'est pas appelé (jamais de rechargement). Le cas échoue par son tour en `error`, et l'exécution continue.
11. `reset()` et `_reconfigure` ne touchent pas à `self.agent_eval`. Les exécutions survivent à `reset()`, à « Vider la conversation », aux changements de scénario et de modèle.

Messages : `session.state.agent_eval` (raison de l'état) et `agent_eval.refused.running` ont le même texte.

## Modèle des exécutions en mémoire (`runs.py`)

```
TrialOutcome = {
  trial: int,                               # 1..k
  status: "passed" | "failed" | "not_run",
  not_run_reason: "window" | "cancelled" | "budget" | None,
  reason_text: str | None,                  # raison du non-lancement, dans la langue de la session
  verdict: CaseVerdict | None,              # None si non lancé avant tout tour
  failing: CheckVerdict | None,             # première vérification qui échoue (plafond compris)
  model_calls: int,
  turn_ids: list[str],
  has_trace: bool,                          # des enveloppes existent (essai annulé en cours compris)
}
CaseResult = {
  case_id, title_text, brick, brick_label_text, source,   # instantané pris au lancement
  max_model_calls, k,
  status: "pending" | "running" | "passed" | "failed" | "not_run",
  not_run_reason, reason_text,              # cas entièrement non lancé
  trials: list[TrialOutcome],
  successes: int, ran: int,                 # essais réussis, essais lancés (passed + failed)
  pass_at_k: bool | None, pass_pow_k: bool | None,         # k = 3 seulement, sinon None
}
Run = {
  run_id: "r1", "r2"…,                      # compteur du processus
  started_at, ended_at: str | None,         # ISO local, horloge de la session
  scope: "suite" | "case", k: 1 | 3,
  language: "fr" | "en" | "de",
  model: ActiveModel | None,                # active_model() au lancement
  system_prompt: {text, is_default},        # celui de la session au lancement
  status: "running" | "done" | "cancelled" | "budget" | "error", error_text: str | None,
  cases: list[CaseResult],
  passed: int, ran: int, not_run: int,      # comptés par cas
}
```

- Les exécutions vivent dans un `OrderedDict`, avec au plus `MAX_RUNS = 20` exécutions finies. Au-delà, la plus ancienne part avec ses enveloppes. L'exécution en cours n'est jamais évincée.
- **Statut d'un cas** :
  - k = 1 : celui de son essai ;
  - k = 3 : `passed` si `successes > ran / 2` (majorité stricte des essais lancés : 2 sur 3 donne « Réussi », comme la maquette), `failed` si `ran ≥ 1`, `not_run` si aucun essai n'a été lancé (avec la raison du premier essai non lancé).
- Les cas fournis prennent leur titre dans la langue de la session au lancement ; les cas de séance gardent la leur (non-goal : pas de traduction). L'instantané garde l'affichage d'une exécution intact après « Effacer mes cas ».
- Rien n'est écrit sur disque (non-goal).

## pass@k et pass^k

Sur `n = k` essais d'un même cas, avec `c` réussites :
- **pass@k** = « au moins un essai réussit ». L'estimateur sans biais `1 − C(n−c, k) / C(n, k)` vaut 1 si `c ≥ 1`, sinon 0, quand `n = k`.
- **pass^k** = « tous les essais réussissent » (τ-bench). `C(c, k) / C(n, k)` vaut 1 si `c = n`, sinon 0.

On affiche donc des booléens, pas des taux. Valeurs définitives dès qu'elles sont acquises :
- `pass_at_k` vaut `True` dès qu'un essai réussit, `False` si les `k` essais ont été lancés sans réussite, et `None` sinon (exécution arrêtée avant) ;
- `pass_pow_k` vaut `False` dès qu'un essai échoue, `True` si les `k` essais ont été lancés et ont tous réussi, et `None` sinon.

`None` s'affiche « — ». Ces valeurs n'existent que pour k = 3 et ne s'affichent que dans cette vue.

## Comparaison (`runs.compare_runs(a, b)`, pur)

- **Lignes** : les cas de A dans leur ordre, puis ceux de B absents de A.
- **Changement** :

| A | B | `change` |
|---|---|---|
| passed | failed | `regressed` |
| failed | passed | `fixed` |
| même statut lancé | | `unchanged` |
| absent ou `not_run` | | `absent` (`absent_from: "a"` ou `"b"`) |

Un `not_run` compte comme absent : le cas n'a pas été joué. La cellule affiche « Non lancé » et le changement « absent de A » ou « absent de B ». Absent des deux côtés n'arrive pas.
- **En-tête** : `differs` liste `model` (si les `ActiveModel.id` diffèrent) et `system_prompt` (si les textes diffèrent). `control = not differs` donne la ligne « Rejeu témoin : ce qui change ici vient du modèle, pas de vous. »
- `same_run` : A et B identiques donnent 422 `refused.same_run`.
- Les deux exécutions peuvent avoir des `k` différents : on compare le statut des cas.

## Trace d'un essai (`runs.trace_items(envelopes, verdict, lang)`, pur)

Une liste d'éléments `{seq, context_id, text, fault: bool}`, dans l'ordre des `seq`. Les textes viennent de `messages.yaml` (`agent_eval.trace.*`). Les éléments d'un contexte `sub{n}` sont préfixés par `trace.sub`.

| Enveloppe | Élément |
|---|---|
| `turn_started` `message` / `compaction` | `trace.message` / `trace.compaction` |
| `model_call_started` | `trace.model_call` (numéroté sur l'essai, tous contextes : le même compte que `model_calls_max`) |
| `tool_started` (+ `tool_ended` de même `call_id`) | `trace.tool` : outil, arguments `nom = "valeur"` coupés à 80 caractères, statut |
| `hook_decided` sauf `allow` | `trace.hook` : hook, point, décision |
| `approval_resolved` | `trace.approval` |
| `subagent_started` / `subagent_ended` | `trace.subagent_started` / `trace.subagent_ended` |
| `history_compacted` | `trace.compacted` |
| `limit_reached` | `trace.limit` |
| `harness_error` | `trace.error` |
| `turn_ended` (principal) | `trace.ended`, puis `trace.answer` pour le dernier tour (réponse de `checks._Journal(...).answer()`, coupée à 300 caractères) |

**Faute** : l'élément dont le `seq` est le plus grand ≤ `failing.seq`. Si `failing.seq` vaut `None` (témoin absent), c'est le dernier élément. Aucun élément n'est marqué pour un essai réussi. Les libellés de statut, de décision et de limite réutilisent ceux du journal qui existent déjà dans `messages.yaml`. Le dev les cherche avant d'en créer.

## Routes (`src/wavestack/web/agent_eval_api.py`)

`register_agent_eval_routes(app, app_session)` installe les routes et le garde. Préfixe `/api/agent_eval/`, partagé avec la story 3, qui a `GET /draft`, `POST /verdict` et `POST /cases`. Erreurs : `{"detail": <texte dans la langue de la session>}` (`render(...)`), comme les autres intentions.

| Route | Entrée | Réponse |
|---|---|---|
| `GET /cases` | | 200 `CasesListing` |
| `DELETE /cases/{case_id}` | | 200 `{deleted: true}` ; 404 `refused.unknown_case` ; 409 `refused.provided_case`, `refused.running`, `refused.unreadable` |
| `DELETE /cases` | | 200 `{cleared: <nombre de cas effacés, 0 si le fichier était illisible>}` ; 409 `refused.running` |
| `POST /runs` | `{case_id: str \| null, k: 1 \| 3}` (`extra="forbid"`) | 202 `{run_id}` ; 404 `unknown_case` ; 409 état (raison de session), `no_case` ; 422 `k_suite` ; 422 FastAPI pour un `k` hors de 1 ou 3 |
| `GET /state` | | 200 `EvalState` |
| `GET /runs/{run_id}` | | 200 `Run` ; 404 `unknown_run` |
| `GET /runs/{run_id}/trace?case_id=…&trial=1` | | 200 `TrialTrace` ; 404 `unknown_run` ou `unknown_trial` |
| `GET /compare?a=r1&b=r2` | | 200 `Comparison` ; 404 `unknown_run` ; 422 `same_run` |

`POST /cases` : la route est prise par la story 3 pour l'enregistrement, d'où `POST /runs` pour lancer. `DELETE /cases/{id}` et `DELETE /cases` sont dans le module de la story 4, sur le même chemin que le `POST` de la story 3 : FastAPI les distingue par la méthode.

```
CaseSummary = {id, title_text, brick, brick_label_text, symptom_text, assertion_text,
               max_model_calls, window, source: "fourni"|"recette"|"séance", origin_turn_id}
CasesListing = {provided: [CaseSummary], session: [CaseSummary],
                session_error: "unreadable" | null}
EvalState = {
  header: {model: ActiveModel | null, system_prompt: {start_text, is_default}},  # start_text : 60 caractères
  current: null | {run_id, index, total, case_id, trial, k, stop_requested},
  runs: [RunSummary],          # du plus ancien au plus récent
}
RunSummary = {run_id, started_at, ended_at, scope, k, model_label, system_prompt_is_default,
              status, passed, ran, not_run}
TrialTrace = {items: [TraceItem], failing: CheckVerdict | null, model_calls}
Comparison = {a, b, differs: ["model" | "system_prompt"], control: bool,
              rows: [{case_id, title_text, a: status | null, b: status | null,
                      change: "regressed"|"fixed"|"unchanged"|"absent", absent_from: "a"|"b"|null}]}
```

**Progression, sans flux.** Le front interroge `GET /state` toutes les secondes tant que `current` n'est pas nul, et à chaque `session_state` reçu (voir Front). À chaque changement de `index` ou de `trial`, et à la fin, il recharge `GET /runs/{current.run_id}`. On n'ajoute ni flux SSE ni nouveau type d'événement au journal : la vue Évaluer du RAG procède déjà par des `GET` (`/api/rag_lab/evaluation`), et les tours des cas sont déjà dans le journal (`case_id`, `run_id`).

Le badge et la trace se calculent côté serveur. La langue affichée est celle de la session au moment de la requête ; les `reason_text` des verdicts gardent la langue de l'exécution.

## Front

### Fichiers

- `web/static/agent-eval.js`, module ES, importé par `app.js` :

  ```js
  export function openView(caseId)          // ouvre la vue ; caseId : fait défiler jusqu'au cas et le met en évidence
  export function closeView()
  export function sessionStateChanged(state) // appelé par app.js à chaque session_state
  export function caseBadge(caseId)          // élément « Cas : titre » ou null ; titre lu dans le cache de GET /cases
  ```

  Au chargement, le module appelle `registerOpenView(openView)` et `onCaseSaved(refreshCases)`, importés d'`./agent-case-form.js`. Textes : `t()` d'`./i18n.js`. Jamais d'import d'`app.js` (cycle).
- `web/static/agent-eval.css` : seulement les classes de la vue dans la maquette (`ae-panel`, `ae-head`, `ae-banner`, `ae-progress`, `ae-group`, `ae-cases`, `ae-case`, `ae-status`, `ae-reason`, `ae-trace`, `ae-dots`, `ae-confirm`, `ae-table`, `ae-diff`, `ae-badge`). Les classes communes (`ae-button`, `ae-text`, `ae-actions`, `ae-danger`) restent dans `agent-case-form.css`. Le module ajoute au `<head>` les deux feuilles s'il ne les trouve pas (test sur `href`), comme la story 3 : `index.html` ne charge aucune des deux.

### Vue et disposition

- **Entrée** : le bouton `#agent-eval-toggle` de la barre du haut, `aria-pressed`. Il ouvre et ferme la vue. Échap ferme la vue quand le focus est dedans.
- **Panneau** : `<section id="agent-eval-panel" class="ae-panel" aria-labelledby=…>`, créé par le module. Ouvert, il prend la place des volets Contexte LLM et Orchestration, masqués (`hidden`), qui retrouvent leur état à la fermeture. La Vue humain reste visible et montre les tours des cas en direct. Le dev passe par l'API de `panes.js` si elle le permet, sinon par un attribut sur le conteneur des volets et une règle d'`agent-eval.css`.
- **Badge** : dans `app.js`, à la création de la bulle d'un `turn_started` qui porte `case_id`, `caseBadge(case_id)` est inséré avant la bulle (`ae-badge`, « Cas : {titre} »). Si le cas est inconnu, le badge montre l'id.

### États de la vue (d'après la maquette)

1. **Chargement** : « Chargement des cas… ».
2. **En-tête** : modèle courant, « Prompt système : « {début} » (par défaut | modifié) », bandeau « Démonstration, pas un banc… ». Toujours visible.
3. **Listes** :
   - « Suite fournie » : titre, `· brique · plafond N`, « Lancer » avec le choix « 1 essai » ou « 3 essais » (deux boutons ou un menu ; « 1 essai » par défaut) ;
   - « Mes cas » : `· séance · tour N · plafond N` et « Supprimer » en plus ;
   - « Mes cas » vide : `mine.empty` ;
   - fichier illisible : `mine.unreadable`, avec « Effacer mes cas » seul.
4. **Avertissement du premier lancement** : si aucune exécution n'existe dans la séance (`runs` vide) et que la page ne l'a pas encore montré, un lancement affiche d'abord dans la page, sans boîte de dialogue du navigateur, « La conversation sera vidée ; votre configuration est rétablie à la fin. », avec « Lancer » et « Annuler ». Une fois par page.
5. **Refusé** : un 409 sur `POST /runs` affiche le `detail` sous les actions (par exemple un tour en cours dans le chat).
6. **En cours** :
   - barre `role="status"` : « Cas {index} sur {total} » pour la suite, « Essai {trial} sur {k} » pour un cas, puis « Arrêter » (`ae-danger`, qui appelle `/api/intentions/stop`), et « Arrêt demandé… » une fois cliqué ;
   - cas courant en « En cours » (`running`), cas suivants en « En attente », cas finis avec leur résultat ;
   - « Lancer », « Lancer la suite », « Supprimer » et « Effacer mes cas » sont désactivés, avec la raison en `title` ;
   - le compositeur montre `session.state.agent_eval`, et son bouton « Arrêter » est visible.
7. **Résultat par cas** :
   - « Réussi » ou « Échoué ». Pour un échec : « {type de vérification} : {reason_text} ». Le libellé du type vient des clés de la story 3 (`main.agent_case.form.checks.kind.*`), et de `check.model_calls_max` pour le plafond ;
   - « Non lancé » avec sa raison : fenêtre, arrêté, plafond de dépense ;
   - « Voir le tour » (`aria-expanded`) charge la trace (`GET /runs/{id}/trace`) et la déplie en `ol.ae-trace`. L'élément fautif porte `class="fault"` et un texte caché « (événement fautif) ». « Masquer le tour » la replie. Avec 3 essais, un sélecteur d'essai (1, 2, 3) est placé au-dessus de la trace ;
   - k = 3 : un rond par essai (`ae-dots`, `i.ok`, `i.ko`, `i.skip`, avec un `aria-label` qui énumère les statuts), puis « 2 réussis sur 3 · pass@3 : oui · pass^3 : non ».
8. **Exécutions de la séance** : `table.ae-table`, avec deux colonnes de boutons radio, « A » et « B », puis heure (HH:MM), modèle, prompt système (« par défaut » ou « modifié »), résultat (« 6 réussis sur 7 lancés » et « · 1 non lancé » s'il y en a), et la portée pour une exécution d'un cas (« L'heure, 3 essais »). Une exécution arrêtée ou bloquée par le plafond l'affiche après le résultat. Par défaut : A est l'avant-dernière exécution, B la dernière.
9. **Comparer** : visible dès deux exécutions. Il montre « Comparer A et B », puis l'en-tête « Diffère : modèle, prompt système. » ou la ligne de rejeu témoin, puis le tableau Cas, A, B, Changement (`ae-diff reg` pour « régressé », `ae-diff fix` pour « corrigé »). A et B identiques : `compare.same_run`.
10. **Vide** : « Lancez la suite pour obtenir une première exécution. »
11. **Effacer mes cas** : une confirmation dans la page (`ae-confirm`, `role="alert"`), « Effacer les {count} cas de séance ? Les cas fournis restent. », avec « Effacer » et « Annuler ». Après l'effacement, « Mes cas » se vide, et les exécutions passées restent intactes (instantanés).
12. **Plus de réponse** (réseau ou 5xx) : `error.no_answer` dans la vue, et la dernière liste affichée reste.

Pas d'agrégat ailleurs que dans cette vue et dans la vue Évaluer du RAG (SPEC, Constraints).

## Textes

### Interface : `main.agent_eval.*`

Fichiers : `content/ui.yaml`, `content/i18n/en/ui.yaml`, `content/i18n/de/ui.yaml`. Le bloc `agent_eval:` se place juste après le bloc `main.agent_case` de la story 3 (lui-même après `main.compare`, avant `orch:`). Mêmes clés et mêmes variables dans les trois langues. Allemand en « Sie ». Formes `.one` et `.other` là où un nombre varie. Les noms des volets (« Vue humain ») en en et de reprennent ceux de `main.panes.*`.

| Clé | fr | en | de |
|---|---|---|---|
| `toggle` | Évaluer l'agent | Evaluate the agent | Agent bewerten |
| `title` | Évaluer l'agent | Evaluate the agent | Agent bewerten |
| `loading` | Chargement des cas… | Loading the cases… | Fälle werden geladen … |
| `head.model` | Modèle : {model} | Model: {model} | Modell: {model} |
| `head.prompt` | Prompt système : « {start} » ({state}) | System prompt: “{start}” ({state}) | Systemprompt: „{start}“ ({state}) |
| `head.prompt_default` | par défaut | default | Standard |
| `head.prompt_custom` | modifié | modified | geändert |
| `banner` | Démonstration, pas un banc : quelques cas, un petit modèle, des résultats qui varient d'une exécution à l'autre. | A demonstration, not a benchmark: a few cases, a small model, results that vary from one run to the next. | Eine Demonstration, kein Benchmark: wenige Fälle, ein kleines Modell, Ergebnisse, die von Lauf zu Lauf schwanken. |
| `group.provided` | Suite fournie | Provided suite | Mitgelieferte Suite |
| `group.mine` | Mes cas | My cases | Meine Fälle |
| `mine.empty` | Aucun cas de séance : faites « En faire un cas » sur un tour de la Vue humain. | No session case yet: use “Make it a case” on a turn of the Human view. | Noch kein Sitzungsfall: Nutzen Sie „Als Fall speichern“ bei einem Turn der Ansicht Mensch. |
| `mine.unreadable` | Le fichier de vos cas est illisible : vos cas ne peuvent pas être lancés. « Effacer mes cas » le vide ; les cas fournis restent jouables. | The file with your cases is unreadable: your cases cannot be run. “Clear my cases” empties it; the provided cases can still be run. | Die Datei mit Ihren Fällen ist nicht lesbar: Ihre Fälle können nicht gestartet werden. „Meine Fälle löschen“ leert sie; die mitgelieferten Fälle bleiben spielbar. |
| `case.meta` | · {brick} · plafond {max} | · {brick} · limit {max} | · {brick} · Obergrenze {max} |
| `case.meta_session` | · séance · {turn} · plafond {max} | · session · {turn} · limit {max} | · Sitzung · {turn} · Obergrenze {max} |
| `case.run` | Lancer | Run | Starten |
| `case.run_label` | Lancer le cas « {title} » | Run the case “{title}” | Fall „{title}“ starten |
| `case.trials.one` | {count} essai | {count} try | {count} Versuch |
| `case.trials.other` | {count} essais | {count} tries | {count} Versuche |
| `case.delete` | Supprimer | Delete | Löschen |
| `case.delete_label` | Supprimer le cas « {title} » | Delete the case “{title}” | Fall „{title}“ löschen |
| `run_suite` | Lancer la suite | Run the suite | Suite starten |
| `busy` | Une exécution est en cours. | A run is in progress. | Ein Lauf ist im Gang. |
| `first_run.text` | La conversation sera vidée ; votre configuration est rétablie à la fin. | The conversation will be cleared; your configuration is restored at the end. | Die Unterhaltung wird geleert; Ihre Konfiguration wird am Ende wiederhergestellt. |
| `first_run.go` | Lancer | Run | Starten |
| `first_run.cancel` | Annuler | Cancel | Abbrechen |
| `progress.suite` | Cas {index} sur {total} | Case {index} of {total} | Fall {index} von {total} |
| `progress.trials` | Essai {trial} sur {k} | Try {trial} of {k} | Versuch {trial} von {k} |
| `stop` | Arrêter | Stop | Stoppen |
| `stop_requested` | Arrêt demandé… | Stop requested… | Stopp angefordert … |
| `status.passed` | Réussi | Passed | Bestanden |
| `status.failed` | Échoué | Failed | Nicht bestanden |
| `status.not_run` | Non lancé | Not run | Nicht gestartet |
| `status.running` | En cours | Running | Läuft |
| `status.pending` | En attente | Waiting | Wartet |
| `failing` | {check} : {reason}. | {check}: {reason}. | {check}: {reason}. |
| `check.model_calls_max` | Appels au modèle sous le plafond | Model calls within the limit | Modellaufrufe unter der Obergrenze |
| `trace.show` | Voir le tour | Show the turn | Turn anzeigen |
| `trace.hide` | Masquer le tour | Hide the turn | Turn ausblenden |
| `trace.label` | Trace du cas | Case trace | Ablauf des Falls |
| `trace.loading` | Lecture de la trace… | Reading the trace… | Ablauf wird gelesen … |
| `trace.fault` | (événement fautif) | (faulty event) | (fehlerhaftes Ereignis) |
| `trace.trial` | Essai {trial} | Try {trial} | Versuch {trial} |
| `trace.gone` | Cette trace n'est plus en mémoire. | This trace is no longer in memory. | Dieser Ablauf ist nicht mehr im Speicher. |
| `trials.summary.one` | {passed} réussi sur {ran} · pass@{k} : {at} · pass^{k} : {all} | {passed} passed out of {ran} · pass@{k}: {at} · pass^{k}: {all} | {passed} von {ran} bestanden · pass@{k}: {at} · pass^{k}: {all} |
| `trials.summary.other` | {passed} réussis sur {ran} · pass@{k} : {at} · pass^{k} : {all} | {passed} passed out of {ran} · pass@{k}: {at} · pass^{k}: {all} | {passed} von {ran} bestanden · pass@{k}: {at} · pass^{k}: {all} |
| `trials.prefix` | {k} essais : | {k} tries: | {k} Versuche: |
| `yes` | oui | yes | ja |
| `no` | non | no | nein |
| `undecided` | — | — | — |
| `runs.title` | Exécutions de la séance | Runs of this session | Läufe dieser Sitzung |
| `runs.col.time` | Heure | Time | Uhrzeit |
| `runs.col.model` | Modèle | Model | Modell |
| `runs.col.prompt` | Prompt système | System prompt | Systemprompt |
| `runs.col.result` | Résultat | Result | Ergebnis |
| `runs.pick_a` | A | A | A |
| `runs.pick_b` | B | B | B |
| `runs.result.one` | {passed} réussi sur {ran} lancés | {passed} passed out of {ran} run | {passed} von {ran} gestarteten bestanden |
| `runs.result.other` | {passed} réussis sur {ran} lancés | {passed} passed out of {ran} run | {passed} von {ran} gestarteten bestanden |
| `runs.not_run.one` | · {count} non lancé | · {count} not run | · {count} nicht gestartet |
| `runs.not_run.other` | · {count} non lancés | · {count} not run | · {count} nicht gestartet |
| `runs.scope_case` | {title}, {trials} | {title}, {trials} | {title}, {trials} |
| `runs.status.cancelled` | · arrêtée | · stopped | · gestoppt |
| `runs.status.budget` | · plafond de dépense atteint | · spending cap reached | · Ausgabengrenze erreicht |
| `runs.status.error` | · interrompue par une erreur | · interrupted by an error | · durch einen Fehler unterbrochen |
| `runs.empty` | Lancez la suite pour obtenir une première exécution. | Run the suite to get a first run. | Starten Sie die Suite, um einen ersten Lauf zu erhalten. |
| `compare.title` | Comparer A et B | Compare A and B | A und B vergleichen |
| `compare.diff` | Diffère : {fields}. | Differs: {fields}. | Unterschied: {fields}. |
| `compare.field.model` | modèle | model | Modell |
| `compare.field.system_prompt` | prompt système | system prompt | Systemprompt |
| `compare.control` | Rejeu témoin : ce qui change ici vient du modèle, pas de vous. | Control rerun: what changes here comes from the model, not from you. | Kontrolllauf: Was sich hier ändert, kommt vom Modell, nicht von Ihnen. |
| `compare.same_run` | Choisissez deux exécutions différentes. | Choose two different runs. | Wählen Sie zwei verschiedene Läufe. |
| `compare.col.case` | Cas | Case | Fall |
| `compare.col.change` | Changement | Change | Änderung |
| `compare.change.regressed` | régressé | regressed | verschlechtert |
| `compare.change.fixed` | corrigé | fixed | behoben |
| `compare.change.unchanged` | inchangé | unchanged | unverändert |
| `compare.change.absent_a` | absent de A | missing from A | fehlt in A |
| `compare.change.absent_b` | absent de B | missing from B | fehlt in B |
| `compare.missing` | — | — | — |
| `clear` | Effacer mes cas | Clear my cases | Meine Fälle löschen |
| `clear_confirm.one` | Effacer le cas de séance ? Les cas fournis restent. | Clear the session case? The provided cases stay. | Den Sitzungsfall löschen? Die mitgelieferten Fälle bleiben. |
| `clear_confirm.other` | Effacer les {count} cas de séance ? Les cas fournis restent. | Clear the {count} session cases? The provided cases stay. | Die {count} Sitzungsfälle löschen? Die mitgelieferten Fälle bleiben. |
| `clear_confirm.yes` | Effacer | Clear | Löschen |
| `clear_confirm.no` | Annuler | Cancel | Abbrechen |
| `error.no_answer` | WaveStack ne répond pas : la vue n'a pas pu être mise à jour. | WaveStack is not responding: the view could not be updated. | WaveStack antwortet nicht: Die Ansicht konnte nicht aktualisiert werden. |

### Backend : `messages.yaml`

Fichiers : `content/messages.yaml` et ses deux surcouches. Les clés vont **à la fin** du bloc `agent_eval:` de la story 1, après `turn_completed`. La story 3 place son bloc `agent_case:` avant, ce qui évite les conflits. `session.state.agent_eval` va dans `session.state`, après `mcp_lab`.

| Clé | fr | en | de |
|---|---|---|---|
| `session.state.agent_eval` | Évaluation de l'agent en cours : attendez sa fin ou arrêtez-la. | Agent evaluation in progress: wait for it to end or stop it. | Agentenbewertung läuft: Warten Sie das Ende ab oder stoppen Sie sie. |
| `agent_eval.refused.running` | (même texte que `session.state.agent_eval`) | (same) | (gleich) |
| `agent_eval.refused.unknown_case` | Ce cas n'existe pas ou plus. | This case does not exist (any more). | Diesen Fall gibt es nicht (mehr). |
| `agent_eval.refused.provided_case` | Un cas fourni ne se supprime pas. | A provided case cannot be deleted. | Ein mitgelieferter Fall lässt sich nicht löschen. |
| `agent_eval.refused.k_suite` | Trois essais se lancent sur un cas, jamais sur la suite. | Three tries run on one case, never on the suite. | Drei Versuche laufen auf einem Fall, nie auf der Suite. |
| `agent_eval.refused.no_case` | Aucun cas à lancer. | No case to run. | Kein Fall zum Starten. |
| `agent_eval.refused.unreadable` | Le fichier de vos cas est illisible : effacez-le avec « Effacer mes cas ». | The file with your cases is unreadable: clear it with “Clear my cases”. | Die Datei mit Ihren Fällen ist nicht lesbar: Leeren Sie sie mit „Meine Fälle löschen“. |
| `agent_eval.refused.unknown_run` | Cette exécution n'est plus en mémoire. | This run is no longer in memory. | Dieser Lauf ist nicht mehr im Speicher. |
| `agent_eval.refused.unknown_trial` | Cet essai n'existe pas. | This try does not exist. | Diesen Versuch gibt es nicht. |
| `agent_eval.refused.same_run` | Choisissez deux exécutions différentes. | Choose two different runs. | Wählen Sie zwei verschiedene Läufe. |
| `agent_eval.not_run.window` | demande une fenêtre de {window} tokens (fenêtre courante : {current}) | needs a {window}-token window (current window: {current}) | verlangt ein Fenster von {window} Tokens (aktuelles Fenster: {current}) |
| `agent_eval.not_run.cancelled` | arrêté | stopped | gestoppt |
| `agent_eval.not_run.budget` | plafond de dépense atteint ({cap}) | spending cap reached ({cap}) | Ausgabengrenze erreicht ({cap}) |
| `agent_eval.trace.message` | Message : « {text} » | Message: “{text}” | Nachricht: „{text}“ |
| `agent_eval.trace.compaction` | Compaction : résumé de l'historique | Compaction: summary of the history | Verdichtung: Zusammenfassung des Verlaufs |
| `agent_eval.trace.model_call` | Appel au modèle {n} | Model call {n} | Modellaufruf {n} |
| `agent_eval.trace.tool` | Outil {tool}({arguments}) : {status} | Tool {tool}({arguments}): {status} | Werkzeug {tool}({arguments}): {status} |
| `agent_eval.trace.hook` | Hook {hook} · {point} : {decision} | Hook {hook} · {point}: {decision} | Hook {hook} · {point}: {decision} |
| `agent_eval.trace.approval` | Validation : {decision} par le harnais (exécution d'un cas) | Approval: {decision} by the harness (case run) | Freigabe: {decision} durch den Harness (Fall-Lauf) |
| `agent_eval.trace.subagent_started` | Sous-agent lancé : « {task} » | Sub-agent started: “{task}” | Subagent gestartet: „{task}“ |
| `agent_eval.trace.subagent_ended` | Sous-agent fini : {status} | Sub-agent ended: {status} | Subagent beendet: {status} |
| `agent_eval.trace.compacted` | Historique réduit : {strategy} | History reduced: {strategy} | Verlauf gekürzt: {strategy} |
| `agent_eval.trace.limit` | Limite atteinte : {limit} | Limit reached: {limit} | Grenze erreicht: {limit} |
| `agent_eval.trace.error` | Erreur du harnais : {message} | Harness error: {message} | Harness-Fehler: {message} |
| `agent_eval.trace.ended` | Fin du tour : {status} | End of turn: {status} | Ende des Turns: {status} |
| `agent_eval.trace.answer` | Réponse : « {text} » | Answer: “{text}” | Antwort: „{text}“ |
| `agent_eval.trace.sub` | Sous-agent · {text} | Sub-agent · {text} | Subagent · {text} |

Les libellés `{status}`, `{decision}`, `{limit}`, `{strategy}` et `{point}` réutilisent ceux du journal qui existent déjà dans `messages.yaml` (statuts de tour, `limits`, `approval_figures`, points de hook). Le dev ne crée une clé que si aucune n'existe.

## Reprise de `tools/eval/case_player.py` (story 2)

- `case_player.play_case` est **supprimé**. Ses règles passent dans l'exécuteur : configuration, historique, réponse H5, `on_overflow` et filtrage des tours. La seule différence voulue est `_apply_case`, qui ne passe plus par `reset()` (pas de restauration de la mémoire, pas de `harness_reset`).
- `tools/eval/measure_cases.py` passe par `session.agent_eval.start([case_id], k=3)`, puis `wait(run_id)`, et lit `model_calls` dans chaque `TrialOutcome`. `--runs` accepte seulement 1 ou 3 (constraint de la SPEC : k ∈ {1, 3}). Un cas `not_run` (`window`) reste « non mesurable ici ». `README.md` est mis à jour.
- `tests/test_agent_cases_provided.py` : les tests 5 à 7 (réussit, échoue, plafonds tenus) passent par `start([case_id], k=1)` puis `wait`, et lisent `trials[0].verdict`. Les attentes restent les mêmes. Le test 9 (outil) n'est pas modifié, sauf l'appel.
- `git grep case_player` ne doit plus rien renvoyer, hors des specs.

## Tests

Les tests utilisent le faux moteur (`booted_session`, `FakeEngine`) et `WAVESTACK_DATA_DIR` sous `tmp_path`. Les cas de séance sont écrits par `store.write_session_cases` dans ce dossier : un vrai fichier, aucun mock. Les cas sont lancés par `start([ids], k)` pour une liste exacte. Le registre de dépense (`cloud_base._spend`) est remis à zéro entre les tests par la fixture existante (sinon, une fixture `autouse` du module la crée).

### `tests/test_agent_eval_runner.py` (session)

1. **Suite séquentielle.** Trois cas :
   - A, scripté pour réussir (`call("get_datetime")`, puis une réponse) : `passed` ;
   - B, `answer_contains "Pascal"` sur une réponse neutre : `failed`, avec `failing.kind == "answer_contains"` et la `reason_text` exacte ;
   - C, `window: 8192` sur une session en 4 096 : `not_run`, `window`, avec la raison exacte (« demande une fenêtre de 8 192 tokens (fenêtre courante : 4 096) »).

   On vérifie aussi :
   - **aucun rechargement** : la fabrique de moteur, enveloppée d'un compteur, n'est appelée qu'au `boot` ; aucun `session_state` `model_load` depuis le repère ; `_window_state()["configured"]` inchangé ;
   - agrégats `passed == 1`, `ran == 2`, `not_run == 1` ;
   - les tours, dans l'ordre A puis B ;
   - l'état `agent_eval` entre deux cas, puis `idle` à la fin.
2. **Arrêt en cours de suite.** `FakeEngine(gate=Event)` retient le deuxième cas. `stop()` renvoie `True`, puis on relâche la porte. Le cas 1 a son verdict ; les cas 2 et 3 sont `not_run` (`cancelled`), le cas 2 avec `has_trace` vrai et son `turn_ended` `cancelled`. `run.status == "cancelled"`, l'état est `idle` et la configuration rétablie.
3. **Arrêt entre deux cas.** Le `stop()` est appelé dans l'état `agent_eval`, synchronisé par un abonné au journal sur le `session_state` `agent_eval` qui suit le premier tour. Le cas suivant n'est pas lancé (aucun `turn_started` de plus).
4. **Plafond `max_session_usd` atteint.**
   - (a) `values={"finops": {"max_session_usd": 0.01}}`. La porte retient le cas 1 pendant que le test ajoute 0,02 $ par `record_spend(CallCost(...))`, l'API publique du registre, pour en poser l'état et non pour le remplacer. Le cas 1 garde son verdict. Les cas 2 et 3 sont `not_run` (`budget`), avec la raison et le plafond formaté. `run.status == "budget"`, et le faux moteur n'a reçu aucun appel après le cas 1.
   - (b) Plafond déjà atteint au lancement : tous les cas `not_run` (`budget`), zéro appel au moteur.
5. **H5 refusé par le harnais.** Cas `hooks: [h5]`, `tools: [public_holidays]`, `approval: refuse`, moteur `[call("public_holidays", year="2026"), "Je n'ai pas pu vérifier."]`. On attend :
   - `passed` (`hook_decided h5 ask_human`, `tool_not_called public_holidays`) ;
   - un `approval_resolved` `refused` dans les enveloppes de l'essai, et aucune réponse du test ;
   - un passage par `awaiting_human`, puis le retour à `agent_eval`, puis à `idle` ;
   - aucun `tool_started public_holidays` (rien n'est parti sur le réseau).
6. **`on_overflow`.** Session en 4 096, historique qui déborde (le remplissage du cas `code_talvane_apres_compaction` de la story 2) :
   - `compaction` avec `["Résumé : … TLV-7731-QZ.", "… TLV-7731-QZ."]` donne `passed`, trois `turn_ids` (O, C, T) qui portent tous `case_id` et `run_id`, et un `model_calls` de 2 ;
   - `sliding_window` donne deux `turn_ids` (O, T) ;
   - `none` donne `failed`, raison « tour incomplet (fini en « overflow ») ».
7. **Configuration rétablie.** Avant l'exécution : briques `[short_memory, system_prompt, tools]`, `get_datetime` coupé, H5 allumé, prompt système personnalisé, une entrée de mémoire globale ajoutée, un scénario actif, deux échanges dans la conversation. Après l'exécution (un cas qui allume `hooks` et `global_memory`) :
   - `_wanted`, outils, hooks, compétences, serveurs MCP, `_mcp_lazy`, `_rag_rerank`, `_custom_prompt` et `_active_scenario` égaux à l'instantané ;
   - dernier `bricks_changed` égal à celui d'avant ;
   - `_history == []`, `_last is None` ;
   - mémoire globale inchangée (pas de restauration de la démonstration), aucun `harness_reset` dans le journal depuis le repère ;
   - l'exécution s'est faite avec la configuration du cas : le `bricks_changed` émis avant le tour du cas montre `hooks` voulu.
8. **Prompt système.** Un cas sans `system_prompt` : le prompt rendu au moteur contient le texte personnalisé de la session. Un cas avec `system_prompt` figé : il contient le texte figé. Dans les deux cas, `run.system_prompt` est celui de la session.
9. **Résultats gardés après `reset()`.** Après une exécution, `reset()` :
   - `state()["runs"]` est identique ;
   - `trace(run_id, case_id, 1)` répond toujours ;
   - `agent_cases.json` est intact.
10. **Refus pendant une exécution** (porte fermée) : `send`, `launch_scenario`, `reset`, `set_context_window`, `compact` et un second `start` lèvent `SendRefused`, avec le texte de `agent_eval.refused.running` en fr. `delete_case` et `clear_cases` lèvent aussi `SendRefused`. `start(None, k=3)` lève `ValueError`.
11. **Étiquettes du tour** : `case_id` et `run_id` dans le `turn_started` des tours de cas, absents d'un tour envoyé avant et après l'exécution.
12. **k = 3.** Les trois essais partagent le même moteur : on lui donne des sorties enchaînées qui font réussir l'essai 1, échouer le 2 et réussir le 3. `successes == 2`, `ran == 3`, `pass_at_k is True`, `pass_pow_k is False`, statut `passed`.
13. **Bornes de boucle.** `values={"tools": {"max_calls": 2}}` et un moteur qui rappelle l'outil sans fin. Le cas 1 est `failed`, raison « tour incomplet (fini en « limit ») ». Le cas 2 est lancé ensuite et réussit.
14. **Exception dans l'exécuteur** : un cas dont `_apply_case` lève (serveur MCP inconnu de la session si les ids inconnus lèvent, sinon un `prompt` refusé par un garde-fou), selon ce que le dev retient au point ouvert 1. `run.status == "error"`, les cas restants sont `not_run` (`cancelled`), l'état final est `idle` et la configuration est rétablie.

### `tests/test_agent_eval_runs.py` (pur, journaux construits)

- `classify_trial` : `passed` et `failed` selon `verify` ; arrêt demandé donne `not_run`/`cancelled` ; un `harness_error` de cause `max_session_usd` donne `not_run`/`budget`.
- Statut d'un cas pour k = 3 : 3/3, 2/3 et 1/3 lancés, 1/2 lancé après un arrêt (`failed`), 0 lancé (`not_run`).
- pass@k et pass^k, avec toutes leurs bornes : un premier succès donne `pass_at_k` vrai même si le reste est arrêté ; un premier échec donne `pass_pow_k` faux ; un arrêt avant de conclure donne `None`.
- Agrégats d'une exécution : réussis, lancés, non lancés comptés à part.
- `compare_runs` : les quatre changements, `absent_from` des deux côtés, `not_run` lu comme absent, ordre des lignes, `differs` (modèle seul, prompt seul, les deux), `control` vrai sans différence.
- `trace_items` : un élément par type d'enveloppe du tableau ; numérotation des appels au modèle sous-agent compris ; préfixe `sub` ; élément fautif pour `model_calls_max` (le `model_call_started` n° plafond + 1), pour `argument_never` (le `tool_started`), pour une absence (la fin de tour) et pour un témoin absent (le dernier élément) ; aucun élément fautif sur un essai réussi ; arguments coupés à 80 caractères.

### `tests/test_agent_eval_api.py` (`TestClient`)

- `GET /cases` : les fournis et les cas de séance ; un fichier illisible donne `session_error: "unreadable"`, avec les fournis présents.
- `DELETE /cases/{id}` : un cas de séance donne 200 et disparaît du fichier ; un id fourni donne 409 `provided_case` ; un id inconnu donne 404.
- `DELETE /cases` : 200, `cleared` égal au nombre de cas ; les cas fournis restent listés ; un fichier illisible est remis à zéro.
- `POST /runs` : 202, puis `GET /state` jusqu'à `current == null`, puis `GET /runs/{id}` complet. `{case_id: null, k: 3}` donne 422 `k_suite` ; `k: 2` donne 422 ; un cas inconnu donne 404 ; un champ en trop donne 422.
- **Garde** : pendant une exécution (porte fermée), les intentions de classe (a) et (b) sont refusées en 409 avec le texte de `refused.running`, dans la langue de la session :
  - `POST /api/intentions/send` ;
  - un `POST` de brique (classe a) ;
  - `DELETE /api/agent_eval/cases`.

  En revanche, `POST /api/intentions/stop` est accepté et arrête l'exécution, et `GET /api/agent_eval/state` répond 200.
- `GET /runs/{id}/trace` : 200 avec un élément `fault` ; essai inconnu donne 404.
- `GET /compare` : 200 ; une exécution inconnue donne 404 ; `a == b` donne 422.
- **Parité i18n** : le test de miroir existant couvre `main.agent_eval.*` et les nouvelles clés `agent_eval.*` et `session.state.agent_eval` (mêmes clés et mêmes variables en en et de). Un test vérifie les formes `.one`/`.other`.

### Réalignement

`git grep` sur :
- `SessionState`, ses valeurs et `"mcp_lab"` dans `tests/` et `web/static/` (listes d'états) ;
- les clés de `TurnStartedPayload` (tests qui comparent un payload `turn_started` entier) ;
- les routes de `create_app` ;
- `case_player`.

Les tests et scénarios trouvés sont réalignés dans le même commit.

### E2E

Le scénario `agent_eval` s'ajoute **en dernier** dans `SCENARIOS` de `tools/e2e/run_e2e.py`, après `glossary` et les ajouts des autres stories. Sa fonction `s_agent_eval` va en fin de fichier, avec une ligne dans `tools/e2e/README.md`. Il tourne avec le faux llama-server (`fake_local_server.py`) et Edge, et suit `vues.md` :

1. **Du formulaire à la vue** :
   - un tour « Quelle heure est-il ? » fait appeler `get_datetime` ;
   - « En faire un cas », `tool_not_called get_datetime`, enregistrer ;
   - « Ouvrir Évaluer l'agent » ouvre la vue, et le cas est dans « Mes cas ». C'est l'étape laissée par la story 3.
2. Ouvrir et fermer la vue par le bouton de la barre du haut (`aria-pressed`) ; la Vue humain reste visible.
3. **Lancer la suite** : l'avertissement du premier lancement apparaît, puis « Lancer ». La barre « Cas n sur N » apparaît, et le compositeur est désactivé avec la raison. En fin d'exécution, on vérifie :
   - au moins un « Réussi » (`heure_get_datetime`, que le faux serveur fait appeler `get_datetime`) ;
   - au moins un « Échoué » (le cas de séance de l'étape 1, et les cas que le faux serveur ne sait pas jouer) ;
   - un « Non lancé » pour la fenêtre (`code_talvane_apres_compaction`, qui demande 4 096 : l'E2E règle d'abord la fenêtre configurée sur une autre valeur si le défaut de l'E2E est 4 096 ; le dev vérifie) ;
   - les badges « Cas : … » dans la Vue humain.
4. « Voir le tour » sur l'échec : la trace se déplie, avec un élément `fault`.
5. Sur `heure_get_datetime`, « 3 essais » : trois ronds et « 3 réussis sur 3 · pass@3 : oui · pass^3 : oui ».
6. Changer le prompt système (tiroir existant), relancer la suite, puis comparer A et B : « Diffère : prompt système. » et au moins une ligne avec un changement. Comparer ensuite deux exécutions sans changement : la ligne de rejeu témoin.
7. **Arrêter** : lancer la suite puis cliquer « Arrêter ». Les cas restants sont « Non lancé » avec « arrêté », et l'exécution est marquée « arrêtée ». Pour que l'arrêt soit déterministe, le dev retient une réponse du faux serveur (une route de debug à ajouter si besoin, comme la porte du faux moteur) ou s'appuie sur un délai mesuré ; il ne compte pas sur la chance.
8. La configuration est rétablie : le tiroir du prompt système montre toujours le texte modifié à l'étape 6, et les briques sont celles d'avant l'exécution.
9. « Effacer mes cas » demande la confirmation dans la page, puis « Mes cas » se vide. Les cas fournis restent, et `agent_cases.json` vaut `{"version": 1, "cases": []}`. Les exécutions passées restent listées.
10. En anglais, puis en allemand : titre de la vue, bandeau et statuts traduits.
11. Capture `agent-eval`.

## Fichiers

Nouveaux :
- `src/wavestack/agent_eval/runs.py`
- `src/wavestack/session/agent_eval_runner.py`
- `src/wavestack/web/agent_eval_api.py`
- `src/wavestack/web/static/agent-eval.js`
- `src/wavestack/web/static/agent-eval.css`
- `tests/test_agent_eval_runner.py`, `tests/test_agent_eval_runs.py`, `tests/test_agent_eval_api.py`

Supprimé : `tools/eval/case_player.py`.

Modifiés. Les fichiers partagés avec la story 3 sont en **gras**, avec leur point d'insertion :
- **`src/wavestack/web/app.py`** : l'import, et la ligne `register_agent_eval_routes(app, app_session)` **juste après** la ligne `register_agent_case_routes(...)` de la story 3 (elle-même après `/api/intentions/compact`). Rien d'autre : le garde est installé par cette fonction.
- **`src/wavestack/web/static/app.js`**, une dizaine de lignes :
  - l'import d'`./agent-eval.js` **juste après** celui d'`./agent-case-form.js` ;
  - `sessionStateChanged(state)` dans le traitement de `session_state` ;
  - `state?.state !== "agent_eval"` dans la condition `stop.hidden` (vers la l. 3804) ;
  - `caseBadge(...)` à la création de la bulle d'un `turn_started`.
- **`content/ui.yaml`**, **`content/i18n/en/ui.yaml`**, **`content/i18n/de/ui.yaml`** : le bloc `main.agent_eval` **après** `main.agent_case`.
- **`content/messages.yaml`** et ses deux surcouches :
  - les clés de la story 4 **à la fin** du bloc `agent_eval:`, après `turn_completed` (la story 3 met `agent_case:` avant `agent_eval:`) ;
  - `session.state.agent_eval`, après `session.state.mcp_lab`.
- **`tools/e2e/run_e2e.py`** : le scénario en dernier dans `SCENARIOS` et la fonction en fin de fichier ; une ligne dans `tools/e2e/README.md`.
- `src/wavestack/web/static/index.html` : le bouton `#agent-eval-toggle` (`data-i18n="main.agent_eval.toggle"`) dans `header.top-bar`, juste avant `#pane-chips`. La story 3 ne touche pas ce fichier.
- `src/wavestack/session/app_session.py` : les onze points d'accroche ci-dessus, et l'extraction de `_finops_capped()`.
- `src/wavestack/trace/catalog.py` : `SessionState` (`"agent_eval"`) et `TurnStartedPayload` (`case_id`, `run_id`).
- `tools/eval/measure_cases.py`, `tools/eval/README.md`, `tests/test_agent_cases_provided.py` (passage par l'exécuteur).

Non modifiés : `agent_eval/cases.py`, `checks.py`, `store.py`, `draft.py`, `agent_case_api.py`, `agent-case-form.js` et `.css`, `contrat-des-cas.md`.

## Points ouverts

1. **Id inconnu dans un cas de séance** : une compétence supprimée, un serveur MCP retiré de la configuration. Par défaut, `_apply_case` ignore l'id et le cas se joue sans lui. Le contrat n'a pas de raison `not_run` pour ce cas, et en ajouter une changerait le contrat. *À trancher par Anaël* : ignorer en silence (défaut), ou ajouter `not_run` (`config`) au contrat.
2. **Statut d'un cas à 3 essais** : la majorité stricte (2 sur 3 donne « Réussi ») suit la maquette. On pourrait aussi retenir pass^3 (strict) ou pass@3 (indulgent). Ce choix décide de ce que la comparaison montre pour une exécution à 3 essais. *À revoir par Anaël.*
3. **Un cas interrompu par « Arrêter »** est `not_run` (`cancelled`) plutôt que `failed`, avec sa trace consultable. Une coupure du formateur n'est pas une faute de l'agent.
4. **Plafond atteint en cours de cas** (appel cloud refusé, `cause == "max_session_usd"`) : l'essai est `not_run` (`budget`) et l'exécution s'arrête. Ce n'est pas testé avec le faux moteur (local, sans prix) : seule la fonction pure `classify_trial` l'est.
5. **`approval: approve`** n'a pas de test de session : H5 ne vise que des outils réseau, et accepter enverrait une requête. Il est couvert par le test pur du formulaire (story 3) et par la réponse de l'exécuteur (`approved=True`), lue dans un journal construit si le dev trouve un outil réseau factice existant. Sinon, c'est un report.
6. **Mémoire globale pendant une exécution** : elle n'est ni restaurée ni figée. Un cas qui la ferait écrire (outil de mémoire, s'il existe) la modifierait pour la suite de la séance. Aucun cas fourni ne le fait.
7. **Rechargement après architecture refusée (E119)** : il est désactivé pendant une exécution. Le cas échoue, et le rechargement n'est pas proposé à la fin. Ce cas est rare : un modèle qui refuse son architecture au premier tour.
8. **Pas de flux ni d'événement de journal pour l'exécution** (début, fin, cas courant) : la progression passe par `GET /state` toutes les secondes. Un événement `agent_eval_run_*` rendrait l'exécution visible dans l'Orchestration, mais changerait le catalogue. C'est un report possible.
9. **Panneau sur deux volets** : le dev choisit entre l'API de `panes.js` et une règle CSS. Si `panes.js` doit changer, c'est signalé dans le rapport, et le changement reste minimal.
10. **Ordre de développement** : la story 4 suppose les stories 2 et 3 fusionnées : cas fournis, `registerOpenView`, `onCaseSaved`, les clés `main.agent_case.form.checks.kind.*` et `case_player.py` à supprimer. Sinon, le dev rebase sur leurs branches et le dit dans son rapport.
11. **Garde HTTP par middleware** : c'est un motif nouveau dans `web/`. Il refuse aussi les intentions des autres pages (Modèles, ateliers) pendant une exécution, ce qui est voulu, puisqu'il n'y a jamais de rechargement. La liste blanche se limite à `POST /api/intentions/stop`.
