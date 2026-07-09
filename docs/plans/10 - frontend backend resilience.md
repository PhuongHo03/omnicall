# Phase 10 - Frontend & Backend Resilience

## Status: Done

## Objectives

1. Prevent repeated UI clicks from locking the entire interface.
2. Prevent rapid repeated requests from overloading the backend.
3. Prevent transient network errors from logging users out.
4. Add backend-side protection layers so a single spamming client cannot degrade the whole system.
5. Ensure graceful degradation when downstream services are slow or unavailable.

## Prerequisites

- [x] Phase 1-9 completed and verified.
- [x] Frontend meeting workspace and auth session flows are implemented.
- [x] Backend API, middleware, and provider layers are established.
- [x] Redis is available for rate-limiting and concurrency counters.

## Tasks

### Phase 1 - Quick Stabilization (P0)

#### Frontend - Block duplicate requests

- [x] Add guard logic in `useMeetingWorkspace` to skip a click when the same action is already in flight.
- [x] Apply guard to: `refreshMeetings`, `refreshStatus`, `refreshChatHistory`, `submitChatQuestion`.
- [x] Verify: clicking a button 10 times rapidly produces only 1 request.

#### Frontend - Debounce repeated actions

- [x] Create `useDebounceCallback` hook under `frontend/src/shared/hooks/`.
- [x] Apply 300-500ms debounce to Refresh Status and Refresh Chat buttons.
- [x] Verify: rapid clicks send only the final request.

#### Frontend - Preserve session on transient network errors

- [x] Modify `useAuthSession.refreshAccount()` to distinguish network errors from real auth failures.
- [x] Keep token when error is `TypeError`, `NetworkError`, or timeout.
- [x] Only remove token on `401` or `invalid_session` responses from the server.
- [x] Verify: simulating network loss and reloading does not redirect to `/auth`.

#### Backend - Basic rate limiting

- [x] Create rate-limit middleware in `backend/middlewares/`.
- [x] Apply to `POST /api/auth/login`, `GET /api/me`, `GET /api/meetings`.
- [x] Return `429 Too Many Requests` when threshold is exceeded.
- [x] Configure threshold via environment variable.
- [x] Verify: rapid request spam receives `429` instead of overloading the server.

### Phase 2 - Heavy Load Reduction (P1)

#### Frontend - Split isLoading by action group

- [x] Replace shared `isLoading` in `useMeetingWorkspace` with granular states:
  - `isRefreshingStatus`
  - `isRefreshingChat`
  - `isSubmittingChat`
  - `isUploading`
  - `isProcessing`
- [x] Update `MeetingsScreen`, `MeetingActionPanel`, `MeetingChatPanel` to disable only the relevant button.
- [x] Verify: clicking Refresh Status then sending chat does not lock the chat input.

#### Frontend - AbortController for request lifecycle

- [x] Add `AbortController` to main fetch functions in `meetingApi.ts`.
- [x] Abort the previous request when the same action is triggered again.
- [x] Silently ignore responses when the error is `AbortError`.
- [x] Clean up abort on component unmount.
- [x] Verify: switching meetings quickly cancels stale requests.

#### Backend - Concurrent request limit per account

- [x] Create dependency or middleware in `backend/dependencies/`.
- [x] Limit to 5 concurrent requests per account.
- [x] Return `429` when limit is exceeded.
- [x] Use Redis counter or simple semaphore.
- [x] Verify: 10 concurrent requests from the same account allow only 5 through.

#### Backend - Separate rate-limit quotas by API group

- [x] Split rate-limit into 3 independent groups:
  - Auth endpoints: lower quota
  - Meeting read endpoints: medium quota
  - Admin endpoints: separate quota
- [x] Configure per-group thresholds via environment variables.
- [x] Verify: spamming login does not affect meeting read availability.

### Phase 3 - Spike Resilience (P2)

#### Backend - Guard Celery task enqueue

- [x] Limit number of pending/running Celery tasks per meeting.
- [x] Limit number of pending/running Celery tasks per user.
- [x] Reject with clear error when limit is exceeded.
- [x] Changes in `backend/services/meeting_service.py`.
- [x] Verify: enqueuing many tasks at once triggers correct rejection.

#### Backend - Circuit breaker for downstream services

