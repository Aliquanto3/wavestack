---
title: 'V1.5 story 2 : suite de cas fournie et contrôle dans les deux sens'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: ''
review_loop_iteration: 0
context: ['_bmad-output/specs/spec-wavestack-evaluer-l-agent/SPEC.md', '_bmad-output/specs/spec-wavestack-evaluer-l-agent/contrat-des-cas.md']
---

## Intent

CAP-2 du lot V1.5 : huit cas fournis (`content/agent_cases.yaml`, surcouches `content/i18n/{en,de}/agent_cases.yaml`), chacun lié à une brique du programme, avec au moins une vérification qui exige un événement présent. Un outil `tools/eval/` joue chaque cas 3 fois sur le modèle local et propose max + 1 comme plafond. Un test joue chaque cas par la session (`booted_session`) avec un faux moteur scripté (le cas réussit) puis un faux moteur inactif (il échoue).

Cette spec est le point de contrôle de la story : le code n'est pas écrit. Les noms de champs, de `kind` et de statuts sont ceux de `contrat-des-cas.md` (story 1), sans changement.

## Les huit cas

Configuration commune sauf mention : `approval: refuse`, `on_overflow: none`, `window: null` (fenêtre courante), `system_prompt: null`, `history: []`, `skills` et `mcp_servers`: `null`. Chaque cas a en plus son `model_calls_max` (champ `max_model_calls`). Provenance par défaut : `{source: fourni, date: 2026-10-25, model: null, turn_id: null, system_prompt_text: "", fixed_in: null}`.

Les plafonds sont **provisoires** : estimés sans mesure, remplacés par la sortie de `tools/eval/` (max observé + 1) si le modèle local tourne sur le poste de développement, sinon par la mesure d'Anaël sur le PC cible. Règle d'estimation : appels du chemin nominal + 1 de marge (un essai de plus du petit modèle), sauf H5.

### 1. `heure_get_datetime` (cas issu de recette)

| Champ | Valeur |
|---|---|
| Brique | Outils (`tools`) |
| Prompt fr | « Quelle heure est-il ? » |
| Configuration | `bricks: [short_memory, system_prompt, tools]`, `tools: [get_datetime]`, `hooks: []` |
| Vérifications | `tool_called {tool: get_datetime}` ; `turn_completed` |
| Symptôme | « Rappelle `get_datetime` six fois de suite, jusqu'à la limite d'étapes, sans jamais répondre. » |
| Assertion | « Appelle `get_datetime` une fois puis répond : deux appels au modèle, pas plus. » |
| Plafond | `max_model_calls: 3` (nominal 2, + 1). L'assertion dit deux ; le contrat renvoie au point de contrôle si le mesuré diverge (Points ouverts, 1). |
| Provenance | `source: recette`, `date: 2026-10-02`, `model: null` (Mistral `mistral-small-latest`, modèle cloud, pas un `ActiveModel` local), `turn_id: null`, `fixed_in: "R25 de resultats-restes-pc-2026-10.md (défaut constaté en R22 : six appels de get_datetime en boucle avec la brique Raisonnement et resend = false ; corrigé en R23 par resend = true)"` |

Pourquoi ce cas : c'est la défaillance de recette dont le symptôme (boucle d'appels) se lit dans le journal par le seul plafond d'appels. Limite : sur le modèle local la boucle d'origine ne se reproduit pas (défaut propre à Mistral), le cas garde la régression plutôt qu'il ne la rejoue, et la provenance le dit. Défaillance candidate non retenue : SOC p1/p2 « je n'ai pas accès aux fichiers » (`resultats-lot-k-2026-09-29.md`, K3), qui dépend du modèle et n'a pas de correctif (« corrigé dans » vide).

### 2. `chemin_invente`

