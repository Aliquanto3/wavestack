---
title: 'Story 3 : mémoire résidente d''un modèle servi par llama-server, lue dans son processus'
type: 'fix'
created: '2026-10-28'
status: 'draft'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/src/wavestack/models/servers.py'
  - '{project-root}/src/wavestack/models/discovery.py'
  - '{project-root}/src/wavestack/models/catalog.py'
  - '{project-root}/_bmad-output/specs/spec-wavestack-lfm3/rapport-mesures-2026-10-28.md'
---

## Intent

`servers.served_bytes` (`models/servers.py:983-1004`) estime la mémoire d'un modèle servi par
llama-server : taille du fichier + `served_kv × n_ctx`. Mesure du 2026-10-28 sur le PC cible
(LFM3-1.7B QAD-Q4_0, `-c 16384`) : 2 112 Mo résidents, 1 218 Mo privés, pour une estimation de
1 353 Mo. L'écart vient du réarrangement des poids Q4_0 pour le CPU (repack, ≈ 800 Mo) et des
tampons de calcul (≈ 200 Mo), que l'estimation ignore ; il dépend de la quantification, du CPU
et des options de lancement (`--no-repack` : 1 308 Mo résidents).

**Décision d'Anaël (2026-10-28)** : le budget compte la **mémoire résidente** du processus
llama-server, **lue** avec psutil, plutôt qu'estimée. Un modèle servi est toujours déjà chargé :
sa mémoire se lit, elle ne se devine pas.

Repli, quand le processus est introuvable ou illisible (serveur sur un autre poste, processus
d'un autre utilisateur, accès refusé) : l'estimation actuelle, avec deux corrections bornées :

1. une provision de tampons de calcul (`SERVER_BUFFERS_BYTES`) ;
2. un chemin `-m` relatif résolu sous `config.models_dir()` seulement. Aujourd'hui `_local`
   (l.1031) le rejette, à juste titre puisqu'il est relatif au dossier de llama-server (test
   `test_llama_server_relative_model_path_is_not_read_here`, `tests/test_model_servers.py:1701`),
   et l'estimation se réduit à la taille du fichier. Le diagnostic le dit déjà
   (`candidate.context_counted`, `discovery.py:234`, texte `diagnostic.served.no_cache`).

Hors périmètre : le repack dans le repli (il dépend du CPU et de la quantification) ; la part
par emplacement du cache à fenêtre glissante (cache unifié, ≈ 2,5 Mo par emplacement pour
LFM3) ; Ollama (il donne déjà sa mémoire dans `/api/ps`).

## Given/When/Then

- Given un modèle servi par llama-server sur `http://127.0.0.1:8080` et un processus à l'écoute
  de ce port dont `memory_info().rss` vaut 2 112 Mo, When `served_bytes`, Then 2 112 Mo, sans
  lire l'en-tête du fichier.
- Given un serveur sur une adresse qui n'est pas la boucle locale (`http://192.168.1.20:8080`),
  When `served_bytes`, Then aucun processus n'est cherché et le repli s'applique.
- Given un serveur sur la boucle locale dont le processus est introuvable (`pid` absent) ou
  illisible (`psutil.AccessDenied`, `psutil.NoSuchProcess`), When `served_bytes`, Then le repli
  s'applique, sans exception.
- Given le repli et un modèle dont le KV est lisible, When `served_bytes`, Then taille + KV ×
  `n_ctx` + `SERVER_BUFFERS_BYTES`.
- Given le repli et un KV illisible, When `served_bytes`, Then taille du fichier +
  `SERVER_BUFFERS_BYTES`, et `context_counted` reste faux.
- Given un `model_path` relatif (`LFM3-1.7B-QAD-Q4_0.gguf`) présent sous `config.models_dir()`,
  When la découverte construit le candidat, Then `gguf_path` est le chemin absolu sous
  `models_dir()`, `context_counted` est vrai et le repli compte le KV.
- Given un `model_path` relatif absent de `models_dir()` (même s'il existe dans le dossier
  courant de WaveStack), When la découverte construit le candidat, Then rien n'est lu,
  `context_counted` est faux (comportement actuel, test l.1701 inchangé).
- Given un modèle Ollama, When `served_bytes`, Then rien ne change (`resident_size` ou
  `ollama_load_bytes`), et aucun processus n'est cherché.

## Tâches

1. `src/wavestack/models/servers.py` : `_server_rss(url) -> int | None`. Hôte de `url` sur la
   boucle locale (réutiliser la règle de `config._is_loopback`, l.190, en la rendant publique
   si besoin, sans la recopier), sinon `None`. Puis `psutil.net_connections(kind="tcp")` :
   premier `pid` d'une connexion `CONN_LISTEN` sur ce port, puis
   `psutil.Process(pid).memory_info().rss`. Tout `psutil.Error` (et `OSError`) → `None`.
   Commentaire d'une ligne : `rss` est le working set sous Windows, le « résident » mesuré.
