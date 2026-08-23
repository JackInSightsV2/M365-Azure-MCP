"""Transport-independent tool definitions and execution core."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Protocol

from mcp.types import Resource, TextContent, Tool
from pydantic import AnyUrl, BaseModel, ConfigDict, Field, ValidationError

SERVER_INSTRUCTIONS = (
    "This server connects to the user's Microsoft cloud: Microsoft 365 (also called M365 "
    "or Office 365), Entra ID (Azure AD), and Microsoft Azure. Use it whenever the user "
    "asks about their Microsoft account, tenant, email, calendar, Teams, SharePoint or "
    "OneDrive files, users, groups, licenses, Intune devices, sign-in or audit logs, or "
    "Azure subscriptions and resources — do not answer those from general knowledge when "
    "these tools can fetch the real data.\n\n"
    "- graph_command: Microsoft 365 and Entra ID (Azure AD) via the Microsoft Graph API. "
    "Read or manage users, groups, licenses, mail, calendar, Teams, files, devices, and "
    "directory data. GET reads; POST/PUT/PATCH/DELETE write.\n"
    "- execute_azure_cli_command: Microsoft Azure resources via the Azure CLI (commands "
    "begin with 'az') — subscriptions, resource groups, virtual machines, storage, "
    "networking, costs.\n"
    "- azure_rest_request: the same Azure resources via the Azure Resource Manager REST "
    "API, for when the Azure CLI is unavailable or blocked by Conditional Access.\n\n"
    "Prefer read operations, inspect the help resources before unfamiliar actions, and "
    "never place credentials in tool arguments. Authentication prompts may require the "
    "user to complete a device sign-in and retry."
)


class AzureExecutor(Protocol):
    """Azure execution port shared by real and fake adapters."""

    async def execute_azure_cli(self, command: str) -> str: ...

    async def close(self) -> None: ...


class GraphExecutor(Protocol):
    """Graph execution port shared by real and fake adapters."""

    async def execute_command(
        self,
        command: str,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]: ...

    async def close(self) -> None: ...


class RestExecutor(Protocol):
    """Azure Resource Manager REST port shared by real and fake adapters."""

    async def execute_command(
        self,
        command: str,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]: ...

    async def close(self) -> None: ...


class AzureToolInput(BaseModel):
    """Typed Azure CLI tool input."""

    command: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid")


class GraphToolInput(BaseModel):
    """Typed Microsoft Graph tool input."""

    command: str = Field(min_length=1)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    data: Optional[Dict[str, Any]] = None
    model_config = ConfigDict(extra="forbid")


class AzureRestToolInput(BaseModel):
    """Typed Azure Resource Manager REST tool input."""

    command: str = Field(min_length=1)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    data: Optional[Dict[str, Any]] = None
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ToolExecutionResult:
    """One canonical result consumed by MCP and OpenAPI transports."""

    tool_name: str
    payload: Any
    text: str
    is_error: bool


class ToolApplication:
    """Validate and dispatch every tool call through one typed core."""

    def __init__(
        self,
        azure_service: AzureExecutor | None,
        graph_service: GraphExecutor | None,
        arm_service: RestExecutor | None = None,
    ) -> None:
        self.azure_service = azure_service
        self.graph_service = graph_service
        self.arm_service = arm_service
        self.logger = logging.getLogger(__name__)

    async def execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
    ) -> ToolExecutionResult:
        if name == "execute_azure_cli_command":
            if self.azure_service is None:
                return self._error(name, "Azure CLI service not initialized")
            try:
                request = AzureToolInput.model_validate(arguments)
            except ValidationError as error:
                return self._error(name, self._validation_message(error))
            payload = await self.azure_service.execute_azure_cli(request.command)
            is_error = payload.startswith("Error:") or "\nError:" in payload
            return ToolExecutionResult(name, payload, payload, is_error)

        if name == "azure_rest_request":
            if self.arm_service is None:
                return self._error(name, "Azure REST service not enabled")
            try:
                arm_request = AzureRestToolInput.model_validate(arguments)
            except ValidationError as error:
                return self._error(name, self._validation_message(error))
            arm_payload = await self.arm_service.execute_command(
                arm_request.command,
                arm_request.method,
                arm_request.data,
            )
            return ToolExecutionResult(
                name,
                arm_payload,
                self._format_graph(
                    GraphToolInput(
                        command=arm_request.command,
                        method=arm_request.method,
                        data=arm_request.data,
                    ),
                    arm_payload,
                ),
                not bool(arm_payload.get("success")),
            )

        if name == "graph_command":
            if self.graph_service is None:
                return self._error(name, "Graph service not initialized")
            try:
                graph_request = GraphToolInput.model_validate(arguments)
            except ValidationError as error:
                return self._error(name, self._validation_message(error))
            graph_payload = await self.graph_service.execute_command(
                graph_request.command,
                graph_request.method,
                graph_request.data,
            )
            return ToolExecutionResult(
                name,
                graph_payload,
                self._format_graph(graph_request, graph_payload),
                not bool(graph_payload.get("success")),
            )

        return self._error(name, f"Unknown tool: {name}")

    @staticmethod
    def _validation_message(error: ValidationError) -> str:
        issue = error.errors()[0]
        location = ".".join(str(part) for part in issue["loc"])
        if issue["type"] == "missing":
            return f"Missing {location} argument"
        return f"Invalid {location}: {issue['msg']}"

    @staticmethod
    def _format_graph(request: GraphToolInput, result: Dict[str, Any]) -> str:
        label = f"{request.method.upper()} {request.command}"
        if result.get("success"):
            data = result.get("data")
            rendered = f"```json\n{json.dumps(data, indent=2)}\n```" if data else "Completed."
            return f"Success ({label})\n\n{rendered}"

        text = f"Error ({label})\n\n{result.get('error', 'Unknown error')}"
        if result.get("auth_required") and result.get("instructions"):
            text += f"\n\nInstructions:\n{result['instructions']}"
        if result.get("error_details"):
            details = result["error_details"]
            if not isinstance(details, str):
                details = json.dumps(details, indent=2)
            text += f"\n\nDetails:\n{details}"
        return text

    @staticmethod
    def _error(name: str, message: str) -> ToolExecutionResult:
        text = f"Error: {message}"
        return ToolExecutionResult(name, {"success": False, "error": message}, text, True)

    async def close(self) -> None:
        """Close both adapters, even when the first close fails."""
        errors: list[Exception] = []
        for service in (self.azure_service, self.graph_service, self.arm_service):
            if service is None:
                continue
            try:
                await service.close()
            except Exception as error:
                errors.append(error)
        if errors:
            raise errors[0]


def create_tools() -> list[Tool]:
    """Return the canonical tool schemas exposed by every MCP transport."""
    return [
        Tool(
            name="execute_azure_cli_command",
            description=(
                "Inspect and manage Microsoft Azure resources by running Azure CLI commands "
                "(must begin with 'az'). Use for Azure subscriptions, resource groups, virtual "
                "machines, storage accounts, networking, role assignments, and cost data. "
                "Examples: 'az account show', 'az group list', 'az vm list -o table'. Subject "
                "to the configured execution policy."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "minLength": 1,
                        "description": (
                            "Azure CLI command beginning with 'az', for example "
                            "'az account show' or 'az group list'"
                        ),
                    }
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="azure_rest_request",
            description=(
                "Inspect and manage Microsoft Azure resources through the Azure Resource "
                "Manager REST API (https://management.azure.com), without the Azure CLI. Use "
                "this when the Azure CLI is unavailable or blocked by Conditional Access, or "
                "for ARM endpoints the CLI does not cover — subscriptions, resource groups, "
                "resources, deployments, role assignments, and costs. Include the api-version "
                "query parameter. Example: 'subscriptions?api-version=2022-12-01'. GET reads; "
                "POST/PUT/PATCH/DELETE write."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "minLength": 1,
                        "description": (
                            "Azure Resource Manager path including the api-version query "
                            "parameter, for example 'subscriptions?api-version=2022-12-01'"
                        ),
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                        "default": "GET",
                    },
                    "data": {"type": "object", "description": "Body for write requests"},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="graph_command",
            description=(
                "Connect to the user's Microsoft 365 and Entra ID (Azure AD) via the Microsoft "
                "Graph API — the way to reach their Microsoft account and tenant. Also known "
                "as Microsoft 365, M365, Office 365, Azure AD, or Entra. Read or manage users, "
                "groups, licenses, mail and Outlook, calendar, OneDrive and SharePoint files, "
                "Teams, devices and Intune, and sign-in or audit logs. Provide a Microsoft "
                "Graph v1.0 path and HTTP method (GET reads; POST/PUT/PATCH/DELETE write). "
                "Examples: 'me', 'users', 'users/{id}', 'groups', 'me/messages'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "minLength": 1,
                        "description": (
                            "Microsoft Graph v1.0 path such as 'me', 'users', 'users/{id}', "
                            "'groups', or 'me/messages'"
                        ),
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                        "default": "GET",
                        "description": "GET reads; POST, PUT, PATCH, DELETE write",
                    },
                    "data": {"type": "object", "description": "JSON body for write requests"},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        ),
    ]


def create_resources() -> list[Resource]:
    """Return concise operational help resources."""
    return [
        Resource(
            uri=AnyUrl("azure://help"),
            name="Azure CLI Help",
            description="Authentication, policy, and Azure CLI examples",
            mimeType="text/markdown",
        ),
        Resource(
            uri=AnyUrl("graph://help"),
            name="Microsoft 365 & Entra ID Help",
            description="Users, mail, Teams, groups, licenses, devices — auth, policy, and examples",
            mimeType="text/markdown",
        ),
    ]


def read_resource(uri: AnyUrl) -> str:
    """Read a canonical help resource."""
    if str(uri) == "azure://help":
        return """# Azure CLI tool

