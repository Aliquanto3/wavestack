---
title: 'Story 3 : mémoire résidente d''un modèle servi par llama-server, lue dans son processus'
type: 'bugfix'
created: '2026-10-28'
status: 'ready-for-dev'
route: 'dispatch'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-lfm3/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-lfm3/rapport-mesures-2026-10-28.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** `servers.served_bytes` (`src/wavestack/models/servers.py:983`) estime un modèle
servi par llama-server à taille du fichier + KV × `n_ctx` : 1 353 Mo pour LFM3-1.7B à
`-c 16384`, contre 2 112 Mo résidents mesurés sur le PC cible le 2026-10-28 (repack des poids
Q4_0 ≈ 800 Mo et tampons de calcul ≈ 200 Mo non comptés). Servi avec un `-m` relatif, il ne
compte que la taille du fichier.

**Approach:** décision d'Anaël du 2026-10-28 : quand llama-server tourne sur ce poste, lire la
mémoire résidente (`psutil`, `memory_info().rss`) du processus à l'écoute de son port. Repli
quand le processus est introuvable ou illisible : l'estimation actuelle plus une provision de
tampons de calcul `SERVER_BUFFERS_BYTES`, et un `-m` relatif résolu sous `config.models_dir()`
seulement.

## Boundaries & Constraints

**Always:**
- Lecture seulement pour une URL de serveur sur la boucle locale (`localhost`, `127.0.0.0/8`,
  `::1`), règle unique de `config._is_loopback` (rendue publique si besoin, jamais recopiée).
- Toute erreur de lecture (`psutil.Error`, `OSError`, aucun `pid`) donne le repli, jamais
  d'exception.
- Un chemin relatif n'est résolu que sous `config.models_dir()`, et seulement s'il y désigne un
  fichier ; jamais sous le dossier courant de WaveStack ni par recherche de nom.
- Une seule règle de chemin local (`servers.local_path`) pour `served_bytes`, `served_kv`,
  `ollama_load_bytes`, `_header_dimensions`, `catalog.header_path` et la découverte.
- Les tests ne voient jamais un vrai llama-server ni la mémoire d'un vrai processus.

**Never:**
- Ne pas modifier Ollama (`resident_size` de `/api/ps`, `ollama_load_bytes`) ni lui chercher
  de processus.
- Ne pas estimer le repack dans le repli (dépend du CPU et de la quantification), ni la part
  par emplacement du cache à fenêtre glissante.
- Pas de clé de `wavestack.toml`, pas de nouveau texte d'interface (`diagnostic.served.no_cache`
  couvre le chemin non résolu), pas de cache de la lecture.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Lu | llama-server sur `http://127.0.0.1:8080`, processus à l'écoute de 8080 avec `rss` = 2 112 Mo | `served_bytes` = 2 112 Mo, en-tête non lu | — |
| Hôte distant | `http://192.168.1.20:8080` | `net_connections` jamais appelé ; repli | — |
| Pas de processus | boucle locale, aucun `CONN_LISTEN` sur le port (ou `pid` None) | repli | sans exception |
| Illisible | `psutil.AccessDenied` ou `NoSuchProcess` | repli | sans exception |
| Repli, KV lisible | fichier absolu lisible | taille + KV × `n_ctx` + `SERVER_BUFFERS_BYTES` | — |
| Repli, KV illisible | KV ou fichier illisible | taille (de `/v1/models` ou du fichier) + `SERVER_BUFFERS_BYTES` ; `context_counted` faux | — |
| Relatif présent | `model_path` = `LFM3-1.7B-QAD-Q4_0.gguf`, fichier sous `models_dir()` | `gguf_path` absolu sous `models_dir()`, `context_counted` vrai, le repli compte le KV | — |
| Relatif absent | `model_path` relatif absent de `models_dir()` (même présent dans le dossier courant) | rien n'est lu, `context_counted` faux (test l.1701 inchangé) | — |
| Ollama | modèle Ollama, chargé ou non | inchangé, aucun processus cherché | — |

</intent-contract>

## Code Map

