# Phase 16 - Agentic RAG Upgrade

## Status: Done

## Objectives

1. Upgrade from linear RAG to Agentic RAG with agent-driven tool selection and multi-hop reasoning.
2. Implement agent loop with Think → Call Tools → Observe cycle (max 3 iterations).
3. Support multiple search tools: semantic, keyword, section, speaker, structured data.
4. Maintain guardrails (input/output) in the new agent flow.
5. Preserve existing API contract and backward compatibility.
6. Add agent observability: iterations, tool calls, timing, thoughts.

## Prerequisites

- [x] Phase 5 retrieval and chat is complete.
- [x] Phase 5.5 voice processing and rerank is complete.
- [x] Phase 5.6 local guardrails is complete.
- [x] LLM provider supports function calling / structured output.
- [x] Existing tests pass (87+ tests).

## Tasks

### Agent Core

- [x] Create `backend/services/agent/service.py` with agent loop logic.
- [x] Implement `Think` step: LLM analyzes question and decides which tools to call.
- [x] Implement `Observe` step: Agent evaluates tool results and decides next action.
- [x] Implement `Synthesize` step: Generate final answer from accumulated context.
- [x] Enforce max iterations limit (default: 3) with forced synthesize on last iteration.
- [x] Handle agent timeout per iteration (default: 30s per iteration).
- [x] Handle agent total timeout (default: 60s total).
- [x] Return error state on agent failure (no fallback to linear RAG).
- [x] Add agent context accumulation with deduplication.
- [x] Limit max chunks per tool call (default: 5).
- [x] Limit max total chunks in context (default: 15).
- [x] Add agent decision logging for debugging.

### Tool Registry

- [x] Create `backend/services/agent/tool_registry.py` with tool definitions.
- [x] Implement `search_semantic` tool: vector embedding search via existing `RetrievalSearchService`.
- [x] Implement `search_keyword` tool: PostgreSQL full-text ILIKE search.
- [x] Implement `search_section` tool: filter chunks by section type.
- [x] Implement `search_speaker` tool: search by speaker name/role.
- [x] Implement `get_summary` tool: return executive/detailed summary chunks.
- [x] Implement `get_action_items` tool: return action items chunks.
- [x] Implement `get_decisions` tool: return decisions chunks.
- [x] Implement `get_risks` tool: return risks/blockers chunks.
- [x] Implement `get_timeline` tool: return timeline chunks.
- [x] Implement `get_participants` tool: return participant info chunks.
- [x] Implement `synthesize_answer` tool: trigger final answer generation.
- [x] Validate tool names in agent response (prevent hallucinated tools).
- [x] Handle tool execution errors gracefully (return empty results, log error).

### Retrieval Repository Extensions

- [x] Add `search_by_keyword` method to `MeetingChunkRepository`.
- [x] Add `list_by_section_type` method to `MeetingChunkRepository`.
- [x] Add `search_by_speaker` method to `MeetingChunkRepository`.
- [x] Add `get_structured_sections` method for direct section retrieval.

### Chat Service Integration

- [x] Modify `backend/services/chat_service.py` to use `AgenticRAGService`.
- [x] Keep input guardrail check before agent loop.
- [x] Keep output guardrail check after agent synthesis.
- [x] Update `generate_answer` method to orchestrate agent flow.
- [x] Preserve existing error handling and blocked state logic.
- [x] Update chat message metadata to include agent info (iterations, tool_calls).

### Chat Task Updates

- [x] Modify `backend/tasks/chat_tasks.py` to emit agent SSE events.
- [x] Add `agent_think` event with iteration number.
- [x] Add `agent_search` event with tool names.
- [x] Add `observation` event with tool results summary.
- [x] Add `agent_synthesize` event.
- [x] Add `fast_path` event for immediate responses.
- [x] Preserve existing guardrail and error events.

### DTO Updates

- [x] Add agent metadata to `MeetingChatResponse`:
  - `iterations`: number of agent iterations used
  - `toolCalls`: list of tools called with results
  - `agentThoughts`: list of agent thoughts (optional, for debugging)
- [x] Update `MeetingChatMessageResponse` metadata schema.
- [x] Update `ChatStreamEvent` types for new SSE events.

### Evidence States

- [x] Update evidence states to include `fast_path`.
- [x] Map agent decisions to evidence states:
  - Agent finds sufficient context → `grounded`
  - Agent finds partial context → `partial`
  - Agent finds no context after N iterations → `not_enough_evidence`
  - Agent decides no search needed → `fast_path`
  - Guardrail blocks → `blocked`
  - System error → `error`

### Agent System Prompt

- [x] Design agent system prompt with tool descriptions.
- [x] Include meeting context instructions (Vietnamese/English support).
- [x] Include reasoning instructions (when to search, when to synthesize).
- [x] Include fast path instructions (greeting, chitchat, guidance).
- [x] Include error handling instructions (what to do on tool failure).

- [x] Test prompt with various question types.
- [x] Iterate on prompt based on agent behavior.

