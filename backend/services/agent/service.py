"""Agentic RAG service for meeting-grounded chat answers."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from backend.configs.settings import Settings, get_settings
from backend.providers.llm_provider import (
    LLMProvider,
    LLMProviderError,
    get_effective_model_name,
    get_effective_provider_name,
    get_llm_provider,
)
from backend.services.agent.context_manager import AgentContextManager, ContextChunk
from backend.services.agent.tool_registry import AgentToolRegistry
from backend.services.agent.fast_path import FastPathHandler
from backend.services.operational_log_service import OperationalLogService
from backend.services.agent.parallel_executor import ParallelExecutionSummary, ParallelToolExecutor
from backend.services.retrieval_search_service import RetrievalSearchService
from backend.services.agent.token_management import TokenBudget, TokenManager

logger = logging.getLogger(__name__)

_VALID_TOOLS = {
    "search_semantic",
    "search_keyword",
    "search_section",
    "search_speaker",
    "get_summary",
    "get_action_items",
    "get_decisions",
    "get_risks",
    "get_timeline",
    "get_participants",
    "synthesize_answer",
}
_VALID_EVIDENCE_STATES = {
    "grounded",
    "partial",
    "not_enough_evidence",
    "fast_path",
    "blocked",
    "error",
}
_MAX_ITERATIONS_DEFAULT = 3
_ITERATION_TIMEOUT_SECONDS = 30
_TOTAL_TIMEOUT_SECONDS = 60


@dataclass
class AgentResult:
    """Final response from the agentic RAG flow."""

    answer: str
    evidence_state: str
    confidence: float
    provider: str = "agentic-rag"
    model: str | None = None
    iterations: int = 0
    total_duration_ms: int = 0
    tool_calls_summary: list[dict[str, Any]] = field(default_factory=list)
    agent_thoughts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_answer_payload(self) -> dict[str, Any]:
        """Convert to the answer payload shape used by ``MeetingChatService``."""
        return {
            "answer": self.answer,
            "evidenceState": self.evidence_state,
            "confidence": self.confidence,
            "provider": self.provider,
            "model": self.model,
            "agentIterations": self.iterations,
            "agentToolCalls": self.tool_calls_summary,
            "agentThoughts": self.agent_thoughts,
        }


class AgenticRAGService:
    """Runs a bounded Think -> Execute Tools -> Observe loop for one question."""

    def __init__(
        self,
        *,
        session: Session,
        llm_provider: LLMProvider | None = None,
        retrieval_search: RetrievalSearchService | None = None,
        operational_logs: OperationalLogService | None = None,
        settings: Settings | None = None,
        max_iterations: int = _MAX_ITERATIONS_DEFAULT,
        iteration_timeout_seconds: float = _ITERATION_TIMEOUT_SECONDS,
        total_timeout_seconds: float = _TOTAL_TIMEOUT_SECONDS,
        max_chunks_per_tool: int = 5,
        max_total_chunks: int = 15,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.llm_provider = llm_provider or get_llm_provider()
        self.retrieval_search = retrieval_search or RetrievalSearchService(session)
        self.operational_logs = operational_logs
        self.max_iterations = max(1, int(max_iterations or _MAX_ITERATIONS_DEFAULT))
        self.iteration_timeout_seconds = float(iteration_timeout_seconds or _ITERATION_TIMEOUT_SECONDS)
        self.total_timeout_seconds = float(total_timeout_seconds or _TOTAL_TIMEOUT_SECONDS)
        self.tool_registry = AgentToolRegistry(session, retrieval_search=self.retrieval_search)
        self.fast_path_handler = FastPathHandler(self.llm_provider)
        self.context_manager = AgentContextManager(
            max_chunks_per_tool=max_chunks_per_tool,
            max_total_chunks=max_total_chunks,
        )
        self.tool_executor = ParallelToolExecutor(tool_timeout_seconds=min(10.0, self.iteration_timeout_seconds))
        self.token_manager = TokenManager(
            max_context_tokens=getattr(self.settings, "agentic_rag_max_context_tokens", 4000)
        )

    def generate_answer(
        self,
        *,
        meeting_id: str,
        question: str,
        workspace_id: str,
        event_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentResult:
        """Generate an answer using fast path detection and agentic retrieval."""
        started = time.perf_counter()
        self.context_manager.reset()
        self.context_manager.set_query(question)

        fast_path = self.fast_path_handler.handle(question)
        if fast_path is not None:
            self._event(event_callback, {"type": "fast_path", "message": fast_path.answer})
            return AgentResult(
                answer=fast_path.answer,
                evidence_state=fast_path.evidence_state,
                confidence=0.95,
                provider="agentic-rag-fast-path",
                model=get_effective_model_name(self.llm_provider),
                total_duration_ms=_elapsed_ms(started),
                metadata={"chunks": [], "tokenUsage": self._token_summary()},
            )

        thoughts: list[dict[str, Any]] = []
        accumulated_context: list[dict[str, Any]] = []
        seen_chunk_ids: set[str] = set()
        accumulated_tokens = 0
        budget = self.token_manager.create_budget(reserved=700)

        try:
            for iteration in range(1, self.max_iterations + 1):
                if time.perf_counter() - started >= self.total_timeout_seconds:
                    break

                self.context_manager.increment_iteration()
                self._event(
                    event_callback,
                    {
                        "type": "agent_think",
                        "iteration": iteration,
                        "message": "Đang lập kế hoạch tìm bằng chứng tiếp theo...",
                    },
                )
                decision = self._think(
                    question=question,
                    iteration=iteration,
                    force_synthesize=iteration == self.max_iterations,
                )
                thought = {
                    "iteration": iteration,
                    "decision": decision.get("action", ""),
                    "reasoning": decision.get("reasoning", ""),
                    "tools": [call["tool"] for call in decision.get("tool_calls", [])],
                    "duration_ms": decision.get("durationMs", 0),
                }
                thoughts.append(thought)

                if decision.get("action") == "synthesize":
                    self._event(
                        event_callback,
                        {
                            "type": "agent_synthesize",
                            "iteration": iteration,
                            "forced": iteration == self.max_iterations,
                            "message": "Đang tạo câu trả lời cuối cùng...",
                        },
                    )
                    return self._result_from_synthesis(
                        decision=decision,
                        thoughts=thoughts,
                        started=started,
                    )

                tool_calls = self._valid_tool_calls(decision.get("tool_calls", []), question=question)
                if not tool_calls:
                    if self.context_manager.chunks:
                        return self._synthesize_from_context(thoughts=thoughts, started=started)
                    tool_calls = [{"tool": "search_semantic", "parameters": {"query": question, "limit": 6}}]

                self._event(
                    event_callback,
                    {
                        "type": "agent_search",
                        "iteration": iteration,
                        "tools": [call["tool"] for call in tool_calls],
                        "message": _search_event_message(tool_calls),
                    },
                )
                execution = self._execute_tools(
                    meeting_id=meeting_id,
                    workspace_id=workspace_id,
                    tool_calls=tool_calls,
                )
                added, accumulated_tokens = self._accumulate_context(
                    execution=execution,
                    accumulated_context=accumulated_context,
                    seen_chunk_ids=seen_chunk_ids,
                    accumulated_tokens=accumulated_tokens,
                    token_budget=budget,
                )
                self._event(
                    event_callback,
                    {
                        "type": "observation",
                        "iteration": iteration,
                        "total_chunks": added,
                        "resultCount": added,
                        "successCount": execution.success_count,
                        "failureCount": execution.failure_count,
                    },
                )

                if budget.is_exhausted:
                    break

            self._event(
                event_callback,
                {
                    "type": "agent_synthesize",
                    "iteration": len(thoughts),
                    "forced": True,
                    "message": "Đang tạo câu trả lời cuối cùng...",
                },
            )
            return self._synthesize_from_context(thoughts=thoughts, started=started)
        except Exception as exc:
            logger.warning("agentic_rag.failed error=%s", str(exc))
            self._event(
                event_callback,
                {
                    "type": "agent_synthesize",
                    "iteration": len(thoughts),
                    "forced": True,
                    "message": "Đang tạo câu trả lời cuối cùng...",
                },
            )
            return self._fallback_from_retrieval(
                meeting_id=meeting_id,
                workspace_id=workspace_id,
                question=question,
                thoughts=thoughts,
                started=started,
                error=exc,
            )

    def _think(self, *, question: str, iteration: int, force_synthesize: bool = False) -> dict[str, Any]:
        started = time.perf_counter()
        response = self.llm_provider.generate_json(
            system_prompt=_agent_system_prompt(
                tools=self.tool_registry.get_tools(),
                force_synthesize=force_synthesize,
            ),
            user_prompt=_agent_user_prompt(
                question=question,
                iteration=iteration,
                context=self.context_manager.format_context_for_llm(),
            ),
        )
        if not isinstance(response, dict):
            raise LLMProviderError("Agent provider response was not a JSON object.")
        action = response.get("action")
        if action not in {"continue", "synthesize"}:
            action = "synthesize" if force_synthesize else "continue"
        return {
            **response,
            "action": action,
            "durationMs": _elapsed_ms(started),
        }

    def _execute_tools(
        self,
        *,
        meeting_id: str,
        workspace_id: str,
        tool_calls: list[dict[str, Any]],
    ) -> ParallelExecutionSummary:
        async def run() -> ParallelExecutionSummary:
            async def execute_one(tool_name: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
                result = self.tool_registry.execute_tool(
                    meeting_id=meeting_id,
                    workspace_id=workspace_id,
                    tool_name=tool_name,
                    arguments=parameters,
                )
                if not result.success:
                    raise RuntimeError(result.error or f"Tool {tool_name} failed.")
                data = result.data or []
                if isinstance(data, dict):
                    data = [data]
                return list(data)

            tool_map = {tool: execute_one for tool in _VALID_TOOLS}
            return await self.tool_executor.execute(tool_calls, tool_map)

        try:
            return asyncio.run(run())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(run())
            finally:
                loop.close()

    def _accumulate_context(
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
                normalized = _normalize_chunk(chunk)
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
                result_chunks.append(_context_chunk(normalized))
            self.context_manager.add_chunks(result_chunks, tool_name=tool_result.tool_name)
            self.context_manager.record_tool_call(
                tool_result.tool_name,
                tool_result.parameters,
                len(tool_result.result),
            )
            token_budget.used = accumulated_tokens
        return added, accumulated_tokens

    def _result_from_synthesis(
        self,
        *,
        decision: dict[str, Any],
        thoughts: list[dict[str, Any]],
        started: float,
    ) -> AgentResult:
        answer = decision.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            return self._synthesize_from_context(thoughts=thoughts, started=started)
        evidence_state = _evidence_state(decision.get("evidenceState"), has_context=bool(self.context_manager.chunks))
        confidence = _confidence(decision.get("confidence"), default=0.75)
        return AgentResult(
            answer=answer.strip(),
            evidence_state=evidence_state,
            confidence=confidence,
            provider=get_effective_provider_name(self.llm_provider),
            model=get_effective_model_name(self.llm_provider),
            iterations=len(thoughts),
            total_duration_ms=_elapsed_ms(started),
            tool_calls_summary=self._tool_call_summary(),
            agent_thoughts=thoughts,
            metadata={
                "chunks": self._context_chunks_for_metadata(),
                "tokenUsage": self._token_summary(),
            },
        )

    def _synthesize_from_context(self, *, thoughts: list[dict[str, Any]], started: float) -> AgentResult:
        chunks = self.context_manager.get_chunks_sorted_by_score()
        if not chunks:
            return AgentResult(
                answer="Không đủ bằng chứng trong dữ liệu cuộc họp để trả lời câu hỏi này.",
                evidence_state="not_enough_evidence",
                confidence=0.0,
                provider="agentic-rag-evidence-guard",
                model=None,
                iterations=len(thoughts),
                total_duration_ms=_elapsed_ms(started),
                tool_calls_summary=self._tool_call_summary(),
                agent_thoughts=thoughts,
                metadata={"chunks": [], "tokenUsage": self._token_summary()},
            )

        try:
            response = self.llm_provider.generate_json(
                system_prompt=_synthesis_system_prompt(),
                user_prompt=_synthesis_user_prompt(
                    question=self.context_manager.context.query,
                    context=self.context_manager.format_context_for_llm(include_tool_history=False),
                ),
            )
            answer = response.get("answer")
            if not isinstance(answer, str) or not answer.strip():
                raise LLMProviderError("Synthesis response did not include an answer.")
            evidence_state = _evidence_state(response.get("evidenceState"), has_context=True)
            confidence = _confidence(response.get("confidence"), default=0.7)
            provider = get_effective_provider_name(self.llm_provider)
            model = get_effective_model_name(self.llm_provider)
        except Exception:
            answer = _fallback_answer_from_context(chunks)
            evidence_state = "partial"
            confidence = 0.45
            provider = "agentic-rag-local-summary"
            model = None

        return AgentResult(
            answer=answer,
            evidence_state=evidence_state,
            confidence=confidence,
            provider=provider,
            model=model,
            iterations=len(thoughts),
            total_duration_ms=_elapsed_ms(started),
            tool_calls_summary=self._tool_call_summary(),
            agent_thoughts=thoughts,
            metadata={
                "chunks": self._context_chunks_for_metadata(),
                "tokenUsage": self._token_summary(),
            },
        )

    def _fallback_from_retrieval(
        self,
        *,
        meeting_id: str,
        workspace_id: str,
        question: str,
        thoughts: list[dict[str, Any]],
        started: float,
        error: Exception,
    ) -> AgentResult:
        try:
            retrieved = self.retrieval_search.search_meeting(
                workspace_id=workspace_id,
                meeting_id=meeting_id,
                query=question,
            )
        except Exception:
            retrieved = []
        chunks = [
            _normalize_chunk(
                {
                    "chunkId": item.record.chunk_id,
                    "text": item.record.text,
                    "sourceType": item.record.source_type,
                    "sectionType": item.record.section_type,
                    "jsonPointer": item.record.json_pointer,
                    "citationIds": list(item.record.citation_ids or []),
                    "segmentIds": list(item.record.segment_ids or []),
                    "startMs": item.record.start_ms,
                    "endMs": item.record.end_ms,
                    "metadata": item.record.metadata_json or {},
                    "score": item.score,
                }
            )
            for item in retrieved[:6]
        ]
        self.context_manager.add_chunks([_context_chunk(chunk) for chunk in chunks])
        answer = _fallback_answer_from_context(self.context_manager.get_chunks_sorted_by_score())
        return AgentResult(
            answer=answer,
            evidence_state="partial" if chunks else "error",
            confidence=0.4 if chunks else 0.0,
            provider="agentic-rag-fallback",
            model=None,
            iterations=len(thoughts),
            total_duration_ms=_elapsed_ms(started),
            tool_calls_summary=self._tool_call_summary(),
            agent_thoughts=thoughts,
            metadata={
                "chunks": self._context_chunks_for_metadata(),
                "tokenUsage": self._token_summary(),
                "error": {"type": type(error).__name__, "message": str(error)},
            },
        )

    def _valid_tool_calls(self, tool_calls: Any, *, question: str) -> list[dict[str, Any]]:
        valid: list[dict[str, Any]] = []
        if not isinstance(tool_calls, list):
            return valid
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            tool_name = call.get("tool") or call.get("name")
            if tool_name not in _VALID_TOOLS or tool_name == "synthesize_answer":
                continue
            parameters = call.get("parameters") or call.get("arguments") or {}
            if not isinstance(parameters, dict):
                parameters = {}
            if tool_name == "search_semantic":
                parameters.setdefault("query", question)
            if tool_name == "search_keyword":
                parameters.setdefault("keyword", question)
            valid.append({"tool": tool_name, "parameters": parameters})
        return valid

    def _tool_call_summary(self) -> list[dict[str, Any]]:
        return [
            {
                "tool": call.tool_name,
                "arguments": call.arguments,
                "result_count": call.result_count,
            }
            for call in self.context_manager.tool_calls
        ]

    def _context_chunks_for_metadata(self) -> list[dict[str, Any]]:
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

    def _token_summary(self) -> dict[str, Any]:
        token_chunks = self.token_manager.create_token_chunks(self._context_chunks_for_metadata())
        return self.token_manager.get_token_summary(token_chunks)

    @staticmethod
    def _event(callback: Callable[[dict[str, Any]], None] | None, event: dict[str, Any]) -> None:
        if callback is not None:
            callback(event)


def _agent_system_prompt(*, tools: list[dict[str, Any]], force_synthesize: bool) -> str:
    tool_names = [
        tool.get("function", {}).get("name")
        for tool in tools
        if isinstance(tool.get("function", {}), dict)
    ]
    mode = "You must synthesize now." if force_synthesize else "You may call tools or synthesize."
    return (
        "You are Omnicall's meeting intelligence agent. "
        "Use only meeting data returned by tools. "
        "Choose focused tools, observe results, then synthesize a concise answer in the user's language. "
        f"{mode} "
        f"Available tools: {', '.join(name for name in tool_names if name)}. "
        "Return JSON. For tool use: "
        '{"action":"continue","reasoning":"...","tool_calls":[{"tool":"search_semantic","parameters":{"query":"..."}}]}. '
        "For a final answer: "
        '{"action":"synthesize","reasoning":"...","answer":"...","evidenceState":"grounded|partial|not_enough_evidence","confidence":0.0}.'
    )


def _agent_user_prompt(*, question: str, iteration: int, context: str) -> str:
    return (
        f"Question: {question}\n"
        f"Iteration: {iteration}\n\n"
        f"Current context:\n{context or '(none yet)'}"
    )


def _synthesis_system_prompt() -> str:
    return (
        "Answer as a meeting intelligence assistant. "
        "Use only the supplied context. Return JSON with answer, evidenceState, and confidence. "
        "Use not_enough_evidence when the context does not support the answer."
    )


def _synthesis_user_prompt(*, question: str, context: str) -> str:
    return f"Question: {question}\n\nContext:\n{context}"


def _normalize_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunkId": chunk.get("chunkId") or chunk.get("chunk_id") or "",
        "meetingId": chunk.get("meetingId") or chunk.get("meeting_id"),
        "sourceType": chunk.get("sourceType") or chunk.get("source_type") or "",
        "sectionType": chunk.get("sectionType") or chunk.get("section_type") or "",
        "jsonPointer": chunk.get("jsonPointer") or chunk.get("json_pointer") or "",
        "citationIds": list(chunk.get("citationIds") or chunk.get("citation_ids") or []),
        "segmentIds": list(chunk.get("segmentIds") or chunk.get("segment_ids") or []),
        "startMs": chunk.get("startMs") if "startMs" in chunk else chunk.get("start_ms"),
        "endMs": chunk.get("endMs") if "endMs" in chunk else chunk.get("end_ms"),
        "text": str(chunk.get("text") or ""),
        "score": float(chunk.get("score") or 0.0),
        "metadata": dict(chunk.get("metadata") or {}),
    }


def _context_chunk(chunk: dict[str, Any]) -> ContextChunk:
    metadata = dict(chunk.get("metadata") or {})
    metadata.setdefault("jsonPointer", chunk.get("jsonPointer", ""))
    return ContextChunk(
        chunk_id=chunk["chunkId"],
        text=chunk.get("text", ""),
        score=float(chunk.get("score") or 0.0),
        source_type=chunk.get("sourceType", ""),
        section_type=chunk.get("sectionType", ""),
        citation_ids=list(chunk.get("citationIds") or []),
        segment_ids=list(chunk.get("segmentIds") or []),
        start_ms=chunk.get("startMs"),
        end_ms=chunk.get("endMs"),
        metadata=metadata,
    )


def _fallback_answer_from_context(chunks: list[ContextChunk]) -> str:
    lines = [chunk.text.strip() for chunk in chunks[:3] if chunk.text.strip()]
    if not lines:
        return "Không đủ bằng chứng trong dữ liệu cuộc họp để trả lời câu hỏi này."
    return "Dựa trên dữ liệu cuộc họp: " + " ".join(lines)


def _search_event_message(tool_calls: list[dict[str, Any]]) -> str:
    tools = [_tool_label(str(call.get("tool"))) for call in tool_calls if call.get("tool")]
    if not tools:
        return "Đang tìm bằng chứng trong cuộc họp..."
    return "Đang tìm bằng " + ", ".join(tools) + "..."


def _tool_label(tool_name: str) -> str:
    return {
        "search_semantic": "tìm kiếm ngữ nghĩa",
        "search_keyword": "tìm theo từ khóa",
        "search_section": "lọc theo mục",
        "search_speaker": "tìm theo người nói",
        "get_summary": "tóm tắt cuộc họp",
        "get_action_items": "việc cần làm",
        "get_decisions": "quyết định",
        "get_risks": "rủi ro",
        "get_timeline": "mốc thời gian",
        "get_participants": "người tham gia",
    }.get(tool_name, tool_name)


def _evidence_state(value: Any, *, has_context: bool) -> str:
    if value in _VALID_EVIDENCE_STATES:
        return str(value)
    return "grounded" if has_context else "not_enough_evidence"


def _confidence(value: Any, *, default: float) -> float:
    if isinstance(value, int | float):
        return max(0.0, min(1.0, float(value)))
    return default


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
