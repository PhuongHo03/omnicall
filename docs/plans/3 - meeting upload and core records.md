# Phase 3 - Meeting Upload And Core Records

## Status: Done

## Objectives

1. Create authenticated meeting records.
2. Store uploaded files in MinIO and metadata in PostgreSQL.
3. Enqueue processing jobs after durable state is written.
4. Expose enough meeting status for the frontend to guide users through upload, queued processing, failures, and retry.

## Prerequisites

- [x] Phase 2 local runtime is complete.
- [x] PostgreSQL migrations are available.
- [x] MinIO bucket configuration is available.

## Tasks

### Backend Core

- [x] Add auth boundary and workspace membership checks.
- [x] Add `users`, `workspaces`, and `workspace_members` migration baseline.
- [x] Add `meetings`, `meeting_assets`, and `processing_jobs` migrations.
- [x] Add database constraints for meeting ownership, workspace membership, asset uniqueness, and job idempotency.
- [x] Add meeting, asset, and processing job models separate from DTOs.
- [x] Add repositories for meeting, asset, and job persistence.
- [x] Add DTOs for meeting creation, asset upload, processing trigger, and status responses.
- [x] Add backend upload validation for content type, extension, size, and meeting state.
- [x] Add backend authorization checks for meeting creation, read, upload, process, and retry.

### Meeting Status

- [x] Represent meeting status as `DRAFT`, `UPLOADED`, `QUEUED`, `PROCESSING`, `READY`, and `FAILED`.
- [x] Represent processing job status as `PENDING`, `RUNNING`, `RETRYING`, `SUCCEEDED`, `FAILED`, and `CANCELLED`.
- [x] Return user-safe failure reason and retry eligibility in meeting status responses.
- [x] Keep internal stack traces and provider errors out of client responses.

### Storage And Queue

- [x] Add storage provider abstraction for MinIO.
- [x] Store uploaded file bytes in MinIO.
- [x] Store asset metadata in PostgreSQL.
- [x] Use namespaced object keys: `workspaces/{workspaceId}/meetings/{meetingId}/uploads/{uuid}.{ext}`.
- [x] Create processing job only after asset metadata is committed.
- [x] Enqueue worker task after database write.
- [x] Use an idempotency key for repeated upload/process requests.
- [x] Ensure failed queue publishing leaves a visible job/meeting state.

### API

- [x] Implement `POST /api/meetings`.
- [x] Implement `GET /api/meetings`.
- [x] Implement `GET /api/meetings/{meetingId}`.
- [x] Implement `POST /api/meetings/{meetingId}/assets`.
- [x] Implement `POST /api/meetings/{meetingId}/process`.
- [x] Implement `GET /api/meetings/{meetingId}/processing-status`.

### Frontend

- [x] Add meeting list screen.
- [x] Add create/upload meeting flow.
- [x] Add browser recording entry point that produces a completed upload asset before live chunking exists.
- [x] Display processing status from backend.
- [x] Display retry action only when backend marks it allowed.
- [x] Keep frontend upload validation as UX-only; backend remains authoritative.

## Verification Plan

### Automated Tests

- [x] Add backend tests for upload validation and authorization.
- [x] Add repository tests for meeting/asset/job persistence.
- [x] Add idempotency tests for duplicate upload/process requests.
- [x] Add API tests for status transitions and safe error responses.

### Manual Verification

- [x] Upload a supported meeting file.
- [x] Confirm MinIO object and PostgreSQL metadata exist.
- [x] Confirm processing job is enqueued.
- [x] Retry an allowed failed processing job and confirm a new valid job path.
- [x] Attempt unauthorized meeting access and confirm backend denies it.

### Acceptance Criteria

- [x] Frontend cannot bypass backend validation.
- [x] Uploaded files are private by default.
- [x] Meeting state is durable before async processing starts.
- [x] All meeting and asset operations are workspace-authorized by backend.
- [x] Upload and processing trigger requests are safe to retry.

---

## Completion Report

> **Completed at:** 2026-06-12
> **Verified by:** `python3 -m compileall backend`, `docker compose --env-file .env.example config`, `alembic upgrade head`, gateway API curl checks, PostgreSQL count check, RabbitMQ queue check, `python -m unittest discover -s backend/tests -v`, `npm run build`, Playwright screenshots, Playwright UI smoke test

### What was implemented

- Implemented the backend portion of Phase 3: dev auth context, workspace membership bootstrap, SQLAlchemy models, Alembic baseline migration, repositories, DTOs, MinIO upload provider, Celery queue provider, and meeting APIs.
- Verified a meeting can be created, a supported `.wav` file can be uploaded to MinIO, asset metadata is persisted in PostgreSQL, and a processing job is enqueued to RabbitMQ.
- Verified unauthenticated meeting list access returns `401`.
- Added automated backend tests for auth headers, workspace scoping, upload validation, upload/process idempotency, persistence, status transitions, visible queue failure, and retry with a new job.
- Added Vite/React frontend with feature-layered meeting workspace UI.
- Added meeting list, create form, file upload, browser recording upload, process/refresh controls, status display, and retry action label controlled by backend `retryAllowed`.
- Routed `/` through NGINX to the frontend while keeping `/api/` routed to backend.

### What was changed from original plan

- Production auth is not implemented yet. Current auth boundary is a development header-based context using `X-User-ID` and `X-Workspace-ID`, with local bootstrap of user/workspace/member records.
- Worker execution is not implemented yet. The backend publishes `omnicall.processing.process_meeting` tasks to RabbitMQ, but no Celery worker service is running this task in Compose yet.
- Frontend uses development auth context fields so the local app can exercise backend workspace authorization before production auth exists.

### Notes for future sessions

- Run migrations after backend rebuilds with `docker compose --env-file .env.example exec -T backend alembic upgrade head`.
- Use `Idempotency-Key` on upload and process requests when clients need retry-safe behavior.
- Add the Celery worker service and real processing task implementation in Phase 4.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/plans/0 - project overview.md`
- [x] `README.md`
