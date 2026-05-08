"""MCP client and tool adapter support."""

from cognix.mcp.adapter import attach_workspace_mcp_tools, mcp_server_to_core_tools
from cognix.mcp.client import MCPClient, MCPToolSpec

__all__ = [
    "MCPClient",
    "MCPToolSpec",
    "attach_workspace_mcp_tools",
    "mcp_server_to_core_tools",
]
