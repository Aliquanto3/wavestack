---
title: 'Gemma 4 E2B et E4B : lecteur gemma4 et canal de pensée'
type: 'feature'
created: '2026-10-24'
status: 'draft'
route: ''
review_loop_iteration: 0
context: []
---

> **En attente (2026-10-24)** : écartée par la décision d'exclure les SLM dont l'exécution laisse un doute (3,1 Go en Q4_K_M, jamais essayé sur le PC cible). À reprendre si le benchmark de SLM le justifie. Licence vérifiée : Apache-2.0.

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Gemma 4 E2B et E4B chargent dans WaveStack, mais sans outils. Leur gabarit a son propre format d'appel, `<|tool_call>call:calculator{expression:<|"|>12*37<|"|>}<tool_call|>`. Leur raisonnement passe par un canal `<|channel>thought\n…<channel|>` que les balises `<think>` ne voient pas : la variable `enable_thinking` est détectée, mais la pensée s'afficherait comme réponse.

**Approach:** Une famille `gemma4`, reconnue au gabarit (`<|turn>` et `<|tool_call>call:`), avec un lecteur `gemma4` pour la syntaxe d'arguments du gabarit (macro `format_argument`). Les balises de raisonnement deviennent `("<|channel>thought", "<channel|>")`, et la fin de tour est `<turn|>`. Le modèle reste facultatif : au moins 3,1 Go en Q4_K_M, il est à réserver aux postes de 16 Go.

## Boundaries & Constraints

**Always:**
- Fichiers de référence : `unsloth/gemma-4-E2B-it-GGUF@0314792d7f1f7e229411f620751375812bb9faf2`, `gemma-4-E2B-it-Q4_K_M.gguf`, 3 106 738 272 octets, sha256 `740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8`. E4B : `unsloth/gemma-4-E4B-it-GGUF`, `gemma-4-E4B-it-Q4_K_M.gguf`, ~4,98 Go, révision à épingler à l'implémentation. Architecture `gemma4`, connue du llama.cpp embarqué. Licence : Apache-2.0 (vérifiée sur ai.google.dev le 2026-10-24).
- Le gabarit d'E2B devient la fixture `tests/fixtures/gemma4_chat_template.jinja`, vérifiée contre l'en-tête Q4_K_M. Une seconde fixture pour E4B seulement si son gabarit diffère.
- Le lecteur suit exactement `format_argument` du gabarit : chaîne `<|"|>…<|"|>`, `true`/`false`, nombre nu, objet `{clé:valeur,…}` (clés parfois entre `<|"|>`), liste `[…]`. Il ne lève jamais d'exception : en cas d'échec, `Malformed` avec un message en fr, en et de.
- Le canal de pensée suit les règles AD-6 existantes : un appel dans la pensée ne compte pas, et la pensée passée suit le gabarit (`strip_thinking`, `reasoning_wrap`).
- La valeur par défaut `enable_thinking | default(false)` du gabarit est respectée : la brique Raisonnement l'active.

**Never:**
- Pas d'audio ni d'image (les GGUF texte suffisent, pas de `mmproj`).
- Ne pas modifier `ChannelSplitter` au-delà de ce qu'exigent des balises de plusieurs caractères (déjà gérées).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Appel simple | `<|tool_call>call:calculator{expression:<|"|>12*37<|"|>}<tool_call|>` | `ToolCall("calculator", {"expression": "12*37"})` | N/A |
| Types | `{n:42,x:1.5,ok:true,l:[<|"|>a<|"|>,2],o:{k:<|"|>v<|"|>}}` | `{"n": 42, "x": 1.5, "ok": True, "l": ["a", 2], "o": {"k": "v"}}` | N/A |
| Chaîne avec `}` ou `,` | `{s:<|"|>a,b}c<|"|>}` | `{"s": "a,b}c"}` | N/A |
| Deux appels | deux blocs `<|tool_call>…<tool_call|>` | deux `ToolCall` | N/A |
| Jamais fermé | `<|tool_call>call:x{a:1}` sans `<tool_call|>` | aucun appel | `Malformed` « jamais fermée » |
| Syntaxe invalide | `<|tool_call>call:x{a:<|"|>1}<tool_call|>` | aucun appel | `Malformed` « arguments illisibles » |
| Pensée | `<|channel>thought\nJe calcule<channel|>Réponse` | canal `reasoning` « Je calcule », texte « Réponse » | N/A |
| Appel dans la pensée | `<|tool_call>…` entre `<|channel>thought` et `<channel|>` | ne compte pas | N/A |

