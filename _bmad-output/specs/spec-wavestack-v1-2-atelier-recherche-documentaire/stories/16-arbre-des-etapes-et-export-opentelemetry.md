---
title: 'Story 16 : Arbre des étapes et export OpenTelemetry'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/vues.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/brownfield.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/attaques-et-conformite.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-12 : le participant ne voit l'exécution que comme une séquence plate ; `Envelope` porte `step_id` et `parent_step`, mais l'atelier laisse `parent_step` vide et aucune brique OpenTelemetry n'existe (brownfield.md). Le formateur ne peut pas montrer l'exécution dans son Langfuse ou son Phoenix.

**Approach:** Un arbre (course, étape, sous-étape, appel de modèle) construit **par la session à partir du journal** (`trace/tree.py`) et joint à `rag_lab_run_ended` (`steps`), dessiné dans un volet repliable de l'onglet Construire (`rag-tree.js`). Un export OTLP/HTTP (protobuf) aux conventions GenAI, derrière l'extra `otel`, envoyé **par la fabrique réseau** (AD-15) et **seulement** quand `[otel] endpoint` est réglé et que le formateur clique.

## Boundaries & Constraints

**Always:**
- `parent_step` posé de façon générique depuis les identifiants du moteur de chaîne (`rag_lab.parent_step`) : `run.sN` → `run`, `run.sN.index` → `run.sN` ; toute étape ajoutée (RAPTOR, CRAG de la story 12) l'hérite. Un appel de modèle garde le `step_id`/`call_id` de son étape (contrat de `test_rag_lab_generation`) et reçoit `parent_step` = cette étape.
- Rien ne sort sans `[otel] endpoint` (http/https avec hôte, sans identifiants dans l'URL) ; l'hôte n'entre dans `allowed_hosts` que par cette URL.
- Aucun texte (question, passage, prompt, réponse) dans l'arbre ni dans les spans, sauf `[otel] capture_content = true`.
- Seuls `Content-Type`, `User-Agent` et, si `[otel] auth_env` nomme une variable, `Authorization` partent ; jamais une clé de modèle cloud.
- Sans l'extra : l'application démarre, l'API dit l'indisponibilité, le bouton reste caché.

**Never:** service embarqué ; exporteur HTTP du SDK (il contournerait la fabrique) ; dépendance de base nouvelle ; ressource lue dans l'environnement (`OTEL_RESOURCE_ATTRIBUTES`).

</frozen-after-approval>

## I/O & Edge-Case Matrix

| Cas | Entrée | Attendu |
|---|---|---|
| Course normale | chaîne livrée, modèle local | arbre : course, étapes (libellés de `rag_lab_run_started`), appel sous Generation avec tokens |
| Partie avant son étape | index BM25 (`run.sK.index`) émis avant `run.sK` | rattachée à `run.sK` une fois les deux connues |
| Sans URL | `[otel] endpoint` vide | `ready: false`, export 409, aucun `outbound_request` |
| Sans extra | modules `opentelemetry.sdk` absents | `available: false`, raison `rag_lab.otel.missing`, export 409 |
| Collecteur qui refuse | statut ≥ 300 | 502, « statut N » |
| Course inconnue | `run_id` absent du journal | 409 `rag_lab.otel.no_run` |

## Code Map

- `src/wavestack/trace/tree.py` (nouveau) : `run_events`, `build`, `Texts`.
- `src/wavestack/trace/otel.py` (nouveau) : `missing`, `encode` (SDK + encodeur OTLP), `send` (fabrique), `traces_url`.
- `src/wavestack/trace/catalog.py` : `RagLabStep`, `RagLabRunEndedPayload.steps`, origine `otel` des requêtes sortantes ; `trace/scope.py` : `Origin` + `otel`.
- `src/wavestack/rag/lab.py` : `parent_step()`, `TreeTexts`, `RagLabContent.tree`.
- `src/wavestack/session/app_session.py` : `_rag_lab_scope` (parent), portée de l'appel de modèle, `_rag_lab_steps`, `rag_lab_otel`, `export_rag_lab_otel`, `rag_lab_state["otel"]`.
- `src/wavestack/config.py` : `otel_endpoint`, `otel_capture_content`, `otel_auth_env`, `allowed_hosts` ; `wavestack.toml` `[otel]`.
- `src/wavestack/web/app.py` : `GET /api/rag_lab/otel`, `POST /api/rag_lab/otel/export`.
- Front : `rag.html` (volet `#rag-tree`), `rag-tree.js` (nouveau), `rag.css` (bloc final).
- Textes : `content/rag_lab.yaml` `tree:` et `content/messages.yaml` `rag_lab.otel` (fr, en, de).
- `pyproject.toml` extra `otel` (`opentelemetry-sdk==1.44.0`, `opentelemetry-exporter-otlp-proto-common==1.44.0`, même version que l'`opentelemetry-api` déjà verrouillée), `uv.lock`.

## Conventions GenAI appliquées

Source : dépôt `open-telemetry/semantic-conventions-genai` (les conventions GenAI y ont déménagé), lu le 2026-10-25, commit `9ffc7e0` du 2026-10-21, statut *Development*, adossé à semantic-conventions v1.44.0 ; noms d'attributs vérifiés dans `opentelemetry-semantic-conventions` 0.65b0. `schema_url` : `https://opentelemetry.io/schemas/1.44.0`.

- Course : `invoke_workflow wavestack.rag_lab`, INTERNAL, `gen_ai.operation.name=invoke_workflow`, `gen_ai.workflow.name`.
- Appel de modèle : `chat {modèle}`, INTERNAL en local et CLIENT en cloud, `gen_ai.operation.name=chat`, `gen_ai.provider.name` (`llama_cpp` en local, le `provider` de l'entrée cloud), `gen_ai.request.model`, `gen_ai.usage.input_tokens` / `output_tokens`, `gen_ai.response.finish_reasons`.
- Étape de recherche (`vector_search`, `lexical_search`) : `retrieval {option}`, `gen_ai.data_source.id`.
- Autres étapes et parties : INTERNAL, attributs `wavestack.rag_lab.*`. Erreur ou arrêt : statut ERROR et `error.type`.
- Contenu opt-in : `gen_ai.input.messages` / `gen_ai.output.messages` en chaîne JSON (les attributs structurés ne sont pas encore pris sur les spans).

## Tasks & Acceptance

- [x] `parent_step` renseigné sur les événements de l'atelier (étapes, parties, appels de modèle).
- [x] Arbre avec durées et tokens dans l'onglet Construire, rejoué après rechargement (`last_run`).
- [x] Export OTLP aux conventions GenAI vérifié par un faux collecteur HTTP local (port libre).
- [x] Sans réglage, rien ne sort (pytest et E2E `rag_lab_tree`).

## Verification

- `uv run pytest -q tests/test_rag_lab_otel.py` (10 tests ; 3 sautés sans l'extra, dont la CI qui fait `uv sync --locked` sans extra).
- Ciblés : `test_rag_lab`, `test_rag_lab_generation`, `_decision`, `_graphrag`, `_wiki`, `_agentic`, `_views`, `_costs`, `test_net_*`, `test_trace_architecture`, `test_i18n`, `test_ui_texts`, `test_backend_messages`.
- E2E : `rag rag_rerank rag_lab rag_lab_tree` (capture `92-atelier-rag-arbre.jpg`).

## Ce que doit vérifier Anaël à la main (done_checkpoint)

1. `uv sync --extra otel`, lancer Phoenix (`http://localhost:6006`) ou un Langfuse, régler `[otel] endpoint` dans `settings.json`, redémarrer, lancer une chaîne, ouvrir « Arbre des étapes », cliquer « Exporter cette exécution » : la trace s'affiche avec ses spans `chat` et `retrieval` (Langfuse : `auth_env` vers une variable contenant `Basic …`).
2. Sans réglage : note « Rien ne sort du poste sinon », pas de bouton.
3. Avec `capture_content = true` : la question et la réponse apparaissent dans le collecteur.

## Décisions (à revoir par Anaël)

- **Export à la demande** (bouton), jamais automatique à chaque course ; vues.md parle d'un bouton, CAP-12 dit « une exécution produit des spans ». À revoir par Anaël.
- **Pas d'exporteur HTTP du SDK** : l'extra prend `opentelemetry-sdk` + l'encodeur OTLP commun (pas `opentelemetry-exporter-otlp-proto-http` de brownfield.md), l'envoi passe par la fabrique (AD-15). À revoir par Anaël.
- **Règle de journalisation** : aucun texte par défaut (convention GenAI + journal local) ; `capture_content` opt-in envoie question, prompt rendu (celui de l'étape quand elle n'a qu'un appel) et réponses. Le prompt contient les passages. À revoir par Anaël.
- **`auth_env`** : seul moyen d'atteindre un Langfuse (Basic auth) ; nom de variable, jamais la valeur dans la configuration. À revoir par Anaël.
- **Appel de modèle** : `step_id` de son étape conservé, `parent_step` = l'étape elle-même (pas d'identifiant d'appel distinct dans les événements, pour garder le contrat existant) ; l'arbre numérote les appels `étape.cK`. À revoir par Anaël.
- **Changement d'URL = redémarrage** : la garde réseau est installée au démarrage avec `allowed_hosts`. À revoir par Anaël.
- **Origine `otel`** ajoutée aux requêtes sortantes (journal) ; envoi en boucle locale non tracé, comme toute requête loopback (AD-15).
- **Extra épinglé sur 1.44.0** (dernière 1.45.1) pour ne pas relever l'`opentelemetry-api` de la base.

## Reports

- Spans `embeddings` pour l'étape Embedding (nom du modèle à exposer dans l'arbre).
- Arbre et export pour l'onglet Évaluer (plusieurs courses) et pour les courses de mise à jour (l'arbre est déjà joint, non dessiné).
- Tests de l'export en CI : la CI n'installe pas les extras ; un job `--extra otel` les ferait tourner.
- Plusieurs requêtes (`dense_retrieval × 2` de la maquette) : une seule étape par recherche dans l'arbre actuel.

## Spec Change Log

- 2026-10-25 : création et implémentation (dev-story, sans point de contrôle de spec).
