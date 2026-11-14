# Agent workflow convergence design

## Intent

Make the shipped product match the centralized multi-Agent architecture described to the user: generation remains Coordinator-led, while the contextual Editing Agent becomes a low-friction conversational editor. Remove the unused legacy collection-chat surface and expose a concise execution trace without exposing internal prompts or raw logs.

## Goals

- A safe Editing Agent change is saved immediately as a new resume revision.
- The latest Agent change can be undone without deleting history; undo creates another revision.
- A blocked edit never writes and the user can immediately clarify in the next message.
- The generation panel shows a human-readable Planner/Writer/Reviewer/Reviser trace derived from persisted step receipts.
- Upload remains available through a dedicated stateless endpoint after the unused legacy chat session service is removed.
- Documentation describes the implementation as centralized, role-specialized multi-Agent orchestration and distinguishes logical agents from independent processes.
- Only confirmed reproducible caches and obsolete tracked code are removed; user data, exports, dependencies, portable builds and legacy task compatibility stay intact.

## Non-goals

- Do not add peer-to-peer Agent chat or multiple worker processes.
- Do not add per-Agent provider configuration UI in this iteration.
- Do not remove `execution_compat.py`; stored legacy jobs still depend on it.
- Do not delete `data/`, `node_modules/`, `.venv/`, portable builds, successful exports or user IDE settings.
- Do not claim real-provider writing quality from synthetic tests.

## Approaches considered

### Keep proposal-and-apply

Lowest implementation risk, but preserves the extra confirmation the user explicitly dislikes. Rejected.

### Auto-apply in place

Fastest interaction, but overwrites the last version and makes model mistakes hard to recover. Rejected.

### Auto-save a new revision with bounded undo

Chosen. The Agent still produces a candidate and passes deterministic gates. A safe candidate is saved as a new revision; the UI immediately refreshes and offers one-click undo. Undo requires the current revision to still equal the Agent-applied revision and restores the base snapshot as another revision, so history remains append-only.

## Architecture

`AgentService.post` remains the only model boundary for contextual edits. It computes the proposal, blocks unsupported changes, or atomically applies a safe proposal using optimistic revision checks. The response returns both session state and the saved resume so the React workbench updates without an extra adoption step. `AgentService.undo` restores the recorded base revision only when no later edit exists.

Generation trace labels are a pure frontend projection over persisted `step_receipts`; no new execution state is introduced. Legacy `ChatService` and `/api/chat/sessions` are removed because the current UI never calls them. File extraction moves to `/api/uploads` and directly returns the existing `uploads.extract_upload` result.

## Safety and compatibility

- The model never writes directly; deterministic evidence gates still decide whether a candidate is writable.
- Auto-apply rechecks target hash and revision after the model call.
- Undo is CAS-protected and never deletes a version.
- Blocked responses remain visible and accept a follow-up message instead of forcing discard.
- Existing resume, job and checkpoint schemas remain readable.
- The old upload route is intentionally replaced rather than aliased, because no current frontend consumer uses it after this release.

## Acceptance

- Safe Agent message: one request, one new revision, updated editor, visible undo.
- Unsupported claim: no new revision, risk explanation, next message remains enabled.
- Stale target or stale undo: HTTP 409, latest manual content preserved.
- Generated-task target: candidate is adopted and edited without an orphan job.
- Trace shows completed/current role labels and handles retries without duplicate labels.
- DOCX/PDF/TXT upload works at `/api/uploads`; `/api/chat/sessions` is gone.
- Full Python and web suites, Ruff, TypeScript, Vite build and diff checks pass.
