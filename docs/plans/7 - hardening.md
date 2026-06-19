# Phase 7 - Hardening

## Status: Done

## Objectives

1. Strengthen security, privacy, and operational reliability.
2. Add test coverage around high-risk flows.
3. Define retention, deletion, and audit behavior.
4. Add real account authentication with `Admin` and `User` roles.
5. Add account-scoped uploaded file storage and safe meeting-session deletion.
6. Replace the temporary sidebar context UI with account-aware navigation and file storage UX.

## Prerequisites

- [x] Core upload, processing, retrieval, chat, and admin flows are implemented.
- [x] Main runtime is stable enough for end-to-end verification.

## Tasks

### Authentication And Roles

- [x] Add account registration for local users.
- [x] Add login/logout/session or token flow owned by the backend.
- [x] Add `GET /api/me` to return current account and product role.
- [x] Replace development header-only auth in the frontend with backend-issued auth state.
- [x] Keep development headers available only as a clearly documented local fallback if still needed.
- [x] Support exactly two product roles for this phase:
  - [x] `Admin` can access admin metrics.
  - [x] `Admin` can delete meeting sessions and trigger cascading cleanup.
  - [x] `Admin` can delete other accounts and trigger cascading cleanup for their sessions, meetings, and stored files.
  - [x] `User` can create/upload/process/chat with their own meetings and view their own uploaded files.
  - [x] `User` cannot access admin metrics or delete meeting sessions.
- [x] Enforce all role checks in backend dependencies/services, not in the frontend.
- [x] Prevent an admin from deleting or demoting their own active account.
- [x] Block account deletion while any target meeting is actively processing.
- [x] Revoke queued processing jobs before deleting target meetings.
- [x] Invalidate admin metrics cache after destructive admin deletion.

### Meeting Session Deletion

- [x] Add backend endpoint for deleting a meeting session.
- [x] Restrict meeting session deletion to `Admin`.
- [x] On session deletion, remove or tombstone all related authoritative and derived data:
  - [x] meeting record and processing jobs.
  - [x] meeting asset metadata.
  - [x] uploaded object bytes in MinIO.
  - [x] processed JSON result.
  - [x] processed JSON and retrieval chunks.
  - [x] Milvus vectors for the meeting.
  - [x] chat sessions and messages.
- [x] Make deletion idempotent and safe to retry.
- [x] Record audit events for meeting session deletion success and failure.

### Account File Storage

- [x] Add an account file library that lists files uploaded by the current account.
- [x] Store file metadata with owner/account, object key, content type, size, upload time, and linked meeting/session when present.
- [x] Add backend endpoint to list current account files.
- [x] Add backend endpoint to play/download an owned file through backend authorization.
- [x] Add backend endpoint to delete an owned file only when it is not linked to an existing meeting session.
- [x] If a file is linked to an existing meeting session, return a safe conflict response and instruct the UI to delete the session first.
- [x] When an `Admin` deletes a meeting session, delete the linked file bytes and metadata as part of the cascade.
- [x] Add tests that file deletion cannot bypass the meeting-session reference rule.

### Frontend Account And File UX

- [x] Add login and registration screens.
- [x] Add account display in the app shell/sidebar using the authenticated backend account.
- [x] Remove the temporary context panel from the primary sidebar UI.
- [x] Replace the freed sidebar context space with the account file library.
- [x] Let users select an uploaded file from the library and play it when authorized.
- [x] Let users delete an uploaded file only when backend says it is not linked to an active meeting session.
- [x] Ask for confirmation before deleting an uploaded file.
- [x] Show a clear conflict state when a file cannot be deleted because its meeting session still exists.
- [x] Show admin-only UI affordances for metrics dashboard and meeting-session deletion.
- [x] Ask for confirmation before deleting a meeting session.
- [x] Add admin account management actions for role changes and account deletion.
- [x] Ask for confirmation before deleting an account.
- [x] Keep frontend role display as UX only; backend remains authoritative.

