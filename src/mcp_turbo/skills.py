"""Skill Registry and On-Demand Provider for Antigravity & Agent Workflows.

Solves the 23,000+ token skill bloat caused by mounting 100+ SKILL.md summaries
into the system prompt. Instead of all skill headers being loaded by default,
SkillManager discovers, parses, and indexes skills with BM25, exposing them
on demand.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .client_manager import BM25Index, ToolMeta, tokenize
from .minifier import minify_text

logger = logging.getLogger("mcp_turbo.skills")


@dataclass
class SkillMeta:
    name: str
    description: str
    path: str
    content: str
    tokens: set[str] = field(default_factory=set)


class SkillManager:
    """Discovers, parses, and indexes SKILL.md files from Antigravity and plugins."""

    def __init__(self):
        self.skills: dict[str, SkillMeta] = {}
        self.doc_lengths: list[int] = []
        self.doc_freqs: dict[str, int] = {}
        self.avg_doc_len: float = 0.0

    def parse_skill_file(self, file_path: Path) -> SkillMeta | None:
        """Parse YAML frontmatter and markdown body from SKILL.md."""
        try:
            raw_text = file_path.read_text(encoding="utf-8", errors="replace")
            # Extract frontmatter between --- and ---
            match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw_text, re.DOTALL)
            name = file_path.parent.name
            description = ""
            content = raw_text

            if match:
                frontmatter_raw, content = match.groups()
                # Parse simple YAML lines
                name_match = re.search(r"^name:\s*(.+)$", frontmatter_raw, re.MULTILINE)
                if name_match:
                    name = name_match.group(1).strip().strip("'\"")

                desc_match = re.search(
                    r"^description:\s*(?:>-\s*|\|-\s*)?(.*?)(?=\n[a-zA-Z0-9_-]+:|\Z)",
                    frontmatter_raw,
                    re.MULTILINE | re.DOTALL,
                )
                if desc_match:
                    description = desc_match.group(1).strip().replace("\n", " ")

            return SkillMeta(
                name=name,
                description=description,
                path=str(file_path),
                content=content.strip(),
            )
        except Exception as e:
            logger.debug("Failed to parse skill file %s: %s", file_path, e)
            return None

    def discover_skills(self, search_roots: list[Path]) -> int:
        """Walk candidate directories for SKILL.md files and index them."""
        self.skills.clear()
        total_len = 0
        items: list[SkillMeta] = []

        for root in search_roots:
            if not root.is_dir():
                continue
            for skill_path in root.glob("**/SKILL.md"):
                parsed = self.parse_skill_file(skill_path)
                if parsed and parsed.name:
                    self.skills[parsed.name] = parsed
                    items.append(parsed)

        # Build BM25 index over skills
        self.doc_lengths = []
        self.doc_freqs = {}

        for skill in items:
            doc_text = f"{skill.name} {skill.description}"
            tokens = tokenize(doc_text)
            skill.tokens = set(tokens)
            doc_len = len(tokens)
            self.doc_lengths.append(doc_len)
            total_len += doc_len

            for term in skill.tokens:
                self.doc_freqs[term] = self.doc_freqs.get(term, 0) + 1

        self.avg_doc_len = total_len / len(items) if items else 1.0
        logger.info("Discovered and indexed %d skills across %d roots", len(self.skills), len(search_roots))
        return len(self.skills)

    def search_skills(self, query: str, limit: int = 3) -> list[dict[str, str]]:
        """Find matching skills using BM25 ranking."""
        items = list(self.skills.values())
        if not items:
            return []

        q_terms = tokenize(query)
        if not q_terms:
            return [
                {
                    "name": s.name,
                    "description": minify_text(s.description, max_length=150),
                    "path": s.path,
                }
                for s in items[:limit]
            ]

        n_docs = len(items)
        scores: list[tuple[float, SkillMeta]] = []
        k1 = 1.5
        b = 0.75

        for idx, skill in enumerate(items):
            score = 0.0
            doc_len = self.doc_lengths[idx]

            skill_name_lower = skill.name.lower()
            query_lower = query.lower()
            if query_lower == skill_name_lower:
                score += 50.0
            elif query_lower in skill_name_lower:
                score += 20.0

            for term in q_terms:
                if term in skill.tokens:
                    df = self.doc_freqs.get(term, 0)
                    idf = max(0.1, math_log((n_docs - df + 0.5) / (df + 0.5) + 1.0))
                    tf = 1.0
                    denom = tf + k1 * (1.0 - b + b * (doc_len / self.avg_doc_len))
                    score += idf * ((tf * (k1 + 1.0)) / denom)

            if score > 0:
                scores.append((score, skill))

        scores.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "name": s.name,
                "description": minify_text(s.description, max_length=150),
                "path": s.path,
            }
            for _, s in scores[:limit]
        ]

    def get_skill_content(self, skill_name: str) -> str:
        """Fetch full markdown guide for a specific skill on demand."""
        skill = self.skills.get(skill_name)
        if not skill:
            available = ", ".join(list(self.skills.keys())[:10])
            return f"Error: Skill '{skill_name}' not found. Available samples: [{available}]"
        return f"# Skill: {skill.name}\nSource: {skill.path}\n\n{skill.content}"


def math_log(x: float) -> float:
    import math
    return math.log(x)
