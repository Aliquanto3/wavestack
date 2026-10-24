---
title: 'Modèles facultatifs des installateurs, dont Qwen3.5-0.8B'
type: 'feature'
created: '2026-10-24'
status: 'ready-for-dev'
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
- [ ] `install.ps1`, `install.sh` -- table des modèles facultatifs, option `-Models` / `WAVESTACK_MODELS`, alias MiniCPM5, erreur sur identifiant inconnu.
- [ ] `docs/installation.md`, `docs/modeles.md` -- table et exemples (`-Models qwen3.5-0.8b`, `curl … | WAVESTACK_MODELS=qwen3.5-0.8b bash`).
- [ ] `tests/test_installers.py` -- URL identiques partout pour chaque entrée ; mode à blanc avec et sans `-Models` ; alias ; identifiant inconnu (code de sortie non nul, rien créé) ; `-Models list` (table affichée, rien créé) ; vérification d'empreinte sur un petit fichier local servi sans réseau (fonction de vérification isolée ou URL `file://`), empreinte fausse : fichier supprimé et arrêt.
- [ ] `tests/test_tools.py` ou `tests/test_model_switch.py` -- un test qui charge la fixture Qwen3.5 sous l'architecture `qwen35` et un nom de fichier 0.8B, et vérifie la famille `qwen3` et le lecteur `qwen3_coder`.

**Acceptance Criteria:**
- Given `-Models qwen3.5-0.8b,minicpm5`, when l'installateur tourne deux fois, then les deux fichiers sont téléchargés une seule fois, à côté de Qwen3.5-2B.
- Given `-Models inconnu`, when l'installateur tourne, then il s'arrête avant tout téléchargement et liste les identifiants valides.
- Given `-WithMiniCPM`, when l'installateur tourne, then le comportement est celui de la 1.2.0.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected: OK
- `uv run pytest -q --tb=short tests/test_installers.py` -- expected: vert

**Manual checks (if no CLI):**
- Sur le PC cible seulement : `.\install.ps1 -Models qwen3.5-0.8b -NoLaunch`, puis choisir Qwen3.5-0.8B dans WaveStack, activer Outils et demander « Combien font 12 × 37 ? ».
