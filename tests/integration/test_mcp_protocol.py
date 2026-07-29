"""Protocol round trips against the in-process server, in both supported eras."""

import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS

from unified_mcp.application import ToolApplication
from unified_mcp.config import Settings
from unified_mcp.testing import FakeAzureCliService, FakeGraphService
from unified_mcp.transports import create_mcp_server

# "auto" negotiates the newest specification the SDK serves; "legacy" forces the
# deprecated initialize handshake that older clients still use.
ERAS = ["auto", "legacy"]


def make_server(**overrides):
    settings = Settings(**overrides)
    application = ToolApplication(FakeAzureCliService(), FakeGraphService())
    return create_mcp_server(settings, application)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ERAS)
async def test_tools_are_listed_and_callable_in_both_protocol_eras(mode):
    async with Client(make_server(), mode=mode) as client:
        listing = await client.list_tools()
        result = await client.call_tool("execute_azure_cli_command", {"command": "az group list"})

    assert [tool.name for tool in listing.tools] == [
        "execute_azure_cli_command",
        "graph_command",
    ]
    assert listing.tools[0].input_schema["required"] == ["command"]
    assert result.is_error is False
    assert "rg1" in result.content[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ERAS)
async def test_tool_results_carry_structured_content(mode):
    async with Client(make_server(), mode=mode) as client:
        result = await client.call_tool("graph_command", {"command": "me"})

    assert result.is_error is False
    assert result.structured_content["data"]["displayName"] == "Mock User"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ERAS)
async def test_failed_tool_calls_stay_in_the_result(mode):
    async with Client(make_server(), mode=mode) as client:
        result = await client.call_tool("no_such_tool", {})

    assert result.is_error is True
    assert "Unknown tool" in result.content[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ERAS)
async def test_help_resources_are_listed_and_readable(mode):
    async with Client(make_server(), mode=mode) as client:
        listing = await client.list_resources()
        read = await client.read_resource("graph://help")

    assert [str(resource.uri) for resource in listing.resources] == [
        "azure://help",
        "graph://help",
    ]
    assert "graph_command" in read.contents[0].text


@pytest.mark.asyncio
async def test_list_and_read_results_advertise_cache_hints():
    async with Client(make_server(), mode="auto") as client:
        assert client.protocol_version == "2026-07-28"
        tools = await client.list_tools()
        resources = await client.list_resources()
        read = await client.read_resource("azure://help")

    for result in (tools, resources, read):
        assert result.ttl_ms > 0
        assert result.cache_scope == "public"


@pytest.mark.asyncio
async def test_legacy_clients_receive_no_cache_hints():
    async with Client(make_server(), mode="legacy") as client:
        assert client.protocol_version != "2026-07-28"
        tools = await client.list_tools()

    assert tools.ttl_ms == 0
    assert tools.cache_scope == "private"


@pytest.mark.asyncio
async def test_unknown_resource_is_a_protocol_error():
    async with Client(make_server(), mode="auto") as client:
        with pytest.raises(MCPError) as error:
            await client.read_resource("azure://missing")

    assert error.value.code == INVALID_PARAMS


@pytest.mark.asyncio
async def test_graph_api_version_reaches_the_tool_surface():
    async with Client(make_server(GRAPH_API_VERSION="beta"), mode="auto") as client:
        listing = await client.list_tools()
        read = await client.read_resource("graph://help")

    graph_tool = next(tool for tool in listing.tools if tool.name == "graph_command")
    assert "beta" in graph_tool.description
    assert "`beta`" in read.contents[0].text
