"""Dynamic Auto-Discovery module for Antigravity, Cursor, and MCP servers."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from mcp import StdioServerParameters

logger = logging.getLogger("mcp_turbo.discovery")


def get_default_search_paths() -> list[Path]:
    """Return standard search directories for plugins and MCP configurations."""
    home = Path.home()
    paths = [
        home / ".gemini" / "config" / "plugins",
        home / ".gemini" / "config",
        home / ".cursor",
        Path.cwd() / ".agents",
        Path.cwd() / ".agent",
    ]
    return [p for p in paths if p.exists()]


def auto_discover_all_servers(
    explicit_config_path: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Scan both explicit config files AND installed plugin directories automatically."""
    servers: dict[str, dict[str, Any]] = {}

    # 1. First load explicit config if provided and exists
    if explicit_config_path:
        p = Path(explicit_config_path)
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for name, spec in data.get("mcpServers", {}).items():
                        # Don't proxy self
                        if name == "mcp-turbo":
                            continue
                        servers[name] = spec
            except Exception as e:
                logger.warning("Failed to load config %s: %s", p, e)

    # 2. Automatically scan plugins in ~/.gemini/config/plugins
    plugins_dir = Path.home() / ".gemini" / "config" / "plugins"
    if plugins_dir.is_dir():
        for mcp_file in plugins_dir.glob("**/mcp_config.json"):
            try:
                with open(mcp_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for name, spec in data.get("mcpServers", {}).items():
                        if name not in servers and name != "mcp-turbo":
                            servers[name] = spec
            except Exception:
                pass

        for mcp_file in plugins_dir.glob("**/mcp.json"):
            try:
                with open(mcp_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for name, spec in data.get("mcpServers", {}).items():
                        if name not in servers and name != "mcp-turbo":
                            servers[name] = spec
            except Exception:
                pass

    # Normalize parsed server specifications
    normalized: dict[str, dict[str, Any]] = {}
    for name, spec in servers.items():
        if "url" in spec or "serverUrl" in spec:
            url = spec.get("url") or spec.get("serverUrl")
            normalized[name] = {
                "type": "sse",
                "url": url,
                "headers": spec.get("headers"),
            }
        else:
            command = spec.get("command")
            if not command:
                continue
            args = spec.get("args", [])
            env = spec.get("env")
            merged_env = None
            if env:
                merged_env = {**os.environ, **env}

            normalized[name] = {
                "type": "stdio",
                "params": StdioServerParameters(
                    command=command,
                    args=args,
                    env=merged_env,
                ),
            }

    logger.info("Auto-discovery identified %d downstream servers", len(normalized))
    return normalized
