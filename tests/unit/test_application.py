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
