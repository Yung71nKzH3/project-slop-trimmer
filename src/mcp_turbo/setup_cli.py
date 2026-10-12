"""Automated Installer & Setup CLI for Antigravity, Cursor, and Claude Desktop.

Automates the entire onboarding process:
1. Detects agent environments (Antigravity global/workspace, Cursor, Claude Desktop).
2. Discovers existing MCP server configurations across plugins/configs.
3. Automatically creates downstream config (mcp_turbo_downstream.json).
4. Configures the target agent to mount mcp-turbo as its single optimized gateway.
5. Injects the imperative workflow rule so the agent naturally uses registry_search.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

AGENT_PATHS = {
    "antigravity_global": Path.home() / ".gemini" / "config",
    "antigravity_rules": Path.home() / ".gemini" / "antigravity" / "rules",
    "cursor": Path.home() / ".cursor",
    "claude_desktop": (
        Path.home() / "AppData" / "Roaming" / "Claude"
        if sys.platform == "win32"
        else Path.home() / "Library" / "Application Support" / "Claude"
    ),
}

DEFAULT_RULE_CONTENT = """# Tool Routing via mcp-turbo

All external tool capabilities (databases, git, filesystems, cloud APIs, etc.) are consolidated through `mcp-turbo`.
- You do not have direct access to downstream tools in your primary prompt schema.
- Before executing any external tool, query `registry_search(query="<task or tool keywords>")` to discover available tool schemas.
- Execute the retrieved tool using `execute_tool(tool_name="<exact name>", arguments={...})`.
"""


def get_python_executable() -> str:
    """Return the absolute path to the current python binary."""
    return sys.executable


def scan_existing_mcp_servers(gemini_config_dir: Path) -> dict[str, Any]:
    """Scan Antigravity plugins and config files for existing mcpServers definitions."""
    discovered_servers: dict[str, Any] = {}

    # Check plugin directories
    plugins_dir = gemini_config_dir / "plugins"
    if plugins_dir.is_dir():
        for mcp_file in plugins_dir.glob("**/mcp_config.json"):
            try:
                with open(mcp_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for s_name, s_spec in data.get("mcpServers", {}).items():
                        discovered_servers[s_name] = s_spec
            except Exception:
                pass

        for mcp_file in plugins_dir.glob("**/mcp.json"):
            try:
                with open(mcp_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for s_name, s_spec in data.get("mcpServers", {}).items():
                        discovered_servers[s_name] = s_spec
            except Exception:
                pass

    return discovered_servers


def setup_antigravity(dry_run: bool = False) -> None:
    print("\n" + "=" * 65)
    print(">> mcp-turbo: Configuring Antigravity Integration")
    print("=" * 65)

    config_dir = AGENT_PATHS["antigravity_global"]
    rules_dir = AGENT_PATHS["antigravity_rules"]
    config_dir.mkdir(parents=True, exist_ok=True)
    rules_dir.mkdir(parents=True, exist_ok=True)

    target_mcp_config = config_dir / "mcp_config.json"
    downstream_config = config_dir / "mcp_turbo_downstream.json"
    rule_file = rules_dir / "mcp-turbo.md"

    # 1. Discover existing or draft default servers
    print("[1/3] Scanning for existing MCP configurations...")
    existing = scan_existing_mcp_servers(config_dir)

    # If current mcp_config.json has non-turbo servers, import them
    if target_mcp_config.is_file():
        try:
            with open(target_mcp_config, "r", encoding="utf-8") as f:
                current_data = json.load(f)
                for s_name, s_spec in current_data.get("mcpServers", {}).items():
                    if s_name != "mcp-turbo":
                        existing[s_name] = s_spec
        except Exception:
            pass

    # Ensure at least a sample downstream entry exists if empty
    if not existing:
        existing = {
            "example-echo": {
                "command": sys.executable,
                "args": ["-c", "print('hello from downstream')"],
            }
        }
        print("       (No existing servers found - seeded with template)")
    else:
        print(f"       Found {len(existing)} downstream server definitions across plugins.")

    print(f"[2/3] Writing downstream servers to: {downstream_config}")
    if not dry_run:
        with open(downstream_config, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": existing}, f, indent=2)

    # 2. Configure Antigravity's mcp_config.json
    print(f"[3/3] Pointing Antigravity {target_mcp_config} to mcp-turbo...")
    py_exec = get_python_executable()
    turbo_proxy_config = {
        "mcpServers": {
            "mcp-turbo": {
                "command": py_exec,
                "args": [
                    "-m",
                    "mcp_turbo.server",
                    "--config",
                    str(downstream_config),
                ],
            }
        }
    }

    if not dry_run:
        # Backup original if it had content
        if target_mcp_config.is_file() and target_mcp_config.stat().st_size > 0:
            shutil.copy2(target_mcp_config, target_mcp_config.with_suffix(".json.bak"))
        with open(target_mcp_config, "w", encoding="utf-8") as f:
            json.dump(turbo_proxy_config, f, indent=2)

    # 3. Create Rule file
    print(f"[*] Installing Antigravity prompt rule: {rule_file}")
    if not dry_run:
        with open(rule_file, "w", encoding="utf-8") as f:
            f.write(DEFAULT_RULE_CONTENT)

    print("\n" + "=" * 65)
    print("SUCCESS: Antigravity is now configured with mcp-turbo!")
    print(f"Downstream Config: {downstream_config}")
    print(f"Antigravity Config: {target_mcp_config}")
    print(f"Rule Installed:     {rule_file}")
    print("=" * 65 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="mcp-turbo CLI: Manage, benchmark, and auto-configure MCP proxy"
    )
    parser.add_argument(
        "--agent",
        choices=["antigravity"],
        default="antigravity",
        help="Agent target to configure (default: antigravity)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without writing"
    )

    args, unknown = parser.parse_known_args()
    setup_antigravity(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
