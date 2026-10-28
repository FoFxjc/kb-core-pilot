"""MCP server with the five tools (port of kb service/app.py MCP tools; design §5, §7). Tool descriptions, the server instructions and
the usage rules come from config/mcp.yaml. Tools record their calls with source "mcp" and the session id the client
sends in the X-KB-Session header."""

import json
from functools import cache
from typing import Annotated, Any

import yaml
from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, ImageContent, TextContent
from pydantic import Field

from kb_core.access import scope as access_scope
from kb_core.access.identity import Identity, identify, require_reader
from kb_core.config import current
from kb_core.paths import data_dir
from kb_core.retrieval.browse import browse, render_text
from kb_core.retrieval.concepts import resolve_concept
from kb_core.retrieval.core import ApiError
from kb_core.retrieval.facts import get_metric_series
from kb_core.retrieval.read import read
from kb_core.retrieval.search import search


@cache
def texts() -> dict:
    return yaml.safe_load((data_dir("config") / "mcp.yaml").read_text())


def _desc(tool: str) -> str:
    t = texts()
    return t["tools"][tool] + "\n" + t["rules"]


def _session(ctx: Context | None) -> str | None:
    headers = getattr(getattr(ctx, "request_context", None), "request", None)
    headers = getattr(headers, "headers", None) if headers is not None else None
    return (headers.get("x-kb-session") or None) if headers else None


def _identity(ctx: Context | None) -> Identity:
    """The MCP caller, from the same headers as HTTP (access/identity.py): behind the SSO gateway the gateway's user
    and groups; in auth mode none the client's X-KB-Subject (missing = public). No request (in-process use): the
    settings' mode decides, so a gateway deployment never serves a call without an identity."""
    request = getattr(getattr(ctx, "request_context", None), "request", None)
    headers = getattr(request, "headers", None) if request is not None else None
    settings = current()
    if settings is None:
        raise ApiError("INTERNAL", "settings not loaded")
    who = identify(headers or {}, settings)
    require_reader(who)
    return who


def _clean(**kw) -> dict:
    return {k: v for k, v in kw.items() if v is not None}


def _enum(values: list[str], desc: str) -> Any:
    return Field(default=None, description=desc, json_schema_extra={"enum": values})


def _result(fn, params: dict, ctx: Context | None, text=None) -> CallToolResult:
    try:
        who = _identity(ctx)
        with access_scope.as_user(who.user):
            body = fn(params, source="mcp", session_id=_session(ctx), subject=who.role)
    except ApiError as e:
        body = e.body()
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(body, ensure_ascii=False))],
                              structured_content=body, is_error=True)
    images = []
    for r in body.get("results", []):
        img = r.get("image")
        if img:
            images.append(img)
            r["image"] = {k: v for k, v in img.items() if k != "data_base64"}
    content: list = [TextContent(type="text", text=json.dumps(body, ensure_ascii=False, separators=(",", ":")))]
    if text is not None:
        content.append(TextContent(type="text", text=text(body["results"])))
    content += [ImageContent(type="image", data=i["data_base64"], mime_type=i["mime"]) for i in images]
    return CallToolResult(content=content, structured_content=body)


