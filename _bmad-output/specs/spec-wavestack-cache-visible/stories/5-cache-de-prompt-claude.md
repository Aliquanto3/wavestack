---
title: 'Story 5 : cache de prompt Claude, 5 min ou 1 h'
type: 'feature'
created: '2026-10-24'
status: 'review'
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

**Approach:** Un réglage `off` / `5m` / `1h` (off par défaut), propre aux modèles `anthropic_messages`. Actif, les outils, le `system` et le dernier message de la requête partent avec un point de cache : le préfixe fixe seul est trop court pour le seuil du fournisseur, c'est la conversation qui grandit qui se met en cache. L'écriture à 1 h est facturée ×2 le prix d'entrée (×1,25 pour 5 min, déjà déclaré). Les cases de la story 1 se remplissent d'après la réponse, sans rien changer à leur contrat.

## Boundaries & Constraints

**Où vit le réglage :**
- Défaut : `[cloud] claude_cache = "off"` dans `wavestack.toml` ; surcharge dans `settings.json` (`cloud.claude_cache`), écrite par la session seule (comme `context.window`). Valeur hors `off`/`5m`/`1h` (illisible, booléen, casse) : `off`.
- Changement dans le panneau (celui du modèle cloud, à côté de la fenêtre de contexte) par l'intention `claude_cache` (`POST /api/intentions/claude_cache`, `AppSession.set_claude_cache`), sur le modèle de `set_context_window` : acceptée en `idle` seulement, sinon `SendRefused` avec la raison ; enregistrée dans `settings.json` ; prend effet à l'appel suivant, sans recharger.
- Le réglage est global à la séance, pas un champ d'entrée `[[cloud.models]]`. Il ne vaut que pour `api = "anthropic_messages"` : les autres API ne reçoivent jamais `cache_control` (non-but du lot).

**Sans clé Claude :**
- « Clé Claude » : au moins une entrée de `cfg.cloud_models[0]` avec `api == "anthropic_messages"` et `config.cloud_key(entry) is not None` (`config.py:1353` : clé de `api_keys.json` pour l'hôte de l'entrée, sinon variable `key_env`). C'est le test qui grise une entrée du panneau cloud (`DiagnosticSession._cloud_refusal`, `session/diagnostic.py:948-958`) et qui donne son `key_set` (`diagnostic.py:1003`) : réutiliser `config.cloud_key`, sans relire `api_keys.json` ni écrire un second test. L'état est recalculé à chaque lecture de l'état du panneau : une clé saisie pendant la séance dégrise le sélecteur sans relancer.
- Sans clé : le sélecteur est grisé, avec sa raison (clé Claude absente, où la saisir). `set_claude_cache` lève `SendRefused` avec la même raison. La valeur déjà enregistrée n'est pas effacée ; elle reste sans effet tant qu'aucun appel Claude ne part.
- Avec une clé mais un autre modèle actif : le sélecteur reste actif, avec la mention « s'applique aux modèles Claude ».

