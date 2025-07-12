#!/usr/bin/env python3
"""Unified Microsoft MCP Server - Main entry point."""

import asyncio
import json
import logging
import sys
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource, 
    Tool, 
    TextContent, 
    ImageContent, 
    EmbeddedResource
)

from unified_mcp.config import Settings
from unified_mcp.services.azure_cli_service import AzureCliService
from unified_mcp.services.graph_service import GraphService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('unified_mcp.log'),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)

# Global service instances
azure_cli_service: Optional[AzureCliService] = None
graph_service: Optional[GraphService] = None

def create_azure_cli_tool() -> Tool:
    """Create the Azure CLI command execution tool definition."""
    return Tool(
        name="execute_azure_cli_command",
        description=(
            "Execute Azure CLI commands. This tool allows you to run any Azure CLI command "
            "and get the output. Commands must start with 'az'. For authentication, you can "
            "use 'az login' for device code flow or configure service principal credentials "
            "in environment variables."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "The Azure CLI command to execute. Must start with 'az'. "
                        "Examples: 'az account list', 'az login', 'az group list'"
                    ),
                }
            },
            "required": ["command"],
        },
    )

def create_graph_tool() -> Tool:
    """Create the Microsoft Graph API tool definition."""
    return Tool(
        name="graph_command",
        description="Execute Microsoft Graph API commands. Supports GET, POST, PUT, PATCH, DELETE operations.",
        inputSchema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Graph API endpoint (e.g., 'users', 'me', 'groups', 'devices')"
                },
                "method": {
                    "type": "string", 
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    "default": "GET",
                    "description": "HTTP method to use"
                },
                "data": {
                    "type": "object",
                    "description": "Request body data (for POST, PUT, PATCH operations)"
                },
                "client_secret": {
                    "type": "string",
                    "description": "Azure AD client secret (optional, for authenticated operations)"
                }
            },
            "required": ["command"]
        }
    )

