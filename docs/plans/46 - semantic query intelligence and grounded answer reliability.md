# Phase 46 - Semantic query intelligence and grounded answer reliability

## Status: Done

> **Baseline note:** Phase 46 remains the completed and runtime-verified Semantic Query IR/cardinality baseline. Phase 47 carries that foundation into the more general typed QueryGraph, DiscourseState, per-goal evidence-branch, and canonical graph/cache architecture; it does not rewrite this phase's historical acceptance results.

## Objectives

1. Replace phrase-driven planning with a validated semantic Query IR that separates operation, target, answer shape, entities, relations, filters, and temporal constraints.
2. Select retrieval tools by declared capabilities and allow validated query decomposition without losing the canonical user question.
3. Verify structured records by fields/roles first and support multilingual transcript claims without weakening number, negation, entity, or direction checks.
4. Repair transcript citation coverage, deterministic count provenance, semantic-tool timeout alignment, and fallback/cache behavior exposed by runtime acceptance testing.

## Prerequisites

- [x] Phase 44 durable conversation, snapshot, cache, memory, and claim-verification fences are complete.
- [x] Runtime failure evidence is captured for meeting `c261b38b-f600-4b43-bfa7-ccbc7da7863c`.
- [x] Existing backend suite passes before Phase 46 changes (`342 tests`).

## Tasks

### Semantic Query IR and planning

- [x] Add a closed, validated Query IR for operation, target, answer shape, entities, relations, filters, and temporal constraints.
- [x] Derive Query IR through bounded semantic interpretation with deterministic fallback and clarification for unsafe ambiguity.
- [x] Make query planning and tool selection consume Query IR rather than raw phrase lists.
- [x] Keep validated retrieval subqueries instead of overwriting them with the original question.
- [x] Make replanning change executable retrieval requirements before forced synthesis.
- [x] Reject provider-invented constraints and generic business roles such as customer/agent from entity and filter identity.
- [x] Allow high-confidence typed factual lookup/count/list questions to override narrow guardrail false positives without bypassing unsafe terms or prompt-injection checks.

### Grounding and synthesis

- [x] Verify structured key/value and actor/target records from authoritative fields before lexical checks.
- [x] Add bounded multilingual entailment/alias handling while retaining strict number, negation, entity, and directional-role gates.
- [x] Dispatch deterministic projections by operation and target; return to LLM synthesis when a projection is not applicable.
- [x] Preserve claim verification on retrieval and synthesis fallback paths.

### Retrieval and source quality

- [x] Give transcript windows citation/evidence lineage and preserve short evidence-bearing utterances.
- [x] Remove deterministic record-ID collisions and prevent unknown/noise speaker labels from inflating participant count.
- [x] Align semantic tool and reranker timeouts and avoid per-request model-load timeouts.
- [x] Tighten retrieval-cache admission and entity extraction for unverified or low-quality contexts.
- [x] Fuse generation-valid Milvus and authoritative PostgreSQL candidates with RRF; validated Query IR paths use authoritative pins without a blocking per-request crossencoder.

### Conversation-aware semantic continuation

- [x] Carry sanitized prior Semantic Query IR frames in resolver-only conversation context without treating prior answers as evidence.
- [x] Merge only missing closed IR slots for elliptical follow-ups; explicit current operation, target, entities, filters, negation, and time must override history.
- [x] Prevent fast-path from overriding meeting-domain or context-resolved effective Query IR.
- [x] Preserve a bounded clarification-repair frame so the next user message can complete the unresolved request without admitting clarification text as evidence.
- [x] Keep context fingerprints and cache identities distinct for the same follow-up under different semantic frames.

### Exact cardinality premises

- [x] Add source-grounded, current-clause `expectedCount` to Query IR; accept only a digit bound to a typed collection noun, re-ground provider values from source text, and include it in cache/context identity.
- [x] Treat `expectedCount` as a user premise rather than a retrieval limit; participant list requests compile into coupled actual-count and full-identity-list branches.
- [x] Require one exact cited participant aggregate and one complete unique identity set; lower-bound facts, conflicting counts, mentioned-only people, and unsupported target cardinalities fail closed.
- [x] Apply the exact-count and complete-roster contract to ordinary global participant count/list requests as well as requests that state an expected count; keep COUNT and LIST coupled during replanning.
- [x] Reject scoped participant aggregates and validate `expectedCount` per subplan; preserve full semantic branch identity so same-target clauses with different scope/count cannot collapse.
- [x] Re-run cardinality verification at every synthesis entry point and at claim persistence; an exact global count must cite an authoritative exact aggregate and cannot be grounded by a lower bound, conflicting record, or uncited summary.
- [x] Protect a fully modeled digit-bound participant collection from history rebinding, so resolver output cannot turn its collection noun into a fabricated entity.
- [x] Give `participant.overview` a stable record identity while admitting pre-ID snapshots only through the closed legacy overview contract.
- [x] Store attendee-only `attendeeNames` in the overview with its stable citation so complete rosters are not limited by participant-profile retrieval caps.
- [x] Adjudicate fully covered bare typed count questions deterministically while leaving unmatched modifiers, references, numbers, entities, filters, time, and unsupported scripts ambiguous.

