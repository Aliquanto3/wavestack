---
title: 'Story 1 : Bilan et Journal de la barre'
type: 'feature'
created: '2026-10-27'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-retours-2026-10-27/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-retours-2026-10-27/brownfield.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le Bilan de la séance (bar.js) n'affiche un montant que si `c.calls > 0`, or `_accumulate` n'incrémente `calls` que si un coût existe (`cloud_base.py:1266-1281`) : un modèle sans `pricing` (Gemma) laisse une empreinte sans montant. Le texte de la popup déborde (`.bar-flyout-note` sans `overflow-wrap`, `.bar-flyout` sans `min-width: 0`, `pages.css:261-320`). Le Journal (`bar.js:27-48`) ne garde que les `security_event` : aucun appel de modèle n'y apparaît, et rien ne filtre « Sécurité seulement » puisqu'il n'y a rien d'autre à filtrer.

**Approach:** Toujours afficher un montant (0 € avec la mention d'offre gratuite quand `pricing` est absent). Faire déborder le texte proprement à 360 px. Alimenter le Journal avec les appels de modèle de tous les onglets (en plus des décisions de sécurité), en s'appuyant sur les enveloppes déjà émises (`model_call_started`/`model_call_ended`, `trace/catalog.py:460-536`), bornées en mémoire comme `SecurityJournal` (`mcp/security_log.py`, `deque(maxlen=500)`). Un filtre « Sécurité seulement » masque les appels et ne garde que les décisions de sécurité.

## Boundaries & Constraints

**Contrat de l'entrée du Journal (noms figés pour cette story) :**

| Champ | Sens |
|---|---|
| `kind` | `"model_call"` ou `"security"` — distingue les deux familles dans une liste unique. |
| `onglet` | Libellé de l'onglet d'où vient l'appel (voir « Dérivation de l'onglet » ci-dessous). |
| `modele` | `label` et `hosting` de l'`ActiveModel` courant de cet onglet (catalog.py:104-114), jamais le `model_id` brut seul. |
| `tokens_in` / `tokens_out` | `prompt_tokens` / `output_tokens` de `ModelCallEndedPayload`. |
| `cout_usd` | `cost_in_usd + cost_out_usd` si `pricing` déclaré, sinon `None` (affiché « 0 € » + mention offre gratuite, jamais confondu avec un vrai 0 €). |
| `empreinte` | `energy_wh_min/max`, `gco2e_min/max`, `impact_method` (ecologits/codecarbon) de `ModelCallEndedPayload`, si présents. |
| `duree_ms` | `duration_ms` de `ModelCallEndedPayload`. |
| Jamais | `text`, `raw_output`, `reasoning`, `tool_calls` : aucune entrée ne porte le prompt ni la réponse. |

