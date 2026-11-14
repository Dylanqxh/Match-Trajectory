# Workbench Navigation, Agent Editing, and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver section-based editing, resume-owned task navigation, safe Agent presentation edits, model diagnostics, visible Agent execution stages, and a reproducible Docker Compose deployment path.

**Architecture:** Keep persisted resume/job schemas compatible and derive navigation groupings at the API/UI boundary. Isolate editor grouping and workspace-tree projection in pure modules, extend Agent diffs to include literal highlights, and package the existing local FastAPI/React application in a loopback-published container.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/SQLite, React 19, TypeScript, Vitest, Pytest, Playwright Chromium, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-11-14-workbench-navigation-agent-and-release-design.md`

## Global Constraints

- Preserve all existing resume, job, version, export, and credential data.
- Agent edits may change presentation and evidence-supported content; unsupported new facts remain blocked.
- The diagnostic script must not echo or persist API keys.
- Container publishing defaults to `127.0.0.1` and must not expose the workbench to the LAN.
- Do not claim real-provider quality or clean-machine portability without direct evidence.
- Every behavior change follows RED-GREEN TDD.

## Review Focus

- Switching editor tabs with unsaved changes must preserve the whole in-memory document; cover in Task 1 component tests.
- Changing a section kind must move it between groups without duplicating or losing it; cover in Task 1 pure-function tests.
- Presentation-only Agent edits must create a version, while non-literal or excessive highlights must fail validation; cover in Task 3 service tests.
- Legacy jobs without a derived resume relation must remain visible in the task inbox; cover in Task 4 grouping tests.
- Container startup must remain local-only and persist `/app/data`; cover in Task 6 configuration tests.

---

### Task 1: Section-based resume editor

**Files:**
- Create: `web/src/editorSections.ts`
- Create: `web/src/editorSections.test.ts`
- Create: `web/src/ResumeEditor.tsx`
- Create: `web/src/ResumeEditor.test.tsx`
- Modify: `web/src/ExperienceFields.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/styles.css`

**Interfaces:**
- Produces: `EditorSectionKey`, `editorSectionCounts(content: Content)`, `sectionKindsFor(key: EditorSectionKey)`.
- Produces: `ResumeEditor({content, disabled, onChange}: ResumeEditorProps)` rendering one active group while mutating the full `Content`.
- Extends: `ExperienceFields` with `visibleKinds: string[]` and `defaultKind: string`.

- [x] Add pure tests for basic, education, work, project, and other grouping/counts, including a kind change that moves one stable section ID.
- [x] Run `npm.cmd run test:web -- editorSections.test.ts` and confirm RED.
- [x] Implement `editorSections.ts` with fixed labels and kind mappings.
- [x] Add server-rendered component tests proving one group is visible at a time and tab switching keeps the supplied full content callback.
- [x] Implement `ResumeEditor`, filtered `ExperienceFields`, App integration, responsive vertical navigation, and empty-group guidance.
- [x] Run focused Vitest and `npm.cmd run typecheck`; confirm GREEN.

### Task 2: Standalone model connection diagnostics

**Files:**
- Create: `tools/test_model_connection.py`
- Create: `tests/test_model_connection_tool.py`
- Modify: `README.md`
- Modify: `app/provider_protocols.py`
- Modify: `tests/test_providers.py`

**Interfaces:**
- Produces: `normalize_endpoint(base_url: str, protocol: str = "openai_compatible") -> str` used by both runtime and diagnostic output.
- Produces: `run_probe(base_url: str, model: str, api_key: str, *, transport=None) -> dict` and an interactive CLI using `getpass.getpass`.

- [x] Add failing tests for base `/v1`, full `/chat/completions`, trailing slash, safe success output, classified failure, and absence of the key from stdout/stderr/files.
- [x] Run `python -m pytest tests/test_model_connection_tool.py tests/test_providers.py -q` and confirm RED.
- [x] Centralize endpoint normalization and implement the diagnostic CLI with interactive prompts plus optional `--base-url` and `--model` flags; never accept the key as a CLI flag.
- [x] Document Windows PowerShell and macOS/Linux invocation and the fact that it tests OpenAI-compatible Chat Completions only.
- [x] Run focused Pytest and Ruff; confirm GREEN.

### Task 3: Agent presentation-only edits

**Files:**
- Modify: `app/resume_agent.py`
- Modify: `app/model_client.py`
- Modify: `tests/test_resume_agent.py`
- Modify: `web/src/AgentPanel.tsx`
- Modify: `web/src/AgentPanel.test.tsx`

**Interfaces:**
- Produces: proposal changes with optional `presentation_before: list[str]` and `presentation_after: list[str]`.
- Preserves: existing CAS apply/undo and evidence gates for semantic changes.

- [x] Add failing service tests for metric-only highlighting, highlight removal, mixed wording/highlight edits, invalid highlights, and unsupported factual additions.
- [x] Run `python -m pytest tests/test_resume_agent.py -q` and confirm presentation-only edits are currently treated as unchanged.
- [x] Preserve validated candidate highlights, include them in diff detection, and exempt only pure presentation changes from new-reference requirements.
- [x] Update the Agent prompt to state that literal highlights are allowed and add UI copy/diff rendering for presentation changes.
- [x] Run focused Python/Web tests and typecheck; confirm GREEN.

### Task 4: Resume-owned workspace navigation

**Files:**
- Modify: `app/jobs.py`
- Modify: `tests/test_store.py`
- Modify: `web/src/api.ts`
- Create: `web/src/workspaceTree.ts`
- Create: `web/src/workspaceTree.test.ts`
- Create: `web/src/WorkspaceSidebar.tsx`
- Create: `web/src/WorkspaceSidebar.test.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/styles.css`

**Interfaces:**
- Extends: `GenerationSummary` with `resume_id: string | null`, `created_at`, and `updated_at`.
- Produces: `buildWorkspaceTree(resumes: Summary[], jobs: GenerationSummary[]) -> {resumes: ResumeNode[]; inbox: GenerationSummary[]}`.
- Produces: `WorkspaceSidebar` callbacks for select/delete resume and select/delete job.

- [x] Add failing backend tests for adopted, recheck, and unmatched job relationships.
- [x] Extend `JobStore.list()` to derive `resume_id` without rewriting stored jobs.
- [x] Add failing grouping tests for one resume with multiple jobs, empty resumes, deleted/missing parents, and unmatched legacy jobs.
- [x] Implement the pure tree and sidebar component with nested resume histories and a separate active-task inbox.
- [x] Replace the two peer lists in `App` and run focused Pytest/Vitest/typecheck; confirm GREEN.

### Task 5: User-facing Agent execution trace

**Files:**
- Modify: `web/src/executionTrace.tsx`
- Modify: `web/src/executionTrace.test.ts`
- Modify: `web/src/styles.css`

**Interfaces:**
- Extends: `AgentTraceItem` with `icon: string` and stable `detail` for completed/current stages.

- [x] Add failing tests for role icons, completed/current wording, repeated receipts, revision loops, and waiting-input state.
- [x] Implement accessible icons, a compact connected timeline, and status labels without exposing raw step IDs or prompts.
- [x] Run focused Vitest and typecheck; confirm GREEN.

### Task 6: Loopback-only Docker Compose deployment

**Files:**
- Create: `Dockerfile`
- Create: `compose.yaml`
- Create: `.dockerignore`
- Modify: `app/cli.py`
- Modify: `tests/test_startup.py`
- Create: `tests/test_deployment_files.py`
- Modify: `README.md`
- Modify: `docs/ENVIRONMENT.md`

**Interfaces:**
- Extends: CLI with `--host` restricted to `127.0.0.1` or `0.0.0.0`; default stays `127.0.0.1`.
- Produces: Compose service `match-trajectory`, host mapping `127.0.0.1:18765:18765`, and persistent volume mounted at `/app/data`.

- [ ] Add failing CLI tests for default host, container host, invalid host, and port fallback behavior.
- [ ] Implement host-aware binding without changing native defaults.
- [ ] Add static deployment tests asserting locked dependency install, built frontend, matching Chromium, CJK font configuration, loopback-only publishing, healthcheck, and persistent data.
- [ ] Implement Dockerfile, Compose, ignore rules, and exact one-command documentation.
- [ ] Run deployment tests and `docker compose config` when Docker CLI is available; record inability to build if no engine exists rather than claiming success.

### Task 7: Full verification and delivery evidence

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-11-14-workbench-navigation-agent-and-release.md`

**Interfaces:**
- Produces: an evidence table separating source tests, local browser verification, container configuration, real provider tests, and clean-machine tests.

- [ ] Run project-scoped Pytest with a fresh basetemp, Ruff, Vitest, TypeScript, Vite build, and `git diff --check`.
- [ ] Start the app with isolated data and verify tabs, task hierarchy, Agent trace, and model-settings UI in the browser with zero console errors.
- [ ] Run the diagnostic tool against a local deterministic OpenAI-compatible fixture; do not use or request a real key for automated verification.
- [ ] Validate Compose configuration and build/start only if the local Docker engine is available.
- [ ] Update README evidence boundaries and mark completed plan checkboxes without claiming unperformed clean-device or real-provider validation.
- [ ] Review the complete diff for data loss, credential exposure, stale task visibility, and responsive layout regressions; fix Important findings with RED-GREEN tests.
