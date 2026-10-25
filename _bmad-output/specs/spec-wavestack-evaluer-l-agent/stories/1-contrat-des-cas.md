---
title: 'Story 1 : contrat d''un cas et moteur de vérification sur le journal'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-evaluer-l-agent/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-evaluer-l-agent/contrat-des-cas.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-evaluer-l-agent/brownfield.md'
---

## Intent

**Problem:** les stories 2 à 5 ont besoin d'un modèle de cas, d'un chargement des cas fournis et de séance, et d'une vérification pure sur le journal d'un tour.

**Approach:** module `src/wavestack/agent_eval/` sans route ni front : `cases.py` (modèles et cas fournis), `checks.py` (`verify`, pure), `store.py` (fichier de séance). Noms exactement ceux de `contrat-des-cas.md`.

## Contrat livré

- `cases.AgentCase` (`extra="forbid"`) : champs du contrat ; `checks` 1 à 3, union discriminée par `kind` (`ToolCalledCheck`, `ToolNotCalledCheck`, `ArgumentNeverCheck`, `AnswerContainsCheck`, `HookDecidedCheck`, `SubagentCalledCheck`, `TurnCompletedCheck`) ; `model_calls_max` jamais écrit dans `checks`, tiré de `max_model_calls`. `Provenance`, `HistoryExchange`, `CheckKind`, `RunStatus`, `NotRunReason`, `ProvenanceSource`.
- `cases.load_provided_cases(lang=None, known=None)` : `content/agent_cases.yaml` (`cases: [...]`) ou sa traduction ; fichier absent : `[]`. Refuse un cas sans `brick`, avec `system_prompt` ou de provenance `séance`, un id en double, un id de configuration inconnu (avec `known`).
- `checks.verify(case, envelopes, lang="fr") -> CaseVerdict` : vérifications du cas dans l'ordre, puis `model_calls_max` (tous contextes). Textes par `msg` (`messages.yaml`, section `agent_eval`, fr, en, de), comme un hook.
- `store` : `read_session_cases`, `write_session_cases` (atomique), `add_session_case`, `delete_session_case`, `clear_session_cases`, `SessionCasesUnreadable` ; chemin `config.agent_cases_path()`.

## Décisions tranchées

- Témoin : `turn_ended` (contexte principal) du dernier `turn_started` de `kind` `message`. Sans `turn_started` : tour incomplet. Témoin d'un statut autre que `completed` : tour incomplet aussi (raison avec le statut, `seq` du témoin).
- `turn_completed` : un tour fini `overflow`, suivi d'un autre tour de message, avec `on_overflow` différent de `none`, est le chemin prévu du cas : ni son statut ni ses `harness_error` ne comptent.
- `seq` : premier événement qui fait réussir ou fautif ; pour une absence ou une négative réussie, le témoin ; plafond dépassé : l'appel numéro plafond + 1 ; tour incomplet : `None`.
- `tool_called` avec `before` en échec : `seq` du premier `before`.
- Réponse finale (`answer_contains`) : `turn_ended.text` s'il est présent ; sinon les `model_delta` de canal `text` du contexte principal après le dernier `model_call_started` principal du dernier tour de message.
- Fichier de séance illisible (JSON, version, clé en trop, cas invalide, id en double, provenance autre que `séance`) : `SessionCasesUnreadable` ; `add` ne l'écrase jamais, `clear` le répare.

## Tests

`tests/test_agent_eval_checks.py`, `tests/test_agent_eval_store.py` : chaque vérification dans les deux sens, témoin absent, sous-agent compté dans le plafond, écriture atomique, fichier illisible, `reset()` sans effet sur le fichier.

## Reports

Aucun.

## Revue

### Passe 1 (2026-10-25, SHA revu 214f9289)

- Important, medium, second avis : cas fourni sans vérification positive accepté (`turn_completed` seul passe sur un moteur inactif). Corrigé : `cases.POSITIVE_KINDS` exigé par `load_provided_cases` ; tests dans les deux sens.
- Important, medium, second avis : la session émet toujours `turn_ended` (son `finally`), un tour `cancelled`, `limit`, `error`, `overflow` ou `blocked` passait `answer_contains` ou `tool_called`. Corrigé : témoin non `completed` = tour incomplet pour toutes les vérifications (clé `agent_eval.incomplete_status`, `seq` du témoin) ; tolérance overflow intacte (tours antérieurs) ; outil bloqué par H1 ou refusé par H5 : tour `completed` (test). Contrat précisé dans `contrat-des-cas.md`.
- Nit, low, second avis : `version: true` accepté. Corrigé (`type(version) is int`), test.
- Nit, low, second avis : `Provenance.date` non validée. Corrigé (date ou date-heure ISO), tests.
- Nit, low, second avis : temporaire à nom fixe laissé sur disque si `os.replace` échoue. Corrigé (`tempfile.mkstemp` dans le dossier, supprimé en cas d'échec), test. `memory.write_memory` garde le même défaut : Pre-existing, non corrigé.
- Complexité : 0 constat (quelques parcours O(n) par vérification, au plus 4 vérifications).