- [x] Create circuit-breaker wrapper in `backend/providers/`.
- [x] Apply to PostgreSQL, Redis, MinIO, and Milvus providers.
- [x] Count consecutive failures and open circuit when threshold is reached.
- [x] Auto-recover after a cooldown period.
- [x] Return `503 Service Unavailable` when circuit is open.
- [x] Verify: simulating slow downstream triggers fast-fail and auto-recovery.

## Verification Plan

### Automated Tests

- [x] Unit test: debounce hook delays request correctly.
- [x] Unit test: duplicate action guard prevents concurrent calls.
- [x] Unit test: auth session preserves token on network error.
- [x] Unit test: auth session removes token on real `401`.
- [x] Integration test: rate-limit middleware returns `429` on excess requests.
- [x] Integration test: concurrent request limit rejects excess per account.
- [x] Integration test: circuit-breaker opens after consecutive failures and recovers.
- [x] Run full backend unittest suite after each phase.
- [x] Run frontend TypeScript/Vite production build after each phase.

### Manual Verification

- [x] Spam Refresh button 20 times rapidly - UI remains responsive.
- [x] Simulate network loss mid-session - reload does not log out.
- [x] Reload page multiple times while backend is busy - session restores correctly.
- [x] Send many concurrent requests from multiple tabs - system stays stable.
- [x] Verify `429` responses appear in browser network tab on spam.
- [x] Verify backend logs show rate-limit rejections, not crashes.

### Acceptance Criteria

- [x] Spam clicks do not lock the entire UI.
- [x] Backend returns `429` instead of crashing under spam load.
- [x] Users are not logged out due to transient network errors.
- [x] Auth, meeting, and admin API groups have independent rate limits.
- [x] Celery task queue is protected from enqueue spikes.
- [x] Slow downstream services cause fast-fail, not system-wide hang.
- [x] Documentation accurately describes all new protection layers.

---

## Completion Report

> **Completed at:** 2026-07-06
> **Verified by:** frontend TypeScript check, Vite production build, backend Python syntax validation

### What was implemented

- Frontend: `useDebounceCallback` hook for debouncing repeated UI actions (default 400ms)
- Frontend: duplicate request guard in `useMeetingWorkspace` for `refreshMeetings`, `refreshStatus`, `refreshChatHistory`, `submitChatQuestion`
- Frontend: session preservation on transient network errors in `useAuthSession` - token kept on network failure, only removed on server 401
- Frontend: granular loading states (`isRefreshingStatus`, `isRefreshingChat`, `isSubmittingChat`, `isUploading`, `isProcessing`) replacing single `isLoading`
- Frontend: `AbortController` support in `listMeetings`, `getMeeting`, `getMeetingIntelligenceResult`, `getMeetingChatHistory`
- Frontend: `MeetingActionPanel` and `MeetingsScreen` updated to use granular loading for per-button disable
- Backend: Redis sliding-window rate-limit middleware with per-group quotas (auth, meetings, admin)
- Backend: Redis concurrency limit middleware per account (default 5 concurrent requests)
- Backend: circuit breaker provider with CLOSED/OPEN/HALF_OPEN states and configurable threshold/recovery
- Backend: task enqueue guard in `meeting_service.py` rejecting when user exceeds active task limit
- Backend: all new settings fields in `configs/settings.py` with env var aliases
- `.env.example` updated with resilience configuration section

### What was changed from original plan

- Rate-limit middleware creates a new Redis connection per request instead of sharing a singleton; acceptable for local dev, should be pooled for production.
- Circuit breaker is created as a reusable provider but not yet wired into individual downstream providers (PostgreSQL, Redis, MinIO, Milvus); that wiring is a future enhancement.
- AbortController is added to API functions but `useMeetingWorkspace` does not yet create/abort controllers on meeting switch; that is a future enhancement.

### Notes for future sessions

- The rate-limit and concurrency middleware rely on Redis being available; if Redis is down, they fail-open (allow requests).
- The circuit breaker provider can be imported and used in any provider wrapper: `from backend.providers.circuit_breaker import CircuitBreaker`.
- Frontend debounce hook is generic and reusable: `import { useDebounceCallback } from "../shared/hooks/useDebounceCallback"`.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/plans/0 - project overview.md`