def build_mcp() -> MCPServer:
    t = texts()
    server = MCPServer(t["server_name"], instructions=t["instructions"] + "\n" + t["rules"])

    @server.tool(name="search", description=_desc("search"))
    def mcp_search(
        query: Annotated[str, Field(description="Question or keywords, 1-200 characters; Chinese or English")],
        lang: Annotated[str | None, _enum(["any", "en", "zh"], "Document language filter, default any")] = None,
        fiscal_years: Annotated[list[int] | None, Field(default=None, description="Report years, e.g. [2025]")] = None,
        doc_ids: Annotated[list[str] | None, Field(default=None, description="Restrict to these documents")] = None,
        section_types: Annotated[list[str] | None, Field(default=None, description="Section types")] = None,
        group_by: Annotated[str | None, _enum(["none", "fiscal_year", "doc_id", "lang", "section_type"],
                                              "Grouping, default none")] = None,
        per_group: Annotated[int | None, Field(default=None, description="Minimum results per group 1-10, default 3")] = None,
        limit: Annotated[int | None, Field(default=None, description="Number of results 1-30, default 10")] = None,
        include_snippet: Annotated[bool | None, Field(default=None, description="Return excerpts, default true")] = None,
        doc_type: Annotated[str | None, Field(default=None, description="Document type, default annual_report")] = None,
        ctx: Context | None = None,
    ) -> CallToolResult:
        return _result(search, _clean(query=query, lang=lang, fiscal_years=fiscal_years, doc_ids=doc_ids,
                                      section_types=section_types, group_by=group_by, per_group=per_group, limit=limit,
                                      include_snippet=include_snippet, doc_type=doc_type), ctx)

    @server.tool(name="browse", description=_desc("browse"))
    def mcp_browse(
        doc_id: Annotated[str, Field(description="Document ID, e.g. as returned by search in source.doc_id")],
        node_id: Annotated[str | None, Field(default=None, description="Expand from this node; default root")] = None,
        depth: Annotated[int | None, Field(default=None, description="Levels to expand 1-6, default 2")] = None,
        tree_source: Annotated[str | None, Field(default=None, description="Tree source, default primary tree")] = None,
        ctx: Context | None = None,
    ) -> CallToolResult:
        return _result(browse, _clean(doc_id=doc_id, node_id=node_id, depth=depth, tree_source=tree_source), ctx,
                       text=render_text)

    @server.tool(name="read", description=_desc("read"))
    def mcp_read(
        node_id: Annotated[str | None, Field(default=None, description="Node ID; either this or doc_id + page_range")] = None,
        doc_id: Annotated[str | None, Field(default=None, description="Document ID, with page_range")] = None,
        page_range: Annotated[list[int] | None, Field(default=None, description="[start, end] physical pages, span <= 5")] = None,
        include_tables: Annotated[bool | None, Field(default=None, description="Include tables, default true")] = None,
        include_images: Annotated[bool | None, Field(default=None, description="Include page images, default false")] = None,
        max_chars: Annotated[int | None, Field(default=None, description="Text budget 5000-60000, default 40000")] = None,
        ctx: Context | None = None,
    ) -> CallToolResult:
        return _result(read, _clean(node_id=node_id, doc_id=doc_id, page_range=page_range, include_tables=include_tables,
                                    include_images=include_images, max_chars=max_chars), ctx)

    @server.tool(name="resolve_concept", description=_desc("resolve_concept"))
    def mcp_resolve_concept(
        term: Annotated[str, Field(description="A term in any language, or a concept_id, 1-100 characters")],
        lang_hint: Annotated[str | None, _enum(["any", "en", "zh"], "Prefer aliases in this language, falling back to "
                                                                    "all languages; default any")] = None,
        limit: Annotated[int | None, Field(default=None, description="Number of results 1-20, default 5")] = None,
        ctx: Context | None = None,
    ) -> CallToolResult:
        return _result(resolve_concept, _clean(term=term, lang_hint=lang_hint, limit=limit), ctx)

    @server.tool(name="get_metric_series", description=_desc("get_metric_series"))
    def mcp_get_metric_series(
        concept_id: Annotated[str, Field(description="Concept ID, e.g. net_profit, cet1_ratio; look it up with "
                                                     "resolve_concept first if needed")],
        fiscal_years: Annotated[list[int] | None, Field(default=None, description="Fiscal years, e.g. [2023, 2024, 2025]; "
                                                                                  "default all available years")] = None,
        basis: Annotated[str | None, _enum(["latest", "original", "both"], "latest: current version (default) / "
                                                                           "original: earliest version / both")] = None,
        with_yoy: Annotated[bool | None, Field(default=None, description="Include year-on-year absolute and percentage "
                                                                         "change, default true")] = None,
        include_obs: Annotated[bool | None, Field(default=None, description="Include every observation supporting the "
                                                                            "version, default false")] = None,
        entity_scope: Annotated[str | None, _enum(["group", "bank"], "Only group scope (group) is available")] = None,
        ctx: Context | None = None,
    ) -> CallToolResult:
        return _result(get_metric_series, _clean(concept_id=concept_id, fiscal_years=fiscal_years, basis=basis,
                                                 with_yoy=with_yoy, include_obs=include_obs,
                                                 entity_scope=entity_scope), ctx)

    return server
