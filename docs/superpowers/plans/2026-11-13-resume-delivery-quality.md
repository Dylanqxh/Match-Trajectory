# Resume Delivery Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a general-role resume workbench with reliable identity intake, direct export, one-page PDF fitting and useful visual emphasis.

**Architecture:** Preserve the existing structured resume model and evidence gates, but separate advisory review from export authorization. Add conservative deterministic normalization for identity/highlights, and make PDF layout depend on measured browser geometry. Extend the existing universal-plus-role-overlay Skill router rather than adding one-off title logic.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Playwright Chromium, python-docx, React 19, TypeScript, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-11-13-resume-delivery-quality-design.md`

## Global Constraints

- Personal facts only come from uploaded/user material.
- Current editor content is always downloadable; review is advisory.
- Preserve unrelated working-tree changes.
- New behavior follows red-green-refactor.

## Review Focus

- A resume heading must not be mistaken for a name; identity tests include headings and a valid standalone Chinese name.
- A one-page fit must not create a second page or clip the last line; the rendering test checks page count and visible bottom position.
- Direct export must still reject a concurrently changed revision and an entirely blank document.
- Auto-highlighting must only select literal substrings already in the item text and must preserve explicit highlights.
- Unknown job titles must use general rules; frontend and testing titles must select only their own maintained overlays.

---

### Task 1: Conservative identity intake

**Files:**
- Modify: `app/intake.py`
- Test: `tests/test_intake.py`

**Interfaces:**
- Produces: `parse_material(text, purpose="resume") -> dict` with a top-of-document name fallback.

- [ ] Add failing tests for `何明鑫` on the first line and for rejecting `教育背景` as a name.
- [ ] Run the two tests and confirm the missing-name failure.
- [ ] Implement a bounded standalone-name detector; explicit labels retain priority.
- [ ] Run intake tests and confirm they pass.

### Task 2: Direct current-version export

**Files:**
- Modify: `app/exports.py`
- Modify: `web/src/App.tsx`
- Modify: `web/src/exportFlow.ts`
- Test: `tests/test_exports.py`
- Test: `web/src/exportFlow.test.ts`

**Interfaces:**
- Produces: `check_export(record, request)` that enforces revision consistency and nonblank output only.
- Produces: one-click `download(format)` UI behavior without confirm/takeover.

- [ ] Change tests to require direct AI/manual export without confirmation and retain stale-revision/blank guards.
- [ ] Run focused Python and Web tests and confirm the old gates fail.
- [ ] Remove review/confirmation authorization from export and simplify the export panel to PDF/Word actions plus advisory review details.
- [ ] Run focused tests and confirm they pass.

### Task 3: Deterministic emphasis and measured one-page PDF

**Files:**
- Modify: `app/gates.py`
- Modify: `app/rendering.py`
- Modify: `web/src/App.tsx`
- Test: `tests/test_writing_gates.py`
- Test: `tests/test_pdf.py`

**Interfaces:**
- Produces: skill items with a literal category-label highlight when none exists.
- Produces: `render_pdf(...)` that measures and fits content to a single A4 page within readable scale bounds.

- [ ] Add a failing skill-highlight test and a representative rendered-PDF fill test.
- [ ] Run them and confirm empty highlights and large bottom whitespace fail.
- [ ] Add deterministic skill-label highlighting and a bounded geometry fitting pass in Chromium; keep HTML preview on the same fitting script.
- [ ] Run rendering tests, render the current resume, and inspect its PNG.

### Task 4: General role overlays including frontend and testing

**Files:**
- Create: `skills/resume-writing/references/roles/frontend.md`
- Create: `skills/resume-writing/references/roles/testing.md`
- Modify: `skills/resume-writing/examples/writing-boundaries.json`
- Modify: `app/skill.py`
- Modify: `app/generation_models.py`
- Modify: `app/chat.py`
- Modify: `app/resume_agent.py`
- Modify: `web/src/roleDirections.ts`
- Test: `tests/test_skill.py`
- Test: `tests/test_chat_api.py`
- Test: `tests/test_writing_coach.py`
- Test: `web/src/RoleDirectionPicker.test.tsx`

**Interfaces:**
- Produces: maintained `frontend` and `testing` role directions and `infer_role_direction(target_role) -> str`.

- [ ] Add failing backend/UI tests for both directions, general fallback and Agent fallback routing.
- [ ] Run focused tests and confirm schema/router/UI failures.
- [ ] Add the two overlays, examples, enum values and shared inference; preserve explicit direction priority.
- [ ] Run focused tests and confirm they pass.

### Task 5: Repair current record and end-to-end verification

**Files:**
- Modify current local SQLite record only through the store/API save path.
- Delete: `artifacts/inspect_latest.py`

**Interfaces:**
- Consumes all preceding behavior.

- [ ] Save the current resume with extracted name and deterministic skill highlights as a new revision.
- [ ] Build the Web app and restart the local server.
- [ ] Verify in the visible browser that name, bold skill labels and direct PDF/Word buttons are present.
- [ ] Download both formats, render the PDF and DOCX, and visually inspect the pages.
- [ ] Run the full relevant Python/Web suites, typecheck, build, Ruff and `git diff --check`.
