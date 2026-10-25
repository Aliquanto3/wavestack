"""V1.2 story 20 (CAP-18): the RAG workshop's composed chain exposed as an MCP server.

The application is otherwise an MCP *client* (`mcp/connection.py`, `mcp/lab.py`); here it is a
server, read only, on its own port: streamable HTTP under `/mcp/architecture`, 127.0.0.1 only.
`ExposedEndpoint` is mounted once, when the application is created; each start builds a new
`MCPServer` (`build_server`), whose `session_manager.run()` runs once, in a task of the
application's loop, closed by an event at the stop. Stopped, the endpoint answers 404.

The endpoint's guard, in this order: stopped, 404; an `Origin` other than the page's, 403; the
bearer token absent or wrong, 401 (compared in constant time); then the SDK's own application,
whose DNS-rebinding protection stays on. The token lives in memory only.

No `from __future__ import annotations` here: the SDK reads the tools' signatures (their
`Annotated` bounds and descriptions, built at each start in the session's language) as objects.
Importing this module has no side effect.
"""

import asyncio
import hmac
from collections.abc import Awaitable, Callable
from concurrent.futures import Future
from typing import Annotated, Any, Protocol

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field
from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse

from wavestack.rag import exposed

PATH = "/mcp/architecture"
SERVER_NAME = "wavestack-atelier-rag"
PREFIX = "workshop__"  # the tools' names in `mcp/policy._DEFAULTS` and the Journal
TOOLS = ("search_documents", "describe_architecture")
READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
READY_TIMEOUT_S = 5.0  # a request arriving just after the start waits for the manager


def policy_name(tool: str) -> str:
    """The tool's name in the policy and the Journal (`workshop__search_documents`)."""
    return f"{PREFIX}{tool}"


def is_exposed_path(path: str) -> bool:
    """The endpoint's own paths, the only ones `_same_origin_post` lets through without the
    page's `Origin` (a client outside the browser sends none)."""
    return path == PATH or path.startswith(f"{PATH}/")


def client_name(context: Context | None) -> str | None:
    """The client's name as announced at `initialize` (`clientInfo.name`), or `None`."""
    try:
        info = context.session.client_params.client_info  # type: ignore[union-attr]
        return str(info.name) if info is not None and info.name else None
    except Exception:  # noqa: BLE001 - a client that announced nothing
        return None


class Backend(Protocol):
    """What the server asks the session: the rule of a tool, the refusal of a tool whose rule is
    not `allow` (its Journal entry), a search and the description."""

    def rule_of(self, name: str) -> str: ...

    def denied(self, tool: str, client: str | None) -> str: ...

    def search(
        self, question: str, top_k: int, client: str | None
    ) -> Awaitable[CallToolResult]: ...

    def describe(self, client: str | None) -> CallToolResult: ...


class _ExposedServer(MCPServer):
    """`tools/list` without the tools whose current rule is not `allow`, and a `tools/call`
    on one of them refused before its arguments are read: the server has nobody to ask, `ask`
    is a refusal."""

    def __init__(self, backend: Backend, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._backend = backend

    async def list_tools(self):  # noqa: ANN201 - the SDK's own type
        tools = await super().list_tools()
        return [t for t in tools if self._backend.rule_of(policy_name(t.name)) == "allow"]

    async def call_tool(self, name: str, arguments: dict[str, Any], context=None):  # noqa: ANN001, ANN201
        if name in TOOLS and self._backend.rule_of(policy_name(name)) != "allow":
            text = self._backend.denied(name, client_name(context))
            return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)
        return await super().call_tool(name, arguments, context)


def build_server(backend: Backend, texts: exposed.ExposedTexts, version: str = "") -> MCPServer:
    """A new server, its two read-only tools described in the language of the start."""
    server = _ExposedServer(
        backend, name=SERVER_NAME, instructions=texts.server.instructions_text, version=version
    )
    tool_texts = texts.tools

    @server.tool(
        name="search_documents",
        description=tool_texts.search_documents.description_text,
        annotations=READ_ONLY,
    )
    async def search_documents(
        question: Annotated[
            str,
            Field(
                min_length=1,
                max_length=exposed.QUESTION_MAX,
                description=tool_texts.search_documents.question_text,
            ),
        ],
        ctx: Context,
        top_k: Annotated[
            int,
            Field(
                ge=1,
                le=exposed.TOP_K_MAX,
                description=tool_texts.search_documents.top_k_text,
            ),
        ] = exposed.TOP_K_DEFAULT,
    ) -> exposed.SearchResult:
        return await backend.search(question, top_k, client_name(ctx))  # type: ignore[return-value]

    @server.tool(
        name="describe_architecture",
        description=tool_texts.describe_architecture.description_text,
        annotations=READ_ONLY,
    )
    async def describe_architecture(ctx: Context) -> exposed.Description:
        return backend.describe(client_name(ctx))  # type: ignore[return-value]

    return server


