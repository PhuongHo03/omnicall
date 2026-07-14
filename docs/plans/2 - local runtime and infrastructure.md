# Phase 2 - Local Runtime And Infrastructure

## Status: Done

## Objectives

1. Run Omnicall services through Docker Compose.
2. Keep public traffic behind NGINX and internal services private.
3. Provide healthchecks and explicit environment configuration.

## Prerequisites

- [x] Phase 1 repository foundation is complete.
- [x] Root `.env.example` exists.

## Tasks

### Compose Runtime

- [x] Add `docker-compose.yml` with explicit required environment variables.
- [x] Add named volumes for PostgreSQL, Redis, RabbitMQ, MinIO, Milvus, and Prometheus data.
- [x] Keep backend, databases, queues, caches, object storage APIs, and vector DB internal via `expose`.
- [x] Bind NGINX through `APP_BIND_IP`.
- [x] Bind admin/debug UIs only through `LOCAL_BIND_IP`.

### Infrastructure Config

- [x] Add NGINX config for `/` and `/api/` routing.
- [x] Add Prometheus scrape config.
- [x] Add service healthchecks.

## Verification Plan

### Automated Tests

- [x] Run Compose config validation.

### Manual Verification

- [x] Start the local stack.
- [x] Confirm only the gateway and approved admin UIs are host-bound.
- [x] Confirm backend health works through `/api/health`.

### Acceptance Criteria

- [x] Local runtime can start repeatably.
- [x] Public/internal service exposure follows project rules.

---

## Completion Report

> **Completed at:** 2026-06-12
> **Verified by:** `docker compose config`, `docker compose ps -a`, and HTTP checks through gateway/admin ports

### What was implemented

- Added Docker Compose runtime for NGINX, backend, PostgreSQL, Redis, RabbitMQ, MinIO, Milvus, Prometheus, Adminer, and RedisInsight.
- Added backend container build through `backend/Dockerfile`.
- Added NGINX gateway config with `/api/` proxying to the internal backend and a temporary `/` readiness response until the frontend exists.
- Added Prometheus config as an internal monitoring service with a placeholder for future backend metrics.
- MinIO no longer uses a Compose init container; backend creates the meeting-assets bucket lazily, and Milvus connects directly to MinIO with `MINIO_BUCKET_NAME`.
- Kept core service protocols internal through `expose`; only NGINX is public through `APP_BIND_IP`.
- Bound admin/debug UIs to `LOCAL_BIND_IP`: Adminer, RedisInsight, RabbitMQ Management, MinIO Console, and Prometheus.
- Reconciled the root `.env` with `.env.example` so retrieval, Agentic RAG, and extraction-window settings are present in both files without duplicate keys.

### What was changed from original plan

- Worker and frontend containers were not added yet because their codebases are not implemented. They remain planned for later phases.
- Local admin/debug UIs are grouped on ports `8081` through `8086`: Adminer, MinIO Console, Milvus WebUI, RedisInsight, RabbitMQ Management, and Prometheus.
- Ollama now runs as a Compose service and backend/worker use `http://ollama:11434` on the internal network.
- Milvus uses `MINIO_ACCESS_KEY_ID` and `MINIO_SECRET_ACCESS_KEY` when connecting to MinIO.

### Notes for future sessions

- Add worker containers after Celery tasks exist in Phase 4.
- Add frontend routing through NGINX after the Vite app exists.
- Add backend `/metrics` scraping only after application metrics are implemented.

### Related docs updated

- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/plans/0 - project overview.md`
- [x] `README.md`
