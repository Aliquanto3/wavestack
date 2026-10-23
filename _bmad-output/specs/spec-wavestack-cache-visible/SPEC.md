---
id: SPEC-wavestack-cache-visible
companions:
  - brownfield.md
sources: []
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# WaveStack : cache visible

## Why

Le cache de prompt est le premier poste de dépense d'un agent IA. Dans le bilan tokens d'agent-cost-kit, la relecture du cache dépasse souvent toutes les autres lignes, et beaucoup d'écriture au regard de la lecture signale un cache perdu. Anaël veut expliquer ce bilan en formation avec WaveStack. Aujourd'hui, WaveStack ne montre le cache que par des lignes de texte dans le compteur d'un appel. Aucun scénario ne le fait vivre, et le cache Claude n'y est jamais activé.

## Capabilities

- **CAP-1** Données de cache par appel
  - **intent:** Chaque appel au modèle, local ou cloud, porte ses tokens lus du cache, écrits dans le cache et non cachés.
  - **success:** Un test couvre un faux moteur local, une fausse réponse Anthropic (lecture et écriture) et une fausse réponse compatible OpenAI (lecture seule). Dans chaque cas, l'appel porte les trois cases, ou « non déclaré » pour une case que le fournisseur ne remonte pas, même sans prix déclaré.
- **CAP-2** Jauge du cache
  - **intent:** À côté de la barre de contexte, le participant voit pour le dernier appel la part lue du cache, écrite et non cachée, et la cause quand le cache n'a pas servi.
  - **success:**
    - Sur deux questions d'affilée avec le modèle local, la jauge du second appel montre une part lue non nulle.
    - Après un changement du prompt système, elle montre tout en écriture et cite la cause.
    - Un E2E le vérifie.
- **CAP-3** Bilan consolidé
  - **intent:** En fin de conversation ou de séance, le participant lit sa consommation totale. Le bilan donne :
    - les tokens par case ;
    - le coût par poste, dans un anneau « où part l'argent » ;
    - le coût qu'aurait eu la séance sans cache ;
    - le temps évité en local ;
    - le signal « beaucoup d'écriture : le cache se perd ».
  - **success:**
    - Le Bilan de la séance existant affiche deux colonnes, « Cette conversation » et « Depuis le lancement ». « Vider la conversation » remet la première à zéro, pas la seconde.
    - Les totaux égalent la somme des appels, ce qu'un test vérifie.
    - Le signal apparaît quand l'écriture dépasse la lecture sur la conversation.
- **CAP-4** Vider le cache
  - **intent:** Le formateur vide la mémoire de contexte du modèle local, pour montrer ce que fait une expiration sans attendre.
  - **success:** Après un clic sur le bouton, l'appel suivant passe tout en écriture, avec la cause « cache vidé ». Un E2E le vérifie. En cloud, le bouton est grisé et dit pourquoi.
- **CAP-5** Cache de prompt Claude
  - **intent:** Le formateur active le cache Claude, pour 5 min ou 1 h, et voit l'écriture au premier appel puis la lecture aux suivants.
  - **success:**
    - Le réglage vaut off par défaut.
    - Avec 5 min ou 1 h, la requête envoyée porte des points de cache sur le préfixe stable (vérifié sur une fausse API).
    - Le coût compte l'écriture au bon multiplicateur, ×1,25 ou ×2.
    - Sans clé Claude, le réglage est grisé avec sa raison.
- **CAP-6** Scénarios du cache
  - **intent:** Un module du programme guidé fait vivre le cache, du modèle local au bilan d'agent-cost-kit.
  - **success:**
    - Le module compte au moins quatre scénarios, en fr, en et de, chacun avec sa consigne et ses prompts :
      - lecture du cache ;
      - préfixe cassé ;
      - expiration par « Vider le cache » ;
      - cache Claude 5 min et 1 h, facultatif, avec une clé ;
      - lecture d'un bilan d'agent-cost-kit, case par case.
    - Le guide et une fiche expliquent les trois cases et la durée de vie.
    - Les tests de contenu sont verts.

## Constraints

- Le vocabulaire est celui du bilan d'agent-cost-kit : « Lecture cache », « Écriture cache 5 min » ou « 1 h », « Non caché ». Chaque colonne du bilan correspond ainsi à un segment de WaveStack.
- **Modèle local.**
  - Lu = tokens repris de la mémoire de contexte (`kv_cache_tokens`). Écrit = tokens évalués, qui y sont conservés.
  - Il n'y a ni « non caché » ni durée de vie en local, et la jauge le dit.
- **Cloud.**
  - Un fournisseur qui ne déclare pas l'écriture (Groq, Mistral, Gemini, OpenAI) voit sa case écriture marquée « non déclarée par le fournisseur », jamais 0.
  - Le cache d'un fournisseur ne se purge pas. « Vider le cache » n'agit qu'en local. En cloud, on montre l'expiration par l'attente réelle ou en changeant le préfixe.
  - Le cache Claude est off par défaut : la facturation ne change pas sans action du formateur. La dépense reste plafonnée par `[finops] max_session_usd`.
- **Développement.**
  - Pas de nouvelle dépendance.
  - Les fichiers carrefour (`ui.yaml`, `messages.yaml`, `app.py`, `app.js`, `run_e2e.py`) ne reçoivent que des ajouts.
  - Textes en fr, en et de.
  - Faux moteurs en test, aucun modèle réel dans la suite par défaut, et un E2E par nouvel élément visuel.
  - L'interdiction des métriques agrégées ne s'applique pas : le bilan est déjà un agrégat, accepté depuis la V1.1.

## Non-goals

- Lire les transcriptions de Claude Code dans WaveStack. Le bilan mensuel reste dans agent-cost-kit.
- Une nouvelle mesure d'impact environnemental. GreenOps reste tel quel.
- Le cache sémantique ou le cache de réponses. Seul le cache de préfixe est traité.
- `cache_control` pour d'autres fournisseurs que Claude.

## Success signal

En formation, avec le modèle local et sans réseau, un participant :
1. pose deux fois une question et voit la jauge passer en lecture ;
2. change le prompt système et voit tout repartir en écriture, avec la cause ;
3. vide le cache, et l'appel suivant passe tout en écriture ;
4. lit en fin de conversation le bilan par case et le temps évité.

Le formateur ouvre ensuite le bilan d'agent-cost-kit et en explique chaque colonne d'après ce que la salle vient de voir.

## Assumptions

- Le lot est la V1.3, exécutée avant la story 2 de la V1.2 (décision d'Anaël du 2026-10-23).
- Le cache KV local se vide sans recharger le modèle : `llama_kv_cache_clear` pour le moteur intégré, effacement du slot pour llama-server.
