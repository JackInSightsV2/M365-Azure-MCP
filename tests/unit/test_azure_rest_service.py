import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from azure.core.credentials import AccessToken

from unified_mcp.config import Settings
from unified_mcp.execution_policy import ExecutionPolicy, ExecutionPolicyMode
from unified_mcp.services.azure_rest_service import ARM_BASE_URL, AzureRestService


@pytest.fixture
def token_broker():
    broker = MagicMock()
    broker.get_token = AsyncMock(return_value=AccessToken("arm-token", 4_102_444_800))
    broker.close = AsyncMock()
    return broker


@pytest.fixture
def service(token_broker):
    return AzureRestService(Settings(), token_broker=token_broker)


@pytest.mark.asyncio
async def test_execute_command_success(service):
    response = MagicMock(status_code=200)
    response.json.return_value = {"value": [{"subscriptionId": "sub-1"}]}
    client = AsyncMock()
    client.request.return_value = response
    service._get_http_client = MagicMock(return_value=client)

    result = await service.execute_command("subscriptions?api-version=2022-12-01")

    assert result["success"] is True
    assert result["data"]["value"][0]["subscriptionId"] == "sub-1"
    called_url = client.request.await_args.args[1]
    assert called_url == f"{ARM_BASE_URL}subscriptions?api-version=2022-12-01"


@pytest.mark.asyncio
async def test_execute_command_uses_bearer_token(service):
    response = MagicMock(status_code=200)
    response.json.return_value = {}
    client = AsyncMock()
    client.request.return_value = response
    service._get_http_client = MagicMock(return_value=client)

    await service.execute_command("subscriptions?api-version=2022-12-01")

    headers = client.request.await_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer arm-token"


@pytest.mark.asyncio
async def test_execute_command_error(service):
    response = MagicMock(status_code=404)
    response.json.return_value = {"error": {"message": "Not found"}}
    client = AsyncMock()
    client.request.return_value = response
    service._get_http_client = MagicMock(return_value=client)

    result = await service.execute_command("subscriptions/x?api-version=2022-12-01")

    assert result["success"] is False
    assert result["status_code"] == 404
    assert "Not found" in result["error"]


@pytest.mark.asyncio
async def test_empty_command_rejected(service):
    result = await service.execute_command("   ")
    assert result["success"] is False
    assert "path is required" in result["error"]


@pytest.mark.asyncio
async def test_unsupported_method_rejected(service):
    result = await service.execute_command("subscriptions", method="OPTIONS")
    assert result["success"] is False
    assert "Unsupported HTTP method" in result["error"]


@pytest.mark.asyncio
async def test_read_only_policy_denies_writes(token_broker):
    policy = ExecutionPolicy(mode=ExecutionPolicyMode.READ_ONLY)
    service = AzureRestService(Settings(), token_broker=token_broker, policy=policy)

    result = await service.execute_command(
        "subscriptions/x/resourceGroups/rg?api-version=2021-04-01",
        method="PUT",
        data={"location": "eastus"},
    )

    assert result["success"] is False
    assert "policy denied" in result["error"]


@pytest.mark.asyncio
async def test_device_auth_timeout_surfaces_prompt(token_broker):
    service = AzureRestService(Settings(), token_broker=token_broker)
    token_broker.get_token = AsyncMock(side_effect=asyncio.TimeoutError())
    service.device_code_info = {
        "verification_uri": "https://microsoft.com/devicelogin",
        "user_code": "ABC-123",
        "expires_in": 900,
    }

    result = await service.execute_command("subscriptions?api-version=2022-12-01")

    assert result["success"] is False
    assert result["auth_required"] is True
    assert result["user_code"] == "ABC-123"
