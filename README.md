# Microsoft 365 & Azure MCP Server

A unified MCP (Model Context Protocol) server that provides access to Microsoft Graph API and Azure CLI through a single Docker container.

## 🚀 Quick Start

### Claude Desktop

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "unified-microsoft-mcp": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--name",
        "unified-microsoft-mcp",
        "-e",
        "LOG_LEVEL=INFO",
        "ghcr.io/jackinsightsv2/m365-azure-mcp:latest"
      ]
    }
  }
}
```

### Cursor

Add this to your `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "unified-microsoft-mcp": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--name",
        "unified-microsoft-mcp",
        "-e",
        "LOG_LEVEL=INFO",
        "ghcr.io/jackinsightsv2/m365-azure-mcp:latest"
      ],
      "env": {}
    }
  }
}
```

### Warp AI

Add this to your Warp MCP configuration:

```json
{
  "unified-microsoft-mcp": {
    "command": "docker",
    "args": [
      "run",
      "--rm",
      "-i",
      "--name",
      "unified-microsoft-mcp",
      "-e",
      "LOG_LEVEL=INFO",
      "ghcr.io/jackinsightsv2/m365-azure-mcp:latest"
    ],
    "env": {},
    "working_directory": null,
    "start_on_launch": true
  }
}
```

The Docker container will be automatically downloaded from GitHub Container Registry.

## 🛠️ Available Tools

### `execute_azure_cli_command`
Execute Azure CLI commands for managing Azure resources. Communicate naturally - ask Claude/Cursor to "list my Azure subscriptions" or "create a resource group called MyRG in East US".

### `graph_command`
Execute Microsoft Graph API commands for managing Microsoft 365 resources. Ask naturally - "show me my profile" or "list all users in my organization".

## 🔐 Authentication & Security

Both tools support two authentication modes with a security layer:

### 1. Interactive Authentication (Default - Most Secure)
When you don't provide credentials in the configuration, the server will prompt you to authenticate through your browser when first using each tool. This keeps your credentials out of configuration files.

### 2. Automated Authentication (Optional)
For automated scenarios, you can provide credentials via environment variables.

## 🔧 Configuration with Credentials (Optional)

If you want to avoid interactive authentication prompts, add environment variables to your MCP configuration:

### Claude Desktop
```json
{
  "mcpServers": {
    "unified-microsoft-mcp": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--name",
        "unified-microsoft-mcp",
        "-e",
        "AZURE_APP_TENANT_ID=your-tenant-id",
        "-e",
        "AZURE_APP_CLIENT_ID=your-client-id",
        "-e",
        "AZURE_APP_CLIENT_SECRET=your-client-secret",
        "-e",
        "GRAPH_APP_CLIENT_ID=your-graph-client-id",
        "-e",
        "GRAPH_APP_TENANT_ID=your-graph-tenant-id",
        "-e",
        "GRAPH_APP_CLIENT_SECRET=your-graph-client-secret",
        "-e",
        "LOG_LEVEL=INFO",
        "ghcr.io/jackinsightsv2/m365-azure-mcp:latest"
      ]
    }
  }
}
```

### Cursor
```json
{
  "mcpServers": {
    "unified-microsoft-mcp": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--name",
        "unified-microsoft-mcp",
        "-e",
        "AZURE_APP_TENANT_ID=your-tenant-id",
        "-e",
        "AZURE_APP_CLIENT_ID=your-client-id",
        "-e",
        "AZURE_APP_CLIENT_SECRET=your-client-secret",
        "-e",
        "GRAPH_APP_CLIENT_ID=your-graph-client-id",
        "-e",
        "GRAPH_APP_TENANT_ID=your-graph-tenant-id",
        "-e",
        "GRAPH_APP_CLIENT_SECRET=your-graph-client-secret",
        "-e",
        "LOG_LEVEL=INFO",
        "ghcr.io/jackinsightsv2/m365-azure-mcp:latest"
      ],
      "env": {}
    }
  }
}
```

### Warp AI
```json
{
  "unified-microsoft-mcp": {
    "command": "docker",
    "args": [
      "run",
      "--rm",
      "-i",
      "--name",
      "unified-microsoft-mcp",
      "-e",
      "AZURE_APP_TENANT_ID=your-tenant-id",
      "-e",
      "AZURE_APP_CLIENT_ID=your-client-id",
      "-e",
      "AZURE_APP_CLIENT_SECRET=your-client-secret",
      "-e",
      "GRAPH_APP_CLIENT_ID=your-graph-client-id",
      "-e",
      "GRAPH_APP_TENANT_ID=your-graph-tenant-id",
      "-e",
      "GRAPH_APP_CLIENT_SECRET=your-graph-client-secret",
      "-e",
      "LOG_LEVEL=INFO",
      "ghcr.io/jackinsightsv2/m365-azure-mcp:latest"
    ],
    "env": {},
    "working_directory": null,
    "start_on_launch": true
  }
}
```

### Environment Variables

#### Azure CLI
- `AZURE_APP_TENANT_ID`: Your Azure AD tenant ID
- `AZURE_APP_CLIENT_ID`: Your service principal client ID  
- `AZURE_APP_CLIENT_SECRET`: Your service principal client secret
- `AZURE_SUBSCRIPTION_ID`: Your Azure subscription ID (optional)

#### Microsoft Graph
- `GRAPH_APP_CLIENT_ID`: Your app registration client ID
- `GRAPH_APP_TENANT_ID`: Your app registration tenant ID
- `GRAPH_APP_CLIENT_SECRET`: Your app registration client secret

## 🔒 Security Best Practice

**Recommended**: Use the default configuration without credentials. The server will securely prompt for authentication when needed, keeping your secrets out of configuration files. Only add credentials to the configuration if you need fully automated operation.

## 📄 License

MIT License 