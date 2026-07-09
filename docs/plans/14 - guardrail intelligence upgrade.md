# Phase 14 - Guardrail Intelligence Upgrade

## Status: Done

## Objectives

1. Replace brittle prefix-based parser with regex-based flexible parsing that handles varied model responses.
2. Normalize raw llama-guard3 category codes (`S1`-`S7`) into human-readable business labels.
3. Split strict mode into per-layer controls (`GUARDRAIL_INPUT_STRICT_MODE`, `GUARDRAIL_OUTPUT_STRICT_MODE`).
4. Implement soft-block and rule-based redaction as alternatives to full-block for output guardrail.
5. Derive confidence from model response heuristics instead of hardcoding fixed values.
6. Add cumulative latency budget to prevent guardrail from slowing chat beyond acceptable threshold.
7. Enrich guardrail metadata for observability: text length, truncation flag, prompt version, attempt count.
8. Add orchestration tests covering the full guardrail decision chain in the chat flow.

## Prerequisites

- [x] Phase 13 completed: transcript and context guardrail layers removed; only input and output guardrails remain.
- [x] Input guardrail for chat is implemented and active.
- [x] Output guardrail for chat is implemented and active.
- [x] Guardrail provider (`llama-guard3` via Ollama) is available.
- [x] Guardrail provider unit tests pass (6/6).

## Tasks

### P1 - Parser Hardening

#### Flexible response parsing

- [x] Replace `text.startswith("safe")` with regex `r'^\s*safe\b'` in `_parse_llama_guard_response`.
- [x] Replace `text.startswith("unsafe")` with regex `r'^\s*unsafe\b'`.
- [x] Add keyword fallback: if response contains `safe`, `benign`, `no issues`, `harmless` without any unsafe keyword → treat as allow.
- [x] Add keyword fallback: if response contains `unsafe`, `harmful`, `malicious`, `injection`, `jailbreak`, `exfiltration` → treat as block.
- [x] Empty response: change from auto-allow to `warn` (or `block` if strict mode) with category `empty_response`.
- [x] Unknown response: keep `warn` action but lower confidence to `0.3` and add category `unparseable_response`.

#### Prompt versioning

- [x] Add `PROMPT_VERSION` constant to `backend/providers/guardrail_provider.py` (initial value `"v1"`).
- [x] Include prompt version in `_build_llama_guard_prompt` system context line.
- [x] Include `promptVersion` in `GuardrailResult.to_metadata()` output.
- [x] Verify: change prompt version, confirm metadata reflects new version.

### P2 - Category Normalization

#### Category mapping

- [x] Add `_CATEGORY_MAP` dict in `backend/providers/guardrail_provider.py` mapping llama-guard3 codes to labels:
  - `S1` → `violence`
  - `S2` → `sexual_content`
  - `S3` → `criminal_planning`
  - `S4` → `illegal_weapons`
  - `S5` → `regulated_substances`
  - `S6` → `self_harm`
  - `S7` → `jailbreak`
  - `prompt_injection` → `prompt_injection`
  - `exfiltration` → `exfiltration`
  - `system_prompt` → `system_prompt_leak`
- [x] Add `normalized_categories: list[str]` field to `GuardrailResult`.
- [x] Populate `normalized_categories` during parsing using `_CATEGORY_MAP`.
- [x] Unknown codes → keep raw code, add `"unknown_category"` to normalized list.
- [x] Update `to_metadata()` to include `normalizedCategories` alongside raw `categories`.
- [x] Verify: send prompt injection question, confirm normalized category includes `prompt_injection`.

### P3 - Per-Layer Strict Mode

#### Configuration

- [x] Add `guardrail_input_strict_mode: bool | None = Field(default=None, alias="GUARDRAIL_INPUT_STRICT_MODE")` to `Settings`.
- [x] Add `guardrail_output_strict_mode: bool | None = Field(default=None, alias="GUARDRAIL_OUTPUT_STRICT_MODE")` to `Settings`.
- [x] Add `GUARDRAIL_INPUT_STRICT_MODE` and `GUARDRAIL_OUTPUT_STRICT_MODE` to `.env.example`.
- [x] Add both variables to `docker-compose.yml` backend and worker service environment.

#### Wiring

