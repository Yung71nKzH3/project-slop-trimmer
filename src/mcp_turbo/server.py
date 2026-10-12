"""Meta MCP Server exposing on-demand tool & skill search and routing execution."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Support both mcp 2.x (MCPServer) and mcp 1.x (FastMCP)
try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from .client_manager import ClientManager
from .discovery import auto_discover_all_servers, get_default_search_paths
from .minifier import dumps_compact
from .skills import SkillManager

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
        "mcp-turbo is a high-performance proxy routing calls to downstream MCP servers "
        "and caching skills to prevent prompt bloat. Direct downstream tools and skills "
        "are hidden. Use 'registry_search' to discover tool schemas, 'execute_tool' to run them, "
        "and 'skill_search' / 'load_skill' to access workflow runbooks on demand."
    ),
)

client_mgr = ClientManager()
skill_mgr = SkillManager()


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


@mcp_app.tool()
def skill_search(query: str, limit: int = 3) -> str:
    """Search for relevant workflow skills and domain runbooks on demand.

    Solves prompt bloat by keeping 100+ skill guides in an on-demand registry.

    Args:
        query: Topic, language, or workflow (e.g., 'flutter unit test', 'bigquery sql', 'firebase auth').
        limit: Maximum number of skill summaries to return (default 3).

    Returns:
        JSON list of candidate skills with their names and descriptions.
    """
    clean_limit = max(1, min(limit, 5))
    results = skill_mgr.search_skills(query, limit=clean_limit)
    return dumps_compact(results)


@mcp_app.tool()
def load_skill(skill_name: str) -> str:
    """Fetch the full instructions and guidelines for a specific skill into context.

    Call this after identifying a skill name from 'skill_search'.

    Args:
        skill_name: The exact name of the skill (e.g., 'gemini-api-dev', 'dart-add-unit-test').

    Returns:
        The complete markdown instructions for that skill.
    """
    return skill_mgr.get_skill_content(skill_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="mcp-turbo: Zero-bloat MCP & Skills proxy with on-demand search"
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
    logger.info("Initializing mcp-turbo...")

    # 1. Discover and initialize downstream MCP servers (auto-scans plugins + config)
    servers = auto_discover_all_servers(config_path)
    count = await client_mgr.initialize_with_specs(servers)
    logger.info("Loaded %d downstream tools into registry index.", count)

    # 2. Discover and initialize Antigravity Skills
    search_roots = get_default_search_paths()
    skill_count = skill_mgr.discover_skills(search_roots)
    logger.info("Indexed %d skills into on-demand skill registry.", skill_count)

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