**Points de cache (préfixe stable) :**
- Ordre du préfixe Anthropic : outils, `system`, messages. Trois points au plus (le fournisseur en accepte quatre) : le dernier outil de `tools` (s'il y en a), le dernier bloc de `system` (s'il y en a) et le dernier bloc du dernier message.
- Pourquoi un point sur le dernier message (décision de la revue de spec du 2026-10-24) : mesuré sur la configuration par défaut avec `claude_haiku`, le `system` fait 124 caractères et les 3 outils 993 caractères de JSON ; toutes briques allumées, 1 823 et 2 469 caractères, soit de l'ordre du millier de tokens au plus (`chars_per_token = 4`). C'est sous le seuil du fournisseur ou à sa limite basse : avec les seuls points du préfixe fixe, le scénario de la story 6 ne montrerait aucune écriture. L'historique de WaveStack ne fait que s'allonger : pas de fenêtre glissante (un dépassement est une erreur, les stratégies de `app_session.py:433` ne sont que proposées), la mémoire va dans le `system`, et seuls un vidage de la conversation ou une compaction (V1.4) le réécrivent. Deux écarts connus, qui ne coûtent qu'une écriture et que la jauge montre : un résultat d'outil d'un tour passé devient son `stub` dans l'historique (`_step_messages`, `app_session.py:4238-4241`), et les extraits RAG du message courant ne sont pas repris dans l'historique. Dans la boucle d'outils d'un tour, la requête suivante prolonge exactement la précédente : lecture assurée au-dessus du seuil.
- Dernier message : `cache_control` sur son dernier bloc s'il est de type `text`, `tool_result` ou `tool_use` ; sinon (bloc de réflexion), pas de point d'historique pour cet appel. Réglage actif, chaque message dont le `content` est une chaîne non vide part en liste d'un bloc `{"type": "text", "text": …}`, qu'il soit dernier ou non : la forme d'un message ne change pas quand il cesse d'être le dernier, et le préfixe reste octet pour octet celui de l'appel précédent. Une chaîne vide reste une chaîne, sans point.
- `system` : avec le réglage actif et un texte non vide, `system` devient une liste d'un bloc `{"type": "text", "text": <textes joints par "\n\n">, "cache_control": …}` ; le texte est identique à la chaîne d'aujourd'hui. Réglage `off` : corps de requête octet pour octet identique à aujourd'hui (chaînes, aucun `cache_control`).
- `cache_control` : `5m` → `{"type": "ephemeral"}` ; `1h` → `{"type": "ephemeral", "ttl": "1h"}`. Même durée sur tous les points (un point à 1 h ne peut suivre un point à 5 min). Aucun en-tête bêta à ajouter.
- Seuil du fournisseur : sous le minimum de tokens cachables du modèle (seuil du fournisseur, propre à chaque modèle, non déclaré dans le catalogue), Anthropic ne cache rien et répond `cache_creation = 0`. Ce n'est pas une erreur : la jauge (story 2) montre tout en « Non caché ». Le texte du réglage le dit en une phrase, sans nombre. Le fournisseur ne cherche un préfixe déjà écrit que sur un nombre limité de blocs avant chaque point : un tour très long en appels d'outils peut repartir en écriture (limite assumée, dite dans la fiche de la story 6, sans nombre).
- Pour la story 6 : le geste qui montre « écriture puis lecture » doit faire dépasser ce seuil par la conversation (texte long collé dans le message, ou résultat de `fetch_page` dans la boucle d'outils), jamais compter sur le prompt système seul.
- Où le réglage s'applique : `render_chat_body` reçoit `cache_ttl` et ne le passe qu'au traducteur `anthropic_messages`. Seul `_render_chat` (`app_session.py:4671` : tours et sous-agent, requête affichée comprise) le fournit ; les laboratoires (`_run_lab`, `_rag_lab_generate`, `_mcp_lab_ask_loop`) et « Tester » (`diagnostic.py:1091`) restent sans `cache_control`.

**Prix et multiplicateur 1 h :**
- Déclaré ou dérivé : `CloudPricing` reçoit `cache_write_1h_usd_per_mtok` (optionnel, `≥ 0`, mêmes validations que `cache_write_usd_per_mtok`). Absent, il vaut `2.0 × input_usd_per_mtok` (constante `CACHE_WRITE_1H_FACTOR` dans `cloud_base.py`, règle Anthropic : ×2 l'entrée). Déclaré dans `wavestack.toml` pour `claude_haiku` (2,0) et `claude_sonnet` (4,0) ; l'exemple Opus commenté (`wavestack.toml:605-616`) reste sur la dérivation.
- `call_cost` et `cache_savings` reçoivent `cached_write_1h` : la part 1 h au prix 1 h, le reste de l'écriture au prix 5 min déjà déclaré (`cache_write_usd_per_mtok`, sinon prix d'entrée). `cache_write_usd` somme les deux parts ; `cache_priced` reste faux seulement quand le prix 5 min d'une part 5 min est absent (la part 1 h a toujours un prix, déclaré ou dérivé).
- Part 1 h = `cache_write_1h_tokens` de la story 1, lu dans la réponse (`usage.cache_creation.ephemeral_1h_input_tokens`), borné par `cache_write_tokens`. Absente (réponse sans détail) : toute l'écriture compte à 5 min, sans repli sur le réglage envoyé (limite assumée, signalée dans le code ; l'API actuelle donne ce détail).
- Cohérence avec CAP-5 (×1,25 ou ×2) : ×2 est assuré par la dérivation ; ×1,25 vient du prix 5 min déclaré, qui peut manquer à une entrée ajoutée par le formateur. Sans lui, la règle CAP-4 vaut (prix d'entrée, `cache_priced` faux, « prix non déclaré ») : pas de dérivation ×1,25 implicite. Un test vérifie que chaque entrée `anthropic_messages` livrée dans `wavestack.toml` déclare l'écriture 5 min à 1,25 fois l'entrée et l'écriture 1 h à 2 fois.
- Commentaire de `wavestack.toml:518-520` réécrit : le cache n'est plus « jamais activé ».

**Lien avec `cache_write_1h_tokens` :** le champ reste celui de la réponse (story 1), jamais déduit du réglage. Réglage 1 h : écriture au premier appel avec `cache_write_1h_tokens == cache_write_tokens`, lecture ensuite. Réglage 5 min : `cache_write_1h_tokens` vaut 0 si le détail est donné, `None` sinon. Réglage `off` : écriture 0. Le bilan (story 4) lit ces champs et rien d'autre ; aucun champ de payload n'est ajouté.

**Effet sur le plafond `[finops] max_session_usd` :**
- Aucun changement du contrôle : `session_cap_error` compare le total de la séance au plafond avant l'appel ; aucune prime d'écriture n'est estimée d'avance.
- Le coût réel d'un appel inclut déjà la prime (×1,25 ou ×2 sur l'écriture), et `record_spend` l'ajoute au total : un premier appel avec écriture 1 h peut dépasser le plafond du coût de cet appel, comme tout appel en cours (règle déjà écrite dans `[finops]`). Commentaire de `[finops]` complété d'une phrase.
- Les appels sans `pricing` restent hors plafond.

