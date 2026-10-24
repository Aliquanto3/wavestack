---
title: 'Modèles facultatifs des installateurs, dont Qwen3.5-0.8B'
type: 'feature'
created: '2026-10-24'
status: 'done'
route: 'dispatch'
baseline_commit: '51d34f64cca83f82cea31c30bb1883280bec3032'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les installateurs ne savent télécharger en option qu'un seul modèle (`-WithMiniCPM`, PR #82). Ajouter Qwen3.5-0.8B, puis les modèles des specs B à D, demanderait une option par modèle, en double dans `install.ps1` et `install.sh`.

**Approach:** Une liste unique de modèles facultatifs, avec pour chacun un identifiant court, une URL à révision épinglée, un nom de fichier, une taille et une licence. Cette liste est lue par une option `-Models id1,id2` (PowerShell) et par `WAVESTACK_MODELS=id1,id2` (bash, et PowerShell sous `irm | iex`). Elle commence avec `qwen3.5-0.8b` et `minicpm5`. `-WithMiniCPM` et `WAVESTACK_WITH_MINICPM=1` restent des alias, puisqu'ils sont publiés en 1.2.0. Qwen3.5-2B reste téléchargé d'office et chargé par défaut.

## Boundaries & Constraints

**Always:**
- Qwen3.5-0.8B : `unsloth/Qwen3.5-0.8B-GGUF`, révision `6ab461498e2023f6e3c1baea90a8f0fe38ab64d0`, `Qwen3.5-0.8B-Q4_K_M.gguf`, 532 517 120 octets, sha256 `bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517`, Apache-2.0. Son gabarit est identique à `tests/fixtures/qwen3_5_chat_template.jinja` (vérifié le 2026-10-24) : aucun code de reconnaissance à écrire.
- Même schéma pour chaque modèle : idempotent, `.part` puis renommage, rien en mode à blanc (`-DryRun` / `WAVESTACK_DRY_RUN=1`, qui affiche les modèles demandés).
- Un identifiant inconnu arrête l'installateur avant tout téléchargement, avec la liste des identifiants valides.
- Une seule source de vérité pour les URL : les tests comparent ps1, sh et `docs/installation.md`.
- Décision du 2026-10-24 (empreinte) : chaque modèle facultatif est vérifié après téléchargement, avec `Get-FileHash -Algorithm SHA256` (PowerShell) ou `sha256sum` (repli sur `shasum -a 256` sous macOS) en bash. Un fichier non conforme est supprimé (le `.part`), et l'installateur s'arrête avec un message clair. Un fichier déjà présent n'est pas revérifié (idempotence, pas de relecture de 1,5 Go à chaque lancement). MiniCPM5 : sha256 `ec2d5801640099e97d8d7e8003ad4d81f336e757811f03a26173dddf386602fd`, 1 561 318 368 octets.
- Décision du 2026-10-24 (liste) : `-Models list` / `WAVESTACK_MODELS=list` affiche la table (identifiant, fichier, taille, licence), puis s'arrête sans rien installer, cloner ni télécharger.

**Never:**
- Ne pas changer ce que fait l'installateur sans option (le téléchargement de Qwen3.5-2B n'est pas vérifié par empreinte dans cette story).
- Pas de téléchargement de modèle de chat depuis l'interface.

</frozen-after-approval>

## Code Map