2. `servers.served_bytes`, branche llama-server (Ollama inchangé, placé avant) : renvoyer
   `_server_rss(model.server_url)` quand il n'est pas `None` ; sinon le repli. Repli : l'actuel
   + `SERVER_BUFFERS_BYTES`, constante du module avec un commentaire `shortcut:` (tampons de
   calcul seulement, repack non compté ; valeur mesurée sur LFM3, à revoir si le repli devient
   courant). Valeur : 256 Mio (tampons mesurés ≈ 200 Mo). Mettre à jour la docstring.
3. `servers.py`, `_local` devient `local_path(path)` (public, un seul endroit pour la règle) :
   chemin absolu → tel quel ; chemin relatif → `config.models_dir() / path` s'il désigne un
   fichier, sinon `None`. Commentaire d'une ligne : un chemin relatif est celui de
   llama-server, seul le dossier des modèles de WaveStack est un ancrage sûr. Remplacer les
   copies de la règle : `_header_dimensions` (l.293) et `catalog.header_path`
   (`catalog.py:420-421` ; import circulaire `catalog` → `discovery` → `servers` à vérifier,
   sinon import local comme `_header_kv`).
4. `src/wavestack/models/discovery.py` (l.226) : `candidate.gguf_path =
   servers.local_path(model.model_path) or model.model_path`, pour que la carte, le budget et
   le tableau lisent le même fichier.
5. `src/wavestack/session/app_session.py`, `_cost` (l.1946-1948) : inchangé (il lit
   `served_bytes`). Vérifier seulement que `_reload_cost` (l.1968) ne touche pas llama-server.
6. Pas de nouveau texte : `diagnostic.served.no_cache` couvre le chemin non résolu ; le chiffre
   affiché reste `served_bytes`.

## Tests

- `tests/test_model_servers.py` (jamais un vrai llama-server ni un vrai port : monkeypatch de
  `psutil.net_connections` et `psutil.Process`, ou de `servers._server_rss`) :
  - nouveau : processus trouvé sur la boucle locale → `served_bytes` = son `rss` ;
  - nouveau : hôte distant → `net_connections` n'est pas appelé, repli ;
  - nouveau : `pid` absent, puis `psutil.AccessDenied` → repli, sans exception ;
  - nouveau : `model_path` relatif présent sous `models_dir()` (le `conftest` pose
    `WAVESTACK_DATA_DIR` sur `tmp_path`, copier `TINY` dans `models/`) → lu, `context_counted`
    vrai ;
  - `test_llama_server_relative_model_path_is_not_read_here` (l.1701) : inchangé, vert ;
  - `test_llama_server_memory_counts_its_whole_context` (l.1653),
    `test_llama_server_kv_unreadable_counts_the_file_and_keeps_the_warning` (l.1691),
    `test_llama_server_with_several_slots_counts_the_whole_context` (l.1710) : attentes
    réalignées sur `+ SERVER_BUFFERS_BYTES` (constante importée, jamais recopiée), avec
    `_server_rss` neutralisé (`None`) pour qu'un llama-server réel du poste ne fausse pas le
    test. Neutraliser de même dans tout autre test existant qui appelle `served_bytes` sur
    llama-server (chercher `served_bytes` et `list_served` dans `tests/`).
- `tests/test_model_catalog.py::test_llama_server_capabilities_from_props` (l.166),
  `tests/test_discovery.py`, `tests/test_memory_budget.py`, `tests/test_global_memory.py` :
  verts.
- `uv run pytest -q --tb=short tests/test_model_servers.py tests/test_model_catalog.py tests/test_discovery.py tests/test_memory_budget.py tests/test_global_memory.py`
- `uv run python .claude/cost-kit/controle_rapide.py`

## E2E à rejouer (non lancé par cette story)

Scénarios du diagnostic qui affichent la mémoire d'un modèle servi (chercher `served` dans
`tools/e2e/`), avec le faux llama-server de `tools/e2e/stack.py` : ce faux serveur tourne sur
la boucle locale, le chiffre affiché devient le résident du processus Python qui l'héberge.
Si un scénario vérifie une valeur exacte, le réaligner ou neutraliser la lecture dans la pile
E2E, et le dire dans le rapport. Recette par Anaël : LFM3 servi depuis le dossier des modèles,
chiffre du diagnostic comparé au « Plage de travail » du Gestionnaire des tâches.

## Choix faits à la place d'Anaël

- Repli sans repack : un réarrangement qui dépend du CPU et de la quantification ne se devine
  pas sans mesure ; la lecture couvre le cas courant (llama-server sur ce poste).
- `SERVER_BUFFERS_BYTES` en constante plutôt qu'une clé de `wavestack.toml` : une valeur
  mesurée, pas un réglage pour l'utilisateur.
- Ancrage du chemin relatif sur `models_dir()` seulement, jamais sur le dossier courant de
  WaveStack ni sur une recherche par nom : pas de faux fichier lu.
- Lecture à chaque découverte, sans cache : un appel de `net_connections` par modèle servi,
  quelques millisecondes.