- [x] In `MeetingChatService._check_guardrail()`, accept explicit `strict_mode` parameter instead of always using global setting.
- [x] Input guardrail call: use `self.settings.guardrail_input_strict_mode if self.settings.guardrail_input_strict_mode is not None else self.settings.guardrail_strict_mode`.
- [x] Output guardrail call: use `self.settings.guardrail_output_strict_mode if self.settings.guardrail_output_strict_mode is not None else self.settings.guardrail_strict_mode`.
- [x] Verify: set input strict=true, output strict=false, confirm input blocks on error but output fails open.

### P4 - Output Soft Block and Redaction

#### Soft block strategy

- [x] Add `redaction_strategy` field to `GuardrailResult` with values `"full_block"`, `"soft_block"`, `"redact_sensitive"`.
- [x] Default for `block` action: `"full_block"`.
- [x] `_apply_output_guardrail`: when strategy is `soft_block`, replace answer with safe message but preserve citations and evidence state metadata.
- [x] `_apply_output_guardrail`: when strategy is `redact_sensitive`, keep answer but mark metadata as `redacted=true`.

#### Rule-based PII pre-redaction

- [x] Add `_redact_pii(text: str) -> str` helper in `backend/providers/guardrail_provider.py`.
- [x] Regex patterns for: email addresses, phone numbers (Vietnamese format), credit card numbers.
- [x] Replace matches with `[EMAIL]`, `[PHONE]`, `[CARD]` placeholders.
- [x] Apply `_redact_pii` to answer text before calling output guardrail.
- [x] Add `GUARDRAIL_PII_REDACTION_ENABLED` setting (default `true`).
- [x] Verify: answer containing email → guardrail sees `[EMAIL]`, user sees original answer with metadata flag.

### P5 - Confidence Heuristics

#### Heuristic scoring

- [x] Replace hardcoded `0.9` for safe with heuristic:
  - `0.85` base + `0.05` if response matches exactly `"safe"` + `0.05` if prompt version is current.
- [x] Replace hardcoded `0.95` for unsafe with heuristic:
  - `0.80` base + `0.05` if category codes present + `0.05` if multiple categories.
- [x] Replace hardcoded `0.5` for empty response with `0.3`.
- [x] Replace hardcoded `0.4` for unknown response with `0.3`.
- [x] Add `confidence_source` field to `GuardrailResult`: `"heuristic"`, `"model"`, `"hardcoded"`.
- [x] Include `confidenceSource` in `to_metadata()`.
- [x] Verify: safe response → confidence ~0.9, unsafe with categories → confidence ~0.9.

### P6 - Latency Budget

#### Configuration

- [x] Add `guardrail_latency_budget_ms: int = Field(default=8000, alias="GUARDRAIL_LATENCY_BUDGET_MS")` to `Settings`.
- [x] Add `GUARDRAIL_LATENCY_BUDGET_MS=8000` to `.env.example`.
- [x] Add to `docker-compose.yml` backend and worker service environment.

#### Enforcement

- [x] In `MeetingChatService.generate_answer()`, track cumulative guardrail latency across input + output checks.
- [x] After input guardrail, if cumulative latency exceeds budget:
  - Skip output guardrail check.
  - Log warning event with `budgetExceeded=true`.
  - Set output guardrail result to `None` in metadata.
