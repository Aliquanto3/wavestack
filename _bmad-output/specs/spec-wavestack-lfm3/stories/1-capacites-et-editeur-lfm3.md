---
title: 'Story 1 : capacités et éditeur d''un modèle LFM3, en direct comme servi'
type: 'bugfix'
created: '2026-10-28'
status: 'in-progress'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-lfm3/SPEC.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** LFM3-1.7B a un template ChatML avec des appels au format `qwen3_coder`
(`<tool_call>\n<function=NOM>\n<parameter=ARG>…`), `enable_thinking` et `<think>`. Sans
architecture (llama-server), `capabilities_for` le reconnaît par son template ; avec
l'architecture `lfm3` (en-tête lu par le catalogue, ou un futur llama-cpp-python), il tombe au
cas générique, sans analyseur ni arrêt, et le tableau annonce « pas d'appel d'outil ». Servi
avec un `-m` relatif (en-tête illisible), LFM3 est rangé chez « Qwen (Alibaba) ». En direct,
llama-cpp-python ≤ 0.3.36 refuse le fichier avec un message qui ne nomme pas l'architecture.

**Approach:** reconnaître le template Qwen3 quelle que soit l'architecture quand il porte
`<function=` (format sans ambiguïté), avec la famille de l'architecture (`lfm3`) ; faire passer
les noms LFM avant l'architecture pour l'éditeur ; nommer l'architecture refusée dans le message
de la sonde.

## Boundaries & Constraints

**Always:** famille `qwen3` gardée sans architecture et pour une architecture `qwen3*`. Textes
en fr dans `content/`, surcouches en et de sous `content/i18n/{en,de}/`, aucun littéral français
dans le code Python. Les modèles déjà couverts (SmolLM3, Falcon-H1, Hunyuan, Qwen3.5, MiniCPM5,
Granite 4, EXAONE 4) gardent exactement leurs capacités. Aucun test ne lit le vrai GGUF.

**Never:** pas de mise à jour de llama-cpp-python ; pas d'ajout de LFM3 au catalogue de
téléchargement ; pas de retrait de `caps.family` dans `publisher_for` ; pas de numéro de build
de llama.cpp dans les textes ; ne pas toucher `_load_refused` ni `transient_fr`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| LFM3 en direct | `architecture="lfm3"`, template LFM3 | famille `lfm3`, analyseur `qwen3_coder`, arrêts `("<\|im_end\|>",)`, `reasoning_variable="enable_thinking"`, balises `("<think>","</think>")`, `reasoning` vrai, `incompatible_reason` nul | N/A |
| LFM3 servi | `architecture=None`, template LFM3 | famille `qwen3`, le reste identique (comportement actuel) | N/A |
| SmolLM3 | `architecture="smollm3"`, template sans `<function=` | inchangé (aucun analyseur) | N/A |
| Aller-retour | appel `calculator` rendu par le template LFM3 | `parse_tool_calls(…, "qwen3_coder", schémas)` retrouve nom et arguments | N/A |
| Éditeur, en-tête illisible | `publisher_for(["qwen3"], ["LFM3-1.7B-QAD-Q4_0.gguf"])` | éditeur `lfm` (« LFM (Liquid AI) »), en fr, en et de | N/A |
| Refus en direct, en-tête lisible | « Failed to load model », `general.architecture="lfm3"` | raison `models.probe.incompatible_architecture` qui nomme « lfm3 » et la bibliothèque, renvoie vers llama-server | détail brut gardé dans `detail` |
| Refus en direct, en-tête illisible | « Failed to load model », pas de métadonnées | raison `models.probe.incompatible` (texte actuel) | idem |

</frozen-after-approval>

## Code Map

