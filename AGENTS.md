# AGENTS.md - Omnicall Project Rules

## Project Documentation Rules

Apply these project-local rules when changing code, config, runtime behavior, or documentation:

- `docs/rules/update-planning.md`
- `docs/rules/update-explanation.md`

In short:

- Keep roadmap and phase status in `docs/plans/`.
- Keep source-derived explanations in `docs/explanations/`.
- For code/config behavior changes, update the relevant explanation docs and current phase plan after verification.
- Final responses must mention which plan/docs files were updated, or explicitly say no docs update was needed.
- When creating or updating `README.md`, apply the `readme-style` skill.

## Architecture Notes

Use the software boundary rules already established for Omnicall:

- Frontend owns presentation and user interaction only.
- When building frontend code, apply the `frontend-feature-layered-structure` skill:
  - Preserve framework-native routing, e.g. Vite/React routes under `frontend/src/routes/`.
  - Put business features under `frontend/src/features/<feature>/`.
  - Use feature layers only when they have real code: `api`, `dtos`, `hooks`, `screens`, `states`, `types`, and feature-local `components`.
  - Keep root-level frontend folders limited to truly shared code such as `components`, `layouts`, `styles`, `utils`, and `assets`.
  - Keep screens mostly compositional; API calls go in `api`, runtime validation/mapping in `dtos`, orchestration in `hooks`, reusable state transitions in `states`, and feature-only UI in feature `components`.
- Backend owns business logic, validation, authorization, and durable state coordination.
- Worker owns async processing and retryable side effects.
- Gateway owns public routing and edge concerns.
- PostgreSQL is the durable source of truth.
- MinIO stores file bytes.
- Redis stores temporary/cache/lock/idempotency data.
- RabbitMQ delivers async tasks.
- Milvus stores derived vector embeddings, not authoritative business truth.
- Prometheus stays internal and is queried through backend admin APIs.

## README Style

When `README.md` is created or updated, use the project README style:

- Treat it as a product landing page inside GitHub Markdown.
- Start with a centered hero section, tagline, dense `for-the-badge` badges, and quick navigation links.
- Prefer tables and short sections over long paragraphs.
- Include system overview, Mermaid system flow, concise executable Quick Start, application pipelines, deployment profiles, repository map, documentation index, and `Notes On Accuracy`.
- Document only behavior and pipelines verified against the source.
- Keep tone objective and technical; mark optional, incomplete, or planned capabilities clearly.