**Never:**
- Pas de `cache_control` pour une autre API (OpenAI, Gemini, Mistral, Groq), pas plus de trois points par requête, pas de bouton « Vider le cache » en cloud (story 3, grisé).
- Pas de nouvel appel réseau, pas de nouvelle dépendance, pas de changement des noms de champs de la story 1, de `ConsumptionUpdatedPayload` ni de la signature de `record_spend`.
- Aucun test n'appelle l'API réelle.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Réglage off (défaut) | Claude actif, aucun réglage | corps identique à aujourd'hui : `system` chaîne, aucun `cache_control` | N/A |
| 5 min | `claude_cache = "5m"`, system + 2 outils, un message | `system` : un bloc avec `{"type": "ephemeral"}` ; seul le dernier des outils porte `cache_control` ; le message part en un bloc texte qui porte le point | N/A |
| 1 h | `claude_cache = "1h"` | idem avec `"ttl": "1h"` sur les trois points | N/A |
| Deuxième tour | 5 min, `short_memory`, sans outil | messages passés en blocs texte sans point, seul le dernier le porte ; le corps du tour 2 reprend celui du tour 1 octet pour octet jusqu'à la fin de son message (points mis à part) | N/A |
| Boucle d'outils | 5 min, appel 2 d'un tour | le dernier bloc `tool_result` porte le point ; le corps de l'appel 1 (points mis à part) est préfixe de celui de l'appel 2 | N/A |
| Sans outil | 5 min, `tools` vide | points sur le bloc `system` et le dernier message ; pas de clé `tools` | N/A |
| Sans system | texte vide | pas de `system` ; points sur le dernier outil et le dernier message | N/A |
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

