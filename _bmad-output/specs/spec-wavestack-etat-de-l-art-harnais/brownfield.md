# Existant à réutiliser (relevé du 2026-10-24, `main` à `51d34f6`)

Les numéros de ligne datent de ce relevé ; la V1.3 et la PR #79 les décaleront.

## Catégories des briques (story 1)

- **Catégorie structurelle** : `Category = Literal["prompt", "context", "harness"]` (`bricks/contract.py:12`), posée dans `BrickDeclaration` (`bricks/registry.py`) : `reasoning` en `prompt` (:39-41), `guardrails` déjà en `harness` (:230-232).
- **Texte affiché** : `category_text` de `content/bricks/*.yaml` et de leurs miroirs `content/i18n/{en,de}/bricks/`. `reasoning.yaml:3` dit « prompt engineering », `guardrails.yaml:3` dit « harnais ».
- **Couleur par discipline** : `discipline_of()` et `_group_discipline()` (`context/window.py:20-50`) tirent la discipline de la catégorie. Reclasser le raisonnement change sa couleur dans la jauge et le panneau.
- **E2E** : `s_disciplines` (`tools/e2e/run_e2e.py:2609-2649`) compare chaque segment au jeton `--color-discipline-{d}` ; il reste juste tant que la catégorie et le jeton suivent. Captures `28-disciplines-*` à refaire.
- **Libellés des disciplines** : `ui.yaml` `disciplines` (:168).

## Guide du harnais (stories 1 et 2)

- `content/demo_files/guide_harnais.md` (1 227 mots) est un document de démonstration lu par le modèle : délégation au sous-agent (`content/subagent.yaml:10, 22` ; `scenarios.yaml:297-337`) et préréglage « Guide du harnais (prose, compression) » (`content/tools.yaml`).
- **Piège** : chaque section ajoutée allonge le résultat de `read_file`. Rejouer les scénarios `subagent` et `compression` sur le faux moteur et vérifier la fenêtre de 4 096 tokens ; la consigne de `subagent` borne déjà le résumé à 80 mots.
- Le guide du formateur `docs/guide.md` reçoit un renvoi vers la nouvelle section.

## Outil `search_documents` et `read_file` (story 3)

