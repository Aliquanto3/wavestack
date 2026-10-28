---
title: 'Story 1 : capacités et éditeur d''un modèle LFM3, en direct comme servi'
type: 'bugfix'
created: '2026-10-28'
status: 'in-review'
route: 'dispatch'
baseline_commit: '049458152381352eef44259890f57c461e70b29c'
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
- [x] `tests/fixtures/lfm3_chat_template.jinja` -- copie exacte de `https://huggingface.co/LiquidAI/LFM3-1.7B/resolve/main/chat_template.jinja` (12 129 octets, licence `lfm1.0`) ; si le réseau manque, `tokenizer.chat_template` du GGUF `LFM3-1.7B-QAD-Q4_0.gguf` (scratchpad de la session ac4fd306, `lfm3/`), identique à un saut de ligne final près (vérifié le 2026-10-28) -- fixture du template réel.
- [x] `src/wavestack/models/capabilities.py` -- `by_template` = `"<tool_call>" in template and ("enable_thinking" in template or "<think>" in template) and (meta.architecture is None or "<function=" in template)` ; famille de cette branche : `"qwen3"` sans architecture ou pour `qwen3*`, sinon l'architecture ; docstring mise à jour (LFM3 rejoint Qwen3 par son template) -- le format `qwen3_coder` est sans ambiguïté, la famille sert aussi à l'éditeur.
- [x] `content/models/publishers.yaml` + `content/i18n/{en,de}/models/publishers.yaml` -- `names_first: true` sur `lfm` -- aucun autre nom de modèle ne contient « lfm ».
- [x] `src/wavestack/models/probe.py` -- `incompatible_fr(architecture: str | None = None)` : avec une architecture, `Message("models.probe.incompatible_architecture", lib=…, architecture=…)`, sinon le message actuel ; à l'échec de la sonde quand `_load_refused(exc)`, lire `gguf_meta.try_read_metadata(file_path)` et passer `general.architecture` si c'est une chaîne non vide -- nommer la cause probable.
- [x] `content/messages.yaml` + `content/i18n/{en,de}/messages.yaml` -- clé `models.probe.incompatible_architecture`, par exemple « {lib} ne sait pas charger ce fichier d'architecture « {architecture} » : sans doute trop récente pour lui (ou fichier incomplet ou abîmé). Servez-le avec llama-server, dans une version récente de llama.cpp, ou choisissez un autre modèle. » -- texte de la nouvelle raison.
- [x] `tests/test_tool_parser_lfm3.py` (nouveau) -- capacités avec `lfm3` et avec `None` ; aller-retour d'un appel rendu par le template et relu par `qwen3_coder` ; rendu avec `enable_thinking=False` qui ouvre `<think></think>` -- couvre la matrice.
- [x] `tests/test_model_catalog.py` -- éditeur `lfm` pour un modèle servi au nom LFM3 sans en-tête, en fr, en et de.
- [x] `tests/test_probe.py` -- en-tête lisible avec `general.architecture="lfm3"` et chargement refusé : la raison nomme l'architecture ; en-tête illisible : raison actuelle.

**Acceptance Criteria:**
- Given les tests existants des parseurs, du catalogue, des serveurs et de la sonde, when la story est fusionnée, then ils passent sans modification de leurs attentes.
- Given `tests/test_i18n.py`, when il s'exécute, then la nouvelle clé existe en fr, en et de.

## Implementation Notes

Implémenté le 2026-10-28. `by_template` accepte désormais une architecture tant que le
template porte `<function=` ; la famille de la branche Qwen3/LFM3 devient l'architecture dès
qu'elle est connue et ne commence pas par `qwen3`. `publisher_for` n'a pas changé : seul
`names_first` sur `lfm` suffit (le nom de fichier l'emporte sur l'architecture `qwen` lue du
template). `incompatible_fr` prend une architecture optionnelle ; `probe_file` la lit du
même en-tête Python déjà lu pour le KV. La fixture `tests/fixtures/lfm3_chat_template.jinja`
vient du GGUF `LFM3-1.7B-QAD-Q4_0.gguf` (scratchpad de la session ac4fd306), le réseau n'étant
pas nécessaire pour l'obtenir (12 129 octets, identiques au fichier Hugging Face à la date
indiquée dans l'énoncé).

