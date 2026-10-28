"""HTTP API + MCP (design §7; api-contract §2, §8): the five tools under /v1, admin endpoints, page images and
regions, MCP (streamable HTTP) at /mcp. Binds 127.0.0.1 unless
configured otherwise. `kb-core serve` runs doctor first and refuses to start on any failure or missing index."""

import contextlib
from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse

from urllib.parse import parse_qsl

from starlette.datastructures import Headers

from kb_core.access import scope as access_scope
from kb_core.access.identity import Identity, identify, require_admin, require_reader
from kb_core.config import Settings
from kb_core.retrieval import context
from kb_core.retrieval.browse import browse
from kb_core.retrieval.concepts import resolve_concept
from kb_core.retrieval.core import ApiError
from kb_core.retrieval.facts import get_metric_series
from kb_core.retrieval.read import read, render_image
from kb_core.retrieval.search import search
from kb_core.serve import admin
from kb_core.serve.chat import ChatService
from kb_core.serve.mcp import build_mcp


def _source(request: Request) -> str:
    """X-KB-Source: mcp / chat / eval / ui / http (default http); other values are rejected."""
    value = request.headers.get("x-kb-source") or "http"
    if value not in admin.SOURCES:
        raise ApiError("INVALID_PARAM", f"X-KB-Source must be one of {admin.SOURCES}", param="X-KB-Source",
                       allowed=admin.SOURCES)
    return value


def _identity(request: Request, query: bool = False) -> Identity:
    """The caller (access/identity.py). In auth mode none, X-KB-Subject (and with `query` a `subject` query parameter:
    an <img> tag cannot send headers) picks a demo role; behind the SSO gateway the identity comes from its headers."""
    return identify(request.headers, request.app.state.settings,
                    request.query_params.get("subject") if query else None)


def _subject(request: Request, query: bool = False) -> str | None:
    """The data role a call runs as (None = public, only in auth mode none; a gateway user needs a data role)."""
    who = _identity(request, query)
    require_reader(who)
    return who.role


def _call(fn, request: Request, params: dict) -> dict:
    who = _identity(request)
    require_reader(who)
    with access_scope.as_user(who.user):
        return fn(params, source=_source(request), session_id=request.headers.get("x-kb-session"), subject=who.role)


ADMIN_PREFIX = "/v1/admin/"


class IdentityGate:
    """ASGI middleware (auth mode trusted_header): every request needs a gateway identity before any route or MCP
    runs; /v1/admin/* needs the admin role; data tools and MCP need a data role. Errors use the contract's structure.
    In auth mode none it does nothing (development)."""

    def __init__(self, app, settings: Settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or self.settings.auth_mode == "none":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)              # the same view of the headers as the routes and MCP
        path = scope.get("path", "")
        query = dict(parse_qsl(scope.get("query_string", b"").decode("latin-1")))
        try:
            who = identify(headers, self.settings, query.get("subject"))
            if path.startswith(ADMIN_PREFIX):
                require_admin(who)
            elif path.startswith("/v1/") or path.startswith("/mcp"):
                require_reader(who)
        except ApiError as e:
            response = JSONResponse(e.body(), status_code=e.http_status)
            return await response(scope, receive, send)
        return await self.app(scope, receive, send)


def _read_params(qp) -> dict:
    out: dict = {k: qp[k] for k in ("node_id", "doc_id", "include_tables", "include_images", "max_chars") if k in qp}
    ranges = qp.getlist("page_range")
    if len(ranges) == 1:
        out["page_range"] = ranges[0]              # "98-100" or "98,100"
    elif ranges:
        out["page_range"] = ranges                 # repeated keys (api-contract §3): page_range=98&page_range=100
    return out


def ui_dir() -> Path:
    """The built web app (web/ -> `npm run build`), served at /ui."""
    return Path(__file__).parent / "static"


def _ui_file(path: str) -> Path:
    root = ui_dir().resolve()
    try:
        target = (root / path).resolve()
        found = bool(path) and target.is_relative_to(root) and target.is_file()
    except (ValueError, OSError):                # e.g. a NUL byte in the path
        raise ApiError("NOT_FOUND", f"no UI file {path!r}") from None
    if found:
        return target
    if path.startswith("assets/") or not (root / "index.html").is_file():
        raise ApiError("NOT_FOUND", f"no UI file {path!r}" if (root / "index.html").is_file()
                       else "the UI is not built (cd web && npm run build)")
    return root / "index.html"                 # a client-side route such as /ui/docs/<doc_id>/pages/<n>


