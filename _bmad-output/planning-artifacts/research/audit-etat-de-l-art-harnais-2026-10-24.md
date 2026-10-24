# Audit état de l'art des harnais (2026-10-24)

Produit en session Claude Code le 2026-10-24, à la demande d'Anaël : vérifier que WaveStack est à l'état de l'art des harnais agentiques, sur le fond et sur la pédagogie. Sources fournies : arXiv 2609.00006, walkinglabs/learn-harness-engineering, OCTO, SFEIR. Suite donnée : `../sprint-change-proposal-2026-10-24-etat-de-l-art-harnais.md`.

Les quatre sources sont globalement correctes, mais de fiabilité inégale. WaveStack applique déjà l'essentiel de leurs principes, et parfois mieux qu'elles ne le décrivent. J'ai repéré cinq écarts, surtout de pédagogie, et un seul touche au fond (le RAG).

## 1. Vérification des sources

| Source | Fiabilité | Ce qui est solide | Ce qui pose problème |
|---|---|---|---|
| **arXiv 2609.00006** (Barbaste et al., **Wavestone AI Lab**, juillet 2026) | Élevée : c'est la référence | Étude du code source de 11 harnais de code (Claude Code, Codex CLI, Gemini CLI…). Elle définit le harnais (« tout sauf le modèle ») en **7 sous-systèmes** : boucle, intégration LLM, outils, mémoire et contexte, sécurité, orchestration, extensibilité. Elle en tire 13 observations et 18 recommandations, avec la bonne filiation du terme (Hashimoto et Trivedy chez LangChain en février 2026, Böckeler en avril). | Le périmètre est celui des **agents de code** : « pas de RAG sur le code » ne veut pas dire « pas de RAG sur des documents ». Les scores SWE-bench sont annoncés par les éditeurs. Claude Code est étudié à partir d'une copie de son code source qui a circulé (la fuite de mars 2026). Détail sans incidence : l'identifiant 2609 (septembre) ne colle pas avec la date « 15 Jul 2026 » imprimée dans la marge. |
| **walkinglabs/learn-harness-engineering** (environ 21 000 étoiles) | Bonne | Ses principes rejoignent les articles d'Anthropic sur les agents qui travaillent longtemps : le dépôt comme source de vérité, l'état gardé sur disque, une fonctionnalité à la fois, une fin de tâche prouvée par des tests, le créateur séparé du vérificateur. | Le sens est différent : c'est le harnais que **l'utilisateur** monte autour d'un agent de code (AGENTS.md, feature_list, init.sh), pas le moteur interne. Le cours vise des développeurs. |
| **OCTO** (Bruno Boucard, 23 octobre 2026) | Bonne | Les prix sont exacts : ce sont ceux de ta grille. Le calcul se vérifie : un token de sortie coûte bien 100 fois un token d'entrée relu en cache (20 $ contre 0,20 $ par million). Les principes s'appuient sur des sources : contexte stable au début et dynamique à la fin, outils chargés à la demande, rester mono-agent. | Les volumes de tokens sont des exemples inventés pour l'illustration. « Fusionner les pipelines multi-agents » est à nuancer : selon le papier (R12), des sous-agents en parallèle restent rentables pour explorer large. |
| **SFEIR** (Charlotte Ryssen, mai 2026) | La plus faible | Les 5 couches (contexte, outillage, exécution, garde-fous, observabilité) font une grille de lecture correcte. Le papier Meta-Harness qu'elle cite existe ([arXiv 2603.28052](https://arxiv.org/abs/2603.28052), Stanford). | **Chiffres faux** : SWE-bench Verified n'existe que depuis août 2024, donc « 5 % en 2023 » est anachronique, et « plus de 50 % en 2026 » sous-estime : les meilleurs dépassaient 80 % dès fin 2025. Elle range **BMAD, GSD et Spec Kit parmi les « méta-harnais »**, ce qui contredit le papier (un méta-harnais orchestre des harnais, comme Omnigent) et Meta-Harness (optimisation automatique du harnais). Le même mot a donc trois sens : à éviter devant des apprenants. La formule « Agent = Modèle + Harness » est attribuée sans source à Anthropic, Salesforce et Princeton, alors qu'elle vient de Trivedy chez LangChain. |