- **Outils natifs** : `NATIVE_TOOLS` (`tools/native.py:131-148`), `ToolSpec` (`tools/registry.py`, `reads_local_path` :59). Description envoyée au modèle et préréglages : `content/tools.yaml`.
- **`read_file`** (`native.py:117-128`) : confiné à `content/demo_files/` par `demo_dir()`, `resolve_demo_path()` et `demo_relative()` (:94-114) ; la traduction est choisie fichier par fichier par `config.content_file`. Le listage (« . ») ne montre que `demo_files`.
- **Hook H1** (`hooks.py:168-180`) juge tout outil `reads_local_path` avec la même résolution que `read_file`. Ouvrir `corpus/<doc>.md` impose d'étendre la résolution partagée, pas de la contourner, sinon H1 et `read_file` divergent.
- **Corpus Exemplia** : `content/corpus/*.md` (8 documents sur `main`, enrichis par la PR #79), traduits sous `content/i18n/{en,de}/corpus/`. C'est le corpus du RAG ; `search_documents` cherche dans la langue de la session, avec le même repli fichier par fichier que `read_file`.
- **Recommandation** : recherche insensible à la casse et aux accents (`unicodedata`, déjà utilisé par `rag/lab.py:23`), résultats `fichier:ligne: texte`, nombre de résultats borné pour tenir dans la fenêtre.
- **Brique RAG** : `content/bricks/rag.yaml`, que la PR #79 modifie aussi : la fusionner avant.

## Débordement (story 4)

- **Refus actuel** : `_render` puis `if payload["overflow"]: self._emit_overflow(...); return "overflow"` (`session/app_session.py:7160-7168`, chat principal) ; sous-agent : `:5511-5516` ; atelier MCP : `:12137-12149`.
- **`_emit_overflow`** (`:8370-8412`) : calcule la cause la plus lourde et émet `context_overflow` avec `message_text` et `strategies_text`, quatre textes tirés de `_OVERFLOW_STRATEGIES` (`:433`) et de `messages.yaml` `session.overflow.strategies` (:140-144).
- **Payload** : `ContextOverflowPayload` (`trace/catalog.py:361-365`) n'a que du texte. Pour des boutons, ajouter des identifiants de stratégie et la disponibilité, sans retirer `strategies_text`.
- **Rendu** : `overflowCard()` (`web/static/app.js:5006-5017`), appelé depuis `app.js:465, 785, 6506`.
- **Bouton existant** : `#clear-conversation` (`web/static/index.html:171`, `ui.yaml` `main.chat.clear`). « Compacter » se place à côté.

## Historique de session (story 4)

- **Stockage** : `self._history: list[Exchange]` (`app_session.py:887`) ; `Exchange` (`:436-455`) est un `NamedTuple` (`turn_id`, `user`, `text`, `reasoning`, `steps`, `injection`, …). Ajouter un champ avec valeur par défaut, par exemple `summary: bool = False`, garde les constructeurs existants.
- **Instantané d'un tour** : `build_turn_state()` (`:4110-4118`) copie l'historique sous `_lock`.
- **Rejeu** : `_start()` (`:4950-4980`) garde dans `self._last` l'historique du dernier tour ; « Renvoyer » le restaure. **Piège** : après une compaction, rejouer le tour refusé rétablirait l'historique d'avant. Le renvoi automatique part comme un nouveau tour sur l'historique réécrit, et `_last` doit suivre.
- **Vider** : `clear_conversation()` (`:6274-6285`) montre le motif à suivre : refus hors `idle`, mise à jour sous `_lock`, `self._cache_cause = ...`, puis `conversation_cleared`, `_emit_architecture()`, `_refresh_preview()`.
- **Cause du cache** : `self._cache_cause` alimente `PrefixNotReusedPayload.cause` ; `PrefixCause` (`catalog.py:724-736`) liste `in_turn`, `system`, `history`, `template`, `reset`, `replay`, `abandoned`, `subagent`, `llm`, `mcp_lab`, `rag_lab`. La V1.3 (story 3) ajoute la cause « cache vidé » ; `compaction` et `sliding_window` s'ajoutent après.
- **Appel de résumé** : il suit le chemin d'un appel au modèle (journal `model_call_*`, `record_spend` pour le coût cloud et le temps local, plafond FinOps, annulation). Composant proposé : `short_memory.compaction`, sous la brique Mémoire courte (sans elle, pas d'historique). Prompt de résumé dans `content/prompts/`, en fr, en et de.
- **Mode chat** (cloud) : `_check_reuse` ne vaut que pour `RenderedContext` (`:7169`) ; en cloud, la jauge V1.3 lit l'écriture dans la réponse du fournisseur, la cause vient du harnais.

## Scénarios et programme

- `content/scenarios.yaml` : `program` (:37-55), six modules ; module 3 « RAG » (45 min, `rag`, `rag_rerank`) ; module 6 « Sous-agent et compression » (60 min, `subagent`, `compression`).
- `duration_min` est borné à 30-60 (`scenarios.py:44`). Décision : le module 6 devient « Sous-agent » (`subagent`, 45 min) et un module 7 « Contexte long et carte » (`compression`, puis `compaction` en story 4, puis `harness_map`, 45 min) ; le module RAG passe à 60 min. La consigne du premier scénario du module 7 rappelle les exceptions AD-9, comme les autres premiers scénarios.
- Tests et E2E qui comptent les modules ou citent le module 6 : à suivre lors de la scission (story 2).
- `expects_overflow` (`scenarios.py:35-36`) existe sans scénario : le scénario de compaction peut être le premier à l'utiliser.
- L'en-tête de `scenarios.yaml` (:16-19) dit déjà que les prompts nomment l'outil pour un petit modèle : la consigne d'échafaudage de CAP-2 le rend visible au participant.
