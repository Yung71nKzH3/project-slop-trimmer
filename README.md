# mcp-turbo (mcp-proxy) ⚡

> High-performance zero-dependency local proxy server solving MCP context-window bloat in AI agents (Cursor, Claude Desktop, Antigravity).

---

## 🎯 The Problem

When mounting dozens of MCP servers (Git, Postgres, Slack, Cloud APIs, etc.), modern AI agents ingest **every tool schema** on every prompt turn:
- **80+ tools** consume **15,000+ tokens** before the conversation even begins.
- High token burn, sluggish response times, degraded instruction following, and frequent context-window exhaustion.

## 🚀 The Solution: `mcp-turbo`

`mcp-turbo` sits between your agent and your downstream MCP servers, replacing dozens of tool definitions with **just 2 meta-tools**:

1. **`registry_search(query: str, limit: int = 3)`**: On-demand, in-memory BM25 search over all downstream tool schemas. Returns minified, token-optimized JSON schemas only when relevant.
2. **`execute_tool(tool_name: str, arguments: dict)`**: Asynchronously routes and executes the tool on the target child server over persistent `stdio` pipes, returning sanitized and safely truncated outputs.

```
┌────────────────────────────────────────────────────────┐
│                      AI AGENT                          │
│          (Exposed ONLY 2 Meta-Tools in Prompt)         │
└───────────────────────────┬────────────────────────────┘
                            │
               stdio JSON-RPC (2 Meta-Tools)
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                      mcp-turbo                         │
│  - In-Memory BM25 Tool Registry                        │
│  - Schema Minifier (-78% schema token weight)          │
│  - Output Guard (Truncates lists & keeps JSON shapes)  │
└───────┬───────────────────┼────────────────────┬───────┘
        │ stdio             │ stdio              │ stdio
        ▼                   ▼                    ▼
┌───────────────┐   ┌───────────────┐    ┌───────────────┐
│  Git MCP      │   │  Postgres MCP │    │  Custom API   │
│  (15 tools)   │   │  (35 tools)   │    │  (30 tools)   │
└───────────────┘   └───────────────┘    └───────────────┘
```

---

## 📊 Benchmark & Token Reduction

Tested against a multi-server setup with 25 enterprise tools (`tests/benchmark.py`):

| Metric | Vanilla MCP Setup (25 Tools) | `mcp-turbo` (2 Meta-Tools) | Savings / Impact |
| :--- | :--- | :--- | :--- |
| **Active Tools in Prompt** | 25 tools | **2 meta-tools** | **-92.0% tool count** |
| **Prompt Schema Characters** | 35,602 chars | **923 chars** | **-97.4% size** |
| **Estimated Schema Tokens** | ~8,900 tokens | **~230 tokens** | **🔥 97.4% TOKEN REDUCTION** |
| **Single Tool Schema Size** | 949 chars | **203 chars** | **78.6% minified** |
| **Payload Bloat Protection** | Uncapped JSON blobs | **Auto-Truncated <= 6k chars** | Prevents context overflow |

---

## 🛠️ Architecture

- **`client_manager.py`**:
  - Spawns and manages asynchronous child processes using `mcp.client.stdio.stdio_client`.
  - Discovers tool schemas via `tools/list` during startup.
  - Implements a zero-dependency **BM25 search index** with sub-word tokenization.
- **`minifier.py`**:
  - Recursively strips schema bloat (`$schema`, redundant `title`, `additionalProperties`, verbose markdown).
  - Compacts JSON serialization (`separators=(',', ':')`).
- **`output_guard.py`**:
  - Intercepts tool execution outputs exceeding ~1,500 tokens (6,000 characters).
  - Preserves top list items and structure while truncating internal payload bursts.
- **`server.py`**:
  - FastMCP / MCPServer standard stdio JSON-RPC interface compatible with MCP 1.x and 2.x.

---

## 💻 Installation & Quickstart

```bash
# Clone and install in editable mode
git clone https://github.com/your-username/mcp-turbo.git
cd mcp-turbo
uv venv
source .venv/bin/activate  # or .\.venv\Scripts\activate on Windows
uv pip install -e .
```

### Configuration (`mcp_config.json`)

Configure downstream MCP servers exactly as you would in Cursor or Claude Desktop:

```json
{
  "mcpServers": {
    "git": {
      "command": "uvx",
      "args": ["mcp-server-git"]
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/workspace"]
    }
  }
}
```

### Running the Proxy

```bash
mcp-turbo --config mcp_config.json
```

### Adding to Claude Desktop / Cursor

Add `mcp-turbo` as your single MCP server:

```json
{
  "mcpServers": {
    "mcp-turbo": {
      "command": "mcp-turbo",
      "args": ["--config", "/absolute/path/to/mcp_config.json"]
    }
  }
}
```

---

## 🧪 Running Tests & Benchmarks

```bash
# Run unit tests
python -m unittest discover tests

# Run benchmark harness
python tests/benchmark.py
```
