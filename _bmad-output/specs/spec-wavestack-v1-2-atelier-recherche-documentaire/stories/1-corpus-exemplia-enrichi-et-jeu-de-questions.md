---
title: 'Story 1 : corpus Exemplia enrichi et jeu de questions'
type: 'feature'
created: '2026-10-23'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-2-atelier-recherche-documentaire/corpus-et-questions.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le corpus Exemplia compte 8 documents par langue, sans renvois exploitables, sans versions, sans marquage de droits ni document d'attaque, et aucun jeu de questions préparées n'existe. Les stories suivantes de la V1.2 (décomposition, GraphRAG, Évaluer, attaques, effacement, droits) n'ont donc pas de cas concret.

**Approach:** Ajouter des documents fictifs de la même entreprise, pour 25 à 30 au total, et trois métadonnées dans `content/rag.yaml` : `audience`, `active` et `languages`. Livrer un jeu de questions en fr, en et de, chargé et validé par pydantic, et vérifié par un test qui retrouve chaque extrait attendu dans son document. Contenu seulement : aucune nouvelle étape, aucune interface.

## Boundaries & Constraints

**Always:**
- Les 8 documents existants restent, avec leurs `id`. On peut les retoucher pour rendre un renvoi explicite.
- Le contenu est entièrement fictif et ne contient aucune donnée personnelle réelle.
- Chaque document déclare `audience: all` ou `audience: hr`. Il y a 3 ou 4 documents RH.
- Le document piégé et la sentinelle sont `active: false`, et `chunk_corpus` les exclut. Ils sont traduits dans les trois langues.
- Un document monolingue déclare `languages: [de]`, par exemple. Son fichier est rangé sous `content/corpus/`, dans sa langue d'origine, et n'a pas de copie sous `i18n/`. Le repli de `config.content_file` l'indexe donc tel quel dans les trois index. Le contrôle de miroir l'exempte par ce champ.
- Le corpus actif tient en environ 12 000 tokens par langue. Le plafond est de 16 384 tokens, question et réponse comprises.
- Le jeu de questions compte au moins 3 questions par type, pour 7 types, dans les trois langues. Les surcouches en et de reprennent les mêmes `id`, `type` et `doc_id`.
- Décision d'Anaël (2026-10-23) : fr, en et de en une seule passe, relus au point d'étape final.
- Décision d'Anaël (2026-10-23) : l'annotation humaine est reportée à la story 15. Ici, `RagQuestion` ne porte qu'un champ `annotation` facultatif, laissé vide.
- Les tests qui attendaient un document précis en tête de résultats sont réalignés sur le nouveau corpus sans changer leur intention. C'est aussi le cas des E2E.

**Never:**
- Pas de sélecteur de question ni d'interface : c'est la story 4.
- Pas de filtrage par profil (story 18), pas d'activation du document piégé ou de la sentinelle (stories 17 et 18), pas de bouton Ajouter, Modifier ou Supprimer (story 3).
- Pas de changement du découpage ni des réglages de la recherche.
- Pas de nouvelle dépendance.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Document inactif | `active: false` | Absent des chunks, de l'index et de l'empreinte du corpus | N/A |
| Document monolingue | `languages: [de]`, fichier dans `content/corpus/` | Indexé en allemand dans les index fr, en et de ; exempté du miroir | Le test échoue si une copie existe sous `i18n/` |
| Question interlingue | Question en fr, passage attendu dans un document en de seulement | L'extrait est retrouvé dans le texte allemand | N/A |
| Question sans réponse | `type: no_answer` | `expected_passages` vide, réponse attendue « je ne sais pas » | Le modèle refuse une liste non vide |
| Question temporelle | v1 périmée, v2 en vigueur | Passage attendu dans la v2, passage de la v1 dans `trap_passages` | N/A |
| Fichier de questions invalide | Clé inconnue ou `doc_id` inconnu | Erreur de validation explicite au chargement | `extra="forbid"`, validateur de `doc_id` |

</frozen-after-approval>

## Code Map

