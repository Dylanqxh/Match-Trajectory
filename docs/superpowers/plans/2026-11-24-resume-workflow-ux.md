# Resume Workflow UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build distinct intake, generation, and document workspaces with dual material entry and a preview-first editor layout.

**Architecture:** Keep the single React shell and existing API, but derive one of three workspaces from current resume/job state. Serialize structured form content into the existing `source_text` contract and use focused components for entry selection and document view controls.

**Tech Stack:** React 19, TypeScript, Vitest, native CSS, FastAPI contract unchanged.

**Spec:** `docs/superpowers/specs/2026-11-24-resume-workflow-ux-design.md`

## Global Constraints

- Node `>=22.12.0 <23`; do not lower the project engine requirement.
- Do not access or add image, video, or audio behavior.
- Keep the generation API, evidence gates, model protocols, and export rendering unchanged.
- Combined `source_text` must be at most 20,000 characters before a job is created.
- Switching material paths or workspaces must not clear user input.
- Do not display synthetic percentage progress.

## Review Focus

- A user with only structured education or one structured experience can generate instead of receiving an empty framework.
- Uploaded text plus structured fields cannot silently drop either source or exceed the API limit unnoticed.
- Selecting an old generate job while a resume is open still opens the dedicated generation workspace.
- A failed/waiting generation remains recoverable without returning to or clearing the intake form.
- Preview focus remains usable at desktop, tablet, and narrow widths without trapping editor actions.

---

### Task 1: Dual material entry and source composition

**Files:**
- Create: `web/src/materialSource.ts`
- Create: `web/src/materialSource.test.tsx`
- Create: `web/src/MaterialSourcePanel.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/styles.css`

**Interfaces:**
- Produces: `MaterialPath = "upload" | "form"`; `buildGenerationSource(uploadedText: string, content: Content): string`; `MaterialSourcePanel` props for selected path and structured content edits.
- Consumes: existing `Content`, `MaterialIntake`, and `ResumeEditor` interfaces.

- [ ] **Step 1: Write failing material source tests**

Test that both entry routes render as peer choices, the selected path exposes the correct editor, and `buildGenerationSource` preserves uploaded text plus non-empty education/summary/experience fields while omitting empty fields.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `npm run test:web -- web/src/materialSource.test.tsx`
Expected: FAIL because `materialSource` and `MaterialSourcePanel` do not exist.

- [ ] **Step 3: Implement source composition and the dual-entry panel**

Use stable plain-text headings, preserve both paths across switching, and reuse `ResumeEditor` for the blank-form route. In `App.generate`, validate the composed length and submit it as `source_text`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `npm run test:web -- web/src/materialSource.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add docs/superpowers/specs/2026-11-24-resume-workflow-ux-design.md docs/superpowers/plans/2026-11-24-resume-workflow-ux.md web/src/materialSource.ts web/src/materialSource.test.tsx web/src/MaterialSourcePanel.tsx web/src/App.tsx web/src/styles.css
git commit -m "feat: restore dual resume material paths"
```

### Task 2: Dedicated generation workspace and stage cards

**Files:**
- Create: `web/src/workspaceView.ts`
- Create: `web/src/workspaceView.test.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/GenerationPanel.tsx`
- Modify: `web/src/executionTrace.tsx`
- Modify: `web/src/executionTrace.test.tsx`
- Modify: `web/src/styles.css`

**Interfaces:**
- Consumes: Task 1 intake state and existing `GenerationSummary.mode`.
- Produces: `resolveWorkspaceView(recordOpen: boolean, job: GenerationSummary | undefined, jobId: string | null): "intake" | "generation" | "document"`; dedicated `.generation-workspace`; stage-card trace markup retaining real workflow edges.

- [ ] **Step 1: Write failing workspace and trace tests**

Test intake/document/generate-job routing, including a selected generate job while a resume is open. Extend trace assertions to require icon stage cards, status text, optional branch copy, and no percentage.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `npm run test:web -- web/src/workspaceView.test.ts web/src/executionTrace.test.tsx`
Expected: FAIL because workspace routing and stage-card markup do not exist.

- [ ] **Step 3: Implement the dedicated generation workspace**

Remove generation-panel embedding from the intake form and document canvas for generate jobs. Render one task workspace with a return-to-materials action and redesign the trace into icon cards plus honest branch/recovery information.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `npm run test:web -- web/src/workspaceView.test.ts web/src/executionTrace.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add web/src/workspaceView.ts web/src/workspaceView.test.ts web/src/App.tsx web/src/GenerationPanel.tsx web/src/executionTrace.tsx web/src/executionTrace.test.tsx web/src/styles.css
git commit -m "feat: add dedicated generation workspace"
```

### Task 3: Preview-first document workspace

**Files:**
- Create: `web/src/DocumentViewToolbar.tsx`
- Create: `web/src/DocumentViewToolbar.test.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/styles.css`

**Interfaces:**
- Consumes: document workspace from Task 2.
- Produces: `DocumentView = "split" | "preview" | "edit"`; accessible view toolbar; `document-view-*` layout classes.

- [ ] **Step 1: Write the failing toolbar test**

Render each state and assert three controls, selected-state semantics, and the requested next view callback.

- [ ] **Step 2: Run focused test and verify RED**

Run: `npm run test:web -- web/src/DocumentViewToolbar.test.tsx`
Expected: FAIL because the toolbar does not exist.

- [ ] **Step 3: Implement preview-first layouts**

Default to a wider preview column, add the toolbar, hide the non-focused pane in preview/edit modes, center the A4 sheet in preview focus, and keep narrow-screen single-column behavior.

- [ ] **Step 4: Run focused and full frontend verification**

Run: `npm run test:web -- web/src/DocumentViewToolbar.test.tsx`
Expected: PASS.

Run: `npm run test:web && npm run typecheck && npm run build`
Expected: all commands exit 0 with no test failures or TypeScript errors.

- [ ] **Step 5: Run the available backend regression command**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: PASS, or an explicitly recorded pre-existing Windows WMI/SQLAlchemy environment failure matching the baseline before this frontend-only change.

- [ ] **Step 6: Commit**

```powershell
git add web/src/DocumentViewToolbar.tsx web/src/DocumentViewToolbar.test.tsx web/src/App.tsx web/src/styles.css
git commit -m "feat: make resume preview the primary workspace"
```

