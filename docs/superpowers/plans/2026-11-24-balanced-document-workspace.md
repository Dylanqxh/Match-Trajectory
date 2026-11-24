# Balanced Document Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Increase the usable width of the editing form in split view without shrinking focused preview or focused edit modes.

**Architecture:** Keep the existing three document view states and change only the CSS layout contract. Split view gets a balanced responsive grid; constrained windows reuse the existing single-column behavior at an earlier breakpoint.

**Tech Stack:** React 19, TypeScript, CSS Grid, Playwright

**Spec:** `docs/superpowers/specs/2026-11-24-balanced-document-workspace-design.md`

## Global Constraints

- Split-view editor track minimum: `400px`.
- Split-view preview track minimum: `430px`.
- Single-column workbench breakpoint: `1180px`.
- Preserve `preview` and `edit` view behavior and existing mobile rules.
- Do not add media functionality or inspect media content.

## Review Focus

- A 1234px viewport must leave materially more than the current 255px usable form width.
- A viewport at or below 1180px must not keep two tracks whose minimum widths overflow the canvas.
- Focused preview must continue to hide the editor rather than reserving editor width.
- Focused edit must continue to hide the preview and use one full-width track.
- Existing 980px/mobile rules must remain compatible with the earlier workbench breakpoint.

---

### Task 1: Encode and implement the balanced layout contract

**Files:**
- Create: `tools/test-document-layout.mjs`
- Modify: `package.json`
- Modify: `web/src/styles.css`

**Interfaces:**
- Consumes: existing `.editor-grid`, `.document-view-preview`, `.document-view-edit`, and workbench responsive selectors.
- Produces: CSS-only responsive layout behavior; no React or data interface changes.

- [x] **Step 1: Write the failing browser layout test**

Load a minimal workbench DOM with the production stylesheet in headless Chromium. At `1234x923`, assert the editor and preview are both visible and at least `400px`/`430px` wide. At `1180x923`, assert the editor and preview occupy separate rows and do not overflow the available canvas.

- [x] **Step 2: Run the targeted test and verify it fails**

Run: `npm run test:layout`
Expected: FAIL because the desktop editor is still capped at `320px` and the `1180px` viewport still uses two columns.

- [x] **Step 3: Implement the responsive grid rules in `web/src/styles.css`**

Use `minmax(400px,.82fr) minmax(430px,1fr)` for desktop split view and move the workbench-specific single-column rules to `@media(max-width:1180px)`. Keep global sidebar and mobile rules at their existing breakpoints.

- [x] **Step 4: Run targeted and full frontend verification**

Run: `npm run test:layout`, `npm run test:web`, `npm run typecheck`, and `npm run build`.
Expected: all commands exit 0.

- [x] **Step 5: Verify live DOM dimensions without screenshots**

At the active desktop viewport, verify the editor track is at least 400px and the preview remains visible in split view.

- [x] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-11-24-balanced-document-workspace-design.md docs/superpowers/plans/2026-11-24-balanced-document-workspace.md tools/test-document-layout.mjs package.json web/src/styles.css
git commit -m "fix: rebalance the document editing workspace"
```