- `src/wavestack/models/capabilities.py:103` -- `capabilities_for` ; `by_template` l.142-146 (exige `meta.architecture is None`), test `arch.startswith("qwen3")` l.164, branche `hermes` l.175 (exige l'absence de `<function=`), cas générique l.191-199. Docstring l.104-111.
- `src/wavestack/models/catalog.py:200` -- `publisher_for` : `caps.family` passe avant les noms, sauf éditeur `names_first`.
- `content/models/publishers.yaml:74` -- éditeur `lfm` ; modèle à suivre : `deepseek` (`names_first: true`, l.107). Copies : `content/i18n/{en,de}/models/publishers.yaml:58`.
- `src/wavestack/models/probe.py:122` -- `incompatible_fr()` ; échec de la sonde l.198 (`if _load_refused(exc)`) ; lecture Python de l'en-tête déjà faite l.215 (`gguf_meta.try_read_metadata`).
- `content/messages.yaml` -- `models.probe.incompatible` (vers l.2181), à côté duquel ajouter `incompatible_architecture` ; surcouches `content/i18n/{en,de}/messages.yaml`.
- `tests/test_tool_parser_granite4.py` -- modèle du nouveau test (`meta(architecture, template)`, `FIXTURES`) ; `test_other_families_unchanged` et `test_real_templates_failing_the_round_trip` doivent rester verts sans modification.
- `tests/fixtures/*_chat_template.jinja` -- fixtures de templates réels, source citée en tête du test.
- `tests/test_probe.py:168` -- `test_incompatible_file_reason_is_french_with_the_raw_detail`, modèle du nouveau cas ; `tests/gguf_writer.py` écrit l'en-tête.
- `tests/test_model_servers.py` l.1019, l.1254 (`test_a_chatml_template_with_tool_calls_only_is_not_qwen3`), l.1261 ; `tests/test_model_catalog.py:166` (`test_llama_server_capabilities_from_props`, attend Qwen pour le faux serveur Qwen) : inchangés.

## Tasks & Acceptance

**Execution:**
- [ ] `tests/fixtures/lfm3_chat_template.jinja` -- copie exacte de `https://huggingface.co/LiquidAI/LFM3-1.7B/resolve/main/chat_template.jinja` (12 129 octets, licence `lfm1.0`) ; si le réseau manque, `tokenizer.chat_template` du GGUF `LFM3-1.7B-QAD-Q4_0.gguf` (scratchpad de la session ac4fd306, `lfm3/`), identique à un saut de ligne final près (vérifié le 2026-10-28) -- fixture du template réel.
- [ ] `src/wavestack/models/capabilities.py` -- `by_template` = `"<tool_call>" in template and ("enable_thinking" in template or "<think>" in template) and (meta.architecture is None or "<function=" in template)` ; famille de cette branche : `"qwen3"` sans architecture ou pour `qwen3*`, sinon l'architecture ; docstring mise à jour (LFM3 rejoint Qwen3 par son template) -- le format `qwen3_coder` est sans ambiguïté, la famille sert aussi à l'éditeur.
- [ ] `content/models/publishers.yaml` + `content/i18n/{en,de}/models/publishers.yaml` -- `names_first: true` sur `lfm` -- aucun autre nom de modèle ne contient « lfm ».
- [ ] `src/wavestack/models/probe.py` -- `incompatible_fr(architecture: str | None = None)` : avec une architecture, `Message("models.probe.incompatible_architecture", lib=…, architecture=…)`, sinon le message actuel ; à l'échec de la sonde quand `_load_refused(exc)`, lire `gguf_meta.try_read_metadata(file_path)` et passer `general.architecture` si c'est une chaîne non vide -- nommer la cause probable.
- [ ] `content/messages.yaml` + `content/i18n/{en,de}/messages.yaml` -- clé `models.probe.incompatible_architecture`, par exemple « {lib} ne sait pas charger ce fichier d'architecture « {architecture} » : sans doute trop récente pour lui (ou fichier incomplet ou abîmé). Servez-le avec llama-server, dans une version récente de llama.cpp, ou choisissez un autre modèle. » -- texte de la nouvelle raison.
- [ ] `tests/test_tool_parser_lfm3.py` (nouveau) -- capacités avec `lfm3` et avec `None` ; aller-retour d'un appel rendu par le template et relu par `qwen3_coder` ; rendu avec `enable_thinking=False` qui ouvre `<think></think>` -- couvre la matrice.
- [ ] `tests/test_model_catalog.py` -- éditeur `lfm` pour un modèle servi au nom LFM3 sans en-tête, en fr, en et de.
- [ ] `tests/test_probe.py` -- en-tête lisible avec `general.architecture="lfm3"` et chargement refusé : la raison nomme l'architecture ; en-tête illisible : raison actuelle.

**Acceptance Criteria:**
- Given les tests existants des parseurs, du catalogue, des serveurs et de la sonde, when la story est fusionnée, then ils passent sans modification de leurs attentes.
- Given `tests/test_i18n.py`, when il s'exécute, then la nouvelle clé existe en fr, en et de.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Design Notes

Famille `lfm3` en direct plutôt que `qwen3` : seul le format d'appel est celui de Qwen3, et la
famille sert à l'éditeur. Sans architecture (llama-server), rien d'autre ne distingue le modèle :
on garde `qwen3`, et `names_first` sur LFM corrige l'éditeur par le nom du fichier. On ne retire
pas `caps.family` de `publisher_for` : la famille sert d'indice à d'autres modèles servis.

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_tool_parser_lfm3.py tests/test_tool_parser_granite4.py tests/test_model_catalog.py tests/test_model_servers.py tests/test_probe.py tests/test_i18n.py` -- expected: tout vert
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected: lint et format propres

**Manual checks (if no CLI):**
- Recette par Anaël (non lancée par la story) : LFM3 servi par llama-server, chemin absolu puis relatif, rangé chez « LFM (Liquid AI) », appels d'outil annoncés. Aucun scénario E2E ne charge LFM3 ; rejouer ceux de la page Modèles seulement si la fixture d'éditeurs y est lue.
