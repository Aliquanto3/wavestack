# Carte du harnais : sous-systèmes et rôles (CAP-3)

Source : Barbaste et al., *Harness Engineering*, Wavestone AI Lab, arXiv 2609.00006 (7 sous-systèmes) ; Böckeler, martinfowler.com (guides et capteurs). Placement validé au point de contrôle de la story 2 (revue du 2026-10-24).

## Sous-systèmes

Identifiants de code ; libellés anglais exacts du papier (tableau 1, §2.3, vérifiés le 2026-10-24), dans son ordre ; fr et de traduits.

| Id | fr | en | de |
|---|---|---|---|
| `loop` | Boucle de l'agent | Agent loop | Agentenschleife |
| `llm` | Intégration du LLM | LLM integration | LLM-Integration |
| `tools` | Outils et actions | Tools & actions | Werkzeuge und Aktionen |
| `memory` | Mémoire et contexte | Memory & context | Gedächtnis und Kontext |
| `security` | Sécurité et permissions | Safety & permissions | Sicherheit und Berechtigungen |
| `orchestration` | Orchestration | Orchestration | Orchestrierung |
| `extensibility` | Extensibilité | Extensibility | Erweiterbarkeit |

## Rôles (Böckeler)

- `guide` : oriente le modèle avant qu'il agisse.
- `sensor` (capteur) : observe ce qui se passe et bloque ou corrige ; **calculé** (règle déterministe) ou **déduit** (jugé par un modèle).
- `none` : capacité donnée au modèle, ni guide ni capteur.

## Placement des briques

| Brique | Discipline (CAP-1) | Sous-système | Rôle |
|---|---|---|---|
| Prompt système | prompt | `memory` | guide |
| Raisonnement | harness | `llm` | none |
| Mémoire courte (dont compaction, fenêtre glissante) | context | `memory` | none |
| Mémoire globale | context | `memory` | guide |
| RAG | context | `memory` | none |
| Compression | context | `memory` | none |
| Skills | context | `extensibility` | guide |
| Outils natifs (dont `search_documents`) | harness | `tools` | none |
| MCP | harness | `extensibility` | none |
| Hooks | harness | `extensibility` | guide et capteur calculé (H3 injecte, H1 bloque) |
| Garde-fous | harness | `security` | capteur déduit |
| Sous-agent | harness | `orchestration` | none |

## Sans brique

Un sous-système sans brique affiche ce que le cœur du harnais y fait toujours, pour qu'aucune case ne reste vide :
- `loop` : boucle d'appels et bornes (`session.limits.calls`, `session.limits.retries` de `messages.yaml`) ;
- `llm` : moteur local ou fournisseur cloud, gabarit de conversation ;
- `orchestration` : journal des étapes, vue Orchestration.

## Règles pour le test d'exhaustivité

- Chaque brique du registre a un sous-système parmi les 7 identifiants et un rôle parmi `guide`, `sensor`, `none` (une brique peut cumuler `guide` et `sensor`).
- Un rôle `sensor` précise `computed` ou `inferred`.
- Chaque identifiant a son libellé dans `ui.yaml` fr, en et de.