## Spec Change Log

## Review Triage Log

Passe 1 (2026-10-28) : Blind Hunter, Edge Case Hunter, Verification Gap, second avis.

| # | Constat | Verdict | Preuve | Suite |
|---|---|---|---|---|
| 1 | `reason_message` ne reconnaît pas `incompatible_architecture` après le passage par le processus fils ou settings.json : texte français en en/de (Verification Gap, Blind Hunter) | medium | `discovery.py:312` compare par égalité avec `incompatible_fr()` seul ; `catalog.py:703` rend ce résultat | patch |
| 2 | Architecture vide `""` → famille `""` (Edge Case) | low | `capabilities.py:171` teste `meta.architecture is None` ; correction directe | patch |
| 3 | Motif `lfm` sans borne, désormais `names_first` : « Wolfmind », « SelfMerge » rangés chez LFM (Blind Hunter, second avis) | low | `matches_name` = `re.search` ; correction directe du motif | patch |
| 4 | Lecture complète de l'en-tête au refus pour lire `general.architecture` (Edge Case) | low | `probe.py:202` sans `stop_at` ; correction directe | patch |
| 5 | Docstring du test : fixture dite « Hugging Face » alors qu'extraite du GGUF (second avis, Blind Hunter) | low | rapport du dev | patch |
| 6 | `by_template` élargi touche d'autres architectures ChatML avec `<function=` (Nemotron…) (tous) | false | voulu par l'Approach figée ; `<\|im_start\|>` reste exigé ; ce format est celui de `qwen3_coder`, l'analyseur est donc juste, au lieu d'aucun | rejeté |
| 7 | Chargement direct (`app_session.py:2547`) garde le texte générique (Blind Hunter) | low | la sonde refuse le fichier avant tout chargement ; corriger ajoute une lecture d'en-tête sur un chemin rare | rejeté |
| 8 | « Sans doute trop récente » trompeur pour un fichier tronqué d'architecture connue (Edge Case, Blind Hunter, second avis) | low | le texte, donné par la spec, dit déjà « ou fichier incomplet ou abîmé » | rejeté |
| 9 | `try_read_metadata` pourrait laisser passer `ValueError`/`OverflowError` (Edge Case) | false | même aide déjà appelée sans garde l.215 de la même fonction ; elle attrape `OSError, GGUFError, UnicodeDecodeError, struct.error` ; aucun cas montré | rejeté |
| 10 | Nom d'architecture non assaini dans le message (Blind Hunter) | low | l'architecture de l'en-tête est déjà affichée ailleurs (tableau) ; rendu échappé par les gabarits | rejeté |
| 11 | Guillemets « » dans en/de (Blind Hunter) | false | convention du dépôt : 25 et 23 occurrences dans `content/i18n/{en,de}/messages.yaml` | rejeté |
| 12 | Test de la sonde avec sous-chaîne française codée en dur (Blind Hunter) | low | compare aussi à `incompatible_fr()` ; cosmétique | rejeté |
| 13 | Pas de test du rendu en/de de la nouvelle clé (Blind Hunter) | low | couvert par le test du constat 1 | rejeté |
| 14 | Docstring et commentaire de `capabilities_for` longs (Blind Hunter) | low | cosmétique | rejeté |
| 15 | `publisher_for` jamais testé avec `lfm3` issu de `caps.family` (second avis) | false | l'architecture `lfm` couvre `lfm3` par préfixe (cas `["lfm2"]` existant) | rejeté |
| 16 | Ligne de journal `probe.incompatible` du diagnostic en français pour en/de (Verification Gap) | low | `diagnostic.py:367`, déjà vrai du texte générique avant la story | reporté |

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
