---
title: 'Granite 4.0 Nano (350M, 1B) : appels JSON <tool_call>'
type: 'feature'
created: '2026-10-24'
status: 'ready-for-dev'
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
- [ ] `tests/fixtures/granite4_chat_template.jinja` -- gabarit vérifié contre l'en-tête.
- [ ] `src/wavestack/models/capabilities.py` -- détection et séquences d'arrêt.
- [ ] `content/models/publishers.yaml` (+ i18n si besoin) -- architecture `granite`.
- [ ] `install.ps1`, `install.sh`, `tests/test_installers.py` -- deux entrées dans la liste de la spec A.
- [ ] `tests/test_tool_parser_granite4.py` -- matrice ; capacités de la fixture (famille `granite`, `hermes`, arrêt, pas de raisonnement) ; rendu avec outil et appel passé ; cycle complet calculatrice avec `FakeEngine(template=GRANITE, architecture="granite")`.
- [ ] `docs/modeles.md`, `docs/installation.md` -- table des modèles et option d'installation.

**Acceptance Criteria:**
- Given le gabarit Granite 4.0, when les capacités sont lues, then la brique Outils est disponible avec le lecteur `hermes` et l'arrêt `<|end_of_text|>`.
- Given Granite et la brique Outils, when le modèle appelle la calculatrice puis répond, then l'outil s'exécute et le second prompt contient l'appel et le résultat (rôle `tool` du gabarit), sans `harness_error`.

## Implementation Notes

- 2026-10-24, préparation par l'orchestrateur : les deux fichiers Q4_K_M sont déjà téléchargés et vérifiés (tailles et sha256 de la spec) dans `%TEMP%\wavestack-e2e-models\models`. Leurs gabarits réels sont identiques octet pour octet (6 418 caractères) : une seule fixture `tests/fixtures/granite4_chat_template.jinja`, à extraire de l'en-tête de l'un d'eux par `gguf_meta.read_metadata`. Architecture `granite`, `general.basename` `granite-4.0`, tailles `350M` et `1B`. La spec A est fusionnée (#86) : la table `$OptionalModels` (install.ps1) et `OPTIONAL_MODELS` (install.sh) reçoivent les entrées `granite-4.0-350m` et `granite-4.0-1b`.

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected: OK
- `uv run pytest -q --tb=short tests/test_tool_parser_granite4.py tests/test_tool_parser_minicpm5.py tests/test_tools.py tests/test_render_reference.py tests/test_model_catalog.py tests/test_installers.py` -- expected: vert

**Manual checks (if no CLI):**
- Sur le PC cible seulement : Granite 4.0 1B puis 350M, brique Outils, « Combien font 12 × 37 ? ».
