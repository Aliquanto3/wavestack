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

CAP-3 de la V1.5. Sur un tour terminé de la Vue humain, « En faire un cas » ouvre un tiroir pré-rempli depuis le journal (prompt, configuration, historique, outils appelés). Le formateur nomme le symptôme et l'assertion, choisit une ou deux vérifications ; le serveur rejoue `verify` sur le tour d'origine, sans appel au modèle, et dit si le cas échoue bien sur ce tour. L'enregistrement écrit un cas de séance (`agent_cases.json`, provenance `séance`) qui survit à `reset()`.

Base : `origin/main` à `3214fec5` plus le contrat de la story 1 (commit `214f9289`, branche à fusionner avant celle-ci) : `AgentCase`, `Provenance`, `Check`, `new_case_id`, `checks.verify(case, envelopes, lang)`, `store.*`. Cette story ne les recrée pas. Disposition : maquette, section 1 ; comportement : `vues.md`.

## Décisions

- **Brouillon et verdict calculés par le serveur** à partir du journal ; le client n'envoie que ses saisies. La provenance (modèle, `turn_id`, date, prompt système du tour) vient toujours du journal, jamais du corps de la requête.
- **Un module d'API à part**, `web/agent_eval_api.py`, avec `register_agent_eval_routes(app, app_session)` appelé d'une ligne dans `create_app` : `app.py` fait déjà plus de 1 600 lignes de routes et la story 4 y ajoute les siennes (voir « Fichiers »).
- **Tour éligible** : `turn_started.kind == "message"`, sans `case_id` (tour joué par une exécution, story 4), avec un `turn_ended` de statut différent de `cancelled` (un tour annulé est « incomplet » pour `verify` : toutes ses vérifications échoueraient, le verdict n'apprendrait rien). Refus 409 avec une raison sinon.
- **Pas de nouvelle clé de contrat** : le contrat des cas n'a ni `mcp_lazy` ni `rag_rerank` ; le brouillon ne les reprend pas (voir Points ouverts).

## Reconstitution du brouillon

Module `src/wavestack/agent_eval/draft.py`, **pure** (aucune I/O, aucun accès au `Journal` : elle lit la liste d'enveloppes reçue, comme `verify`).

```
reconstitute_draft(envelopes: Sequence[Envelope], turn_id: str) -> CaseDraft
class DraftRefused(Exception): reason: Literal["unknown_turn", "not_a_message", "case_turn", "unfinished", "cancelled"]
```

Fonction pure du `seq` du `turn_started` d'origine (`S`) : seules comptent les enveloppes de `seq < S` pour la configuration et l'historique, et celles du tour pour les outils. Test : ajouter des enveloppes de `seq` supérieur à la fin du tour ne change pas le brouillon.

`CaseDraft` (pydantic, `extra="forbid"`, renvoyé tel quel par la route) :

| Champ | Source dans le journal |
|---|---|
| `turn_id`, `seq`, `date` | `turn_started` (`seq`, `ts` en ISO) |
| `model` (`ActiveModel` \| None) | `turn_started.active_model` |
| `prompt` | `turn_started.message` |
| `bricks` (ids des briques voulues) | dernier `bricks_changed` de `seq < S` : cartes avec `wanted` |
| `tools`, `hooks`, `skills`, `mcp_servers` | même événement : ids des `options` avec `enabled` des cartes `tools`, `hooks`, `skills`, `mcp` |
| `window` (int \| None) | dernier `context_window_state` de `seq < S` : `configured` si `hosting` vaut `file` ou `server`, sinon `None` (fenêtre déclarée d'un modèle cloud : pas exigée) |
| `system_prompt` : `{text, is_default}` | même `bricks_changed` : `system_prompt` |
| `history` : liste de `{user, assistant}` | voir ci-dessous |
| `history_available` (bool), `history_note` | faux si une stratégie a touché l'historique (voir ci-dessous) |
| `tool_calls` : liste `{seq, tool, arguments, status, context_id}` | `tool_started` du tour (tous contextes), `status` lu dans le `tool_ended` de même `call_id` (`None` si absent) |
| `hooks_decided` : `{hook, decision}` | `hook_decided` du tour |
| `subagent_called` (bool) | au moins un `subagent_started` du tour |
| `model_calls` (int) | `model_call_started` du tour, tous contextes |
| `answer_text` | `turn_ended.text` |
| `suggested_max_model_calls` | `max(1, model_calls)` |

**Historique à `S`.** Parcours des enveloppes de `seq < S` par `turn_id` :
- repart de vide à chaque `conversation_cleared` et `harness_reset` ;
- un tour de `kind == "message"` terminé `completed` ajoute `{user: message, assistant: turn_ended.text}` (un tour `blocked` n'entre pas, comme dans la session) ;
- un tour avec `replay_of = X` part de l'historique d'avant `X` (AD-17), puis s'ajoute le sien ;
- un `history_compacted` après le dernier effacement : `history = []`, `history_available = false`, `history_note = "compacted"` (le résumé n'est pas rejouable fidèlement ; voir Points ouverts). Même résultat si un `turn_ended.text` manque pour un tour `completed`.

`history_available = false` : la case « Reprendre l'historique » est absente et la note l'explique.

**Mapping vers `AgentCase`** (`draft.to_case(form)`, pure aussi) : `id = new_case_id()` (injecté en paramètre pour les tests), `history = draft.history` si `form.include_history` et `history_available`, sinon `[]` ; `system_prompt = draft.system_prompt.text` si `form.freeze_system_prompt`, sinon `None` ; `window`, `bricks`, `tools`, `hooks`, `skills`, `mcp_servers` du brouillon ; `approval = "refuse"`, `on_overflow = "none"` (défauts du contrat ; un tour qui a eu une validation H5 est repris tel quel, la validation de l'exécution sera refusée : voir Points ouverts) ; `provenance = {source: "séance", date, model, turn_id, system_prompt_text: draft.system_prompt.text, fixed_in: None}`.

## Routes

Toutes sous `/api/agent_eval/`, dans `web/agent_eval_api.py`. Erreurs : `{"detail": <texte dans la langue de la session>}`, comme les autres intentions.

| Route | Entrée | Réponse |
|---|---|---|
| `GET /draft?turn_id=t4` | requête | 200 `CaseDraft` ; 404 `unknown_turn` ; 409 pour les autres `DraftRefused` (texte de la raison) |
| `POST /verdict` | `CaseForm` | 200 `FormVerdict` ; 404/409 comme `/draft` ; 422 si une vérification est mal formée (pydantic) |
| `POST /cases` | `CaseForm` | 201 `{case: AgentCase}` ; 404/409 comme `/draft` ; 422 `{detail: [{field, message_text}]}` (titre, symptôme, assertion, 1 à 2 vérifications, plafond ≥ 1) ; 409 fichier de séance illisible (`SessionCasesUnreadable`), texte qui propose « Effacer mes cas » (vue de la story 4) |

```
CaseForm = {
  turn_id: str,
  title_text: str, symptom_text: str, assertion_text: str,   # vides tolérés par /verdict
  prompt: str,                                               # modifiable
  include_history: bool, freeze_system_prompt: bool,
  max_model_calls: int,                                      # >= 1
  checks: list[Check]                                        # 1 à 2 (le contrat en admet 3)
}
FormVerdict = {
  passed: bool,               # tous les contrôles, plafond compris, réussissent sur le tour d'origine
  cannot_fail: bool,          # == passed : le cas ne peut pas échouer sur ce tour
  failing: CheckVerdict | None,   # la première vérification qui échoue (reason_text, seq)
  checks: list[CheckVerdict], model_calls: int
}
```

- `/verdict` recalcule le brouillon depuis `get_journal().all_events()`, construit un `AgentCase` d'essai (id `draft`), filtre les enveloppes sur `turn_id` d'origine (tous contextes) et appelle `verify(case, envelopes, session.language)`. Aucun appel au modèle, aucun événement émis, aucun état de session lu en dehors de la langue.
- `/cases` refait la même construction, avec `new_case_id()`, et appelle `store.add_session_case(case, provided)` (`provided` : cas fournis chargés par le chargeur de la story 2 ; `[]` tant que la story 2 n'est pas fusionnée). Le verdict n'est pas bloquant : un cas qui ne peut pas échouer s'enregistre (vues.md).
- Le prompt modifié ne change pas le verdict (celui-ci lit le tour d'origine) : il n'est pas envoyé à `/verdict` pour le calcul, mais `/cases` l'enregistre.
- Le `turn_id` du `prompt` est `provenance.turn_id`, la chaîne du tour d'origine est donc retrouvable par la story 4.

## Formulaire

`web/static/agent-eval.js` (exporte `openCaseForm(turnId)` et `closeCaseForm()`), styles `ae-*` de la maquette dans `web/static/agent-eval.css` (nouveau fichier, lié par `index.html` ; la maquette les propose pour `app.css`, mais la story 4 les complète : un fichier à part évite le conflit). Disposition : tiroir `.ae-drawer`, sur le volet de la Vue humain, rôle `dialog` modal, focus sur le titre à l'ouverture et rendu au bouton « En faire un cas » à la fermeture.

**Entrée.** Dans `app.js`, à côté de « Comparer » (`turn-actions`), un bouton `En faire un cas` par tour éligible (tour de message, terminé, ni compaction, ni annulé, ni tour d'exécution). Modification d'`app.js` : l'import de `openCaseForm` et la création du bouton (une dizaine de lignes). Rien d'autre.

**Contenu** (ordre de la maquette) : titre (champ) ; prompt (zone, modifiable) ; configuration en lecture seule (briques, sous-options, fenêtre, modèle) ; outils appelés, numérotés, avec arguments et statut ; case « Reprendre l'historique (N échanges) » (cochée si N > 0, absente si `history_available` est faux) ; case « Figer ce prompt système dans le cas » (décochée) ; symptôme ; assertion ; une ou deux vérifications ; plafond d'appels (pré-rempli à `suggested_max_model_calls`) ; verdict ; « Enregistrer » et « Annuler ».

**Vérifications.** Un sélecteur du catalogue (hors `model_calls_max`), puis les paramètres de ce type, pré-remplis depuis le tour :

| Type | Paramètres du formulaire | Pré-remplissage |
|---|---|---|
| `tool_called` | outil (liste), `before` (liste facultative) | premier outil appelé ; `before` vide |
| `tool_not_called` | outil | premier outil appelé |
| `argument_never` | outil, argument, contient | premier appel : premier argument et sa valeur |
| `answer_contains` | texte | vide |
| `hook_decided` | hook, décision (`block` \| `ask_human`) | première décision vue dans le tour, sinon vide |
| `subagent_called`, `turn_completed` | aucun | |

La liste d'outils propose ceux du tour, puis ceux de la configuration. Première vérification par défaut : `tool_called` si le tour a appelé un outil, sinon `turn_completed`. « Ajouter une vérification » disparaît à deux ; « Retirer » disparaît à une.

**États.**
1. *Fermé.*
2. *Chargement* : tiroir ouvert, « Lecture du tour… », saisie désactivée.
3. *Refusé* (409/404) : pas de tiroir ; le texte du refus s'affiche dans une note sous l'action du tour, comme `replay_refused`.
4. *Prêt, intact* : champs pré-remplis ; « Annuler » ferme sans confirmation.
5. *Modifié* : dès qu'un champ diffère du brouillon, « Annuler » devient une confirmation « Abandonner les modifications ? » avec « Abandonner » et « Continuer » (comme le tiroir du prompt système, dans la page, jamais `confirm()`).
6. *Verdict en cours* : `/verdict` appelé à chaque changement de vérification ou de plafond, après 250 ms sans saisie, la dernière réponse l'emporte (compteur de requêtes) ; l'ancien verdict reste grisé.
7. *Verdict « échoue bien »* (`passed` faux) : bandeau `ae-verdict fails`, `role="status"` : « Le tour d'origine échoue bien à ce cas. » suivi de la raison de `failing` (`reason_text`).
8. *Verdict « ne peut pas échouer »* (`passed` vrai) : bandeau `ae-verdict warns` : « Ce cas ne peut pas échouer sur ce tour. Il ne détectera pas la défaillance que vous avez vue. » L'enregistrement reste possible.
9. *Verdict indisponible* (réseau ou 5xx) : « WaveStack ne répond pas : le verdict n'a pas pu être calculé. » ; l'enregistrement reste possible.
10. *Invalide* : « Enregistrer » est actif ; une tentative avec symptôme, assertion ou titre vide, ou plafond < 1, affiche l'erreur sous chaque champ (`message_text` du 422) et place le focus sur le premier.
11. *Enregistrement* : « Enregistrer » désactivé, « Enregistrement… ».
12. *Enregistré* : le formulaire est remplacé par « Cas enregistré. » avec « Ouvrir Évaluer l'agent » et « Fermer ». « Ouvrir » appelle `window.agentEval?.openView?.()` ; la vue arrive avec la story 4, et le bouton est masqué tant que cette fonction n'existe pas.
13. *Fichier illisible* (409 à l'enregistrement) : message d'erreur dans le tiroir, qui reste ouvert et intact.

`Échap` suit « Annuler ». Contraste, taille de cible et tokens : ceux de la maquette.

## Textes

Clés `main.agent_eval.*` dans `content/ui.yaml` (fr), `content/i18n/en/ui.yaml`, `content/i18n/de/ui.yaml`, mêmes clés et mêmes variables dans les trois (parité). Allemand en « Sie ». Les `reason_text` du verdict viennent de la story 1 (déjà en trois langues).

| Clé | fr | en | de |
|---|---|---|---|
| `form.action` | En faire un cas | Make it a case | Als Fall speichern |
| `form.action_label` | En faire un cas du {turn} | Make a case from {turn} | {turn} als Fall speichern |
| `form.title` | En faire un cas | Make it a case | Als Fall speichern |
| `form.subtitle` | {turn} · {model} · {date} | {turn} · {model} · {date} | {turn} · {model} · {date} |
| `form.loading` | Lecture du tour… | Reading the turn… | Der Turn wird gelesen … |
| `form.field.title` | Titre | Title | Titel |
| `form.field.prompt` | Prompt | Prompt | Prompt |
| `form.field.symptom` | Symptôme | Symptom | Symptom |
| `form.field.assertion` | Assertion | Assertion | Behauptung |
| `form.field.max_calls` | Plafond d'appels au modèle | Model-call limit | Obergrenze für Modellaufrufe |
| `form.config.legend` | Configuration du tour (lecture seule) | Turn configuration (read-only) | Konfiguration des Turns (schreibgeschützt) |
| `form.config.line` | Briques : {bricks} · Fenêtre : {window} | Bricks: {bricks} · Window: {window} | Bausteine: {bricks} · Fenster: {window} |
| `form.config.window_unset` | non exigée | not required | nicht verlangt |
| `form.tools.legend` | Outils appelés par le tour | Tools called by the turn | Vom Turn aufgerufene Werkzeuge |
| `form.tools.none` | Aucun outil appelé. | No tool called. | Kein Werkzeug aufgerufen. |
| `form.history.include.one` | Reprendre l'historique ({count} échange) | Reuse the history ({count} exchange) | Verlauf übernehmen ({count} Austausch) |
| `form.history.include.other` | Reprendre l'historique ({count} échanges) | Reuse the history ({count} exchanges) | Verlauf übernehmen ({count} Austausche) |
| `form.history.compacted` | L'historique a été compacté ou réduit avant ce tour : il ne peut pas être repris. | The history was compacted or trimmed before this turn: it cannot be reused. | Der Verlauf wurde vor diesem Turn verdichtet oder gekürzt: Er kann nicht übernommen werden. |
| `form.freeze_prompt` | Figer ce prompt système dans le cas | Freeze this system prompt in the case | Diesen Systemprompt im Fall festhalten |
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
| `form.error.required` | Ce champ est obligatoire. | This field is required. | Dieses Feld ist erforderlich. |
| `form.error.max_calls` | Le plafond doit être au moins 1. | The limit must be at least 1. | Die Obergrenze muss mindestens 1 betragen. |
| `form.error.checks_count` | Choisissez une ou deux vérifications. | Choose one or two checks. | Wählen Sie eine oder zwei Prüfungen. |
| `form.error.unreadable` | Le fichier de vos cas est illisible : le cas n'a pas été enregistré. Vous pouvez l'effacer depuis « Évaluer l'agent » (« Effacer mes cas »). | The file with your cases is unreadable: the case was not saved. You can clear it from “Evaluate the agent” (“Clear my cases”). | Die Datei mit Ihren Fällen ist nicht lesbar: Der Fall wurde nicht gespeichert. Sie können sie unter „Agent bewerten“ („Meine Fälle löschen“) leeren. |
| `form.error.no_answer` | WaveStack ne répond pas : le cas n'a pas été enregistré. | WaveStack is not responding: the case was not saved. | WaveStack antwortet nicht: Der Fall wurde nicht gespeichert. |
| `refused.unknown_turn` | Ce tour n'est plus dans le journal (WaveStack a été relancé). | This turn is no longer in the journal (WaveStack was restarted). | Dieser Turn ist nicht mehr im Journal (WaveStack wurde neu gestartet). |
| `refused.not_a_message` | Seul un tour de message peut devenir un cas. | Only a message turn can become a case. | Nur ein Nachrichten-Turn kann zu einem Fall werden. |
| `refused.case_turn` | Ce tour a été joué par une exécution de cas. | This turn was played by a case run. | Dieser Turn wurde von einem Fall-Lauf gespielt. |
| `refused.unfinished` | Ce tour n'est pas terminé. | This turn is not finished yet. | Dieser Turn ist noch nicht beendet. |
| `refused.cancelled` | Ce tour a été arrêté : son journal est incomplet, il ne peut pas devenir un cas. | This turn was stopped: its journal is incomplete, it cannot become a case. | Dieser Turn wurde gestoppt: Sein Journal ist unvollständig, er kann kein Fall werden. |

Messages du backend (réponses `detail`) : les cinq `refused.*` passent par `msg(key, lang)` de `content/messages.yaml` (trois langues, mêmes clés `agent_eval.refused.*`) ; les textes du tableau ci-dessus sont ceux de leurs valeurs. `form.error.unreadable` aussi est servi par le backend.

## Tests

Unitaires, fichiers `tests/test_agent_eval_draft.py` et `tests/test_agent_eval_api.py` ; journaux construits à la main (listes d'`Envelope`), pas de mock interne.

`reconstitute_draft` :
- configuration lue du dernier `bricks_changed` avant `S`, pas d'un événement plus tardif ; deux `bricks_changed` de part et d'autre de `S` donnent la configuration du premier (preuve de la pureté en `seq`) ;
- fenêtre : modèle local donne `configured`, modèle cloud donne `None` ;
- outils appelés dans l'ordre, arguments exacts, statut lu dans `tool_ended`, outils du sous-agent présents avec leur `context_id` ;
- `model_calls` et `suggested_max_model_calls` (0 appel donne 1) ;
- historique : trois échanges `completed` ; un `conversation_cleared` entre eux remet à vide ; un tour `blocked` n'y entre pas ; un tour de rejeu part de l'historique d'avant son origine ; `history_compacted` donne `history_available` faux ; un `turn_ended.text` manquant aussi ;
- refus : `unknown_turn`, `not_a_message` (compaction), `case_turn` (`case_id` rempli), `unfinished`, `cancelled` ;
- `to_case` : historique omis si `include_history` est faux ou indisponible ; prompt système `None` par défaut, texte si figé, `provenance.system_prompt_text` toujours rempli ; `provenance.source == "séance"`, `turn_id` et `model` du tour ; id commençant par `u`.

Routes (`TestClient`, session `booted_session` du faux moteur, `WAVESTACK_DATA_DIR` sous `tmp_path`) :
- un vrai tour joué par le faux moteur (outil `get_datetime`), puis `GET /draft` renvoie le prompt, l'outil et les arguments exacts ;
- `/verdict` avec `tool_not_called get_datetime` : `passed` faux, `failing.kind == "tool_not_called"`, `reason_text` dans la langue de la session ; avec `tool_called get_datetime` : `passed` et `cannot_fail` vrais ;
- le faux moteur n'est pas appelé par `/verdict` (compteur d'appels inchangé) et le journal n'a aucune nouvelle enveloppe ;
- plafond inférieur aux appels réels : `/verdict` échoue sur le plafond ;
- `POST /cases` : 201, le cas relu par `store.read_session_cases()` est identique, provenance conforme ; un corps qui prétend une autre provenance est ignoré (champ refusé ou sans effet) ; symptôme vide donne 422 avec le champ nommé ; 3 vérifications donnent 422 ; fichier illisible donne 409 et rien d'écrit ;
- `reset()` de la session : le cas enregistré est toujours dans `agent_cases.json` ;
- tour annulé : `/draft` donne 409 (statut `cancelled`) ; `turn_id` inconnu donne 404 ;
- parité i18n : le test existant de miroir de `ui.yaml` et `messages.yaml` couvre les nouvelles clés (aucune clé `main.agent_eval.form.*` absente de `en` ou `de`, mêmes variables) ; test de la forme `.one`/`.other` de `form.history.include`.

Réalignement : `git grep` des tests qui comptent les actions d'un tour ou les clés `main.*` (aucun relevé à la rédaction ; à refaire au développement).

E2E : scénario `agent_case` ajouté à `SCENARIOS` de `tools/e2e/run_e2e.py`, faux moteur local (`fake_local_server.py`), Edge ; décrit dans `vues.md` :
1. un message qui fait appeler `get_datetime` ; le tour se termine ;
2. « En faire un cas » est proposé sur ce tour ; pas sur un tour annulé (stop pendant un second tour) ;
3. le tiroir s'ouvre pré-rempli : prompt, outil `get_datetime` avec ses arguments, historique à zéro échange donc case absente ou non cochée, « Figer ce prompt système » décoché ;
4. symptôme, assertion, titre remplis ; vérification `tool_not_called get_datetime` : bandeau « échoue bien » ;
5. changer en `tool_called get_datetime` : avertissement « ne peut pas échouer » ;
6. « Annuler » sur un tiroir modifié demande « Abandonner » (puis « Continuer ») ;
7. « Enregistrer » avec symptôme vide : erreur sous le champ ; puis rempli : « Cas enregistré » ;
8. `agent_cases.json` contient le cas (lecture sur disque, `WAVESTACK_DATA_DIR` de l'E2E), `provenance.source == "séance"` ; après « Vider la conversation » et la réinitialisation du harnais, le fichier est intact ;
9. en anglais puis en allemand : titre du tiroir et bandeau traduits ;
10. avec la story 4 fusionnée : « Ouvrir Évaluer l'agent » ouvre la vue et le cas y figure dans « Mes cas » (étape ajoutée à la fusion, pas dans cette story) ;
11. capture `agent-case-form`.

## Fichiers

Nouveaux : `src/wavestack/agent_eval/draft.py` ; `src/wavestack/web/agent_eval_api.py` ; `src/wavestack/web/static/agent-eval.js` ; `src/wavestack/web/static/agent-eval.css` ; `tests/test_agent_eval_draft.py` ; `tests/test_agent_eval_api.py`.

Modifiés :
- `src/wavestack/web/app.py` : une ligne, `register_agent_eval_routes(app, app_session)` ; **partagé avec la story 4** (qui ajoutera ses routes dans `agent_eval_api.py`, pas dans `app.py` ; la story 6 y ajoute `/api/glossary`).
- `src/wavestack/web/static/app.js` : import et bouton « En faire un cas » dans les actions d'un tour ; **partagé avec la story 4**.
- `src/wavestack/web/static/index.html` : lien vers `agent-eval.css` ; **partagé avec la story 4** (bouton de la barre du haut).
- `content/ui.yaml`, `content/i18n/en/ui.yaml`, `content/i18n/de/ui.yaml` (section `main.agent_eval`, **partagée avec la story 4**) ; `content/messages.yaml` et surcouches (`agent_eval.refused.*`).
- `tools/e2e/run_e2e.py` (une entrée de `SCENARIOS`, **partagé**), `tools/e2e/README.md` (une ligne).

Pour limiter les conflits, les clés de la story 3 sont sous `main.agent_eval.form.*` et `main.agent_eval.refused.*` ; la story 4 prend `main.agent_eval.view.*`.

## Reports

- Recréer un cas à partir d'un tour de rejeu ou d'un tour d'exécution (story 4) : non, refusé.
- Modification d'un cas enregistré : hors périmètre (SPEC, Non-goals).
- Pré-remplir `approval` et `on_overflow` depuis le tour : non faits (défauts du contrat).

## Points ouverts

1. **Tour annulé.** Refusé ici (409), en attendant le correctif de revue de la story 1 qui rendra un tour annulé « incomplet » ; à confirmer par Anaël, ainsi que le cas du tour arrêté par une limite (`limit`, `overflow`, `error`), proposé et vérifiable comme les autres.
2. **Historique après compaction.** Indisponible (case absente avec note) plutôt que reconstitué ; le journal porte `summary_text` et `removed_turn_ids`, une reconstitution fidèle est possible mais plus lourde (report possible, ou ajout si Anaël y tient).
3. **Cas qui a eu une validation H5 ou un débordement.** Le brouillon prend `approval = "refuse"` et `on_overflow = "none"` par défaut : un tour où le formateur a accepté H5 serait donc rejoué avec un refus. Ajouter deux sélecteurs au formulaire (contrat inchangé) ou garder les défauts ?
4. **Options sans champ dans le contrat** (`mcp_lazy`, `rag_rerank`) : non reprises. Ajouter ces champs au contrat des cas est un changement de spec (stories 1 et 4).
5. **Chargeur des cas fournis** : `add_session_case(case, provided)` a besoin des ids fournis pour l'unicité ; le nom de la fonction de la story 2 n'est pas connu. Ici `[]` tant qu'elle n'est pas fusionnée, puis un appel au chargeur à la fusion. Un id `u` + 8 hex ne peut de toute façon pas entrer en collision avec une clé lisible.
6. **Date de provenance** : la date du tour d'origine (choix retenu), pas celle de l'enregistrement.
7. **Fenêtre d'un modèle réseau** (Ollama, llama-server) : traitée comme celle d'un fichier local (`configured`) ; à vérifier au développement qu'une exécution (story 4) ne la déclare pas « non lancé » à tort.
8. **Plafond de 1 à 2 vérifications dans le formulaire** contre 1 à 3 dans le contrat : voulu (consigne de la story), pas de changement du contrat.
9. **Bouton « Ouvrir Évaluer l'agent »** : convention `window.agentEval.openView` à valider avec la story 4 (ou export ES partagé de `agent-eval.js`, plus propre : à trancher au démarrage de la story 4).
