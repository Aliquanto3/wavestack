# UX — onglet Sécurité refondu (story 16.4, CAP-10)

Maquette : [maquette-securite.html](maquette-securite.html), avec deux bascules : 360 px et thème sombre. Charte : [DESIGN.md vague 2](../spec-wavestack-v1-1-vague-2/ux/DESIGN.md), aucun nouveau jeton. Si ce fichier ou DESIGN.md contredit la maquette, ce sont eux qui font foi.
Le skill bmad-ux a tourné en mode non interactif : DESIGN.md n'a pas été réécrit, les choix ci-dessous sont à valider par Anaël.

## Intentions
- Lire la page sans Anaël. Chaque section commence par la phrase « Pourquoi c'est là ».
- Partir de la question pour aller à la preuve : une carte-question mène à la section qui y répond, déjà filtrée.
- Montrer l'ordre des contrôles avec le schéma « Le chemin d'un message » (message → garde-fous → modèle → règle de l'outil → journal).
- Une seule affordance pour tout ce qui se clique : curseur main, contour `{colors.primary}` au survol, anneau `{colors.primary}` de 2 px au focus clavier. Un indice reste visible au repos : chevron ▸, flèche → ou ↓, relief. Ce qui ne se clique pas (pastilles, chiffres, étapes 1 et 3) n'a aucun de ces signes.
- Ordre des sections : cartes, chemin, matrice et contrôles, journal, limites, légende « Ce qui se clique » (repliée).

## Composants réutilisés
- `.sec-question-card` (devient un `<button>`), `.sec-matrix`, `status-chip` (low, mid, high, off), `disclosure-row` (pages.css:387-434), `button-primary` et `button-secondary` (pages.css:535).

## Nouveaux composants
- **question-card-button** : la carte avec le relief `{colors.relief}`, un lien « Voir … → » en bas à droite, et au survol un contour primary avec la flèche qui glisse de 3 px.
- **call-path** : 5 étapes numérotées. Les étapes 2, 4 et 5 sont des boutons qui montrent leur état réel et mènent à leur section.
- **filter-chip** : pastille à bascule (`aria-pressed`). Cochée, elle passe sur fond primary avec un ✓. Elle sert pour le journal (Tout, Refusés et bloqués, Autorisés par vous) et la matrice (Tous, Seulement ceux qui écrivent).
- **rule-chip** : la règle en `status-chip` (Autoriser en low, Demander en mid, Refuser en high, Mixte en off), avec une légende des trois règles sous la matrice.
- **sec-why** : encadré « Pourquoi c'est là », filet gauche primary.
- **disclosure-row** : contour primary et chevron primary au survol, anneau au focus. Le badge passe à la ligne quand la place manque.
- Ligne de matrice dépliable : outils et règles, plus « Pourquoi ce risque ». Sous 560 px, chaque ligne devient une carte.

## Ce que la story 16.7 devra implémenter
1. Dans `security.html` et `security.js` : les cartes-boutons (défilement, focus sur la section, filtre appliqué), le schéma call-path, les filtres du journal et de la matrice, les lignes de matrice dépliables, la légende.
2. Dans `pages.css` : les états `:hover` et `:focus-visible` de `disclosure-row` (ils valent aussi pour le Journal de la barre, à vérifier avec la story 16.1), filter-chip, question-card-button, call-path et sec-why. Les jetons sont les seuls autorisés.
3. Dans `security_state()` : ajouter `tools` (id, label_text, rule) à chaque ligne de `risk_matrix`, tiré de `row["rules"]`. Le reste existe déjà (voir la correspondance dans la maquette).
4. Textes nouveaux en fr, en et de, dans la même story : `security.path.*`, `security.{matrix,controls,journal}.why`, `security.matrix.{id}.why` (7), `security.controls.*.what`, `security.journal.filters.*`, `security.matrix.filter_*`, `security.legend.*` ; et `security.questions.not_covered` qui devient « à dire au client ».
5. Les textes `reason_text` du journal ne sont pas inventés : la maquette en montre des exemples marqués « [texte d'exemple] ».
6. Accessibilité : `aria-expanded` et `aria-controls` sur chaque ligne dépliable, `aria-pressed` sur les filtres. Le focus suit le défilement déclenché par une carte. Pas de survol sans équivalent au focus.
7. Réaligner les E2E de la page Sécurité (sélecteurs `#sec-questions`, `#sec-matrix-body`, `#sec-controls`, `#sec-journal`, `#sec-limits`), ou garder ces id.
