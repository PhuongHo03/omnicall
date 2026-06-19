# Phase 6 - Admin And Operations

## Status: Done

## Objectives

1. Add internal Prometheus metrics scraping.
2. Expose normalized admin metrics through the backend only.
3. Build a frontend admin dashboard with safe refresh behavior.
4. Add a navbar entry that routes admin users to the admin dashboard.
5. Scrape the service and container metrics needed to monitor the local Omnicall stack without adding Grafana.

## Prerequisites

- [x] Phase 2 local runtime is complete.
- [x] Phase 5.5 voice processing and rerank is complete.
- [x] Phase 5.6 local guardrails is complete.
- [x] Admin auth/session boundary exists.
- [x] Prometheus is reachable by backend on the internal network.

## Tasks

### Metrics Backend

- [x] Add Prometheus client abstraction in backend.
- [x] Add `GET /api/admin/metrics`.
- [x] Cache normalized metrics in Redis under `admin:metrics:snapshot` for 10 seconds.
- [x] Require backend admin authorization.

### Dashboard

- [x] Add admin dashboard screen.
- [x] Add a navbar button/link for admin users to open the admin dashboard.
- [x] Refresh metrics every 30 seconds.
- [x] Call only `/api/admin/metrics` from the browser.
- [x] Do not add Grafana; the project frontend is the admin metrics UI.

### Monitoring

- [x] Add backend application metrics at an internal `/metrics` endpoint.
- [x] Add worker/job metrics target for queue and processing visibility.
- [x] Add container-level CPU and memory metrics through the internal Docker stats exporter.
- [x] Add PostgreSQL exporter for database health, connections, transactions, locks, and table/index activity.
- [x] Add Redis exporter for cache/lock health, memory, commands, keyspace, and connections.
- [x] Add RabbitMQ Prometheus metrics for queue depth, consumers, message rates, channels, and node health.
- [x] Add MinIO metrics for object storage health, capacity, request rates, and bucket-level storage where available.
- [x] Add Milvus metrics for vector database health, request latency, insert/search counts, and collection/index status where available.
- [x] Add NGINX metrics for gateway request/connection health using an internal status endpoint and exporter.
- [x] Add Prometheus scrape jobs for backend, worker-derived app metrics, Docker containers, NGINX, PostgreSQL, Redis, RabbitMQ, MinIO, Milvus, etcd, and Prometheus itself.
- [x] Keep exporter ports internal-only with `expose`; only approved local admin UIs may use host-bound `ports`.

## Verification Plan

### Automated Tests

- [x] Add backend tests for admin authorization and cache behavior.

### Manual Verification

- [x] Confirm frontend never calls Prometheus directly.
- [x] Confirm repeated dashboard refresh uses Redis cache when fresh.
- [x] Confirm Prometheus targets for backend, Docker containers, PostgreSQL, Redis, RabbitMQ, MinIO, Milvus, NGINX, etcd, and Prometheus are up.
- [x] Confirm dashboard shows service health and container resource signals needed for local operations.

### Acceptance Criteria

- [x] Prometheus is internal-only.
- [x] Admin metrics are protected by backend auth.
- [x] Admin users can reach the dashboard from the frontend navbar.
- [x] Dashboard covers application, worker, queue, database, cache, object storage, vector database, gateway, and container resource health.
- [x] Dashboard data remains fresh enough for operations.

---

## Completion Report

> **Completed at:** 2026-06-17
> **Verified by:** Compose config, backend tests, backend compile, frontend build, Prometheus target smoke, Docker container metrics smoke, and admin API smoke.

### What was implemented

- Added internal backend `/metrics` with HTTP, latency, meeting, processing job, and chat message gauges/counters.
- Added `GET /api/admin/metrics`, protected by backend admin authorization and normalized through backend DTOs.
- Added Redis-backed 10-second admin metrics cache under `admin:metrics:snapshot`.
- Added Prometheus provider/cache provider/service boundaries for admin metrics.
- Added frontend admin dashboard feature with navbar navigation and 30-second refresh.
- Added Prometheus scrape jobs for backend, Docker container stats, NGINX, PostgreSQL, Redis, RabbitMQ, MinIO, Milvus, etcd, and Prometheus.
- Added Docker stats exporter under `infras/docker-exporter/` for project container CPU and memory metrics.
- Enabled RabbitMQ Prometheus plugin, MinIO public Prometheus metrics, NGINX internal `stub_status`, and exporter services.

### What was changed from original plan

- Grafana was intentionally not added. The project frontend is the admin operations UI.
- cAdvisor was tested but did not expose usable Docker container labels on this machine because Docker storage metadata was not available in the shape it expected. It was replaced with an internal Docker stats exporter that reads the Docker socket read-only and exposes project-scoped container CPU/RAM metrics for Prometheus.

### Notes for future sessions

- Prometheus is still localhost-bound as an admin UI on `${PROMETHEUS_PORT}`, but the browser-facing dashboard does not call it directly.
- The Docker stats exporter is internal-only and reports running containers with `com.docker.compose.project=omnicall`.

### 2026-06-18 admin metrics expansion update

- Expanded `Infrastructure Services` dashboard coverage with PostgreSQL connection states and database size, Redis connected clients, RabbitMQ consumers, MinIO used capacity, etcd database size, Milvus collections, and Milvus stored rows.
- Kept infrastructure metrics grouped under one frontend section while pinning related cards together by row and using semantic row labels for singleton service metrics.
- Rebuilt backend/frontend and refreshed the Redis admin metrics cache after query changes.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/plans/0 - project overview.md`