**Dérivation de l'onglet et du modèle (aucun champ dédié dans l'enveloppe) :**
- `model_call_started`/`model_call_ended` (`cloud_base.py:1170` `run_call`, seul émetteur, cloud et local : la distinction se fait sur `isinstance(entry, CloudModel)`, jamais sur un champ séparé) ne portent ni le nom de l'onglet ni le modèle. L'`actor`/`component` de l'enveloppe (`envelope.py:26-30`) donne la piste : `component` commence par `llm` (`_lab_scope("llm")`, `app_session.py:9914`), `rag_lab` (`_rag_lab_scope`, `app_session.py:10962`) ou `mcp_lab`/`mcp.{id}` (`_mcp_lab_scope`, `app_session.py:13674`) ; `None`/`chat` sans préfixe = conversation principale.
- Recommandation : garder la dérivation **côté client**, dans `bar.js`, comme le reste de la barre : chaque page connaît déjà son onglet (elle est chargée une fois par page) et son modèle actif courant (déjà suivi par `app.js`/`llm.js`/`rag.js`/`mcp.js` pour l'indicateur de modèle, AD-12). `bar.js` n'a donc pas besoin de parser `component` : il reçoit l'onglet et le modèle actif en paramètre de la fonction qui l'alimente (appelée par chaque page's propre lecteur `/api/stream`, comme `feedBar` aujourd'hui), pas de l'enveloppe.
- Appels locaux (RAG, LLM lab, chat local) : mêmes enveloppes, `cost_*` absents, `impact_method: "codecarbon"` si le moteur local mesure (LocalMeter, `app_session.py:1234-1243`, `:9359`). Repérer par `git grep '"model_call_ended"' src` (seuls émetteurs : `cloud_base.py:1170`) avant d'implémenter — aucun autre chemin à couvrir.

**Always:**
- Montant toujours affiché (`c.calls > 0` ne doit plus décider de l'affichage, seulement du style « offre gratuite » vs montant réel) ; corriger l'incrément de `calls`/`impact_calls` dans `_accumulate` si besoin pour ne pas fausser le nombre d'« appels tarifés » affiché ailleurs.
- `.bar-flyout-note` : `overflow-wrap: anywhere` (ou `break-word`) ; `.bar-flyout` grid items : `min-width: 0`.
- Journal borné en mémoire, même ordre de grandeur que `SecurityJournal` (500 entrées) ; pas de persistance disque (constraint SPEC.md).
- Entrée du Journal sans prompt ni réponse (constraint SPEC.md).

**Never:**
- Ne pas changer le format de `ModelCallEndedPayload` ni de `ConsumptionUpdatedPayload` : ce sont des contrats déjà utilisés par d'autres écrans (cache, bilan).
- Ne pas faire remonter le Journal au serveur comme une nouvelle enveloppe de catalogue si le dérivation client suffit (voir Questions).
- Ne pas toucher à l'onglet Sécurité (story 7) ni au panneau des briques (story 5).

## Tests et E2E à réaligner

- Nouveaux tests unitaires JS (ou Python si la dérivation migre côté serveur, voir Questions) : montant « 0 € + offre gratuite » après un appel Gemma ; montant réel après un appel tarifé ; entrée de Journal ajoutée après un `model_call_ended` avec les champs du contrat ; filtre « Sécurité seulement » qui masque les appels et garde les décisions de sécurité.
- E2E de la barre à nommer et réaligner (chercher `bar-spend`, `bar-log` dans `tools/e2e/`) :
  - `bar_spend_shows_amount_without_pricing` (nouveau) : appel Gemma, popup Bilan, montant « 0 € » visible, mention offre gratuite.
  - `bar_spend_popup_no_overflow_360px` (nouveau) : fenêtre à 360 px, aucun texte ne dépasse de `.bar-flyout`.
  - `bar_log_lists_model_calls` (nouveau) : une génération RAG puis un appel MCP sans outil ajoutent chacun une ligne (onglet, modèle, tokens, coût/empreinte, durée).
  - `bar_log_security_only_filter` (nouveau) : le filtre ne laisse voir que les décisions de sécurité.
  - Tout scénario E2E existant qui compte les lignes du Journal ou suppose qu'il ne contient que des décisions de sécurité (chercher `bar-log` dans `tools/e2e/`) : à réaligner dans le même commit.

## Questions pour Anaël

1. **Dérivation de l'onglet/modèle côté client vs nouvelle enveloppe serveur.** Recommandation : rester côté client (`bar.js` reçoit onglet + modèle actif en paramètre depuis chaque page), pour ne pas changer le contrat `ModelCallEndedPayload` ni ajouter une enveloppe. Si tu préfères une source unique côté serveur (plus robuste si une page oublie d'alimenter la barre), il faut une nouvelle enveloppe ou un champ `tab`/`model_id` ajouté à l'enveloppe — plus gros changement, à trancher avant le code.
2. **Taille du Journal affiché dans la popup.** Aujourd'hui 5 lignes (preview client). Avec les appels de modèle en plus, 5 lignes se videront vite. Recommandation : garder la popup à 5 lignes les plus récentes (comme aujourd'hui) mais bornées en mémoire à 500 côté serveur pour un futur export/filtre plus large ; pas de pagination dans cette story (non-goal implicite). À confirmer.
3. **Nom de l'onglet pour la conversation principale.** `component` n'a pas de préfixe pour le chat principal. Recommandation : le libellé « Conversation » (ou le nom affiché de l'onglet Accueil). À valider avec le libellé réel de la navigation.
4. **Appels locaux sans empreinte mesurée** (moteur qui ne déclare rien à CodeCarbon, ou appel coupé avant mesure). Recommandation : afficher « — » plutôt que masquer la colonne empreinte, cohérent avec le reste de l'app (`rangeText`/notes d'absence).

</frozen-after-approval>

## Code Map

- `src/wavestack/web/static/bar.js:27-48` (`feedBar`), `:100-170` (`renderSpend`/`detailSentence`), `:419-499` (`renderLog`/`renderLogPanel`/`logRow`) — montant toujours affiché, Journal étendu, filtre.
- `src/wavestack/web/static/pages.css:261-320` (`.bar-flyout`, `.bar-flyout-note`) — `min-width: 0`, `overflow-wrap`.
- `src/wavestack/trace/catalog.py:460-536` (`ModelCallStartedPayload`, `ModelCallEndedPayload`) — lecture seule, pas de changement de schéma a priori (voir Question 1).
- `src/wavestack/mcp/security_log.py:17-49` (`SecurityJournal`, `_KEPT`) — motif de bornage à reproduire si le Journal migre côté serveur.
- Chaque page (`app.js`, `llm.js`, `rag.js`, `mcp.js`) — son lecteur `/api/stream` doit transmettre à `feedBar` le `kind` déjà géré plus `model_call_ended`, avec l'onglet et le modèle actif qu'elle connaît déjà (AD-12).

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_bar.py` (ou le module de test existant de la barre, à vérifier par `git grep -l "bar-log\|bar-spend" tests`)
- `uv run python .claude/cost-kit/controle_rapide.py`
