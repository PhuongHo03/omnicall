"""Token counting and management for context windows.

Provides token counting, truncation with priority to high-score chunks,
and token budget management per iteration.
"""
from dataclasses import dataclass, field
from typing import Any


# ─── Constants ───────────────────────────────────────────────────────────
# Single source of truth for token estimation parameters
TOKENS_PER_CHAR_ESTIMATE = 0.25  # Rough heuristic: ~4 chars per token for English text


@dataclass(frozen=True)
class TokenChunk:
    """A chunk with token count information.

    Attributes:
        chunk_id: Unique identifier for the chunk.
        text: The chunk text content.
        score: Relevance score used for prioritization.
        token_count: Estimated token count for the chunk text.
        source_type: Origin of the chunk.
        section_type: Structured section type.
        metadata: Additional metadata dictionary.
    """
    chunk_id: str
    text: str
    score: float
    token_count: int
    source_type: str = ""
    section_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenBudget:
    """Token budget for an iteration.

    Attributes:
        total_limit: Total token limit for the budget.
        used: Tokens already consumed.
        reserved: Tokens reserved for response generation.
    """
    total_limit: int
    used: int = 0
    reserved: int = 0

    @property
    def available(self) -> int:
        """Return the number of available tokens."""
        return max(0, self.total_limit - self.used - self.reserved)

    @property
    def is_exhausted(self) -> bool:
        """Return ``True`` if the budget is exhausted."""
        return self.available <= 0


@dataclass
class TokenUsage:
    """Token usage statistics.

    Attributes:
        chunk_tokens: Tokens used by retrieved chunks.
        prompt_tokens: Tokens used by the system/user prompt.
        response_tokens: Tokens reserved for the model response.
        total_tokens: Sum of all token usage.
    """
    chunk_tokens: int = 0
    prompt_tokens: int = 0
    response_tokens: int = 0
    total_tokens: int = 0


