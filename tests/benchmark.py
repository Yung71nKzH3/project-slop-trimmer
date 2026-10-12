"""Benchmark & Test Harness comparing Vanilla MCP schema bloat vs mcp-turbo."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mcp_turbo.client_manager import ClientManager
from mcp_turbo.minifier import dumps_compact, minify_tool_definition
from mcp_turbo.output_guard import sanitize_output


def estimate_tokens(text: str) -> int:
    """Standard approximation: ~4 characters per token."""
    return max(1, len(text) // 4)


async def run_benchmark():
    project_root = Path(__file__).resolve().parent.parent
    mock_server_script = project_root / "tests" / "mock_mcp_server.py"
    config_file = project_root / "tests" / "test_mcp_config.json"

    # Create temporary config
    config_data = {
        "mcpServers": {
            "mock-enterprise": {
                "command": sys.executable,
                "args": [str(mock_server_script)],
            }
        }
    }
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)

    print("=" * 70)
    print(">> Running mcp-turbo Benchmark & Verification Harness")
    print("=" * 70)

    mgr = ClientManager()
    try:
        print("[1/4] Spawning downstream mock server and caching schemas...")
        tool_count = await mgr.initialize(config_file)
        print(f"       -> Discovered {tool_count} downstream enterprise tools.")

        # 1. Measure Vanilla schema weight (all 25 tools in prompt)
        vanilla_tools = [meta.raw_tool for meta in mgr.tool_registry.values()]
        vanilla_json = json.dumps(vanilla_tools, indent=2)
        vanilla_chars = len(vanilla_json)
        vanilla_tokens = estimate_tokens(vanilla_json)

        # 2. Measure mcp-turbo schema weight exposed to agent prompt
        # In mcp-turbo, the agent ONLY sees:
        # registry_search + execute_tool
        proxy_tools_schema = [
            {
                "name": "registry_search",
                "description": "Find and inspect available tools. Call before executing any tool.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Keywords or tool name"},
                        "limit": {"type": "integer", "description": "Max tools to return"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "execute_tool",
                "description": "Execute a tool found via registry_search with arguments.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string", "description": "Exact tool name"},
                        "arguments": {"type": "object", "description": "Tool parameters"},
                    },
                    "required": ["tool_name"],
                },
            },
        ]
        turbo_base_json = json.dumps(proxy_tools_schema, indent=2)
        turbo_base_chars = len(turbo_base_json)
        turbo_base_tokens = estimate_tokens(turbo_base_json)

        # 3. Test on-demand BM25 tool search
        print("\n[2/4] Testing BM25 On-Demand Registry Search...")
        search_query = "git telemetry"
        results = mgr.search_tools(search_query, limit=2)
        minified_results_str = dumps_compact(results)
        print(f"       Query: '{search_query}' -> Found {len(results)} relevant tool(s)")
        print(f"       Sample retrieved schema payload: {minified_results_str[:120]}...")

        # 4. Test tool routing & execution with Output Guard
        print("\n[3/4] Testing Tool Execution & Output Guard Truncation...")
        raw_exec = await mgr.execute_tool("git_tool_1", {"query": "test"})
        raw_char_len = len(raw_exec)
        print(f"       Output Guard truncated output to {raw_char_len} chars (Limit: ~6,000 chars)")
        print(f"       Preview: {raw_exec[:180]}...")

        # Summary Benchmark
        print("\n" + "=" * 70)
        print("TOKEN REDUCTION BENCHMARK RESULTS")
        print("=" * 70)
        reduction_chars = ((vanilla_chars - turbo_base_chars) / vanilla_chars) * 100
        reduction_tokens = ((vanilla_tokens - turbo_base_tokens) / vanilla_tokens) * 100

        print(f"{'Metric':<30} | {'Vanilla Setup (25 Tools)':<25} | {'mcp-turbo (2 Meta-Tools)'}")
        print("-" * 75)
        print(f"{'Active Exposed Tools':<30} | {vanilla_tools.__len__():<25} | 2")
        print(f"{'Prompt Schema Chars':<30} | {vanilla_chars:<25} | {turbo_base_chars}")
        print(f"{'Estimated Schema Tokens':<30} | {vanilla_tokens:<25} | {turbo_base_tokens}")
        print(f"{'Token Bloat Reduction':<30} | {'0%':<25} | {reduction_tokens:.1f}% SAVINGS")
        print("=" * 70)

        # Schema minifier individual gain
        sample_raw = vanilla_tools[0]
        sample_min = minify_tool_definition(sample_raw)
        sample_raw_len = len(json.dumps(sample_raw))
        sample_min_len = len(dumps_compact(sample_min))
        sample_saving = ((sample_raw_len - sample_min_len) / sample_raw_len) * 100
        print(f"[*] Individual Tool Schema Minification: {sample_raw_len} chars -> {sample_min_len} chars ({sample_saving:.1f}% reduction)")
        print("=" * 70)

    finally:
        await mgr.shutdown()
        if config_file.exists():
            config_file.unlink()


def main():
    asyncio.run(run_benchmark())


if __name__ == "__main__":
    main()
