# Rule: Keep Project Plans Current

`docs/plans/` is the project roadmap directory. Each phase has its own file, making it easy to track progress and provide context for future AI sessions.

## Directory structure

```text
docs/plans/
├── 0 - project overview.md        <- Tong quan du an, tech stack, cau truc tong the
├── 1 - setup infrastructure.md    <- Phase 1
├── 2 - build core features.md     <- Phase 2
├── 3 - integrate ai models.md     <- Phase 3
└── ...
```

### File naming convention

- Format: `<n> - <short description>.md`
- `n` is the phase number starting from `0`.
- Phase `0` is always the **project overview** - not a work phase.
- Short description uses lowercase, spaces between words.
- Examples: `1 - setup infrastructure.md`, `2 - build authentication.md`

## Phase 0 - Project overview file

`docs/plans/0 - project overview.md` contains project-level information shared across all phases:

```markdown
# Project Overview

## Tech Stack
- Language/runtime, frameworks, databases, queues, storage, AI/ML, etc.

## Project Structure
<ASCII tree of top-level directories and key files>

## Connection & Runtime Info
| Resource     | Detail           |
|-------------|------------------|
| Port(s)     | ...              |
| UI URL      | ...              |
| Env vars    | ...              |
| Credentials | ...              |

## Explanation Files
- `docs/explanations/<area>-explanation.md` - Description

## Phase Summary
| Phase | Name                     | Status |
|-------|--------------------------|--------|
| 1     | Setup infrastructure     | Done |
| 2     | Build core features      | In progress |
| 3     | Integrate AI models      | Pending |
```

Update this file when:

- Tech stack, project structure, or connection info changes.
- A phase starts, finishes, or is added/removed.
- A new explanation file is created.

## Phase file template (Phase 1+)

Each phase file follows this structure:

```markdown
# Phase N - <Name>

## Status: Pending | In Progress | Done

## Objectives
Clear, measurable goals for this phase:
1. <Objective 1>
2. <Objective 2>

## Prerequisites
What must be ready before starting this phase:
- [ ] <Prerequisite from previous phase or external>
- [ ] <Dependency, tool, config, etc.>

## Tasks
Detailed checklist of everything needed:

### <Group/Component 1>
- [ ] Task description - brief context or rationale
- [ ] Task description
  - [ ] Sub-task if needed

### <Group/Component 2>
- [ ] Task description
- [ ] Task description

## Verification Plan

### Automated Tests
- [ ] <Test command or script to run>
- [ ] <Expected result>

### Manual Verification
- [ ] <Manual check description>
- [ ] <Expected behavior>

### Acceptance Criteria
- [ ] <Criterion 1 - how to confirm the objective is met>
- [ ] <Criterion 2>

---

## Completion Report
> **Completed at:** <date>
> **Verified by:** <method - e.g. unit tests, manual test, CI pipeline>

### What was implemented
- <Summary of completed work>

### What was changed from original plan
- <Any deviations, additions, or removals>

### Notes for future sessions
- <Important constraints, gotchas, or context>

### Related docs updated
- [ ] `docs/explanations/<area>-explanation.md`
- [ ] `docs/plans/0 - project overview.md` (phase summary table)
```

## Status labels

| Label | Meaning |
|-------|---------|
| Pending | Not started |
| In Progress | Actively being worked on |
| Done | Implemented and verified |

## When to update

### Update a phase file when:

- Work on that phase begins -> change status to In Progress, start checking off tasks.
- A task is completed -> mark `[x]`.
- New tasks are discovered during implementation -> add them to the checklist.
- Verification steps are executed -> mark test results.
- The phase is fully complete -> fill in the **Completion Report**, change status to Done.

### Update the overview file (`0 - project overview.md`) when:

- A phase status changes.
- Project structure, tech stack, or connection info changes.
- A new phase or explanation file is added/removed.
- Runtime behavior changes: ports, services, env vars, credentials.

### Create a new phase file when:

- A new major milestone or work area is identified.
- Number it sequentially after existing phases.
- Add the phase to the summary table in the overview file.

### Do NOT update plan files for:

- Tiny internal fixes that do not affect roadmap or future-session context.
- Pure formatting or log text changes.
- Test-only changes unless they affect setup or documented behavior.

## Order of operations

For code/config behavior changes:

1. Implement the source change.
2. Verify with the smallest relevant check.
3. Update matching `docs/explanations/*-explanation.md`.
4. Update the current phase file in `docs/plans/` - check off tasks, add notes.
5. If the phase is now complete:
   a. Fill in the **Completion Report** section.
   b. Change the phase status to Done.
   c. Update the phase summary table in `0 - project overview.md`.
6. Final response must mention which plan/docs files were updated, or explicitly say they were not needed.

## Consistency rules

- Source of truth is current code/config, not older docs.
- Do not claim a phase is Done if verification steps were skipped.
- Do not leave stale info (old ports, old file names, old services) in plan files.
- Do not invent roadmap status; derive it from completed work.
- If docs and source conflict, trust source, then update docs.
- Keep plan files actionable and goal-oriented, not a chronological changelog.
- Preserve the existing language/style of plan files unless asked to change.
- Task items should be concrete and actionable, not vague aspirations.
