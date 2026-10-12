"""Downstream MCP Process and Registry Manager.

Supports:
- stdio subprocesses and remote SSE/HTTP transports.
- Dynamic tool elevation tracking.
- Idempotent LRU tool output caching.
- On-demand BM25 registry index.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

from .cache import ToolOutputCache
from .elevation import ElevationTracker
from .minifier import dumps_compact, minify_tool_definition
from .output_guard import sanitize_output

logger = logging.getLogger("mcp_turbo.client_manager")


@dataclass
class ToolMeta:
    server_name: str
    tool_name: str
    raw_tool: dict[str, Any]
    minified_tool: dict[str, Any]
    tokens: set[str] = field(default_factory=set)


def tokenize(text: str) -> list[str]:
    """Tokenize query and schema strings into lowercase terms."""
    if not text:
        return []
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    subwords = []
    for word in words:
        subwords.append(word)
        parts = re.findall(r"[a-z]+|[0-9]+|[A-Z][a-z]*", word)
        if len(parts) > 1:
            subwords.extend([p.lower() for p in parts])
    return subwords


class BM25Index:
    """Zero-dependency BM25 search index for tool schemas."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus: list[ToolMeta] = []
        self.doc_lengths: list[int] = []
        self.avg_doc_len: float = 0.0
        self.doc_freqs: dict[str, int] = {}

    def build(self, tools: list[ToolMeta]) -> None:
        self.corpus = tools
        self.doc_lengths = []
        self.doc_freqs = {}
        total_len = 0

        for tool in tools:
            doc_text = f"{tool.tool_name} {tool.raw_tool.get('description', '')}"
            props = (
                tool.raw_tool.get("inputSchema", {}).get("properties", {})
                if isinstance(tool.raw_tool.get("inputSchema"), dict)
                else {}
            )
            if isinstance(props, dict):
                doc_text += " " + " ".join(props.keys())

            tokens = tokenize(doc_text)
            tool.tokens = set(tokens)
            doc_len = len(tokens)
            self.doc_lengths.append(doc_len)
            total_len += doc_len

            for term in tool.tokens:
                self.doc_freqs[term] = self.doc_freqs.get(term, 0) + 1

        self.avg_doc_len = total_len / len(tools) if tools else 1.0

    def search(self, query: str, limit: int = 3) -> list[ToolMeta]:
        if not self.corpus:
            return []

        q_terms = tokenize(query)
        if not q_terms:
            return self.corpus[:limit]

        n_docs = len(self.corpus)
        scores: list[tuple[float, ToolMeta]] = []

        for idx, tool in enumerate(self.corpus):
            score = 0.0
            doc_len = self.doc_lengths[idx]

            tool_name_lower = tool.tool_name.lower()
            query_lower = query.lower()
            if query_lower == tool_name_lower:
                score += 50.0
            elif query_lower in tool_name_lower:
                score += 20.0

            for term in q_terms:
                if term in tool.tokens:
                    df = self.doc_freqs.get(term, 0)
                    idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
                    tf = 1.0
                    denom = tf + self.k1 * (
                        1.0 - self.b + self.b * (doc_len / self.avg_doc_len)
                    )
                    score += idf * ((tf * (self.k1 + 1.0)) / denom)

            if score > 0:
                scores.append((score, tool))

        scores.sort(key=lambda x: x[0], reverse=True)
        return [tool for _, tool in scores[:limit]]


class DownstreamSession:
    """Manages an active connection to an MCP server (stdio or SSE/HTTP)."""

    def __init__(
        self,
        name: str,
        params: StdioServerParameters | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.name = name
        self.params = params
        self.url = url
        self.headers = headers
        self._cm: Any = None
        self._session_cm: Any = None
        self.session: ClientSession | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> list[dict[str, Any]]:
        """Launch process or connect to SSE endpoint."""
        if self.url:
            # Connect via SSE transport
            self._cm = sse_client(self.url, headers=self.headers)
            read_stream, write_stream = await self._cm.__aenter__()
        elif self.params:
            # Connect via stdio transport
            self._cm = stdio_client(self.params)
            read_stream, write_stream = await self._cm.__aenter__()
        else:
            raise ValueError(f"Server '{self.name}' must specify stdio params or url")

        self._session_cm = ClientSession(read_stream, write_stream)
        self.session = await self._session_cm.__aenter__()
        await self.session.initialize()

        # Fetch tools
        response = await self.session.list_tools()
        tools_list = []
        for t in response.tools:
            if hasattr(t, "model_dump"):
                tools_list.append(t.model_dump())
            elif isinstance(t, dict):
                tools_list.append(t)
            else:
                tools_list.append({
                    "name": getattr(t, "name", ""),
                    "description": getattr(t, "description", ""),
                    "inputSchema": getattr(t, "inputSchema", {}),
                })
        return tools_list

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None) -> Any:
        if not self.session:
            raise RuntimeError(f"Server '{self.name}' session is not started.")
        async with self._lock:
            result = await self.session.call_tool(tool_name, arguments or {})
            if hasattr(result, "content"):
                content_parts = []
                for item in result.content:
                    if hasattr(item, "text"):
                        content_parts.append(item.text)
                    elif isinstance(item, dict) and "text" in item:
                        content_parts.append(item["text"])
                    else:
                        content_parts.append(str(item))
                return "\n".join(content_parts)
            return result

    async def close(self) -> None:
        try:
            if self._session_cm:
                await self._session_cm.__aexit__(None, None, None)
        except Exception as e:
            logger.debug("Error closing session %s: %s", self.name, e)
        try:
            if self._cm:
                await self._cm.__aexit__(None, None, None)
        except Exception as e:
            logger.debug("Error closing client transport %s: %s", self.name, e)


