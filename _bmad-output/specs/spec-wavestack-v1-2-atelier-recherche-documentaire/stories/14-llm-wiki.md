---
title: 'Story 14 : LLM Wiki'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/architectures.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/litterature.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/vues.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/attaques-et-conformite.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/stories/11-recherche-agentique-et-pageindex.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/stories/18-effacement-et-droits-d-acces.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/stories/19b-fiches-de-composant.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-7 annonce huit architectures ; après la story 11, le LLM Wiki (pattern de Karpathy : le modèle **compile** les sources en un wiki de pages Markdown reliées, le **vérifie** par une passe de lint, et chaque question se résout dans les pages du wiki) n'existe pas. `rag_erasure.yaml` (story 18) déclare l'endroit `wiki_pages` « construit, story 14 », et la fiche d'architecture `llm_wiki` (story 19) porte `story: 14`. H3 (« égale le RAG sur quelques centaines de documents, puis décroche ») et H13 (« coûte plus à l'indexation et à la mise à jour ») ne se lisent nulle part.

**Approach:** Un préréglage `llm_wiki` sur le schéma de la story 11 (PageIndex) : segment de recherche vide, option de Contexte `wiki_pages`, famille « Structure » après PageIndex. Le wiki est **précalculé** (`content/rag_wiki.yaml` ×3), compilé par une **règle déterministe sans modèle** ; le modèle n'intervient qu'à « Reconstruire » (il écrit la synthèse de chaque page) et à la requête (il choisit les pages dans l'index). Mise à jour = **recompilation des pages touchées, puis lint**, chaque partie mesurée. Implémentation maison, aucune dépendance.

## Boundaries & Constraints

**Always:**
- Chiffres de la session (AD-1), `StageCost` / trois temps de la story 3. Préréglages existants inchangés ; `PRESETS`, `PRESET_CONTEXT` et `OPTIONS["context"]` gagnent `llm_wiki` / `wiki_pages` **en fin** ; `PRESET_FAMILIES["structure"] == ("pageindex", "llm_wiki")` ; `SEARCHLESS_OPTIONS` gagne `wiki_pages` (ajout après sa définition : `check_pipeline` refuse toute étape de recherche par `searches_itself`, `embed_query` caché, étages de tête `skipped`, clé `searchless_options` du catalogue) ; `CORPUS_OPTIONS` inchangé.
- **Pages = documents actifs de la chaîne** (copie de travail comprise), jamais le disque ni les documents inactifs (piège, sentinelle). Module pur `rag/wiki.py` : `build_wiki(docs, lang, concepts, audiences, only)`.
- **Règle de compilation.** Mots : `\w+` sans accents, ≥ 5 lettres, sans chiffre, hors mots vides de la langue. **Concept** = un des `TERMS_PER_DOC = 2` meilleurs termes d'un document au score tf × log(N / df) (tf = phrases du document, ≥ 2 ; df de 2 à max(2, N // 3)), départage par terme. **Page de source** `source/<doc_id>` : titre du document, synthèse = deux premières phrases coupées à `SYNTHESIS_MAX_CHARS = 300`, « Points clés » = au plus `FACTS_PER_PAGE = 4` phrases suivantes contenant un chiffre (coupées à 240), « Concepts » = liens `[[concept/<terme>]]`, ligne « Source : corpus/<doc_id>.md ». **Page de concept** `concept/<terme>` : titre = forme la plus fréquente, une citation par document qui le nomme (première phrase, lien `[[source/<doc_id>]]`). **Index** `index` : toutes les pages par type, titre et synthèse coupée à 120. Chaque page garde ses `sources`, son `audience` (`hr` si une de ses sources l'est) et l'empreinte sha256 de ce dont elle est compilée.
- **Vocabulaire gelé.** Les concepts qui ont une page sont ceux du fichier lu (reconstruit, sinon livré) ; ils ne changent qu'à une compilation complète (« Reconstruire », `tools/build_wiki.py`). C'est ce qui rend une mise à jour locale et donne du sens au lint.
- **Lint** (règle, 0 token, mesuré) : `broken_link` (lien vers une page absente, y compris dans une synthèse écrite par le modèle), `orphan_page` (aucune autre page n'y renvoie, l'index à part), `thin_concept` (< 2 sources), `empty_concept` (concept du vocabulaire qu'aucun document ne cite plus), `missing_concept` (concept qu'une compilation complète donnerait, sans page), `stale_synthesis` (synthèse reconstruite pour un autre texte). Il dit, il ne corrige pas.
- **Fichier livré** sans durée, reproductible octet par octet (`tools/build_wiki.py`, test de non-péremption ×3) ; en-tête `author: shipped`, `method: heuristic`, `concepts`, puis les pages (texte Markdown complet). Aucun wiki écrit par un vrai modèle dans le dépôt ni par la CI.
- **Requête** : un appel ; le modèle voit la liste numérotée des pages (sources : titre et synthèse coupée ; concepts : titre seul) et répond `PAGES: 2, 5` (au plus `WIKI_BREADTH = 3`) ou `PAGES: NONE` ; chaque page choisie est un élément du contexte (texte entier, source = id de la page). Liste tenue dans `fenêtre − réserve` (dernières pages retirées, `wiki_index_trimmed`) ; `NONE` ou numéros hors plage : `no_page_chosen` ; sans ligne `PAGES:` : `wiki_unreadable` (format rappelé). Le texte des documents et des pages est une donnée : seule la réponse du modèle est analysée.
- **Reconstruire / Rétablir** : `rag_lab_rebuild` gagne `target: wiki` ; compilation complète (vocabulaire recalculé) puis un appel par page (hors index) pour sa synthèse, écriture atomique en fin dans `rag_lab_dir()/wiki/{lang}.yaml` (`author: rebuilt`, `method: llm`, modèle, tokens, durée) ; « Arrêter » n'écrit rien ; refus sans modèle (`rebuild_no_model`) ; « Rétablir » = `POST /api/rag_lab/wiki/reset`. Lecture par (id, sha256) : reconstruit, sinon livré, sinon règle ; une page dont la synthèse reconstruite visait un autre texte est « périmée ».
- **Mise à jour (U)**, deux parties : « Wiki compilation » (pages touchées = page du document ajouté, modifié ou supprimé et pages des concepts que son texte, avant ou après, nomme ; pages retirées comptées ; index recalculé ; par la règle : ms, 0 token ; wiki reconstruit et modèle chargé : un appel par page touchée, écrit en fusion dans le fichier reconstruit) puis « Wiki lint ». Un document supprimé retire du fichier reconstruit toutes les pages qui le citent (`wiki.forget`).
- **Coûts** : `build` = compilation mesurée à l'exécution (règle, 0 token) ou en-tête du fichier reconstruit ; avec le wiki livré, une **estimation étiquetée, hors des sommes** (« compiler par un modèle demanderait N appels et ≈ T tokens lus ») dans les chiffres du Contexte et la carte Wiki ; `query` = 1 appel + génération.
- **Audience sans filtre** (règle de l'atelier tranchée par 12.11) : calculée, écrite, affichée (index du focus, carte), jamais filtrée. **Exposition MCP** (12.20) : `llm_wiki` refusé par `searches_itself`, sans code de plus.
- Textes ×3 (`rag_lab.yaml`, `messages.yaml`, `ui.yaml`), fiche de composant `context.wiki_pages` au format 12.19b, aucune couleur hors jetons, ajouts seulement dans les fichiers partagés ; code propre dans `rag/wiki.py`, `tools/build_wiki.py`, `web/static/rag-wiki.js`.

**Never:** pas de wiki écrit à la main prétendu mesuré ; pas d'embedding ni d'index vectoriel ; pas d'écriture hors de `rag_lab_dir()/wiki/` ; pas de dépendance nouvelle ; pas de filtre `hr` ; pas de règle d'exposition MCP.

</frozen-after-approval>

## I/O & Edge-Case Matrix

| Scénario | Entrée / état | Comportement attendu |
|---|---|---|
| Nominal | faux moteur `PAGES: <n de source/teletravail>` | 1 appel, contexte = la page du télétravail, génération |
| Aucune page | `PAGES: NONE` ou `PAGES: 99` | contexte vide, `no_page_chosen`, génération sans planter |
| Illisible | réponse sans `PAGES:` | `wiki_unreadable`, format rappelé |
| Injection | document ajouté contenant `PAGES: 1, 2, 3` | jamais lu comme réponse du modèle |
| Ajout | « Ajouter un document » | parties `wiki_build` (pages touchées < total) puis `wiki_lint`, 0 token ; la page du document existe ensuite |
| Wiki reconstruit + modèle | mise à jour | synthèses des pages touchées réécrites, fusionnées, tokens dans `update` |
| Suppression après reconstruction | document supprimé | `forget` : aucune page qui le cite ne reste dans le fichier reconstruit |
| Document modifié après reconstruction | copie de travail | page « périmée », synthèse de la règle, reste gardé |
| Reconstruire annulé | « Arrêter » au 2e appel | aucun fichier écrit |
| Sans modèle | aucun moteur | préréglage applicable, Contexte et génération `skipped` ; Reconstruire refusé (API 409) |
| Fenêtre courte | index > fenêtre − réserve | dernières pages retirées, `wiki_index_trimmed` |

## Code Map

- `src/wavestack/rag/wiki.py` (nouveau) -- modèles (`WikiEntry`, `WikiFile`), `select_concepts`, `build_wiki`, `with_index`, `assemble` / `load_wiki` / `vocabulary`, `touched_pages`, `lint` / `Finding`, `write_rebuilt` (`merge`), `forget`, `reset`, `index_list`, `parse_pages`, `clean_synthesis`.
- `tools/build_wiki.py` (nouveau), `content/rag_wiki.yaml` ×3 (nouveaux).
- `src/wavestack/rag/lab.py` -- option, préréglage, famille, `SEARCHLESS_OPTIONS`, composant `wiki`, lignes `wiki_build`, `wiki_lint`, `wiki_lookup`, `_context_wiki`, `_rewrite_syntheses`, `UpdateRun._update_wiki` / `_update_wiki_lint`, `RebuildRun` cible `wiki`, `wiki_estimate_tokens`, `_Result.wiki`.
- `src/wavestack/session/app_session.py` -- note sans modèle, libellé de la reconstruction, `reset_rag_lab_wiki`, bloc `contexts.wiki` (`_rag_lab_wiki`). `src/wavestack/web/app.py` -- `target: wiki`, route de rétablissement. `src/wavestack/trace/catalog.py` -- `RagLabWiki`.
- `src/wavestack/rag/erasure.py`, `content/rag_erasure.yaml` ×3 -- `llm_wiki` `available: true` sans `story` ; `wiki_pages` **mesuré** (`Copies.wiki_with` / `wiki_without` = `build_wiki` de la règle, carte pure). `content/rag_sheets.yaml` ×3 -- `story: 14` retiré.
- `content/rag_lab.yaml`, `messages.yaml`, `ui.yaml` ×3 ; `web/static/rag-wiki.js` (nouveau), `rag.html`, `rag.css`.
- Tests : `tests/test_rag_wiki.py`, `tests/test_rag_lab_wiki.py` (nouveaux) ; réalignés : `test_rag_lab.py`, `test_rag_lab_no_index.py`, `test_rag_lab_agentic.py`, `test_rag_erasure.py`, `test_i18n.py`. E2E : `rag_lab_wiki` (nouveau, capture 88), `rag_lab_agentic` réaligné, `fake_local_server.py` (`PAGES:`, synthèse), README.

## Tasks & Acceptance

- [x] Module `wiki.py`, constructeur, fichiers livrés ×3, test de non-péremption.
- [x] Préréglage, famille, option, séquence, focus, carte Wiki.
- [x] Requête, Reconstruire / Rétablir, mise à jour en deux parties, lint.
- [x] Coûts (mesure et estimation étiquetée), effacement mesuré, fiches.
- [x] Textes fr, en, de ; tests ; E2E.

**Acceptance Criteria:**
1. `PRESET_FAMILIES["structure"] == ("pageindex", "llm_wiki")`, chaîne de `llm_wiki` valide à segment vide et Contexte `wiki_pages` ; avec une recherche, refus `searches_itself` ; préréglages existants inchangés ; `searchless_options` contient `wiki_pages`.
2. Le fichier livré ×3 est égal à la règle (deux appels, mêmes octets), en-tête `shipped` / `heuristic` sans mesure ; mesures bornées par le test (25 pages de sources, 30 à 60 concepts, ≥ 250 liens, < 150 Ko par fichier, lint ≤ 2 `orphan_page`), aucune page du piège ni de la sentinelle inactifs ; en fr, `astreinte` et `crise` sont des concepts.
3. Règle sur petit corpus : pages de sources, de concepts, index, points clés chiffrés, liens réciproques ; lint : `orphan_page`, `empty_concept`, `missing_concept`, `thin_concept`, `broken_link` provoqués un à un.
4. Requête : 1 appel, l'index seul est montré (pas le texte des pages), la page choisie est l'élément du contexte avec sa source, étages de tête `skipped`, `build` 0 token et durée > 0, carte « compilé par une règle, sans modèle » et estimation ; `NONE` / hors plage / illisible gérés ; une injection n'est pas lue.
5. Mise à jour : deux parties, pages recompilées « n sur total » avec 1 ≤ n < total, lint ensuite, 0 token ; la page ajoutée existe.
6. Reconstruire : un appel par page, fichier `rebuilt` / `llm` mesuré, vocabulaire recalculé, wiki lu ensuite reconstruit et `build` `measured_at_build` ; mise à jour avec modèle : synthèse réécrite ; suppression : `forget` ; modification : page périmée ; Rétablir ; annulation sans écriture ; refus sans modèle (API comprise).
7. Effacement : `wiki_pages` mesuré ×3 (≥ 1 page avec le code, « à reconstruire » après suppression, « effacé » et 0 après « Reconstruire : LLM Wiki ») ; carte pure.
8. Fiche `context.wiki_pages` ×3 (source arXiv 2605.18490), fiche d'architecture sans `story`, tests 12.19b et i18n verts ; MCP : refus `searches_itself` (test de 12.20 vert).

## Verification

- `uv run pytest -q --tb=short tests/test_rag_wiki.py tests/test_rag_lab_wiki.py tests/test_rag_lab_agentic.py tests/test_rag_sheets.py tests/test_rag_erasure.py tests/test_rag_mcp.py tests/test_rag_pageindex.py tests/test_rag_lab_no_index.py` puis `tests/test_rag_lab.py tests/test_i18n.py tests/test_rag_lab_views.py tests/test_rag_lab_costs.py tests/test_rag_lab_context.py tests/test_rag_access.py`.
- `uv run python .claude/cost-kit/controle_rapide.py`.
- E2E : `--only rag rag_rerank rag_lab_wiki`, puis `--only rag rag_rerank rag_lab rag_lab_agentic rag_lab_mcp`.

## Ce que doit vérifier Anaël à la main (done_checkpoint)

Avec un vrai modèle local (4 096 tokens) : (1) « LLM Wiki » sur 3 questions d'Exemplia (dont `q_multi_crise`, `q_global_securite`) : le modèle suit-il `PAGES:`, choisit-il la bonne page, une page de concept aide-t-elle en multi-sauts ? (2) « Recompiler le wiki » : durée, tokens, qualité des synthèses, comparées à l'estimation affichée ; (3) Ajouter / Modifier / Supprimer un document : pages recompilées, constats du lint (concepts manquants, minces) ; (4) Comparer avec dense et PageIndex : construction et mise à jour plus chères une fois recompilé par le modèle ; (5) Effacement ; (6) lecture critique de la fiche ; (7) fr, en, de, clair et sombre.

## Décisions du point de contrôle

Pas de spec_checkpoint pour cette story : points tranchés par le développeur, chacun **à revoir par Anaël**.

1. **Wiki livré compilé par une règle, modèle à « Reconstruire » seulement** (schéma de 12.11 et 12.13) : un wiki écrit par un vrai modèle ne sort ni de la CI ni d'un run de nuit. Conséquence honnête : avec le wiki livré, construction et mise à jour coûtent moins qu'un RAG dense (ms, 0 token) ; l'estimation étiquetée, hors somme, dit ce qu'un vrai LLM Wiki coûterait. À revoir par Anaël.
2. **Le modèle n'écrit que la synthèse** de chaque page ; la structure (pages, liens, citations, points clés) reste celle de la règle, ce qui garde le lint et l'effacement mesurables. Karpathy fait écrire la page entière. À revoir par Anaël.
3. **Concepts par tf-idf, deux par document** : mesuré sur le corpus livré, 41 concepts (fr), 40 (en), 41 (de), dont du bruit (« pendant », « admise ») ; pas de concepts à plusieurs mots. À revoir par Anaël.
4. **Vocabulaire gelé entre deux compilations complètes** : une mise à jour ne crée ni ne supprime de concept ; le lint le dit (`missing_concept`, `thin_concept`, `empty_concept`). À revoir par Anaël.
5. **Requête = un appel sur l'index** (le modèle choisit au plus 3 pages), pas de recherche lexicale ni de suivi des liens. **L'index montré au modèle donne le titre seul des pages de concepts** : avec leurs synthèses, il pesait 9,3 Ko (fr) et dépassait la fenêtre de 8 192 du faux llama-server (un token par octet) ; sans elles, 4,7 Ko. À revoir par Anaël (mesure réelle au done_checkpoint).
6. **Lint par règle, sans détection de contradictions** (qui demanderait un modèle) : Reports. À revoir par Anaël.
7. **Mise à jour en deux parties** (« Wiki compilation », « Wiki lint ») mesurées à part ; libellés de séquence en anglais (« Wiki compilation », « Wiki lint », « Wiki lookup »), convention de 12.11. À revoir par Anaël.
8. **Aucun filtre `hr`** : 15 pages (fr) ont l'audience RH (pages de concepts mêlant des sources RH), affichées, non filtrées, règle de l'atelier tranchée par 12.11. À revoir par Anaël avec la décision transverse.
9. **Effacement** : `wiki_pages` mesuré sur le wiki de la règle recompilé en mémoire (vocabulaire frais, sentinelle comprise), carte pure. `forget` retire du fichier reconstruit la page du document et toutes les pages de concepts qui le citent.
10. **Source de la fiche** : arXiv 2605.18490 seulement (lien de `litterature.md`) ; Karpathy nommé sans lien, faute d'une URL vérifiée dans le dépôt. À revoir par Anaël.

## Spec Change Log

- 2026-10-25 : rédaction et développement (statut `review`), sur `integration/v1-2-atelier` refusionnée (12.19b, puis 12.20). Mesures du wiki livré : fr 67 pages (25 sources, 41 concepts, index), 368 liens, 108 Ko ; en 66 pages, 323 liens, 93 Ko ; de 67 pages, 320 liens, 101 Ko ; lint du livré : 1 `orphan_page` par langue ; 15 (fr), 14 (en, de) pages d'audience RH ; sentinelle active : 1 page avec le code (fr, en), 2 (de).

## Reports

- Mesure réelle d'une recompilation par un vrai modèle (tokens, durée, qualité) et de la requête (choix des pages) : done_checkpoint d'Anaël.
- Détection de contradictions et d'affirmations périmées par un modèle dans le lint (pattern de Karpathy) ; corrections proposées par le lint.
- Suivi des liens à la requête, recherche lexicale sur les pages, réponses rangées dans le wiki (« file back » de Karpathy).
- Concepts à plusieurs mots, filtrage du bruit du tf-idf.
- Lien vérifié vers la description du pattern par Karpathy dans la fiche.
- Filtre `hr` de l'atelier (décision transverse, 12.11) ; exposition MCP du wiki (règle D12 de 12.20).
- Sans modèle, l'étape Contexte des préréglages sans recherche (PageIndex comme le wiki) est sautée avant de lire la structure : la charge utile `wiki` / `tree` n'est pas émise dans ce cas (constaté, comportement existant de 12.11).
