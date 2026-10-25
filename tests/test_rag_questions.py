"""Story 1: the demonstration question set (corpus-et-questions.md).

Each question's expected and trap passages must really be found in their document, in
every language where the question exists; the schema validates `doc_id` at load time.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from wavestack import config
from wavestack.rag.corpus import (
    RagQuestionSet,
    chunk_corpus,
    load_rag_content,
    load_rag_questions,
)

LANGS = ("fr", "en", "de")
TYPES = (
    "factual",
    "multi_hop",
    "global",
    "no_answer",
    "temporal",
    "cross_lingual",
    "follow_up",
)


@pytest.fixture(autouse=True)
def _fresh_content_caches():
    config.clear_content_caches()
    yield
    config.clear_content_caches()


@pytest.mark.parametrize("lang", LANGS)
def test_every_passage_anchor_is_found_in_its_document(lang):
    questions = load_rag_questions(lang)
    content = load_rag_content(lang)
    files = {doc.id: doc.file for doc in content.documents}
    for question in questions:
        for passage in (*question.expected_passages, *question.trap_passages):
            text = config.content_file(files[passage.doc_id], lang).read_text(encoding="utf-8-sig")
            assert passage.anchor_text in text, (question.id, passage.doc_id)


@pytest.mark.parametrize("lang", LANGS)
def test_every_type_has_at_least_three_questions(lang):
    questions = load_rag_questions(lang)
    counts = {t: 0 for t in TYPES}
    for question in questions:
        counts[question.type] += 1
    assert all(count >= 3 for count in counts.values()), counts


def test_the_overlays_keep_the_same_ids_types_and_doc_ids_as_french():
    french = load_rag_questions("fr")
    french_shape = [
        (q.id, q.type, [p.doc_id for p in q.expected_passages], [p.doc_id for p in q.trap_passages])
        for q in french
    ]
    for lang in ("en", "de"):
        translated = load_rag_questions(lang)
        shape = [
            (
                q.id,
                q.type,
                [p.doc_id for p in q.expected_passages],
                [p.doc_id for p in q.trap_passages],
            )
            for q in translated
        ]
        assert shape == french_shape


def test_a_no_answer_question_has_no_expected_passage():
    for question in load_rag_questions("fr"):
        if question.type == "no_answer":
            assert question.expected_passages == []


def test_an_unknown_doc_id_is_refused_at_load():
    with pytest.raises(ValidationError):
        RagQuestionSet.model_validate(
            {
                "questions": [
                    {
                        "id": "q_bad",
                        "type": "factual",
                        "question_text": "?",
                        "expected_answer_text": "!",
                        "expected_passages": [{"doc_id": "ne_existe_pas", "anchor_text": "x"}],
                    }
                ]
            },
            context={"doc_ids": {"mots_de_passe"}},
        )


def test_a_no_answer_question_with_a_passage_is_refused_at_load():
    with pytest.raises(ValidationError):
        RagQuestionSet.model_validate(
            {
                "questions": [
                    {
                        "id": "q_bad",
                        "type": "no_answer",
                        "question_text": "?",
                        "expected_answer_text": "!",
                        "expected_passages": [{"doc_id": "mots_de_passe", "anchor_text": "x"}],
                    }
                ]
            }
        )


def test_an_unknown_field_is_refused_at_load():
    with pytest.raises(ValidationError):
        RagQuestionSet.model_validate(
            {
                "questions": [
                    {
                        "id": "q_bad",
                        "type": "factual",
                        "question_text": "?",
                        "expected_answer_text": "!",
                        "unexpected_field": True,
                    }
                ]
            }
        )


def test_an_inactive_document_is_not_chunked():
    content = load_rag_content("fr")
    chunks = chunk_corpus(content, 700)
    chunked_ids = {c.doc_id for c in chunks}
    inactive = {doc.id for doc in content.documents if not doc.active}
    assert inactive == {"faq_mots_de_passe", "projet_talvane"}
    assert not inactive & chunked_ids


@pytest.mark.parametrize("lang", LANGS)
def test_a_monolingual_document_has_no_copy_and_is_chunked_as_is(lang):
    """I/O matrix: `languages: [de]` keeps one file under `content/corpus/`, indexed as-is
    in every language through `content_file`'s fallback; a copy under i18n/ fails here."""
    content = load_rag_content(lang)
    monolingual = [doc for doc in content.documents if doc.languages]
    assert {doc.id for doc in monolingual} == {
        "rundschreiben_usb",
        "uk_visitor_badges",
        "plan_continuite_lyon",
    }
    chunks = chunk_corpus(content, 700, lang)
    for doc in monolingual:
        for other in LANGS[1:]:
            assert not (config.content_dir() / "i18n" / other / doc.file).exists(), doc.file
        original = (config.content_dir() / doc.file).read_text(encoding="utf-8-sig")
        assert config.content_file(doc.file, lang) == config.content_dir() / doc.file
        doc_chunks = [c.text for c in chunks if c.doc_id == doc.id]
        assert doc_chunks and all(text[:40] in original for text in doc_chunks)
