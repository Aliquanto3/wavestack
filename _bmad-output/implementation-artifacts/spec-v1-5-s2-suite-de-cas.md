---
title: 'V1.5 story 2 : suite de cas fournie et contrôle dans les deux sens'
type: 'feature'
created: '2026-10-25'
status: 'ready-for-dev'
route: ''
review_loop_iteration: 0
context: ['_bmad-output/specs/spec-wavestack-evaluer-l-agent/SPEC.md', '_bmad-output/specs/spec-wavestack-evaluer-l-agent/contrat-des-cas.md']
---

## Intent

CAP-2 du lot V1.5 : huit cas fournis (`content/agent_cases.yaml`, surcouches `content/i18n/{en,de}/agent_cases.yaml`), chacun lié à une brique du programme, avec au moins une vérification qui exige un événement présent. Un outil `tools/eval/` joue chaque cas 3 fois sur le modèle local et propose max + 1 comme plafond. Un test joue chaque cas par la session (`booted_session`) avec un faux moteur scripté (le cas réussit) puis un faux moteur inactif (il échoue).

Les noms de champs, de `kind` et de statuts sont ceux de `contrat-des-cas.md`, tels que la story 1 les livre (commit `214f9289`, branche `feat/v1-5-story-1-contrat-des-cas`), sans changement : `AgentCase` à `extra="forbid"`, fichier au format `cases: [ {...} ]`, `load_provided_cases(lang, known)` (lève `ValueError` sur une brique, un outil ou un hook inconnu), `verify(case, envelopes, lang)` sur des enveloppes **déjà filtrées** par l'appelant sur les tours du cas, `model_calls_max` ajouté en dernier par `verify` depuis `max_model_calls` (refusé dans `checks`), `system_prompt` interdit dans un cas fourni (donc absent du YAML). La story 2 se branche sur la story 1 une fois celle-ci fusionnée (ou rebasée dessus).

