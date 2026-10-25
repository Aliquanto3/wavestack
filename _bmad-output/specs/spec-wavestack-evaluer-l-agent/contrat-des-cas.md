# Contrat d'un cas d'agent (CAP-1, CAP-2)

Contrat partagé par les stories 2 à 5. La story 1 le code tel quel ; un changement passe par la spec.

## Forme d'un cas

Même forme pour un cas fourni (`content/agent_cases.yaml`, surcouches `content/i18n/{en,de}/`) et un cas de séance (`data_dir()/agent_cases.json`). Modèle pydantic à `extra="forbid"`, comme `Scenario`.

| Champ | Type | Règle |
|---|---|---|
| `id` | str | Unique sur fournis + séance. Fourni : clé lisible (`heure_get_datetime`). Séance : `u` + identifiant généré. |
| `title_text` | str | Une ligne. |
| `brick` | str \| None | Brique du programme illustrée (obligatoire pour un cas fourni). |
| `symptom_text` | str | Ce qui a raté, une phrase (« invente un chemin de fichier »). |
| `assertion_text` | str | Ce qui doit être vrai, une phrase (« n'appelle `read_file` qu'avec un fichier listé »). |
| `prompt` | str | Message envoyé. |
| `history` | list[{user, assistant}] | Facultatif. Échanges placés dans l'historique avant le prompt. |
| `bricks`, `tools`, `hooks`, `skills`, `mcp_servers` | comme `Scenario` | Configuration complète, appliquée comme un scénario ; `None` garde les valeurs de lancement. |
| `window` | int \| None | Fenêtre exigée. Différente de la fenêtre courante : cas « non lancé ». |
| `system_prompt` | str \| None | `None` : prompt système de la session (cas fournis : toujours `None`). |
| `approval` | `refuse` \| `approve` | Réponse du harnais à une validation humaine (H5) pendant l'exécution. Défaut `refuse`. |
| `on_overflow` | `none` \| `compaction` \| `sliding_window` | Stratégie appliquée si le tour est refusé pour débordement, puis le message repart (V1.4). Défaut `none`. |
| `max_model_calls` | int ≥ 1 | Plafond d'appels au modèle, toujours vérifié (`model_calls_max`). |
| `checks` | list, 1 à 3 | Vérifications du catalogue ci-dessous, hors `model_calls_max`. |
| `provenance` | objet | `source` (`fourni`, `séance`, `recette`), `date` (ISO), `model` (`ActiveModel` du tour d'origine, ou `None`), `turn_id` (tour d'origine, ou `None`), `system_prompt_text` (celui du tour d'origine, gardé même s'il n'est pas figé), `fixed_in` (str \| None, « corrigé dans »). |

Fichier de séance : `{"version": 1, "cases": [...]}`, écrit atomiquement (temporaire puis `os.replace`, comme `memory.write_memory`). Fichier illisible : la vue le dit et propose « Effacer mes cas » ; les cas fournis restent jouables.

## Journal d'un cas

- **Enveloppes lues** : celles dont le `turn_id` est un tour lancé par le cas : le tour du prompt, le tour de compaction éventuel et le message renvoyé ensuite. Tous contextes (principal et `sub{n}`).
- **Témoin** : le `turn_ended` du dernier tour de message. Absent (annulation, journal tronqué) : toutes les vérifications échouent, raison « tour incomplet ».
- **Fonction** : `verify(case, envelopes) -> CaseVerdict`, pure, sans I/O ni modèle. Elle sert aussi au formulaire sur le tour d'origine (CAP-3).

## Catalogue des vérifications (fermé)

| `kind` | Paramètres | Réussit si | Événements lus |
|---|---|---|---|
| `tool_called` | `tool`, `before` (facultatif) | au moins un `tool_started` de `tool` ; avec `before`, le premier `tool` précède le premier `before` (`before` jamais appelé : réussit) | `tool_started` |
| `tool_not_called` | `tool` | aucun `tool_started` de `tool` (et témoin présent) | `tool_started` |
| `argument_never` | `tool`, `argument`, `contains` | aucun `tool_started` de `tool` dont `arguments[argument]`, en texte, contient `contains` (casse ignorée) | `tool_started` |
| `model_calls_max` | (le `max_model_calls` du cas) | nombre de `model_call_started` ≤ plafond | `model_call_started` |
| `answer_contains` | `text` | la réponse finale contient `text`, casse et espaces multiples ignorés. Réponse finale : les `model_delta` de canal `text` du dernier appel du contexte principal, ou `turn_ended.text` s'il est présent | `model_delta`, `turn_ended` |
| `hook_decided` | `hook`, `decision` (`block` \| `ask_human`) | au moins un `hook_decided` de ce hook avec cette décision | `hook_decided` |
| `subagent_called` | aucun | au moins un `subagent_started` | `subagent_started` |
| `turn_completed` | aucun | tous les tours du cas finissent `completed` et aucun `harness_error` | `turn_ended`, `harness_error` |

Règle d'or : un événement attendu absent fait échouer. Les vérifications négatives (`tool_not_called`, `argument_never`) n'ont pour événement que le témoin.

## Verdict

```
CheckVerdict = {kind, params, passed: bool, reason_text, seq: int | None}
CaseVerdict  = {case_id, passed: bool, checks: [CheckVerdict], model_calls: int}
```

- `seq` : l'enveloppe qui a décidé (l'appel fautif, ou la fin de tour pour une absence) ; la vue la met en évidence dans la trace.
- `reason_text` en français, surcouches en et de, chiffres compris (« 4 appels au modèle pour un plafond de 3 »).
- `passed` du cas : toutes ses vérifications réussies, plafond compris.

## Statuts d'exécution (CAP-4)

`passed`, `failed`, `not_run` avec une raison : `window` (fenêtre exigée), `cancelled`, `budget` (`max_session_usd` atteint). Agrégat : « n réussis sur m lancés », les non lancés comptés à part. Avec k = 3 : réussites sur k, pass@3 (au moins une), pass^3 (toutes).

## Cas fournis visés (CAP-2)

Liste arrêtée au point de contrôle de la story 2, après mesure des plafonds. Vérifications envisagées :

| Cas | Brique | Vérifications |
|---|---|---|
| L'heure | Outils | `tool_called get_datetime` ; l'assertion vise deux appels au plus, le plafond retenu reste le mesuré (s'ils divergent, le point de contrôle tranche) |
| Pas de chemin inventé | Outils | `argument_never read_file path <nom inexistant>` ; plus une vérification positive (`answer_contains` ou `tool_called search_documents`) |
| H1 bloque `confidentiel/` | Hooks | `hook_decided h1 block` ; `argument_never` facultatif |
| Consigne de la mémoire globale | Mémoire globale | `answer_contains` sur la consigne d'une entrée de démonstration |
| `TLV-7731-QZ` après compaction | Contexte long | `window: 4096`, `history` qui déborde, `on_overflow: compaction` ; `answer_contains TLV-7731-QZ` |
| Délégation au sous-agent | Sous-agent | `subagent_called` ; `turn_completed` |
| `search_documents` avant `read_file` | RAG | `tool_called search_documents before read_file` |
| H5 refuse, pas de rappel | Hooks | `approval: refuse` ; `hook_decided h5 ask_human` ; plafond qui interdit le rappel |
| Défaillance de recette | selon le cas | provenance `recette`, `fixed_in` renseigné |

Chaque cas fourni : un test le joue avec un faux moteur scripté (il réussit) et avec un faux moteur qui ne fait rien (il échoue). Plafond mesuré par l'outil de la story 2 : trois exécutions sur le modèle local, maximum observé + 1.
