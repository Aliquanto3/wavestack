---
title: 'Story 4 : bilan consolidé par conversation et depuis le lancement'
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

**Problem:** Le Bilan de la séance (`record_spend`, `_spend` global, `renderSpendPanel`) cumule des dollars et des secondes depuis le lancement, sans tokens, et « Vider la conversation » ne le touche pas. Le participant ne voit ni la répartition lecture, écriture et non caché, ni où part l'argent, ni le signal d'un cache perdu, ni sa seule conversation.

**Approach:** Cumuler, à côté des totaux existants, les cinq champs de cache de la story 1 et la ventilation du coût par poste, dans deux registres : « Depuis le lancement » (le `_spend` actuel, inchangé) et « Cette conversation » (nouveau, remis à zéro avec la conversation). `ConsumptionUpdatedPayload` porte les deux colonnes ; `bar.js` les rend avec un anneau SVG « où part l'argent » et le signal d'écriture.

## Boundaries & Constraints

**Deux colonnes :**
- **Depuis le lancement** : le `_spend` actuel. Champs plats existants de `ConsumptionUpdatedPayload` inchangés (valeurs, noms), plus `cache` et `ring` (ci-dessous). Remis à zéro par un relancement seul, jamais par « Vider la conversation », « Réinitialiser » ni un scénario.
- **Cette conversation** : nouveau registre `_spend_conv`, même forme, exposé dans `conversation` (modèle `SpendColumn`, mêmes champs de coût, d'économie, de cache et d'anneau que la colonne du lancement). Remis à zéro par `reset_conversation_spend()`, appelé à chaque endroit où `app_session` vide `_history` : `clear_conversation()` et `_reconfigure()` (`reset()` et le changement de scénario passent tous deux par là). La remise à zéro émet un `consumption_updated` (sinon la colonne affiche l'ancienne valeur jusqu'au prochain appel) ; la colonne du lancement y est inchangée. `reset_conversation_spend(eur_per_usd, emit)` émet sous `_spend_lock`, comme `record_spend`, pour garder l'ordre des émissions.
- Le bilan se rend dès qu'une colonne a compté quelque chose. `session_spend` (rechargement de page) renvoie les deux colonnes ; sa condition `counted` inclut désormais un appel aux cases de cache comptées (un appel local sans empreinte ni temps évité, un appel cloud sans prix ni empreinte).

**Quels appels comptent dans quelle colonne :**
- Appel de tour (chat principal, sous-agent, appel local compris), compression du tour : **les deux colonnes**. Le sous-agent appartient à la conversation ; ses tokens sont déjà dans `_spend` (pas de double compte, une seule inscription par appel dans chaque registre).
- Appel hors conversation (« Tester », « LLM nu », ateliers, tout appel sans `turn_id`) : **colonne du lancement seule**. Ils ne sont pas dans l'historique que « Vider la conversation » efface.
- `record_spend` reçoit `in_conversation: bool`, posé par l'appelant d'après `current().turn_id is not None` (même test que `_count_impact`). Valeur par défaut `False`. Pour un appel cloud, l'appelant est `ended()` dans `cloud_base.py`, qui importe `current` de `wavestack.trace.scope`.
- Un appel aux cases comptées passe toujours par `record_spend`, même sans coût ni empreinte : la garde `if out.cost is not None or impact is not None` de `ended()` s'élargit à `cache_origin is not None`, et `_count_impact` ne sort plus tôt quand il reçoit `cache`. Sinon un appel Groq sans empreinte, ou un appel local du moteur intégré, manquerait aux totaux.
- Compression : n'a pas de cases de cache ; ne touche que `compression_saved_usd` (et `saved_calls`) de ses colonnes.