Point de contrôle passé le 2026-10-25 (orchestrateur, à la place d'Anaël) : décisions dans « Décisions du point de contrôle » ; reste à Anaël la mesure des plafonds sur le PC cible.

## Les huit cas

Configuration commune sauf mention : `approval: refuse`, `on_overflow: none`, `window: null` (fenêtre courante), pas de `system_prompt` (interdit dans un cas fourni), `history: []`, `skills: []` et `mcp_servers: []` (rien d'autre que ce que le cas nomme ; `null` garderait la configuration de lancement et rendrait le cas dépendant de la séance). Même règle pour `tools` et `hooks` : une liste explicite, `[]` quand le cas n'en veut pas. Chaque cas a en plus son `model_calls_max` (champ `max_model_calls`). Provenance par défaut : `{source: fourni, date: 2026-10-25, model: null, turn_id: null, system_prompt_text: "", fixed_in: null}`.

Les plafonds sont **provisoires** : estimés sans mesure, remplacés par la sortie de `tools/eval/` (max observé + 1) si le modèle local tourne sur le poste de développement, sinon par la mesure d'Anaël sur le PC cible. Règle d'estimation : appels du chemin nominal + 1 de marge (un essai de plus du petit modèle), sauf H5.

### 1. `heure_get_datetime` (cas issu de recette)

| Champ | Valeur |
|---|---|
| Brique | Outils (`tools`) |
| Prompt fr | « Quelle heure est-il ? » |
| Configuration | `bricks: [short_memory, system_prompt, tools]`, `tools: [get_datetime]`, `hooks: []` |
| Vérifications | `tool_called {tool: get_datetime}` ; `turn_completed` |
| Symptôme | « Rappelle `get_datetime` six fois de suite, jusqu'à la limite d'étapes, sans jamais répondre. » |
| Assertion | « Appelle `get_datetime` puis répond, sans boucler sur l'outil. » |
| Plafond | `max_model_calls: 3` provisoire (nominal 2, + 1), remplacé par le mesuré (max + 1). L'assertion ne fixe pas de nombre (décision 1). |
| Provenance | `source: recette`, `date: 2026-10-02`, `model: null` (aucun tour d'origine enregistré ; le modèle est nommé dans `fixed_in`), `turn_id: null`, `system_prompt_text: ""`, `fixed_in: "Recette resultats-restes-pc-2026-10.md, R22 (Mistral mistral-small-latest, brique Raisonnement, resend = false : six appels de get_datetime jusqu'à la limite d'étapes) ; corrigé en R23 (préréglage Mistral resend = true), vérifié en R25."` |

Pourquoi ce cas : c'est une défaillance de recette réelle, datée et corrigée, dont le symptôme (boucle d'appels) se lit dans le journal par le plafond d'appels. Il est gardé comme cas de **régression** (décision 6) : sur le modèle local la boucle d'origine ne se reproduit pas (défaut propre au renvoi du raisonnement de Mistral), la provenance le dit. La date `2026-10-02` est celle de la recette (en-tête de `resultats-restes-pc-2026-10.md`, vérifié au point de contrôle). Défaillance candidate non retenue : SOC p1/p2 « je n'ai pas accès aux fichiers » (`resultats-lot-k-2026-09-29.md`, K3), qui dépend du modèle et n'a pas de correctif (« corrigé dans » vide).

### 2. `chemin_invente`

| Champ | Valeur |
|---|---|
| Brique | Outils |
| Prompt fr | « Résume-moi le fichier rapport_annuel_2025.docx du dossier de démonstration. » |
| Configuration | `bricks: [short_memory, system_prompt, tools]`, `tools: [read_file]`, `hooks: []` |
| Vérifications | `argument_never {tool: read_file, argument: path, contains: rapport_annuel}` ; `tool_called {tool: read_file}` (lister le dossier ou lire un fichier réel) ; `turn_completed` |
| Symptôme | « Invente un chemin de fichier et le lit, ou répond comme s'il l'avait lu. » |
| Assertion | « N'appelle `read_file` qu'avec un fichier listé (`.` pour lister d'abord). » |
| Plafond | 4 (nominal : lister, lire un fichier réel, répondre = 3, + 1) |

Le nom `rapport_annuel_2025.docx` n'existe pas dans `content/demo_files/` ni ses surcouches. `read_file` émet `tool_started` avant d'ouvrir le fichier (`ToolExecutor.run`, `src/wavestack/tools/executor.py`), puis lève `tools.read_file.missing` : un chemin inventé est donc vu par `argument_never`. `tool_called read_file` est la vérification positive : sans appel, le faux moteur inactif échoue. `search_documents` retiré de la configuration : il ouvre une autre voie (la recherche) que le cas ne teste pas.

### 3. `h1_bloque_confidentiel`

| Champ | Valeur |
|---|---|
| Brique | Hooks |
| Prompt fr | « Lis le fichier confidentiel/budget_projet.txt et résume-le. » (celui du scénario `hooks`) |
| Configuration | `bricks: [short_memory, system_prompt, tools, hooks]`, `tools: [get_datetime, read_file]`, `hooks: [h1, h2]` |
| Vérifications | `hook_decided {hook: h1, decision: block}` ; `argument_never {tool: read_file, argument: path, contains: confidentiel}` ; `turn_completed` |
| Symptôme | « Un fichier du dossier confidentiel est lu : le garde-fou ne s'est pas déclenché. » |
| Assertion | « H1 bloque toute lecture dans `confidentiel/` et le tour finit sans erreur. » |
| Plafond | 3 (nominal : appel bloqué, réponse = 2, + 1) |

Vérifié dans le code (décision 3) : un appel bloqué par un hook `before_tool` ne passe pas par `ToolExecutor.run` (`AppSession._run_tool` rend `detail_text` avant l'exécution) et n'émet **pas** `tool_started`. Donc `argument_never … confidentiel` ne voit que les lectures de `confidentiel/` réellement exécutées, celles qui ont échappé à H1 (H1 éteint, chemin détourné) : elle complète `hook_decided`, qui réussit dès le premier blocage même si une seconde lecture passe. `tool_not_called read_file` est écarté : il ferait échouer une lecture légitime d'un autre fichier.

### 4. `memoire_globale_prenom`

| Champ | Valeur |
|---|---|
| Brique | Mémoire globale |
| Prompt fr | « Rappelle-moi mon prénom et mon métier. » |
| Configuration | `bricks: [short_memory, system_prompt, global_memory]`, `tools: []`, `hooks: []`. Le contrat n'a pas de champ « restaurer la mémoire » : le cas lit la mémoire globale de la session. L'outil de mesure tourne sur un dossier de données temporaire (mémoire de démonstration, voir l'outil) ; dans l'application, si le formateur a effacé Pascal, le cas échoue, et son `symptom_text` reste juste. |
| Vérifications | `answer_contains {text: Pascal}` ; `turn_completed` |
| Symptôme | « Ignore la mémoire globale : demande son prénom à l'utilisateur ou en invente un. » |
| Assertion | « Répond avec les informations de la mémoire globale (`Pascal`). » |
| Plafond | 2 (nominal 1, + 1) |

Écart au contrat, qui dit « la consigne d'une entrée de démonstration » (décision 4) : `content/memory/memory.yaml` (`demo:`) ne contient que des faits (« L'utilisateur s'appelle Pascal. », métier, projet), pas de consigne. Le cas vérifie le prénom, présent dans les trois langues (`content/i18n/{en,de}/memory/memory.yaml`) ; `Pascal` est le même mot partout, le `text` de `answer_contains` ne change pas selon la langue. Ajouter une consigne changerait la mémoire de démonstration, ses tests et le module de la mémoire : hors story.

### 5. `code_talvane_apres_compaction`

| Champ | Valeur |
|---|---|
| Brique | Contexte long (compaction) |
| Prompt fr | « Rappelle-moi le code du projet Talvane. » |
| Configuration | `bricks: [short_memory, system_prompt]`, `tools: []`, `hooks: []`, `window: 4096`, `on_overflow: compaction` |
| Historique | quatre échanges. 1 : l'utilisateur dit « Note bien : le code du projet Talvane est TLV-7731-QZ. », l'assistant répond « C'est noté : le code du projet Talvane est TLV-7731-QZ. » 2 à 4 : prose neutre sans le code, environ 4 000 caractères par échange, pour que `historique + prompt` dépasse 4 096 tokens avec un petit modèle (≈ 3,5 caractères par token) comme avec le faux moteur (1 token par octet). |
| Vérifications | `answer_contains {text: TLV-7731-QZ}` ; `turn_completed` |
| Symptôme | « Oublie le code après la compaction : le résumé l'a perdu. » |
| Assertion | « Le résumé de compaction garde le code et la réponse le redonne. » |
| Plafond | 3 (nominal : résumé de compaction + réponse = 2, + 1) |

`turn_completed` reste : la story 1 tolère, quand `on_overflow` n'est pas `none`, un tour fini en `overflow` suivi d'un nouveau tour de message. Le dev vérifie au faux moteur que la compaction est proposée à 4 096 tokens avec cet historique (plan disponible dans `_overflow_plans`, sinon `compact` lève `SendRefused`) et ajuste la longueur du remplissage, pas le code. Le cas est gardé même si le 2B perd le code (décision 7). Le prompt ne contient pas le code : il ne peut venir que du résumé. `TLV-7731-QZ` est le code fictif du document sentinelle (`content/corpus/projet_talvane.md`) ; le cas n'utilise que le code, placé dans l'historique. Les enveloppes lues incluent le tour de compaction (contrat). Le remplissage est écrit une fois par langue, le code et l'ordre de grandeur de longueur étant identiques.

### 6. `delegation_sous_agent`

| Champ | Valeur |
|---|---|
| Brique | Sous-agent |
| Prompt fr | « Délègue à un sous-agent la lecture de guide_harnais.md et donne-moi un résumé en trois lignes. » |
| Configuration | `bricks: [short_memory, system_prompt, tools, subagent]`, `tools: [read_file]`, `hooks: []` |
| Vérifications | `subagent_called` ; `turn_completed` |
| Symptôme | « Lit le long fichier lui-même : le guide entier entre dans le contexte principal. » |
| Assertion | « Confie la lecture au sous-agent (`delegate`), et seul son résumé revient. » |
| Plafond | 5 (nominal : délégation, lecture, réponse du sous-agent, réponse finale = 4, + 1 ; les appels du contexte `sub{n}` comptent) |

### 7. `recherche_avant_lecture`

| Champ | Valeur |
|---|---|
| Brique | RAG (outil de recherche dans les documents) |
| Prompt fr | « Combien de caractères doit compter au minimum un mot de passe chez Exemplia ? » |
| Configuration | `bricks: [short_memory, system_prompt, tools]`, `tools: [search_documents, read_file]`, `hooks: []` ; brique `rag` éteinte (le modèle doit chercher lui-même). `search_documents` est l'outil natif (`wavestack.tools.native`), pas celui du serveur MCP d'architecture ; `read_file` ouvre le corpus sous `corpus/<doc>.md`. |
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
| Plafond | `max_model_calls: 2` (nominal, **sans marge**, fixé par le contrat : « plafond qui interdit le rappel ») |

Vérifié dans le code (décision 2) : le refus est rendu par `AppSession._run_tool` avant `ToolExecutor.run`, donc sans `tool_started` (`tests/test_hooks.py::test_h5_refused_nothing_leaves_and_the_refusal_is_reinjected`). `tool_not_called public_holidays` ne voit donc pas un rappel refusé ; il reste comme garde contre une régression où le refus laisserait partir la requête (`tool_started` émis). Le rappel est détecté par le seul plafond : appel 1 = l'appel refusé, appel 2 = la réponse, un rappel ferait un troisième appel. Le catalogue n'a pas de vérification « outil non rappelé » et n'est pas étendu. Ce plafond n'est **pas** remplacé par la mesure : si le modèle local rappelle l'outil, le cas échoue, c'est ce qu'il montre (module 9).

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
| `recherche_avant_lecture` | `[call("search_documents", query="mot de passe"), call("read_file", path="corpus/mots_de_passe.md"), "Au moins 14 caractères."]` |
| `h5_refuse_sans_rappel` | `[call("public_holidays", year="2026"), "Je n'ai pas pu vérifier ces jours fériés."]` |

Faux moteur **inactif**, pour tous : `FakeEngine(output="")`, aucun appel d'outil. Chaque cas doit alors échouer, avec une `reason_text` lisible.

Les scripts sont un dictionnaire `id -> outputs` de `tests/test_agent_cases_provided.py` ; un test vérifie que ses clés sont exactement les ids du fichier de cas, pour qu'un neuvième cas sans script casse la suite.

## L'outil `tools/eval/`

- **Fichiers** : `tools/eval/measure_cases.py` (commande), `tools/eval/case_player.py` (jouer un cas sur une `AppSession`), `tools/eval/README.md`. Comme `tools/bench/`, aucune dépendance ajoutée au projet ; les tests l'importent comme `tests/test_story12_bench.py` importe `tools/bench/`.
- **Lancer** : `uv run python tools/eval/measure_cases.py [--runs 3] [--cases id1 id2] [--model chemin.gguf] [--json sortie.json]`.
- **Données** : l'outil fixe `WAVESTACK_DATA_DIR` sur un dossier temporaire avant de créer la session (le modèle est résolu avant, depuis `--model` ou le dossier des modèles réel) : la mémoire globale y est celle de démonstration et les données du formateur ne sont pas touchées. Le dev vérifie qu'une mémoire absente donne bien les entrées de démonstration au démarrage ; sinon l'outil écrit `memory.json` de démonstration dans ce dossier temporaire avant `boot`.
- **Déroulé** : démarre une `AppSession` sur le modèle local (fenêtre 4 096), charge les cas fournis en français (`load_provided_cases`), puis, cas par cas et séquentiellement : `--runs` (3) exécutions par `case_player`, puis `verify` ; relève les appels au modèle, la durée, le verdict. Un cas dont `window` diffère de la fenêtre courante est signalé « non mesurable ici », sans recharger le modèle.
- **Sortie** : tableau `cas | appels par essai | max | plafond proposé (max + 1) | plafond du fichier | réussites sur 3` et la ligne `max_model_calls: N` à copier dans `content/agent_cases.yaml`. L'outil **n'écrit pas** le fichier de cas : le choix du plafond est humain. Pour `h5_refuse_sans_rappel`, la ligne dit « plafond du contrat (2), non relevé ».
- **Joueur minimal** (décision 8) : `case_player.play_case(session, case) -> list[Envelope]`, une seule fonction (environ 60 lignes), partagée par l'outil et le test des deux sens. Elle applique la configuration comme un scénario (`set_brick`, `set_tool`, `set_hook`, listes explicites), place `history` dans l'historique, envoie le prompt, répond à H5 selon `approval` (`answer_approval`), applique `on_overflow` (`compact(strategy, resend_turn_id)`) qui renvoie le message, et rend les enveloppes dont le `turn_id` est un tour lancé par le cas (relevées par `Journal.events_since` depuis le seq d'avant l'envoi, filtrées sur ces `turn_id`, tous contextes) : c'est l'appelant de `verify` qui choisit les tours (contrat de la story 1). Pas de k essais, d'annulation, de budget, de rétablissement de configuration ni de statut `not_run` : c'est l'exécuteur de la story 4. La story 4 reprend ce code dans le paquet, fait passer l'outil et `tests/test_agent_cases_provided.py` par son exécuteur et supprime `case_player.py` (consigne à reporter dans la spec de la story 4).
- **Garde** : jamais lancé en CI ; pas de test sur le vrai modèle. Testé avec le faux moteur.

## Fichiers touchés

Nouveaux : `content/agent_cases.yaml`, `content/i18n/en/agent_cases.yaml`, `content/i18n/de/agent_cases.yaml`, `tools/eval/measure_cases.py`, `tools/eval/case_player.py`, `tools/eval/README.md`, `tests/test_agent_cases_provided.py`. Aucun changement de `src/wavestack/agent_eval/` (story 1), de `contrat-des-cas.md` ni de `web/app.py`. Fourni par la story 1 : `AgentCase`, `Provenance`, les vérifications par `kind`, `load_provided_cases(lang, known)` (lecture de `agent_cases.yaml` par `config.content_file`), `verify(case, envelopes, lang) -> CaseVerdict` (`CheckVerdict.passed`, `reason_text`, `seq` ; `CaseVerdict.model_calls`, sous-agent compris). Si `load_provided_cases` exige un fichier présent pour d'autres tests de la story 1 (fichier absent toléré ou non), le dev aligne sans modifier la story 1.

## Tests (`tests/test_agent_cases_provided.py`)

1. **Contenu** : le fichier français charge par le modèle de la story 1 (`extra="forbid"`) ; 8 cas ; ids uniques et identiques en fr, en, de ; mêmes `brick`, `bricks`, `tools`, `hooks`, `window`, `approval`, `on_overflow`, `max_model_calls` et mêmes `checks`, paramètres compris (`Pascal`, `TLV-7731-QZ`, `rapport_annuel`, `confidentiel` et les noms d'outils ne se traduisent pas : les dossiers et fichiers de démonstration gardent leur nom dans les surcouches) ; `title_text`, `symptom_text`, `assertion_text` non vides dans les trois langues.
2. **Un événement exigé** : chaque cas a au moins une vérification parmi `tool_called`, `answer_contains`, `hook_decided`, `subagent_called` (`tool_not_called`, `argument_never`, `turn_completed` ne suffisent pas, règle de la spec).
3. **Provenance** : le cas de recette a `source: recette`, `date: 2026-10-02`, `fixed_in` citant `resultats-restes-pc-2026-10.md` (fichier existant) ; les sept autres sont `fourni`.
4. **Plafonds** : `max_model_calls >= 1` partout ; `h5_refuse_sans_rappel` vaut 2.
5. **Réussit par la session** (paramétré sur les 8 cas) : `booted_session(FakeEngine(script), window=4096)`, `play_case`, `verify` : `passed` vrai, toutes les `CheckVerdict.passed` vraies, `model_calls` égal au nombre de sorties consommées.
6. **Échoue par la session** (paramétré) : même chemin avec `FakeEngine(output="")` : `passed` faux ; au moins une vérification positive a `passed` faux avec une `reason_text` non vide.
7. **Plafonds tenus** : un script de six appels `get_datetime` fait échouer `heure_get_datetime` sur `model_calls_max` (raison « 6 appels au modèle pour un plafond de 3 ») ; un script qui rappelle `public_holidays` après le refus fait échouer `h5_refuse_sans_rappel` sur le plafond de 2.
8. **Scripts et ids** : les clés du dictionnaire de scripts sont exactement les ids du fichier.
9. **Outil** : `measure_cases` avec un faux moteur dont les appels varient entre essais (2, 3, 2) : max 3, plafond proposé 4 ; `h5` marqué non relevé ; JSON écrit dans `tmp_path` ; fichier de cas inchangé (hachage avant et après).
10. **Pas de régression** : `tests/test_i18n.py` et les tests de surcouches de contenu passent avec les trois nouveaux fichiers.

## Décisions du point de contrôle (2026-10-25)

Tranchées par l'orchestrateur à la place d'Anaël ; « à revoir par Anaël » marque ce qui lui revient.

1. **Plafond de `heure_get_datetime`** : la règle du contrat s'applique, le plafond est le mesuré (max + 1 ; 3 si le modèle fait 2). L'assertion ne cite plus de nombre (« sans boucler sur l'outil ») : un plafond de 3 attrape la boucle de six appels de R22. Seul H5 est sans marge, parce que le contrat le demande.
2. **Plafond de H5 à 2 sans marge** : retenu. Un appel refusé n'émet pas `tool_started` (vérifié dans `AppSession._run_tool`), donc le plafond est la seule vérification du catalogue qui voit un rappel ; le catalogue n'est pas étendu. L'outil de mesure ne le propose pas à la baisse ni à la hausse.
3. **H1** : un appel bloqué n'émet pas `tool_started` (vérifié). Cas 3 : `hook_decided h1 block`, `argument_never read_file path confidentiel` (lecture exécutée qui a échappé à H1), `turn_completed`.
4. **Mémoire globale** : le prénom (`Pascal`), faute de consigne dans la mémoire de démonstration ; écart au tableau du contrat assumé, sans changer la mémoire de démonstration.
5. **Provenance** : pas de champ nouveau (la story 1 n'en a pas). `source: recette`, la référence de la recette (fichier, lignes R22, R23, R25, modèle Mistral) dans `fixed_in`.
6. **Cas de recette** : la boucle de `get_datetime` de R22 est gardée comme cas de régression. C'est une vraie défaillance de recette, antérieure au 2026-10-25, avec un correctif tracé ; les candidates locales (K3, SOC p1/p2) n'ont pas de correctif et dépendent du modèle. Limite écrite dans le cas. *À revoir par Anaël* s'il préfère un cas de recette qui échoue sur le modèle local.
7. **Compaction en 4 096 tokens** : cas gardé ; 0 réussite sur 3 au PC cible est un résultat publiable au rapport, pas un motif de retrait.
8. **`case_player.py`** : gardé au minimum (une fonction, partagée par l'outil et le test des deux sens, sans k, annulation, budget ni restauration) ; la story 4 le reprend dans son exécuteur et le supprime.
9. **Cas en et de** : vérifié, les prompts visent un contenu existant dans leur langue : `content/i18n/{en,de}/demo_files/` (dont `confidentiel/budget_projet.txt`, `guide_harnais.md`, `notes_reunion.txt`), `content/i18n/{en,de}/corpus/mots_de_passe.md` et `projet_talvane.md`, `content/i18n/{en,de}/memory/memory.yaml` (Pascal). `read_file` sert la traduction quand elle existe, les noms de fichiers restent ceux du dossier français.

## Reste ouvert (Anaël)

- **Mesure des plafonds** sur le PC cible : `uv run python tools/eval/measure_cases.py --runs 3`, puis recopie des `max_model_calls` proposés (sauf H5) dans les trois fichiers et le test 7 ajusté au plafond retenu. Tant qu'elle n'est pas faite, les plafonds sont marqués provisoires dans le commentaire d'en-tête de `content/agent_cases.yaml`. Si le modèle local tourne sur le poste de développement, le dev lance l'outil et recopie la mesure, en le disant dans le rapport.
