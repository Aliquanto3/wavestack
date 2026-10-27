---
title: 'Story 17.5 : Sécurité, règle en pastille et filtre vide'
type: 'fix'
created: '2026-10-27'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/src/wavestack/web/static/security.js'
  - '{project-root}/src/wavestack/web/static/security.html'
  - '{project-root}/content/ui.yaml'
---

## Intent

Correctifs de recette v1.7.0 (CT-05) sur l'onglet Sécurité. (a) Dans la matrice des risques,
la colonne Règle affiche « Autoriser », « Demander », « Refuser » en texte simple (18 cellules :
lignes et dépliés), alors que la maquette validée (`spec-wavestack-retours-2026-10-27/
maquette-securite.html:463`, `ux-securite.md:20`) en fait une pastille `status-chip`, comme la
légende sous la matrice qui l'utilise déjà. (b) Un filtre (journal ou matrice) qui ne garde
aucune entrée laisse une zone vide sans message, non accessible.

## Given/When/Then

- **(a)** Given la matrice des risques affichée, When une ligne (dépliée ou non) montre sa
  colonne Règle, Then elle affiche une pastille `status-chip` (verte Autoriser, jaune Demander,
  rouge Refuser, neutre Mixte), non cliquable (pas de curseur main, pas de contour au survol,
  pas de chevron), comme la légende déjà en dessous.
- **(b)** Given le filtre du journal ou de la matrice réglé sur une valeur qui ne garde aucune
  entrée, When la liste ou le tableau se vide, Then un message d'état vide apparaît (annoncé en
  `role="status"`), en fr/en/de.
- **(b)** Given un filtre qui redonne des résultats, When on le sélectionne, Then le message
  d'état vide disparaît.

## Tâches

1. `src/wavestack/web/static/security.js` : `ruleLevel(rule)` (allow→low, ask→mid, deny→high,
   mixed→off, comme la légende) et `ruleChip(rule)` = `chip(ruleText(rule), ruleLevel(rule))` ;
   `matrixRow` utilise `ruleChip` pour la cellule Règle ; une nouvelle `ruleKv` (même forme que
   `kv`, mais `dd` reçoit le chip plutôt qu'un texte) pour la liste des outils du dépli. La
   colonne Risque et la légende, déjà en `status-chip`, ne changent pas ; la section Contrôles
   actifs (hors matrice) n'est pas touchée (hors périmètre).
2. `setMatrixFilter` / `setJournalFilter` : calculent si au moins une ligne/entrée reste visible
   et basculent `hidden` sur un nouvel élément d'état vide (`#sec-matrix-filter-empty`,
   `#sec-journal-filter-empty`, déjà dans `security.html`, classe `sec-empty`, `role="status"`).
   `renderJournal` et `prependJournalRow` réappellent `setJournalFilter(journalFilter)` pour
   garder l'état vide synchronisé après un re-rendu ; le message « Aucun événement pour
   l'instant » du journal réellement vide (sans entrée du tout) reste un cas distinct (aucun
   `li[data-decision]`), non concerné par ce nouveau message.
3. `src/wavestack/web/static/security.html` : ajoute les deux `<p class="sec-empty" role="status"
   hidden data-i18n="...">` (matrice, après `.sec-table-wrap` ; journal, après `#sec-journal`).
4. `content/ui.yaml` (+ `content/i18n/en`, `content/i18n/de`) : `security.matrix.filter_empty`
   et `security.journal.filter_empty`.

## Tests

- `uv run pytest -q --tb=short tests/test_i18n.py tests/test_security_page.py` (textes fr/en/de
  complets ; la logique serveur des règles, inchangée, n'est pas dans le périmètre de cette
  story — aucun test Python ne lit le DOM, l'E2E ci-dessous le fait).

## E2E à rejouer (non lancé par cette story, poste partagé du run)

`uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only security_page`

- `s_security_page` réaligné : la cellule Règle de la première ligne de la matrice (et celle de
  son dépli) est vérifiée comme une pastille `status-chip` de niveau connu, pas un texte ; le
  filtre journal « Autorisés par vous » (`data-f="allow_once"`), qui ne correspond à aucune
  entrée du journal factice de la story 10 (seulement `allow` et `deny`), affiche le message
  d'état vide en `role="status"`, puis le filtre « Tout » le fait disparaître. Aucun scénario
  existant ne lisait le texte littéral de la cellule Règle : rien d'autre à réaligner.

## Choix faits à la place d'Anaël

- Pastille réutilisée via `chip()`/`status-chip`, déjà le composant de la légende et de la
  colonne Risque : aucun nouveau composant CSS, conforme à `ux-securite.md` (« réutilise ce
  composant »).
- Message d'état vide en `<p role="status">` statique dans le HTML (masqué/affiché par JS),
  plutôt qu'un nœud recréé à chaque filtrage : plus simple, et `role="status"` annonce le
  changement sans dépendre de l'ordre d'insertion dans le DOM.
- Les cartes et le chemin d'un message (hors scope, confirmé par l'énoncé) ne sont pas touchés ;
  ni la section Contrôles actifs, qui a sa propre liste `kv` et n'est pas la « matrice ».

## Revue

### Passe 1 (2026-10-27, SHA revu 0cfddc94)

Rebasée sur origin/main (17.1, 17.2) sans conflit. Second avis (Haiku) repris point par point.

- Pre-existing · medium · second avis 1 · reporté : la vue carte sous 560 px (`ux-securite.md:23`) n'existe pas depuis 16.7 (ni media query, ni `data-label`). Demande des libellés de colonne traduits par cellule et une vérification visuelle à 360-560 px : story à part, à vérifier par capture E2E à 375 px.
- Nit · low · second avis 2 · rejeté : la pastille dans les dépliés est voulue (demande explicite d'Anaël, critère (a) « lignes et dépliés »).
- Important · low · second avis 3 · corrigé : `prependJournalRow` rejouait `setJournalFilter` sur les 500 lignes à chaque `security_event`, contre l'invariant O(1) du fichier. Compteur `journalShown` tenu à l'ajout et à l'éviction ; le parcours complet ne reste que sur action utilisateur (filtre) et au rendu initial. Complexité : 1 constat.
- Nit · low · second avis 4 · rejeté : le survol colore les cellules de la ligne (affordance de la ligne, 16.7) ; la pastille garde son propre fond, sans curseur ni contour : aucun signe propre à la pastille.
- Important · low · second avis 5 · corrigé : `role="status"` créé `hidden` puis démasqué n'est pas annoncé de façon fiable. La région reste dans la page, vide, et seul son texte change (`setFilterEmpty`) ; un événement live ne peut que vider le message (non annoncé), sauf éviction de la seule ligne visible.
- Nit · low · second avis 6 · corrigé : l'E2E vérifie aussi le niveau (classe connue) des pastilles du dépli.
- Nit · low · second avis 7 · corrigé : l'E2E teste le message vide de la matrice (lignes marquées sans écriture puis filtre « écriture », la vraie matrice ayant toujours un outil qui écrit) et sa disparition.
- Nit · low · second avis 8 · confirmé : `SECURITY_FAKE_JOURNAL` (`tools/e2e/run_e2e.py`) n'a que `allow` et `deny` ; le scénario ne déclenche aucun appel d'outil, donc aucun `allow_once` live.

E2E non lancé (poste partagé) : `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only security_page`
