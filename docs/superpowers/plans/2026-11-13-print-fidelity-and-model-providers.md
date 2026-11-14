# Print Fidelity and Model Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make preview/PDF layout identical and polished, then add first-class OpenAI and Claude connections alongside existing and custom providers.

**Architecture:** Extract the browser fitting program as one served/injected source, retain one A4 sheet geometry across preview and print, and replace width-narrowing expansion with vertical distribution. Add a small provider-protocol boundary that converts OpenAI-compatible and Anthropic-native requests/responses into the existing completion contract.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, httpx, Playwright Chromium, React 19, TypeScript, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-11-13-print-fidelity-and-model-providers-design.md`

## Global Constraints

- Keep all highlights literal and evidence-preserving.
- Connection probes use synthetic content only.
- Preserve current dirty-worktree changes and do not commit mixed user work.
- Every behavior change follows a RED then GREEN test cycle.

## Review Focus

- CSP-blocked preview fitting must fail a test even if direct PDF rendering still works.
- Filling short content must not reduce available line width or create width-induced orphan lines.
- Long content must remain one page without dropping text.
- Anthropic headers and response envelopes must never be treated as OpenAI-compatible shapes.
- Custom relay validation must preserve HTTPS/localhost safety and must not leak API keys.

---

### Task 1: One-source preview and PDF fitting

**Files:**
- Modify: `app/rendering.py`
- Modify: `app/main.py`
- Modify: `tests/test_pdf.py`
- Modify: `tests/test_exports.py`

**Interfaces:**
- Produces: `resume_fit_script() -> str`, served at `/resume-fit.js` and injected by `render_pdf`.
- Produces: `render_html(...)` with one 8 mm sheet geometry and an external fitting script.

- [ ] Add failing tests for external script loading, identical page geometry and absence of reciprocal width-narrowing expansion.
- [ ] Run focused tests and confirm the old inline/zoom implementation fails.
- [ ] Implement the shared script route and vertical-distribution fitting algorithm.
- [ ] Run focused tests and render the current resume for visual inspection.

### Task 2: General-purpose emphasis

**Files:**
- Modify: `app/gates.py`
- Modify: `tests/test_writing_gates.py`

**Interfaces:**
- Produces: deterministic `highlights` containing up to two existing literal phrases: heading first, strongest metric second.

- [ ] Add failing tests for project/work small headings, quantitative results and preservation of explicit highlights.
- [ ] Run focused tests and confirm missing deterministic emphasis.
- [ ] Implement bounded literal highlight augmentation.
- [ ] Run focused tests and verify the current resume render contains the intended bold runs.

### Task 3: Provider protocol adapters and presets

**Files:**
- Create: `app/provider_protocols.py`
- Modify: `app/providers.py`
- Modify: `app/model_client.py`
- Modify: `tests/test_providers.py`
- Modify: `tests/test_model_client.py`

**Interfaces:**
- Produces: request/header/endpoint builders and completion-envelope normalization for `openai_compatible` and `anthropic`.
- Produces: presets `openai`, `anthropic`, `deepseek`, `dashscope`, plus `custom` OpenAI-compatible configuration.

- [ ] Add failing preset, Anthropic probe and Anthropic completion tests.
- [ ] Run focused tests and confirm provider/schema/envelope failures.
- [ ] Implement protocol adapters and route probes/generation through them.
- [ ] Run provider and model-client tests.

### Task 4: Model settings interaction and end-to-end verification

**Files:**
- Modify: `web/src/ModelSettings.tsx`
- Modify: `web/src/styles.css`
- Create: `web/src/ModelSettings.test.tsx`

**Interfaces:**
- Consumes backend provider identifiers and exposes preset selection, visible model ID, key, and custom base URL.

- [ ] Add failing markup tests for OpenAI, Claude, visible model input and custom relay guidance.
- [ ] Run Web tests and confirm the missing choices/fields.
- [ ] Implement the provider cards/select interaction and responsive styling.
- [ ] Run Web tests, typecheck and build.
- [ ] Restart the local service, verify the visible workbench, download and inspect a new PDF, then run the full Python/Web suites and `git diff --check`.
