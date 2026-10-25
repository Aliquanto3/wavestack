"""The routes of « Évaluer l'agent » (V1.5 CAP-4) and their HTTP guard.

`register_agent_eval_routes(app, app_session)` installs, under `/api/agent_eval/`, the list
of the cases, their deletion, the launch of a run, its progress, a run, a try's trace and
the comparison of two runs. Errors: `{"detail": <text in the session's language>}`.

The guard: during a run, every `POST`, `PUT`, `PATCH` or `DELETE` under `/api/` is refused
in 409 (`agent_eval.refused.running`), but `POST /api/intentions/stop`. The intentions of
class (a) (bricks, sub-options, prompt, memory…) would change the configuration the run
restores at its end; those of class (b) are refused by the `agent_eval` state too.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from wavestack.messages import Message, render
from wavestack.session.app_session import AppSession, SendRefused

PREFIX = "/api/agent_eval"
_GUARDED = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_ALLOWED = frozenset({("POST", "/api/intentions/stop")})


class RunIntention(BaseModel):
    """`POST /runs`: the suite (`case_id` null, one try) or one case, 1 or 3 tries."""

    model_config = ConfigDict(extra="forbid")

    case_id: str | None = None
    k: Literal[1, 3] = 1


def register_agent_eval_routes(app: FastAPI, app_session: AppSession) -> None:
    runner = app_session.agent_eval

    def refused(status: int, reason: Any) -> HTTPException:
        return HTTPException(status_code=status, detail=render(reason, app_session.language))

    def keyed(status: int, key: str) -> HTTPException:
        return refused(status, Message(f"agent_eval.refused.{key}"))

    @app.middleware("http")
    async def _agent_eval_guard(request: Request, call_next):  # noqa: ANN001, ANN202
        method, path = request.method, request.url.path
        if (
            method in _GUARDED
            and path.startswith("/api/")
            and (method, path) not in _ALLOWED
            and runner.running
        ):
            detail = render(Message("agent_eval.refused.running"), app_session.language)
            return JSONResponse({"detail": detail}, status_code=409)
        return await call_next(request)

    @app.get(f"{PREFIX}/cases")
    def cases() -> dict[str, Any]:
        return runner.cases().model_dump(mode="json")

    @app.delete(f"{PREFIX}/cases/{{case_id}}")
    def delete_case(case_id: str) -> dict[str, bool]:
        try:
            runner.delete_case(case_id)
        except KeyError:
            raise keyed(404, "unknown_case") from None
        except SendRefused as exc:
            raise refused(409, exc.reason_text) from None
        return {"deleted": True}

    @app.delete(f"{PREFIX}/cases")
    def clear_cases() -> dict[str, int]:
        try:
            return {"cleared": runner.clear_cases()}
        except SendRefused as exc:
            raise refused(409, exc.reason_text) from None

    @app.post(f"{PREFIX}/runs", status_code=202)
    def start_run(intention: RunIntention) -> dict[str, str]:
        ids = None if intention.case_id is None else [intention.case_id]
        try:
            return {"run_id": runner.start(ids, intention.k)}
        except ValueError:
            raise keyed(422, "k_suite") from None
        except KeyError:
            raise keyed(404, "unknown_case") from None
        except SendRefused as exc:
            raise refused(409, exc.reason_text) from None

    @app.get(f"{PREFIX}/state")
    def state() -> dict[str, Any]:
        return runner.state().model_dump(mode="json")

    @app.get(f"{PREFIX}/runs/{{run_id}}")
    def run(run_id: str) -> dict[str, Any]:
        try:
            return runner.run(run_id).model_dump(mode="json")
        except KeyError:
            raise keyed(404, "unknown_run") from None

    @app.get(f"{PREFIX}/runs/{{run_id}}/trace")
    def trace(run_id: str, case_id: str, trial: int = 1) -> dict[str, Any]:
        try:
            runner.run(run_id)
        except KeyError:
            raise keyed(404, "unknown_run") from None
        try:
            return runner.trace(run_id, case_id, trial).model_dump(mode="json")
        except KeyError:
            raise keyed(404, "unknown_trial") from None

    @app.get(f"{PREFIX}/compare")
    def compare(a: str, b: str) -> dict[str, Any]:
        try:
            return runner.compare(a, b).model_dump(mode="json")
        except KeyError:
            raise keyed(404, "unknown_run") from None
        except ValueError:
            raise keyed(422, "same_run") from None