### Security And Privacy

- [x] Add audit events for registration, login, logout, upload, file playback/download, file delete, meeting session delete, and admin metrics access.
- [x] Define retention policy for raw audio, transcripts, and chat history.
- [x] Ensure logs do not include full transcripts, prompts, credentials, or user tokens.
- [x] Review private object download behavior and presigned URL lifetimes.
- [x] Store passwords with PBKDF2-HMAC-SHA256 password hashing.
- [x] Ensure auth tokens/session cookies are not logged.
- [x] Decide local token storage behavior and document the security tradeoff.

### Reliability

- [x] Add idempotency tests for upload and processing.
- [x] Add worker retry and failure-path tests.
- [x] Add authorization tests across meeting and admin endpoints.
- [x] Add deletion cleanup tests for object storage where applicable.
- [x] Add auth tests for registration, login, role enforcement, and `GET /api/me`.
- [x] Add role tests for `Admin` vs `User` access to metrics and meeting deletion.
- [x] Add admin account-management tests for role update, self-change protection, account deletion, and self-delete protection.
- [x] Add account-deletion tests for processing-lock conflict, queued-job revoke, lock release, and metrics-cache invalidation.
- [x] Add file library tests for blocked delete when linked and delete success when unlinked.
- [x] Add cascading meeting-session deletion tests covering PostgreSQL metadata, MinIO object deletion, Milvus delete call, and chat/retrieval/result cleanup.

### Documentation

- [x] Update all explanation docs to match final behavior.
- [x] Mark completed phases with verification evidence.

## Verification Plan

### Automated Tests

- [x] Run backend test suite.
- [x] Run frontend TypeScript/Vite build.
- [x] Run worker-related backend tests.
- [x] Run targeted auth/role tests.
- [x] Run targeted file library and deletion cleanup tests.

### Manual Verification

- [x] Complete an end-to-end auth, meeting upload, file library, admin metrics, and admin deletion check through the gateway.
- [x] Confirm deletion/retention behavior matches documented policy.
- [x] Register/login as `User`, upload an account file, and see it in the account file library API/UI state.
- [x] Confirm `User` cannot open admin metrics or delete a meeting session.
- [x] Login as `Admin`, open metrics, delete a meeting session, and confirm linked file metadata is removed.
- [x] Confirm file delete is blocked while its meeting session exists.
- [x] Confirm an unlinked owned file can be deleted from the file library.
- [x] Confirm admin account deletion removes the target account and target-owned stored files.

### Acceptance Criteria

- [x] High-risk permission and retry paths are tested.
- [x] Retention and audit behavior are documented and implemented.
- [x] Plan and explanation docs match the source.
- [x] Users can register, login, logout, and see their account information in the UI.
- [x] Backend enforces `Admin`/`User` roles for metrics and meeting-session deletion.
- [x] Backend enforces `Admin`/`User` roles for account role management and account deletion.
- [x] Account file storage is usable from the UI and safely scoped by account.
- [x] File deletion and meeting-session deletion follow the documented reference and cleanup rules.
- [x] File, meeting-session, and account deletion actions ask for confirmation before the frontend sends delete requests.
- [x] Temporary frontend context controls are replaced by account-aware UI.

---

## Completion Report

> **Completed at:** 2026-06-17
> **Verified by:** Backend unittest suite, frontend TypeScript/Vite build, Compose config/migration checks, and gateway smoke test.

### What was implemented

