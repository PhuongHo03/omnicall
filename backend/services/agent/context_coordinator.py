"""Context accumulation and metadata coordination for Agentic RAG."""

from typing import Any

from backend.services.agent.context_manager import AgentContextManager
from backend.services.agent.parallel_executor import ParallelExecutionSummary
from backend.services.agent.response_utils import normalize_chunk, to_context_chunk
from backend.services.agent.token_management import TokenBudget, TokenManager


class ContextCoordinator:
    """Apply chunk and token limits while updating the agent context."""

    def __init__(self, *, context_manager: AgentContextManager, token_manager: TokenManager) -> None:
        self.context_manager = context_manager
        self.token_manager = token_manager

    def accumulate(
        self,
        *,
        execution: ParallelExecutionSummary,
        accumulated_context: list[dict[str, Any]],
        seen_chunk_ids: set[str],
        accumulated_tokens: int,
        token_budget: TokenBudget,
    ) -> tuple[int, int]:
        if token_budget.is_exhausted:
            return 0, accumulated_tokens

        added = 0
        for tool_result in execution.tool_results:
            result_chunks = []
            for chunk in tool_result.result:
                normalized = normalize_chunk(chunk)
                chunk_id = normalized.get("chunkId")
                if not chunk_id or chunk_id in seen_chunk_ids:
                    continue
                token_count = self.token_manager.count_tokens(str(normalized.get("text", "")))
                if accumulated_tokens + token_count > token_budget.available:
                    token_budget.used = token_budget.total_limit - token_budget.reserved
                    break
                seen_chunk_ids.add(chunk_id)
                accumulated_context.append(normalized)
                accumulated_tokens += token_count
                added += 1
                result_chunks.append(to_context_chunk(normalized))
            self.context_manager.add_chunks(result_chunks, tool_name=tool_result.tool_name)
            self.context_manager.record_tool_call(
                tool_result.tool_name,
                tool_result.parameters,
                len(tool_result.result),
            )
            token_budget.used = accumulated_tokens
        return added, accumulated_tokens

    def tool_call_summary(self) -> list[dict[str, Any]]:
        return [
            {
                "tool": call.tool_name,
                "arguments": call.arguments,
                "result_count": call.result_count,
            }
            for call in self.context_manager.tool_calls
        ]

    def chunks_for_metadata(self) -> list[dict[str, Any]]:
        return [
            {
                "chunkId": chunk.chunk_id,
                "sourceType": chunk.source_type,
                "sectionType": chunk.section_type,
                "jsonPointer": chunk.metadata.get("jsonPointer", ""),
                "citationIds": chunk.citation_ids,
                "segmentIds": chunk.segment_ids,
                "startMs": chunk.start_ms,
                "endMs": chunk.end_ms,
                "text": chunk.text,
                "score": chunk.score,
                "metadata": chunk.metadata,
            }
            for chunk in self.context_manager.get_chunks_sorted_by_score()
        ]

    def token_summary(self) -> dict[str, Any]:
        token_chunks = self.token_manager.create_token_chunks(self.chunks_for_metadata())
        return self.token_manager.get_token_summary(token_chunks)
