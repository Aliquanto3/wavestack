---
title: 'V1.5 story 3 : « En faire un cas » depuis un tour'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: ''
review_loop_iteration: 0
context: ['_bmad-output/specs/spec-wavestack-evaluer-l-agent/SPEC.md', '_bmad-output/specs/spec-wavestack-evaluer-l-agent/vues.md', '_bmad-output/specs/spec-wavestack-evaluer-l-agent/contrat-des-cas.md']
---

## Intent

CAP-3 de la V1.5. Sur un tour terminé de la Vue humain, « En faire un cas » ouvre un tiroir pré-rempli depuis le journal : prompt, configuration, historique, outils appelés. Le formateur nomme le symptôme et l'assertion, puis choisit une ou deux vérifications. Le serveur rejoue `verify` sur le tour d'origine, sans appel au modèle, et dit si le cas échoue bien sur ce tour. L'enregistrement écrit un cas de séance (`agent_cases.json`, provenance `séance`), qui survit à `reset()`.

Base : la branche part de `origin/main` **après la fusion de la story 1** (PR #137, `feat/v1-5-story-1-contrat-des-cas`). Au démarrage du dev, rebaser sur `origin/main` ; si #137 n'est pas encore fusionnée, rebaser sur sa branche et le dire dans le rapport. La story 1 fournit `AgentCase`, `Provenance`, `Check`, `POSITIVE_KINDS`, `new_case_id`, `load_provided_cases(lang, known)`, `checks.verify(case, envelopes, lang)` et `store.*`. Cette story ne les recrée pas et n'étend pas le contrat (pas de `mcp_lazy`, pas de `rag_rerank`). Disposition : maquette, section 1. Comportement : `vues.md`.

## Décisions

- **Le serveur calcule le brouillon et le verdict** à partir du journal. Le client n'envoie que ses saisies. La provenance (modèle, `turn_id`, date, prompt système du tour) vient toujours du journal, jamais du corps de la requête.
- **Fichiers propres à la story 3**, pour que la story 4 n'ait pas à les toucher :
  - routes : `web/agent_case_api.py`, avec `register_agent_case_routes(app, app_session)`, appelé d'une ligne dans `create_app` ;
  - front : `web/static/agent-case-form.js` ;
  - styles : `web/static/agent-case-form.css` ;
  - textes : `main.agent_case.*` et `agent_case.*`.

  La story 4 a ses propres fichiers (`web/agent_eval_api.py`, `agent-eval.js`, `main.agent_eval.*`). L'invoke de `stories.yaml` disait « routes dans web/app.py » : on s'en écarte volontairement, parce que `app.py` dépasse 1 600 lignes et qu'il est partagé.
- **Tour éligible** : `turn_started.kind == "message"` dans le contexte principal, sans `case_id` dans son payload (champ ajouté par la story 4 aux tours d'exécution ; ici, simple lecture de `payload.get("case_id")`), avec un `turn_ended` du contexte principal, **quel que soit son statut**. Un tour `cancelled`, `limit`, `error`, `overflow` ou `blocked` est précisément un tour raté. Le formulaire le prend, en prévenant que le verdict sur ce tour sera « tour incomplet » (voir « Tour non abouti »). Refus : `unknown_turn` (404), `not_a_message`, `case_turn`, `unfinished` (409). *À revoir par Anaël :* le tour annulé, refusé dans la première version de la spec, est désormais accepté, par cohérence avec le contrat final, qui traite tous les statuts autres que `completed` de la même façon.
- **Pas de règle de vérification positive** pour un cas de séance : `POSITIVE_KINDS` ne vaut que pour les cas fournis (`load_provided_cases`). Un cas avec seulement `tool_not_called` s'enregistre.
- **Pas de nouvelle clé de contrat.** `approval` et `on_overflow` sont déduits du journal et modifiables (voir plus bas). `mcp_lazy` et le reclassement RAG ne sont pas repris : le formulaire le signale.

## Reconstitution du brouillon

Module `src/wavestack/agent_eval/draft.py`, **pur** : aucune I/O, aucun accès au `Journal`. Il lit la liste d'enveloppes reçue, comme `verify`.

```
reconstitute_draft(envelopes: Sequence[Envelope], turn_id: str) -> CaseDraft
class DraftRefused(Exception): reason: Literal["unknown_turn", "not_a_message", "case_turn", "unfinished"]
to_case(draft, form, case_id: str) -> AgentCase
```

C'est une fonction du `seq` du `turn_started` d'origine (`S`). La configuration et l'historique ne lisent que les enveloppes de `seq < S`. Les outils, les appels et la réponse lisent les enveloppes des tours de `verdict_turn_ids`. Test : ajouter, à la fin du journal, des enveloppes de `seq` supérieur à la fin de ces tours ne change pas le brouillon. Le brouillon se calcule en un seul parcours du journal, trié par `seq` : `/verdict` le recalcule à chaque saisie, et le journal contient des milliers de `model_delta`.

`CaseDraft` (pydantic, `extra="forbid"`, renvoyé tel quel par la route) :

| Champ | Source dans le journal |
|---|---|
| `turn_id`, `seq`, `date` | `turn_started` (`seq`, `ts` en ISO) |
| `origin_status` | `turn_ended.status` du tour d'origine (`TurnStatus`) |
| `model` (`ActiveModel` \| None) | `turn_started.active_model` |
| `prompt` | `turn_started.message` |
| `bricks` (ids des briques voulues) | dernier `bricks_changed` de `seq < S` : cartes avec `wanted` |
| `tools`, `hooks`, `skills`, `mcp_servers` | même événement : ids des `options` avec `enabled`, des cartes `tools`, `hooks`, `skills`, `mcp` |
| `not_kept` : liste de `mcp_lazy` \| `rag_rerank` | même événement : carte `mcp` en `mode == "lazy"`, carte `rag` avec `rerank.enabled` (seulement si la brique est voulue) |
| `window` (int \| None) | dernier `context_window_state` de `seq < S` : `configured` si `hosting` vaut `file` ou `server`, sinon `None`. Pour un modèle cloud, la fenêtre est déclarée, pas choisie : le cas ne l'exige pas. |
| `system_prompt` : `{text, is_default}` | même `bricks_changed` : `system_prompt` |
| `history` : liste de `{user, assistant}`, `history_available`, `history_note` | voir « Historique » |
| `approval` (`refuse` \| `approve`) | voir « Validation et débordement » |
| `on_overflow` (`none` \| `compaction` \| `sliding_window`), `verdict_turn_ids` | voir « Validation et débordement » |
| `tool_calls` : liste de `{seq, tool, arguments, status, context_id}` | `tool_started` des tours de `verdict_turn_ids` (tous contextes) ; `status` lu dans le `tool_ended` de même `call_id` (`None` si absent) |
| `hooks_decided` : liste de `{hook, decision}` | `hook_decided` des mêmes tours |
| `subagent_called` (bool) | au moins un `subagent_started` |
| `model_calls` (int) | `model_call_started` des mêmes tours, tous contextes (le même compte que `verify`) |
| `answer_text` | réponse finale, même règle que `verify` : `turn_ended.text` s'il est présent, sinon les `model_delta` de canal `text` du dernier appel principal. Réutiliser `checks._Journal(...).answer()` (même paquet), sans réécrire la règle. |
| `suggested_max_model_calls` | `max(1, model_calls)` |

**Historique à `S`.** On parcourt les enveloppes de `seq < S` en tenant l'historique courant, et un instantané de l'historique avant chaque tour de message (dictionnaire `turn_id → tuple`, pour les rejeux) :
- l'historique repart de vide à chaque `conversation_cleared` et à chaque `harness_reset` ;
- un tour principal de `kind == "message"` terminé `completed` ajoute `{user: message, assistant: réponse}`. La réponse suit la règle d'`answer_text` : **`turn_ended.text` n'est présent que si la sortie a été retenue**, il ne faut donc pas exiger sa présence. Un tour d'un autre statut n'entre pas, comme dans la session ;
- un tour avec `replay_of = X` part de l'instantané d'avant `X` (AD-17), puis s'ajoute ;
- `history_compacted` reproduit `_history_compacted` de la session : il retire les échanges dont le `turn_id` est dans `removed_turn_ids`. Pour la stratégie `compaction`, il met en tête `{user: <message du turn_started du tour de compaction (enveloppe de même turn_id)>, assistant: summary_text}`. C'est ce que la session envoie au modèle : seule l'étiquette « Résumé » de la vue Contexte diffère.
- `history_available` vaut faux seulement si la reconstitution est impossible : un tour `completed` dont la réponse est introuvable, ou une compaction dont le tour ou le `summary_text` manque. Dans ce cas, `history = []` et `history_note = "unavailable"`. Sinon `history_note = "compacted"` si une stratégie a touché l'historique depuis le dernier effacement, et `None` en l'absence de stratégie. La note s'affiche sous la case (texte `form.history.compacted`).
- Limite connue, commune à tous les cas : un échange du contrat ne porte que `user` et `assistant`. Les étapes intermédiaires (appels d'outils et résultats des tours passés) ne sont pas reprises.

**Validation et débordement.**
- `approval` vaut `approve` si un `approval_resolved` des tours de `verdict_turn_ids` a la décision `approved`, et `refuse` sinon (pas de validation, refus ou annulation).
- **Tour renvoyé après un débordement** : le tour principal de message qui précède `T` s'appelle `O`. Si `O` a fini en `overflow` avec le même `message`, et si un `history_compacted` se trouve entre le `turn_ended` de `O` et le `turn_started` de `T`, alors :
  - `on_overflow` prend la `strategy` de ce `history_compacted` ;
  - `verdict_turn_ids` contient `O`, le tour de compaction s'il y en a un, et `T` (les tours que l'exécution du cas produira, au sens de `contrat-des-cas.md`) ;
  - l'historique du brouillon est l'**instantané d'avant `O`**, avant la stratégie : le cas doit redéborder pour rejouer la stratégie.
  Sinon, `on_overflow` vaut `none` et `verdict_turn_ids` vaut `[T]`.
- Le formulaire montre les deux valeurs dans deux sélecteurs, pré-remplis par la déduction. Le formateur peut, par exemple, choisir `compaction` sur un tour fini en `overflow`.

**Mapping vers `AgentCase`** (`to_case`, pur aussi) :
- `id = case_id` (injecté : `new_case_id()` en production, `"draft"` pour `/verdict`) ;
- `prompt = form.prompt` ;
- `history = draft.history` si `form.include_history` et `history_available`, sinon `[]` ;
- `system_prompt = draft.system_prompt.text` si `form.freeze_system_prompt`, sinon `None` ;
- `window`, `bricks`, `tools`, `hooks`, `skills` et `mcp_servers` viennent du brouillon ;
- `approval` et `on_overflow` viennent du formulaire ;
- `max_model_calls` et `checks` viennent du formulaire ;
- `provenance = {source: "séance", date: draft.date, model, turn_id, system_prompt_text: draft.system_prompt.text, fixed_in: None}`.

## Routes

Toutes les routes sont sous `/api/agent_eval/`, dans `web/agent_case_api.py`. La story 4 garde le même préfixe dans son propre module : `GET /cases`, `DELETE /cases`, exécutions. Erreurs : `{"detail": <texte dans la langue de la session>}`, comme les autres intentions.

| Route | Entrée | Réponse |
|---|---|---|
| `GET /draft?turn_id=t4` | requête | 200 `CaseDraft` ; 404 `unknown_turn` ; 409 pour les autres `DraftRefused` (texte de la raison) |
| `POST /verdict` | `CaseForm` | 200 `FormVerdict` ; 404/409 comme `/draft` ; 422 `{detail: [{field, message_text}]}` si une vérification est incomplète ou si le nombre de vérifications ou le plafond est hors bornes |
| `POST /cases` | `CaseForm` | 201 `{case: AgentCase}` ; 404/409 comme `/draft` ; 422 `{detail: [{field, message_text}]}` (titre, symptôme, assertion, prompt vides, vérification incomplète, 1 à 2 vérifications, plafond ≥ 1) ; 409 si le fichier de séance est illisible (`SessionCasesUnreadable`), avec `form.error.unreadable` |

```
CaseForm (extra="forbid") = {
  turn_id: str,
  title_text: str, symptom_text: str, assertion_text: str,   # vides tolérés par /verdict
  prompt: str,                                               # modifiable, ignoré par /verdict
  include_history: bool, freeze_system_prompt: bool,
  approval: "refuse" | "approve", on_overflow: "none" | "compaction" | "sliding_window",
  max_model_calls: int,
  checks: list[dict]      # validés un par un contre `Check` dans la route
}
FormVerdict = {
  passed: bool,                    # tous les contrôles, plafond compris, réussissent sur le tour d'origine
  failing: CheckVerdict | None,    # la première vérification qui échoue (reason_text, seq)
  checks: list[CheckVerdict], model_calls: int,
  origin_complete: bool            # origin_status == "completed"
}
```

- `checks` arrive brut, puis la route le valide contre `Check` (`TypeAdapter`). Elle traduit les erreurs en `{field: "checks.<i>.<param>", message_text}` (`form.error.required`), au lieu du 422 générique de FastAPI : un paramètre vide (texte d'`answer_contains`) doit s'afficher sous son champ. Un `kind` inconnu ou `model_calls_max` donne 422 `form.error.checks_kind`. Un corps mal typé ou un champ en trop (`provenance`, par exemple) garde le 422 générique de FastAPI : seul un client trafiqué le reçoit.
- `/verdict` recalcule le brouillon depuis `get_journal().all_events()`, puis construit l'`AgentCase` d'essai (`to_case(..., "draft")`, avec un titre, un symptôme et une assertion de remplacement s'ils sont vides). Il garde les enveloppes dont le `turn_id` est dans `verdict_turn_ids` (tous contextes) et appelle `verify(case, envelopes, session.language)`. Aucun appel au modèle, aucun événement émis, aucun état de session lu en dehors de la langue.
- `/cases` refait la même construction avec `new_case_id()`, puis appelle `store.add_session_case(case, load_provided_cases())` (`[]` tant que `content/agent_cases.yaml` n'existe pas ; `known` non passé). Le verdict ne bloque pas : un cas qui ne peut pas échouer s'enregistre (vues.md).
- Le prompt modifié ne change pas le verdict, qui lit le tour d'origine. `/cases` l'enregistre.

## Formulaire

`web/static/agent-case-form.js`, module ES. Ses styles `ae-*` (tiroir, champs, vérification, verdict, actions) sont ceux de la maquette, dans `web/static/agent-case-form.css`. Le module charge cette feuille lui-même au premier appel (`<link>` ajouté au `<head>`, tiroir affiché au `load`) : **`index.html` n'est pas modifié**. Disposition : tiroir `.ae-drawer` sur le volet de la Vue humain, rôle `dialog`, `aria-modal`. À l'ouverture, le focus va sur le champ titre ; à la fermeture, il revient à l'élément d'ouverture.

**Interface du module** (contrat avec `app.js` et la story 4) :

```js
export function openCaseForm(turnId, opener)   // opener : l'élément qui reçoit le focus à la fermeture
export function closeCaseForm()
export function canMakeCase(turnStarted, turnEnded) // bool : tour principal de message, terminé, sans case_id
export function registerOpenView(fn)            // fn(caseId) : « Ouvrir Évaluer l'agent » ; bouton masqué tant qu'aucune fonction n'est enregistrée
export function onCaseSaved(fn)                 // abonnement : fn(case) après chaque 201 ; renvoie une fonction de désabonnement
```

La story 4 fait, dans `agent-eval.js` : `import { registerOpenView, onCaseSaved } from "./agent-case-form.js"`, puis appelle `registerOpenView(openView)` et `onCaseSaved(refreshMyCases)` au chargement. `agent-case-form.js` n'importe jamais `agent-eval.js`. Pas de `window.agentEval`.

**Entrée.** Dans `app.js`, à côté de « Comparer » (`turn-actions`), un bouton `En faire un cas` par tour où `canMakeCase` est vrai. Le bouton est ajouté quand le `turn_ended` arrive. Modification d'`app.js` : une ligne d'import et la création du bouton, une dizaine de lignes en tout. Rien d'autre.

**Contenu** (ordre de la maquette) :
- titre (champ) ;
- note de tour non abouti, si `origin_status != "completed"` ;
- prompt (zone, modifiable) ;
- configuration en lecture seule : briques, sous-options, fenêtre, modèle, et la ligne `form.config.not_kept` si `not_kept` n'est pas vide ;
- outils appelés, numérotés, avec arguments et statut ;
- case « Reprendre l'historique (N échanges) » : cochée si N > 0 et si `short_memory` est dans `bricks`, absente si `history_available` est faux (note `form.history.unavailable`), note `form.history.compacted` si `history_note == "compacted"` ;
- case « Figer ce prompt système dans le cas » (décochée) ;
- sélecteurs `approval` et `on_overflow` ;
- symptôme ;
- assertion ;
- une ou deux vérifications ;
- plafond d'appels, pré-rempli à `suggested_max_model_calls` ;
- verdict ;
- « Enregistrer » et « Annuler ».

**Vérifications.** Un sélecteur du catalogue (sans `model_calls_max`), puis les paramètres du type choisi, pré-remplis depuis le tour :

| Type | Paramètres du formulaire | Pré-remplissage |
|---|---|---|
| `tool_called` | outil (liste), `before` (liste facultative) | premier outil appelé ; `before` vide |
| `tool_not_called` | outil | premier outil appelé |
| `argument_never` | outil, argument, contient | premier appel : premier argument et sa valeur en texte |
| `answer_contains` | texte | vide |
| `hook_decided` | hook, décision (`block` \| `ask_human`) | première décision vue dans le tour, sinon vide |
| `subagent_called`, `turn_completed` | aucun | |

La liste d'outils propose ceux du tour, puis ceux de la configuration. Première vérification par défaut :
- `turn_completed` si le tour n'a pas abouti ;
- sinon `tool_called` si le tour a appelé un outil ;
- sinon `turn_completed`.

« Ajouter une vérification » disparaît à deux vérifications, « Retirer » à une. Le contrat en admet trois : le formulaire s'en tient aux « une ou deux » de CAP-3, sans changer le contrat.

**Tour non abouti** (`origin_status` autre que `completed`). Une note s'affiche en tête du tiroir (`form.incomplete`) : sur ce tour, toutes les vérifications échouent (« tour incomplet »), donc le verdict ne dit pas si elles ciblent le défaut vu. Le bandeau de verdict reste « échoue bien », avec la raison renvoyée par `verify` (« tour incomplet (fini en « limit ») »). C'est vrai : le tour d'origine échouerait à ce cas. Sans la note, l'information serait trompeuse.

**États.**
1. *Fermé.*
2. *Chargement* : le tiroir s'ouvre avec « Lecture du tour… », saisie désactivée.
3. *Refusé* (404 ou 409 sur `/draft`) : le tiroir se referme, le focus revient au bouton, et le texte du refus s'affiche dans une note sous les actions du tour, comme `replay_refused`.
4. *Prêt, intact* : champs pré-remplis ; « Annuler » ferme sans confirmation.
5. *Modifié* : dès qu'un champ diffère du brouillon, « Annuler » devient une confirmation dans la page (jamais `confirm()`), comme pour le tiroir du prompt système. Elle demande « Abandonner les modifications ? » et propose « Abandonner » et « Continuer ».
6. *Verdict en cours* : `/verdict` est appelé à chaque changement de vérification, de plafond, d'`approval` ou d'`on_overflow`, après 250 ms sans saisie. La dernière réponse l'emporte (compteur de requêtes). L'ancien verdict reste affiché, grisé.
7. *Verdict à compléter* : si une vérification a un paramètre vide, `/verdict` n'est pas appelé (ou son 422 de champ est traité ainsi) et le bandeau affiche `form.verdict.incomplete`.
8. *Verdict « échoue bien »* (`passed` faux) : bandeau `ae-verdict fails`, `role="status"`, avec « Le tour d'origine échoue bien à ce cas. » suivi du `reason_text` de `failing`.
9. *Verdict « ne peut pas échouer »* (`passed` vrai) : bandeau `ae-verdict warns` avec « Ce cas ne peut pas échouer sur ce tour. Il ne détectera pas la défaillance que vous avez vue. » L'enregistrement reste possible.
10. *Verdict indisponible* (réseau ou 5xx) : « WaveStack ne répond pas : le verdict n'a pas pu être calculé. » L'enregistrement reste possible.
11. *Invalide* : « Enregistrer » reste actif. Une tentative d'enregistrement invalide affiche l'erreur sous chaque champ fautif (`message_text` du 422, champ nommé par `field`) et place le focus sur le premier.
12. *Enregistrement* : « Enregistrer » est désactivé et affiche « Enregistrement… ».
13. *Enregistré* : le formulaire est remplacé par « Cas enregistré. », avec « Ouvrir Évaluer l'agent » (visible seulement si `registerOpenView` a été appelé ; ferme le tiroir puis appelle `fn(case.id)`) et « Fermer ». Les abonnés d'`onCaseSaved` sont notifiés.
14. *Fichier illisible* (409 à l'enregistrement) : message d'erreur dans le tiroir, qui reste ouvert et intact.
15. *Plus de réponse à l'enregistrement* : `form.error.no_answer`, le tiroir reste ouvert.

`Échap` fait comme « Annuler ». Contraste, taille de cible et tokens : ceux de la maquette.

## Textes

Clés `main.agent_case.*` dans `content/ui.yaml` (fr), `content/i18n/en/ui.yaml` et `content/i18n/de/ui.yaml`, avec les mêmes clés et les mêmes variables dans les trois (parité). Le bloc `agent_case:` se place juste après `main.compare` (avant `orch:`), dans les trois fichiers. Allemand en « Sie ». Les `reason_text` du verdict viennent de la story 1, déjà en trois langues.

| Clé | fr | en | de |
|---|---|---|---|
| `form.action` | En faire un cas | Make it a case | Als Fall speichern |
| `form.action_label` | En faire un cas du {turn} | Make a case from {turn} | {turn} als Fall speichern |
| `form.title` | En faire un cas | Make it a case | Als Fall speichern |
| `form.subtitle` | {turn} · {model} · {date} | {turn} · {model} · {date} | {turn} · {model} · {date} |
| `form.loading` | Lecture du tour… | Reading the turn… | Der Turn wird gelesen … |
| `form.incomplete` | Ce tour s'est terminé sans aboutir (« {status} ») : sur lui, toutes les vérifications échouent (« tour incomplet »). Le verdict ne dit donc pas si vos vérifications visent le défaut que vous avez vu. | This turn ended without completing (“{status}”): every check fails on it (“incomplete turn”). The verdict therefore does not tell whether your checks target the failure you saw. | Dieser Turn wurde nicht abgeschlossen („{status}“): Bei ihm schlagen alle Prüfungen fehl („unvollständiger Turn“). Das Urteil sagt also nicht, ob Ihre Prüfungen den beobachteten Fehler treffen. |
| `form.field.title` | Titre | Title | Titel |
| `form.field.prompt` | Prompt | Prompt | Prompt |
| `form.field.symptom` | Symptôme | Symptom | Symptom |
| `form.field.assertion` | Assertion | Assertion | Behauptung |
| `form.field.max_calls` | Plafond d'appels au modèle | Model-call limit | Obergrenze für Modellaufrufe |
| `form.config.legend` | Configuration du tour (lecture seule) | Turn configuration (read-only) | Konfiguration des Turns (schreibgeschützt) |
| `form.config.line` | Briques : {bricks} · Fenêtre : {window} | Bricks: {bricks} · Window: {window} | Bausteine: {bricks} · Fenster: {window} |
| `form.config.window_unset` | non exigée | not required | nicht verlangt |
| `form.config.not_kept` | Non repris par le cas : {options}. L'exécution gardera le réglage courant. | Not kept by the case: {options}. The run will keep the current setting. | Vom Fall nicht übernommen: {options}. Der Lauf behält die aktuelle Einstellung. |
| `form.config.option.mcp_lazy` | chargement paresseux MCP | MCP lazy loading | verzögertes Laden (MCP) |
| `form.config.option.rag_rerank` | reranking RAG | RAG reranking | RAG-Reranking |
| `form.tools.legend` | Outils appelés par le tour | Tools called by the turn | Vom Turn aufgerufene Werkzeuge |
| `form.tools.none` | Aucun outil appelé. | No tool called. | Kein Werkzeug aufgerufen. |
| `form.history.include.one` | Reprendre l'historique ({count} échange) | Reuse the history ({count} exchange) | Verlauf übernehmen ({count} Austausch) |
| `form.history.include.other` | Reprendre l'historique ({count} échanges) | Reuse the history ({count} exchanges) | Verlauf übernehmen ({count} Austausche) |
| `form.history.compacted` | L'historique a été compacté ou réduit avant ce tour : il est repris tel que le modèle l'a reçu (résumé compris). | The history was compacted or trimmed before this turn: it is reused as the model received it (summary included). | Der Verlauf wurde vor diesem Turn verdichtet oder gekürzt: Er wird so übernommen, wie das Modell ihn erhalten hat (Zusammenfassung inbegriffen). |
| `form.history.unavailable` | L'historique de ce tour ne peut pas être reconstitué depuis le journal : il ne sera pas repris. | This turn's history cannot be rebuilt from the journal: it will not be reused. | Der Verlauf dieses Turns lässt sich aus dem Journal nicht rekonstruieren: Er wird nicht übernommen. |
| `form.freeze_prompt` | Figer ce prompt système dans le cas | Freeze this system prompt in the case | Diesen Systemprompt im Fall festhalten |
| `form.approval.label` | Validation humaine (H5) pendant l'exécution | Human approval (H5) during the run | Menschliche Freigabe (H5) während des Laufs |
| `form.approval.refuse` | refuser | refuse | ablehnen |
| `form.approval.approve` | accepter | approve | annehmen |
| `form.overflow.label` | Si le contexte déborde | If the context overflows | Wenn der Kontext überläuft |
| `form.overflow.none` | arrêter le tour | stop the turn | Turn beenden |
| `form.overflow.compaction` | compacter puis renvoyer | compact, then resend | verdichten, dann erneut senden |
| `form.overflow.sliding_window` | fenêtre glissante puis renvoyer | sliding window, then resend | gleitendes Fenster, dann erneut senden |
| `form.checks.legend` | Vérifications (une ou deux) | Checks (one or two) | Prüfungen (eine oder zwei) |
| `form.checks.type_label` | Type de vérification | Check type | Art der Prüfung |
| `form.checks.add` | Ajouter une vérification | Add a check | Prüfung hinzufügen |
| `form.checks.remove` | Retirer cette vérification | Remove this check | Diese Prüfung entfernen |
| `form.checks.kind.tool_called` | Outil appelé | Tool called | Werkzeug aufgerufen |
| `form.checks.kind.tool_not_called` | Outil non appelé | Tool not called | Werkzeug nicht aufgerufen |
| `form.checks.kind.argument_never` | Argument jamais passé | Argument never passed | Argument nie übergeben |
| `form.checks.kind.answer_contains` | Texte dans la réponse | Text in the answer | Text in der Antwort |
| `form.checks.kind.hook_decided` | Hook qui décide | Hook decided | Hook hat entschieden |
| `form.checks.kind.subagent_called` | Sous-agent appelé | Sub-agent called | Subagent aufgerufen |
| `form.checks.kind.turn_completed` | Tour fini sans erreur | Turn completed without error | Turn fehlerfrei beendet |
| `form.checks.param.tool` | Outil | Tool | Werkzeug |
| `form.checks.param.before` | avant (facultatif) | before (optional) | vor (optional) |
| `form.checks.param.argument` | Argument | Argument | Argument |
| `form.checks.param.contains` | contient | contains | enthält |
| `form.checks.param.text` | Texte | Text | Text |
| `form.checks.param.hook` | Hook | Hook | Hook |
| `form.checks.param.decision` | Décision | Decision | Entscheidung |
| `form.checks.decision.block` | bloque | blocks | blockiert |
| `form.checks.decision.ask_human` | demande l'accord | asks for approval | fragt nach Zustimmung |
| `form.verdict.fails` | Le tour d'origine échoue bien à ce cas. | The original turn does fail this case. | Der ursprüngliche Turn besteht diesen Fall tatsächlich nicht. |
| `form.verdict.cannot_fail` | Ce cas ne peut pas échouer sur ce tour. Il ne détectera pas la défaillance que vous avez vue. | This case cannot fail on this turn. It will not catch the failure you saw. | Dieser Fall kann bei diesem Turn nicht fehlschlagen. Er erkennt den beobachteten Fehler nicht. |
| `form.verdict.pending` | Calcul du verdict… | Computing the verdict… | Urteil wird berechnet … |
| `form.verdict.incomplete` | Complétez les vérifications pour voir le verdict. | Complete the checks to see the verdict. | Vervollständigen Sie die Prüfungen, um das Urteil zu sehen. |
| `form.verdict.unavailable` | WaveStack ne répond pas : le verdict n'a pas pu être calculé. | WaveStack is not responding: the verdict could not be computed. | WaveStack antwortet nicht: Das Urteil konnte nicht berechnet werden. |
| `form.save` | Enregistrer | Save | Speichern |
| `form.saving` | Enregistrement… | Saving… | Wird gespeichert … |
| `form.cancel` | Annuler | Cancel | Abbrechen |
| `form.discard.ask` | Abandonner les modifications ? | Discard your changes? | Änderungen verwerfen? |
| `form.discard.yes` | Abandonner | Discard | Verwerfen |
| `form.discard.no` | Continuer | Keep editing | Weiter bearbeiten |
| `form.saved` | Cas enregistré. | Case saved. | Fall gespeichert. |
| `form.open_view` | Ouvrir Évaluer l'agent | Open Evaluate the agent | „Agent bewerten“ öffnen |
| `form.close` | Fermer | Close | Schließen |
| `form.error.no_answer` | WaveStack ne répond pas : le cas n'a pas été enregistré. | WaveStack is not responding: the case was not saved. | WaveStack antwortet nicht: Der Fall wurde nicht gespeichert. |

Messages du backend (réponses `detail`), dans `content/messages.yaml` et ses surcouches, bloc `agent_case:` placé **juste avant** le bloc `agent_eval:` de la story 1 (la story 4 complète `agent_eval:` en fin de fichier), lus par `msg(key, lang)` :

| Clé | fr | en | de |
|---|---|---|---|
| `agent_case.refused.unknown_turn` | Ce tour n'est plus dans le journal (WaveStack a été relancé). | This turn is no longer in the journal (WaveStack was restarted). | Dieser Turn ist nicht mehr im Journal (WaveStack wurde neu gestartet). |
| `agent_case.refused.not_a_message` | Seul un tour de message peut devenir un cas. | Only a message turn can become a case. | Nur ein Nachrichten-Turn kann zu einem Fall werden. |
| `agent_case.refused.case_turn` | Ce tour a été joué par une exécution de cas. | This turn was played by a case run. | Dieser Turn wurde von einem Fall-Lauf gespielt. |
| `agent_case.refused.unfinished` | Ce tour n'est pas terminé. | This turn is not finished yet. | Dieser Turn ist noch nicht beendet. |
| `agent_case.error.required` | Ce champ est obligatoire. | This field is required. | Dieses Feld ist erforderlich. |
| `agent_case.error.max_calls` | Le plafond doit être au moins 1. | The limit must be at least 1. | Die Obergrenze muss mindestens 1 betragen. |
| `agent_case.error.checks_count` | Choisissez une ou deux vérifications. | Choose one or two checks. | Wählen Sie eine oder zwei Prüfungen. |
| `agent_case.error.checks_kind` | Ce type de vérification n'existe pas. | This check type does not exist. | Diese Art von Prüfung gibt es nicht. |
| `agent_case.error.unreadable` | Le fichier de vos cas est illisible : le cas n'a pas été enregistré. Vous pouvez l'effacer depuis « Évaluer l'agent » (« Effacer mes cas »). | The file with your cases is unreadable: the case was not saved. You can clear it from “Evaluate the agent” (“Clear my cases”). | Die Datei mit Ihren Fällen ist nicht lesbar: Der Fall wurde nicht gespeichert. Sie können sie unter „Agent bewerten“ („Meine Fälle löschen“) leeren. |

## Tests

Tests unitaires dans `tests/test_agent_eval_draft.py` et `tests/test_agent_case_api.py`. Les journaux sont construits à la main (listes d'`Envelope`), sans mock interne.

`reconstitute_draft` :
- la configuration vient du dernier `bricks_changed` avant `S` : avec deux `bricks_changed` de part et d'autre de `S`, le brouillon prend le premier (preuve de la pureté en `seq`) ;
- `not_kept` : carte `mcp` en `lazy` et `rag` avec reranking actif donnent les deux, brique non voulue rien ;
- fenêtre : un modèle `file` ou `server` donne `configured`, un modèle cloud donne `None` ;
- outils appelés : dans l'ordre, arguments exacts, statut lu dans `tool_ended`, outils du sous-agent présents avec leur `context_id` ;
- `model_calls` et `suggested_max_model_calls` (0 appel donne 1) ;
- `answer_text` sans `turn_ended.text` : reconstitué depuis les `model_delta` (cas courant, sortie non retenue) ;
- historique :
  - trois échanges `completed` **sans `turn_ended.text`**, donc `history_available` vrai et les réponses reconstituées depuis les deltas ;
  - un `conversation_cleared` entre deux échanges remet l'historique à vide ;
  - un tour `blocked` ou `limit` n'y entre pas ;
  - un tour de rejeu part de l'historique d'avant son origine ;
  - après `history_compacted` `sliding_window`, les échanges retirés manquent ;
  - après `compaction`, le résumé est en tête (message du tour de compaction, `summary_text`) et `history_note == "compacted"` ;
  - un `summary_text` manquant donne `history_available` faux ;
- `origin_status` : un tour `limit`, `error`, `cancelled` ou `overflow` est accepté et renvoie son statut ;
- refus : `unknown_turn`, `not_a_message` (tour de compaction), `case_turn` (payload avec `case_id`), `unfinished` ;
- `approval` : `approval_resolved` `approved` donne `approve`, `refused` donne `refuse`, sans validation `refuse` ;
- débordement :
  - séquence `O` en `overflow`, puis tour de compaction et `history_compacted`, puis `T` de même message : `on_overflow == "compaction"`, `verdict_turn_ids == [O, C, T]`, historique d'avant la compaction ;
  - même séquence en `sliding_window` : `[O, T]` ;
  - message différent : `none` et `[T]` ;
- `to_case` :
  - historique omis si `include_history` est faux ou si l'historique est indisponible ;
  - prompt système `None` par défaut, son texte s'il est figé, `provenance.system_prompt_text` toujours rempli ;
  - `provenance.source == "séance"`, `turn_id`, `model` et `date` du tour ;
  - `approval` et `on_overflow` du formulaire ;
  - un cas avec seulement `tool_not_called` est valide (pas de règle positive pour la séance).

Routes (`TestClient`, session `booted_session` du faux moteur, `WAVESTACK_DATA_DIR` sous `tmp_path`) :
- un vrai tour joué par le faux moteur (outil `get_datetime`), puis `GET /draft` : il renvoie le prompt, l'outil, les arguments exacts et `answer_text` non vide ;
- `/verdict` :
  - avec `tool_not_called get_datetime` : `passed` faux, `failing.kind == "tool_not_called"`, `reason_text` dans la langue de la session ;
  - avec `tool_called get_datetime` : `passed` vrai ;
  - le faux moteur n'est pas appelé (compteur d'appels inchangé) et le journal n'a aucune nouvelle enveloppe ;
  - avec un plafond inférieur aux appels réels, il échoue sur le plafond ;
  - un tour en `limit` (`[tools] max_calls` à 1 et un faux moteur qui rappelle l'outil ; à défaut, un tour annulé) : `/draft` 200 avec `origin_status == "limit"` ; `/verdict` `passed` faux, `origin_complete` faux, raison « tour incomplet » ;
  - `answer_contains` avec un texte vide : 422 avec `field == "checks.0.text"` ;
- `POST /cases` :
  - 201, le cas relu par `store.read_session_cases()` est identique et sa provenance conforme ;
  - un corps qui ajoute `provenance` reçoit 422 (champ en trop), et rien n'est écrit ;
  - symptôme vide : 422 avec le champ nommé ;
  - 3 vérifications : 422 `checks_count` ;
  - fichier illisible : 409 et rien d'écrit ;
- après `reset()` de la session, le cas enregistré est toujours dans `agent_cases.json` ;
- `turn_id` inconnu : 404 ; tour de compaction : 409 ;
- parité i18n : le test de miroir existant couvre `main.agent_case.*` et `agent_case.*` (mêmes clés et mêmes variables en `en` et en `de`) ; test de la forme `.one`/`.other` de `form.history.include`.

Réalignement : `git grep` des tests qui comptent les actions d'un tour, les clés `main.*` ou les routes de `create_app` (rien relevé à la rédaction ; à refaire au développement).

E2E : scénario `agent_case`, inséré dans `SCENARIOS` de `tools/e2e/run_e2e.py` **juste après `compact_button`**, avec sa fonction `s_agent_case` après `s_compact_button`. La story 4 ajoute les siens en fin de liste. Faux moteur local (`fake_local_server.py`), Edge. Le scénario suit `vues.md` :
1. un message fait appeler `get_datetime` ; le tour se termine ;
2. « En faire un cas » est proposé sur ce tour ;
3. le tiroir s'ouvre pré-rempli : prompt, outil `get_datetime` avec ses arguments, historique à zéro échange (case absente ou décochée), « Figer ce prompt système » décoché, `approval` sur « refuser » ;
4. symptôme, assertion et titre remplis, vérification `tool_not_called get_datetime` : bandeau « échoue bien » ;
5. passage à `tool_called get_datetime` : avertissement « ne peut pas échouer » ;
6. « Annuler » sur le tiroir modifié demande « Abandonner », puis « Continuer » ;
7. « Enregistrer » avec un symptôme vide : erreur sous le champ ; une fois rempli : « Cas enregistré », et pas de bouton « Ouvrir Évaluer l'agent » (aucune vue enregistrée) ;
8. `agent_cases.json` contient le cas, avec `provenance.source == "séance"` (lecture sur disque dans `r.stack.data_dir`). Après « Vider la conversation » et la réinitialisation du harnais, le fichier est intact ;
9. un second tour arrêté (stop) propose aussi l'action ; le tiroir montre la note de tour non abouti ;
10. en anglais, puis en allemand : titre du tiroir et bandeau traduits ;
11. capture `agent-case-form`.

L'étape « Ouvrir Évaluer l'agent ouvre la vue, avec le cas dans Mes cas » revient à la story 4.

## Fichiers

Nouveaux :
- `src/wavestack/agent_eval/draft.py` ;
- `src/wavestack/web/agent_case_api.py` ;
- `src/wavestack/web/static/agent-case-form.js` ;
- `src/wavestack/web/static/agent-case-form.css` ;
- `tests/test_agent_eval_draft.py` ;
- `tests/test_agent_case_api.py`.

Modifiés (fichiers partagés en **gras**, chacun avec un point d'insertion fixé pour éviter les conflits avec la story 4) :
- **`src/wavestack/web/app.py`** : import et une ligne `register_agent_case_routes(app, app_session)`, placés juste après l'enregistrement des routes de compaction (`/api/intentions/compact`). La story 4 met sa ligne ailleurs, ou à la suite.
- **`src/wavestack/web/static/app.js`** : l'import (après celui de `panes.js`) et le bouton dans `turn-actions`, après « Comparer ».
- **`content/ui.yaml`**, **`content/i18n/en/ui.yaml`**, **`content/i18n/de/ui.yaml`** : bloc `main.agent_case`, après `main.compare`.
- **`content/messages.yaml`** et ses deux surcouches : bloc `agent_case`, avant `agent_eval`.
- **`tools/e2e/run_e2e.py`** : une entrée après `compact_button` et la fonction ; `tools/e2e/README.md` : une ligne.
- `index.html` n'est **pas** modifié (la feuille de style est chargée par le module).

## Reports

- Modifier un cas enregistré : hors périmètre (SPEC, Non-goals).
- Reprendre `mcp_lazy` et le reclassement RAG : il faudrait changer le contrat (stories 1 et 4). Le formulaire le signale.
- Étapes intermédiaires de l'historique (appels d'outils des tours passés) : le contrat ne les porte pas.

## Décisions du point de contrôle (2026-10-25)

1. **Tour non `completed`** : tout tour de message terminé est éligible, `cancelled` compris. Le formulaire affiche la note « tour non abouti », propose `turn_completed` comme première vérification, et le verdict « échoue bien » donne la raison « tour incomplet ». Seuls `unknown_turn`, `not_a_message`, `case_turn` et `unfinished` sont refusés. *À revoir par Anaël* (accepter le tour annulé).
2. **Historique après compaction** : reconstitué fidèlement depuis `removed_turn_ids` et `summary_text`, comme `_history_compacted`. Indisponible seulement si le journal ne permet pas la reconstitution. Corrigé au passage : la première version exigeait `turn_ended.text`, absent sauf quand la sortie est retenue, ce qui rendait presque tout historique indisponible.
3. **`approval` et `on_overflow`** : les deux. Ils sont déduits du journal (`approval_resolved` ; renvoi après `overflow` et `history_compacted`, avec historique d'avant la stratégie et `verdict_turn_ids` alignés sur le contrat), puis affichés dans deux sélecteurs modifiables.
4. **`mcp_lazy` et `rag_rerank`** : hors contrat, non repris, signalés par `not_kept`. Le contrat n'est pas étendu.
5. **Cas fournis** : `add_session_case(case, load_provided_cases())`, disponible dès la story 1 (`[]` sans fichier).
6. **Date de provenance** : la date du tour d'origine (`turn_started.ts`), c'est-à-dire celle de la défaillance observée.
7. **Fenêtre d'un modèle réseau** (Ollama, llama-server, `hosting == "server"`) : `configured`, comme un fichier local. La story 4 doit comparer `case.window` au `configured` du `context_window_state` courant, et à aucun autre champ.
8. **Une ou deux vérifications** dans le formulaire, contre une à trois dans le contrat : voulu (CAP-3), le contrat ne change pas. Pas de vérification positive obligatoire pour un cas de séance.
9. **Interface avec la story 4** : exports ES d'`agent-case-form.js` (`registerOpenView`, `onCaseSaved`, `openCaseForm`, `closeCaseForm`, `canMakeCase`), et pas de `window.agentEval`. Fichiers, clés et routes séparés ; les points d'insertion des fichiers partagés sont fixés dans « Fichiers ».

## Écarts constatés au développement

- **Id d'essai** : `/verdict` construit le cas d'essai avec l'id `udraft`, pas `draft` : l'id d'un cas de séance commence par `u` (validateur d'`AgentCase`).
- **Bouton** : il n'existait ni `turn-actions` ni « Comparer » par tour (« Comparer » est un bouton global du compositeur). `app.js` crée une rangée `div.turn-actions` sous la bulle du modèle (fonction `caseActions`), avec `data-focus-key="agent-case:{turn}"` et `data-turn-label` (le nom du tour, pour le sous-titre du tiroir). Le tour garde `caseId` (lu dans `turn_started.case_id`, que la story 4 ajoute).
- **Note de refus** : posée sous la rangée d'actions du tour, elle disparaît au prochain rendu du chat.
- **Clés `yes` et `no`** de `form.discard` : écrites entre guillemets dans `ui.yaml`, sinon YAML 1.1 les lit comme des booléens.
- **Journal des tests** : le journal est global au processus et les `turn_id` repartent à `t1` à chaque session ; les tests de route remplacent le journal par un journal neuf.
- `agent-case-form.js` : `canMakeCase(started, ended)` lit les charges utiles (`{kind, case_id}` et `{status}`) ; `index.html` et `app.css` ne sont pas modifiés ; `tests/test_ui_texts.py` ajoute le module à la liste des scripts de la page.