def result(text: str, structured: Any) -> CallToolResult:
    """A tool's answer: a readable text and its `structuredContent` (a pydantic model)."""
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=structured.model_dump(mode="json"),
    )


def refused(text: str) -> ToolError:
    """A refusal the client reads as `isError` (busy, index absent, delay)."""
    return ToolError(text)


class ExposedEndpoint:
    """The ASGI application mounted at `PATH`: the guard, then the running server's application.
    `start` and `stop` are called from any thread; the server's manager lives on `loop`."""

    def __init__(self, port: int) -> None:
        self.port = port
        self._app: Any = None
        self._token: str | None = None
        self._ready: asyncio.Event | None = None
        self._stop: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.serving: Future[None] | None = None

    @property
    def running(self) -> bool:
        return self._app is not None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}{PATH}"

    def origins(self) -> list[str]:
        return [f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}"]

    def start(self, server: MCPServer, token: str, loop: asyncio.AbstractEventLoop) -> None:
        """The server's application handed to the endpoint, its manager run on `loop`."""
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[f"127.0.0.1:{self.port}", f"localhost:{self.port}"],
            allowed_origins=self.origins(),
        )
        app = server.streamable_http_app(
            streamable_http_path="/", json_response=True, transport_security=security
        )
        manager = server.session_manager
        ready, stop = asyncio.Event(), asyncio.Event()

        async def serve() -> None:
            async with manager.run():
                ready.set()
                await stop.wait()

        self._ready, self._stop, self._loop = ready, stop, loop
        self._token = token
        self.serving = asyncio.run_coroutine_threadsafe(serve(), loop)
        self.serving.add_done_callback(lambda f: f.cancelled() or f.exception())  # always read
        self._app = app

    def stop(self) -> Future[None] | None:
        """The flag falls at once (404 from now on); the manager's task ends on its loop.
        Returns the task's future (awaited by `aclose`, never waited for from a thread)."""
        stop, loop, serving = self._stop, self._loop, self.serving
        self._app, self._token = None, None
        self._stop, self.serving = None, None
        if stop is not None and loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(stop.set)
            except RuntimeError:  # the loop closed meanwhile
                pass
        return serving

    async def aclose(self, timeout: float = 5.0) -> None:
        """On the loop, at shutdown: the stop, then the manager's end awaited."""
        serving = self.stop()
        if serving is None:
            return
        try:
            await asyncio.wait_for(asyncio.wrap_future(serving), timeout)
        except Exception:  # noqa: BLE001, S110 - a manager that ends badly is forgotten
            pass

    def _allowed(self, headers: Headers, token: str) -> int | None:
        origin = headers.get("origin")
        if origin is not None and origin not in self.origins():
            return 403
        given = headers.get("authorization", "")
        scheme, _, value = given.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            value.strip().encode(), token.encode()
        ):
            return 401
        return None

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        app, token, ready = self._app, self._token, self._ready
        if scope["type"] != "http" or app is None or token is None or ready is None:
            await PlainTextResponse("Not Found", status_code=404)(scope, receive, send)
            return
        status = self._allowed(Headers(scope=scope), token)
        if status is not None:
            headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
            text = "Unauthorized" if status == 401 else "Forbidden"
            await PlainTextResponse(text, status_code=status, headers=headers)(scope, receive, send)
            return
        try:
            await asyncio.wait_for(ready.wait(), READY_TIMEOUT_S)
        except TimeoutError:
            await PlainTextResponse("Unavailable", status_code=503)(scope, receive, send)
            return
        # The SDK's application answers on its own path, `/`, whatever the mount.
        inner = dict(scope) | {"path": "/", "raw_path": b"/", "root_path": ""}
        await app(inner, receive, send)
