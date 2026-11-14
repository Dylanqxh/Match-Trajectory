# Skill and Workspace UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose every maintained resume-writing role safely and turn the first screen into one explicit direction-to-material-to-generation flow.

**Architecture:** Keep the existing workflow and frozen Skill snapshots. Add a shared front-end role-direction definition and picker, expand the backend input contract and loader mapping, then update stage-specific Skill guidance and the existing start screen without changing editor/export lifecycles.

**Tech Stack:** Python 3.12, Pydantic 2, pytest, React 19, TypeScript, Vite, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-12-skill-and-workspace-ux-design.md`

## Global Constraints

- Do not add runtime dependencies or change old tasks' `pinned_role` behavior.
- The form never infers a role direction from a job title.
- Materials still require explicit send consent; name and contact remain local fields.
- Owner, 0-to-1, launch state, team results and causal claims must stay within supplied evidence.
- WMI and `_ssl` environment failures are reported separately from product regressions.

## Review Focus

- A new algorithm/data/operations task must load its matching role resource rather than general.
- An old task pinned to a stored role must ignore a conflicting new direction.
- The form must reject generation before a direction is selected, while `other` remains a valid explicit choice.
- A returning user with `mt_assistant_open=1` may keep the assistant open; a first-time user sees it collapsed.
- The direction cards and primary action must remain usable below the 980px and 760px breakpoints.

---

### Task 1: Complete role-direction routing

**Files:** `app/generation_models.py`, `app/skill.py`, `app/chat.py`, `tests/test_skill.py`, `tests/test_m0_baseline.py`, `tests/test_chat_api.py`

**Interfaces:**
- Consumes: stored role names in `app.skill.STORED_ROLES`.
- Produces: `RoleDirection = product | backend | algorithm | data-analysis | operations | other` across API and Skill loading.

- [ ] Write failing pytest cases for all six directions, pinned-role precedence, and Chinese chat direction parsing.
- [ ] Run the exact new tests and confirm failures are caused by the missing enum/mapping.
- [ ] Expand `GenerationInput.role_direction`, map all explicit directions in `load_skill`, and extend `_direction` without changing old snapshots.
- [ ] Run the targeted tests and the existing Skill/writing-coach suites; expect pass.
- [ ] Commit the routing change.

### Task 2: Absorb evidence-first Skill guidance

**Files:** `skills/resume-writing/SKILL.md`, `skills/resume-writing/references/contract.md`, `skills/resume-writing/references/editorial.md`, `skills/resume-writing/references/claim-audit.md`, `app/skill.py`, `tests/test_writing_coach.py`, `docs/简历Skill设计方案.md`

**Interfaces:**
- Consumes: `SkillBundle.stage_resources` and immutable evidence IDs.
- Produces: review/revise stage bundles containing `references/claim-audit.md` and evidence-first drafting instructions.

- [ ] Write a failing test that review/revise load claim-audit guidance while plan/draft do not, and that the bundle version changes with the stage resources.
- [ ] Run it and confirm the new resource is absent.
- [ ] Add the atomic-claim audit reference and update entry/contract/editorial guidance with source mapping and role/scope/result/causality boundaries.
- [ ] Wire the reference into review/revise only and update the design document with implemented scope.
- [ ] Run Skill, writing-coach and generation-model tests; expect pass.
- [ ] Commit the Skill change.

### Task 3: Rebuild the start-screen hierarchy

**Files:** `web/src/roleDirections.ts`, `web/src/RoleDirectionPicker.tsx`, `web/src/RoleDirectionPicker.test.tsx`, `web/src/App.tsx`, `web/src/ChatPanel.tsx`, `web/src/styles.css`, `package.json`

**Interfaces:**
- Consumes: backend `RoleDirection` string values from Task 1.
- Produces: `RoleDirectionPicker({ value, onChange })` and `ROLE_DIRECTIONS`; App submits only a selected direction.

- [ ] Write a failing Vitest server-render test for six accessible direction choices, specialist helper copy and explicit general fallback.
- [ ] Run the test and confirm the picker module is missing.
- [ ] Add the shared direction definition and picker, then integrate an initially empty direction into `App.generate()` with a validation error.
- [ ] Reorder the start card into direction, materials, consent and action; move secondary fields into one details block; default the assistant closed unless explicitly persisted open.
- [ ] Add responsive styling for direction cards, progress steps and the collapsed assistant.
- [ ] Run Vitest, TypeScript and a Vite build to an isolated output directory; expect pass.
- [ ] Reload the local page and browser-test desktop/narrow layouts, picker interaction, default assistant state and console errors.
- [ ] Commit the UI change.

### Task 4: Integrated verification and documentation

**Files:** `README.md`, optionally `docs/PRD-下一迭代需求.md`

**Interfaces:**
- Consumes: Tasks 1-3 behavior.
- Produces: current usage instructions and a verified change set.

- [ ] Update README direction and first-run instructions without claiming real-model quality improvement.
- [ ] Run targeted backend suites, Vitest, TypeScript, Ruff and isolated Vite build.
- [ ] Attempt the complete project test command; report WMI/_ssl separately if infrastructure blocks it.
- [ ] Inspect `git diff --check`, status and final diff against the spec.
- [ ] Request one whole-change code review, fix Critical/Important findings with RED-GREEN tests, and rerun verification.
- [ ] Commit documentation/fixes and prepare the handoff.