- `content/rag.yaml:52-77` et les surcouches `content/i18n/{en,de}/rag.yaml` -- liste `documents` (`id`, `title_text`, `file`). Les surcouches reprennent la liste ; les documents monolingues y sont déclarés aussi, avec leur titre traduit.
- `src/wavestack/rag/corpus.py:24-29` `CorpusDocument` (`extra="forbid"`) -- ajouter `audience`, `active` et `languages`. `:50` `RagContent`, `:84` `load_rag_content(lang)`.
- `src/wavestack/rag/corpus.py:129-143` `chunk_corpus` -- point d'entrée unique du corpus (index, session, atelier, empreinte) : y filtrer `active`.
- `content/corpus/*.md` -- format : `# Titre`, commentaire `<!-- Texte fictif… -->`, paragraphes ; 312 à 347 mots par document.
- `data/rag_index.sqlite`, `data/rag_index.en.sqlite`, `data/rag_index.de.sqlite` -- index versionnés à reconstruire avec `scripts/build_rag_index.py --lang …`. Sinon, la session les signale périmés (`app_session.py:3197`).
- `tests/test_i18n.py:100, 173-187, 252, 309-315` -- miroir du corpus et parité des `(id, file)`, à exempter selon `languages`.
- `tests/test_rag.py:179-189` -- `len(documents) == 8` et 250 à 450 mots, à réaligner.
- Têtes de résultats attendues, à revérifier : `test_rag.py:198,226,565`, `test_rag_lab.py:110,560`, `test_rag_rerank.py:267`, `test_rag_review.py:118`, `test_annex_language.py:141-147`, `tools/e2e/run_e2e.py:6613,6958`.
- `docs/guide.md:132` -- « huit textes fictifs ».
- Schéma de question repris du brouillon V2 : `_bmad-output/specs/spec-wavestack-v2/stories/1-jeu-de-questions-reponses-attendues.md:29-32`.
- Comptage des tokens : tiktoken `cl100k_base`, livré hors ligne (`compression/env.py:55 apply_offline_env()`), dans l'extra `compression`.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/rag/corpus.py` -- champs `audience: Literal["all","hr"]`, `active: bool = True` et `languages: list[str] | None = None` ; filtre `active` dans `chunk_corpus`. Ajouter un modèle `RagQuestion` (`extra="forbid"`) et `load_rag_questions(lang)`, avec un validateur qui contrôle `doc_id` et les passages selon le type -- le contenu doit se valider au chargement.
- [x] `content/corpus/*.md`, `content/i18n/{en,de}/corpus/*.md` -- écrire les nouveaux documents (liste des Design Notes) et retoucher les renvois des existants -- CAP-1.
- [x] `content/rag.yaml` et ses deux surcouches -- déclarer les documents et leurs métadonnées.
- [x] `content/rag_questions.yaml` et ses deux surcouches -- au moins 21 questions -- CAP-2.
- [x] `tests/test_rag_questions.py` -- chaque extrait attendu, et chaque extrait piège, existe dans `content_file(doc.file, lang)` pour chaque langue ; au moins 3 questions par type ; parité des `id`, `type` et `doc_id` entre langues ; un `doc_id` inconnu est refusé ; un document inactif n'est pas découpé.
- [x] `tests/test_i18n.py`, `tests/test_rag.py` et les tests de têtes de résultats -- exemption des monolingues, bornes de 25 à 30 documents et de 150 à 450 mots, réalignement des têtes.
- [x] `data/rag_index*.sqlite` -- reconstruire les trois index.
- [x] `docs/guide.md:132` -- décrire le nouveau corpus en une phrase.
- [x] `.memlog.md` de la spec -- consigner les tokens mesurés par langue.

**Acceptance Criteria:**
- Given le corpus livré, when on charge `rag.yaml` dans chaque langue, then il y a entre 25 et 30 documents, chacun avec son `audience`, et exactement deux documents inactifs.
- Given le corpus actif, when on compte ses tokens avec `cl100k_base`, then chaque langue reste sous 15 000 tokens et vise environ 12 000.
- Given le jeu de questions, when la suite `tests/test_rag_questions.py` tourne, then chaque type a au moins 3 questions dans chaque langue et tous les extraits sont trouvés.
- Given le nouveau corpus, when on lance la suite RAG et les E2E RAG ciblés, then ils sont verts et aucun index n'est signalé périmé.

## Design Notes

