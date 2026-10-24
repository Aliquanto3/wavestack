"""V1.3 story 2 (CAP-2): the cache gauge's texts, in the three languages, and the text of every
`PrefixCause` it can cite (a cause added later, such as story 3's, fails here until its text is)."""

from pathlib import Path
from typing import get_args

import pytest
import yaml

from wavestack.trace.catalog import PrefixCause

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "fr": ROOT / "content" / "ui.yaml",
    "en": ROOT / "content" / "i18n" / "en" / "ui.yaml",
    "de": ROOT / "content" / "i18n" / "de" / "ui.yaml",
}
KEYS = {
    "label", "read", "write", "write_1h", "uncached", "not_declared", "not_applicable",
    "not_measured", "local_note", "cause", "cause_unknown", "short", "short_none",
    "short_not_measured", "pair",
}  # fmt: skip


@pytest.mark.parametrize("language", FILES)
def test_every_cause_has_its_text(language: str) -> None:
    main = yaml.safe_load(FILES[language].read_text(encoding="utf-8"))["main"]
    causes = main["orch"]["prefix_causes"]
    missing = [c for c in get_args(PrefixCause) if not str(causes.get(c, "")).strip()]
    assert not missing, f"{language}: no text for {missing}"


@pytest.mark.parametrize("language", FILES)
def test_cache_gauge_texts_exist(language: str) -> None:
    main = yaml.safe_load(FILES[language].read_text(encoding="utf-8"))["main"]
    texts = main["cache_gauge"]
    assert set(texts) == KEYS
    assert "{tokens}" in texts["read"] and "{tokens_1h}" in texts["write_1h"]
    assert "{cause}" in texts["cause"] and "{percent}" in texts["short"]
    assert "{name}" in texts["pair"] and "{value}" in texts["pair"]
