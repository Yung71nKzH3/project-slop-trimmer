# mcp-turbo (mcp-proxy) ⚡

> The lightweight, high-performance local proxy gateway for Model Context Protocol (MCP) and Agent Skills.
> **Eliminates 98%+ of prompt context-window bloat** across Antigravity, Cursor, and Claude Desktop.

---

## 🎯 The Problem

When you mount multiple MCP servers (Postgres, Git, Filesystem, Cloud APIs) and install domain plugins, modern AI agents inject **every single tool schema and skill description** directly into the sys[...]

- **130+ Skills & 25+ Tools** consume **~24,000 tokens** before you even type your first prompt turn.
- In Antigravity, this directly exceeds the **20,000 Customization Token Budget**, causing the IDE to warn:  
  `⚠️ Customization token budget exceeded. Large customizations are excluded from context.`
- High costs, sluggish responses, attention degradation, and dropped capabilities.

---

## 🚀 The Solution

`mcp-turbo` sits between your agent and your tools/skills, exposing **only 4 lean meta-tools**:

1. `registry_search(query: str, limit: int = 3)`: Fast BM25 keyword search over all downstream tool schemas. Returns minified, stripped schemas on demand.
2. `execute_tool(tool_name: str, arguments: dict)`: Routes execution over persistent `stdio` or `SSE` pipes to child servers, sanitizing outputs via Output Guard.
3. `skill_search(query: str, limit: int = 3)`: Instant BM25 search over all 130+ installed runbooks and skills.
4. `load_skill(skill_name: str)`: Pulls complete markdown instructions into context only when needed.

```
┌─────────────────────────────────────────────────────────────────��[...]
│                           AI AGENT                              │
│              (Sees ONLY 4 Meta-Tools in Prompt)                 │
└────────────────────────────────┬────────────────────────────────��[...]
                                 │
                   stdio JSON-RPC (4 Meta-Tools)
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────��[...]
│                           mcp-turbo                             │
│  ├─ Dynamic Plugin Auto-Discovery (zero-maintenance setup)      │
│  ├─ Schema Minifier (-78% schema token weight)                  │
│  ├─ Output Guard (Truncates massive blobs <= 6k chars)          │
│  ├─ In-Memory BM25 Registry (Tools + 130+ Skills)               │
│  ├─ Idempotent LRU Output Cache (Sub-ms repeated queries)       │
│  └─ Dynamic Tool Elevation (Promotes high-traffic tools)        │
└────────────┬───────────────────┼────────────────────┬───────────��[...]
             │ stdio             │ stdio              │ SSE / HTTP
             ▼                   ▼                    ▼
     ┌───────────────┐   ┌───────────────┐    ┌───────────────┐
     │    Git MCP    │   │  Postgres MCP │    │  Remote Cloud │
     │  (15 tools)   │   │  (35 tools)   │    │  (30 tools)   │
     └───────────────┘   └───────────────┘    └───────────────┘
```

---

## 📊 Benchmark & Efficiency Results

Tested against a real multi-server environment with 25 enterprise tools and 137 Antigravity plugin skills (`tests/benchmark.py`):

| Category | Vanilla Setup | `mcp-turbo` Gateway | Impact / Savings |
| :--- | :--- | :--- | :--- |
| **Downstream Tools** | 25 tools | **2 meta-tools** | **-92% tool count** |
| **Installed Skills in Prompt** | 137 skills | **2 on-demand tools** | Kept in BM25 registry |
| **Tool Schema Tokens** | ~8,900 tokens | **~220 tokens** | **97.5% reduction** |
| **Skill Catalog Tokens** | ~14,694 tokens | **~118 tokens** | **99.2% reduction** |
| **Total Prompt Tokens** | **~23,594 tokens** | **~338 tokens** | 🔥 **98.6% TOTAL SAVINGS** |
| **Budget Limit Status** | ❌ **Exceeded 20k Budget** (11+ skills dropped) | ✅ **< 2.5% of Budget** | **Zero Exclusions** |
| **Individual Tool Minification**| 949 chars | **203 chars** | **78.6% minified** |
| **Tool Output Protection** | Uncapped blobs (50k+ chars) | **Guarded <= 6,000 chars** | Structural shape preserved |

---

## 📥 Installation Options

Choose whichever installation method fits your setup:

### Option 1: Zero-Dependency Standalone Binary (Recommended)
*No Python installation or virtual environment required.*

1. Download the latest binary for your operating system from [GitHub Releases](https://github.com/your-username/mcp-turbo/releases):
   - **Windows**: `mcp-turbo-windows-x86_64.exe`
   - **macOS (Apple Silicon)**: `mcp-turbo-darwin-arm64`
   - **Linux**: `mcp-turbo-linux-x86_64`
2. Place the binary in your PATH (e.g., `~/.local/bin` or `C:\Program Files\mcp-turbo`).

### Option 2: Via `uvx` / `pipx`
If you already use Python or `uv`:
```bash
# Using uv (fastest)
uv tool install mcp-turbo

# Using pipx
pipx install mcp-turbo
```

### Option 3: From Source (Development)
```bash
git clone https://github.com/Yung71nKzH3/project-slop-trimmer.git
cd project-slop-trimmer
uv venv
source .venv/bin/activate  # or .\.venv\Scripts\activate on Windows
uv pip install -e .
```

---

## ⚡ 1-Click Agent Setup

Run the automated onboarding command:

```bash
# If installed via binary or pip/uv:
mcp-turbo-setup

# Or directly from source:
python -m mcp_turbo.setup_cli
```

### What this command does:
1. **Auto-Discovers All Downstream Servers**: Scans Antigravity plugin folders (`~/.gemini/config/plugins/`) and drafts `mcp_turbo_downstream.json`.
2. **Reconfigures Agent Gateway**: Points `~/.gemini/config/mcp_config.json` to `mcp-turbo`.
3. **Installs Prompt Routing Rules**: Creates `~/.gemini/antigravity/rules/mcp-turbo.md` instructing the model to discover tools and skills on demand.

> **Zero Maintenance**: Once configured, `mcp-turbo` auto-discovers newly installed plugins and tools every time it launches. You **do not** need to re-run setup when installing new skills or plugins!

---

## ⚙️ Manual Configuration

If configuring manually or using Claude Desktop / Cursor:

### Claude Desktop (`claude_desktop_config.json`) / Cursor (`mcp.json`)
```json
{
  "mcpServers": {
    "mcp-turbo": {
      "command": "mcp-turbo",
      "args": ["--config", "/path/to/mcp_turbo_downstream.json"]
    }
  }
}
```

### Downstream Server Configuration (`mcp_turbo_downstream.json`)
Supports both standard `stdio` subprocesses and remote `sse` endpoints:

```json
{
  "mcpServers": {
    "git": {
      "command": "uvx",
      "args": ["mcp-server-git"]
    },
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/db"]
    },
    "remote-api": {
      "url": "https://mcp.internal.company.com/sse",
      "headers": {
        "Authorization": "Bearer YOUR_TOKEN"
      }
    }
  }
}
```

---

## 🧪 Testing & Benchmarks

```bash
# Run unit tests
python -m unittest tests/test_core.py

# Run benchmark harness
python tests/benchmark.py
```

---

## 📜 License

MIT License. Contributions welcome!
