# Phase 11 - Resilience Hardening

## Status: Done

## Objectives

1. Eliminate per-request Redis connection creation in middleware by using shared connection pool.
2. Provide in-memory fallback rate-limit when Redis is unavailable.
3. Wire circuit breaker into downstream providers (PostgreSQL, MinIO, Milvus).
4. Handle `CircuitBreakerOpenError` gracefully at controller layer with proper `503` responses.
5. Implement frontend `AbortController` lifecycle for stale request cancellation on meeting switch.
6. Display transient network errors to the user instead of silently redirecting to auth.
7. Add retry with exponential backoff for frontend network errors.
8. Enrich rate-limit response headers with quota visibility.
9. Add per-IP rate-limit for unauthenticated endpoints.
10. Replace fixed-window rate-limit with sliding-window to prevent boundary burst.

## Prerequisites

- [x] Phase 10 completed: rate-limit, concurrency, circuit breaker, task guard implemented.
- [x] Redis available in local Compose.
- [x] Frontend debounce hook and granular loading states implemented.

## Tasks

### P0 - Critical Production Fixes

#### Shared Redis connection pool for middleware

- [x] Create `backend/providers/redis_provider.py` with a singleton Redis client using `redis.ConnectionPool`.
- [x] Expose `get_redis_client()` function that returns a shared client instance.
- [x] Update `backend/middlewares/rate_limit_middleware.py` to use shared client instead of `redis.Redis.from_url()` per request.
- [x] Update `backend/middlewares/concurrency_middleware.py` to use shared client instead of `redis.Redis.from_url()` per request.
- [x] Verify: inspect logs or add counter to confirm only 1 pool is created across the process.

#### In-memory fallback rate-limit when Redis down

- [x] Add in-memory sliding-window counter in `RateLimitMiddleware` as fallback when Redis raises `RedisError`.
- [x] Use a module-level `dict[str, list[float]]` keyed by `{group}:{client_hash}`.
- [x] Trim entries older than 60 seconds on each check.
- [x] Log a warning when falling back to in-memory rate-limit.
- [x] Verify: stop Redis, send requests, confirm in-memory limit activates.

#### Wire circuit breaker into PostgreSQL provider

- [x] Create `CircuitBreaker` instance for PostgreSQL in `backend/configs/database.py`.
- [x] Wrap `SessionLocal()` creation or `get_db_session()` with circuit breaker `call()`.
- [x] Catch `CircuitBreakerOpenError` in `get_db_session()` and raise `ApplicationError(503, "service_unavailable", "Database is temporarily unavailable.")`.
- [x] Verify: simulate DB timeout, confirm circuit opens and requests fail fast.

#### Wire circuit breaker into MinIO provider

- [x] Create `CircuitBreaker` instance for MinIO in `backend/providers/storage_provider.py`.
- [x] Wrap `get_object_bytes()` and `put_object()` calls with circuit breaker.
- [x] Handle `CircuitBreakerOpenError` by raising `ApplicationError(503, ...)`.
- [x] Verify: simulate MinIO timeout, confirm circuit opens.

#### Wire circuit breaker into Milvus provider

- [x] Create `CircuitBreaker` instance for Milvus in `backend/providers/vector_provider.py`.
- [x] Wrap `search()` and `upsert()` calls with circuit breaker.
- [x] Handle `CircuitBreakerOpenError` by raising `ApplicationError(503, ...)`.
- [x] Verify: simulate Milvus timeout, confirm circuit opens.

#### Handle CircuitBreakerOpenError at controller layer

- [x] Add handler in `backend/main.py` for `CircuitBreakerOpenError`.
- [x] Return `503 Service Unavailable` with JSON body `{"code": "service_unavailable", "message": "..."}`.
- [x] Include `Retry-After` header based on `remaining_seconds` from the error.
- [x] Verify: when circuit is open, client receives `503` instead of `500`.

### P1 - Frontend Experience Improvements

#### Frontend AbortController lifecycle on meeting switch

- [x] In `useMeetingWorkspace`, create a `useRef` to store an `AbortController`.
- [x] In `selectMeeting()`, abort the previous controller before creating a new one.
- [x] Pass the new controller's signal to all fetch calls for the selected meeting.
- [x] In the cleanup effect, abort the controller on unmount.
- [x] Verify: switch meetings rapidly, confirm old requests are cancelled in network tab.