- Added backend-owned local account registration, login, logout, bearer sessions, `GET /api/me`, and `Admin`/`User` role normalization.
- Updated public registration so new accounts are always created as `User`; Admin role changes are handled by the admin account dashboard.
- Kept development header auth as a local fallback when no bearer token is present.
- Consolidated PostgreSQL to one local-dev baseline migration, `0001_initial_schema`.
- Kept 9 business tables: `users`, `account_sessions`, `audit_events`, `meetings`, `meeting_assets`, `processing_jobs`, `meeting_intelligence_results`, `meeting_chunks`, and `chat_messages`.
- Added account file APIs for list, upload, authorized playback/download, and safe delete.
- Added admin-only meeting session deletion that removes meeting records, processing jobs, assets, processed JSON, retrieval chunks, chat history, linked file metadata/object bytes, and derived Milvus vectors.
- Replaced the temporary frontend context panel with login/register UI, account-aware shell, account file library, authenticated API calls, admin dashboard gating, and admin meeting delete controls.
- Added admin account management UI/API for listing accounts and changing another account's role with self-role-change protection.
- Added admin account deletion UI/API for deleting another account, with self-delete protection and cleanup of target-owned sessions, files, and meeting artifacts.
- Hardened admin account deletion with Redis processing locks, best-effort Celery revoke by job ID, single account-delete transaction scope for meeting cleanup, and admin metrics cache invalidation.
- Added shared in-app confirmation prompts before destructive file, meeting-session, and account deletion actions in the frontend, replacing browser-native confirm dialogs.
- Added URL-backed frontend routing for `/auth`, `/meetings`, `/meetings/:meetingId`, `/admin/metrics`, and `/admin/accounts`.
- Split the admin portal into independent metrics and account-management screens/hooks; `/admin` redirects to `/admin/metrics`.
- Kept Login/Register as tabs on the shared `/auth` route, made `/meetings` the authenticated landing page, and replaced separate admin navbar links with one right-side Admin Portal dropdown visible only to `Admin`.
- Moved account identity out of the Meetings content area and into a navbar account hover/focus dropdown beside logout, showing display name, email, and role.
- Updated the account trigger to show the account display name and distinct Admin/User icons instead of a generic icon with a role label.
- Added audit events for auth, upload, file playback/delete, admin metrics access, meeting session deletion, account role changes, and account deletion.

### What was changed from original plan

- Local registration no longer exposes role selection and defaults to `User`. Enterprise invite/approval flows remain outside this phase.
- Frontend stores the local bearer token in `localStorage` for developer ergonomics; backend authorization remains authoritative.
- Direct file deletion is blocked while an existing meeting session references the file. Admin meeting deletion is the cleanup path for linked files.

### Notes for future sessions