### Context-aware cache lifecycle

- [x] Keep semantically indexed entries from different valid context fingerprints side by side; a context mismatch is a skip/hard boundary, not a reason to remove the other context's entry.
- [x] Continue pruning entries whose generation, pipeline contract, integrity hash, or payload is globally stale/corrupt.

## Verification Plan

### Automated Tests

- [x] Query IR paraphrase matrix covers Vietnamese/English summary, participant, price, decision, timeline, reason, and attribute questions.
- [x] Structured verifier tests cover key/value records, multilingual paraphrases, numbers, negation, and directional roles.
- [x] Agent tests cover capability selection, executable replan, validated query decomposition, transcript fallback, and verified resilience paths.
- [x] Processing/retrieval tests cover record-ID collision, unknown speaker handling, transcript citations, short utterances, and semantic timeout behavior.
- [x] Focused semantic/resolver/planner/verifier/retrieval/cache suite passes (`190 tests`).
- [x] Full backend unittest discovery passes (`530 tests`) against both bind-mounted source and a freshly built backend image.
- [x] End-to-end tests cover participant-count to participant-name follow-up, self-contained participant-name queries, explicit target override, and no-history ambiguity.
- [x] Clarification-repair tests prove the next user fragment completes the prior typed request while retrieval still uses current-snapshot evidence.
- [x] Fast-path tests prove meeting-domain and resolved follow-ups cannot return assistant identity or small-talk answers.

### Runtime Verification

- [x] Rebuild/reprocess meeting `c261b38b-f600-4b43-bfa7-ccbc7da7863c` with repaired source contracts.
- [x] Rebuild its final retrieval snapshot and verify `participant-overview` contains the stable overview citation, exact count `2`, and attendee-only names `Donna` and `Carolyn Lake`.
- [x] Verify basic summary and participant-count questions return grounded, cited answers.
- [x] Verify price/age/decision count questions do not route to participant count.
- [x] Confirm semantic retrieval completes without the prior 10-second timeout.
- [x] Re-run the reported multi-turn sequence on meeting `c261b38b-f600-4b43-bfa7-ccbc7da7863c` and confirm participant names are grounded instead of fast-path/clarification responses.
- [x] Verify `Có bao nhiêu người tham gia?` returns the exact grounded count and the following `Họ tên gì?` resolves to the complete participant-name set without inheriting an `expectedCount` premise.
- [x] Verify `2 người nói tên gì?` returns the full exact set and `999 người nói tên gì?` corrects the unsupported premise without truncating or fabricating identities.
- [x] Verify the order-independent self-contained form `Tên của 2 người là gì?` remains standalone even with prior history, keeps no entity binding, and returns the complete grounded roster.

### Acceptance Criteria

- [x] Equivalent paraphrases map to the same typed intent without adding phrase-specific planner branches.
- [x] Operation and target are independent, so `how many` cannot imply participant count by itself.
- [x] Evidence present in structured fields or cited transcript can produce a grounded answer across Vietnamese/English wording.
- [x] Ambiguous interpretation asks for clarification, while a well-typed query with unsupported evidence returns not enough evidence instead of selecting a misleading cache/retrieval contract.
- [x] Elliptical follow-ups inherit compatible semantic targets/fields from prior turns without copying prior answer text as factual evidence.
- [x] A complete current typed collection cannot be rebound to prior answer text, while a truly elliptical projection still receives a context-specific semantic frame.
- [x] Clarification responses repair the pending semantic request, and typed meeting queries always reach retrieval/verification rather than fast-path.

---

## Completion Report

> **Reopened at:** 2026-07-16 after runtime multi-turn acceptance exposed missing semantic-frame carry-over, fast-path gating, and clarification repair.
> **Re-completed at:** 2026-07-17
> **Verified by:** focused `190`-test semantic/resolver/planner/verifier/retrieval/cache suite, full `530`-test backend runs against bind-mounted source and the freshly built image, image build/deploy, healthy backend/worker/beat containers, target snapshot rebuild, and runtime acceptance against the target meeting

### What was implemented

