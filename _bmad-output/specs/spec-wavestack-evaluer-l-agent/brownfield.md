# Existant et décisions d'architecture (relevé du 2026-10-25, `main` à `d4d4bb3d`)

## Journal d'événements

- **Stockage** : `Journal` en mémoire, `seq` jamais remis à zéro dans un processus, perdu au redémarrage (`trace/journal.py`, AD-2).
- **Enveloppe** : `seq`, `turn_id`, `context_id` (`sub{n}` pour le sous-agent), `call_id`, `step_id`, `kind`, `payload` (`trace/envelope.py:16`).
- **Payloads lus par les vérifications** (`trace/catalog.py`) :

| Événement | Champs | Ligne |
|---|---|---|
| `turn_started` | `message`, `replay_of`, `active_model`, `kind` (`message` \| `compaction`) | :194 |
| `turn_ended` | `status` (`TurnStatus` :189), `text` | :204 |
| `harness_error` | `message_text`, `cause` | :77 |
| `model_call_started` / `model_delta` | `phase_label` / `channel`, `text` | :455, :466 |
| `tool_started` / `tool_ended` | `tool`, `arguments`, `source` / `status` | :802, :818 |
| `limit_reached` | `limit` (`calls`, `retries`, `sub_calls`, `sub_retries`) | :833 |
| `hook_decided` | `hook`, `point`, `decision` (`HookDecision` :919) | :922 |
| `approval_requested` / `approval_resolved` | `approval_id`, `tool` / `decision` | :993, :1000 |
| `subagent_started` / `subagent_ended` | `task`, `tools` / `status`, `calls` | :1165, :1173 |
| `bricks_changed` | `bricks`, `system_prompt` | :790 |

- **Nouveaux champs** (story 4) : `turn_started` gagne `case_id` et `run_id` facultatifs, pour le badge du cas dans le chat et pour retrouver les tours d'une exécution.

## Moteur de vérification (story 1)