Use `execute_azure_cli_command` with a command beginning with `az`.

- Interactive: call `az login` and complete the device flow.
- Automation: configure service-principal credentials or managed identity.
- Policy: `EXECUTION_POLICY` can be `unrestricted`, `read-only`, or `allowlist`.

Examples: `az account show`, `az group list`, `az vm list`.
Commands are parsed without a shell and sensitive flags are redacted from logs.

If the Azure CLI is unavailable or blocked by Conditional Access, use
`azure_rest_request` instead. It calls Azure Resource Manager REST directly and signs
in with a configurable public client (`AZURE_ARM_CLIENT_ID`, Azure PowerShell by
default). Example path: `subscriptions?api-version=2022-12-01`.
"""
    if str(uri) == "graph://help":
        return """# Microsoft 365 and Entra ID tool

Use `graph_command` to reach the user's Microsoft 365 (M365 / Office 365) and Entra ID
(Azure AD) data through the Microsoft Graph API. Give a Graph v1.0 path and a method.

Common paths:
- Signed-in user: `me`, `me/messages`, `me/events`, `me/drive/root/children`
- Directory: `users`, `users/{id}`, `groups`, `groups/{id}/members`
- Licensing: `users/{id}/licenseDetails`, `subscribedSkus`
- Devices/Intune: `deviceManagement/managedDevices`
- Security: `auditLogs/signIns`

The default method is GET; POST, PUT, PATCH, and DELETE require suitable application permissions.

Device-code authentication is used by default. Managed identity and client-secret application
authentication are supported for automation. `EXECUTION_POLICY=read-only` permits only GET.
"""
    raise ValueError(f"Unknown resource: {uri}")


async def process_tool_call(
    name: str,
    arguments: Dict[str, Any],
    azure_service: AzureExecutor | None,
    graph_service: GraphExecutor | None,
    arm_service: RestExecutor | None = None,
) -> List[TextContent]:
    """Compatibility wrapper for callers of the original transport helper."""
    result = await ToolApplication(azure_service, graph_service, arm_service).execute_tool(
        name, arguments
    )
    return [TextContent(type="text", text=result.text)]
