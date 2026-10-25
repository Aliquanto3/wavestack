# Mesure des cas d'évaluation fournis (V1.5, story 2)

`measure_cases.py` joue chaque cas de `content/agent_cases.yaml` plusieurs fois de suite sur le
modèle local et propose, par cas, un plafond d'appels au modèle : le plus grand nombre observé,
plus un (`max_model_calls`).

```
uv run python tools/eval/measure_cases.py --runs 3
uv run python tools/eval/measure_cases.py --runs 3 --cases chemin_invente --json mesures.json
uv run python tools/eval/measure_cases.py --model C:\chemin\modele.gguf
```

- Le modèle est celui du dossier des modèles réel (ou `--model`). L'outil fixe ensuite
  `WAVESTACK_DATA_DIR` sur un dossier temporaire : la mémoire globale est celle de
  démonstration, les réglages et les données du formateur ne sont pas touchés.
- Sortie : un tableau (appels par essai, max, plafond proposé, plafond du fichier, réussites)
  et les lignes `max_model_calls: N` à recopier **à la main** dans `content/agent_cases.yaml` et
  ses deux traductions (`content/i18n/{en,de}/agent_cases.yaml`). L'outil n'écrit aucun fichier
  de cas : le choix du plafond est humain.
- Le plafond proposé est le max des essais **réussis** + 1 : un essai qui boucle jusqu'à la
  limite d'étapes ne devient pas le plafond. Sans essai réussi, rien n'est proposé. Une erreur
  sur un essai (délai dépassé, refus) est notée et la mesure continue.
- `h5_refuse_sans_rappel` garde son plafond de contrat (2, sans marge) : l'outil le dit, ne le
  propose pas. Si le modèle rappelle l'outil après le refus, le cas échoue, c'est ce qu'il montre.
- Un cas dont `window` diffère de la fenêtre courante est signalé « non mesurable ici ».
- Jamais lancé en CI, jamais par un test sur un vrai modèle (les tests utilisent un faux moteur).
  Les plafonds du fichier sont **provisoires** tant que cette mesure n'a pas été faite sur le PC
  cible.
- Chaque cas est joué par l'exécuteur de la session (`session.agent_eval`, story 4 du lot V1.5),
  comme dans la vue « Évaluer l'agent » : une exécution d'un cas, `--runs` essais (1 ou 3), avec la
  configuration du cas, son historique, la réponse du harnais à H5 et `on_overflow`. L'outil lit
  les appels au modèle de chaque essai. Il ne désactive jamais le contrôle de la fenêtre : il mesure
  sur la fenêtre réelle.
