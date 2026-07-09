"""Tests for ParallelToolExecutor — Parallel tool execution.

Covers:
- Test parallel execution
- Test partial failures
- Test timeout handling
- Test sequential fallback
"""

from __future__ import annotations

import asyncio
import unittest

from backend.services.parallel_tool_executor import (
    ParallelExecutionSummary,
    ParallelToolExecutor,
    ToolResult,
)


async def _mock_tool_success(
    tool_name: str,
    parameters: dict,
    delay: float = 0.01,
) -> list[dict]:
    """Mock tool that succeeds after a delay."""
    await asyncio.sleep(delay)
    return [{"chunk_id": f"{tool_name}-001", "text": f"Result from {tool_name}"}]


async def _mock_tool_failure(tool_name: str, parameters: dict) -> list[dict]:
    """Mock tool that raises an error."""
    raise ValueError(f"Tool {tool_name} failed")


async def _mock_tool_slow(tool_name: str, parameters: dict) -> list[dict]:
    """Mock tool that takes too long."""
    await asyncio.sleep(10)
    return [{"chunk_id": f"{tool_name}-001"}]


async def _mock_tool_empty(tool_name: str, parameters: dict) -> list[dict]:
    """Mock tool that returns empty results."""
    return []


class ToolResultTestCase(unittest.TestCase):
    """Test cases for ToolResult dataclass."""

    def test_succeeded_property(self) -> None:
        """Test succeeded property."""
        result = ToolResult(
            tool_name="test",
            parameters={},
            result=[{"chunk_id": "001"}],
        )
        self.assertTrue(result.succeeded)

    def test_succeeded_property_with_error(self) -> None:
        """Test succeeded property with error."""
        result = ToolResult(
            tool_name="test",
            parameters={},
            result=[],
            error="Some error",
        )
        self.assertFalse(result.succeeded)

    def test_has_results_property(self) -> None:
        """Test has_results property."""
        result = ToolResult(
            tool_name="test",
            parameters={},
            result=[{"chunk_id": "001"}],
        )
        self.assertTrue(result.has_results)

    def test_has_results_property_empty(self) -> None:
        """Test has_results property with empty result."""
        result = ToolResult(
            tool_name="test",
            parameters={},
            result=[],
        )
        self.assertFalse(result.has_results)


class ParallelExecutionSummaryTestCase(unittest.TestCase):
    """Test cases for ParallelExecutionSummary."""

    def test_all_failed_property(self) -> None:
        """Test all_failed property."""
        summary = ParallelExecutionSummary(
            tool_results=[
                ToolResult(tool_name="t1", parameters={}, result=[], error="fail"),
                ToolResult(tool_name="t2", parameters={}, result=[], error="fail"),
            ],
            success_count=0,
            failure_count=2,
        )
        self.assertTrue(summary.all_failed)

    def test_all_failed_property_partial_success(self) -> None:
        """Test all_failed with partial success."""
        summary = ParallelExecutionSummary(
            tool_results=[
                ToolResult(tool_name="t1", parameters={}, result=[{"chunk_id": "001"}]),
                ToolResult(tool_name="t2", parameters={}, result=[], error="fail"),
            ],
            success_count=1,
            failure_count=1,
        )
        self.assertFalse(summary.all_failed)

    def test_all_chunks_property(self) -> None:
        """Test all_chunks property."""
        summary = ParallelExecutionSummary(
            tool_results=[
                ToolResult(
                    tool_name="t1",
                    parameters={},
                    result=[{"chunk_id": "001"}, {"chunk_id": "002"}],
                ),
                ToolResult(
                    tool_name="t2",
                    parameters={},
                    result=[{"chunk_id": "003"}],
                ),
            ],
        )
        chunks = summary.all_chunks
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0]["chunk_id"], "001")
        self.assertEqual(chunks[2]["chunk_id"], "003")


