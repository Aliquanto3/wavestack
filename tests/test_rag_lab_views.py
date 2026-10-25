"""V1.2 story 4: the view tabs, the prepared-question selector and the comparison's texts
(CAP-2, CAP-9). The comparison itself is drawn by the page from the journal's events (checked
by the E2E scenario `rag_lab_views`); here the session's side: the questions the state hands
to the selector and the texts in the three languages.

Real code throughout; the doubles stand at the boundary (fake embedder, reranker and engine).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_bricks import HEADERS  # noqa: F401  (the fixtures of the RAG tests)
from test_rag import build
from test_rag_lab import _client, ready

from wavestack.rag import lab as rag_lab
from wavestack.rag.corpus import load_rag_questions

STATIC = Path(__file__).resolve().parent.parent / "src" / "wavestack" / "web" / "static"


@pytest.fixture
def index(tmp_path: Path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


def test_the_state_hands_the_prepared_questions_to_the_selector(index):
    session, _ = ready(index)
    questions = session.rag_lab_state()["questions"]
    shipped = [q for q in load_rag_questions("fr") if not q.history]
    assert [q["id"] for q in questions] == [q.id for q in shipped]
    assert all(set(q) == {"id", "type", "question_text"} for q in questions)
    assert questions and {q["type"] for q in questions} >= {"factual", "no_answer", "temporal"}
    # Over HTTP too, the page's own source.
    assert _client(session).get("/api/rag_lab").json()["questions"] == questions


@pytest.mark.parametrize("lang", ["fr", "en", "de"])
def test_the_tab_prepared_and_compare_texts_exist_in_each_language(lang):
    content = rag_lab.load_lab_content(lang)
    assert content.tabs.compare_text and content.compare.pinned_text != content.compare.current_text
    assert content.prepared.types.factual_text and "{name}" in content.tabs.soon_text
    assert "{question}" in content.compare.pinned_status_text
    assert load_rag_questions(lang)  # the same questions, the same file in each language


def test_the_page_is_the_document_search_workshop_with_five_tabs():
    html = (STATIC / "rag.html").read_text(encoding="utf-8")
    for tab in ("build", "compare", "evaluate", "attack", "sheets"):
        assert f'data-tab="{tab}"' in html and f'id="rag-panel-{tab}"' in html
    assert "Atelier recherche documentaire" in html and "Atelier RAG" not in html.split("<main")[1]
    # The common bar gains no tab; the lot 5 selectors stay (the A/B ids stay gone).
    assert html.count('class="site-nav-brand"') == 1 and 'id="rag-run"' in html
    assert 'id="rag-compare"' not in html and 'id="rag-comparison"' not in html
