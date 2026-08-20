import pytest

from unified_mcp.application import ToolApplication, create_tools
from unified_mcp.testing import FakeAzureCliService, FakeAzureRestService, FakeGraphService


def test_create_tools_exposes_azure_rest_request():
    names = {tool.name for tool in create_tools()}
    assert names == {"execute_azure_cli_command", "azure_rest_request", "graph_command"}


@pytest.mark.asyncio
async def test_azure_rest_request_routes_to_arm_service():
    app = ToolApplication(FakeAzureCliService(), FakeGraphService(), FakeAzureRestService())

    result = await app.execute_tool(
        "azure_rest_request",
        {"command": "subscriptions?api-version=2022-12-01"},
    )

    assert result.is_error is False
    assert "Fake Subscription" in result.text


@pytest.mark.asyncio
async def test_azure_rest_request_without_service_is_error():
    app = ToolApplication(FakeAzureCliService(), FakeGraphService(), arm_service=None)

    result = await app.execute_tool("azure_rest_request", {"command": "subscriptions"})

    assert result.is_error is True
    assert "not enabled" in result.text


@pytest.mark.asyncio
async def test_azure_rest_request_validates_command():
    app = ToolApplication(FakeAzureCliService(), FakeGraphService(), FakeAzureRestService())

    result = await app.execute_tool("azure_rest_request", {})

    assert result.is_error is True
    assert "Missing command" in result.text


def test_tool_descriptions_use_intent_keywords():
    """Descriptions must carry the everyday terms users phrase requests in, so the
    model matches intent to a tool instead of answering from general knowledge."""
    tools = {t.name: t.description.lower() for t in create_tools()}

    graph = tools["graph_command"]
    assert "microsoft 365" in graph
    assert "entra" in graph and "azure ad" in graph
    for term in ("users", "mail", "teams", "groups", "licenses"):
        assert term in graph, term

    azure_cli = tools["execute_azure_cli_command"]
    assert "azure" in azure_cli and "subscription" in azure_cli

    arm = tools["azure_rest_request"]
    assert "conditional access" in arm and "resource manager" in arm


def test_server_instructions_signal_microsoft_connection():
    from unified_mcp.application import SERVER_INSTRUCTIONS

    lowered = SERVER_INSTRUCTIONS.lower()
    assert "microsoft 365" in lowered
    assert "entra" in lowered
    # tool names remain present for clients that surface instructions
    assert "graph_command" in SERVER_INSTRUCTIONS
    assert "execute_azure_cli_command" in SERVER_INSTRUCTIONS
