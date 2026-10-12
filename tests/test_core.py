"""Unit tests for mcp-turbo minifier, output guard, BM25, cache, and elevation."""

import unittest
from mcp_turbo.minifier import minify_schema, minify_tool_definition, dumps_compact
from mcp_turbo.output_guard import sanitize_output
from mcp_turbo.client_manager import BM25Index, ToolMeta
from mcp_turbo.cache import ToolOutputCache
from mcp_turbo.elevation import ElevationTracker


class TestMinifier(unittest.TestCase):
    def test_minify_schema_strips_bloat(self):
        verbose_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "VerboseObjectSchema",
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {
                    "type": "string",
                    "title": "NameTitle",
                    "description": "The user's full name with markdown [link](http://example.com) and **bold** styling.",
                },
                "age": {
                    "type": "integer",
                    "default": 18,
                    "example": 25,
                },
            },
            "required": ["name"],
        }
        minified = minify_schema(verbose_schema)
        self.assertNotIn("$schema", minified)
        self.assertNotIn("title", minified)
        self.assertNotIn("additionalProperties", minified)
        self.assertNotIn("title", minified["properties"]["name"])
        self.assertNotIn("default", minified["properties"]["age"])
        self.assertEqual(minified["required"], ["name"])

    def test_minify_tool_definition(self):
        tool = {
            "name": "super_tool",
            "description": "Does amazing work. ## Section 1\nDetails here...",
            "inputSchema": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
            },
        }
        res = minify_tool_definition(tool)
        self.assertEqual(res["name"], "super_tool")
        compact = dumps_compact(res)
        self.assertNotIn("\n", compact)
        self.assertIn('"name":"super_tool"', compact)


class TestOutputGuard(unittest.TestCase):
    def test_short_output_preserved(self):
        out = "hello world"
        self.assertEqual(sanitize_output(out), "hello world")

    def test_large_list_truncation(self):
        large_data = {
            "status": "ok",
            "items": [{"id": i, "val": f"val_{i}"} for i in range(100)],
        }
        sanitized = sanitize_output(large_data)
        self.assertIn("additional items omitted", sanitized)
        self.assertIn('"id": 0', sanitized)

    def test_massive_string_truncation(self):
        huge_str = "A" * 15000
        sanitized = sanitize_output(huge_str, max_chars=1000)
        self.assertIn("TRUNCATED", sanitized)
        self.assertLessEqual(len(sanitized), 1100)


class TestBM25Index(unittest.TestCase):
    def test_search_matching(self):
        tools = [
            ToolMeta(
                server_name="git",
                tool_name="git_diff",
                raw_tool={"description": "Show git repository differences and commits"},
                minified_tool={"name": "git_diff"},
            ),
            ToolMeta(
                server_name="db",
                tool_name="sql_query",
                raw_tool={"description": "Execute arbitrary SQL query against database"},
                minified_tool={"name": "sql_query"},
            ),
        ]
        index = BM25Index()
        index.build(tools)

        results = index.search("diff commits", limit=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_name, "git_diff")

        results_sql = index.search("database query", limit=1)
        self.assertEqual(len(results_sql), 1)
        self.assertEqual(results_sql[0].tool_name, "sql_query")


class TestCacheAndElevation(unittest.TestCase):
    def test_cache_read_vs_write(self):
        cache = ToolOutputCache()
        self.assertTrue(cache.is_cacheable("get_user_info"))
        self.assertTrue(cache.is_cacheable("search_files"))
        self.assertFalse(cache.is_cacheable("delete_database"))
        self.assertFalse(cache.is_cacheable("create_file"))

        cache.set("get_user_info", {"id": 1}, "cached_result")
        self.assertEqual(cache.get("get_user_info", {"id": 1}), "cached_result")
        self.assertIsNone(cache.get("get_user_info", {"id": 2}))

    def test_elevation_tracker(self):
        tracker = ElevationTracker(elevation_threshold=2)
        self.assertFalse(tracker.is_elevated("git_status"))
        
        # 1st call
        elevated = tracker.record_call("git_status")
        self.assertFalse(elevated)
        self.assertFalse(tracker.is_elevated("git_status"))

        # 2nd call -> triggers elevation
        elevated = tracker.record_call("git_status")
        self.assertTrue(elevated)
        self.assertTrue(tracker.is_elevated("git_status"))
        self.assertIn("git_status", tracker.get_elevated())


if __name__ == "__main__":
    unittest.main()