- Add stricter account provisioning before shared production use, such as invite-only Admin creation or SSO.
- Add retention jobs when the product needs automatic expiration rather than explicit admin/user deletion.
- Add more UI-level automated tests when a browser test runtime is available.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/explanations/worker-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/plans/0 - project overview.md`

### 2026-06-18 account deletion update

- Added `DELETE /api/admin/accounts/{userId}` for admin-only deletion of another account.
- Added account-deletion cleanup tests and re-ran the full backend suite: `73` tests passed.
- Rebuilt backend/frontend images and restarted `backend`, `frontend`, and `nginx`.
- Re-ran frontend TypeScript/Vite build after destructive-confirmation UI changes.
- Moved cross-feature frontend components, layouts, and styles under `frontend/src/shared/`.

### 2026-06-18 production-grade account deletion update

- Added `task_id=job_id` for meeting-processing Celery tasks so queued jobs can be revoked by ID.
- Enabled Celery remote control for targeted revoke while keeping worker gossip/mingle disabled.
- Added Redis processing-lock checks to admin meeting/account deletion.
- Added safe `409` conflicts when deletion would race an active worker.
- Invalidated the Redis admin metrics snapshot after admin meeting/account deletion.
- Added targeted tests for lock conflict, queued-job revoke, lock release, and metrics-cache invalidation.
- Re-ran full backend suite: `75` tests passed.

### 2026-06-18 frontend routing update

- Added React Router and URL-backed auth, meetings, selected-meeting, admin metrics, and admin accounts routes.
- Added guest, authenticated, and Admin route guards.
- Set `/admin/metrics` as the default admin portal page through the `/admin` redirect.
- Split admin metrics and account management into independent screens and hooks so each route loads only its own data.
- Verified frontend build and direct gateway access for every route.

### 2026-06-18 infrastructure configuration update

- Added source-controlled runtime configs for PostgreSQL, Redis, RabbitMQ, etcd, and Milvus under `infras/`.
- Mounted every service config read-only from Compose while keeping credentials and environment-specific values in `.env`.
- Kept MinIO command/environment configured in Compose without an unnecessary standalone config directory.
- Recreated the stateful containers without deleting named volumes.
- Verified custom PostgreSQL config/HBA, Redis AOF and memory policy, RabbitMQ management/Prometheus plugins, existing etcd member data, and the existing Milvus `meeting_chunks` collection.

### 2026-06-18 long voice processing reliability update

- Confirmed a queued long MP3 job waited for the prior worker task and was then consumed correctly; the failure was model runtime timeout, not RabbitMQ/Celery queue ordering.
- Added duration-aware ASR/diarization subprocess timeouts through `ASR_TIMEOUT_REALTIME_FACTOR`.
- Compacted LLM analysis prompts and increased the local Ollama fallback analysis timeout to `600` seconds.
- Reprocessed `test4` successfully to `READY` with a persisted processed JSON result.

### 2026-06-19 processed JSON UI preference update

- Changed the Processed JSON collapsible sections from hard-coded default-open behavior to a browser-local UI preference.
- Closing `Summary`, `Analysis`, `Quality`, or another processed JSON section now remains respected when switching meeting sessions.
- Re-ran the frontend TypeScript/Vite build successfully.

### 2026-06-19 PostgreSQL schema consolidation update

- Replaced the multi-step local migration chain with one baseline migration: `0001_initial_schema`.
- Reset the local development PostgreSQL schema as approved and reapplied the baseline migration.
- Reduced durable business tables to 9: `users`, `account_sessions`, `audit_events`, `meetings`, `meeting_assets`, `processing_jobs`, `meeting_intelligence_results`, `meeting_chunks`, and `chat_messages`.
- Removed the old `workspaces`, `workspace_members`, `account_files`, `transcript_segments`, `meeting_insights`, and `chat_sessions` tables.
- Moved account file-library metadata into standalone `meeting_assets` rows with `meeting_id = NULL`.
- Kept processed transcript and insight details authoritative in `meeting_intelligence_results.result_json`; only `meeting_chunks` remains as the derived PostgreSQL retrieval index.
- Stored chat history directly by `chat_messages.meeting_id`; one meeting is one chat thread.
- Re-ran backend unittest discovery: `62` tests passed.
- Re-ran frontend TypeScript/Vite build successfully.
- Verified ORM metadata has exactly 9 business tables and PostgreSQL has those 9 tables plus `alembic_version`.
- Recreated backend and worker containers; both reported healthy, and gateway `/api/health` returned `200 OK`.

### 2026-06-18 worker queue and local LLM recovery update

- Fixed Celery 5.6 remote-control compatibility with RabbitMQ 4 by explicitly permitting its transient non-exclusive pidbox queues.
- Replaced the worker's RabbitMQ socket-only healthcheck with a targeted Celery ping that detects a stopped consumer.
- Added separate local fallback timeout/context settings and compacted analysis prompt metadata without removing the authoritative transcript from processed JSON.
- Recovered the orphaned `test2` job and verified it moved from `PENDING` to `RUNNING` and finally `SUCCEEDED`; the meeting reached `READY`.
- Added a separate Celery Beat scheduler and durable `processing-maintenance` queue with an isolated direct exchange/routing key for stale `PENDING` job reconciliation.
- Added persistent delivery, late acknowledgment, worker-loss rejection, Redis reconciliation locking, stale-job cooldown metadata, and configurable scan interval/threshold/batch size.
- Verified Beat automatically sent reconciliation after 60 seconds and the worker completed it from the maintenance path.
- Added transaction rollback and authoritative row reload before worker failure-state persistence.
- Re-ran the complete backend suite after reconciliation hardening: `82` tests passed.
