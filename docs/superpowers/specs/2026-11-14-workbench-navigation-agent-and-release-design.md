# Workbench Navigation, Agent Editing, and Release Design

## Intent

Make the resume workbench easier to navigate, make model-connection failures diagnosable without exposing credentials, let the contextual Agent perform safe presentation-only edits such as bolding metrics, and present resumes as the parent object of their generation history. Add a reproducible container path for Windows, macOS, and Linux while keeping native release claims evidence-based.

## Product decisions

- The editor uses a narrow vertical section rail inside the editing panel. Only the selected group is rendered: basic information, education, work/internship, projects, or skills/other.
- The live A4 preview remains visible and continues to update from the whole resume, not only the selected group.
- A resume is the primary navigation object. Jobs with an adopted or reviewed resume are shown under that resume; unfinished jobs without a resume stay in a separate inbox.
- Agent freedom covers wording, ordering, structure, deletion, and literal presentation highlights. New employment, skills, numbers, responsibilities, states, or outcomes still require supplied evidence or an explicit user statement.
- Model diagnostics use the same URL normalization, protocol adapter, timeout, and error classification as the application. The diagnostic script prompts for the key without echoing it and never writes it to disk.
- Generation progress exposes only user-facing role, action, and status. It does not expose prompts, chain-of-thought, raw provider payloads, or personal material.
- Cross-platform one-command deployment is provided through Docker Compose. Native packages remain a separate release track and cannot be described as verified until built and exercised on clean machines for each operating system.

## Approaches considered

### Editor navigation

1. Keep the long form and add sticky headings. Low implementation cost, but it does not reduce the amount of visible form or cognitive load.
2. Use independent accordions. Better scanning, but multiple expanded groups can recreate the same long page and hide where the user is.
3. Use one active vertical section rail. Chosen because it gives stable navigation, bounded form height, keyboard-accessible buttons, and preserves the existing preview.

### Resume and task navigation

1. Keep resumes and jobs as peer lists. Rejected because it hides one-to-many ownership.
2. Build a new normalized database hierarchy and migration. Correct long term, but disproportionate for data that already records adopted and review relationships.
3. Project a tree from existing job relationships and keep unmatched work in an inbox. Chosen as a compatible first step; no stored jobs are rewritten.

### Cross-platform delivery

1. Source scripts only. Small, but still requires users to install exact Python, Node, Chromium, and fonts.
2. Native packages only. Best experience, but packages must be built and signed separately per operating system and cannot be produced credibly from one Windows machine.
3. Docker Compose now, native packages as a verified release track. Chosen because it creates one reproducible runtime across all three systems without overstating native validation.

## Architecture

`ResumeEditor` owns only the active editor group and delegates field mutations through the existing whole-document `Content` callback. `editorSections` is a pure mapping from section kinds to user-facing groups. `ExperienceFields` receives the full section array plus a visible-kind filter so edits retain stable section IDs and ordering.

`JobStore.list()` adds a derived `resume_id` from `adopted_resume_id` or `input.review_resume_id`. The frontend `workspaceTree` groups summaries without changing persistence. `WorkspaceSidebar` renders resume nodes, nested jobs, and an unmatched task inbox.

Agent proposals compare both semantic block text and per-item highlights. Literal highlight changes are first-class diffs and do not require a new evidence citation when the underlying text and facts are unchanged. Model-supplied highlights still pass the existing `Item` validation limits.

The Docker service binds inside the container while Compose publishes only to host loopback. The same FastAPI session/origin/host checks stay active. The image includes the built frontend, Python lockfile environment, matching Playwright Chromium, and a CJK font; user data lives in a named volume.

## Safety and compatibility

- Existing resume and job rows remain readable; no destructive migration is introduced.
- Changing tabs never discards unsaved edits.
- Changing a section kind moves it to the corresponding tab without changing its ID.
- Agent formatting changes cannot highlight text that is absent, repeat highlights, or cover most of a bullet.
- API keys are neither command-line arguments nor saved by the diagnostic script.
- Container port publishing is loopback-only by default; the app is not exposed to the LAN.
- Docker availability is a prerequisite, not hidden. Native clean-machine verification remains an explicit open acceptance item.

## Acceptance

- Selecting an editor tab shows only that form group while the full preview remains intact.
- Work, project, education, and skills/other groups show correct counts and retain edits when switching.
- A request such as “把百分比和提升指标加粗” creates a new version whose literal metric highlights render in preview/PDF/DOCX; unsupported factual additions remain blocked.
- The standalone model diagnostic reports the resolved endpoint and a safe error category without echoing or persisting the key.
- Sidebar jobs are nested under their related resume; unmatched running/failed jobs remain discoverable.
- The execution trace uses distinct icons and stable role/action labels for completed and current stages.
- `docker compose up --build` starts the app with persistent data and host-loopback access on systems with Docker Compose.
- Python, web tests, Ruff, TypeScript, Vite, Compose configuration, and Dockerfile static checks pass; claims about real providers and clean operating systems remain limited to actual evidence.