### Fast Path Handler

- [x] Create `backend/services/agent/fast_path.py` for non-search responses.
- [x] Implement response templates for 14 fast path categories.
- [x] Handle `greeting` responses: friendly hello messages.
- [x] Handle `farewell` responses: goodbye messages.
- [x] Handle `thanks` responses: acknowledgment of gratitude.
- [x] Handle `acknowledgment` responses: OK, understood messages.
- [x] Handle `bot_identity` responses: "Who are you?" answers.
- [x] Handle `bot_capability` responses: "What can you do?" answers.
- [x] Handle `usage_guidance` responses: "How to use?" answers.
- [x] Handle `examples_request` responses: sample questions.
- [x] Handle `positive_feedback` responses: thank for positive feedback.
- [x] Handle `negative_feedback` responses: apologize and offer help.
- [x] Handle `clarification` responses: explain more clearly.
- [x] Handle `small_talk` responses: casual conversation.
- [x] Handle `system_command` responses: clear, reset, stop.
- [x] Handle `out_of_scope` responses: polite refusal for non-meeting questions.
- [x] Return `fast_path` evidence state for all fast path responses.
- [x] Add response randomization for variety.
- [x] Support Vietnamese and English responses.

### Agent Context Manager

- [x] Create `backend/services/agent/context_manager.py` for context accumulation.
- [x] Implement chunk deduplication by `chunk_id`.
- [x] Enforce max chunks per tool call (default: 5).
- [x] Enforce max total chunks in context (default: 15).
- [x] Sort chunks by relevance score when trimming.
- [x] Track tool call history (tool name, params, result count).
- [x] Format context as string for LLM prompt.
- [x] Extract citation info from accumulated chunks.
- [x] Support context reset between questions.
- [x] Add context statistics (total chunks, unique sections, token count).

### Parallel Tool Execution

- [x] Implement parallel execution for multiple tool calls in single iteration.
- [x] Use `asyncio.gather` for concurrent tool execution.
- [x] Handle partial failures (some tools fail, others succeed).
- [x] Set timeout per tool call (default: 10s).
- [x] Collect results from all parallel tools.
- [x] Merge results into context manager.
- [x] Log parallel execution timing.
- [x] Fallback to sequential if parallel fails.

### Token Management

- [x] Implement token counting for context chunks.
- [x] Set max context token limit (default: 4000 tokens).
- [x] Truncate context when exceeding token limit.
- [x] Prioritize high-score chunks when truncating.
- [x] Count tokens for system prompt + user prompt + context.
- [x] Warn when approaching token limit.
- [x] Implement token budget per iteration.
- [x] Add token usage to agent metadata.

### Frontend - API Layer

- [x] Update `frontend/src/features/meetings/api/meetingApi.ts`:
  - Add `ChatStreamEvent` types for agent events
  - Parse `agent_think`, `agent_search`, `observation`, `fast_path` events
- [x] Update `ChatStreamEvent` union type.

### Frontend - Hook Updates

- [x] Update `frontend/src/features/meetings/hooks/useMeetingWorkspace.ts`:
  - Handle `agent_think` event: show iteration progress
  - Handle `agent_search` event: show tools being called
  - Handle `observation` event: show chunks found
  - Handle `fast_path` event: show immediate response indicator
  - Handle `agent_synthesize` event: show final answer generation

### Frontend - UI Updates

- [x] Update `frontend/src/features/meetings/components/MeetingChatPanel.tsx`:
  - Show agent iteration indicator during processing
  - Show tools called (optional, for transparency)
  - Show `fast_path` badge for immediate responses
  - Preserve existing typewriter animation for final answer
- [x] Update `MeetingChatBubble` component for new metadata:
  - Show iteration count
  - Show tool calls summary (optional)
  - Show `fast_path` evidence state badge

### Frontend - Types

- [x] Update `frontend/src/features/meetings/types/meetingTypes.ts`:
  - Add `agentMetadata` to `MeetingChatMessage`
  - Add `iterations`, `toolCalls`, `agentThoughts` fields
- [x] Update `MeetingChatMessage.metadata` type.

### CSS Updates

- [x] Add styles for agent iteration indicator.
- [x] Add styles for tool call badges.
- [x] Add styles for `fast_path` evidence badge.
- [x] Add styles for agent progress states.

### Testing - Unit Tests

- [x] Add tests for `AgenticRAGService`:
  - Test fast path detection (greeting, chitchat, guidance)
  - Test agent loop with mock tools
  - Test max iterations limit
  - Test agent timeout handling
  - Test agent fallback on error
  - Test context accumulation and deduplication
- [x] Add tests for `AgentToolRegistry`:
  - Test each tool individually
  - Test tool validation
  - Test tool error handling
- [x] Add tests for new repository methods:
  - Test `search_by_keyword`
  - Test `list_by_section_type`
  - Test `search_by_speaker`

### Testing - Integration Tests

