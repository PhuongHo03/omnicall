"""Agentic RAG service for meeting-grounded chat answers."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Callable

from sqlalchemy.orm import Session

from backend.configs.settings import Settings, get_settings
from backend.providers.llm import (
    LLMProvider,
    LLMProviderError,
    get_effective_model_name,
    get_effective_provider_name,
    get_llm_provider,
)
from backend.services.agent.context_manager import AgentContextManager
from backend.services.agent.tool_registry import AgentToolRegistry
from backend.services.agent.fast_path import FastPathHandler
from backend.services.operational_log_service import OperationalLogService
from backend.services.agent.parallel_executor import ParallelExecutionSummary, ParallelToolExecutor
from backend.services.retrieval.search_service import RetrievalSearchService
from backend.services.agent.token_management import TokenBudget, TokenManager
from backend.services.agent.prompt_builder import (
    search_event_message as _search_event_message,
    synthesis_system_prompt as _synthesis_system_prompt,
    synthesis_user_prompt as _synthesis_user_prompt,
)
from backend.services.agent.response_utils import (
    _VALID_EVIDENCE_STATES,
    confidence as _confidence,
    elapsed_ms as _elapsed_ms,
    ensure_fact_search_for_precise_participant_attributes as _ensure_fact_search_for_precise_participant_attributes,
    evidence_state as _evidence_state,
    fallback_answer_from_context as _fallback_answer_from_context,
    is_precise_participant_attribute_question as _is_precise_participant_attribute_question,
    normalize_chunk as _normalize_chunk,
    to_context_chunk as _context_chunk,
)
from backend.services.agent.result_models import AgentResult
from backend.services.agent.agent_loop import AgentLoop, VALID_TOOLS
from backend.services.agent.context_coordinator import ContextCoordinator
from backend.services.agent.answer_synthesizer import AnswerSynthesizer
from backend.services.agent.query_planner import QueryPlan, build_query_plan, replan_query
from backend.services.agent.evidence_verifier import EvidenceVerificationResult, verify_evidence

logger = logging.getLogger(__name__)

_VALID_TOOLS = VALID_TOOLS
_MAX_ITERATIONS_DEFAULT = 2
_ITERATION_TIMEOUT_SECONDS = 30
_TOTAL_TIMEOUT_SECONDS = 60


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
        max_iterations: int | None = None,
        iteration_timeout_seconds: float | None = None,
        total_timeout_seconds: float | None = None,
        max_replans: int | None = None,
        max_tool_calls_per_iteration: int | None = None,
        max_chunks_per_tool: int | None = None,
        max_total_chunks: int | None = None,
        session_factory=None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.llm_provider = llm_provider or get_llm_provider()
        self.retrieval_search = retrieval_search or RetrievalSearchService(session)
        self.operational_logs = operational_logs
        self.max_iterations = _bounded_int(max_iterations, getattr(self.settings, "agentic_rag_max_iterations", _MAX_ITERATIONS_DEFAULT), 1, 10)
        self.max_replans = _bounded_int(max_replans, getattr(self.settings, "agentic_rag_max_replans", 1), 0, 5)
        self.max_tool_calls_per_iteration = _bounded_int(max_tool_calls_per_iteration, getattr(self.settings, "agentic_rag_max_tool_calls_per_iteration", 4), 1, 8)
        self.iteration_timeout_seconds = _bounded_float(iteration_timeout_seconds, getattr(self.settings, "agentic_rag_iteration_timeout_seconds", _ITERATION_TIMEOUT_SECONDS), 1.0, 300.0)
        self.total_timeout_seconds = _bounded_float(total_timeout_seconds, getattr(self.settings, "agentic_rag_total_timeout_seconds", _TOTAL_TIMEOUT_SECONDS), 1.0, 600.0)
        self.max_chunks_per_tool = _bounded_int(max_chunks_per_tool, getattr(self.settings, "agentic_rag_max_chunks_per_tool", 5), 1, 20)
        self.max_total_chunks = _bounded_int(max_total_chunks, getattr(self.settings, "agentic_rag_max_total_chunks", 12), 1, 50)
        self.tool_registry = AgentToolRegistry(
            session,
            retrieval_search=self.retrieval_search,
            session_factory=session_factory,
        )
        self.fast_path_handler = FastPathHandler(self.llm_provider)
        self.context_manager = AgentContextManager(
            max_chunks_per_tool=self.max_chunks_per_tool,
            max_total_chunks=self.max_total_chunks,
        )
        self.tool_executor = ParallelToolExecutor(tool_timeout_seconds=min(10.0, self.iteration_timeout_seconds))
        self.agent_loop = AgentLoop(
            llm_provider=self.llm_provider,
            tool_registry=self.tool_registry,
            context_manager=self.context_manager,
            tool_executor=self.tool_executor,
        )
        self.token_manager = TokenManager(
            max_context_tokens=getattr(self.settings, "agentic_rag_max_context_tokens", 4000)
        )
        self.context_coordinator = ContextCoordinator(
            context_manager=self.context_manager,
            token_manager=self.token_manager,
        )
        self.answer_synthesizer = AnswerSynthesizer(
            llm_provider=self.llm_provider,
            retrieval_search=self.retrieval_search,
            context_manager=self.context_manager,
            context_coordinator=self.context_coordinator,
        )

    def generate_answer(
        self,
        *,
        meeting_id: str,
        question: str,
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
        query_plan = build_query_plan(question)
        replan_count = 0
        self._event(event_callback, {
            "type": "agent_plan",
            "iteration": 0,
            "intent": query_plan.intent,
            "sections": query_plan.sections,
            "recordTypes": query_plan.record_types,
            "recordSubtypes": query_plan.record_subtypes,
            "relationTypes": query_plan.relation_types,
            "answerShape": query_plan.answer_shape,
            "subQueryCount": len(query_plan.sub_queries),
        })

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
                    plan=query_plan,
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
                    result = self._result_from_synthesis(
                        decision=decision,
                        thoughts=thoughts,
                        started=started,
                    )
                    return self._annotate_result(result, query_plan, replan_count)

                tool_calls = self._valid_tool_calls(decision.get("tool_calls", []), question=question)
                planned_tool_calls = self._tool_calls_from_plan(query_plan, question)
                if not tool_calls or all(call["tool"] in {"search_semantic", "search_keyword"} for call in tool_calls):
                    tool_calls = planned_tool_calls
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

                verification = verify_evidence(query_plan, self.context_manager.chunks)
                self._event(event_callback, {
                    "type": "agent_verify",
                    "iteration": iteration,
                    "sufficient": verification.sufficient,
                    "missingFields": verification.missing_fields,
                    "evidenceCount": len(verification.evidence_chunk_ids),
                })
                if not verification.sufficient and iteration < self.max_iterations and replan_count < self.max_replans:
                    replan_count += 1
                    query_plan = replan_query(query_plan, verification.missing_fields)
                    self._event(event_callback, {
                        "type": "agent_replan",
                        "iteration": iteration + 1,
                        "replanCount": replan_count,
                        "reason": verification.reason_code,
                        "missingFields": verification.missing_fields,
                    })
                    self._event(event_callback, {
                        "type": "agent_plan",
                        "iteration": iteration + 1,
                        "intent": query_plan.intent,
                        "sections": query_plan.sections,
                        "recordTypes": query_plan.record_types,
                        "recordSubtypes": query_plan.record_subtypes,
                        "relationTypes": query_plan.relation_types,
                        "answerShape": query_plan.answer_shape,
                        "subQueryCount": len(query_plan.sub_queries),
                    })

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
            result = self._synthesize_from_context(thoughts=thoughts, started=started)
            return self._annotate_result(result, query_plan, replan_count)
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
            result = self._fallback_from_retrieval(
                meeting_id=meeting_id,
                question=question,
                thoughts=thoughts,
                started=started,
                error=exc,
            )
            if "query_plan" in locals():
                return self._annotate_result(result, query_plan, replan_count)
            return result

    def _think(self, *, question: str, iteration: int, force_synthesize: bool = False, plan: QueryPlan | None = None) -> dict[str, Any]:
        self._sync_agent_loop()
        return self._run_with_timeout(
            lambda: self.agent_loop.think(
                question=question,
                iteration=iteration,
                force_synthesize=force_synthesize,
                plan=str(plan.to_dict()) if plan else "",
            ),
            self.iteration_timeout_seconds,
        )

    def _execute_tools(
        self,
        *,
        meeting_id: str,
        tool_calls: list[dict[str, Any]],
    ) -> ParallelExecutionSummary:
        self._sync_agent_loop()
        return self.agent_loop.execute_tools(
            meeting_id=meeting_id,
            tool_calls=tool_calls,
        )

    def _sync_agent_loop(self) -> None:
        """Keep legacy runtime overrides on the service authoritative."""
        self.agent_loop.llm_provider = self.llm_provider
        self.agent_loop.tool_registry = self.tool_registry
        self.agent_loop.context_manager = self.context_manager
        self.agent_loop.tool_executor = self.tool_executor

    def _accumulate_context(
        self,
        *,
        execution: ParallelExecutionSummary,
        accumulated_context: list[dict[str, Any]],
        seen_chunk_ids: set[str],
        accumulated_tokens: int,
        token_budget: TokenBudget,
    ) -> tuple[int, int]:
        self._sync_context_coordinator()
        return self.context_coordinator.accumulate(
            execution=execution,
            accumulated_context=accumulated_context,
            seen_chunk_ids=seen_chunk_ids,
            accumulated_tokens=accumulated_tokens,
            token_budget=token_budget,
        )

    def _result_from_synthesis(
        self,
        *,
        decision: dict[str, Any],
        thoughts: list[dict[str, Any]],
        started: float,
    ) -> AgentResult:
        self._sync_answer_synthesizer()
        if self.context_manager.chunks:
            return self.answer_synthesizer.from_context(thoughts=thoughts, started=started)
        return self.answer_synthesizer.from_decision(decision=decision, thoughts=thoughts, started=started)

    def _synthesize_from_context(self, *, thoughts: list[dict[str, Any]], started: float) -> AgentResult:
        self._sync_answer_synthesizer()
        remaining = max(1.0, self.total_timeout_seconds - (time.perf_counter() - started))
        return self._run_with_timeout(
            lambda: self.answer_synthesizer.from_context(thoughts=thoughts, started=started),
            remaining,
        )

    @staticmethod
    def _annotate_result(result: AgentResult, plan: QueryPlan, replan_count: int) -> AgentResult:
        result.metadata.update({"queryPlan": plan.to_dict(), "replans": replan_count})
        return result

    def _fallback_from_retrieval(
        self,
        *,
        meeting_id: str,
        question: str,
        thoughts: list[dict[str, Any]],
        started: float,
        error: Exception,
    ) -> AgentResult:
        self._sync_answer_synthesizer()
        return self.answer_synthesizer.fallback_from_retrieval(
            meeting_id=meeting_id,
            question=question,
            thoughts=thoughts,
            started=started,
            error=error,
        )

    def _valid_tool_calls(self, tool_calls: Any, *, question: str) -> list[dict[str, Any]]:
        valid: list[dict[str, Any]] = []
        if not isinstance(tool_calls, list):
            return _ensure_fact_search_for_precise_participant_attributes(valid, question)[: self.max_tool_calls_per_iteration]
        seen_calls: set[tuple[str, str]] = set()
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            tool_name = call.get("tool") or call.get("name")
            if tool_name not in _VALID_TOOLS:
                continue
            parameters = call.get("parameters") or call.get("arguments") or {}
            if not isinstance(parameters, dict):
                parameters = {}
            if tool_name == "search_semantic":
                parameters.setdefault("query", question)
            if tool_name == "search_keyword":
                parameters.setdefault("keyword", question)
            parameters = self._normalize_tool_parameters(tool_name, parameters)
            signature = (tool_name, repr(sorted(parameters.items())))
            if signature in seen_calls:
                continue
            seen_calls.add(signature)
            valid.append({"tool": tool_name, "parameters": parameters})
        valid = _ensure_fact_search_for_precise_participant_attributes(valid, question)
        return valid[: self.max_tool_calls_per_iteration]

    @staticmethod
    def _tool_calls_from_plan(plan: QueryPlan, question: str) -> list[dict[str, Any]]:
        # Canonical v2 selectors are the planner's primary output. Section
        # names are only used below for top-level projections (summary and
        # operational metadata), never to locate knowledge.records.
        if plan.record_types:
            calls = [{
                "tool": "search_records",
                "parameters": {
                    "record_types": plan.record_types,
                    "record_subtypes": plan.record_subtypes,
                    "relation_types": plan.relation_types,
                    "answer_shape": plan.answer_shape,
                    "query": question,
                    "limit": 10,
                },
            }]
            if any(section.startswith("summary.") for section in plan.sections):
                calls.append({"tool": "get_summary", "parameters": {}})
            return calls[:4]
        if plan.intent == "prices_and_commercial_terms":
            return [
                {"tool": "search_section", "parameters": {"section_type": "fact.record", "query": "price cost amount dollar discount $", "limit": 5}},
                {"tool": "get_summary", "parameters": {}},
            ]
        if plan.intent == "business_and_product_entities":
            return [
                {"tool": "search_section", "parameters": {"section_type": "entity.profile", "query": "company store shop brand product name", "limit": 5}},
                {"tool": "search_section", "parameters": {"section_type": "fact.record", "query": "company store shop brand product name", "limit": 5}},
                {"tool": "get_summary", "parameters": {}},
            ]
        calls: list[dict[str, Any]] = []
        direct = {
            "summary.executive": "get_summary",
            "summary.topic": "get_summary",
        }
        for section in plan.sections:
            tool = direct.get(section)
            if tool and tool not in {item["tool"] for item in calls}:
                calls.append({"tool": tool, "parameters": {}})
            if len(calls) >= 4:
                break
            if section in {"meeting.metadata", "source.processing", "quality.overview", "quality.warning", "extraction.overview", "extraction.warning", "evidence.map", "transcript.coverage", "fact.record", "entity.profile", "transcript.window"}:
                calls.append({"tool": "search_section", "parameters": {"section_type": section, "limit": 5}})
                if len(calls) >= 4:
                    break
        if not calls:
            calls.append({"tool": "search_semantic", "parameters": {"query": question, "limit": 6}})
        return calls

    @staticmethod
    def _normalize_tool_parameters(tool_name: str, parameters: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(parameters)
        if "limit" in normalized:
            try:
                normalized["limit"] = max(1, min(10, int(normalized["limit"])))
            except (TypeError, ValueError):
                normalized["limit"] = 5
        if tool_name == "get_summary" and normalized.get("summary_type") not in {None, "executive", "topic", "timeline", "all"}:
            normalized["summary_type"] = "all"
        return normalized

    def _run_with_timeout(self, callback: Callable[[], Any], timeout: float) -> Any:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(callback)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"Agent step timed out after {timeout:.1f}s") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _tool_call_summary(self) -> list[dict[str, Any]]:
        self._sync_context_coordinator()
        return self.context_coordinator.tool_call_summary()

    def _context_chunks_for_metadata(self) -> list[dict[str, Any]]:
        self._sync_context_coordinator()
        return self.context_coordinator.chunks_for_metadata()

    def _token_summary(self) -> dict[str, Any]:
        self._sync_context_coordinator()
        return self.context_coordinator.token_summary()

    def _sync_context_coordinator(self) -> None:
        """Keep legacy runtime overrides on the service authoritative."""
        self.context_coordinator.context_manager = self.context_manager
        self.context_coordinator.token_manager = self.token_manager

    def _sync_answer_synthesizer(self) -> None:
        """Keep legacy runtime overrides on the service authoritative."""
        self.answer_synthesizer.llm_provider = self.llm_provider
        self.answer_synthesizer.retrieval_search = self.retrieval_search
        self.answer_synthesizer.context_manager = self.context_manager
        self._sync_context_coordinator()
        self.answer_synthesizer.context_coordinator = self.context_coordinator

    @staticmethod
    def _event(callback: Callable[[dict[str, Any]], None] | None, event: dict[str, Any]) -> None:
        if callback is not None:
            callback(event)


def _bounded_int(value: Any, fallback: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value if value is not None else fallback)
    except (TypeError, ValueError):
        number = int(fallback)
    return max(minimum, min(maximum, number))


def _bounded_float(value: Any, fallback: Any, minimum: float, maximum: float) -> float:
    try:
        number = float(value if value is not None else fallback)
    except (TypeError, ValueError):
        number = float(fallback)
    return max(minimum, min(maximum, number))