Proposition de documents à ajouter (19, pour 27 au total), à valider :
- **Chaîne multi-sauts 1** : `incidents` (existant) → `gestion_crise` (procédure de crise) → `astreinte` (annexe des contacts d'astreinte).
- **Chaîne multi-sauts 2** : `prestataires` (politique) → `clauses_contrats` (clauses de sécurité) → `registre_sous_traitants`.
- **Temporel** : `charte_messagerie_v1` (2024, périmée), `charte_messagerie_v2` (2026, en vigueur), `note_changement_messagerie`.
- **Monolingues** : `rundschreiben_usb` (de, circulaire du siège allemand), `uk_visitor_badges` (en, filiale britannique), `plan_continuite_lyon` (fr).
- **RH** (`audience: hr`) : `grille_remunerations`, `dossier_disciplinaire`, `entretiens_annuels`.
- **Autres** : `acces_physique`, `revue_habilitations`, `formation_securite`.
- **Inactifs** : `faq_mots_de_passe` (piégé : une instruction cachée, et une fausse longueur minimale qui vise une question factuelle) et `projet_talvane` (sentinelle, code fictif `TLV-7731-QZ`).
- **Sans réponse** : stationnement, mutuelle, restauration (thèmes absents).

Schéma d'une question (fr) :
```yaml
- id: q_multi_1
  type: multi_hop   # factual | multi_hop | global | no_answer | temporal | cross_lingual | follow_up
  history: []       # tours précédents, pour follow_up
  question_text: Qui appeler la nuit en cas d'incident majeur ?
  expected_answer_text: …
  expected_passages: [{doc_id: gestion_crise, anchor_text: …}, {doc_id: astreinte, anchor_text: …}]
  trap_passages: []  # temporal : passage de la v1
```

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_rag_questions.py tests/test_rag.py tests/test_i18n.py tests/test_rag_lab.py tests/test_rag_rerank.py tests/test_rag_review.py tests/test_annex_language.py` -- expected : vert.
- `uv run python .claude/cost-kit/controle_rapide.py` -- expected : vert.
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only <scénarios RAG>` -- expected : vert.

## Implementation Notes

- 19 nouveaux documents (27 au total, 25 actifs, 2 inactifs : `faq_mots_de_passe` piégé, `projet_talvane` sentinelle), 3 monolingues (`rundschreiben_usb` de, `uk_visitor_badges` en, `plan_continuite_lyon` fr) exemptés du miroir i18n via `languages`.
- `incidents.md` (fr/en/de) retouché pour renvoyer explicitement à `gestion_crise`/`astreinte` (chaîne multi-sauts 1).
- 21 questions (3 × 7 types) en fr/en/de dans `content/rag_questions.yaml` ; chaque `anchor_text` vérifié par script contre le fichier réel de sa langue avant d'écrire le test ; parité `id`/`type`/doc_id` entre langues vérifiée.
- Tokens `cl100k_base` du corpus actif (mesurés avec `uv run --extra compression`) : fr 9762, en 7099, de 10622 -- sous le plafond de 15000 ; en est sous la cible d'~12000 mais aucun ajustement n'a été demandé pour ça.
- Index reconstruits avec `uv run python scripts/build_rag_index.py --lang {fr,en,de}` (modèle réel Granite Embedding, déjà présent sur le poste).
- Têtes de résultats réalignées : `test_rag.py` (bornes 25-30 documents, 150-450 mots), `test_rag_lab.py`/`test_rag_rerank.py` (comptes d'extraits 73/187/50/74, le reranking de la requête hôtel est rétabli en revue, voir Review Triage Log), `test_annex_language.py` (sha256 de l'index français, filtre `active` sur les ensembles de titres/doc_id).
- `RagQuestion.audience` ajouté (facultatif, cité par `corpus-et-questions.md`) en plus du schéma des Design Notes, pour la question RH de type `global`.

## Spec Change Log

## Review Triage Log

Revue unique (Opus, 2026-10-23), base be6124d à jour, aucun rebase.

- medium · second avis 1 · corrigé · la ligne « document monolingue » de la matrice n'avait pas de test : `test_a_monolingual_document_has_no_copy_and_is_chunked_as_is` (fr, en, de) échoue si une copie existe sous `i18n/` et vérifie que le fichier d'origine est découpé tel quel.
- medium · second avis 2 · corrigé · la démonstration du reranking avait été remplacée par « l'ordre ne change pas » (intention changée). Avec `FakeEmbedder` et 27 documents, la question de l'hôtel classait « Déplacements » 10e, hors des 8 candidats. Le prompt du scénario `rag_rerank` devient « Quel plafond de remboursement pour une nuit d'hôtel à Paris chez Exemplia ? » (même sens). « Déplacements » repasse 6e à l'embedding, puis 1er au reranking. Les assertions d'origine sont rétablies en pytest (`("deplacements", 6)`) et en E2E (avant > 3, flèche ↑, « Extrait 1 — Déplacements et notes de frais » dans le corps). Surcouches en et de inchangées : leur sens couvre les deux formulations.
- low · second avis 3 · rejeté · « 25 documents (27 déclarés dans content/rag.yaml) » est exact : 27 documents sont bien déclarés, dont 2 inactifs.
- low · second avis 4 · rejeté · le seul chargeur, `load_rag_questions`, passe toujours le contexte `doc_ids`. La validation sans contexte ne sert qu'aux tests de schéma.
- low · second avis 5 · sans objet · l'assertion `("classification", 1)` disparaît avec le correctif 2.
- info · revue · vérifié · réponses `no_answer` en « Je ne sais pas » / « I don't know » / « Ich weiß es nicht ». Renvois des deux chaînes multi-sauts présents dans le texte. v1 (janvier 2024) et v2 (1er janvier 2026) datées. Contenu fictif, mention « Texte fictif » présente. Thèmes sans réponse absents du corpus.
- info · revue · noté · `test_annex_language.py::test_a_missing_index_of_the_language_offers_its_build` a échoué une fois dans un lot de 9 fichiers (4 min, poste chargé). Il passe seul et dans son fichier (30/30) : attente de construction sensible à la charge, sans lien avec la story.
- Complexité : 0 constat (contenu et chargeurs lus une fois, aucune structure qui grossit).