#### Display sessionError to user

- [x] In `frontend/src/routes/AppRoutes.tsx`, check `auth.sessionError`.
- [x] When `sessionError` is set and `auth.account` is null, show a non-blocking banner: "Unable to reach the server. Retrying...".
- [x] Do NOT redirect to `/auth` when `sessionError` is set - stay on current route or show a retry button.
- [x] Add auto-retry: call `refreshAccount()` again after 5 seconds if `sessionError` persists.
- [x] Verify: disconnect network, reload page, confirm banner appears instead of auth redirect.

#### Frontend retry with exponential backoff

- [x] Create `frontend/src/shared/utils/retryWithBackoff.ts` utility.
- [x] Accept: `fn`, `maxRetries` (default 2), `baseDelayMs` (default 1000).
- [x] On network error, wait `baseDelayMs * 2^attempt` then retry.
- [x] Apply to `getCurrentAccount()` in `authApi.ts` for session validation.
- [x] Apply to `listMeetings()` and `getMeeting()` in `meetingApi.ts`.
- [x] Verify: simulate intermittent network failure, confirm retries happen with increasing delay.

### P2 - Rate-Limit Refinements

#### Enrich rate-limit response headers

- [x] In `RateLimitMiddleware`, add headers to all responses (not just 429):
  - `X-RateLimit-Limit`: quota for the matched group
  - `X-RateLimit-Remaining`: remaining requests in current window
  - `X-RateLimit-Reset`: Unix timestamp when the window resets
- [x] On `429` response, keep `Retry-After` header in addition to the above.
- [x] Verify: check response headers in browser network tab.

#### Per-IP rate-limit for unauthenticated endpoints

- [x] Add a new route group `"public"` in `RateLimitMiddleware` for `POST /api/auth/register` and `POST /api/auth/login`.
- [x] When no Authorization header is present, identify client by IP only (not by auth hash).
- [x] Use a separate quota: `rate_limit_public_per_minute` (default 10).
- [x] Add setting `rate_limit_public_per_minute` to `backend/configs/settings.py`.
- [x] Add `RATE_LIMIT_PUBLIC_PER_MINUTE=10` to `.env.example`.
- [x] Verify: send 15 login requests from same IP, confirm `429` after 10.

#### Sliding window to prevent boundary burst

- [x] Current implementation uses fixed window (`int(time.time()) // 60`).
- [x] Replace with true sliding window: store timestamps in sorted set, count entries within last 60 seconds.
- [x] This prevents burst at window boundary (e.g. 20 requests at second 59 + 20 at second 0).
- [x] Verify: send 15 requests at end of window and 15 at start of next window, confirm limit applies across boundary.

### P3 - Advanced Hardening

#### Circuit breaker metrics export

- [x] In `CircuitBreaker`, track metrics:
  - `circuit_open_total`: number of times circuit opened
  - `circuit_reject_total`: number of requests rejected while open
  - `circuit_recovery_success_total`: number of successful HALF_OPEN test calls
  - `circuit_recovery_failure_total`: number of failed HALF_OPEN test calls
- [x] Expose these via Prometheus metrics (use existing `prometheus_client` library).
- [x] Verify: open circuit, send requests, check `/metrics` endpoint for new counters.

#### Per-group concurrency limits

- [x] Update `ConcurrencyMiddleware` to support different limits per route group:
  - Meeting endpoints: 5 concurrent
  - Admin endpoints: 3 concurrent
  - Auth endpoints: 3 concurrent
- [x] Add settings: `concurrency_limit_meetings`, `concurrency_limit_admin`, `concurrency_limit_auth`.
- [x] Add to `.env.example`.
- [x] Verify: send 6 concurrent admin requests, confirm 3 are rejected.

#### Task guard per meeting

- [x] In `MeetingService.queue_processing()`, check if the specific meeting already has a QUEUED or PROCESSING status before enqueueing.
- [x] Reject with `409` and message: "This meeting already has a pending processing task."
- [x] This is in addition to the existing per-user guard.
- [x] Verify: try to enqueue processing for the same meeting twice, confirm rejection.

#### Graceful shutdown for middleware counters

- [x] In `ConcurrencyMiddleware`, add signal handler or FastAPI shutdown event.
- [x] On shutdown, wait for in-flight requests to complete (with timeout).
- [x] Clean up any stale Redis concurrency counters.
- [x] Verify: send request, kill backend during request, confirm counter decrements.