- `src/wavestack/models/servers.py:983-1002` -- `served_bytes(model, path, window)` : branche Ollama d'abord (`resident_size`, `ollama_load_bytes`), puis taille + `served_kv × n_ctx`. Ajouter la lecture pour `engine == "llama_server"` avant le repli, et `SERVER_BUFFERS_BYTES` au repli llama-server.
- `src/wavestack/models/servers.py:1022-1030` -- `served_kv` : appelle `_local(path)` ; passer à `local_path`.
- `src/wavestack/models/servers.py:1033-1034` -- `_local(path)` (absolu seulement) : devient `local_path(path)` publique (absolu tel quel ; relatif → `config.models_dir() / path` si `is_file()`, sinon `None`). Appelants : `served_bytes` (l.993), `ollama_load_bytes` (l.1011), `served_kv` (l.1030).
- `src/wavestack/models/servers.py:290-297` -- `_header_dimensions` recopie la règle (`path if path and Path(path).is_absolute()`) : utiliser `local_path`.
- `src/wavestack/models/servers.py:846` -- `ServedModel.server_url` : URL dont on prend l'hôte et le port (`urllib.parse.urlsplit`, port par défaut 80 / 443 si absent).
- `src/wavestack/config.py:190-196` -- `_is_loopback(host)` : la règle de boucle locale ; utilisée aussi l.275 et 358.
- `src/wavestack/config.py:1449` -- `models_dir()`.
- `src/wavestack/models/catalog.py:414-422` -- `header_path` : pour llama-server, `path if Path(path).is_absolute() else None` ; utiliser `servers.local_path` (import local dans la fonction si l'import en tête crée un cycle `catalog` → `discovery` → `servers`).
- `src/wavestack/models/discovery.py:226` -- `candidate.gguf_path = model.model_path` : `servers.local_path(model.model_path) or model.model_path`.
- `src/wavestack/models/discovery.py:234` -- `context_counted = servers.served_kv(model, model.model_path) is not None` : passer `candidate.gguf_path` (même fichier que la carte et le budget).
- `src/wavestack/session/app_session.py:1946-1958, 1968` -- lecture seule : `_cost` lit `served.served_bytes` ; `_reload_cost` ne concerne qu'Ollama.
- `pyproject.toml:15` -- `psutil>=7.2,<8` déjà en dépendance.
- `tests/conftest.py` -- fixtures `autouse` (l.25-189) : y ajouter celle qui neutralise la lecture.
- `tests/test_model_servers.py:1653-1750` -- tests llama-server de la mémoire (l.1662, 1696, 1708, 1719, 1750), l.1793, 1913, 1942 : attentes à réaligner sur `+ servers.SERVER_BUFFERS_BYTES` quand elles portent sur le repli llama-server ; l.1701 `test_llama_server_relative_model_path_is_not_read_here` inchangé.

Vérification préalable faite le 2026-10-28 sur le poste de dev, session non élevée : `psutil.net_connections(kind="tcp")` trouve en 5 ms le `pid` d'un processus enfant à l'écoute, et `memory_info().rss` est lisible. Sous Windows, `rss` est le working set, le « Plage de travail » du Gestionnaire des tâches.

## Tasks & Acceptance

**Execution:**
- `src/wavestack/config.py` -- rendre `_is_loopback` publique (`is_loopback`, appelants l.275 et 358 mis à jour) -- une seule règle.
- `src/wavestack/models/servers.py` -- `_server_rss(url) -> int | None` (boucle locale sinon `None` ; premier `pid` d'une connexion `CONN_LISTEN` sur le port ; `Process(pid).memory_info().rss` ; `psutil.Error`/`OSError` → `None` ; commentaire d'une ligne sur le working set) ; `served_bytes` lit `_server_rss(model.server_url)` pour llama-server et le renvoie s'il n'est pas `None` ; repli + `SERVER_BUFFERS_BYTES = 256 * 1024**2` avec un commentaire `shortcut:` (tampons mesurés ≈ 200 Mo sur LFM3, repack non compté, à revoir si le repli devient courant) ; `local_path` remplace `_local` et la copie de `_header_dimensions` ; docstrings à jour -- cœur du correctif.
- `src/wavestack/models/catalog.py` -- `header_path` passe par `servers.local_path` -- un seul ancrage.
- `src/wavestack/models/discovery.py` -- `gguf_path` résolu et `context_counted` sur `candidate.gguf_path` -- carte, budget et tableau lisent le même fichier.
- `tests/conftest.py` -- fixture `autouse` qui remplace `servers._server_rss` par `lambda url: None` -- aucun test existant ne lit la mémoire d'un vrai processus (un llama-server réel du poste fausserait les attentes).
- `tests/test_model_servers.py` -- nouveaux tests couvrant chaque ligne de la matrice (monkeypatch de `psutil.net_connections` et `psutil.Process`, dans le module `servers`, la fixture d'en haut levée par `monkeypatch.setattr` du vrai `_server_rss` sauvegardé ou testé directement ; relatif présent : copier `TINY` sous `config.models_dir()`, le `conftest` pose `WAVESTACK_DATA_DIR` sur `tmp_path`) ; attentes existantes du repli llama-server réalignées sur `servers.SERVER_BUFFERS_BYTES` (importée, jamais recopiée) -- garde-fous.

**Acceptance Criteria:**
- Given LFM3 servi par llama-server sur ce poste, when le diagnostic s'affiche, then le chiffre de mémoire du modèle servi est la mémoire résidente de son processus.
- Given le budget mémoire avec un modèle llama-server actif sur ce poste, when `_cost` est calculé à la fenêtre courante, then il part de cette mémoire résidente (plus la marge).
- Given la suite `tests/test_model_servers.py` sur un poste où un vrai llama-server écoute, when elle tourne, then ses résultats ne dépendent pas de ce processus.

## Spec Change Log

## Review Triage Log

## Design Notes

Le `pid` trouvé est celui du processus qui écoute réellement (vérifié : avec le lanceur
`python.exe` d'un venv, c'est l'interpréteur enfant, pas le lanceur) : pour llama-server, le
binaire lui-même. Un appel de `net_connections` par modèle servi et par découverte coûte
quelques millisecondes : pas de cache.

E2E à nommer dans le rapport, pas à lancer : les scénarios du diagnostic qui affichent la
mémoire d'un modèle servi (`grep -rn served tools/e2e/`), avec le faux llama-server de
`tools/e2e/stack.py` sur la boucle locale : le chiffre affiché devient le résident du processus
qui l'héberge. Si un scénario vérifie une valeur exacte, le dire dans le rapport.

## Verification

**Commands:**
- `uv run python -m pytest -q --tb=short tests/test_model_servers.py tests/test_model_catalog.py tests/test_discovery.py tests/test_memory_budget.py tests/test_global_memory.py tests/test_config_paths.py` -- expected: tout vert
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected: OK