- [x] If input guardrail itself exceeds budget:
  - Continue to retrieval (don't block on timeout).
  - Log warning with `budgetExceeded=true`.
- [x] Add `budgetExceeded` field to `GuardrailResult.to_metadata()`.
- [x] Verify: mock guardrail to sleep 5s, set budget to 3s, confirm output guardrail is skipped.

### P7 - Observability Metadata

#### Enriched metadata

- [x] Add `text_length: int` field to `GuardrailResult` — original text length before truncation.
- [x] Add `truncated: bool` field — whether text was cut to fit limit.
- [x] Add `attempt_count: int` field — how many provider calls were made (including retries).
- [x] Update `to_metadata()` to include `textLength`, `truncated`, `attemptCount`.
- [x] Pass `attempt_count` from `_call_ollama` retry loop to result.
- [x] Set `truncated=True` in `_compact_guardrail_text` when text exceeds limit.

#### Operational log enrichment

- [x] Guardrail operational log `details` should include new metadata fields.
- [x] Verify: send long question, confirm `truncated=true` and `textLength` in operational logs.

### P8 - Orchestration Tests

#### Input guardrail orchestration

- [x] Add `test_input_block_skips_retrieval`: mock provider to return block on input → verify `retrieval_search.search_meeting` is never called.
- [x] Add `test_input_block_saves_blocked_metadata`: verify user message metadata contains `action=block` and correct categories.
- [x] Add `test_input_allow_proceeds_to_retrieval`: mock provider to return allow → verify retrieval is called.

#### Output guardrail orchestration

- [x] Add `test_output_block_replaces_answer`: mock provider to return block on output → verify answer is replaced with safe message.
- [x] Add `test_output_block_clears_citations`: verify citations are empty when output is blocked.
- [x] Add `test_output_redact_preserves_evidence`: mock provider to return redact → verify answer is replaced but evidence state preserved.
- [x] Add `test_output_allow_keeps_answer`: mock provider to return allow → verify original answer persisted.

#### Fail-open / fail-closed

- [x] Add `test_guardrail_provider_error_fail_open`: mock provider to raise error, strict_mode=false → verify flow continues with warn action.
- [x] Add `test_guardrail_provider_error_fail_closed`: mock provider to raise error, strict_mode=true → verify flow blocked.

#### Latency budget

- [x] Add `test_latency_budget_skips_output_guardrail`: mock input guardrail to exceed budget → verify output guardrail not called.
- [x] Add `test_latency_budget_within_limit_both_called`: both guardrails within budget → verify both called.

#### PII redaction

- [x] Add `test_pii_redaction_masks_email`: answer with email → guardrail sees `[EMAIL]` placeholder.
- [x] Add `test_pii_redaction_masks_phone`: answer with phone number → guardrail sees `[PHONE]` placeholder.

## Verification Plan

### Automated Tests

- [x] Run guardrail provider unit tests (parser, normalization, confidence, PII).
- [x] Run chat service orchestration tests (all new P8 tests).
- [x] Run full backend unit test suite.
- [x] Run frontend production build.
- [x] Verify no regressions in existing guardrail tests.

### Manual Verification

- [x] Send a normal meeting question → confirm input guardrail allows, answer is grounded.
- [x] Send a prompt injection question → confirm input guardrail blocks with normalized category.
- [x] Send a question that produces a sensitive answer → confirm output guardrail handles with soft block or redact.
- [x] Stop Ollama → confirm fail-open/fail-closed works per layer strict mode setting.
- [x] Check operational logs → confirm enriched metadata (textLength, truncated, promptVersion, normalizedCategories).
- [x] Verify latency budget: set low budget, send rapid questions, confirm output guardrail skips gracefully.

### Acceptance Criteria

- [x] Parser handles varied model responses without misclassification.
- [x] Category codes are normalized into readable labels in metadata and logs.
- [x] Strict mode can be configured independently for input and output layers.
- [x] Output guardrail supports soft block and redaction strategies.
- [x] Confidence reflects model response quality, not hardcoded values.
- [x] Latency budget prevents guardrail from exceeding acceptable wait time.
- [x] Operational logs contain rich metadata for debugging guardrail decisions.
- [x] Orchestration tests cover all guardrail decision paths in chat flow.

---

## Completion Report

> **Completed at:** 2026-07-06
> **Verified by:** 86/86 unit tests passed (21 guardrail + 8 orchestration + 57 existing), frontend production build passed

### What was implemented

- Regex-based flexible parser replacing brittle `startswith` checks
- Category normalization map (`S1`-`S7` → `violence`, `sexual_content`, etc.)
- Per-layer strict mode (`GUARDRAIL_INPUT_STRICT_MODE`, `GUARDRAIL_OUTPUT_STRICT_MODE`)
- Soft block strategy for output guardrail (preserves citations)
- Rule-based PII pre-redaction (email, phone, card numbers)
- Confidence heuristics replacing hardcoded values
- Latency budget with output guardrail skip when exceeded
- Observability metadata: `textLength`, `truncated`, `attemptCount`, `promptVersion`, `normalizedCategories`, `confidenceSource`, `decisionId`, `budgetExceeded`
- Prompt versioning (`PROMPT_VERSION = "v1"`)
- 21 new guardrail provider tests + 8 orchestration tests
-

### What was changed from original plan

- `redact_pii` is applied to answer text before calling output guardrail, not as a separate post-processing step
- `redaction_strategy` defaults to `full_block` on block; only returns citations when explicitly set to `soft_block`
-

### Notes for future sessions

- `PROMPT_VERSION` should be bumped when the guardrail prompt template changes
- `_CATEGORY_MAP` can be extended for new llama-guard3 category codes without code changes elsewhere
- PII redaction uses Vietnamese phone format by default; international formats may need extension
- Latency budget is cumulative across input + output; does not reset between guardrail calls
-

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/plans/0 - project overview.md`
- [x] `docs/PROJECT_PLAN.md`
