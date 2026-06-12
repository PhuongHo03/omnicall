# Phase 6 - Admin And Operations

## Status: Pending

## Objectives

1. Add internal Prometheus metrics scraping.
2. Expose normalized admin metrics through the backend only.
3. Build an admin dashboard with safe refresh behavior.

## Prerequisites

- [ ] Phase 2 local runtime is complete.
- [ ] Admin auth/session boundary exists.
- [ ] Prometheus is reachable by backend on the internal network.

## Tasks

### Metrics Backend

- [ ] Add Prometheus client abstraction in backend.
- [ ] Add `GET /api/admin/metrics`.
- [ ] Cache normalized metrics in Redis under `admin:metrics:snapshot` for 10 seconds.
- [ ] Require backend admin authorization.

### Dashboard

- [ ] Add admin dashboard screen.
- [ ] Refresh metrics every 30 seconds.
- [ ] Call only `/api/admin/metrics` from the browser.

### Monitoring

- [ ] Add scrape jobs for backend, worker, NGINX, PostgreSQL, Redis, RabbitMQ, MinIO, and Milvus exporters where available.

## Verification Plan

### Automated Tests

- [ ] Add backend tests for admin authorization and cache behavior.

### Manual Verification

- [ ] Confirm frontend never calls Prometheus directly.
- [ ] Confirm repeated dashboard refresh uses Redis cache when fresh.

### Acceptance Criteria

- [ ] Prometheus is internal-only.
- [ ] Admin metrics are protected by backend auth.
- [ ] Dashboard data remains fresh enough for operations.

---

## Completion Report

> **Completed at:** Not complete yet
> **Verified by:** Pending

### What was implemented

- Pending phase completion.

### What was changed from original plan

- Pending phase completion.

### Notes for future sessions

- None yet.

### Related docs updated

- [ ] `docs/explanations/backend-explanation.md`
- [ ] `docs/explanations/frontend-explanation.md`
- [ ] `docs/explanations/infrastructure-explanation.md`
- [ ] `docs/plans/0 - project overview.md`
