# Phase 10 - Frontend & Backend Resilience

## Status: Pending

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

- [ ] Add guard logic in `useMeetingWorkspace` to skip a click when the same action is already in flight.
- [ ] Apply guard to: `refreshMeetings`, `refreshStatus`, `refreshChatHistory`, `submitChatQuestion`.
- [ ] Verify: clicking a button 10 times rapidly produces only 1 request.

#### Frontend - Debounce repeated actions

- [ ] Create `useDebounceCallback` hook under `frontend/src/shared/hooks/`.
- [ ] Apply 300-500ms debounce to Refresh Status and Refresh Chat buttons.
- [ ] Verify: rapid clicks send only the final request.

#### Frontend - Preserve session on transient network errors

- [ ] Modify `useAuthSession.refreshAccount()` to distinguish network errors from real auth failures.
- [ ] Keep token when error is `TypeError`, `NetworkError`, or timeout.
- [ ] Only remove token on `401` or `invalid_session` responses from the server.
- [ ] Verify: simulating network loss and reloading does not redirect to `/auth`.

#### Backend - Basic rate limiting

- [ ] Create rate-limit middleware in `backend/middlewares/`.
- [ ] Apply to `POST /api/auth/login`, `GET /api/me`, `GET /api/meetings`.
- [ ] Return `429 Too Many Requests` when threshold is exceeded.
- [ ] Configure threshold via environment variable.
- [ ] Verify: rapid request spam receives `429` instead of overloading the server.

### Phase 2 - Heavy Load Reduction (P1)

#### Frontend - Split isLoading by action group

- [ ] Replace shared `isLoading` in `useMeetingWorkspace` with granular states:
  - `isRefreshingStatus`
  - `isRefreshingChat`
  - `isSubmittingChat`
  - `isUploading`
  - `isProcessing`
- [ ] Update `MeetingsScreen`, `MeetingActionPanel`, `MeetingChatPanel` to disable only the relevant button.
- [ ] Verify: clicking Refresh Status then sending chat does not lock the chat input.

#### Frontend - AbortController for request lifecycle

- [ ] Add `AbortController` to main fetch functions in `meetingApi.ts`.
- [ ] Abort the previous request when the same action is triggered again.
- [ ] Silently ignore responses when the error is `AbortError`.
- [ ] Clean up abort on component unmount.
- [ ] Verify: switching meetings quickly cancels stale requests.

#### Backend - Concurrent request limit per account

- [ ] Create dependency or middleware in `backend/dependencies/`.
- [ ] Limit to 5 concurrent requests per account.
- [ ] Return `429` when limit is exceeded.
- [ ] Use Redis counter or simple semaphore.
- [ ] Verify: 10 concurrent requests from the same account allow only 5 through.

#### Backend - Separate rate-limit quotas by API group

- [ ] Split rate-limit into 3 independent groups:
  - Auth endpoints: lower quota
  - Meeting read endpoints: medium quota
  - Admin endpoints: separate quota
- [ ] Configure per-group thresholds via environment variables.
- [ ] Verify: spamming login does not affect meeting read availability.

### Phase 3 - Spike Resilience (P2)

#### Backend - Guard Celery task enqueue

- [ ] Limit number of pending/running Celery tasks per meeting.
- [ ] Limit number of pending/running Celery tasks per user.
- [ ] Reject with clear error when limit is exceeded.
- [ ] Changes in `backend/services/meeting_service.py`.
- [ ] Verify: enqueuing many tasks at once triggers correct rejection.

#### Backend - Circuit breaker for downstream services

- [ ] Create circuit-breaker wrapper in `backend/providers/`.
- [ ] Apply to PostgreSQL, Redis, MinIO, and Milvus providers.
- [ ] Count consecutive failures and open circuit when threshold is reached.
- [ ] Auto-recover after a cooldown period.
- [ ] Return `503 Service Unavailable` when circuit is open.
- [ ] Verify: simulating slow downstream triggers fast-fail and auto-recovery.

## Verification Plan

### Automated Tests

- [ ] Unit test: debounce hook delays request correctly.
- [ ] Unit test: duplicate action guard prevents concurrent calls.
- [ ] Unit test: auth session preserves token on network error.
- [ ] Unit test: auth session removes token on real `401`.
- [ ] Integration test: rate-limit middleware returns `429` on excess requests.
- [ ] Integration test: concurrent request limit rejects excess per account.
- [ ] Integration test: circuit-breaker opens after consecutive failures and recovers.
- [ ] Run full backend unittest suite after each phase.
- [ ] Run frontend TypeScript/Vite production build after each phase.

### Manual Verification

- [ ] Spam Refresh button 20 times rapidly - UI remains responsive.
- [ ] Simulate network loss mid-session - reload does not log out.
- [ ] Reload page multiple times while backend is busy - session restores correctly.
- [ ] Send many concurrent requests from multiple tabs - system stays stable.
- [ ] Verify `429` responses appear in browser network tab on spam.
- [ ] Verify backend logs show rate-limit rejections, not crashes.

### Acceptance Criteria

- [ ] Spam clicks do not lock the entire UI.
- [ ] Backend returns `429` instead of crashing under spam load.
- [ ] Users are not logged out due to transient network errors.
- [ ] Auth, meeting, and admin API groups have independent rate limits.
- [ ] Celery task queue is protected from enqueue spikes.
- [ ] Slow downstream services cause fast-fail, not system-wide hang.
- [ ] Documentation accurately describes all new protection layers.

---

## Completion Report

> **Completed at:** -
> **Verified by:** -

### What was implemented

-

### What was changed from original plan

-

### Notes for future sessions

-

### Related docs updated

- [ ] `docs/explanations/backend-explanation.md`
- [ ] `docs/explanations/frontend-explanation.md`
- [ ] `docs/plans/0 - project overview.md`
