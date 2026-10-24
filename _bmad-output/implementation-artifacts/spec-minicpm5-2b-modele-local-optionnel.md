---
title: 'MiniCPM5-2B, modèle local optionnel'
type: 'feature'
created: '2026-10-24'
status: 'in-review'
route: 'dispatch'
baseline_commit: 'bde9e65c12ddb95a835f4e1e55a27bf3c9a7b7b5'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** WaveStack ne sait appeler des outils qu'avec les gabarits de la famille Qwen3. MiniCPM5-2B (OpenBMB, Apache-2.0), petit modèle entraîné à l'appel d'outils, charge bien mais tombe dans la famille générique : pas de lecteur d'appels, donc pas de briques Outils, MCP, Skills ni sous-agents, et pas d'arrêt sur `<|im_end|>`.

**Approach:** Reconnaître le gabarit de MiniCPM5 à son texte (l'en-tête GGUF déclare l'architecture `llama`), ajouter le lecteur `minicpm5` des appels `<function name="…"><param name="…">…</param></function>` (valeurs en CDATA comprises), avec la séquence d'arrêt `<|im_end|>`. Les installateurs proposent le téléchargement en option. Qwen3.5-2B reste le modèle par défaut, téléchargé et chargé comme aujourd'hui.

## Boundaries & Constraints

