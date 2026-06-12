# Documentation Explanation

## Structure

```text
docs/
├── PROJECT_PLAN.md                 <- Planning index
├── explanations/
│   ├── backend-explanation.md      <- Backend structure and runtime behavior
│   ├── documentation-explanation.md <- Documentation rules and layout
│   ├── frontend-explanation.md     <- Frontend structure and meeting workflow
│   └── infrastructure-explanation.md <- Compose and infrastructure runtime
├── plans/
│   ├── 0 - project overview.md     <- Project-wide source of planning context
│   ├── 1 - repository foundation.md
│   ├── 2 - local runtime and infrastructure.md
│   ├── 3 - meeting upload and core records.md
│   ├── 4 - processing pipeline.md
│   ├── 5 - retrieval and chat.md
│   ├── 6 - admin and operations.md
│   └── 7 - hardening.md
└── rules/
    ├── update-explanation.md       <- Rule for keeping explanation docs current
    └── update-planning.md          <- Rule for keeping phase plans current
```

Root documentation and project files now include:

```text
AGENTS.md                           <- Project rules for AI/code sessions
README.md                           <- Product and architecture hub
docker-compose.yml                  <- Local runtime wiring
.env.example                        <- Runtime configuration template
.dockerignore                       <- Docker build context ignores
.gitignore                          <- Local artifact and secret ignores
infras/                             <- Gateway and monitoring configs
frontend/                           <- Vite React frontend service
```

## Planning Rule

`docs/plans/` is the canonical roadmap directory.

- `0 - project overview.md` stores project-wide context, structure, runtime info, explanation docs, and phase summary.
- Phase files `1+` store objectives, prerequisites, task checklists, verification plans, acceptance criteria, and completion reports.
- Plan files are updated when phase status, project structure, runtime behavior, ports, services, environment variables, or explanation files change.

`docs/PROJECT_PLAN.md` is only an index pointing to the canonical plan files.

## Explanation Rule

`docs/explanations/*-explanation.md` files describe how each project area works based on current source code and config.

When code/config changes affect future understanding, update the matching explanation file:

- Backend changes map to `docs/explanations/backend-explanation.md`.
- Infrastructure changes map to `docs/explanations/infrastructure-explanation.md` when that area exists.
- Frontend changes map to `docs/explanations/frontend-explanation.md` when that area exists.
- Worker changes map to `docs/explanations/worker-explanation.md` when that area exists.
- Documentation structure/rule changes map to `docs/explanations/documentation-explanation.md`.

Explanation docs should describe current implemented behavior, not planned behavior.

## Project Rule Entry Point

`AGENTS.md` references the project-local rules:

- `docs/rules/update-planning.md`
- `docs/rules/update-explanation.md`

Future sessions should apply these rules for code, config, runtime, and documentation changes.

## README Style Rule

When `README.md` is created or updated, apply the `readme-style` skill.

Required README cadence:

1. Hero section.
2. System overview.
3. System flow using Mermaid diagrams.
4. Concise Quick Start with executable commands.
5. Application pipelines.
6. Deployment profiles.
7. Repository map.
8. Documentation index.
9. `Notes On Accuracy`.

The README should behave as a high-level navigation hub, not exhaustive documentation. It should use a centered hero, badge line, quick navigation, concise tables, short definitive prose, and technical honesty. It must document only behavior and pipelines verified against current source code, and it must clearly mark optional, incomplete, or planned capabilities.

## Frontend Structure Rule

When frontend work starts, apply the `frontend-feature-layered-structure` skill.

Expected Vite/React shape:

```text
frontend/src/
├── routes/                 <- Thin framework-native route composition
├── features/               <- Business feature modules
│   └── <feature>/
│       ├── api/            <- Backend request functions
│       ├── dtos/           <- Runtime validation, mapping, payload builders
│       ├── hooks/          <- Fetch lifecycle and UI orchestration
│       ├── screens/        <- Route-level feature composition
│       ├── states/         <- Reusable/non-trivial state transitions
│       ├── types/          <- TypeScript compile-time contracts
│       └── components/     <- Feature-local presentational UI
├── components/             <- Shared UI across unrelated features
├── layouts/                <- Shared page/app shells
├── styles/                 <- Global CSS and design tokens
├── utils/                  <- Pure cross-feature helpers
├── assets/                 <- Shared static assets, if needed
└── main.tsx                <- Vite app entrypoint
```

Only create a frontend layer when it has real code. Do not add dry placeholder folders. Routes should stay thin; screens should compose hooks/state/components rather than own API calls or complex transitions.

*Document reflects project state at **Phase 3 - Meeting Upload And Core Records** after frontend implementation and frontend explanation docs were added.*
