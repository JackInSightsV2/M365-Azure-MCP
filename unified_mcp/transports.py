"""MCP and OpenAPI transport factories around the shared tool application."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any, Dict, Literal, Optional

import mcp.types as types
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server import Server, ServerRequestContext
from mcp.server.caching import CacheableMethod, CacheHint
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route
from starlette.types import ASGIApp

from unified_mcp import __version__
from unified_mcp.application import (
    SERVER_INSTRUCTIONS,
    ToolApplication,
    create_resources,
    create_tools,
    read_resource,
)
from unified_mcp.config import Settings
from unified_mcp.security import HttpSecurityMiddleware

logger = logging.getLogger(__name__)

# The tool and resource surfaces are fixed at startup, so clients on the
# 2026-07-28 specification may cache list and read results across contexts.
CACHE_HINTS: Mapping[CacheableMethod, CacheHint] = {
    "server/discover": CacheHint(ttl_ms=3_600_000, scope="public"),
    "tools/list": CacheHint(ttl_ms=3_600_000, scope="public"),
    "resources/list": CacheHint(ttl_ms=3_600_000, scope="public"),
    "resources/read": CacheHint(ttl_ms=3_600_000, scope="public"),
}

# Headers the 2026-07-28 transport adds for gateways, plus the legacy session header
# still sent by clients on the deprecated handshake era.
MCP_REQUEST_HEADERS = [
    "Authorization",
    "Content-Type",
    "Last-Event-ID",
    "MCP-Protocol-Version",
    "Mcp-Method",
    "Mcp-Name",
    "Mcp-Session-Id",
]


class AzureCliRequest(BaseModel):
    command: str


class AzureCliResponse(BaseModel):
    result: Any


class GraphRequest(BaseModel):
    command: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    data: Optional[Dict[str, Any]] = None


class GraphResponse(BaseModel):
    success: bool = False
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    status_code: Optional[int] = None
    error_details: Any = None
    suggestion: Optional[str] = None
    auth_required: Optional[bool] = None
    verification_uri: Optional[str] = None
    user_code: Optional[str] = None
    expires_in: Optional[int] = None
    instructions: Optional[str] = None

    model_config = {"extra": "allow"}


RequestContext = ServerRequestContext[Dict[str, Any]]


def create_mcp_server(settings: Settings, application: ToolApplication) -> Server[Dict[str, Any]]:
    """Create the protocol server and register transport-independent handlers.

    Handlers are constructor arguments and return whole protocol results, which is
    the SDK v2 shape for the 2026-07-28 specification. One server instance serves
    both that specification and the deprecated handshake era.
    """
    tools = create_tools(settings.graph_api_version)
    resources = create_resources()

    async def handle_list_tools(
        context: RequestContext,
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tools)

    async def handle_call_tool(
        context: RequestContext,
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        result = await application.execute_tool(params.name, params.arguments or {})
        structured = (
            result.payload if isinstance(result.payload, dict) else {"result": result.payload}
        )
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=result.text)],
            structured_content=structured,
            is_error=result.is_error,
        )

    async def handle_list_resources(
        context: RequestContext,
        params: types.PaginatedRequestParams | None,
    ) -> types.ListResourcesResult:
        return types.ListResourcesResult(resources=resources)

    async def handle_read_resource(
        context: RequestContext,
        params: types.ReadResourceRequestParams,
    ) -> types.ReadResourceResult:
        try:
            text = read_resource(params.uri, settings.graph_api_version)
        except ValueError as error:
            # Unknown URIs are a caller mistake, so they are a protocol error rather
            # than resource content. SDK v2 no longer wraps handler exceptions.
            raise MCPError(types.INVALID_PARAMS, str(error)) from error
        return types.ReadResourceResult(
            contents=[
                types.TextResourceContents(
                    uri=params.uri,
                    mime_type="text/markdown",
                    text=text,
                )
            ]
        )

    return Server(
        settings.mcp_server_name,
        version=__version__,
        instructions=SERVER_INSTRUCTIONS,
        cache_hints=CACHE_HINTS,
        on_list_tools=handle_list_tools,
        on_call_tool=handle_call_tool,
        on_list_resources=handle_list_resources,
        on_read_resource=handle_read_resource,
    )


def _api_key(settings: Settings) -> str | None:
    return settings.mcp_api_key.get_secret_value() if settings.mcp_api_key else None


def create_streamable_http_app(settings: Settings, server: Server[Dict[str, Any]]) -> ASGIApp:
    """Create the current MCP Streamable HTTP application.

    Stateless mode is the default because the 2026-07-28 specification carries the
    protocol version, client identity, and capabilities on every request, so requests
    no longer have to reach the instance that served the handshake.
    """
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=settings.mcp_json_response,
        stateless_http=settings.mcp_stateless_http,
        host=settings.mcp_host,
        debug=settings.log_level == "DEBUG",
    )
    cors_app = CORSMiddleware(
        app,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=MCP_REQUEST_HEADERS,
        expose_headers=["Mcp-Session-Id"],
    )
    return HttpSecurityMiddleware(
        cors_app,
        api_key=_api_key(settings),
        allowed_origins=settings.cors_allowed_origins,
    )


def create_sse_app(settings: Settings, server: Server[Dict[str, Any]]) -> ASGIApp:
    """Create the deprecated MCP HTTP+SSE application.

    The 2026-07-28 specification deprecates this transport with a one-year transition
    window. Use streamable-http unless a client cannot speak it yet.
    """
    logger.warning(
        "The sse transport is deprecated by the 2026-07-28 MCP specification; "
        "migrate clients to MCP_TRANSPORT=streamable-http"
    )
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> PlainTextResponse:
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())
        return PlainTextResponse("")

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
        debug=settings.log_level == "DEBUG",
    )
    cors_app = CORSMiddleware(
        app,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=MCP_REQUEST_HEADERS,
    )
    return HttpSecurityMiddleware(
        cors_app,
        api_key=_api_key(settings),
        allowed_origins=settings.cors_allowed_origins,
    )


def create_openapi_app(settings: Settings, application: ToolApplication) -> ASGIApp:
    """Create the REST facade using the same execution core as MCP."""
    app = FastAPI(
        title="Unified Microsoft MCP API",
        description="OpenAPI interface for Azure CLI and Microsoft Graph tools",
        version=__version__,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/health", include_in_schema=False)
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/execute-azure-cli", response_model=AzureCliResponse)
    async def execute_azure_cli(request: AzureCliRequest) -> AzureCliResponse:
        execution = await application.execute_tool(
            "execute_azure_cli_command",
            request.model_dump(),
        )
        payload = execution.payload
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                pass
        return AzureCliResponse(result=payload)

    @app.post("/execute-graph-command", response_model=GraphResponse)
    async def execute_graph_command(request: GraphRequest) -> GraphResponse:
        execution = await application.execute_tool("graph_command", request.model_dump())
        return GraphResponse.model_validate(execution.payload)

    return HttpSecurityMiddleware(
        app,
        api_key=_api_key(settings),
        allowed_origins=settings.cors_allowed_origins,
        public_paths={"/docs", "/openapi.json", "/redoc"},
    )


async def run_transport(
    settings: Settings,
    server: Server[Dict[str, Any]],
    application: ToolApplication,
) -> None:
    """Run the selected transport until shutdown."""
    if settings.mcp_transport == "stdio":
        logger.info("Starting MCP stdio transport")
        async with stdio_server() as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options(),
            )
        return

    if settings.mcp_transport == "streamable-http":
        app = create_streamable_http_app(settings, server)
    elif settings.mcp_transport == "sse":
        app = create_sse_app(settings, server)
    elif settings.mcp_transport == "openapi":
        app = create_openapi_app(settings, application)
    else:
        raise RuntimeError(f"Unsupported MCP transport: {settings.mcp_transport}")

    config = uvicorn.Config(
        app,
        host=settings.mcp_host,
        port=settings.mcp_port,
        log_level=settings.log_level.lower(),
    )
    await uvicorn.Server(config).serve()
