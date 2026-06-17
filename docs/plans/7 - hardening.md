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
- [x] Add `GET /api/me` to return current account, role, and workspace/account context.
- [x] Replace development header-only auth in the frontend with backend-issued auth state.
- [x] Keep development headers available only as a clearly documented local fallback if still needed.
- [x] Support exactly two product roles for this phase:
  - [x] `Admin` can access admin metrics.
  - [x] `Admin` can delete meeting sessions and trigger cascading cleanup.
  - [x] `User` can create/upload/process/chat with their own meetings and view their own uploaded files.
  - [x] `User` cannot access admin metrics or delete meeting sessions.
- [x] Enforce all role checks in backend dependencies/services, not in the frontend.

### Meeting Session Deletion

- [x] Add backend endpoint for deleting a meeting session.
- [x] Restrict meeting session deletion to `Admin`.
- [x] On session deletion, remove or tombstone all related authoritative and derived data:
  - [x] meeting record and processing jobs.
  - [x] meeting asset metadata.
  - [x] uploaded object bytes in MinIO.
  - [x] processed JSON result.
  - [x] transcript segments, insights, and retrieval chunks.
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
- [x] Show a clear conflict state when a file cannot be deleted because its meeting session still exists.
- [x] Show admin-only UI affordances for metrics dashboard and meeting-session deletion.
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

### Acceptance Criteria

- [x] High-risk permission and retry paths are tested.
- [x] Retention and audit behavior are documented and implemented.
- [x] Plan and explanation docs match the source.
- [x] Users can register, login, logout, and see their account information in the UI.
- [x] Backend enforces `Admin`/`User` roles for metrics and meeting-session deletion.
- [x] Account file storage is usable from the UI and safely scoped by account.
- [x] File deletion and meeting-session deletion follow the documented reference and cleanup rules.
- [x] Temporary frontend context controls are replaced by account-aware UI.

---

## Completion Report

> **Completed at:** 2026-06-17
> **Verified by:** Backend unittest suite, frontend TypeScript/Vite build, Compose config/migration checks, and gateway smoke test.

### What was implemented

- Added backend-owned local account registration, login, logout, bearer sessions, `GET /api/me`, and `Admin`/`User` role normalization.
- Kept development header auth as a local fallback when no bearer token is present.
- Added `account_sessions`, `account_files`, and `audit_events` persistence with Alembic migration `0006_auth_files_audit`.
- Added Alembic migration `0007_normalize_product_roles` to convert legacy `owner` rows to `Admin` and enforce `Admin`/`User` database role constraints.
- Added account file APIs for list, upload, authorized playback/download, and safe delete.
- Added admin-only meeting session deletion that removes meeting records, processing jobs, assets, processed JSON, transcript/insight/chunk rows, chat history, linked account file metadata/object bytes, and derived Milvus vectors.
- Replaced the temporary frontend context panel with login/register UI, account-aware shell, account file library, authenticated API calls, admin dashboard gating, and admin meeting delete controls.
- Added audit events for auth, upload, file playback/delete, admin metrics access, and meeting session deletion.

### What was changed from original plan

- Local registration currently allows choosing `Admin` for development and local operations. Enterprise invite/approval flows remain outside this phase.
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