class ClientManager:
    """Coordinates downstream MCP processes, caching, elevation, and search."""

    def __init__(self):
        self.sessions: dict[str, DownstreamSession] = {}
        self.tool_registry: dict[str, ToolMeta] = {}
        self.index = BM25Index()
        self.cache = ToolOutputCache()
        self.elevation = ElevationTracker(elevation_threshold=2)

    def load_config(self, config_path: str | Path) -> dict[str, dict[str, Any]]:
        path = Path(config_path)
        if not path.is_file():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        servers_dict = data.get("mcpServers", {})
        parsed: dict[str, dict[str, Any]] = {}

        for name, spec in servers_dict.items():
            if "url" in spec:
                parsed[name] = {
                    "type": "sse",
                    "url": spec["url"],
                    "headers": spec.get("headers"),
                }
            else:
                command = spec.get("command")
                args = spec.get("args", [])
                env = spec.get("env")
                merged_env = None
                if env:
                    merged_env = {**os.environ, **env}

                parsed[name] = {
                    "type": "stdio",
                    "params": StdioServerParameters(
                        command=command,
                        args=args,
                        env=merged_env,
                    ),
                }

        return parsed

    async def initialize(self, config_path: str | Path) -> int:
        """Start all configured servers and build search registry."""
        server_configs = self.load_config(config_path)
        all_tools: list[ToolMeta] = []

        for name, spec in server_configs.items():
            try:
                if spec["type"] == "sse":
                    session = DownstreamSession(name, url=spec["url"], headers=spec.get("headers"))
                else:
                    session = DownstreamSession(name, params=spec["params"])

                tools_list = await session.start()
                self.sessions[name] = session

                for tool_raw in tools_list:
                    tool_name = tool_raw.get("name", "")
                    minified = minify_tool_definition(tool_raw)
                    meta = ToolMeta(
                        server_name=name,
                        tool_name=tool_name,
                        raw_tool=tool_raw,
                        minified_tool=minified,
                    )
                    self.tool_registry[tool_name] = meta
                    all_tools.append(meta)
                logger.info("Connected downstream server '%s' (%d tools)", name, len(tools_list))
            except Exception as e:
                logger.error("Failed to initialize server '%s': %s", name, e)

        self.index.build(all_tools)
        return len(all_tools)

    def search_tools(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """Search tools and return compact minified tool schemas."""
        matched_metas = self.index.search(query, limit=limit)
        results = []
        for meta in matched_metas:
            tool_dict = dict(meta.minified_tool)
            # Annotate if elevated or cached
            if self.elevation.is_elevated(meta.tool_name):
                tool_dict["elevated"] = True
            results.append(tool_dict)
        return results

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> str:
        """Route tool call with cache inspection, execution, and output sanitization."""
        # 1. Check LRU Cache for read operations
        cached_result = self.cache.get(tool_name, arguments)
        if cached_result is not None:
            logger.info("Cache hit for tool '%s'", tool_name)
            return cached_result

        # 2. Check Registry
        meta = self.tool_registry.get(tool_name)
        if not meta:
            available = ", ".join(list(self.tool_registry.keys())[:10])
            return (
                f"Error: Tool '{tool_name}' not found in registry. "
                f"Did you run registry_search? Available samples: [{available}]"
            )

        session = self.sessions.get(meta.server_name)
        if not session:
            return f"Error: Downstream server '{meta.server_name}' is not reachable."

        # 3. Track Dynamic Elevation
        newly_elevated = self.elevation.record_call(tool_name)
        if newly_elevated:
            logger.info("Tool '%s' promoted to elevated status (frequent usage).", tool_name)

        # 4. Execute tool
        try:
            raw_result = await session.call_tool(tool_name, arguments or {})
            sanitized = sanitize_output(raw_result)

            # 5. Populate Cache if cacheable
            self.cache.set(tool_name, arguments, sanitized)
            return sanitized
        except Exception as e:
            return f"Execution error on '{tool_name}': {type(e).__name__}: {str(e)}"

    async def shutdown(self) -> None:
        """Terminate all downstream sessions."""
        for name, session in self.sessions.items():
            await session.close()
        self.sessions.clear()
        self.tool_registry.clear()
        self.cache.invalidate()
        self.elevation.reset()
