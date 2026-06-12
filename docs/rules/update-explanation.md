# Rule: Keep Explanation Docs Current

`docs/explanations/*-explanation.md` files describe how each project area works. Keep them aligned with source changes so future AI sessions can understand the repo quickly.

## Documentation mapping

When source code changes, update the matching explanation file under `docs/explanations/`.

**Mapping convention:** each top-level directory or major component maps to `docs/explanations/<area>-explanation.md`.

- Scan the project root to identify top-level directories and major components.
- For each changed area, look for (or create) a matching `docs/explanations/<area>-explanation.md`.
- Infrastructure-related files (e.g. Docker, CI/CD, deployment configs) map to `docs/explanations/infrastructure-explanation.md`.
- If a change introduces a new major service or tool, create a new `docs/explanations/<area>-explanation.md` for it.
- If a change touches multiple areas, update each matching explanation file.

## When to update

Update explanation docs when a change affects future understanding of structure, behavior, operations, or integration.

Required updates:

- Add/remove/rename important files or folders.
- Add/remove/change public APIs, routes, endpoints, CLI args, env vars, ports, or generated files.
- Change runtime behavior: startup, shutdown, cleanup, logs, process ownership, container resources, safety scope.
- Change business logic or cross-service flow.
- Add/remove dependencies in any package manifest (e.g. `pom.xml`, `package.json`, `requirements.txt`, `go.mod`, `Cargo.toml`, etc.).
- Change DB migrations, seed data, tables, indexes, or default accounts.
- Change auth/security, secrets handling, or credentials policy.
- Change AI/ML model selection, model path fallback, detection/inference flow, storage upload, alert flow, or worker threading.
- Add runner scripts or change how local tools are executed.

Usually skip updates for:

- Tiny bug fixes that do not change external behavior or future-session context.
- Pure formatting changes.
- Internal refactors with no name/signature/behavior/config/runtime change.
- Log text changes that do not alter operations.
- Test-only changes unless they document important behavior or setup.

When unsure, prefer a short doc update over stale docs.

## What to update inside an explanation file

### 1. Structure tree

If files/folders changed, update the ASCII tree.

Keep entries short:

```text
├── src/main.py         <- App entrypoint
└── src/configs/        <- Runtime/model config
```

Do not list generated/local artifacts unless users must know they are created/ignored.

### 2. Behavior sections

Update the section that explains the changed behavior:

- Request/response flow.
- Runtime lifecycle.
- Worker/thread flow.
- Storage/DB/queue flow.
- Cleanup behavior.
- Env/config behavior.
- CLI usage.

Prefer concise source-derived descriptions. Do not invent future features.

### 3. Tables and examples

Update tables/code blocks when the source changes:

- Endpoint tables.
- CLI arguments.
- Env var tables.
- Dependency tables.
- Port/resource tables.
- Example commands.
- Payload examples.

Examples must match current source defaults.

### 4. Footer

Each explanation file ends with a phase/status footer, for example:

```markdown
*Document reflects project state at **Phase N**. ...*
```

Update the footer when:

- The file content changes materially.
- The project phase changes.
- The footer describes outdated behavior.

Keep the existing language/style of the doc unless the user asks to translate it.

## Order of operations

For code/config behavior changes:

1. Implement the source change.
2. Verify the source change with the smallest relevant check.
3. Update matching explanation file(s).
4. Check the updated section/footer.
5. Update `docs/plans/0 - project overview.md` and the current phase file if structure, phase, runtime behavior, ports, services, or explanation files changed.
6. Final response must mention docs/planning updates, or explicitly say they were not needed.

## Consistency rules

- Source of truth is current code/config, not older docs.
- Do not document behavior that is not implemented.
- Do not leave old filenames, old ports, old service names, or old cleanup behavior in docs.
- Do not create new documentation files unless a new major area needs one or the user asks.
- Keep docs explanatory, not a chronological changelog.
- Preserve project language/style in existing docs unless asked otherwise.