def create_app(settings: Settings) -> FastAPI:
    mcp = build_mcp()
    chat = ChatService(settings)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        context.init(settings)
        chat.set_tools(await mcp.list_tools())
        async with mcp.session_manager.run():
            yield
        context.close()

    app = FastAPI(title="kb-core", version="v1", lifespan=lifespan)
    app.state.chat = chat
    app.state.settings = settings
    app.add_middleware(IdentityGate, settings=settings)

    @app.exception_handler(ApiError)
    async def api_error(_request: Request, e: ApiError):
        return JSONResponse(e.body(), status_code=e.http_status)

    # every HTTP-layer error uses the contract's error structure (api-contract §3), not the framework's
    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, e: RequestValidationError):
        problems = [{"loc": list(x.get("loc", [])), "message": x.get("msg")} for x in e.errors()]
        param = next((str(x["loc"][-1]) for x in problems if x["loc"]), None)
        err = ApiError("INVALID_PARAM", "invalid request: " + "; ".join(str(x["message"]) for x in problems),
                       param=param, problems=problems)
        return JSONResponse(err.body(), status_code=err.http_status)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, e: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(e.status_code, "INTERNAL")
        body = {"contract": "v1", "error": {"code": code, "message": str(e.detail), "details": {}}}
        return JSONResponse(body, status_code=e.status_code)

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, e: Exception):
        err = ApiError("INTERNAL", f"internal error: {type(e).__name__}")
        return JSONResponse(err.body(), status_code=err.http_status)

    # sync handlers: ES and Postgres calls block, FastAPI runs them in a thread pool
    @app.post("/v1/search")
    def http_search(request: Request, params: dict = Body(...)):
        return _call(search, request, params)

    @app.post("/v1/resolve_concept")
    def http_resolve_concept(request: Request, params: dict = Body(...)):
        return _call(resolve_concept, request, params)

    @app.post("/v1/get_metric_series")
    def http_get_metric_series(request: Request, params: dict = Body(...)):
        return _call(get_metric_series, request, params)

    @app.get("/v1/docs/{doc_id}/tree")
    def http_browse(doc_id: str, request: Request):
        qp = request.query_params
        return _call(browse, request, {"doc_id": doc_id, **{k: qp[k] for k in ("node_id", "depth", "tree_source")
                                                             if k in qp}})

    @app.get("/v1/read")
    def http_read(request: Request):
        return _call(read, request, _read_params(request.query_params))

    @app.get("/v1/docs/{doc_id}/pages/{page_no}.png")
    def page_png(doc_id: str, page_no: int, request: Request):
        admin.visible_page(doc_id, page_no, _subject(request, query=True))
        return FileResponse(render_image(doc_id, page_no), media_type="image/png")

    @app.get("/v1/docs/{doc_id}/pages/{page_no}/regions")
    def page_regions(doc_id: str, page_no: int, request: Request):
        return admin.page_regions(doc_id, page_no, _subject(request))

    @app.get("/v1/admin/config")
    def admin_config():
        return admin.config(live_chat=chat.enabled, role_picker=settings.auth_mode == "none")

    @app.get("/v1/admin/chat/status")
    def admin_chat_status():
        return chat.status()

    @app.post("/v1/admin/chat")
    async def admin_chat(request: Request, params: dict = Body(...)):
        """Live chat (SSE): validation errors are normal JSON errors; once streaming starts, failures arrive as an
        `error` event followed by `answer`. The chat runs as the caller's identity (behind the gateway: the user's
        data role; in auth mode none: the `subject` in the body)."""
        message = params.get("message")
        who = identify(request.headers, settings, params.get("subject"))
        require_reader(who)
        session_id = await chat.prepare(message, params.get("session_id"), who.role, user=who.user)
        return StreamingResponse(chat.run_turn(message, session_id), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/v1/admin/replays")
    def admin_replays():
        return admin.replays()

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/ui/chat")

    @app.get("/ui")
    @app.get("/ui/{path:path}")
    def ui(path: str = ""):
        return FileResponse(_ui_file(path))

    @app.get("/v1/admin/docs")
    def admin_docs(request: Request):
        return admin.docs(_subject(request))

    @app.post("/v1/admin/import")
    def admin_import(params: dict = Body(...)):
        out = admin.import_packages(params.get("path"))
        context.current().catalog.refresh()
        return out

    @app.get("/v1/admin/runs")
    def admin_runs(doc_id: str | None = None, stage: str | None = None, limit: str | None = None):
        return admin.runs(doc_id, stage, limit)

    @app.get("/v1/admin/traces")
    def admin_traces(request: Request):
        return admin.traces(request.query_params)

    @app.get("/v1/admin/traces/{trace_id}")
    def admin_trace(trace_id: str):
        return admin.trace(trace_id)

    @app.get("/v1/admin/sessions/{session_id}")
    def admin_session(session_id: str):
        return admin.session(session_id)

    @app.get("/v1/admin/evals")
    def admin_evals(kind: str | None = None, limit: str | None = None):
        return admin.evals(kind, limit)

    @app.get("/v1/admin/docs/{doc_id}/nodes")
    def admin_doc_nodes(doc_id: str, request: Request):
        return admin.doc_nodes(doc_id, _subject(request))

    @app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def v1_fallback(path: str, request: Request):
        """Unmatched /v1 requests: METHOD_NOT_ALLOWED when the path exists with other methods, else NOT_FOUND
        (without this the MCP mount at / would answer them in plain text)."""
        allowed = sorted({m for r in app.routes if isinstance(r, APIRoute) and r.endpoint is not v1_fallback
                          and r.path_regex.match(request.url.path) for m in r.methods} - {"HEAD"})
        if allowed:
            raise ApiError("METHOD_NOT_ALLOWED", f"{request.method} is not allowed on {request.url.path}",
                           allowed=allowed)
        raise ApiError("NOT_FOUND", f"no endpoint {request.url.path}")


    # MCP checks the Host header against the bind address (DNS rebinding protection)
    app.mount("/", mcp.streamable_http_app(streamable_http_path="/mcp", host=settings.host))
    return app


def uvicorn_options(settings: Settings) -> dict:
    return {"host": settings.host, "port": settings.port}


def run(settings: Settings) -> None:
    import uvicorn

    uvicorn.run(create_app(settings), **uvicorn_options(settings))