**Always:**
- Le fichier de référence est `MiniCPM5-2B-Q4_K_M.gguf` de `openbmb/MiniCPM5-2B-GGUF`, à la révision épinglée `2079a22f3beaa4e306449978533478fe0522f4b3` (1 561 318 368 octets, sha256 `ec2d5801640099e97d8d7e8003ad4d81f336e757811f03a26173dddf386602fd`). Son gabarit (vérifié le 2026-10-24, identique à celui de l'API Hugging Face) devient la fixture `tests/fixtures/minicpm5_chat_template.jinja`.
- La détection se fait sur le gabarit, quelle que soit l'architecture, pour un fichier comme pour llama-server ou Ollama (qui n'exposent pas l'architecture) : présence de `<|im_start|>`, `<function name="` et `<param name="`.
- Le raisonnement suit les règles existantes : `enable_thinking` dans le gabarit, donc brique Raisonnement disponible, balises `<think>`.
- Un appel mal formé ne lève jamais d'exception : il produit un `Malformed` avec un message traduit en fr, en et de.
- Les installateurs gardent l'idempotence, le `.part` puis renommage, et `-DryRun` / `WAVESTACK_DRY_RUN=1` ne télécharge rien.
- Décision du 2026-10-24 (démarrage) : sans choix sauvegardé utilisable et avec plusieurs fichiers utilisables, WaveStack charge `Qwen3.5-2B-Q4_K_M.gguf` s'il en fait partie (nom de fichier, casse ignorée), sans le sauvegarder comme choix. Le blocage `model.several` reste pour les autres cas.

**Never:**
- Ne pas changer le modèle par défaut, ni ce que l'installateur fait sans l'option.
- Ne pas télécharger MiniCPM5 sans demande explicite (option ou variable d'environnement).
- Pas de nouvel éditeur dans `publishers.yaml` : l'entrée `minicpm` existante (reconnaissance par le nom `MiniCPM5`) suffit.
- Pas de téléchargement de modèle de chat depuis l'interface (hors périmètre).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Appel simple | `<function name="calculator"><param name="expression">12*37</param></function>` | `ToolCall("calculator", {"expression": "12*37"})` | N/A |
| Valeur CDATA | `<param name="code"><![CDATA[a < b && c\nd]]></param>` | valeur `a < b && c\nd`, sans l'enveloppe CDATA | N/A |
| Typage | paramètre `integer` du schéma, valeur `42` | `42` (int), via `convert_value` | texte gardé si la conversion échoue |
| Plusieurs appels | deux blocs `<function …>` à la suite, texte autour | deux `ToolCall`, chacun avec son bloc en `source` | N/A |
| `</function>` dans une CDATA | `<param name="s"><![CDATA[x</function>y]]></param></function>` | un seul appel, valeur `x</function>y` | N/A |
| Jamais fermé | `<function name="x"><param name="a">1</param>` sans `</function>` | aucun appel | `Malformed` « jamais fermée » propre au format |
| Paramètre non fermé | `<param name="a">1` puis `</function>` | aucun appel | `Malformed` « `<param>` non fermée » |
| Pas d'attribut name | `<function name=""></function>` ou balise ouvrante tronquée | aucun appel | `Malformed` « balise `<function name="…">` absente ou mal fermée » |
| Appel dans le raisonnement | `<function …>` entre `<think>` et `</think>` | ne compte pas (règle AD-6 existante) | N/A |
| Gabarit Qwen3.5 | fixture `qwen3_5_chat_template.jinja` | famille `qwen3`, lecteur `qwen3_coder` inchangés | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/models/capabilities.py` -- `capabilities_for` : ajouter la branche MiniCPM5 (famille `minicpm5`, lecteur `minicpm5`, `stop_sequences=("<|im_end|>",)`, `reasoning_tags=_THINK_TAGS`, `reasoning_variable` lu dans le gabarit) avant la branche Qwen3. `TOOL_CALL_TAGS` (l. 202) est commun à `qwen3_coder` et `hermes` : ajouter une table des balises par lecteur, `('<function name="', "</function>")` pour `minicpm5`, et une fonction d'accès qui rend `TOOL_CALL_TAGS` par défaut.
- `src/wavestack/tools/parser.py` -- `_FORMATS` et `parse_tool_calls` : lire les balises du format au lieu des constantes `OPEN`/`CLOSE`. Pour `minicpm5`, le bloc est toute la balise `<function …>…</function>`, et sa fin est le premier `</function>` hors CDATA. Réutiliser `convert_value`. Valeur hors CDATA : défaire `&lt;`, `&gt;`, `&amp;`, `&quot;` et `&apos;` (`xml.sax.saxutils.unescape` plus les deux guillemets).
- `src/wavestack/session/app_session.py:8507` -- `ChannelSplitter(tool_tags=TOOL_CALL_TAGS …)` : prendre les balises du lecteur de `self._caps`. L'import se trouve l. 142. Aucun autre changement de session.
- `src/wavestack/context/render.py` -- ne pas modifier : `_tojson` accepte déjà `ensure_ascii`, et le gabarit rend lui-même les appels passés à partir de `tool_calls` (arguments en dictionnaire, comme pour Qwen3.5).
- `content/messages.yaml`, `content/i18n/{en,de}/messages.yaml` (bloc `tools.parser`, l. ~682) -- trois messages MiniCPM5 : balise `<function name="…">`, `<param>` non fermée, jamais fermée.
- `content/models/publishers.yaml` -- ne pas modifier : `minicpm` (l. 98) reconnaît `general.basename = MiniCPM5`. L'architecture `llama` n'est revendiquée par aucun éditeur (Llama se reconnaît au nom).
- `install.ps1` (param l. 25-32, variables l. 40-41, téléchargement l. 105-115), `install.sh` (l. 6-20, 75-85), `install.bat` (délègue, ne rien changer) -- option `-WithMiniCPM` et variable `WAVESTACK_WITH_MINICPM=1` (les deux côtés, car `irm | iex` ne passe pas d'option), sur le modèle de `-NoLaunch` / `WAVESTACK_NO_LAUNCH`.
- `tests/test_installers.py` (l. 24-26, 82, 98, 142) -- vérifie aujourd'hui que l'URL Qwen est la même dans README, ps1 et sh : faire de même pour l'URL MiniCPM5 (ps1, sh, `docs/installation.md`).
- `tests/test_tools.py` (helper `call`, `tool_session`) -- modèle de test du cycle complet avec `FakeEngine(template=…)`.
- `tests/test_model_catalog.py:455-466` -- cas de `publisher_for` : ajouter `MiniCPM5` avec l'architecture `llama`.
- `tests/fake_engine.py` -- `FakeEngine(template=…, architecture=…)`.
- `docs/installation.md` (« Installeur en une commande » l. 95-120, « Le modèle local » l. 193-205), `docs/modeles.md` (« Changer de modèle ») -- documenter l'option et le modèle.
- `src/wavestack/session/diagnostic.py` -- docstring (l. 8-14) et `_check_model_locked` (l. 585-600) : `files`/`distinct` puis le blocage `model.several`. Insérer la préférence entre `len(distinct) == 1` et `> 1`, et passer `notice_text` à `_hand_out`. Les blobs Ollama font aussi partie de `files` : seul le nom de fichier compte.
- `src/wavestack/config.py` -- constante `DEFAULT_MODEL_FILE = "Qwen3.5-2B-Q4_K_M.gguf"`. `tests/test_installers.py` vérifie qu'elle égale `QwenFile` / `QWEN_FILE`.
- `tests/test_cli_diagnostic.py:538-585` -- modèle des tests de démarrage (`saved=…`, deux fichiers). `test_several_candidates_block_until_a_choice` doit rester vert.

## Tasks & Acceptance

**Execution:**
- [x] `tests/fixtures/minicpm5_chat_template.jinja` -- copier le gabarit du GGUF officiel (texte de `tokenizer.chat_template`, téléchargeable par `https://huggingface.co/api/models/openbmb/MiniCPM5-2B-GGUF?expand%5B%5D=gguf`, champ `gguf.chat_template`) -- fixture de référence.
- [x] `src/wavestack/models/capabilities.py` -- branche MiniCPM5 et balises par lecteur -- reconnaissance et séparation des canaux.
- [x] `src/wavestack/tools/parser.py` -- lecteur `minicpm5` et balises par format ; mettre à jour la docstring du module -- lecture des appels.
- [x] `src/wavestack/session/app_session.py` -- balises du lecteur courant pour `ChannelSplitter` -- un appel MiniCPM5 va dans le canal `tool_call`.
- [x] `content/messages.yaml` + `content/i18n/en/messages.yaml` + `content/i18n/de/messages.yaml` -- trois messages -- erreurs lisibles dans les trois langues.
- [x] `src/wavestack/config.py`, `src/wavestack/session/diagnostic.py` -- constante `DEFAULT_MODEL_FILE` et préférence au démarrage (décision du 2026-10-24), docstring à jour -- Qwen3.5-2B reste le modèle chargé par défaut.
- [x] `install.ps1`, `install.sh` -- option de téléchargement de MiniCPM5 (1,5 Go), dans le même dossier `models/`, avec le même schéma idempotent et des messages propres au modèle ; aide (`.PARAMETER`, en-tête bash) à jour -- téléchargement optionnel.
- [x] `docs/installation.md`, `docs/modeles.md` -- option, URL, taille, licence, et le fait que Qwen3.5-2B reste le modèle recommandé -- documentation.
- [x] Tests : `tests/test_tools.py` (ou `tests/test_tool_parser_minicpm5.py`) pour chaque ligne de la matrice, plus un cycle complet calculatrice avec `FakeEngine(template=MINICPM5, architecture="llama")` ; capacités (famille, lecteur, arrêt, raisonnement) sur la fixture, en fichier et sans architecture (serveur) ; `tests/test_installers.py` (URL identique, option absente = pas de téléchargement, `DryRun`) ; `tests/test_model_catalog.py` (éditeur MiniCPM pour l'architecture `llama` + le nom `MiniCPM5`) ; `tests/test_cli_diagnostic.py` (Qwen3.5-2B et MiniCPM5 sans choix sauvegardé : Qwen chargé et non sauvegardé ; choix sauvegardé MiniCPM5 repris ; deux fichiers sans Qwen : blocage inchangé) ; un rendu de la fixture avec outils et appel passé, sans erreur de gabarit et avec `<function name="calculator">` dans le prompt.

**Acceptance Criteria:**
- Given le gabarit MiniCPM5 avec l'architecture `llama`, when les capacités sont lues, then la famille est `minicpm5`, le lecteur `minicpm5`, l'arrêt `<|im_end|>`, et les briques Outils et Raisonnement sont disponibles.
- Given la brique Outils active avec MiniCPM5, when le modèle répond par un appel puis par un texte, then l'outil s'exécute, son résultat revient dans le prompt suivant (`<tool_response>`), et la trace montre l'appel comme pour Qwen3.5.
- Given une installation sans option, when l'installateur tourne, then seul Qwen3.5-2B est téléchargé et le comportement est identique à aujourd'hui.
- Given `-WithMiniCPM` ou `WAVESTACK_WITH_MINICPM=1`, when l'installateur tourne deux fois, then MiniCPM5 est téléchargé une seule fois, à côté de Qwen3.5-2B.
- Given les deux fichiers dans `models/` sans choix mémorisé, when WaveStack démarre, then le modèle chargé est Qwen3.5-2B, sans blocage ni choix sauvegardé ; given MiniCPM5 sauvegardé comme choix, when WaveStack redémarre, then c'est MiniCPM5 qui est chargé.

## Implementation Notes

Implémenté selon la spec. Suite complète et E2E laissés à la fin du lot (ruff et tests ciblés par story). Le test réel `-WithMiniCPM` (1,5 Go) n'a pas été rejoué.

## Spec Change Log

## Review Triage Log

Revue du 2026-10-24 (Opus), branche rebasée sur `origin/main` (1f3b8d9) avant de juger.

- medium · second avis 1 · corrigé : `<function name="a">…<function name="b">…</function>` donnait un seul appel `a` aux arguments fusionnés `{'x','y'}` (reproduit), donc un outil exécuté avec des arguments d'un autre appel. `_minicpm5_end` rend désormais « jamais fermé » quand un `<function name="` s'ouvre hors CDATA avant le `</function>` ; test `test_a_new_call_before_the_close_means_never_closed` (rouge sans le correctif).
- low · second avis 2 · consigné : `</function>` dans une CDATA ferme le canal `tool_call` trop tôt ; limite déjà assumée en Design Notes, le lecteur lit l'appel correctement (test existant). Effet résiduel : la fin s'affiche comme texte, et une coupure par la limite après ce point suit le chemin `limit` au lieu de `tools.parser.cut`. Un séparateur conscient des CDATA n'est pas un petit correctif.
- false · second avis 3 · rejeté : un `<function name="calc">` jamais fermé rend toute la sortie `Malformed`, comme `<tool_call>` jamais fermé chez Qwen (règle « un bloc mal formé rend la sortie mal formée » de `parse_tool_calls`).
- low · second avis 4 · consigné : `<param>` sans attribut `name`, et du texte entre les `<param>`, sont ignorés en silence ; même tolérance que `qwen3_coder`, hors matrice.
- low · second avis 5 · consigné : la branche MiniCPM5 précède Qwen3 ; elle exige `<|im_start|>`, `<function name="` et `<param name="` ensemble, absents de tous les autres gabarits du dépôt (vérifié sur `tests/fixtures/`), et le gabarit Qwen3.5 reste `qwen3` (test).
- low · second avis 6 · consigné : les tests d'installateur passent par le mode à blanc, comme ceux de Qwen ; le vrai téléchargement (1,5 Go) reste la vérification manuelle ci-dessous.
- low · second avis 7 · corrigé en partie : ajout de `test_output_cut_inside_a_call_takes_the_malformed_path` (sortie coupée dans un appel MiniCPM5 : canal `tool_call`, message `coupée`). Préférence Qwen et blobs Ollama : les blobs se nomment `sha256-…`, ils ne peuvent pas égaler `DEFAULT_MODEL_FILE` ; pas de test ajouté.
- false · revue · rejeté : préférence au démarrage qui sauvegarderait le choix ; `_hand_out` n'écrit pas `selected_model_path` (test `…_is_not_saved`).
- low · revue · consigné : `_minicpm5_end` relance deux `find` depuis chaque fin de CDATA (O(k·n) pour k CDATA), une fois par sortie de modèle ; sans impact réel. Complexité : 0 constat à corriger.

## Design Notes

**Balises du lecteur.** Chez Qwen3, l'appel est enveloppé dans `<tool_call>`. Chez MiniCPM5, la balise `<function …>` est l'appel lui-même, sans enveloppe. Le séparateur de canaux retire les balises du canal `tool_call`, qui ne sert qu'au comptage des jetons. Le lecteur, lui, travaille sur `out.answer`, qui les garde. Limite assumée : un `</function>` dans une CDATA ferme le canal `tool_call` trop tôt, et la fin de la CDATA s'affiche alors comme du texte. Le lecteur, CDATA-aware, lit quand même l'appel correctement.

```text
<think>…</think>
Je calcule.<function name="calculator"><param name="expression">12*37</param></function>
```

**Choix du modèle au démarrage.** Règle d'aujourd'hui (`src/wavestack/session/diagnostic.py:8-14`, `_check_model_locked` l. 541-638) : on prend le `selected_model` sauvegardé ; sinon le seul fichier utilisable ; sinon le démarrage bloque sur le contrôle `model.several` jusqu'à un choix (test `tests/test_cli_diagnostic.py:578-585`). Il n'existe aucune clé de modèle par défaut. La décision du 2026-10-24 ajoute une seule préférence, par nom de fichier : elle fait de Qwen3.5-2B le modèle par défaut sans rien écrire dans la configuration.

## Verification

**Commands:**
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected: lint et format OK
- `uv run pytest -q --tb=short tests/test_tools.py tests/test_installers.py tests/test_model_catalog.py tests/test_render_reference.py tests/test_model_servers.py tests/test_cli_diagnostic.py` -- expected: tout vert

**Manual checks (if no CLI):**
- Avec le vrai fichier (1,5 Go, facultatif) : `.\install.ps1 -WithMiniCPM -NoLaunch`, puis dans WaveStack choisir MiniCPM5, activer Outils et demander « Combien font 12 × 37 ? » : la calculatrice est appelée.