async def main() -> None:
    """Main MCP server entry point."""
    global azure_cli_service, graph_service

    try:
        # Initialize settings and services
        settings = Settings()
        azure_cli_service = AzureCliService(settings)
        graph_service = GraphService(settings)

        # Create MCP server
        server: Server = Server("unified-microsoft-mcp")

        # Register tools
        azure_cli_tool = create_azure_cli_tool()
        graph_tool = create_graph_tool()

        @server.list_tools()  # type: ignore
        async def handle_list_tools() -> List[Tool]:
            """List available tools."""
            return [azure_cli_tool, graph_tool]

        @server.call_tool()  # type: ignore
        async def handle_call_tool(
            name: str, arguments: Dict[str, Any]
        ) -> list[TextContent]:
            """Handle tool execution requests."""
            if name == "execute_azure_cli_command":
                try:
                    # Check if service is initialized
                    if not azure_cli_service:
                        return [TextContent(type="text", text="Error: Azure CLI service not initialized")]

                    # Validate arguments
                    if not arguments or "command" not in arguments:
                        return [TextContent(type="text", text="Error: Missing command argument")]

                    command = arguments["command"]
                    if not isinstance(command, str):
                        return [TextContent(type="text", text="Error: Command must be a string")]

                    logger.info(f"Executing Azure CLI command via MCP: {command}")

                    # Execute the Azure CLI command
                    result = await azure_cli_service.execute_azure_cli(command)
                    return [TextContent(type="text", text=result)]

                except Exception as e:
                    logger.error(f"Error executing Azure CLI command: {e}")
                    return [TextContent(type="text", text=f"Error: {str(e)}")]

            elif name == "graph_command":
                try:
                    # Check if service is initialized
                    if not graph_service:
                        return [TextContent(type="text", text="Error: Graph service not initialized")]

                    command = arguments.get("command", "")
                    method = arguments.get("method", "GET")
                    data = arguments.get("data")
                    client_secret = arguments.get("client_secret")
                    
                    logger.info(f"Executing Graph command: {method} {command}")
                    
                    result = await graph_service.execute_command(command, method, data, client_secret)
                    
                    # Format the response
                    if result.get("success"):
                        response_text = f"✅ **Success** ({method} {command})\n\n"
                        if result.get("data"):
                            response_text += f"```json\n{json.dumps(result['data'], indent=2)}\n```"
                        else:
                            response_text += "Operation completed successfully."
                    else:
                        response_text = f"❌ **Error** ({method} {command})\n\n"
                        response_text += f"**Error:** {result.get('error', 'Unknown error')}\n\n"
                        
                        if result.get("auth_required") and result.get("instructions"):
                            response_text += f"**Instructions:**\n{result['instructions']}\n\n"
                        
                        if result.get("error_details"):
                            response_text += f"**Details:**\n```json\n{json.dumps(result['error_details'], indent=2)}\n```"
                    
                    return [TextContent(type="text", text=response_text)]

                except Exception as e:
                    logger.error(f"Error executing Graph command: {e}")
                    error_text = f"❌ **Graph Tool Execution Failed**\n\n**Error:** {str(e)}"
                    return [TextContent(type="text", text=error_text)]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

        @server.list_resources()  # type: ignore
        async def handle_list_resources() -> List[Resource]:
            """List available resources."""
            return [
                Resource(
                    uri="azure://help",
                    name="Azure CLI Help",
                    description="Help and examples for using Azure CLI commands",
                    mimeType="text/plain"
                ),
                Resource(
                    uri="graph://help",
                    name="Microsoft Graph Help",
                    description="Help and examples for using Microsoft Graph API",
                    mimeType="text/plain"
                )
            ]

        @server.read_resource()  # type: ignore
        async def handle_read_resource(uri: str) -> str:
            """Read a resource."""
            if uri == "azure://help":
                return """
# Azure CLI MCP Help

This tool provides access to Azure CLI commands through MCP.

## Authentication

The Azure CLI tool supports multiple authentication methods:

1. **Device Code Flow (Recommended for interactive use)**
   - Run: `az login`
   - Follow the device code authentication flow
   - Opens browser for authentication

2. **Service Principal (For automated operations)**
   - Set environment variables:
     - `AZURE_TENANT_ID`: Your Azure AD tenant ID
     - `AZURE_CLIENT_ID`: Your service principal client ID
     - `AZURE_CLIENT_SECRET`: Your service principal client secret
     - `AZURE_SUBSCRIPTION_ID`: Your Azure subscription ID (optional)

## Examples

### Login and basic operations
```
execute_azure_cli_command(command="az login")
execute_azure_cli_command(command="az account list")
execute_azure_cli_command(command="az account show")
```

### Resource management
```
execute_azure_cli_command(command="az group list")
execute_azure_cli_command(command="az vm list")
execute_azure_cli_command(command="az storage account list")
```

### Get help
```
execute_azure_cli_command(command="az --help")
execute_azure_cli_command(command="az vm --help")
```

## Security Notes

- Commands are validated to start with 'az'
- Dangerous shell characters are filtered
- All commands are logged for audit purposes
"""

            elif uri == "graph://help":
                return """
# Microsoft Graph MCP Help

This tool provides access to Microsoft Graph API endpoints through MCP.

## Authentication

The Graph tool supports two authentication modes:

1. **Device Code Flow (Recommended for read-only operations)**
   - No client secret required
   - Opens browser for authentication
   - Suitable for user-delegated permissions

2. **Client Secret Flow (For application permissions)**
   - Requires client secret
   - Suitable for automated operations
   - Pass client_secret parameter to the tool

## Configuration

Set these environment variables:
- `CUSTOM_CLIENT_ID`: Your Azure AD application client ID (for read/write mode)
- `CUSTOM_TENANT_ID`: Your Azure AD tenant ID (for read/write mode)
- `CLIENT_SECRET`: Your client secret (optional, for app permissions)

## Examples

### Get current user info
```
graph_command(command="me")
```

### List all users
```
graph_command(command="users")
```

### Get specific user
```
graph_command(command="users/user@domain.com")
```

### Create a user (requires client secret)
```
graph_command(
    command="users", 
    method="POST",
    data={
        "accountEnabled": true,
        "displayName": "John Doe",
        "mailNickname": "johndoe",
        "userPrincipalName": "johndoe@yourdomain.com",
        "passwordProfile": {
            "forceChangePasswordNextSignIn": true,
            "password": "TempPassword123!"
        }
    },
    client_secret="your-client-secret"
)
```

### Update user
```
graph_command(
    command="users/user@domain.com",
    method="PATCH", 
    data={"jobTitle": "Senior Developer"}
)
```

### Delete user
```
graph_command(
    command="users/user@domain.com",
    method="DELETE"
)
```

## Common Endpoints

- `me` - Current user info
- `users` - All users
- `groups` - All groups  
- `devices` - All devices
- `applications` - Applications
- `servicePrincipals` - Service principals
- `directoryRoles` - Directory roles
- `organization` - Organization info

For more endpoints, see: https://docs.microsoft.com/en-us/graph/api/overview
"""
            
            raise ValueError(f"Unknown resource: {uri}")

        logger.info("Starting Unified Microsoft MCP Server...")
        logger.info(f"Available tools: {azure_cli_tool.name}, {graph_tool.name}")
        logger.info(f"Log level: {settings.log_level}")
        logger.info(f"Log file: {settings.log_file}")

        # Run the server with stdio transport
        async with stdio_server() as streams:
            await server.run(
                streams[0],  # read stream
                streams[1],  # write stream
                server.create_initialization_options(),
            )

    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Error in MCP server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 