J'ai ajouté une source qui vaut d'être citée : **Böckeler** ([martinfowler.com](https://martinfowler.com/articles/harness-engineering.html)). Son cadre est très pédagogique : des **guides**, qui orientent l'agent avant qu'il agisse, et des **capteurs**, qui contrôlent après coup ; des contrôles **calculés** (tests, lint) ou **déduits par un modèle** (IA qui juge).

## 2. Ce que WaveStack applique déjà bien

- **La définition** : « Le modèle prédit du texte ; le harnais en fait un agent », « même modèle, harnais différent, comportement différent » (`content/demo_files/guide_harnais.md`). C'est exactement « Agent = Model + Harness ».
- **Le contexte comme ressource rare**, avec un gain et un coût pour chaque brique : c'est le cœur de l'article OCTO et du *context engineering* d'Anthropic.
- **Le chargement progressif** (skills par `load_skill`, MCP en lazy loading) : recommandation R4 et observation 8 du papier.
- **L'hygiène du cache** : la mémoire globale n'entre dans le message système qu'à la conversation suivante, pour qu'il reste stable (`content/bricks/global_memory.yaml`). C'est le principe de l'article OCTO et le choix d'un des harnais étudiés (Hermes). De même, le hook d'injection place la date **avant le message**, pas dans le prompt système, donc en fin de contexte, comme le préconise OCTO.
- **Des hooks déterministes que le modèle ne peut pas contourner**, plus la validation humaine avant tout appel réseau : R11 (règles de sécurité sous forme de données ou de hooks).
- **Des bornes de boucle bon marché** (nombre d'appels, nouveaux essais, réserve de sortie) : R18 mot pour mot.
- **Un sous-agent au contexte isolé**, avec « déléguer ne rend pas plus intelligent » : la nuance de R12.
- **La distinction skill, MCP, outil et prompt système** : R14.
- **L'observabilité et les flux de données** (volet Orchestration, données sortantes) : la 5ᵉ couche de SFEIR, chapitre 6 de walkinglabs.

## 3. Écarts et pistes, par priorité

1. **Le RAG (sur le fond).** WaveStack présente le RAG vectoriel injecté à chaque tour comme *la* brique de recherche. Or aucun des 11 harnais étudiés n'utilise d'embeddings sur le code (observation 9). Ils cherchent **au moment où ils en ont besoin, avec des outils déterministes** (grep, glob, lecture de fichier), et Anthropic recommande la même chose. Sur un corpus documentaire, le RAG vectoriel reste légitime, mais il faudrait ajouter dans `content/bricks/rag.yaml` un paragraphe « RAG injecté ou recherche agentique ». Un outil de recherche dans le corpus (`search_files`) permettrait même de comparer les deux sur un scénario.
2. **Une carte d'ensemble absente.** Le programme avance brique par brique, sans récapitulatif qui situe chaque brique dans les 7 sous-systèmes du papier (ou les 5 couches). Une carte finale, par exemple une fiche « À retenir » ou un écran, est peu coûteuse et donnerait une base commune avec le papier de vos collègues.
3. **Des catégories discutables.** « Raisonnement » est classé *prompt engineering*, alors que c'est une capacité du modèle que le harnais active (sous-système « intégration LLM »). « Garde-fous » est classé « harnais » alors que les autres briques sont « harness engineering ». Dans la littérature, les trois disciplines s'emboîtent : prompt ⊂ contexte ⊂ harnais.
4. **La compaction est nommée, jamais montrée.** Le débordement est refusé et les stratégies sont seulement listées (`content/messages.yaml:140`). Le papier note que la compaction est devenue standard (7 harnais sur 11) et que la piste la plus récente est la façon d'écrire la mémoire. Avec une fenêtre de 4 096 tokens, une démonstration de compaction ou de fenêtre glissante serait très parlante, au prix d'un appel de résumé sur CPU. C'est une candidate pour la V1.2 ou après.
5. **Il manque des notions récentes, toutes peu coûteuses à ajouter.**
   - Les **fichiers de contexte hiérarchiques** (AGENTS.md, CLAUDE.md), convention présente dans les 11 harnais (R6) : une phrase dans la brique Prompt système.
   - Le cadre **guides et capteurs** de Böckeler, qui classe d'un coup prompt, skills, hooks et garde-fous.
   - L'**échafaudage à alléger quand le modèle progresse** (thèse OCTO). WaveStack en est l'illustration inverse : ses prompts nomment l'outil parce que le petit modèle en a besoin. Le dire aux apprenants transforme une contrainte en leçon.
   - Les **skills tiers à traiter comme des paquets** (vérification, quarantaine), à placer dans les scénarios sécurité.

Hors périmètre, je pense, de ce démonstrateur : la plateformisation (ACP, places de marché), les bacs à sable au niveau du système d'exploitation, les modes de permission plan / défaut / sans confirmation. Un rappel d'une ligne suffirait.

Je peux en faire une page à partager, par exemple avec les auteurs du papier au Wavestone AI Lab.

Sources :
- [Barbaste et al., *Harness Engineering*, arXiv 2609.00006](https://arxiv.org/pdf/2609.00006)
- [walkinglabs/learn-harness-engineering](https://github.com/walkinglabs/learn-harness-engineering)
- [OCTO, Harnais agentiques (1/2)](https://blog.octo.com/harnais-agentiques-(12)--pourquoi-les-bonnes-pratiques-d%27hier-coutent-cher-aujourd%27hui)
- [SFEIR, Agent harness](https://www.sfeir.dev/agent-harness-pourquoi-lavenir-de-lia-secrit-desormais-autour-du-modele-et-non-plus-dedans/)
- [Böckeler, Harness engineering (martinfowler.com)](https://martinfowler.com/articles/harness-engineering.html)
- [Lee et al., Meta-Harness, arXiv 2603.28052](https://arxiv.org/abs/2603.28052)
- [Addy Osmani, Agent Harness Engineering](https://addyosmani.com/blog/agent-harness-engineering/)
- [The anatomy of an agent harness (résumé de l'article LangChain)](https://www.dailydoseofds.com/p/the-anatomy-of-an-agent-harness/)
- [walkinglabs/awesome-harness-engineering](https://github.com/walkinglabs/awesome-harness-engineering)
