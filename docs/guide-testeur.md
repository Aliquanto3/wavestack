# Guide du testeur (WaveStack 1.1)

WaveStack est un démonstrateur pédagogique. Il montre ce qu'un harnais (outils, mémoire, RAG, MCP…) ajoute à un petit LLM qui tourne en local sur CPU. **La qualité des réponses du modèle est secondaire** : ce qu'on teste, c'est la clarté de la démonstration et la robustesse de l'appli.

## Installer (10 à 15 min)

Windows 10 ou 11, sans droits administrateur, 3 Go de disque et 4 Go de RAM libres. Dans **PowerShell** (pas CMD) :

```powershell
irm https://raw.githubusercontent.com/Aliquanto3/wavestack/main/install.ps1 | iex
```

Sur un réseau d'entreprise, tapez d'abord `$env:UV_SYSTEM_CERTS = "1"`. En cas de blocage, voir [l'installation détaillée](installation.md). L'appli s'ouvre dans le navigateur ; Ctrl+C dans le terminal l'arrête.

## Parcours conseillé (45 min environ)

| # | Où | À faire | À observer |
|---|---|---|---|
| 1 | Diagnostic (1er lancement) | Choisir Qwen3.5-2B, puis le lien « Harnais » | Le modèle est trouvé ; les messages sont compréhensibles |
| 2 | Atelier Harnais | Scénario « LLM nu » (en bas à gauche), suivre sa consigne | Le modèle ne connaît pas l'heure |
| 3 | Atelier Harnais | Allumer la brique Outils, reposer la même question | Appel de `get_datetime` visible pas à pas ; les quatre volets restent cohérents |
| 4 | Atelier Harnais | Enchaîner 2 ou 3 scénarios du programme (mémoire, RAG, skills…) | Consignes claires, prompts proposés utiles |
| 5 | Atelier LLM | Taper une phrase | Tokens, vecteurs, probabilités et token tiré lisibles |
| 6 | Atelier RAG | Télécharger les modèles demandés, appliquer un préréglage, poser une question | Étapes d'indexation et de requête compréhensibles ; coûts affichés |
| 7 | Atelier MCP | Lancer un échange | Les messages JSON-RPC se suivent |
| 8 | Sécurité | Parcourir la matrice des risques et les garde-fous | Textes compréhensibles, cohérents avec ce qu'on a vu |
| 9 | Langue | Passer en anglais puis en allemand | Aucun texte resté en français, aucune clé brute affichée |

Facultatif : un modèle cloud avec votre propre clé (Groq ou Gemini ont un plan gratuit), voir le README.

## Ce qui nous intéresse

- **Pédagogie** : comprend-on ce que chaque brique ajoute ? Qu'est-ce qui reste obscur ?
- **Clarté** : textes, libellés, consignes, messages d'erreur.
- **Robustesse** : erreurs, blocages, page figée, comportement après rechargement ou changement de langue.
- **Installation** : chaque obstacle rencontré (proxy, antivirus, droits).

Hors sujet : la justesse ou la lenteur des réponses du modèle local (CPU, 2 milliards de paramètres). Signalez-la seulement si l'appli semble figée sans aucune indication.

## Remonter un retour

Pour chaque retour : **la page**, **ce que vous avez fait**, **ce que vous attendiez**, **ce qui s'est passé**, et une capture si possible. Indiquez votre version de Windows et si vous êtes derrière un proxy. Vous pouvez aussi joindre le terminal de lancement, qui garde les erreurs.
