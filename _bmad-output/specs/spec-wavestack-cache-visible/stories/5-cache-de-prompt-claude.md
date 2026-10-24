---
title: 'Story 5 : cache de prompt Claude, 5 min ou 1 h'
type: 'feature'
created: '2026-10-24'
status: 'ready-for-dev'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/brownfield.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-cache-visible/stories/1-donnees-de-cache-par-appel.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** WaveStack n'envoie jamais `cache_control` à Anthropic (`wavestack.toml:518-520`) : le `system` part en une chaîne (`context/render.py:472-520`) et les prix d'écriture déclarés ne servent qu'à compter juste si le cache servait. Le formateur ne peut donc pas montrer en vrai l'écriture au premier appel, la lecture aux suivants et la différence entre 5 min et 1 h.

**Approach:** Un réglage `off` / `5m` / `1h` (off par défaut), propre aux modèles `anthropic_messages`. Actif, le `system` et les outils partent avec un point de cache. L'écriture à 1 h est facturée ×2 le prix d'entrée (×1,25 pour 5 min, déjà déclaré). Les cases de la story 1 se remplissent d'après la réponse, sans rien changer à leur contrat.

## Boundaries & Constraints

**Où vit le réglage :**
- Défaut : `[cloud] claude_cache = "off"` dans `wavestack.toml` ; surcharge dans `settings.json` (`cloud.claude_cache`), écrite par la session seule (comme `context.window`). Valeur hors `off`/`5m`/`1h` (illisible, booléen, casse) : `off`.
- Changement dans le panneau (celui du modèle cloud, à côté de la fenêtre de contexte) par l'intention `claude_cache` (`POST /api/intentions/claude_cache`, `AppSession.set_claude_cache`), sur le modèle de `set_context_window` : acceptée en `idle` seulement, sinon `SendRefused` avec la raison ; enregistrée dans `settings.json` ; prend effet à l'appel suivant, sans recharger.
- Le réglage est global à la séance, pas un champ d'entrée `[[cloud.models]]`. Il ne vaut que pour `api = "anthropic_messages"` : les autres API ne reçoivent jamais `cache_control` (non-but du lot).

**Sans clé Claude :**
- « Clé Claude » : au moins une entrée `anthropic_messages` dont la clé est enregistrée (même test que celui qui active ses entrées dans le panneau cloud).
- Sans clé : le sélecteur est grisé, avec sa raison (clé Claude absente, où la saisir). `set_claude_cache` lève `SendRefused` avec la même raison. La valeur déjà enregistrée n'est pas effacée ; elle reste sans effet tant qu'aucun appel Claude ne part.
- Avec une clé mais un autre modèle actif : le sélecteur reste actif, avec la mention « s'applique aux modèles Claude ».

