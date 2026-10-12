"""Meta MCP Server exposing on-demand tool search and routing execution."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import Any

# Support both mcp 2.x (MCPServer) and mcp 1.x (FastMCP)
try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from .client_manager import ClientManager
from .minifier import dumps_compact

# Setup stderr logger so stdio protocol on stdout remains pristine
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp_turbo.server")

mcp_app = MCPServer(
    "mcp-turbo",
    instructions=(
        "mcp-turbo is a high-performance proxy routing calls to downstream MCP servers. "
        "Direct downstream tools are hidden to eliminate prompt token bloat. "
        "Always call 'registry_search' first to discover tool schemas, then call 'execute_tool' "
        "with the discovered arguments."
    ),
)

client_mgr = ClientManager()


@mcp_app.tool()
def registry_search(query: str, limit: int = 3) -> str:
    """Find and inspect available tools across connected downstream MCP servers.

    MANDATORY PRE-REQUISITE: You do not have direct access to downstream tools.
    You MUST search for tools using this function first before executing them.

    Args:
        query: Keywords, intent, or tool name to search for (e.g., 'git diff', 'search files', 'postgres query').
        limit: Maximum number of tool definitions to return (default 3, max 10).

    Returns:
        Ultra-compact JSON list of matching tool schemas with parameters and descriptions.
    """
    clean_limit = max(1, min(limit, 10))
    results = client_mgr.search_tools(query, limit=clean_limit)
    if not results:
        return "[]"
    return dumps_compact(results)


@mcp_app.tool()
async def execute_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> str:
    """Execute a downstream tool on its host MCP server and return sanitized output.

    Call this function only after obtaining the tool name and argument schema
    from 'registry_search'.

    Args:
        tool_name: The exact name of the tool discovered via registry_search.
        arguments: The arguments dictionary matching the tool's inputSchema.

    Returns:
        The tool's execution result, safely truncated to prevent context bloat.
    """
    return await client_mgr.execute_tool(tool_name, arguments or {})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="mcp-turbo: Zero-bloat MCP proxy with on-demand tool search"
    )
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=os.environ.get("MCP_CONFIG_PATH", "mcp_config.json"),
        help="Path to mcp_config.json containing mcpServers definitions (default: mcp_config.json)",
    )
    return parser.parse_args()


async def run_server(config_path: str) -> None:
    logger.info("Initializing mcp-turbo with config: %s", config_path)
    count = await client_mgr.initialize(config_path)
    logger.info("Loaded %d downstream tools into registry index.", count)

    try:
        await mcp_app.run_stdio_async()
    finally:
        await client_mgr.shutdown()


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run_server(args.config))
    except KeyboardInterrupt:
        logger.info("Server terminated by user.")
    except Exception as e:
        logger.error("Server failure: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