- Added closed Semantic Query IR interpretation, clause-local decomposition, capability-based planning, executable replanning, and per-subplan evidence verification.
- Added typed structured/transcript source contracts, topic and monetary projections, strict claim gates, hybrid Milvus/PostgreSQL fusion, authoritative Query IR pins, bounded timeout fallback, and source-lineage cache identity.
- Repaired deterministic count IDs, excluded unknown/noise speakers, retained short cited transcript evidence, and reprocessed the target meeting to a fresh ready snapshot with two reliable participants.
- Added typed guardrail false-positive adjudication for safe factual questions and removed generic business roles from provider entities/filters.
- Added trusted prior Semantic Query IR frames, closed-slot contextual merge, explicit-current-slot precedence, semantic anchor IDs, and frame-specific context fingerprints without treating prior answer text as factual evidence.
- Made fast-path fail closed for meeting-domain, contextual, ambiguous, or retrieval-required Query IR while retaining greeting/small-talk and explicit assistant-scope responses.
- Added exact-adjacent clarification repair backed by internal PostgreSQL message metadata. Repair re-grounds only user-authored source questions and never admits the assistant clarification prompt as evidence.
- Added participant identity projection that prefers complete identified names over redundant `Speaker 1/2` aliases when the authoritative participant count confirms coverage.
- Added source-grounded `expectedCount` premise handling without result slicing or ordinary history inheritance. Participant-name requests with a stated count retrieve the actual count and the full identity set as separate coupled branches.
- Added exact participant-cardinality verification from `participant.overview`, complete identity-set verification, and grounded correction when the count stated in the question differs from meeting data. Lower-bound counts, conflicting aggregates, incomplete identities, mentioned-only people, and unsupported target cardinalities fail closed.
- Generalized that contract to ordinary global participant lists, kept count/list branches together during replan, rejected scoped use of meeting-global aggregates, validated expected cardinality per branch, and retained distinct same-target clause signatures.
- Added synthesis- and claim-level cardinality guards. Every answer path now rechecks the active plan; an exact global count claim must cite an exact authoritative aggregate and is vetoed on lower bounds, count conflicts, mismatches, or an uncited text-only summary.
- Prevented the open-vocabulary resolver from rebinding a fully covered digit-bound participant collection to history. Explicit current aggregate semantics now remain standalone, while incomplete follow-ups still use trusted semantic carry-over.
- Added attendee-only names and the stable overview citation to `participant.overview`, providing a complete-roster evidence frame independently of profile retrieval limits.
- Fixed semantic-cache index lifecycle so a valid entry for context A survives a lookup under context B; only globally stale or corrupt entries are removed.
- Added stable `participant-overview` record identity plus strict backward-compatible retrieval for existing pre-ID snapshots.
- Added closed full-coverage adjudication for bare typed count questions, while residual references, modifiers, numbers, entities, filters, time, or unsupported scripts remain ambiguous.
- Runtime acceptance returned grounded answers for three topics, two participants, two decisions, and four distinct prices/costs. The unsupported age question remained `lookup/age` and correctly returned not enough evidence with no fabricated citation.
- Runtime continuation acceptance on meeting `c261b38b-f600-4b43-bfa7-ccbc7da7863c` returned a grounded exact count of two, then `Donna, Carolyn Lake` for `Họ tên gì?`; the follow-up IR remained contextual participant/list while `expectedCount` correctly stayed null. The self-contained `2 người nói tên gì?` returned the same full set, and `999 người nói tên gì?` corrected the premise to two without truncation or fabricated identities.
- Final-image acceptance also kept `Tên của 2 người là gì?` standalone under existing history, preserved the original canonical question with `entities=[]` and `expectedCount=2`, and returned the same grounded full roster.
- Runtime clarification repair completed `Người đó đã làm gì?` + `Donna` as an entity lookup containing only `Donna`; it reached retrieval and correctly returned not enough evidence instead of asking again or inventing an answer.

### What was changed from original plan

- Runtime testing exposed two cross-cutting additions: deterministic topic/money projections and typed guardrail false-positive adjudication. Both were added as closed semantic contracts rather than phrase-specific exceptions.
- Validated Query IR retrieval now skips the blocking local crossencoder and uses fused ranking plus authoritative pins; legacy surface-only retrieval retains typed timeout fallback.
- Conversation continuation is a typed semantic-frame merge rather than a grammar-specific rewrite. Explicit current slots clear incompatible inherited scope, and the same surface follow-up under a different frame receives a different context fingerprint/cache identity.
- Exact premise extraction deliberately accepts decimal digits bound to a typed collection noun. Word numerals remain non-exact/clarified until a source-span numeral parser can support them without accent-fold ambiguity; scoped participant aggregates and expected cardinality for unsupported collections deliberately fail closed.
- No database migration or new durable schema was required; pipeline/cache identities were versioned instead.

### Notes for future sessions

- PostgreSQL remains authoritative. Milvus vectors and Redis cache/memory artifacts are derived and remain generation/pipeline fenced.
- Generic roles such as customer, khách hàng, agent, and nhân viên provide target context but cannot become a named entity or owner filter by themselves.
- `semanticQuery` and `clarificationRepair` are internal metadata contracts. Only trusted semantic frames from eligible terminal evidence states may be inherited, and clarification repair applies only to the immediately preceding turn.
- The fresh-image suite can receive setup HTTP 429 responses if a previous run leaves Redis `ratelimit:*` keys; clearing only that disposable namespace restores test isolation without touching conversation caches.

### Related docs

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/worker-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/plans/0 - project overview.md`
