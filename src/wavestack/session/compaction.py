"""V1.4 story 4 (CAP-5): compaction and sliding window of the main chat's short memory.

Pure helpers of the session: which strategies apply and how many exchanges they keep
(`compaction_plan`), the transcript the summary call reads (`transcript_entries`), and the
local documentations still read in the history once old exchanges left it (`kept_docs`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any, Literal, NamedTuple

Strategy = Literal["compaction", "sliding_window"]
STRATEGIES: tuple[Strategy, ...] = ("compaction", "sliding_window")
COMPONENT = "short_memory.compaction"  # the summary call's and the summary's component
LOAD_TOOL_DOC = "load_tool_doc"  # the lazy loading meta-tool (AD-25)
LABELS = ("previous", "user", "assistant", "tool")  # `session.compaction.transcript.*`


class Plan(NamedTuple):
    """One strategy for a history of `n` exchanges: `kept` recent ones stay, the `n - kept`
    oldest are summarized or removed; unavailable, `reason` is the key under
    `session.overflow.choices.unavailable`."""

    strategy: Strategy
    available: bool
    kept: int
    removed: int
    reason: str | None = None


def _largest(low: int, high: int, fits: Callable[[int], bool]) -> int:
    """The largest `k` of `[low, high]` that fits, `fits(low)` being true and `fits`
    monotone (fewer exchanges kept, smaller context): a dichotomy, O(log n) calls."""
    while low < high:
        middle = (low + high + 1) // 2
        if fits(middle):
            low = middle
        else:
            high = middle - 1
    return low


def compaction_plan(
    n: int,
    fits: Callable[[int, bool], bool] | None,
    keep: int,
    overflow: bool,
) -> dict[Strategy, Plan]:
    """The two strategies for `n` exchanges (a summary already there counts as one).

    At an overflow, `fits(k, compacted)` says whether the refused call holds with the `k`
    most recent exchanges (after a summary when `compacted`): the sliding window keeps at
    least the last one and removes at least one; the compaction summarizes at least one.
    A choice whose minimum still does not hold is unavailable (`still_too_long`). Outside
    an overflow, both keep `keep` exchanges and need more than that (`too_few`)."""
    if not overflow:
        enough = n > keep
        reason = None if enough else "too_few"
        return {s: Plan(s, enough, min(keep, n), max(0, n - keep), reason) for s in STRATEGIES}
    assert fits is not None
    plans: dict[Strategy, Plan] = {}
    if n == 0:
        return {s: Plan(s, False, 0, 0, "too_few") for s in STRATEGIES}
    if not fits(0, True):
        plans["compaction"] = Plan("compaction", False, 0, n, "still_too_long")
    else:
        kept = _largest(0, n - 1, lambda k: fits(k, True))
        plans["compaction"] = Plan("compaction", True, kept, n - kept)
    if n == 1:
        plans["sliding_window"] = Plan("sliding_window", False, 1, 0, "single")
    elif not fits(1, False):
        plans["sliding_window"] = Plan("sliding_window", False, 1, n - 1, "still_too_long")
    else:
        kept = _largest(1, n - 1, lambda k: fits(k, False))
        plans["sliding_window"] = Plan("sliding_window", True, kept, n - kept)
    return {s: plans[s] for s in STRATEGIES}


def transcript_entries(exchanges: Iterable[Any], labels: dict[str, str]) -> list[str]:
    """One text per exchange to summarize, oldest first: the previous summary, or the user's
    message (already masked by the guardrails) and the final answer; a tool result is named
    with its size only. `labels`: `previous`, `user`, `assistant` and `tool` (`{name}`,
    `{chars}`)."""
    entries = []
    for ex in exchanges:
        if getattr(ex, "summary", False):
            entries.append(f"{labels['previous']} {ex.text}".strip())
            continue
        lines = [f"{labels['user']} {ex.user}"]
        for step in ex.steps:
            if step.get("role") == "tool":
                content = step.get("content")
                size = len(content) if isinstance(content, str) else 0
                lines.append(labels["tool"].format(name=step.get("name") or "?", chars=size))
        lines.append(f"{labels['assistant']} {ex.text}")
        entries.append("\n".join(lines))
    return entries


def kept_docs(exchanges: Sequence[Any], loaded: Iterable[str]) -> set[str]:
    """D16-b (local mode): the documentations still read in the history, those whose
    `load_tool_doc` call is in a kept exchange's steps."""
    named = {
        call.get("arguments", {}).get("tool")
        for ex in exchanges
        for step in ex.steps
        if step.get("role") == "assistant"
        for call in step.get("tool_calls") or []
        if call.get("name") == LOAD_TOOL_DOC and isinstance(call.get("arguments"), dict)
    }
    return {d for d in loaded if d in named}
