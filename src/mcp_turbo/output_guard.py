"""Output Guard & Truncator module.

Prevents context explosion by intercepting tool execution responses and
sanitizing/truncating large blobs while preserving essential keys and structures.
"""

from __future__ import annotations

import json
from typing import Any


DEFAULT_MAX_CHARS = 6000  # ~1,500 tokens


def truncate_string(val: str, max_chars: int = 500) -> str:
    """Truncate long strings with informative notice."""
    if len(val) <= max_chars:
        return val
    half = max_chars // 2
    omitted = len(val) - max_chars
    return f"{val[:half]}... [TRUNCATED {omitted} chars] ...{val[-half:]}"


def truncate_structure(obj: Any, max_list_items: int = 5, depth: int = 0) -> Any:
    """Summarize list elements and deep structures while preserving shape."""
    if depth > 5:
        return "[MAX DEPTH EXCEEDED]"

    if isinstance(obj, dict):
        return {
            k: truncate_structure(v, max_list_items=max_list_items, depth=depth + 1)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        if len(obj) <= max_list_items:
            return [
                truncate_structure(x, max_list_items=max_list_items, depth=depth + 1)
                for x in obj
            ]
        # Keep top few items and attach summary metadata
        truncated = [
            truncate_structure(x, max_list_items=max_list_items, depth=depth + 1)
            for x in obj[:max_list_items]
        ]
        truncated.append(f"... [{len(obj) - max_list_items} additional items omitted]")
        return truncated
    elif isinstance(obj, str):
        if len(obj) > 600:
            return truncate_string(obj, max_chars=400)
        return obj
    return obj


def sanitize_output(raw_output: Any, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Intercept and constrain tool outputs to prevent context-window bloat."""
    if raw_output is None:
        return ""

    # If output is a string, check if it's JSON
    if isinstance(raw_output, str):
        if len(raw_output) <= max_chars:
            return raw_output
        try:
            parsed = json.loads(raw_output)
            truncated_obj = truncate_structure(parsed)
            res = json.dumps(truncated_obj, indent=2, ensure_ascii=False)
            if len(res) > max_chars:
                return truncate_string(res, max_chars=max_chars)
            return res
        except Exception:
            return truncate_string(raw_output, max_chars=max_chars)

    # If it is a dictionary, list or other data structure
    try:
        truncated_obj = truncate_structure(raw_output)
        res = json.dumps(truncated_obj, indent=2, ensure_ascii=False)
        if len(res) > max_chars:
            return truncate_string(res, max_chars=max_chars)
        return res
    except Exception:
        as_str = str(raw_output)
        return truncate_string(as_str, max_chars=max_chars)
