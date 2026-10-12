"""Minifier module for tool schemas.

Reduces schema token weight by stripping redundant titles, docstrings,
formatting whitespace, and non-essential schema metadata.
"""

from __future__ import annotations

import json
import re
from typing import Any


def minify_text(text: str | None, max_length: int = 200) -> str:
    """Normalize and truncate markdown comments and excessive whitespace."""
    if not text:
        return ""
    # Remove markdown link URLs, keep anchor text: [text](url) -> text
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Strip markdown headers, bold, italics, backticks
    cleaned = re.sub(r"[*_`#>-]", " ", cleaned)
    # Collapse multiple whitespace characters/newlines
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > max_length:
        cleaned = cleaned[: max_length - 3] + "..."
    return cleaned


def minify_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    """Recursively optimize and prune JSON Schema dicts."""
    if not schema or not isinstance(schema, dict):
        return {}

    pruned: dict[str, Any] = {}
    # Fields that add token bloat without execution benefit
    ignored_keys = {
        "$schema",
        "title",
        "additionalProperties",
        "default",
        "examples",
        "example",
    }

    for key, value in schema.items():
        if key in ignored_keys:
            continue
        if key == "description" and isinstance(value, str):
            min_desc = minify_text(value, max_length=120)
            if min_desc:
                pruned[key] = min_desc
        elif key == "properties" and isinstance(value, dict):
            pruned_props = {}
            for prop_name, prop_val in value.items():
                if isinstance(prop_val, dict):
                    pruned_props[prop_name] = minify_schema(prop_val)
                else:
                    pruned_props[prop_name] = prop_val
            pruned[key] = pruned_props
        elif key == "items" and isinstance(value, dict):
            pruned[key] = minify_schema(value)
        elif key in ("anyOf", "allOf", "oneOf") and isinstance(value, list):
            pruned[key] = [
                minify_schema(item) if isinstance(item, dict) else item
                for item in value
            ]
        elif key == "required" and isinstance(value, list):
            if value:
                pruned[key] = value
        else:
            pruned[key] = value

    return pruned


def minify_tool_definition(tool: dict[str, Any]) -> dict[str, Any]:
    """Minify an entire tool object (name, description, inputSchema)."""
    min_tool: dict[str, Any] = {
        "name": tool.get("name", ""),
    }
    desc = tool.get("description")
    if desc:
        min_tool["description"] = minify_text(desc, max_length=160)
    
    input_schema = tool.get("inputSchema")
    if input_schema:
        min_tool["inputSchema"] = minify_schema(input_schema)

    return min_tool


def dumps_compact(data: Any) -> str:
    """Serialize dictionary to ultra-compact single-line JSON."""
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)
