---
title: 'Granite 4.0 Nano (350M, 1B) : appels JSON <tool_call>'
type: 'feature'
created: '2026-10-24'
status: 'in-progress'
route: 'dispatch'
baseline_commit: '82e05ef74b6c7effa9be437c70e5d59743c92844'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Granite 4.0 Nano (IBM, Apache-2.0) écrit ses appels comme Hermes, `<tool_call>{"name": …, "arguments": …}</tool_call>`, format que lit déjà le lecteur `hermes`. WaveStack ne lui propose pourtant pas d'outils : `capabilities_for` n'accepte ce format que dans un gabarit ChatML avec le raisonnement de Qwen3, alors que celui de Granite est en `<|start_of_role|>…<|end_of_role|>`, sans raisonnement.

**Approach:** Reconnaître au gabarit, quelle que soit l'architecture, toute famille qui annonce `<tool_call>` sans `<function=` (donc hors `qwen3_coder` et `minicpm5`). Elle reçoit le lecteur `hermes`, une séquence d'arrêt lue dans les marqueurs de fin de tour du gabarit (`<|end_of_text|>` pour Granite, `<|im_end|>` pour un ChatML), et le raisonnement selon les règles existantes. L'installateur propose les variantes non-H, via la liste de la spec A.

## Boundaries & Constraints

**Always:**
- Modèles visés (Q4_K_M, révisions épinglées le 2026-10-24, architecture `granite`, connue du llama.cpp embarqué) :

  | Modèle | Dépôt @ révision | Fichier, octets, sha256 |
  |---|---|---|
  | Granite 4.0 350M | `ibm-granite/granite-4.0-350m-GGUF@b8208a86a58427e1739265318028eb5895b74bf2` | `granite-4.0-350m-Q4_K_M.gguf`, 236 985 760, `771c588a49607f274a2bba3185733607ebe6f74b996ab90e2d6bee0d98bcec52` |
  | Granite 4.0 1B | `ibm-granite/granite-4.0-1b-GGUF@b27c2fe3f211b7f44e80fa620177aea371099aaa` | `granite-4.0-1b-Q4_K_M.gguf`, 1 023 645 440, `22ec0f9cc99a90185312de3c882c84e7bd6789bdd050389844380a01a831d7f1` |

- Les deux gabarits sont versés en fixture sous `tests/fixtures/` (téléchargés par `https://huggingface.co/api/models/<dépôt>?expand%5B%5D=gguf`, champ `gguf.chat_template`), puis vérifiés contre l'en-tête du fichier Q4_K_M, lu par une requête HTTP `Range` sur les premiers Mo, puis par `gguf_meta.read_metadata`. Une seule fixture si les deux sont identiques.
- Le rendu du 2026-10-24 montre que le gabarit Granite affiche lui-même les `tool_calls` passés (`<|start_of_role|>assistant<|end_of_role|><tool_call>\n{"name": …}\n</tool_call>`) : aucun changement de session n'est nécessaire.
- Les familles `qwen3` et `minicpm5` gardent leur détection et leur lecteur, à l'octet près (tests existants verts).
- Décision du 2026-10-24 : sont exclus les modèles dont la licence ou l'exécution laisse un doute (LFM2.5, EXAONE 4.0, Falcon-H1, SmolLM3-3B, Gemma 4). Les variantes hybrides Granite 4.0-H ont le même gabarit et sont donc reconnues de fait, mais elles ne sont ni proposées par l'installateur, ni recommandées dans la doc.
- Décision du 2026-10-24 (revue) : règle d'aller-retour. Un gabarit qui annonce `<tool_call>` sans `<function=` ne reçoit le lecteur `hermes` que si un appel passé, rendu par le gabarit lui-même (message `assistant` avec `tool_calls`, puis message `tool`), est relu par `parse_tool_calls(…, "hermes", …)` avec le même nom et les mêmes arguments. La sonde est en cache par gabarit et ne lève jamais d'exception ; un échec vaut « pas de lecteur ». Granite 4.0 et un ChatML Hermes passent la sonde. SmolLM3 et Falcon-H1 (appel passé absent du rendu) ainsi que Hunyuan (nom nu et bloc JSON en markdown) échouent et restent sans outils, comme avant. EXAONE 4.0 la passe techniquement, mais il n'est ni proposé par l'installateur ni recommandé (licence).

