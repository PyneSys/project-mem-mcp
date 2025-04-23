# Project Memory MCP

An MCP Server to store and retrieve project information from memory files. This allows AI agents (like Claude) to maintain persistent memory about projects between conversations.

## Overview

Project Memory MCP provides a simple way to:
- Store project information in Markdown format
- Retrieve project information at the beginning of conversations
- Update project information using patches

The memory is stored in a `MEMORY.md` file in each project directory.

## Installation

### Local installation

#### Prerequisites

- Python 3.11 or higher
- Pip package manager

#### Install from PyPI

```bash
pip install project-mem-mcp
```

#### Install from Source

```bash
git clone https://github.com/your-username/project-mem-mcp.git
cd project-mem-mcp
pip install -e .
```

## Usage

The MCP server is started by the client (e.g., Claude Desktop) based on the configuration you provide. You don't need to start the server manually.

### Integration with Claude Desktop

To use this MCP server with Claude Desktop, you need to add it to your `claude_desktop_config.json` file:

#### Using uvx (Recommended)

This method uses `uvx` (from the `uv` Python package manager) to run the server without permanent installation:

```json
{
  "mcpServers": {
    "project-memory": {
      "command": "uvx",
      "args": [
        "project-mem-mcp",
        "--allowed-dir", "/Users/your-username/projects",
        "--allowed-dir", "/Users/your-username/Documents/code"
      ]
    }
  }
}
```

#### Using pip installed version

If you've installed the package with pip:

```json
{
  "mcpServers": {
    "project-memory": {
      "command": "project-mem-mcp",
      "args": [
        "--allowed-dir", "/Users/your-username/projects",
        "--allowed-dir", "/Users/your-username/Documents/code"
      ]
    }
  }
}
```

### Configuring Claude Desktop

1. Install Claude Desktop from the [official website](https://claude.ai/desktop)
2. Open Claude Desktop
3. From the menu, select Settings → Developer → Edit Config
4. Replace the config with one of the examples above (modify paths as needed)
5. Save and restart Claude Desktop

## Tools

Project Memory MCP provides three tools:

### get_project_memory

Retrieves the entire project memory. Should be used at the beginning of every conversation.

```
get_project_memory(project_path: str) -> str
```

### set_project_memory

Sets the entire project memory. Use when creating a new memory file or when updates fail.

```
set_project_memory(project_path: str, project_info: str)
```

### update_project_memory

Updates the project memory by applying a unified diff/patch. More efficient for small changes.

```
update_project_memory(project_path: str, project_info: str)
```

## Example Workflow

1. Begin a conversation with Claude about a project
2. Claude uses `get_project_memory` to retrieve project information
3. Throughout the conversation, Claude uses `update_project_memory` to persist new information
4. If the update fails, Claude can use `set_project_memory` instead

## Security Considerations

- Memory files should never contain sensitive information
- Project paths are validated against allowed directories
- All file operations are restricted to allowed directories

## Dependencies

- fastmcp (>=2.2.0, <3.0.0)
- patch-ng (>=1.18.0, <2.0.0)

## License

MIT