- **Module** : `src/wavestack/agent_eval/` (`cases.py` : modèles et chargement ; `checks.py` : `verify`, pure ; `store.py` : fichier de séance).
- **Pureté** : comme un hook (AD-13, `hooks.py:131`, vue en lecture seule), `verify` ne lit que la liste d'enveloppes reçue. Pas d'accès au `Journal`, au disque, au modèle ni à l'horloge.
- **Tests** : journaux construits à la main (listes d'`Envelope`), chaque vérification dans les deux sens, plus le cas « témoin absent ».
- **Contrat** : `contrat-des-cas.md`.

## Persistance des cas (D4)

- **Dossier** : `config.data_dir()` (`config.py:41`), `%LOCALAPPDATA%\WaveStack` sous Windows, surchargé par `WAVESTACK_DATA_DIR` en test.
- **Fichier** : `agent_cases.json`, écrit comme `memory.json` (`memory.write_memory`, `memory.py:136`, temporaire puis `os.replace`). Chemin exposé par une fonction de `config.py` à côté de `memory_path` (:1553).
- **Cas fournis** : `content/agent_cases.yaml` et surcouches, chargés par `config.content_file` dans la langue courante. Jamais modifiables ni supprimables depuis l'interface.
- **Intentions** (`web/app.py`) : enregistrer un cas, supprimer un cas de séance, effacer mes cas. Confirmation de l'effacement dans la page, jamais par une boîte de dialogue du navigateur.

## Réinitialisation (story 10)

- `AppSession.reset()` (`session/app_session.py:7217`) passe par `_reconfigure` (:7224), qui vide l'historique, `_last` et les actions armées, puis restaure la mémoire de démonstration.
- **Décision** : `reset()` ne touche ni `agent_cases.json` ni les résultats d'exécution. « Effacer mes cas » est une intention à part.
- Test : après `reset()`, les cas de séance et les exécutions sont toujours là.

## Lancer un cas (story 4)

- **Configuration** : appliquée comme un scénario (`_reconfigure`, `scenarios.py:19`), ce qui vide la conversation ; puis `history` placé dans `_history`, comme le fait `replay()` avec `_last` (:5138-5175, AD-17) ; puis le prompt par `_start`.
- **Prompt système** : celui de la session, sauf `system_prompt` du cas.
- **Fenêtre** : `set_context_window` (:2734) recharge le modèle local. Jamais appelé par une exécution : le cas est `not_run` (`window`).
- **Validation humaine** : H5 (`hooks.py:292-317`) suspend le tour en `awaiting_human`. Pendant une exécution, le harnais la résout selon `approval` (`approval_resolved`, tracé).
- **Débordement** : `on_overflow` applique la stratégie de `/api/intentions/compact` (`app.py:1661`, V1.4 story 4), puis le message repart (`_start(chained=True)`).
- **État de session** : pendant une exécution, les autres intentions sont refusées avec une raison, comme pendant un tour (`SessionState`, `catalog.py:88`). Nouvel état ou verrou : choix de la story 4, à annoncer dans son rapport.
- **Arrêt** : « Arrêter » (`stop()`) annule le tour en cours ; les cas restants passent `not_run` (`cancelled`).
- **Plafond de dépense** : `[finops] max_session_usd` (`config.py:836`) vérifié avant chaque cas ; atteint, les cas restants passent `not_run` (`budget`).
- **Bornes de boucle** : `[tools] max_calls`, `max_retries`, `subagent_max_calls` (`config.py:1170-1186`) s'appliquent sans changement.
- **Après l'exécution** : configuration d'avant rétablie (briques, sous-options, prompt système), conversation vidée.
- **Résultats** : en mémoire de session, avec les enveloppes de chaque cas (pour « Voir le tour »). Le front les demande par une route GET, comme la vue Évaluer du RAG (`/api/rag_lab/evaluation`, `rag-evaluate.js:1-12`).

## Faux moteur (tests)

- `tests/fake_engine.py` : `FakeEngine(outputs=[...])`, une sortie par appel, la dernière répétée ; `booted_session(engine, window=4096)`.
- **Scripté pour réussir** : sorties qui émettent les appels d'outil attendus puis une réponse contenant le texte attendu.
- **Inactif** : `FakeEngine(output="")` ou une réponse neutre, sans appel d'outil.
- E2E : `tools/e2e/run_e2e.py` avec `fake_local_server.py`.

## Front

- **Page** : `web/static/index.html` (Harnais). Volets : Vue humain, Contexte LLM, Orchestration ; tiroirs `.edit-drawer` (`app.css:2667`) : prompt système (:110), mémoire globale (:126).
- **Actions d'un tour** : badge de rejeu et « Comparer » (`app.js:3624-3630`, story 9b et 17) ; « En faire un cas » s'y ajoute (story 3).
- **Barre du haut** : `header.top-bar` (`index.html:272`) ; le bouton « Évaluer l'agent » s'y ajoute (story 4).
- **Nouveau module** : `web/static/agent-eval.js` (vue et formulaire), importé par `app.js`, pour limiter les conflits avec `app.js` (8 114 lignes).
- **Navigation commune** : `site-nav.js` et le `<nav class="site-nav">` des six pages ; le glossaire s'y ouvre (story 6), dans `glossary.js`.
- **Agrégats** : seule `rag-evaluate.js` moyenne aujourd'hui (règle V1.2 CAP-11) ; la vue Évaluer l'agent est la seconde exception.

## Glossaire (story 6)

- `content/glossary.yaml` et surcouches. Le glossaire du serveur MCP local (`content/mcp_local/glossary.yaml`, servi par `mcp/local_server.py:45`) reste une donnée de démonstration à part.
- Citation depuis un texte de brique ou de scénario : une syntaxe de renvoi au terme, rendue en lien qui ouvre le glossaire sur ce terme ; test que chaque terme cité existe dans les trois langues.

## Programme (story 5)

- `content/scenarios.yaml` : `program` (8 modules, `Module.duration_min` entre 30 et 60, `scenarios.py:51`), `scenarios`. Le module 9 (45 min) suit le module 8 « Cache ».
- 7 h → 7 h 45, huit → neuf modules : `docs/guide.md:78-80`, `README.md:19`, `tools/demo/compose.py:358`, `tests/test_program.py`.
- Gestes du participant écrits dans `description_text` (pas d'action scriptée).