**Cumul des tokens, `None` compris (règle de la story 1 : `None` n'est jamais sommé comme 0) :** pour chacune des cases `read`, `write`, `write_1h`, `uncached`, le registre garde `tokens` (somme des valeurs déclarées, 0 compris), `declared` (nombre d'appels qui l'ont déclarée) et `undeclared` (nombre d'appels qui ne l'ont pas déclarée). `cache_origin == "local"` avec `cache_uncached_tokens` `None` n'est ni déclaré ni non déclaré : « sans objet », non compté. Un appel dont `cache_origin` est `None` (trace antérieure au lot) n'est pas compté du tout.
- Lecture du total d'une case, rendue dans `bar.js` :
  - `declared == 0` et `undeclared == 0` : tiret, ou « sans objet en local » pour le non caché ;
  - `declared == 0` et `undeclared > 0` : « non déclaré » (jamais 0) ;
  - `undeclared == 0` : valeur exacte ;
  - `declared > 0` et `undeclared > 0` : **total partiel**, « ≥ N (partiel : k appels sur n) ». Ce n'est pas une somme exacte, et elle n'entre ni dans le calcul du signal d'écriture ni dans un pourcentage.
- `write_1h` : la ligne « Écriture cache 1 h » n'est rendue que si au moins un appel l'a déclarée (`declared > 0`). « Écriture cache 5 min » = `write.tokens − write_1h.tokens` (`write_1h` `None` compte pour 0 de la part 1 h : le fournisseur n'en détaille pas, le reste est écrit pour 5 min, règle de la story 1) ; son statut (exact, partiel, non déclaré) est celui de `write`.
- Invariant testé : pour chaque case, `tokens` égale la somme des cases déclarées des appels comptés ; pour les appels aux quatre cases déclarées, `read + write + uncached` du registre égale la somme des `prompt_tokens`.

**Ventilation du coût, anneau « où part l'argent » :**
- Postes, dans l'ordre et avec le vocabulaire d'agent-cost-kit : « Lecture cache », « Écriture cache 5 min », « Écriture cache 1 h », « Non caché » (entrée facturée plein tarif), « Sortie ». Un poste à 0 $ n'a pas de segment mais garde sa ligne de légende si un appel l'a compté.
- Source : `ended()` de `cloud_base.py` calcule, avec les prix déclarés, `ring_usd = {read, write_5m, write_1h, fresh, out}` pour l'appel, et le passe à `record_spend(ring=...)`. Une fonction pure `cost_ring(pricing, prompt_tokens, cached_read, cached_write, cost, cached_write_1h=0)` le calcule, avec **les mêmes comptes bornés et les mêmes prix de repli que `call_cost`** : `cached_read`/`cached_write` de `_cached_tokens(usage)` (absent = 0), bornés comme dans `call_cost` ; un prix de lecture ou d'écriture absent vaut le prix d'entrée (CAP-4). `read = cached_read × prix lecture`, `write_1h = cached_write_1h × prix 1 h`, `write_5m = (cached_write − cached_write_1h) × prix écriture`, `out = cost.output_usd`, **`fresh = cost.input_usd − read − write_5m − write_1h`** (reste : il vaut le non caché au prix d'entrée et absorbe l'arrondi). Invariant : `sum(ring_usd) == cost.input_usd + cost.output_usd` à l'arrondi flottant près, donc l'anneau égale le coût total affiché.
- **Part 1 h et story 5 (ordre de fusion libre) :**
  - Story 5 absente de `main` : `call_cost` facture toute l'écriture au prix 5 min. `ended()` n'envoie pas `cached_write_1h` (défaut 0) : toute l'écriture va dans `write_5m`, et `write_1h` vaut 0 $, sans segment ni ligne de légende. Jamais de part 1 h glissée dans `fresh`. Les **tokens** 1 h (`write_1h` du registre, story 1) restent comptés et rendus, indépendamment du prix.
  - Story 5 présente : `ended()` passe à `cost_ring` le même `cached_write_1h` que celui donné à `call_cost` (`payload["cache_write_1h_tokens"] or 0`), et le prix 1 h vient de `write_1h_price(pricing)` (fonction de la story 5, prix déclaré ou ×2 l'entrée), jamais recalculé.
  - **La story fusionnée en second branche la ligne 1 h** : elle ajoute l'argument `cached_write_1h` à l'appel de `cost_ring` dans `ended()`, importe `write_1h_price` dans `cost_ring`, et ajoute le test « write 150 dont 50 à 1 h → `write_1h` = 50 × prix 1 h, somme = coût ». La première fusionnée ne touche pas au périmètre de l'autre.
- Seuls les appels chiffrés (`pricing` déclaré) alimentent l'anneau. Appel local, Groq, Mistral (sans prix) : pas de poste, et la légende dit « n appels sans prix déclaré, hors anneau ». Sans appel chiffré dans la colonne, pas d'anneau : le texte « aucun appel chiffré » à la place.
- Composant : **nouveau**, `ringSvg(segments, label)` dans `bar.js` (aucun anneau ni camembert n'existe ; `savingsBar` est une barre HTML, qui reste telle quelle). Un `<svg role="img" aria-label>` à `<circle>` en `stroke-dasharray` sur le même cercle (un par poste, décalés par `stroke-dashoffset`), sans bibliothèque ni dépendance. Pas de couleur seule : à côté de l'anneau, une légende en liste (`<ul>`) donne pour chaque poste son nom, son montant en $ et sa part en %, et l'`aria-label` résume le plus gros poste (« Où part l'argent : Lecture cache 62 % du coût »). La légende est du texte visible, pas une info-bulle ; le `<svg>` ne contient pas de `<text>`.
- Couleurs : aucun jeton nouveau (sinon DESIGN.md, `tokens.css` et `test_web_tokens.py` à étendre). Les postes reprennent des jetons existants qui ont déjà leur variante sombre (`[data-theme="dark"]` et `prefers-color-scheme: dark` de `tokens.css`) : « Lecture cache » `--color-segment-global-memory`, « Écriture cache 5 min » `--color-segment-tool-results`, « Écriture cache 1 h » `--color-segment-message`, « Non caché » `--color-segment-tool-descriptions`, « Sortie » `--color-segment-system-prompt` ; piste de fond `--color-line`. Appliquées par classes CSS (`stroke: var(--…)` dans `app.css`), jamais en hex ni en attribut inline, pour suivre le thème. Chaque item de légende porte une pastille de la même classe. Les segments sont séparés par un écart de 1 unité de `stroke-dasharray` (fond visible) pour distinguer deux couleurs voisines. L'information ne tenant pas à la couleur (légende textuelle), le 3:1 de WCAG 1.4.11 n'est pas exigé du trait ; le texte de la légende garde les couleurs de texte du panneau.
- Une colonne, un anneau.

**« Coût sans cache » :**
- Formule : `sans cache = coût réel + cache_saved_usd` de la colonne, `cache_saved_usd` étant l'économie nette signée déjà cumulée, calculée par `cache_savings` comme `cache_full_usd − cost.input_usd` (entrée entière au prix plein, moins l'entrée payée) : gain de lecture `lus × (prix d'entrée − prix de lecture)` **moins** surcoût d'écriture `écrits × (prix d'écriture − prix d'entrée)`, négatif quand l'écriture domine. Vérifié sur le code : `coût réel + cache_saved_usd = entrée au prix plein + sortie`, soit le coût sans cache de l'appel. Seuls les appels à `cache_priced` vrai y entrent (comme aujourd'hui) : un appel au prix de cache partiel n'y apporte rien, et la ligne reste « sur n appels chiffrés ». Dépasse le coût réel quand le cache a économisé, lui est inférieur quand l'écriture a coûté plus que la lecture. Aucune formule nouvelle, aucune relecture du journal.
- Distinct du bloc existant « sans optimisation » (qui y ajoute aussi la compression) : le bilan affiche les deux lignes, « Sans cache » (cache seul) et le bloc existant inchangé.
- Il n'engage que les appels chiffrés avec cache servi ou écriture comptée (`cache_priced_calls`, nouveau compteur, distinct de `saved_calls` qui y mêle la compression). Ligne rendue seulement si `cache_priced_calls > 0`, avec « sur n appels chiffrés ».

**« Temps évité en local » :**
- Formule inchangée : somme de `kv_cache_tokens / kv_prompt_per_second` par appel (`app_session.py:8586-8592`), le débit de lecture du prompt mesuré par le moteur sur cet appel (`READ_MIN_TOKENS` écarte le débit non fiable).
- Seul `llama-server` donne `kv_prompt_per_second`. Pour le moteur intégré et le faux moteur, `cache_read_tokens` existe (story 1) mais sans débit : **aucun temps n'est estimé** (pas de débit inventé). La ligne dit alors « non mesuré » et non 0 si la colonne a des appels locaux avec `cache_read_tokens` > 0 mais `kv_time_saved_s == 0`. Sans appel local, la ligne est cachée.
- Le temps s'additionne dans les deux colonnes (`kv_time_saved_s` du registre de la colonne).

**Signal « beaucoup d'écriture : le cache se perd » :**
- Calculé sur la colonne « Cette conversation » seule (jamais sur le lancement, que plusieurs conversations mêlent).
- Condition : `write.tokens − cold_write_tokens > read.tokens`, avec `write.declared > 0`, `write.undeclared == 0` et `read.undeclared == 0` (somme exacte des deux côtés ; sinon pas de signal, car un total partiel ne se compare pas). `cold_write_tokens` est l'écriture du **premier appel de la colonne qui a déclaré l'écriture** (amorçage du cache), retenue à son inscription (O(1)) et remise à zéro avec la colonne. Un seul appel ne peut donc jamais allumer le signal. Le seuil reste strict (`>`) : égalité, rien.
- Écart à SPEC (« quand l'écriture dépasse la lecture »), décidé à la revue de spec : le cumul brut s'allume à tort sur toute conversation saine. Au premier appel, tout est écrit. Au second, la lecture vaut le premier prompt P1 et l'écriture cumulée vaut P1 plus le delta, donc dépasse toujours la lecture. Le seuil « au moins deux appels » de la rédaction n'y changeait rien. En retirant l'amorçage, une conversation saine donne au second appel delta contre P1, sans signal sauf si le nouveau message dépasse tout le premier prompt. Un cache perdu (lecture 0, tout réécrit) allume le signal dès le second appel.
- Rendu : une ligne `role="status"` sous les tokens, jamais seulement une couleur ; texte de `ui.yaml` ; disparaît quand la lecture rattrape l'écriture.

**Textes :** nouvelles clés `common.bar.spend.*` dans `content/ui.yaml` et `content/i18n/{en,de}/ui.yaml` (colonnes, cases, « total partiel », « non déclaré », « sans objet en local », poste de l'anneau, `aria-label`, signal). Vocabulaire de la SPEC.

**Never:**
- Pas de jauge ni de bouton (stories 2 et 3), pas de `cache_control` ni de prix 1 h (story 5 ; la story 4 utilise `write_1h_price()` seulement si elle est fusionnée après la story 5, voir « Part 1 h et story 5 »).
- Pas de relecture du journal pour recalculer un total : cumul par appel, O(1), comme aujourd'hui.
- Pas de somme d'un `None` comme 0, pas de total partiel présenté comme exact.
- Pas de persistance sur disque. Pas de nouvelle dépendance.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Totaux égaux aux appels | 3 appels Anthropic (lecture, écriture, non caché déclarés) | colonne : `read/write/uncached` = sommes ; `read+write+uncached` = somme des `prompt_tokens` ; anneau = coût total | N/A |
| Appel sans détail | OpenAI : écriture `None`, 2 appels dont 1 sans détail de lecture | écriture « non déclaré » ; lecture « ≥ N (partiel : 1 appel sur 2) » | Aucune exception |
| Écriture 5 min et 1 h | write 150, write_1h 50 | « Écriture cache 5 min » 100, « 1 h » 50 | N/A |
| Local, cache réutilisé | 2 appels du faux moteur | lecture et écriture exactes, non caché « sans objet en local », temps « non mesuré » ; anneau : « aucun appel chiffré » | N/A |
| Local `llama-server` | `cache_n` et débit mesuré | temps évité = `cache_n / débit` cumulé | N/A |
| Signal | conversation : 1 appel, tout en écriture | pas de signal (amorçage retiré : 0 > 0 faux) | N/A |
| Signal, cache sain | local : appel 1 écrit 1 000 ; appel 2 lit 1 000, écrit 100 | pas de signal (100 > 1 000 faux) | N/A |
| Signal, cache perdu | appel 1 écrit 1 000 ; appel 2 lit 0, écrit 1 100 | signal affiché ; lancement : pas de signal | N/A |
| Anneau sans story 5 | Anthropic, write 150 dont `write_1h` 50, `cached_write_1h` non passé | `write_5m` = 150 × prix écriture, `write_1h` 0 $ ; somme = coût ; tokens « 5 min » 100 et « 1 h » 50 | N/A |
| Signal, partiel | écriture exacte, lecture partielle | pas de signal | N/A |
| « Vider la conversation » | colonnes non nulles | `conversation` à zéro, `consumption_updated` émis ; colonne du lancement identique | `SendRefused` hors `idle` comme aujourd'hui |
| Changement de scénario ou « Réinitialiser » | idem | `conversation` à zéro, lancement inchangé | N/A |
| Sous-agent | appel cloud dans un tour | compté une fois dans chaque colonne | N/A |
| Appel de l'atelier ou « Tester » | sans `turn_id` | lancement seul ; conversation inchangée | N/A |
| Appel sans prix | Groq | cases comptées, hors anneau, mention « n appels sans prix déclaré » | N/A |
| Trace antérieure au lot | `cache_origin` `None` | aucune case comptée | N/A |
| Concurrence | deux appels simultanés | totaux égaux à la somme, émis dans l'ordre d'inscription (verrou existant `_spend_lock`) | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/models/cloud_base.py:428-526` `_EMPTY`, `_spend`, `_spend_payload`, `record_spend`, `session_spend`, `reset_spend` -- étendre : second registre `_spend_conv`, cases de cache (`tokens`, `declared`, `undeclared`), `cache_priced_calls`, anneau ; `record_spend(..., cache=None, ring=None, in_conversation=False)` ; `reset_conversation_spend()` ; `reset_spend()` remet les deux à zéro (tests).
- `src/wavestack/models/cloud_base.py:1000-1120` `ended()` et son appel à `record_spend` (:1110) -- passer les cinq champs de `cache_tokens()` (story 1), `ring_usd` (nouvelle fonction pure `cost_ring`, à côté de `call_cost`), `in_conversation` (`current()` de `wavestack.trace.scope`) ; élargir la garde de `record_spend` aux appels aux cases comptées.
- `src/wavestack/session/app_session.py:8586-8592` `_count_impact` (:8848), `:7419` (compression) -- passer `cache`, `in_conversation` ; `clear_conversation` (:6274) et `_reconfigure` (:6574) appellent `reset_conversation_spend()` puis émettent `consumption_updated`.
- `src/wavestack/trace/catalog.py:489-515` `ConsumptionUpdatedPayload` -- modèles `CacheTotals` (par case : `tokens`, `declared`, `undeclared`), `SpendColumn` ; champs `cache`, `ring`, `cache_priced_calls`, `conversation`.
- `src/wavestack/web/static/bar.js:154-197` `renderSpendPanel` -- deux colonnes, lignes de cases, `ringSvg`, signal, ligne « sans cache », temps évité ; `consumption` (état client) lit `conversation`. Textes : `content/ui.yaml` (`common.bar.spend.*`) et surcouches `en`, `de`.
- `src/wavestack/web/app.py:840` lecteur de `session_spend` -- vérifier qu'il ne dépend que de `total_usd`.
- Lecteurs à réaligner : `git grep -n "consumption_updated\|ConsumptionUpdatedPayload\|session_spend\|record_spend" tests tools src`, E2E compris (forme du bilan, nombre de lignes du panneau).

## Tasks & Acceptance

**Execution:**
- [ ] `trace/catalog.py` -- `CacheTotals`, `SpendColumn`, nouveaux champs de `ConsumptionUpdatedPayload`.
- [ ] `models/cloud_base.py` -- second registre, cumul des cinq cases avec `declared`/`undeclared`, anneau, `cache_priced_calls`, `reset_conversation_spend()`.
- [ ] `session/app_session.py` -- `in_conversation`, `cache`, remise à zéro de la colonne dans `clear_conversation` et `_reconfigure`.
- [ ] `web/static/bar.js`, `content/ui.yaml`, `content/i18n/{en,de}/ui.yaml` -- rendu et textes.
- [ ] `tests/test_cache_bilan.py` -- totaux égaux à la somme des appels (cloud Anthropic, compatible OpenAI, faux moteur local) ; total partiel et non déclaré ; part 5 min et 1 h ; anneau égal au coût (`cost_ring` : prix de lecture ou d'écriture absent, comptes bornés, part 1 h sans story 5) ; signal (1 appel, cache sain, cache perdu, partiel) ; appel Groq sans empreinte et appel local sans temps évité bien comptés ; sous-agent compté une fois ; appel sans `turn_id` hors conversation ; remise à zéro par vidage, scénario et réinitialisation sans toucher au lancement.
- [ ] Tests existants à réaligner (`test_cloud_cap.py` sur `session_spend`, `consumption_updated`, tests de contenu `ui.yaml` fr/en/de), puis E2E du bilan (tranche ciblée, non lancée en local pendant le run).

**Acceptance Criteria:**
- Given plusieurs appels, when le bilan est lu, then chaque total de case égale la somme des valeurs déclarées des appels, et le coût de l'anneau égale `total_usd` de la colonne.
- Given un appel qui ne déclare pas une case, then le total est « non déclaré » (aucun appel déclaré) ou « partiel » (mélange), jamais 0 ni une somme présentée comme exacte.
- Given « Vider la conversation », un changement de scénario ou « Réinitialiser », then la colonne « Cette conversation » repart de zéro et « Depuis le lancement » est identique.
- Given une conversation dont l'écriture, amorçage du premier appel retiré, dépasse la lecture, totaux exacts, then le signal apparaît ; avec un seul appel, un cache sain au second appel ou un total partiel, il n'apparaît pas.
- Given un appel sans prix, then ses cases sont comptées et il reste hors de l'anneau, avec la mention.
- Given l'anneau, then il est un `svg` à `role="img"` et `aria-label`, doublé d'une légende textuelle (montant et part).

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_cache_bilan.py tests/test_cache_per_call.py tests/test_cloud_cap.py tests/test_anthropic_messages.py` -- expected : vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected : vert.

## Spec Change Log

- 2026-10-24, rédaction (run de nuit ; choix à relire par Anaël) :
  - Signal d'écriture : au moins deux appels mesurés et totaux exacts, en plus de `write > read` de la SPEC.
  - Appels hors tour (ateliers, « Tester », « LLM nu ») : colonne du lancement seule.
  - Temps évité local : formule existante, limitée à `llama-server` ; pas de débit inventé pour le moteur intégré.
  - Anneau : `fresh` calculé par reste pour que la somme égale le coût ; dépend de `write_1h_price` (story 5) pour la part 1 h.
  - Compatibilité : champs plats de `ConsumptionUpdatedPayload` inchangés (= colonne du lancement).
- 2026-10-24, revue de la spec avant code (Opus, au nom d'Anaël pour la nuit) :
  - Signal : la règle « au moins deux appels » ne tenait pas, car au second appel d'une conversation saine l'écriture cumulée dépasse toujours la lecture. Elle est remplacée par le retrait de l'amorçage (`cold_write_tokens`).
  - Anneau : `cost_ring` reprend les comptes bornés et les prix de repli de `call_cost`. Sans story 5, la part 1 h vaut 0 $ et toute l'écriture va dans le poste 5 min, jamais dans `fresh`. La story fusionnée en second branche `cached_write_1h` et `write_1h_price()`, qui est une fonction de la story 5 et non un champ.
  - « Sans cache » : le signe a été vérifié (`cache_saved_usd = cache_full_usd − cost.input_usd`). La rédaction disait à tort « plus le surcoût d'écriture ».
  - Couleurs de l'anneau : cinq jetons `--color-segment-*` existants, qui ont déjà leur variante sombre, appliqués par classes CSS. Aucun jeton nouveau.
  - Garde d'inscription élargie : un appel aux cases comptées passe par `record_spend` même sans coût ni empreinte. `session_spend` le compte aussi, et la remise à zéro émet sous verrou.
  - Appels hors tour dans la seule colonne du lancement : choix confirmé, cohérent avec CAP-3. « Cette conversation » couvre ce que « Vider la conversation » efface.

## Review Triage Log