**Never:**
- Pas d'entrée d'installateur ni de recommandation pour Granite 4.0-H.
- Pas de nouvel éditeur : `granite` existe dans `publishers.yaml`.
- Ne pas toucher au moteur.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Granite, appel | `<tool_call>\n{"name": "calculator", "arguments": {"expression": "12*37"}}\n</tool_call>` | un `ToolCall` | N/A |
| Granite, JSON illisible | `<tool_call>{name: x</tool_call>` | aucun appel | `Malformed` `json_unreadable` (inchangé) |
| Fin de tour | Granite génère `<|end_of_text|>` | arrêt, marqueur absent du texte | N/A |
| Gabarit ChatML + `<tool_call>` sans raisonnement (Qwen2.5, Hermes) | fixture minimale | lecteur `hermes`, arrêt `<|im_end|>` (aujourd'hui : aucun lecteur) | N/A |
| Qwen3.5, MiniCPM5 | fixtures existantes | famille et lecteur inchangés | N/A |
| Gabarit sans `<tool_call>` (Gemma 3, Llama 3.2) | fixture minimale | aucun lecteur, comme aujourd'hui | N/A |
| Gabarit `<tool_call>` dont l'appel passé n'est pas relu | gabarits réels SmolLM3, Falcon-H1, Hunyuan 1.8B (fixtures) | aucun lecteur, comme aujourd'hui | N/A |
| Gabarit `<tool_call>` relu, autre fin de tour | gabarit réel EXAONE 4.0 (fixture) | lecteur `hermes`, arrêt `[|endofturn|]` | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/models/capabilities.py:47-103` -- `capabilities_for` : ajouter la branche « `<tool_call>` sans `<function=` » après les branches `minicpm5` et `qwen3`, avec une table des marqueurs de fin de tour (`<|end_of_text|>`, `<|im_end|>`) cherchés dans le gabarit. `by_template` (l. 78) reste la règle de Qwen3. `reasoning_tags` et `reasoning_variable` suivent la branche générique actuelle (l. 94-103).
- `src/wavestack/tools/parser.py` -- `_hermes` (l. ~88) réutilisé tel quel.
- `content/models/publishers.yaml:59` -- `granite` (ajouter l'architecture `granite` si elle n'y est pas, à vérifier) ; un cas `(["granite"], ["granite-4.0-1b"], "granite")` dans `tests/test_model_catalog.py:455`.
- `install.ps1`, `install.sh` -- entrées `granite-4.0-350m` et `granite-4.0-1b` dans la liste de la spec A (ou, si A n'est pas encore fusionnée, attendre A).
- `tests/test_tools.py` (`call`, `tool_session`), `tests/fake_engine.py`, `tests/test_tool_parser_minicpm5.py` -- modèles de tests (capacités, cycle complet).
- `docs/modeles.md` -- table « modèles locaux et appels d'outils » (modèle, lecteur, raisonnement, taille) : Qwen3.5-2B et 0.8B, MiniCPM5-2B, Granite 4.0 350M et 1B.

## Tasks & Acceptance

**Execution:**
- [x] `tests/fixtures/granite4_chat_template.jinja` -- gabarit vérifié contre l'en-tête.
- [x] `src/wavestack/models/capabilities.py` -- détection et séquences d'arrêt.
- [x] `content/models/publishers.yaml` (+ i18n si besoin) -- architecture `granite`.
- [x] `install.ps1`, `install.sh`, `tests/test_installers.py` -- deux entrées dans la liste de la spec A.
- [x] `tests/test_tool_parser_granite4.py` -- matrice ; capacités de la fixture (famille `granite`, `hermes`, arrêt, pas de raisonnement) ; rendu avec outil et appel passé ; cycle complet calculatrice avec `FakeEngine(template=GRANITE, architecture="granite")`.
- [x] `docs/modeles.md`, `docs/installation.md` -- table des modèles et option d'installation.

**Acceptance Criteria:**
- Given le gabarit Granite 4.0, when les capacités sont lues, then la brique Outils est disponible avec le lecteur `hermes` et l'arrêt `<|end_of_text|>`.
- Given Granite et la brique Outils, when le modèle appelle la calculatrice puis répond, then l'outil s'exécute et le second prompt contient l'appel et le résultat (rôle `tool` du gabarit), sans `harness_error`.

## Implementation Notes

- 2026-10-24, préparation par l'orchestrateur : les deux fichiers Q4_K_M sont déjà téléchargés et vérifiés (tailles et sha256 de la spec) dans `%TEMP%\wavestack-e2e-models\models`. Leurs gabarits réels sont identiques octet pour octet (6 418 caractères) : une seule fixture `tests/fixtures/granite4_chat_template.jinja`, à extraire de l'en-tête de l'un d'eux par `gguf_meta.read_metadata`. Architecture `granite`, `general.basename` `granite-4.0`, tailles `350M` et `1B`. La spec A est fusionnée (#86) : la table `$OptionalModels` (install.ps1) et `OPTIONAL_MODELS` (install.sh) reçoivent les entrées `granite-4.0-350m` et `granite-4.0-1b`.

## Spec Change Log

## Review Triage Log

Revue du 2026-10-24 (Opus, base `origin/main` = 82e05ef, à jour). Preuve commune : `capabilities_for` passé sur les 23 gabarits réels tirés le 2026-10-24 (architecture déclarée et `None`).

- HIGH · second avis 1 · corrigé : la branche « `<tool_call>` sans `<function=` » donnait `hermes` à SmolLM3, Falcon-H1, EXAONE et Hunyuan. Règle d'aller-retour : `hermes_round_trip` (`capabilities.py`, `@cache`, imports locaux à cause de `tools/parser.py` → `capabilities.py`, `except Exception` → `False`) rend user, `assistant` avec `tool_calls` (arguments en dict), `tool`, et relit par `parse_tool_calls(…, "hermes", {})` le rendu situé après la question (marqueur privé ``), pour ignorer l'exemple vide `<tool_call></tool_call>` des prompts système (Falcon-H1, Granite). Granite 4.0 (350M, 1B, H) et Qwen3-1.7B passent ; SmolLM3, Falcon-H1, Hunyuan échouent.
- HIGH · second avis 2 · corrigé (même cause) : Hunyuan, `json_unreadable` sur `nom\n```json…`, la sonde échoue, aucun lecteur (test `test_real_templates_failing_the_round_trip[hunyuan]`).
- MEDIUM · second avis 3 · corrigé (même cause) : Falcon-H1 n'affiche que `content`, l'appel passé est absent du rendu.
- MEDIUM · second avis 4 · corrigé (même cause) : SmolLM3 et Falcon-H1, fixtures réelles `smollm3_chat_template.jinja`, `falcon_h1_chat_template.jinja`.
- MEDIUM · second avis 5 · corrigé : `[|endofturn|]` ajouté à `_END_OF_TURN_MARKERS` ; EXAONE 4.0 (`exaone4`) reçoit `hermes` et l'arrêt `[|endofturn|]` (test dédié).
- LOW · second avis 6 · corrigé : `_end_of_turn` prend le marqueur écrit le premier dans le gabarit, plus l'ordre de la table.
- LOW · second avis 7 · corrigé : `granite-4.0-350m` annoncé « 0,2 Go » (236 985 760 octets, 0,237 Go / 0,221 Gio) dans `install.sh`, `install.ps1`, `docs/installation.md` (deux endroits) et `docs/modeles.md`.
- LOW · second avis 8 · corrigé : le test de rendu vérifie le bloc exact de l'appel passé (`<|start_of_role|>assistant…</tool_call><|end_of_text|>`) puis `<tool_response>\n444\n</tool_response>`.
- MEDIUM · revue · corrigé : la fixture minimale ChatML Hermes n'affichait pas l'appel passé ; elle le rend désormais en JSON (forme Qwen2.5), avec un exemple vide `<tool_call>` dans le prompt système, et une variante sans appel passé vérifie l'absence de lecteur. Ajouts : Llama 3.2 minimal (matrice « sans `<tool_call>` »), sonde qui ne lève jamais (gabarit qui lève, gabarit qui ne compile pas), sonde qui exige le même appel.
- LOW · revue · corrigé : `docs/modeles.md` disait « tout gabarit … reçoit `hermes` » ; la phrase décrit maintenant l'aller-retour.
- LOW · revue · consigné : SmolLM3 servi par llama-server (architecture `None`) passe par `by_template` (ChatML, `<tool_call>`, `enable_thinking`) et reçoit encore `hermes` dans la branche `qwen3`. Comportement antérieur à la story ; appliquer la sonde à cette branche casse `test_model_catalog.py::test_qwen_file` (gabarit Qwen factice sans appel passé), alors que la spec exige `qwen3` à l'octet près. À traiter dans une story à part (sonde dans la branche `qwen3` et gabarits factices réalistes).
- Complexité : 0 constat (aucune structure qui grossit ; la sonde est en cache par gabarit, un rendu Jinja par gabarit distinct).

## Verification

**Commands:**
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected: OK
- `uv run pytest -q --tb=short tests/test_tool_parser_granite4.py tests/test_tool_parser_minicpm5.py tests/test_tools.py tests/test_render_reference.py tests/test_model_catalog.py tests/test_installers.py` -- expected: vert

**Manual checks (if no CLI):**
- Sur le PC cible seulement : Granite 4.0 1B puis 350M, brique Outils, « Combien font 12 × 37 ? ».