- `src/wavestack/context/render.py:472-520` `_anthropic_messages` -- paramètre `cache_ttl: Literal["5m", "1h"] | None` ; `system` en un bloc, messages chaînes en blocs, `cache_control` sur le dernier outil, le `system` et le dernier bloc du dernier message. `render_chat_body` (`:644`) reçoit `cache_ttl` et ne le passe qu'à ce traducteur (`TRANSLATORS` garde sa signature commune). Le découpage en segments (sentinelles de `_attribute`) reste exact : la concaténation des segments égale le corps envoyé (`_assert_sent_as_traced` de `tests/test_anthropic_messages.py`, à rejouer cache actif). Même fonction pour la requête envoyée et celle affichée : le formateur voit les points de cache dans la requête.
- `src/wavestack/config.py` -- `claude_cache` (accesseur validé, défaut `off`) ; `CloudPricing.cache_write_1h_usd_per_mtok` (`:165-171`).
- `src/wavestack/models/cloud_base.py:285-359` -- `CACHE_WRITE_1H_FACTOR`, `call_cost` et `cache_savings` avec `cached_write_1h` ; appel dans `ended()` avec `cache_write_1h_tokens` de la réponse.
- `src/wavestack/models/anthropic_messages.py` -- adaptateur : le réglage arrive à `_anthropic_messages` seulement pour cette API.
- `src/wavestack/config.py:1353` `cloud_key` -- test de la clé Claude, réutilisé tel quel (comme `session/diagnostic.py:948-1005`).
- `src/wavestack/session/app_session.py:4671` `_render_chat` -- seul appelant qui passe `cache_ttl`.
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
- [ ] `tests/test_claude_cache.py` -- fausse API (`httpx.MockTransport` ou faux serveur du dépôt) qui capture le corps : cas off, 5 min, 1 h, sans outil, sans system, autre API, deuxième tour (préfixe octet pour octet), boucle d'outils, segments = corps envoyé ; réponses fausses avec création, lecture, détail 1 h, sans détail ; coût aux deux durées, prix déclaré et dérivé ; plafond ; intention (idle, hors idle, sans clé, valeur illisible). Aucun appel réel.
- [ ] Réaligner : `tests/test_anthropic_messages.py`, `tests/test_cloud_cap.py` (`call_cost`, `cache_savings`), tests de config des prix (dont : entrées `anthropic_messages` livrées à ×1,25 et ×2 l'entrée) ; `git grep` sur l'E2E et le texte du sélecteur ; `docs/guide.md` si un parcours change.

**Acceptance Criteria:**
- Given le réglage par défaut, when un appel Claude part, then le corps est identique à celui d'avant la story.
- Given 5 min ou 1 h, when un appel Claude part, then le dernier outil, le bloc `system` et le dernier bloc du dernier message portent `cache_control` (avec `ttl: "1h"` pour 1 h) et aucune autre API n'en reçoit.
- Given une fausse réponse avec écriture 1 h, when l'appel se termine, then `cache_write_1h_tokens` vient de la réponse et le coût compte l'écriture à ×2 (dérivé) ou au prix déclaré.
- Given une écriture mixte, then la part 1 h et la part 5 min sont facturées chacune à leur prix, et `cache_write_usd` en est la somme.
- Given aucune clé Claude, then le sélecteur est grisé avec sa raison et l'intention est refusée.
- Given le plafond, then `session_cap_error` est inchangé et le coût réel inclut la prime d'écriture.

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_claude_cache.py tests/test_anthropic_messages.py tests/test_cloud_cap.py tests/test_cache_per_call.py` -- expected : vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected : vert.

## Spec Change Log

- 2026-10-24, revue de spec (rôle d'Anaël, run de nuit) : point de cache ajouté sur le dernier message (préfixe fixe mesuré sous le seuil du fournisseur, historique en ajout seul), messages chaînes en blocs quand le cache est actif ; test de clé Claude cité (`config.cloud_key`) ; `cache_ttl` limité à `_render_chat` ; cohérence ×1,25 / ×2 précisée, avec un test des prix livrés ; exemple Fable inexistant retiré. Non retenu : repli sur le réglage envoyé quand le détail 1 h manque (l'API le donne ; contrat de la story 1 inchangé). Plafond : inchangé, cohérent avec CAP-5 et `[finops]`.

## Review Triage Log

## Revue

### Passe 1 (2026-10-24, SHA revu e802bd0)

Base : origin/main e15cc3e, inchangée au `git fetch` (pas de rebase nécessaire).

- **Important**, medium, reviewer : une clé Claude saisie en séance ne dégrisait pas le sélecteur. `/api/state` rend le dernier `context_window_state` émis, et `set_api_key` n'en émettait aucun. Corrigé : `use_api_key` (appelé par la route après chaque clé) réémet l'état du panneau. Test rouge sans le correctif, vert avec.
- **Nit**, low, second avis 4 : le test « sans clé » remplaçait `config.cloud_key` par un monkeypatch (module interne). Corrigé : `api_keys.json` vidé dans le dossier de données temporaire et `ANTHROPIC_API_KEY` retirée, puis une vraie clé est saisie (dégrisage vérifié).
- **Nit**, low, second avis 1 : écarté. Une chaîne vide reste une chaîne sans point, comme la spec le demande (« Une chaîne vide reste une chaîne, sans point »), déjà testé.
- **Nit**, low, second avis 2 : reporté à la story 6. La mémoire globale, les skills chargés et le prompt système vivent dans `system` : les modifier en cours de séance réécrit tout le cache (préfixe Anthropic). C'est le comportement attendu, mais la spec ne le dit pas : la fiche de la story 6 doit le mentionner, voire en faire un geste de démonstration.
- **Nit**, low, second avis 3 : écarté, déjà dans la spec (« Absente : toute l'écriture compte à 5 min… limite assumée ») et dans le code de `run_call`.
- **Nit**, low, second avis 5 : écarté, déjà dans la spec (« aucune prime d'écriture n'est estimée d'avance ») et dans le commentaire de `[finops]`.
- Vérifié : avec `off`, le corps de `_anthropic_messages` est identique octet pour octet à celui de main, sur une boucle d'outils avec réflexion, des `system` vides et un message vide (comparaison directe avec le traducteur d'origin/main). Le test `test_off_sends_the_body_as_before` fige déjà la forme exacte.
- Complexité : 0 constat. `_claude_cache_locked` lit `api_keys.json` une fois par entrée à chaque émission de l'état du panneau, sur une liste courte et hors de la boucle de tour.
- Tests : `test_claude_cache`, `test_anthropic_messages`, `test_cloud_cap`, `test_cache_per_call`, `test_cloud`, `test_context_window_setting` et `test_web_app` verts. E2E `claude_cache` et `context_window` : 55 vérifications réussies, 0 échec. Contrôle rapide vert.