- `install.ps1` -- variables `$QwenUrl`/`$QwenFile` (l. ~45), param `-WithMiniCPM` et bloc MiniCPM5 (PR #82) à remplacer par la table et une boucle. L'alias `-WithMiniCPM` ajoute `minicpm5` à la liste.
- `install.sh` -- même chose (`MINICPM_URL`, `WITH_MINICPM`). Avec `set -u`, chaque variable doit avoir une valeur par défaut.
- `install.bat` -- délègue à `install.ps1`, ne pas modifier.
- `tests/test_installers.py` -- tests MiniCPM5 de la PR #82 (`MINICPM_URL`, `test_install_ps1_minicpm_dry_run`, `test_install_sh_minicpm_only_on_request`) à généraliser à la table.
- `docs/installation.md` (« Installeur en une commande », « Le modèle local ») -- remplacer le paragraphe MiniCPM5 par une table des modèles facultatifs.
- `docs/modeles.md` (« Deux modèles locaux ») -- passer à « plusieurs modèles locaux ».
- `src/wavestack/config.py` -- `DEFAULT_MODEL_FILE` inchangé.

## Tasks & Acceptance

**Execution:**
- [x] `install.ps1`, `install.sh` -- table des modèles facultatifs, option `-Models` / `WAVESTACK_MODELS`, alias MiniCPM5, erreur sur identifiant inconnu.
- [x] `docs/installation.md`, `docs/modeles.md` -- table et exemples (`-Models qwen3.5-0.8b`, `curl … | WAVESTACK_MODELS=qwen3.5-0.8b bash`).
- [x] `tests/test_installers.py` -- URL identiques partout pour chaque entrée ; mode à blanc avec et sans `-Models` ; alias ; identifiant inconnu (code de sortie non nul, rien créé) ; `-Models list` (table affichée, rien créé) ; vérification d'empreinte sur un petit fichier local servi sans réseau (fonction de vérification isolée ou URL `file://`), empreinte fausse : fichier supprimé et arrêt.
- [x] `tests/test_tools.py` ou `tests/test_model_switch.py` -- un test qui charge la fixture Qwen3.5 sous l'architecture `qwen35` et un nom de fichier 0.8B, et vérifie la famille `qwen3` et le lecteur `qwen3_coder`.

**Acceptance Criteria:**
- Given `-Models qwen3.5-0.8b,minicpm5`, when l'installateur tourne deux fois, then les deux fichiers sont téléchargés une seule fois, à côté de Qwen3.5-2B.
- Given `-Models inconnu`, when l'installateur tourne, then il s'arrête avant tout téléchargement et liste les identifiants valides.
- Given `-WithMiniCPM`, when l'installateur tourne, then le comportement est celui de la 1.2.0.

## Implementation Notes

- 2026-10-24, CI Windows : `Get-FileHash` introuvable quand Windows PowerShell 5.1 est lancé depuis PowerShell 7, qui lui transmet son `PSModulePath` (runner GitHub, ou `install.bat` tapé dans un terminal pwsh). `install.ps1` calcule donc l'empreinte avec `[Security.Cryptography.SHA256]` de .NET. La décision reste la même (empreinte SHA-256 vérifiée), seul l'outil change.

## Spec Change Log

## Review Triage Log

Revue du 2026-10-24 (Opus, branche à jour de `origin/main`). Le téléchargement réel de Qwen3.5-0.8B (empreinte, taille, idempotence, tour Outils) a été vérifié par l'orchestrateur.

- **medium**, revue : `[string]$Models` fait échouer la forme documentée `.\install.ps1 -Models a,b` saisie dans une session PowerShell (ou `& ([scriptblock]::Create(...)) -Models a,b`) : la virgule donne un tableau, et la liaison au paramètre échoue (« Impossible de convertir la valeur en type System.String »). Les tests passaient par `-File`, qui transmet une chaîne. **Corrigé** : `[string[]]$Models`, rejoint par `,`, test `test_install_ps1_models_as_a_powershell_array` (rouge avant le correctif).
- **low**, second avis 1 : `grep -qx` lit l'identifiant comme une expression régulière, et `WAVESTACK_MODELS='qwen3[.]5-0.8b'` passait la validation sans rien installer. **Corrigé** : `grep -Fxq`, test `test_install_sh_model_id_is_not_a_pattern` (rouge avant le correctif).
- **low**, second avis 2 : `list` mêlé à d'autres identifiants affiche la table et ignore le reste. C'est un choix de conception cohérent avec la décision « affiche la table puis s'arrête », identique en ps1 et en sh. **Rejeté**.
- **low**, second avis 3 : le sha256 n'est pas dans la table de la doc. La spec demande que les URL soient identiques partout, pas l'empreinte ; ps1 et sh sont comparés au test (`test_optional_model_row_is_complete`). **Consigné**.
- **low**, second avis 4 : les tests d'empreinte isolent la fonction et ne couvrent pas le site d'appel. L'enchaînement téléchargement, vérification, renommage est en trois lignes visibles, et il a été vérifié en réel par l'orchestrateur. **Consigné**.
- **low**, second avis 5 : `_sh` et `_ps` héritaient des `WAVESTACK_*` du poste, ce qui pouvait fausser les assertions « rien sans option ». **Corrigé** : `_clean_env()`.
- **low**, second avis 6 : `is (len(option) == 2)` dépendait de la forme du paramétrage. **Corrigé** : `is ("-Models" in option)`.
- **false**, second avis 7 : le test 0.8B réutilise la fixture du 2B. C'est voulu par la spec, et le gabarit est identique octet pour octet (vérifié le 2026-10-24). **Rejeté**.
- **low**, revue : sans `sha256sum` ni `shasum`, `install.sh` s'arrête (code 127) en laissant le `.part`, qui sera écrasé au lancement suivant. Les deux outils sont présents sur les cibles Linux et macOS. **Consigné**.
- **low**, revue : dans `install.sh`, `for id in $(...)` n'est pas entre guillemets, donc un identifiant `*` passe par l'expansion des noms de fichiers. L'installateur s'arrête quand même sur un identifiant inconnu, et le seul effet est un message d'erreur qui cite un nom de fichier. **Consigné**.
- Complexité : 0 constat (aucune structure qui grossit pendant l'exécution).

## Verification

**Commands:**
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected: OK
- `uv run pytest -q --tb=short tests/test_installers.py` -- expected: vert

**Manual checks (if no CLI):**
- Sur le PC cible seulement : `.\install.ps1 -Models qwen3.5-0.8b -NoLaunch`, puis choisir Qwen3.5-0.8B dans WaveStack, activer Outils et demander « Combien font 12 × 37 ? ».
