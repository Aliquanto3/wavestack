"""« En faire un cas » (V1.5 CAP-3): the routes under `/api/agent_eval/` that rebuild a case's
draft from a finished turn, tell whether the case fails on that turn, and save it as a session
case. The server computes the draft and the verdict from the journal; the client sends only
what the formatter typed. No model call, no event emitted, no session state read but its
language.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, TypeAdapter, ValidationError

from wavestack.agent_eval import store
from wavestack.agent_eval.cases import Check, load_provided_cases, new_case_id
from wavestack.agent_eval.checks import CheckVerdict, verify
from wavestack.agent_eval.draft import (
    CaseDraft,
    CaseForm,
    DraftRefused,
    reconstitute_draft,
    to_case,
)
from wavestack.messages import msg
from wavestack.session.app_session import AppSession
from wavestack.trace.journal import get_journal

PREFIX = "/api/agent_eval"
# The kinds a form offers: the catalogue without `model_calls_max` (the cap is a field).
FORM_KINDS = frozenset(
    {
        "tool_called",
        "tool_not_called",
        "argument_never",
        "answer_contains",
        "hook_decided",
        "subagent_called",
        "turn_completed",
    }
)
MAX_CHECKS = 2
# `/verdict` tries the case with these when the formatter has not typed them yet.
_PLACEHOLDER = "…"
_CHECK = TypeAdapter(Check)


class FormVerdict(BaseModel):
    passed: bool  # every check, the cap included, passes on the original turn
    failing: CheckVerdict | None  # the first check that fails
    checks: list[CheckVerdict]
    model_calls: int
    origin_complete: bool  # the original turn ended `completed`


def _clean(check: Any) -> Any:
    """A parameter left empty is a parameter not given."""
    if not isinstance(check, dict):
        return check
    return {
        k: v
        for k, v in check.items()
        if v is not None and not (isinstance(v, str) and not v.strip())
    }


def _check_errors(
    checks: list[dict[str, Any]], lang: str
) -> tuple[list[dict[str, str]], list[Any]]:
    """The field errors of the checks, and the cleaned checks."""
    errors: list[dict[str, str]] = []
    cleaned = [_clean(c) for c in checks]
    for i, check in enumerate(cleaned):
        kind = check.get("kind") if isinstance(check, dict) else None
        if kind not in FORM_KINDS:
            errors.append(
                {
                    "field": f"checks.{i}.kind",
                    "message_text": msg("agent_case.error.checks_kind", lang),
                }
            )
            continue
        try:
            _CHECK.validate_python(check)
        except ValidationError as exc:
            for problem in exc.errors():
                loc = problem["loc"]
                param = str(loc[-1]) if len(loc) > 1 else "kind"
                errors.append(
                    {
                        "field": f"checks.{i}.{param}",
                        "message_text": msg("agent_case.error.required", lang),
                    }
                )
    return errors, cleaned


def _form_errors(
    form: CaseForm, lang: str, *, strict: bool
) -> tuple[list[dict[str, str]], CaseForm]:
    """The 422 body's entries and the form with its checks cleaned. `strict` (the save) also
    asks for the texts."""
    errors: list[dict[str, str]] = []
    if strict:
        for field in ("title_text", "symptom_text", "assertion_text", "prompt"):
            if not getattr(form, field).strip():
                errors.append(
                    {"field": field, "message_text": msg("agent_case.error.required", lang)}
                )
    if form.max_model_calls < 1:
        errors.append(
            {"field": "max_model_calls", "message_text": msg("agent_case.error.max_calls", lang)}
        )
    if not 1 <= len(form.checks) <= MAX_CHECKS:
        errors.append(
            {"field": "checks", "message_text": msg("agent_case.error.checks_count", lang)}
        )
    check_errors, cleaned = _check_errors(form.checks, lang)
    return [*errors, *check_errors], form.model_copy(update={"checks": cleaned})


def register_agent_case_routes(app: FastAPI, app_session: AppSession) -> None:
    def refuse(refused: DraftRefused) -> HTTPException:
        status = 404 if refused.reason == "unknown_turn" else 409
        text = msg(f"agent_case.refused.{refused.reason}", app_session.language)
        return HTTPException(status_code=status, detail=text)

    def draft_of(turn_id: str) -> CaseDraft:
        try:
            return reconstitute_draft(get_journal().all_events(), turn_id)
        except DraftRefused as refused:
            raise refuse(refused) from None

    @app.get(f"{PREFIX}/draft")
    def draft(turn_id: str) -> CaseDraft:
        return draft_of(turn_id)

    @app.post(f"{PREFIX}/verdict", response_model=None)
    def verdict(form: CaseForm) -> FormVerdict | JSONResponse:
        lang = app_session.language
        found = draft_of(form.turn_id)
        errors, form = _form_errors(form, lang, strict=False)
        if errors:
            return JSONResponse(status_code=422, content={"detail": errors})
        trial = form.model_copy(
            update={
                "title_text": form.title_text.strip() or _PLACEHOLDER,
                "symptom_text": form.symptom_text.strip() or _PLACEHOLDER,
                "assertion_text": form.assertion_text.strip() or _PLACEHOLDER,
                "prompt": found.prompt,  # the verdict reads the original turn, not the prompt
            }
        )
        # A session case's id starts with `u`.
        case = to_case(found, trial, "udraft")
        wanted = set(found.verdict_turn_ids)
        envelopes = [e for e in get_journal().all_events() if e.turn_id in wanted]
        result = verify(case, envelopes, lang)
        return FormVerdict(
            passed=result.passed,
            failing=next((c for c in result.checks if not c.passed), None),
            checks=result.checks,
            model_calls=result.model_calls,
            origin_complete=found.origin_status == "completed",
        )

    @app.post(f"{PREFIX}/cases", response_model=None)
    def save(form: CaseForm) -> JSONResponse:
        lang = app_session.language
        found = draft_of(form.turn_id)
        errors, form = _form_errors(form, lang, strict=True)
        if errors:
            return JSONResponse(status_code=422, content={"detail": errors})
        case = to_case(found, form, new_case_id())
        try:
            store.add_session_case(case, load_provided_cases())
        except store.SessionCasesUnreadable:
            raise HTTPException(
                status_code=409, detail=msg("agent_case.error.unreadable", lang)
            ) from None
        return JSONResponse(status_code=201, content={"case": case.model_dump(mode="json")})
