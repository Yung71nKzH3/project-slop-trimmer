"""Dynamic Tool Elevation Tracker.

Tracks usage frequency of tools and identifies high-traffic tools that can be
dynamically promoted or prioritized for direct execution.
"""

from __future__ import annotations

import collections
from typing import Any


class ElevationTracker:
    """Monitors tool calls and determines promotion candidates.

    If an agent accesses a tool >= elevation_threshold times, it gets flagged
    as 'elevated', allowing clients/servers to expose it directly or prioritize it.
    """

    def __init__(self, elevation_threshold: int = 2, max_elevated: int = 5):
        self.elevation_threshold = elevation_threshold
        self.max_elevated = max_elevated
        self.call_counts: collections.Counter[str] = collections.Counter()
        self.elevated_tools: set[str] = set()

    def record_call(self, tool_name: str) -> bool:
        """Record tool invocation. Returns True if this call newly elevated the tool."""
        self.call_counts[tool_name] += 1
        if (
            self.call_counts[tool_name] >= self.elevation_threshold
            and tool_name not in self.elevated_tools
            and len(self.elevated_tools) < self.max_elevated
        ):
            self.elevated_tools.add(tool_name)
            return True
        return False

    def is_elevated(self, tool_name: str) -> bool:
        return tool_name in self.elevated_tools

    def get_elevated(self) -> list[str]:
        return list(self.elevated_tools)

    def demote(self, tool_name: str) -> None:
        self.elevated_tools.discard(tool_name)
        if tool_name in self.call_counts:
            self.call_counts[tool_name] = 0

    def reset(self) -> None:
        self.call_counts.clear()
        self.elevated_tools.clear()
