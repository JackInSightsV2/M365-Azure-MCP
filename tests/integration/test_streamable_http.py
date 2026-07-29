"""Over-the-wire checks for the Streamable HTTP transport."""

import asyncio
import socket
from typing import Any

import httpx2
import pytest
import uvicorn
from mcp import Client
from starlette.types import ASGIApp

from unified_mcp.application import ToolApplication
from unified_mcp.config import Settings
from unified_mcp.testing import FakeAzureCliService, FakeGraphService
from unified_mcp.transports import create_mcp_server, create_streamable_http_app


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def build_endpoint(**overrides: Any) -> tuple[ASGIApp, str, int]:
    """Return the streamable-http app, its MCP URL, and the port it must be served on."""
    port = free_port()
    settings = Settings(MCP_TRANSPORT="streamable-http", MCP_HOST="127.0.0.1", **overrides)
    application = ToolApplication(FakeAzureCliService(), FakeGraphService())
    app = create_streamable_http_app(settings, create_mcp_server(settings, application))
    return app, f"http://127.0.0.1:{port}/mcp", port


class RunningServer:
    """Serve one ASGI app on loopback for the duration of a test."""

    def __init__(self, app: ASGIApp, port: int) -> None:
        self._server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        self._task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "RunningServer":
        self._task = asyncio.create_task(self._server.serve())
        while not self._server.started:
            if self._task.done():
                await self._task
            await asyncio.sleep(0.02)
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self._server.should_exit = True
        assert self._task is not None
        await self._task


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [{}, {"MCP_JSON_RESPONSE": True}, {"MCP_STATELESS_HTTP": False}],
    ids=["stateless-sse", "stateless-json", "sessioned"],
)
async def test_streamable_http_serves_tool_calls(overrides):
    app, url, port = build_endpoint(**overrides)

    async with RunningServer(app, port):
        async with Client(url) as client:
            protocol_version = client.protocol_version
            listing = await client.list_tools()
            result = await client.call_tool("graph_command", {"command": "me"})

    assert protocol_version == "2026-07-28"
    assert [tool.name for tool in listing.tools] == [
        "execute_azure_cli_command",
        "graph_command",
    ]
    assert result.is_error is False
    assert result.structured_content["data"]["displayName"] == "Mock User"


@pytest.mark.asyncio
async def test_streamable_http_rejects_requests_without_the_api_key():
    app, url, port = build_endpoint(MCP_API_KEY="secret")

    async with RunningServer(app, port):
        async with httpx2.AsyncClient() as client:
            response = await client.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "ping"})

    assert response.status_code == 401
