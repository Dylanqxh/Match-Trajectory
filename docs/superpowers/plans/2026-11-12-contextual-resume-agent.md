# Contextual Resume Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the global material-intake chat with a target-bound resume editing Agent that proposes auditable changes and applies them as new versions, while improving the workbench hierarchy and responsiveness.

**Architecture:** Add a separate persistent `AgentService` whose sessions bind to a resume revision or generated candidate. A model call returns a structured edit candidate; deterministic evidence gates and a recomputed diff produce a proposal, and only an explicit CAS-protected apply writes a new resume version. The React panel follows the selected target and renders conversation plus before/after proposal cards.

**Tech Stack:** FastAPI, SQLAlchemy/SQLite, Pydantic, existing model client and Skill loader, React 19, TypeScript, CSS, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-12-contextual-resume-agent-design.md`

## Global Constraints

- Keep the legacy `/api/chat/*` contract for compatibility, but remove it from the active UI.
- Never send name, contact, school or API keys to the editing model.
- A user instruction is edit intent, not fact evidence.
- No proposal may mutate a resume before explicit apply.
- Apply must use resume revision or job draft hash CAS and preserve version history.
- Agent-applied versions remain unreviewed until the existing review path runs.
- Do not add runtime dependencies.

## Review Focus

- A stale proposal after manual editing must return 409 and leave the new revision unchanged (Task 2).
- A generated task without a candidate must show an unavailable target instead of invoking the model (Task 2 and Task 3).
- Model output that adds an unsupported number or responsibility must be blocked from apply (Task 1).
- Switching targets while a request resolves must not display the old target's proposal in the new panel (Task 3).
- Desktop and 745px layouts must not produce page-level horizontal overflow (Task 4).

---

### Task 1: Structured Agent proposal engine

**Files:**
- Create: `app/resume_agent.py`
- Modify: `app/model_client.py`
- Modify: `app/store.py`
- Test: `tests/test_resume_agent.py`

**Interfaces:**
- Consumes: `ResumeStore`, `JobStore`, `ModelRegistry`, `ModelClient`, `load_skill`, `validate_draft`, `blocking_gates`.
- Produces: `AgentTargetInput`, `AgentMessageInput`, `AgentService.create/get/post/apply/discard` and JSON-safe session views.

- [ ] Write failing unit/integration tests for a resume-bound proposal, hidden header fields, unsupported-fact blocking, and job-candidate materialization.
- [ ] Run the new tests and confirm failures are caused by the missing Agent interfaces.
- [ ] Implement structured model completion for `agent_edit`, target snapshot projection, recomputed diffs, evidence filtering and proposal persistence.
- [ ] Implement apply/discard with revision or draft-hash CAS and `ResumeStore.save`.
- [ ] Run `tests/test_resume_agent.py` and existing model/store tests.
- [ ] Commit the backend proposal engine.

### Task 2: Agent HTTP contract and compatibility

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_resume_agent.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: Task 1 `AgentService` methods and Pydantic inputs.
- Produces: `/api/agent/sessions`, message, apply and discard routes.

- [ ] Add failing API tests for session reuse, target-not-ready, stale apply and unchanged legacy chat endpoints.
- [ ] Run the API tests and confirm expected failures.
- [ ] Wire `AgentService` into `create_app` and add the five Agent routes.
- [ ] Run Agent, API and legacy chat test files.
- [ ] Commit the HTTP contract.

### Task 3: Target-bound Agent panel

**Files:**
- Create: `web/src/AgentPanel.tsx`
- Create: `web/src/AgentPanel.test.tsx`
- Modify: `web/src/api.ts`
- Modify: `web/src/App.tsx`
- Delete: `web/src/ChatPanel.tsx`
- Delete: `web/src/ChatPanel.test.ts`

**Interfaces:**
- Consumes: Task 2 HTTP contract and the current `record`/`jobId` selection from `App`.
- Produces: `AgentPanel({target, modelReady, onOpenSettings, onApplied})`.

- [ ] Write failing tests for empty target, context label, proposal actions and stale async target responses.
- [ ] Run Vitest and confirm failures are caused by the missing panel.
- [ ] Implement target-scoped session loading, messages, quick prompts, proposal diff, apply and discard actions.
- [ ] Replace the global ChatPanel wiring in `App`; prioritize selected job over selected resume and refresh lists after apply.
- [ ] Run Vitest and TypeScript checks.
- [ ] Commit the contextual panel.

### Task 4: Workbench visual hierarchy and responsive UX

**Files:**
- Modify: `web/src/styles.css`
- Modify: `web/src/App.tsx`
- Modify: `web/src/GenerationPanel.tsx`

**Interfaces:**
- Consumes: Task 3 panel class names and existing workbench components.
- Produces: desktop three-zone layout and stacked narrow-screen layout.

- [ ] Add stable semantic labels/classes needed to distinguish navigation, workspace and Agent context.
- [ ] Apply the dark navigation, elevated document canvas, compact toolbar, stronger selected states and Agent proposal styling.
- [ ] Add responsive rules that remove vertical collapsed text and keep controls at usable sizes.
- [ ] Run Vitest, TypeScript and Vite production build.
- [ ] Verify desktop and 745px in the browser: target switching, no overflow, no console errors.
- [ ] Commit the visual redesign.

### Task 5: Documentation and full verification

**Files:**
- Modify: `README.md`
- Modify: `docs/简历Agent架构设计方案.md`

**Interfaces:**
- Consumes: completed Agent behavior.
- Produces: accurate user and architecture documentation.

- [ ] Document target-bound conversations, proposal/apply behavior, versioning and review boundary.
- [ ] Run full backend tests with the Windows platform workaround, Ruff, frontend tests, TypeScript and Vite build.
- [ ] Inspect the full diff, verify the working tree, and commit documentation.

