# Agent Workflow Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship low-friction contextual Agent editing, visible multi-Agent execution progress, and remove the unused legacy chat surface.

**Architecture:** Keep LangGraph as the centralized generation Coordinator. Make contextual edit application and undo append-only, revision-checked operations in `AgentService`; render generation trace as a frontend projection; keep upload extraction stateless.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/SQLite, React 19, TypeScript, Vitest, Pytest.

**Spec:** `docs/superpowers/specs/2026-11-14-agent-workflow-convergence-design.md`

## Global Constraints

- Preserve existing dirty-worktree changes from the previous resume-quality iteration.
- Every behavior change follows RED-GREEN TDD.
- Never delete `data/`, successful exports, dependencies, portable builds, IDE settings or legacy job adapters.
- Upload parsing behavior and local-origin/session protection remain unchanged.
- Push only after the full verification matrix passes.

## Review Focus

- A manual save racing with Agent auto-apply must win; Agent returns conflict without overwriting it.
- Undo after any later manual save must fail without changing the latest content.
- A blocked candidate must not save and must not lock the user out of a clarifying message.
- Generated-task auto-apply must not create orphan Agent jobs on conflict.
- Repeated stage receipts must not render duplicate user-facing trace steps.

---

### Task 1: Auto-apply and append-only undo

**Files:**
- Modify: `tests/test_resume_agent.py`
- Modify: `app/resume_agent.py`
- Modify: `app/main.py`

**Interfaces:**
- Produces: `AgentService.post(...) -> {session, resume?}` and `AgentService.undo(session_id) -> {session, resume}`.
- Preserves: evidence gates, target hash checks, `AgentService.create/get` session shape.

- [ ] Write failing service and API tests for safe auto-apply, blocked follow-up, stale apply, undo and stale undo.
- [ ] Run focused tests and verify they fail because `post` still returns a proposal and `undo` is absent.
- [ ] Implement auto-apply, stored undo metadata, append-only undo and the `/undo` route; remove public apply/discard routes.
- [ ] Run `python -m pytest tests/test_resume_agent.py -q` and verify pass.

### Task 2: Conversational UI with immediate update and undo

**Files:**
- Modify: `web/src/AgentPanel.test.tsx`
- Modify: `web/src/AgentPanel.tsx`
- Modify: `web/src/api.ts`
- Modify: `web/src/styles.css`

**Interfaces:**
- Consumes: Task 1 response `{session, resume?}` and `/api/agent/sessions/{id}/undo`.
- Produces: no apply/discard UI; successful message refreshes the active resume and exposes undo.

- [ ] Write failing component tests for auto-applied response, blocked follow-up and undo.
- [ ] Run focused Vitest and verify expected failures.
- [ ] Implement message/undo response handling and compact applied-change UI.
- [ ] Run focused Vitest and TypeScript checks.

### Task 3: Human-readable multi-Agent execution trace

**Files:**
- Create: `web/src/executionTrace.ts`
- Create: `web/src/executionTrace.test.ts`
- Modify: `web/src/GenerationPanel.tsx`
- Modify: `web/src/styles.css`

**Interfaces:**
- Consumes: `GenerationJob.step_receipts`, `stage`, and `state`.
- Produces: `executionTrace(job)` with deduplicated completed/current user labels.

- [ ] Write failing pure-function tests for normal flow, revision loop, repeated receipts and waiting input.
- [ ] Run focused Vitest and verify module/function absence.
- [ ] Implement the projection and render it in `GenerationPanel`.
- [ ] Run focused Vitest and TypeScript checks.

### Task 4: Remove legacy chat and preserve stateless upload

**Files:**
- Create: `tests/test_upload_api.py`
- Modify: `web/src/MaterialIntake.tsx`
- Modify: `web/src/api.ts`
- Modify: `app/main.py`
- Delete: `app/chat.py`
- Delete: `tests/test_chat_api.py`

**Interfaces:**
- Produces: `POST /api/uploads` returning the existing extraction result without persistence.
- Removes: `/api/chat/sessions`, `/api/chat/sessions/{id}`, `/api/chat/sessions/{id}/messages`, `/api/chat/uploads` and unused ChatSession types.

- [ ] Write upload API tests against `/api/uploads` and verify the new route fails.
- [ ] Add the stateless route and migrate `MaterialIntake`; run focused Python/web checks.
- [ ] Move retained upload/intake coverage, then delete legacy chat implementation and obsolete tests/types.
- [ ] Run all upload, intake, API and Agent tests.

### Task 5: Documentation, safe cleanup, verification and publication

**Files:**
- Modify: `README.md`
- Modify: `docs/简历Agent架构设计方案.md`
- Delete only verified reproducible cache directories/files under ignored paths.

**Interfaces:**
- Documents the centralized multi-Agent design and auto-version/undo interaction.

- [ ] Update current behavior, architecture wording and test counts without claiming real-provider quality.
- [ ] Audit tracked and ignored files; delete only obsolete tracked chat code and verified caches.
- [ ] Run full Pytest, Ruff, Vitest, TypeScript, Vite build and `git diff --check`.
- [ ] Self-review the whole diff because subagent review is prohibited in this session; fix Important findings with RED-GREEN tests.
- [ ] Commit the complete current iteration and push the current feature branch to `origin`.