**Points de cache (préfixe stable) :**
- Ordre du préfixe Anthropic : outils, `system`, messages. Deux points : le dernier outil de `tools` (s'il y en a) et le dernier bloc de `system`. Aucun point sur l'historique : WaveStack le réécrit par conception (fenêtre, troncature, compression, mémoire), il n'est pas stable.
- `system` : avec le réglage actif et un texte non vide, `system` devient une liste d'un bloc `{"type": "text", "text": <textes joints par "\n\n">, "cache_control": …}` ; le texte est identique à la chaîne d'aujourd'hui. Réglage `off` : corps de requête octet pour octet identique à aujourd'hui (chaîne, aucun `cache_control`).
- `cache_control` : `5m` → `{"type": "ephemeral"}` ; `1h` → `{"type": "ephemeral", "ttl": "1h"}`. Même durée sur les deux points (un point à 1 h ne peut suivre un point à 5 min). Aucun en-tête bêta à ajouter.
- Seuil du fournisseur : sous le minimum de tokens cachables du modèle, Anthropic ne cache rien et répond `cache_creation = 0`. Ce n'est pas une erreur : la jauge (story 2) montre tout en « Non caché ». Le texte du réglage le dit en une phrase, sans nombre par modèle (non déclaré dans le catalogue).

**Prix et multiplicateur 1 h :**
- Déclaré ou dérivé : `CloudPricing` reçoit `cache_write_1h_usd_per_mtok` (optionnel, `≥ 0`, mêmes validations que `cache_write_usd_per_mtok`). Absent, il vaut `2.0 × input_usd_per_mtok` (constante `CACHE_WRITE_1H_FACTOR` dans `cloud_base.py`, règle Anthropic : ×2 l'entrée). Déclaré dans `wavestack.toml` pour `claude_haiku` (2,0) et `claude_sonnet` (4,0) ; les exemples Opus et Fable commentés restent sur la dérivation.
- `call_cost` et `cache_savings` reçoivent `cached_write_1h` : la part 1 h au prix 1 h, le reste de l'écriture au prix 5 min déjà déclaré (`cache_write_usd_per_mtok`, sinon prix d'entrée). `cache_write_usd` somme les deux parts ; `cache_priced` reste faux seulement quand le prix 5 min d'une part 5 min est absent (la part 1 h a toujours un prix, déclaré ou dérivé).
- Part 1 h = `cache_write_1h_tokens` de la story 1, lu dans la réponse (`usage.cache_creation.ephemeral_1h_input_tokens`), borné par `cache_write_tokens`. Absente (réponse sans détail) : toute l'écriture compte à 5 min, sans repli sur le réglage envoyé (limite assumée, signalée dans le code).
- Commentaire de `wavestack.toml:518-520` réécrit : le cache n'est plus « jamais activé ».

**Lien avec `cache_write_1h_tokens` :** le champ reste celui de la réponse (story 1), jamais déduit du réglage. Réglage 1 h : écriture au premier appel avec `cache_write_1h_tokens == cache_write_tokens`, lecture ensuite. Réglage 5 min : `cache_write_1h_tokens` vaut 0 si le détail est donné, `None` sinon. Réglage `off` : écriture 0. Le bilan (story 4) lit ces champs et rien d'autre ; aucun champ de payload n'est ajouté.

**Effet sur le plafond `[finops] max_session_usd` :**
- Aucun changement du contrôle : `session_cap_error` compare le total de la séance au plafond avant l'appel ; aucune prime d'écriture n'est estimée d'avance.
- Le coût réel d'un appel inclut déjà la prime (×1,25 ou ×2 sur l'écriture), et `record_spend` l'ajoute au total : un premier appel avec écriture 1 h peut dépasser le plafond du coût de cet appel, comme tout appel en cours (règle déjà écrite dans `[finops]`). Commentaire de `[finops]` complété d'une phrase.
- Les appels sans `pricing` restent hors plafond.

**Never:**
- Pas de `cache_control` pour une autre API (OpenAI, Gemini, Mistral, Groq), pas de point sur l'historique, pas de bouton « Vider le cache » en cloud (story 3, grisé).
- Pas de nouvel appel réseau, pas de nouvelle dépendance, pas de changement des noms de champs de la story 1, de `ConsumptionUpdatedPayload` ni de la signature de `record_spend`.
- Aucun test n'appelle l'API réelle.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Réglage off (défaut) | Claude actif, aucun réglage | corps identique à aujourd'hui : `system` chaîne, aucun `cache_control` | N/A |
| 5 min | `claude_cache = "5m"`, system + 2 outils | `system` : un bloc avec `{"type": "ephemeral"}` ; dernier outil seul porte `cache_control` | N/A |
| 1 h | `claude_cache = "1h"` | idem avec `"ttl": "1h"` sur les deux points | N/A |
| Sans outil | 5 min, `tools` vide | seul le bloc `system` porte le point ; pas de clé `tools` | N/A |
| Sans system | texte vide | pas de `system` ; point seulement sur le dernier outil | N/A |
| Autre API | `openai_chat`, réglage 1 h | aucun `cache_control` | N/A |
| Premier appel 1 h | usage : `cache_creation=800`, `ephemeral_1h=800` | write 800, write_1h 800 ; coût écriture 800 × prix 1 h | N/A |
| Appel suivant | `cache_read=800` | read 800 ; coût lecture au prix déclaré | N/A |
| Prix 1 h dérivé | entrée sans `cache_write_1h_usd_per_mtok`, input 2,0 | prix 1 h 4,0 $/Mtok | N/A |
| Prix 1 h déclaré | `cache_write_1h_usd_per_mtok = 3,0` | utilisé, pas dérivé | N/A |
| Écriture mixte | write 150, 1h 50 | 50 au prix 1 h, 100 au prix 5 min | N/A |
| Détail absent | write 150, pas de `ephemeral_1h` | 150 au prix 5 min, `cache_write_1h_tokens` `None` | N/A |
| Sous le seuil | réglage 5 min, `cache_creation=0` | écriture 0, tout en non caché | Aucune erreur |
| Sans clé Claude | aucune entrée Anthropic avec clé | sélecteur grisé avec raison ; intention refusée | `SendRefused` |
| Intention hors `idle` | état `streaming` | refus avec raison, rien d'écrit | `SendRefused` |
| Valeur illisible | `settings.json` : `"2h"`, `true` | `off` | Aucune exception |
| Plafond | total à 4,99 $ sur 5 $, appel 1 h | envoyé ; total peut dépasser ; appel suivant refusé | cause `max_session_usd` |