class TokenManager:
    """Manages token counting, limits, and truncation.

    Provides token counting for chunks, maintains maximum context token limits,
    truncates with priority to high-score chunks, and manages token budgets
    per iteration.
    """

    def __init__(
        self,
        max_context_tokens: int = 4000,
        tokens_per_char_estimate: float | None = None,
    ) -> None:
        """Initialize the token manager.

        Args:
            max_context_tokens: Maximum tokens allowed in context.
            tokens_per_char_estimate: Estimated tokens per character (uses global default if None).
        """
        self.max_context_tokens = max_context_tokens
        self.tokens_per_char_estimate = tokens_per_char_estimate or TOKENS_PER_CHAR_ESTIMATE

    # ------------------------------------------------------------------
    # Token counting
    # ------------------------------------------------------------------

    def count_tokens(self, text: str) -> int:
        """Count tokens in text using character-based estimation.

        The estimation uses ~4 characters per token as a rough heuristic
        for English text.  Returns ``0`` for empty strings.

        Args:
            text: Text to count tokens for.

        Returns:
            Estimated token count.
        """
        if not text:
            return 0
        return max(1, int(len(text) * self.tokens_per_char_estimate))

    def count_chunk_tokens(self, chunk: dict[str, Any]) -> int:
        """Count tokens for a chunk dictionary.

        Args:
            chunk: Chunk dictionary with a ``text`` field.

        Returns:
            Token count for the chunk text.
        """
        text = chunk.get("text", "")
        return self.count_tokens(text)

    # ------------------------------------------------------------------
    # Chunk conversion
    # ------------------------------------------------------------------

    def create_token_chunks(
        self,
        chunks: list[dict[str, Any]],
    ) -> list[TokenChunk]:
        """Create ``TokenChunk`` objects with token counts from raw dicts.

        Args:
            chunks: List of chunk dictionaries.

        Returns:
            List of ``TokenChunk`` objects with token counts.
        """
        token_chunks: list[TokenChunk] = []

        for chunk in chunks:
            text = chunk.get("text", "")
            token_count = self.count_tokens(text)

            token_chunks.append(TokenChunk(
                chunk_id=chunk.get("chunk_id", ""),
                text=text,
                score=chunk.get("score", 0.0),
                token_count=token_count,
                source_type=chunk.get("source_type", ""),
                section_type=chunk.get("section_type", ""),
                metadata=chunk.get("metadata", {}),
            ))

        return token_chunks

    # ------------------------------------------------------------------
    # Truncation
    # ------------------------------------------------------------------

    def truncate_to_limit(
        self,
        chunks: list[TokenChunk],
        limit: int | None = None,
    ) -> list[TokenChunk]:
        """Truncate chunks to fit within a token limit.

        Chunks are sorted by score descending so that the highest-priority
        chunks are kept.  If a chunk partially fits, it is text-truncated
        at a word boundary.

        Args:
            chunks: List of ``TokenChunk`` objects.
            limit: Token limit to enforce (defaults to ``max_context_tokens``).

        Returns:
            List of chunks that fit within the limit.
        """
        effective_limit = limit or self.max_context_tokens

        sorted_chunks = sorted(chunks, key=lambda c: c.score, reverse=True)

        selected: list[TokenChunk] = []
        current_tokens = 0

        for chunk in sorted_chunks:
            if current_tokens + chunk.token_count <= effective_limit:
                selected.append(chunk)
                current_tokens += chunk.token_count
            else:
                remaining = effective_limit - current_tokens
                if remaining > 50:  # Minimum viable chunk size
                    truncated_text = self._truncate_text(chunk.text, remaining)
                    truncated_count = self.count_tokens(truncated_text)

                    selected.append(TokenChunk(
                        chunk_id=chunk.chunk_id,
                        text=truncated_text,
                        score=chunk.score,
                        token_count=truncated_count,
                        source_type=chunk.source_type,
                        section_type=chunk.section_type,
                        metadata=chunk.metadata,
                    ))
                    current_tokens += truncated_count
                break

        return selected

    def _truncate_text(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within a token limit at a word boundary.

        Args:
            text: Text to truncate.
            max_tokens: Maximum tokens allowed.

        Returns:
            Truncated text ending with ``...``.
        """
        max_chars = int(max_tokens / self.tokens_per_char_estimate)
        if len(text) <= max_chars:
            return text

        truncated = text[:max_chars]
        last_space = truncated.rfind(" ")
        if last_space > max_chars * 0.8:
            truncated = truncated[:last_space]

        return truncated + "..."

    # ------------------------------------------------------------------
    # Budget management
    # ------------------------------------------------------------------

    def create_budget(
        self,
        total_limit: int | None = None,
        reserved: int = 0,
    ) -> TokenBudget:
        """Create a token budget for an iteration.

        Args:
            total_limit: Total token limit.
            reserved: Tokens reserved for response.

        Returns:
            A ``TokenBudget`` instance.
        """
        effective_limit = total_limit or self.max_context_tokens
        return TokenBudget(
            total_limit=effective_limit,
            reserved=reserved,
        )

    def fit_chunks_to_budget(
        self,
        chunks: list[TokenChunk],
        budget: TokenBudget,
    ) -> list[TokenChunk]:
        """Fit chunks within a token budget.

        Args:
            chunks: List of ``TokenChunk`` objects.
            budget: ``TokenBudget`` to respect.

        Returns:
            List of chunks that fit within the budget.
        """
        return self.truncate_to_limit(chunks, budget.available)

    def calculate_usage(
        self,
        chunks: list[TokenChunk],
        prompt_template: str = "",
        estimated_response_tokens: int = 500,
    ) -> TokenUsage:
        """Calculate total token usage across context, prompt, and response.

        Args:
            chunks: List of chunks.
            prompt_template: Prompt template text.
            estimated_response_tokens: Estimated response tokens.

        Returns:
            ``TokenUsage`` statistics.
        """
        chunk_tokens = sum(c.token_count for c in chunks)
        prompt_tokens = self.count_tokens(prompt_template)

        return TokenUsage(
            chunk_tokens=chunk_tokens,
            prompt_tokens=prompt_tokens,
            response_tokens=estimated_response_tokens,
            total_tokens=chunk_tokens + prompt_tokens + estimated_response_tokens,
        )

    def can_fit_chunks(
        self,
        chunks: list[TokenChunk],
        additional_tokens: int = 0,
        limit: int | None = None,
    ) -> bool:
        """Check if chunks fit within a token limit.

        Args:
            chunks: List of chunks to check.
            additional_tokens: Additional tokens to account for.
            limit: Token limit (defaults to ``max_context_tokens``).

        Returns:
            ``True`` if chunks fit within the limit.
        """
        effective_limit = limit or self.max_context_tokens
        total_tokens = sum(c.token_count for c in chunks) + additional_tokens
        return total_tokens <= effective_limit

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_token_summary(
        self,
        chunks: list[TokenChunk],
    ) -> dict[str, Any]:
        """Return a summary of token usage.

        Args:
            chunks: List of chunks.

        Returns:
            Summary dictionary with counts, utilization, and remaining budget.
        """
        total_tokens = sum(c.token_count for c in chunks)
        avg_tokens = total_tokens / len(chunks) if chunks else 0

        return {
            "chunk_count": len(chunks),
            "total_tokens": total_tokens,
            "average_tokens_per_chunk": round(avg_tokens, 2),
            "max_context_tokens": self.max_context_tokens,
            "remaining_tokens": max(0, self.max_context_tokens - total_tokens),
            "utilization_percent": round(
                (total_tokens / self.max_context_tokens * 100)
                if self.max_context_tokens > 0 else 0,
                2,
            ),
        }


def get_token_manager(
    max_context_tokens: int = 4000,
    tokens_per_char_estimate: float = 0.25,
) -> TokenManager:
    """Get a ``TokenManager`` instance.

    Args:
        max_context_tokens: Maximum context tokens.
        tokens_per_char_estimate: Tokens per character estimate.

    Returns:
        A new ``TokenManager``.
    """
    return TokenManager(
        max_context_tokens=max_context_tokens,
        tokens_per_char_estimate=tokens_per_char_estimate,
    )
