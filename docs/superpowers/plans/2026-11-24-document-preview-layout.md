# Document Preview Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move document review and view controls into a persistent compact left pane so the resume preview receives most of the workspace.

**Architecture:** Add one focused `DocumentWorkspaceControls` component that composes the existing toolbar with optional review state. Restructure the document branch in `App` into a persistent left pane plus preview pane, use CSS view-state classes to hide only the editor body in preview focus, and default the existing Agent rail to its reversible collapsed state.

**Tech Stack:** React 19, TypeScript, Vitest, native CSS

**Spec:** `docs/superpowers/specs/2026-11-24-document-preview-layout-design.md`

## Global Constraints

- Keep Node `>=22.12.0 <23`.
- Do not change review, save, export, preview rendering, or Agent conversation behavior.
- Do not access or add image, video, or audio behavior.
- Do not add dependencies.
- Preserve the untracked user document and unrelated worktree content.

## Review Focus

- Preview focus must keep all three view controls visible so the user can leave that mode.
- A resume without AI review data must not render an empty review action.
- Long review status text must wrap inside the narrow control pane instead of widening it.
- Split mode must give the preview the remaining width after a bounded left pane.
- At widths below 980px, the document workspace must remain usable as one column.
- At a 1234px desktop viewport, the default collapsed Agent must leave materially more than the measured 380px preview-focus width.

---

### Task 1: Persistent left document controls and wider preview

**Files:**
- Create: `web/src/DocumentWorkspaceControls.tsx`
- Create: `web/src/DocumentWorkspaceControls.test.tsx`
- Modify: `web/src/App.tsx:480-515`
- Modify: `web/src/AgentPanel.test.tsx:100-103`
- Modify: `web/src/styles.css:203-234`

**Interfaces:**
- Consumes: `DocumentView`, `DocumentViewToolbar`, a document title/status, and an optional review label/callback.
- Produces: `DocumentWorkspaceControls` with all controls contained in `.document-workspace-controls`; `.document-left-pane` remains present in every view.

- [ ] **Step 1: Write failing component tests**

Assert that `DocumentWorkspaceControls` renders all three view buttons and the review action inside the same control container, invokes both callbacks, wraps the supplied review status, and omits the review action when no review props are supplied.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `npm run test:web -- web/src/DocumentWorkspaceControls.test.tsx`

Expected: FAIL because `DocumentWorkspaceControls` does not exist.

- [ ] **Step 3: Implement the control component and integrate it**

Create `DocumentWorkspaceControls(props)` using the existing `DocumentViewToolbar`. In `App`, compute the existing review label unchanged, place the component before the editor inside `.document-left-pane`, remove the two cross-workspace control rows, and make `preferredAgentCollapsed` return the collapsed default unless the user has explicitly toggled it.

- [ ] **Step 4: Implement the responsive layout**

Use a bounded split left column, a narrow persistent preview-focus column, and a single edit-focus column. Hide `.editor-panel` rather than `.document-left-pane` in preview focus; keep the existing 980px single-column fallback.

- [ ] **Step 5: Run focused and full verification**

Run: `npm run test:web -- web/src/DocumentWorkspaceControls.test.tsx web/src/DocumentViewToolbar.test.tsx`

Expected: PASS.

Run: `npm run test:web && npm run typecheck && npm run build`

Expected: 0 failures, no TypeScript errors, and a successful Vite production build under Node 22.

- [ ] **Step 6: Commit**

```powershell
git add docs/superpowers/specs/2026-11-24-document-preview-layout-design.md docs/superpowers/plans/2026-11-24-document-preview-layout.md web/src/DocumentWorkspaceControls.tsx web/src/DocumentWorkspaceControls.test.tsx web/src/App.tsx web/src/styles.css
git commit -m "feat: enlarge the document preview workspace"
```
