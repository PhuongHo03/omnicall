"""Agent context manager for accumulating and managing context in agent loops.

Handles chunk deduplication, context limits, tool call history tracking,
and context formatting for LLM consumption.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ContextChunk:
    """A chunk of context with metadata.

    Attributes:
        chunk_id: Unique identifier for deduplication.
        text: The chunk text content.
        score: Relevance score used for prioritization.
        source_type: Origin of the chunk (e.g., ``transcript``, ``summary``).
        section_type: Structured section type (e.g., ``action_items``).
        citation_ids: Citation identifiers linked to the chunk.
        segment_ids: Transcript segment identifiers.
        start_ms: Start timestamp in milliseconds.
        end_ms: End timestamp in milliseconds.
        metadata: Additional metadata dictionary.
    """
    chunk_id: str
    text: str
    score: float
    source_type: str = ""
    section_type: str = ""
    citation_ids: list[str] = field(default_factory=list)
    segment_ids: list[str] = field(default_factory=list)
    start_ms: int | None = None
    end_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallRecord:
    """Record of a tool call made during agent execution.

    Attributes:
        tool_name: Name of the tool invoked.
        arguments: Arguments passed to the tool.
        result_count: Number of results returned.
        timestamp: Optional epoch timestamp of the call.
    """
    tool_name: str
    arguments: dict[str, Any]
    result_count: int
    timestamp: float | None = None


@dataclass
class AgentContext:
    """Accumulated context for agent loop execution.

    Attributes:
        chunks: Deduplicated context chunks.
        tool_calls: History of tool calls in this session.
        query: The original user question.
        iteration: Current agent loop iteration number.
    """
    query: str = ""
    iteration: int = 0
    chunks: list[ContextChunk] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)


class AgentContextManager:
    """Manages context accumulation for agent loop execution.

    Handles chunk deduplication by ``chunk_id``, enforces maximum chunk limits
    per tool call and total, sorts by relevance score when trimming, tracks
    tool call history, and formats context for LLM consumption.
    """

    def __init__(
        self,
        max_chunks_per_tool: int = 5,
        max_total_chunks: int = 15,
    ) -> None:
        """Initialize the context manager.

        Args:
            max_chunks_per_tool: Maximum chunks to keep per tool call.
            max_total_chunks: Maximum total chunks to maintain.
        """
        self.max_chunks_per_tool = max_chunks_per_tool
        self.max_total_chunks = max_total_chunks
        self._context = AgentContext()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def context(self) -> AgentContext:
        """Return the current accumulated context."""
        return self._context

    @property
    def chunks(self) -> list[ContextChunk]:
        """Return the current chunks."""
        return self._context.chunks

    @property
    def tool_calls(self) -> list[ToolCallRecord]:
        """Return the tool call history."""
        return self._context.tool_calls

    # ------------------------------------------------------------------
    # Query / iteration helpers
    # ------------------------------------------------------------------

    def set_query(self, query: str) -> None:
        """Set the current query.

        Args:
            query: The user's question.
        """
        self._context = AgentContext(
            query=query,
            iteration=self._context.iteration,
            chunks=self._context.chunks,
            tool_calls=self._context.tool_calls,
        )

    def increment_iteration(self) -> None:
        """Increment the iteration counter."""
        self._context = AgentContext(
            query=self._context.query,
            iteration=self._context.iteration + 1,
            chunks=self._context.chunks,
            tool_calls=self._context.tool_calls,
        )

    # ------------------------------------------------------------------
    # Chunk management
    # ------------------------------------------------------------------

    def add_chunks(
        self,
        new_chunks: list[ContextChunk],
        tool_name: str = "",
        limit_per_tool: int | None = None,
    ) -> list[ContextChunk]:
        """Add chunks with deduplication and limits.

        Chunks are deduplicated by ``chunk_id``.  When a tool returns more
        chunks than ``limit_per_tool`` allows, only the highest-scored ones
        are kept.  After merging, the total context is trimmed to
        ``max_total_chunks`` if necessary.

        Args:
            new_chunks: Chunks to add.
            tool_name: Name of the tool that retrieved these chunks.
            limit_per_tool: Override for max chunks per tool call.

        Returns:
            List of newly added chunks (after deduplication).
        """
        effective_limit = limit_per_tool or self.max_chunks_per_tool

        # Deduplicate by chunk_id
        existing_ids = {c.chunk_id for c in self._context.chunks}
        unique_new: list[ContextChunk] = []

        for chunk in new_chunks:
            if chunk.chunk_id not in existing_ids:
                unique_new.append(chunk)
                existing_ids.add(chunk.chunk_id)

        # Limit per tool call
        if len(unique_new) > effective_limit:
            unique_new = sorted(unique_new, key=lambda c: c.score, reverse=True)[:effective_limit]

        # Add to context
        self._context = AgentContext(
            query=self._context.query,
            iteration=self._context.iteration,
            chunks=self._context.chunks + unique_new,
            tool_calls=self._context.tool_calls,
        )

        # Trim if over total limit
        self._trim_to_limit()

        return unique_new

    def _trim_to_limit(self) -> None:
        """Trim chunks to maximum total limit, keeping highest scored."""
        if len(self._context.chunks) <= self.max_total_chunks:
            return

        sorted_chunks = sorted(
            self._context.chunks,
            key=lambda c: c.score,
            reverse=True,
        )[:self.max_total_chunks]

        self._context = AgentContext(
            query=self._context.query,
            iteration=self._context.iteration,
            chunks=sorted_chunks,
            tool_calls=self._context.tool_calls,
        )

    def get_chunks_sorted_by_score(self) -> list[ContextChunk]:
        """Return chunks sorted by relevance score descending.

        Returns:
            Chunks sorted by score.
        """
        return sorted(
            self._context.chunks,
            key=lambda c: c.score,
            reverse=True,
        )

    # ------------------------------------------------------------------
    # Tool call tracking
    # ------------------------------------------------------------------

    def record_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result_count: int,
        timestamp: float | None = None,
    ) -> ToolCallRecord:
        """Record a tool call.

        Args:
            tool_name: Name of the tool.
            arguments: Arguments passed to the tool.
            result_count: Number of results returned.
            timestamp: Optional epoch timestamp of the call.

        Returns:
            The created ``ToolCallRecord``.
        """
        record = ToolCallRecord(
            tool_name=tool_name,
            arguments=arguments,
            result_count=result_count,
            timestamp=timestamp,
        )
        self._context = AgentContext(
            query=self._context.query,
            iteration=self._context.iteration,
            chunks=self._context.chunks,
            tool_calls=self._context.tool_calls + [record],
        )
        return record

    # ------------------------------------------------------------------
    # Formatting / extraction
    # ------------------------------------------------------------------

    def format_context_for_llm(self, include_tool_history: bool = True) -> str:
        """Format accumulated context as a string for LLM consumption.

        Args:
            include_tool_history: Whether to include tool call history.

        Returns:
            Formatted context string.
        """
        parts: list[str] = []

        if self._context.query:
            parts.append(f"User Query: {self._context.query}")
            parts.append("")

        if self._context.chunks:
            parts.append("Retrieved Context:")
            parts.append("---")
            for i, chunk in enumerate(self._context.chunks, 1):
                source_info = f"[{chunk.source_type}]" if chunk.source_type else ""
                section_info = f" - {chunk.section_type}" if chunk.section_type else ""
                parts.append(f"{i}. {source_info}{section_info}")
                parts.append(f"   Score: {chunk.score:.4f}")
                parts.append(f"   {chunk.text}")
                if chunk.citation_ids:
                    parts.append(f"   Citations: {', '.join(chunk.citation_ids)}")
                parts.append("")
            parts.append("---")

        if include_tool_history and self._context.tool_calls:
            parts.append("Tool Call History:")
            for call in self._context.tool_calls:
                args_str = ", ".join(f"{k}={v}" for k, v in call.arguments.items())
                parts.append(f"- {call.tool_name}({args_str}) -> {call.result_count} results")
            parts.append("")

        return "\n".join(parts)

    def extract_citations(self) -> list[dict[str, Any]]:
        """Extract unique citations from all chunks.

        Returns:
            List of citation dictionaries with chunk and citation info.
        """
        citations: list[dict[str, Any]] = []
        seen: set[str] = set()

        for chunk in self._context.chunks:
            for citation_id in chunk.citation_ids:
                key = f"{chunk.chunk_id}:{citation_id}"
                if key not in seen:
                    seen.add(key)
                    citations.append({
                        "chunk_id": chunk.chunk_id,
                        "citation_id": citation_id,
                        "source_type": chunk.source_type,
                        "section_type": chunk.section_type,
                        "segment_ids": chunk.segment_ids,
                        "start_ms": chunk.start_ms,
                        "end_ms": chunk.end_ms,
                    })

        return citations

    def get_unique_segment_ids(self) -> list[str]:
        """Return all unique segment IDs across chunks.

        Returns:
            Deduplicated list of segment IDs preserving insertion order.
        """
        seen: set[str] = set()
        unique: list[str] = []

        for chunk in self._context.chunks:
            for seg_id in chunk.segment_ids:
                if seg_id not in seen:
                    seen.add(seg_id)
                    unique.append(seg_id)

        return unique

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset the context manager to a clean state."""
        self._context = AgentContext()


def get_agent_context_manager(
    max_chunks_per_tool: int = 5,
    max_total_chunks: int = 15,
) -> AgentContextManager:
    """Get an ``AgentContextManager`` instance.

    Args:
        max_chunks_per_tool: Maximum chunks per tool call.
        max_total_chunks: Maximum total chunks.

    Returns:
        A new ``AgentContextManager``.
    """
    return AgentContextManager(
        max_chunks_per_tool=max_chunks_per_tool,
        max_total_chunks=max_total_chunks,
    )