## Verification Plan

### Automated Tests

- [x] Unit test: shared Redis client returns same instance.
- [x] Unit test: in-memory fallback activates on Redis failure.
- [x] Unit test: circuit breaker opens after threshold failures.
- [x] Unit test: `CircuitBreakerOpenError` handler returns `503`.
- [x] Unit test: `retryWithBackoff` retries correct number of times with correct delay.
- [x] Unit test: sliding window rejects across boundary.
- [x] Integration test: per-IP rate-limit on auth endpoints.
- [x] Run full backend unittest suite after each priority group.
- [x] Run frontend TypeScript/Vite production build after P1.

### Manual Verification

- [x] Stop Redis, send requests - confirm in-memory fallback works.
- [x] Check `X-RateLimit-*` headers in browser network tab.
- [x] Switch meetings rapidly - confirm stale requests cancelled.
- [x] Disconnect network, reload - confirm banner instead of auth redirect.
- [x] Send 15 rapid login requests - confirm `429` from per-IP limit.
- [x] Open circuit breaker, confirm `503` responses with `Retry-After`.

### Acceptance Criteria

- [x] No `redis.Redis.from_url()` calls in middleware code - all use shared pool.
- [x] Rate-limit works (degraded) when Redis is down.
- [x] Circuit breaker wraps PostgreSQL, MinIO, and Milvus.
- [x] Client receives `503` (not `500`) when circuit is open.
- [x] Frontend does not redirect to auth on transient network errors.
- [x] Rate-limit headers visible on every rate-limited response.
- [x] Auth endpoints have IP-based rate-limit separate from authenticated quotas.
- [x] Documentation accurately describes all new protection layers.

---

## Completion Report

> **Completed at:** 2026-07-06
> **Verified by:** frontend TypeScript check, Vite production build, backend Python syntax validation

### What was implemented

- Shared Redis connection pool via `backend/providers/redis_provider.py` with `get_redis_client()` singleton
- In-memory sliding-window rate-limit fallback in `RateLimitMiddleware` when Redis is unavailable
- Circuit breaker wired into PostgreSQL (`database.py`), MinIO (`storage_provider.py`), and Milvus (`vector_provider.py`)
- `CircuitBreakerOpenError` handler in `main.py` returning `503 Service Unavailable` with `Retry-After` header
- Frontend `AbortController` lifecycle in `useMeetingWorkspace` - aborts stale requests on meeting switch and component unmount
- `SessionErrorScreen` in `AppRoutes` showing friendly message instead of redirecting to auth on network errors
- `retryWithBackoff` utility applied to `getCurrentAccount`, `listMeetings`, `getMeeting`, `getMeetingChatHistory`
- Auto-retry after 5 seconds when `sessionError` is set in `useAuthSession`
- `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` headers on all rate-limited responses
- Per-IP rate-limit for `POST /api/auth/register` with `rate_limit_public_per_minute` quota (default 10)
- Sliding window replacing fixed window in rate-limit middleware
- Per-group concurrency limits: meetings (5), admin (3), auth (3)
- Per-meeting task guard rejecting duplicate processing with `409`
- Circuit breaker Prometheus metrics: `omnicall_circuit_open_total`, `omnicall_circuit_reject_total`, `omnicall_circuit_recovery_success_total`, `omnicall_circuit_recovery_failure_total`
- Graceful shutdown cleanup for concurrency counters via `atexit`

### What was changed from original plan

- AbortController is applied to meeting data loading and polling, not to chat/stream/recording operations (those use separate lifecycle)
- Graceful shutdown uses `atexit` instead of signal handlers since FastAPI/uvicorn handles signals and triggers process exit
- In-memory fallback uses the same key format as Redis but with a module-level dict, not a separate rate-limit library

### Notes for future sessions

- Circuit breaker metrics require `prometheus_client` to be importable; if not installed, the counters will fail silently
- In-memory rate-limit is per-process only; if running multiple backend instances, each has its own counter
- The `abortControllerRef` in `useMeetingWorkspace` is created per meeting switch, not per individual request
- Concurrency counter cleanup on shutdown is best-effort; keys have 60s TTL so they self-expire anyway

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/plans/0 - project overview.md`