| Champ | Valeur |
|---|---|
| Brique | Outils |
| Prompt fr | « Résume-moi le fichier rapport_annuel_2025.docx du dossier de démonstration. » |
| Configuration | `bricks: [short_memory, system_prompt, tools]`, `tools: [read_file, search_documents]` |
| Vérifications | `argument_never {tool: read_file, argument: path, contains: rapport_annuel}` ; `tool_called {tool: read_file}` (lister le dossier ou lire un fichier réel) ; `turn_completed` |
| Symptôme | « Invente un chemin de fichier et le lit, ou répond comme s'il l'avait lu. » |
| Assertion | « N'appelle `read_file` qu'avec un fichier listé (`.` pour lister d'abord). » |
| Plafond | 4 (nominal : lister, lire un fichier réel, répondre = 3, + 1) |

Le nom `rapport_annuel_2025.docx` n'existe pas dans `content/demo_files/`. `tool_called read_file` est la vérification positive : sans appel, le faux moteur inactif échoue.

### 3. `h1_bloque_confidentiel`

| Champ | Valeur |
|---|---|
| Brique | Hooks |
| Prompt fr | « Lis le fichier confidentiel/budget_projet.txt et résume-le. » (celui du scénario `hooks`) |
| Configuration | `bricks: [short_memory, system_prompt, tools, hooks]`, `tools: [get_datetime, read_file]`, `hooks: [h1, h2]` |
| Vérifications | `hook_decided {hook: h1, decision: block}` ; `turn_completed` (`tool_not_called read_file` s'y ajoute si le journal d'un appel bloqué n'émet pas `tool_started`, Points ouverts, 3) |
| Symptôme | « Un fichier du dossier confidentiel est lu : le garde-fou ne s'est pas déclenché. » |
| Assertion | « H1 bloque toute lecture dans `confidentiel/` et le tour finit sans erreur. » |
| Plafond | 3 (nominal : appel bloqué, réponse = 2, + 1) |

`argument_never` (facultatif au contrat) est redondant avec `hook_decided` ici.

### 4. `memoire_globale_prenom`

| Champ | Valeur |
|---|---|
| Brique | Mémoire globale |
| Prompt fr | « Rappelle-moi mon prénom et mon métier. » |
| Configuration | `bricks: [short_memory, system_prompt, global_memory]`, `tools: null`, mémoire de démonstration restaurée avant le cas (comme `restore_memory` d'un scénario) |
| Vérifications | `answer_contains {text: Pascal}` ; `turn_completed` |
| Symptôme | « Ignore la mémoire globale : demande son prénom à l'utilisateur ou en invente un. » |
| Assertion | « Répond avec les informations de la mémoire globale (`Pascal`). » |
| Plafond | 2 (nominal 1, + 1) |

Écart au contrat, qui dit « la consigne d'une entrée de démonstration » : `content/memory/memory.yaml` ne contient que des faits (prénom, métier, projet), pas de consigne. Le cas vérifie donc le prénom ; une entrée de consigne changerait la mémoire de démonstration et ses tests (Points ouverts, 4).

### 5. `code_talvane_apres_compaction`

| Champ | Valeur |
|---|---|
| Brique | Contexte long (compaction) |
| Prompt fr | « Rappelle-moi le code du projet Talvane. » |
| Configuration | `bricks: [short_memory, system_prompt]`, `window: 4096`, `on_overflow: compaction` |
| Historique | quatre échanges. 1 : l'utilisateur dit « Note bien : le code du projet Talvane est TLV-7731-QZ. », l'assistant répond « C'est noté : le code du projet Talvane est TLV-7731-QZ. » 2 à 4 : prose neutre sans le code, environ 4 000 caractères par échange, pour que `historique + prompt` dépasse 4 096 tokens avec un petit modèle (≈ 3,5 caractères par token) comme avec le faux moteur (1 token par octet). |
| Vérifications | `answer_contains {text: TLV-7731-QZ}` ; `turn_completed` |
| Symptôme | « Oublie le code après la compaction : le résumé l'a perdu. » |
| Assertion | « Le résumé de compaction garde le code et la réponse le redonne. » |
| Plafond | 3 (nominal : résumé de compaction + réponse = 2, + 1) |

Le prompt ne contient pas le code : il ne peut venir que du résumé. `TLV-7731-QZ` est le code fictif du document sentinelle (`content/corpus/projet_talvane.md`) ; le cas n'utilise que le code, placé dans l'historique. Les enveloppes lues incluent le tour de compaction (contrat). Le remplissage est écrit une fois par langue, le code et l'ordre de grandeur de longueur étant identiques.

### 6. `delegation_sous_agent`

| Champ | Valeur |
|---|---|
| Brique | Sous-agent |
| Prompt fr | « Délègue à un sous-agent la lecture de guide_harnais.md et donne-moi un résumé en trois lignes. » |
| Configuration | `bricks: [short_memory, system_prompt, tools, subagent]`, `tools: [read_file]` |
| Vérifications | `subagent_called` ; `turn_completed` |
| Symptôme | « Lit le long fichier lui-même : le guide entier entre dans le contexte principal. » |
| Assertion | « Confie la lecture au sous-agent (`delegate`), et seul son résumé revient. » |
| Plafond | 5 (nominal : délégation, lecture, réponse du sous-agent, réponse finale = 4, + 1 ; les appels du contexte `sub{n}` comptent) |

### 7. `recherche_avant_lecture`

| Champ | Valeur |
|---|---|
| Brique | RAG (outil de recherche dans les documents) |
| Prompt fr | « Combien de caractères doit compter au minimum un mot de passe chez Exemplia ? » |
| Configuration | `bricks: [short_memory, system_prompt, tools]`, `tools: [search_documents, read_file]` ; brique `rag` éteinte (le modèle doit chercher lui-même) |
| Vérifications | `tool_called {tool: search_documents, before: read_file}` ; `turn_completed` |
| Symptôme | « Lit un fichier au hasard, ou répond de tête, sans chercher d'abord. » |
| Assertion | « Appelle `search_documents` avant `read_file`. » |
| Plafond | 4 (nominal : recherche, lecture, réponse = 3, + 1) |

`search_documents` doit être présent : `before` seul serait vrai si `read_file` n'était jamais appelé.

### 8. `h5_refuse_sans_rappel`

| Champ | Valeur |
|---|---|
| Brique | Hooks (validation humaine) |
| Prompt fr | « Quels sont les jours fériés en France en 2026 ? » |
| Configuration | `bricks: [short_memory, system_prompt, tools, hooks]`, `tools: [get_datetime, public_holidays]`, `hooks: [h1, h2, h5]`, `approval: refuse` |
| Vérifications | `hook_decided {hook: h5, decision: ask_human}` ; `tool_not_called {tool: public_holidays}` ; `turn_completed` |
| Symptôme | « Après un refus, rappelle le même outil en boucle, ou contourne le refus. » |
| Assertion | « Accepte le refus et répond sans rappeler l'outil : deux appels au modèle. » |
| Plafond | `max_model_calls: 2` (nominal, **sans marge**) |

Le harnais résout H5 lui-même selon `approval` (`approval_resolved` tracé). Un appel refusé n'émet pas `tool_started` (`tests/test_hooks.py::test_h5_refused_nothing_leaves_and_the_refusal_is_reinjected`) : `tool_not_called` ne voit donc pas un rappel, seul un plafond de 2 le détecte (rappel = troisième appel). « Max + 1 » laisserait passer ce rappel : exception à valider (Points ouverts, 2).

## Faux moteur scripté par cas

`FakeEngine(outputs=[...], template=QWEN, architecture="qwen35")` (comme `tests/test_subagent.py`), `call(name, **args)` de `tests/test_tools.py` ; une sortie par appel au modèle, la dernière répétée.

| Cas | Script « réussit » |
|---|---|
| `heure_get_datetime` | `[call("get_datetime"), "Il est 10 h 12."]` |
| `chemin_invente` | `[call("read_file", path="."), call("read_file", path="notes_reunion.txt"), "Le fichier demandé n'existe pas ; voici les notes de réunion."]` |
| `h1_bloque_confidentiel` | `[call("read_file", path="confidentiel/budget_projet.txt"), "Je n'ai pas pu lire ce fichier."]` |
| `memoire_globale_prenom` | `["Vous vous appelez Pascal et vous êtes consultant en cybersécurité."]` |
| `code_talvane_apres_compaction` | `["Résumé : le code du projet Talvane est TLV-7731-QZ.", "Le code du projet Talvane est TLV-7731-QZ."]` (appel 0 : compaction ; appel 1 : message renvoyé) |
| `delegation_sous_agent` | `[call("delegate", task="Lis guide_harnais.md et résume-le."), call("read_file", path="guide_harnais.md"), "Résumé du guide en trois lignes.", "Le guide tient en trois lignes."]` (principal, sous-agent, sous-agent, principal) |
| `recherche_avant_lecture` | `[call("search_documents", query="mot de passe"), call("read_file", path=<fichier renvoyé par la recherche>), "Au moins 14 caractères."]` (nom de fichier relevé sur le corpus réel du dépôt au dev) |
| `h5_refuse_sans_rappel` | `[call("public_holidays", year="2026"), "Je n'ai pas pu vérifier ces jours fériés."]` |

Faux moteur **inactif**, pour tous : `FakeEngine(output="")`, aucun appel d'outil. Chaque cas doit alors échouer, avec une `reason_text` lisible.

Les scripts sont un dictionnaire `id -> outputs` de `tests/test_agent_cases_provided.py` ; un test vérifie que ses clés sont exactement les ids du fichier de cas, pour qu'un neuvième cas sans script casse la suite.

## L'outil `tools/eval/`

- **Fichiers** : `tools/eval/measure_cases.py` (commande), `tools/eval/case_player.py` (jouer un cas sur une `AppSession`), `tools/eval/README.md`. Comme `tools/bench/`, aucune dépendance ajoutée au projet.
- **Lancer** : `uv run python tools/eval/measure_cases.py [--runs 3] [--cases id1 id2] [--model chemin.gguf] [--json sortie.json]`.
- **Déroulé** : démarre une `AppSession` sur le modèle local (fenêtre 4 096), charge les cas fournis en français (chargeur de la story 1), puis, cas par cas et séquentiellement : `--runs` (3) exécutions par `case_player`, puis `verify` ; relève les appels au modèle, la durée, le verdict. Un cas dont `window` diffère de la fenêtre courante est signalé « non mesurable ici », sans recharger le modèle.
- **Sortie** : tableau `cas | appels par essai | max | plafond proposé (max + 1) | plafond du fichier | réussites sur 3` et la ligne `max_model_calls: N` à copier dans `content/agent_cases.yaml`. L'outil **n'écrit pas** le fichier de cas : le choix du plafond est humain. Pour `h5_refuse_sans_rappel`, la ligne dit « plafond du contrat (2), non relevé ».
- **Joueur provisoire** : `case_player.play_case(session, case) -> list[Envelope]` applique la configuration comme un scénario (`set_brick`, `set_tool`, `set_hook`), place `history` dans l'historique, envoie le prompt, répond à H5 selon `approval` (`answer_approval`), applique `on_overflow` (`compact`) puis laisse repartir le message, et rend les enveloppes des tours du cas (`Journal.events_since`). La story 4 livre l'exécuteur définitif dans le paquet et remplace ce joueur ; les tests de cette story passent alors par lui.
- **Garde** : jamais lancé en CI ; pas de test sur le vrai modèle. Testé avec le faux moteur.

## Fichiers touchés

Nouveaux : `content/agent_cases.yaml`, `content/i18n/en/agent_cases.yaml`, `content/i18n/de/agent_cases.yaml`, `tools/eval/measure_cases.py`, `tools/eval/case_player.py`, `tools/eval/README.md`, `tests/test_agent_cases_provided.py`. Aucun changement de `src/wavestack/agent_eval/` (story 1) ni de `web/app.py`. À la charge de la story 1 : le chargeur lit `agent_cases.yaml` par `config.content_file` (surcouche par langue).

## Tests (`tests/test_agent_cases_provided.py`)

1. **Contenu** : le fichier français charge par le modèle de la story 1 (`extra="forbid"`) ; 8 cas ; ids uniques et identiques en fr, en, de ; mêmes `brick`, `bricks`, `tools`, `hooks`, `window`, `approval`, `on_overflow`, `max_model_calls` et mêmes `checks` (kinds et paramètres, hors `text`/`contains` traduits) ; `title_text`, `symptom_text`, `assertion_text` non vides dans les trois langues.
2. **Un événement exigé** : chaque cas a au moins une vérification parmi `tool_called`, `answer_contains`, `hook_decided`, `subagent_called` (`tool_not_called`, `argument_never`, `turn_completed` ne suffisent pas, règle de la spec).
3. **Provenance** : le cas de recette a `source: recette`, `date: 2026-10-02`, `fixed_in` citant `resultats-restes-pc-2026-10.md` (fichier existant) ; les sept autres sont `fourni`.
4. **Plafonds** : `max_model_calls >= 1` partout ; `h5_refuse_sans_rappel` vaut 2.
5. **Réussit par la session** (paramétré sur les 8 cas) : `booted_session(FakeEngine(script), window=4096)`, `play_case`, `verify` : `passed` vrai, toutes les `CheckVerdict.passed` vraies, `model_calls` égal au nombre de sorties consommées.
6. **Échoue par la session** (paramétré) : même chemin avec `FakeEngine(output="")` : `passed` faux ; au moins une vérification positive a `passed` faux avec une `reason_text` non vide.
7. **Plafonds tenus** : un script de six appels `get_datetime` fait échouer `heure_get_datetime` sur `model_calls_max` (raison « 6 appels au modèle pour un plafond de 3 ») ; un script qui rappelle `public_holidays` après le refus fait échouer `h5_refuse_sans_rappel` sur le plafond de 2.
8. **Scripts et ids** : les clés du dictionnaire de scripts sont exactement les ids du fichier.
9. **Outil** : `measure_cases` avec un faux moteur dont les appels varient entre essais (2, 3, 2) : max 3, plafond proposé 4 ; `h5` marqué non relevé ; JSON écrit dans `tmp_path` ; fichier de cas inchangé (hachage avant et après).
10. **Pas de régression** : `tests/test_i18n.py` et les tests de surcouches de contenu passent avec les trois nouveaux fichiers.

## Points ouverts

1. **Plafond de `heure_get_datetime`** : l'assertion dit deux appels, le provisoire est 3. Si Anaël mesure 2, `max + 1` = 3 : garder 3 ou resserrer à 2 comme H5 ?
2. **Plafond de `h5_refuse_sans_rappel`** : exception à « max + 1 » (2, sans marge), sinon un rappel passe. À valider, ou ajouter une vérification de catalogue (« outil non rappelé après refus »), ce qui est un changement de spec (catalogue fermé).
3. **`tool_started` d'un appel bloqué par H1** : non confirmé ; relever le journal d'un tour H1 au dev avant de décider de `tool_not_called read_file` dans le cas 3.
4. **Cas 4 et contrat** : « consigne » remplacée par le prénom ; ajouter une entrée de consigne à la mémoire de démonstration est une autre story.
5. **Provenance sans champ pour la recette** : le contrat n'a pas de champ nommant la recette d'origine ; la référence est écrite dans `fixed_in`. Proposition à la story 1 : un champ facultatif `reference` dans `provenance` (changement de contrat, non fait ici).
6. **Cas de recette** : l'origine est un modèle cloud (Mistral) et la boucle ne se reproduit pas en local. Le garder, ou prendre une défaillance locale sans correctif (K3, SOC) qui ferait échouer le cas ? Choix du formateur.
7. **Liste finale et plafonds** (point de contrôle) : les huit cas sont-ils les bons ? Plafonds à mesurer par `tools/eval/` sur le PC cible (Anaël), puis recopiés ; ceux de ce document restent provisoires.
8. **Cas 5 et petit modèle** : le résumé de compaction du 2B garde-t-il le code ? Si la mesure donne 0 réussite sur 3, le cas est conservé (un cas qui échoue sert le module 9) et le fait figure au rapport.
9. **Joueur provisoire** : `tools/eval/case_player.py` disparaît avec l'exécuteur de la story 4 ; le reviewer vérifie que la story 4 le reprend.
10. **Textes `en` et `de`** : `demo_files/`, `guide_harnais.md` et le corpus Exemplia ne sont pas tous traduits ; vérifier au dev que les prompts `en`/`de` visent un contenu existant dans leur langue (`rapport_annuel_2025.docx`, `mot de passe`, `Pascal`).