class ParallelToolExecutorTestCase(unittest.TestCase):
    """Test cases for ParallelToolExecutor."""

    def setUp(self) -> None:
        self.executor = ParallelToolExecutor(tool_timeout_seconds=1.0)

    def _run_async(self, coro):
        """Helper to run async coroutines in tests."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    # ------------------------------------------------------------------
    # Parallel execution tests
    # ------------------------------------------------------------------

    def test_execute_parallel_single_tool(self) -> None:
        """Test parallel execution with single tool."""
        tool_map = {
            "search_semantic": _mock_tool_success,
        }
        tool_calls = [
            {"tool": "search_semantic", "parameters": {"query": "test"}},
        ]

        summary = self._run_async(
            self.executor.execute_parallel(tool_calls, tool_map)
        )

        self.assertIsInstance(summary, ParallelExecutionSummary)
        self.assertEqual(len(summary.tool_results), 1)
        self.assertTrue(summary.tool_results[0].succeeded)
        self.assertEqual(summary.parallel_mode, "parallel")

    def test_execute_parallel_multiple_tools(self) -> None:
        """Test parallel execution with multiple tools."""
        tool_map = {
            "search_semantic": _mock_tool_success,
            "search_keyword": _mock_tool_success,
            "get_summary": _mock_tool_success,
        }
        tool_calls = [
            {"tool": "search_semantic", "parameters": {"query": "test"}},
            {"tool": "search_keyword", "parameters": {"keyword": "decision"}},
            {"tool": "get_summary", "parameters": {}},
        ]

        summary = self._run_async(
            self.executor.execute_parallel(tool_calls, tool_map)
        )

        self.assertEqual(len(summary.tool_results), 3)
        self.assertEqual(summary.success_count, 3)
        self.assertEqual(summary.failure_count, 0)

    def test_execute_parallel_empty_calls(self) -> None:
        """Test parallel execution with empty tool calls."""
        summary = self._run_async(
            self.executor.execute_parallel([], {})
        )

        self.assertEqual(len(summary.tool_results), 0)
        self.assertEqual(summary.total_duration_ms, 0)

    # ------------------------------------------------------------------
    # Partial failures tests
    # ------------------------------------------------------------------

    def test_partial_failure(self) -> None:
        """Test partial failures - some tools succeed, some fail."""
        tool_map = {
            "search_semantic": _mock_tool_success,
            "search_keyword": _mock_tool_failure,
        }
        tool_calls = [
            {"tool": "search_semantic", "parameters": {"query": "test"}},
            {"tool": "search_keyword", "parameters": {"keyword": "fail"}},
        ]

        summary = self._run_async(
            self.executor.execute_parallel(tool_calls, tool_map)
        )

        self.assertEqual(len(summary.tool_results), 2)
        self.assertEqual(summary.success_count, 1)
        self.assertEqual(summary.failure_count, 1)
        self.assertTrue(summary.tool_results[0].succeeded)
        self.assertFalse(summary.tool_results[1].succeeded)

    def test_unknown_tool_error(self) -> None:
        """Test handling of unknown tool names."""
        tool_map = {}  # Empty tool map
        tool_calls = [
            {"tool": "nonexistent_tool", "parameters": {}},
        ]

        summary = self._run_async(
            self.executor.execute_parallel(tool_calls, tool_map)
        )

        self.assertEqual(summary.failure_count, 1)
        self.assertIn("Unknown tool", summary.tool_results[0].error)

    # ------------------------------------------------------------------
    # Timeout handling tests
    # ------------------------------------------------------------------

    def test_tool_timeout(self) -> None:
        """Test tool timeout handling."""
        executor = ParallelToolExecutor(tool_timeout_seconds=0.1)
        tool_map = {
            "slow_tool": _mock_tool_slow,
        }
        tool_calls = [
            {"tool": "slow_tool", "parameters": {}},
        ]

        summary = self._run_async(
            executor.execute_parallel(tool_calls, tool_map)
        )

        self.assertEqual(summary.failure_count, 1)
        self.assertEqual(summary.timeout_count, 1)
        self.assertIn("timed out", summary.tool_results[0].error)

    def test_timeout_with_success(self) -> None:
        """Test mix of timeout and success."""
        executor = ParallelToolExecutor(tool_timeout_seconds=0.1)
        tool_map = {
            "fast_tool": _mock_tool_success,
            "slow_tool": _mock_tool_slow,
        }
        tool_calls = [
            {"tool": "fast_tool", "parameters": {}},
            {"tool": "slow_tool", "parameters": {}},
        ]

        summary = self._run_async(
            executor.execute_parallel(tool_calls, tool_map)
        )

        self.assertEqual(summary.success_count, 1)
        self.assertEqual(summary.timeout_count, 1)

    # ------------------------------------------------------------------
    # Sequential fallback tests
    # ------------------------------------------------------------------

    def test_execute_sequential_fallback(self) -> None:
        """Test sequential execution as fallback."""
        tool_map = {
            "search_semantic": _mock_tool_success,
            "search_keyword": _mock_tool_success,
        }
        tool_calls = [
            {"tool": "search_semantic", "parameters": {"query": "test"}},
            {"tool": "search_keyword", "parameters": {"keyword": "test"}},
        ]

        summary = self._run_async(
            self.executor._execute_sequential(tool_calls, tool_map)
        )

        self.assertEqual(summary.parallel_mode, "sequential")
        self.assertEqual(summary.success_count, 2)

    def test_execute_sequential_with_failure(self) -> None:
        """Test sequential execution with failures."""
        tool_map = {
            "search_semantic": _mock_tool_success,
            "search_keyword": _mock_tool_failure,
        }
        tool_calls = [
            {"tool": "search_semantic", "parameters": {"query": "test"}},
            {"tool": "search_keyword", "parameters": {"keyword": "fail"}},
        ]

        summary = self._run_async(
            self.executor._execute_sequential(tool_calls, tool_map)
        )

        self.assertEqual(summary.success_count, 1)
        self.assertEqual(summary.failure_count, 1)

    def test_execute_method_with_all_failed_retries_sequential(self) -> None:
        """Test that execute retries sequentially when all parallel fail."""
        tool_map = {
            "fail_tool": _mock_tool_failure,
        }
        tool_calls = [
            {"tool": "fail_tool", "parameters": {}},
        ]

        summary = self._run_async(
            self.executor.execute(tool_calls, tool_map)
        )

        # Should have tried parallel, then sequential
        self.assertEqual(summary.failure_count, 1)

    def test_execute_method_parallel_success_no_retry(self) -> None:
        """Test that execute doesn't retry when parallel succeeds."""
        tool_map = {
            "success_tool": _mock_tool_success,
        }
        tool_calls = [
            {"tool": "success_tool", "parameters": {}},
        ]

        summary = self._run_async(
            self.executor.execute(tool_calls, tool_map)
        )

        self.assertEqual(summary.parallel_mode, "parallel")
        self.assertEqual(summary.success_count, 1)

    def test_execute_empty_calls(self) -> None:
        """Test execute with empty calls."""
        summary = self._run_async(
            self.executor.execute([], {})
        )

        self.assertEqual(summary.total_duration_ms, 0)


if __name__ == "__main__":
    unittest.main()
