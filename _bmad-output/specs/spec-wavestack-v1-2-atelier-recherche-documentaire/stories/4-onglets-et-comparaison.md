---
title: 'Story 4 : onglets de vue, question préparée et comparaison de deux exécutions'
type: 'feature'
created: '2026-10-25'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/vues.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/brownfield.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La page `/rag` n'a qu'une vue, nomme encore l'atelier « RAG », ne propose pas les questions préparées de la story 1 et ne permet pas de mettre deux exécutions côte à côte. Les stories d'architecture suivantes n'ont pas de coquille où poser leurs vues ni de moyen de lire l'effet d'un réglage.

**Approach:** Renommer la page « Atelier recherche documentaire » et la découper en cinq onglets (Construire, Comparer, Évaluer, Attaquer, Fiches). Construire est la page du lot 5, inchangée. Un sélecteur de question préparée remplit la question. Un bouton épingle l'exécution terminée ; l'onglet Comparer la montre à côté de l'exécution courante, par rôle (recherche, contexte, réponse, coûts), avec les écarts marqués.

## Boundaries & Constraints

**Always:**
- Évaluer, Attaquer et Fiches restent vides, avec « à venir », jusqu'à leurs stories.
- Les sélecteurs E2E du lot 5 sont conservés ; la barre commune ne gagne pas d'onglet.
- L'épingle est un instantané (question, noms des étapes, passages sans texte, prompt, réponse, coûts par temps) gardé dans le navigateur ; il survit au rechargement.
- Les chiffres viennent des événements de la session (AD-1) : la page range et marque, ne calcule rien.
- Textes en fr, en et de ; aucune couleur hors des jetons.

**Never:**
- Pas de retour de `LANES_MAX`, de `compare()` ni de la voie B : deux exécutions successives.
- Pas de synthèse rédigée des écarts.
- Pas de rang du passage attendu (CAP-10), pas d'arbre des étapes ni d'export OTLP (autres stories).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Pas d'épingle | Comparer ouvert | Colonne Épinglée vide, invite à épingler | N/A |
| Pas d'exécution terminée | Aucune, ou en erreur | Bouton « Épingler » grisé, Courante vide | N/A |
| Même question, même chaîne | Épinglée et courante | « Mêmes passages », aucune marque | N/A |
| Autre question | Questions différentes | Avertissement, passages perdus/ajoutés marqués | N/A |
| Rechargement | Épingle posée | Épingle relue ; `/rag#compare` ouvre l'onglet | Stockage refusé : l'épingle vit avec la page |
| Question de suivi | `history` non vide | Absente du sélecteur (l'atelier n'a pas d'historique) | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/web/static/rag.{html,js,css}` -- onglets, sélecteur, épingle, vue Comparer.
- `src/wavestack/session/app_session.py` -- `rag_lab_state` porte `questions` (`load_rag_questions`).
- `src/wavestack/rag/lab.py` -- `TabTexts`, `PreparedTexts`, `CompareTexts`.
- `content/rag_lab.yaml`, `content/ui.yaml` et surcouches en, de -- titre et textes.
- `tests/test_rag_lab_views.py`, scénario E2E `rag_lab_views`, `docs/guide.md`.

## Tasks & Acceptance

- [x] Titre « Atelier recherche documentaire » (page, h1, `<title>`, E2E, README).
- [x] Onglets, panneaux « à venir », `#compare`.
- [x] Sélecteur de question préparée et badge de type.
- [x] Épingle, vue Comparer (recherche, contexte, réponse, coûts), écarts marqués.
- [x] Tests ciblés et E2E `rag_lab_views`.

**Acceptance Criteria:**
- Given `/rag`, then cinq onglets, Construire par défaut, les trois autres « à venir ».
- Given une exécution épinglée puis relancée, then Comparer montre deux colonnes et les écarts ; l'épingle survit à un rechargement.

## Verification

- `uv run pytest -q --tb=short tests/test_rag_lab_views.py tests/test_rag_lab.py tests/test_rag_lab_costs.py tests/test_i18n.py tests/test_web_tokens.py` -- vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- vert.
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag rag_rerank rag_lab rag_lab_views` -- vert.

## Spec Change Log

- 2026-10-25 : décisions prises à la place d'Anaël, à revoir (voir Reports).

## Reports

- Décisions à revoir : épingle gardée dans le navigateur (`localStorage`), pas côté session, et liée ni à la langue ni au corpus ; titre renommé mais lien de la barre « RAG » et infobulles inchangés ; les préréglages en 11 boutons groupés, le rang du passage attendu et l'arbre des étapes ne sont pas faits ; questions de suivi (avec historique) exclues du sélecteur ; la ligne « contexte » compare les passages de l'étape Contexte.
- Les noms de l'atelier dans les messages et libellés du journal (« Atelier RAG : exécution en cours ») gardent l'ancien nom.

## Revue

### Passe 1 (2026-10-25, SHA revu a1b5265)

Base : `origin/main` fusionnée (a1b5265, sans rebase) ; conflits de la 12.3 squashée résolus en gardant les ajouts de la story. Contrat d'onglets (`rag-<onglet>.js` enregistrés par `registerTab` auprès de `rag.js`) conservé.

- Important · medium · second avis · corrigé : `_rag_lab_questions` n'attrapait pas `yaml.YAMLError` ; un `rag_questions.yaml` mal formé faisait échouer `GET /api/rag_lab` et `main()` de `rag.js` attendait sans fin. Test `test_a_broken_questions_file_leaves_the_page_without_questions` (rouge sans le correctif).
- Important · medium · second avis · corrigé : rien ne vérifiait que `rag.html` charge chaque `rag-<onglet>.js` (la CI ne lance pas l'E2E). Test `test_the_page_loads_each_tab_file_after_the_shell`.
- Nit · low · second avis · corrigé : `loadPin` acceptait une étape sans `items` (TypeError dans `roleOf`, onglets suivants cassés dans `everyTab`).
- Nit · low · second avis · corrigé : le sélecteur de question préparée était reconstruit à chaque événement du journal et fermait un menu ouvert pendant un run ; reconstruit seulement quand la liste change.
- Nit · low · second avis · corrigé : capture d'échec `echec-rag_lab_views.jpg` retirée, `tools/e2e/screenshots/echec-*.jpg` ignoré.
- Nit · low · second avis · corrigé en partie : Début et Fin au clavier sur les onglets ; pas de `tabindex` sur les panneaux, rejeté : Construire et Comparer ont des contrôles focalisables, les trois « à venir » n'ont qu'une phrase.
- Nit · low · second avis · rejeté : épingle non liée à la langue ni au corpus. Une autre question déclenche déjà l'avertissement, et un autre corpus se lit dans les passages ; lier l'épingle relève d'une décision d'Anaël (ajoutée aux décisions à revoir).
- Complexité : 0 constat. À chaque événement, `render` des onglets : Construire ne fait plus qu'une recherche dans la liste des questions ; Comparer ne se redessine que s'il est affiché, en O(étapes × passages) d'une exécution bornée.
- Note E2E : `rag_lab_views` et `rag_lab` supposent `rag` lancé avant (index construit, catalogue de téléchargements) ; seuls, ils échouent. Vert avec `--only rag rag_rerank rag_lab rag_lab_views` (163/163), sur un arbre propre : la vérification « dépôt intact » de `rag_lab` compare `git status` et échoue sur un arbre modifié pendant le run.