</frozen-after-approval>

## Code Map

- `src/wavestack/context/render.py:472-520` `_anthropic_messages` -- paramètre `cache_ttl: Literal["5m", "1h"] | None` ; `system` en un bloc, `cache_control` sur le dernier outil. Même fonction pour la requête envoyée et celle affichée : le formateur voit les points de cache dans la requête.
- `src/wavestack/config.py` -- `claude_cache` (accesseur validé, défaut `off`) ; `CloudPricing.cache_write_1h_usd_per_mtok` (`:165-171`).
- `src/wavestack/models/cloud_base.py:285-359` -- `CACHE_WRITE_1H_FACTOR`, `call_cost` et `cache_savings` avec `cached_write_1h` ; appel dans `ended()` avec `cache_write_1h_tokens` de la réponse.
- `src/wavestack/models/anthropic_messages.py` -- adaptateur : le réglage arrive à `_anthropic_messages` seulement pour cette API.
- `src/wavestack/session/app_session.py:2611` (modèle) -- `set_claude_cache`, état exposé au panneau avec la raison de grisage ; `src/wavestack/web/app.py:971` -- route d'intention.
- `src/wavestack/web/static/app.js` et `ui.yaml` -- sélecteur trois positions, textes en fr, `content/i18n/{en,de}/` ; seuil et « s'applique aux modèles Claude ».
- `wavestack.toml:276-296, 518-520, 557, 586, 691-696` -- défaut, commentaires `[finops]` et Anthropic, prix 1 h, doc `pricing`.
- À vérifier : `git grep -n "_anthropic_messages\|cache_write_usd_per_mtok" src tests tools docs`.

## Tasks & Acceptance

**Execution:**
- [ ] `config.py`, `wavestack.toml` -- réglage `claude_cache`, `cache_write_1h_usd_per_mtok`, commentaires.
- [ ] `render.py` -- blocs `system`, `cache_control` sur le dernier outil ; `off` inchangé.
- [ ] `cloud_base.py` -- prix 1 h déclaré ou dérivé, coût et `cache_savings` à deux durées.
- [ ] `app_session.py`, `web/app.py` -- intention `claude_cache`, raison sans clé, enregistrement dans `settings.json`.
- [ ] Interface : sélecteur, textes fr/en/de, grisage.
- [ ] `tests/test_claude_cache.py` -- fausse API (`httpx.MockTransport` ou faux serveur du dépôt) qui capture le corps : cas off, 5 min, 1 h, sans outil, sans system, autre API ; réponses fausses avec création, lecture, détail 1 h, sans détail ; coût aux deux durées, prix déclaré et dérivé ; plafond ; intention (idle, hors idle, sans clé, valeur illisible). Aucun appel réel.
- [ ] Réaligner : `tests/test_anthropic_messages.py`, `tests/test_cloud_cap.py` (`call_cost`, `cache_savings`), tests de config des prix ; `git grep` sur l'E2E et le texte du sélecteur ; `docs/guide.md` si un parcours change.

**Acceptance Criteria:**
- Given le réglage par défaut, when un appel Claude part, then le corps est identique à celui d'avant la story.
- Given 5 min ou 1 h, when un appel Claude part, then le dernier outil et le bloc `system` portent `cache_control` (avec `ttl: "1h"` pour 1 h) et aucune autre API n'en reçoit.
- Given une fausse réponse avec écriture 1 h, when l'appel se termine, then `cache_write_1h_tokens` vient de la réponse et le coût compte l'écriture à ×2 (dérivé) ou au prix déclaré.
- Given une écriture mixte, then la part 1 h et la part 5 min sont facturées chacune à leur prix, et `cache_write_usd` en est la somme.
- Given aucune clé Claude, then le sélecteur est grisé avec sa raison et l'intention est refusée.
- Given le plafond, then `session_cap_error` est inchangé et le coût réel inclut la prime d'écriture.

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_claude_cache.py tests/test_anthropic_messages.py tests/test_cloud_cap.py tests/test_cache_per_call.py` -- expected : vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected : vert.

## Spec Change Log

## Review Triage Log