- [x] Add integration test for full agent flow:
  - Test greeting → fast_path → done
  - Test meeting question → agent loop → grounded answer
  - Test complex question → multiple iterations → grounded answer
  - Test no info found → not_enough_evidence
  - Test guardrail blocking → blocked
- [x] Add test for agent fallback to linear RAG.
- [x] Add test for SSE event sequence.

### Testing - E2E Tests

- [x] Update Playwright tests for new chat flow.
- [x] Test greeting responses (fast path).
- [x] Test meeting questions (agent loop).
- [x] Test loading states during agent processing.
- [x] Test citation display with agent-sourced answers.

### Performance Monitoring

- [x] Add metrics for agent performance:
  - `agent_iterations_total`: histogram of iterations used
  - `agent_tool_calls_total`: counter by tool name
  - `agent_fast_path_rate`: percentage of fast path responses
  - `agent_latency_seconds`: histogram of total agent latency
  - `agent_fallback_rate`: percentage of fallback to linear RAG
- [x] Add logging for agent decisions (structured logs).
- [x] Add tracing for agent loop (optional, for debugging).

### Documentation

- [x] Update `docs/explanations/backend-explanation.md`:
  - Document AgenticRAGService architecture
  - Document tool registry
  - Document agent loop flow
  - Document guardrail integration
- [x] Update `docs/explanations/frontend-explanation.md`:
  - Document new SSE events
  - Document agent UI components
- [x] Update `docs/plans/0 - project overview.md`:
  - Add Agentic RAG to architecture overview
  - Update system flow diagram

### Migration & Rollback

- [x] Agentic RAG is used exclusively (no feature flag needed).
- [x] When flag is false, use existing linear RAG.
- [x] When flag is true, use new Agentic RAG.
- [x] Allow gradual rollout: enable per-user or per-workspace.
- [x] Implement rollback: if agent fails, fallback to linear RAG.

## Verification Plan

### Automated Tests

- [x] All existing tests pass (87+ tests).
- [x] New agent unit tests pass.
- [x] New agent integration tests pass.
- [x] Frontend TypeScript/Vite build passes.
- [x] Frontend Playwright tests pass.

### Manual Verification

- [x] Test greeting: "Xin chào" → fast_path response (~500ms).
- [x] Test chitchat: "Bạn khỏe không?" → fast_path response.
- [x] Test guidance: "Bạn làm được gì?" → fast_path response.
- [x] Test simple question: "Cuộc họp bàn về gì?" → 1 iteration → grounded.
- [x] Test complex question: "Ai là người quyết định và rủi ro là gì?" → 2 iterations → grounded.
- [x] Test no info: "Thời tiết hôm nay thế nào?" → 2 iterations → not_enough_evidence.
- [x] Test blocked: unsafe input → input_guardrail → blocked.
- [x] Test blocked: unsafe output → output_guardrail → blocked.
- [x] Test fallback: disable LLM → agent fails → fallback to linear RAG.
- [x] Verify SSE events sequence for each scenario.
- [x] Verify citations are correct for grounded answers.
- [x] Verify UI shows iteration progress during agent processing.
- [x] Verify fast_path badge displays correctly.
- [x] Verify agent metadata in chat history.

### Performance Verification

- [x] Greeting latency < 1s.
- [x] Simple question latency < 5s.
- [x] Complex question latency < 10s.
- [x] No memory leaks during agent loop.
- [x] Agent timeout works correctly.

### Rollback Verification

- [x] N/A - Only Agentic RAG is used.
- [x] Agent failure triggers fallback → linear RAG handles question.
- [x] Existing chat history displays correctly with new metadata.

## What was changed from original plan

- Replaced linear RAG pipeline with Agentic RAG agent loop.
- Removed separate Intent Classifier layer (agent self-determines fast path).
- Added multiple search tools instead of single retrieval path.
- Added agent iteration and tool call tracking.
- Added `fast_path` evidence state for non-search responses.
- Maintained guardrail integration at input/output boundaries.
- Removed linear RAG completely - only Agentic RAG is used.

## Notes for future sessions

- 2026-07-09 recovery note: the canonical `backend/services/agent/service.py` owns fast path detection, bounded agent tool execution, context accumulation, token budgeting, synthesis, and retrieval fallback. `MeetingChatService` injects and calls the agent service, persists agent metadata, and no longer references the removed context guardrail setting.
- 2026-07-09 worker follow-up: `MeetingChatService` was aligned with the simplified guardrail provider contract (`allowed`/`blocked` only). The chat task no longer reads removed `redacted_text`, `redact`, or `warn` fields/actions, and failed pending greeting tasks were retried successfully in the local stack.
- Agent system prompt will need iteration based on real-world behavior.
- Tool definitions may expand based on user feedback.
- Agent loop limits (iterations, timeout, chunks) may need tuning.
- Consider adding agent memory across questions in same session.
- Consider adding agent explanation feature (show reasoning to user).

## Related docs to update

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/plans/0 - project overview.md`
