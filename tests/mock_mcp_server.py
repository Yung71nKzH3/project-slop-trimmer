"""Mock MCP Server generating 25+ verbose dummy tools for benchmarking."""

import json

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

app = MCPServer("mock-enterprise-suite")

CATEGORIES = ["database", "git", "cloud", "filesystem", "analytics"]

for cat in CATEGORIES:
    for i in range(1, 6):
        name = f"{cat}_tool_{i}"
        desc = (
            f"Comprehensive enterprise utility for {cat} operation #{i}. "
            f"Performs deep inspection, telemetry logging, auditing, and multi-tenant reconciliation. "
            f"See documentation at https://enterprise.example.com/docs/{cat}/{i} for complete API specifications."
        )

        def make_tool_fn(tool_name: str, tool_desc: str):
            @app.tool(name=tool_name, description=tool_desc)
            def dummy_tool(
                query: str,
                limit: int = 50,
                verbose: bool = False,
                filters: dict | None = None,
            ) -> str:
                # Return verbose enterprise payload
                records = [
                    {
                        "id": f"rec_{j}",
                        "status": "PROCESSED_OK",
                        "attributes": {
                            "category": cat,
                            "index": j,
                            "hash": f"abcdef1234567890_{j}",
                            "metadata": "Extensive verbose enterprise telemetry data recorded during run.",
                        },
                    }
                    for j in range(100)
                ]
                return json.dumps({"status": "success", "count": len(records), "data": records})

            return dummy_tool

        make_tool_fn(name, desc)

if __name__ == "__main__":
    app.run(transport="stdio")