</frozen-after-approval>

## Open Questions

- Entrée d'installateur (spec A). Options : E2B seulement ; E2B et E4B ; aucune avant le benchmark (reconnaissance seule).

## Code Map

- `src/wavestack/models/capabilities.py:47-103` -- branche `gemma4` (avant la branche générique) ; `_THINK_TAGS` n'est pas le bon couple pour cette famille.
- `src/wavestack/tools/parser.py` -- lecteur `gemma4` sur le modèle de `_parse_minicpm5` (balises propres, bloc entier) ; `tool_call_tags` dans `capabilities.py` gagne `("<|tool_call>", "<tool_call|>")`.
- `src/wavestack/context/render.py:127-159` -- `reasoning_wrap` : vérifier qu'il trouve le bloc de pensée de Gemma 4 (`<|channel>thought\n`, `\n<channel|>`), sinon ajuster la sonde.
- `src/wavestack/session/app_session.py:~8503` -- `in_reasoning` est déduit de `rendered.prompt.rstrip().endswith(tags[0])` : vérifier avec la balise `<|channel>thought`.
- `content/messages.yaml`, `content/i18n/{en,de}/messages.yaml` (`tools.parser`) -- messages `gemma4_*`.
- `content/models/publishers.yaml` -- `gemma` reconnaît l'architecture `gemma4` (à confirmer par un test dans `tests/test_model_catalog.py:455`).
- `tests/test_tool_parser_minicpm5.py` -- modèle de structure des tests (lecteur, capacités, séparateur, rendu, cycle complet).

## Tasks & Acceptance

**Execution:**
- [ ] `tests/fixtures/gemma4_chat_template.jinja` -- gabarit vérifié contre l'en-tête.
- [ ] `src/wavestack/models/capabilities.py`, `src/wavestack/tools/parser.py` -- famille, balises, lecteur.
- [ ] `content/*messages.yaml` -- messages en trois langues.
- [ ] `tests/test_tool_parser_gemma4.py` -- matrice, capacités, séparateur, rendu avec outil et appel passé, cycle complet calculatrice avec Raisonnement activé et désactivé.
- [ ] `docs/modeles.md` -- ligne Gemma 4 dans la table des modèles locaux (spec B), avec l'avertissement sur la mémoire.

**Acceptance Criteria:**
- Given le gabarit Gemma 4, when les capacités sont lues, then famille `gemma4`, lecteur `gemma4`, arrêt `<turn|>`, Raisonnement disponible avec les balises du canal de pensée.
- Given Raisonnement activé, when le modèle pense puis appelle un outil, then la pensée va dans le canal `reasoning`, l'appel est exécuté, et le prompt suivant suit le gabarit (pensée retirée ou gardée selon `strip_thinking`) sans `harness_error`.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected: OK
- `uv run pytest -q --tb=short tests/test_tool_parser_gemma4.py tests/test_tool_parser_minicpm5.py tests/test_tools.py tests/test_render_reference.py` -- expected: vert

**Manual checks (if no CLI):**
- Sur le PC cible seulement, avec 16 Go : Gemma 4 E2B, Outils puis Raisonnement, « Combien font 12 × 37 ? » ; noter la mémoire occupée (page Diagnostic, budget mémoire) et le temps par tour.
