# Print Fidelity and Model Providers Design

## Intent

Make the workbench preview and downloaded PDF the same document, use the A4 page more effectively without creating awkward orphan lines, and let users connect popular first-party model APIs or an OpenAI-compatible relay with ordinary credentials.

## Layout decisions

- Preview and PDF use the same HTML, CSS variables and fitting program. The fitting program has one source in Python: the preview loads it as a same-origin script allowed by the current CSP, while PDF rendering injects that exact source into Chromium.
- A4 page margins are 8 mm on all sides. The sheet keeps those margins in both screen and print media; print no longer swaps sheet padding for a separate `@page` margin.
- Filling an underfull page must never narrow the text layout width. It distributes bounded vertical spacing across bullets and sections. It may not use `zoom > 1` with a reciprocal content width.
- Overflow may use bounded down-scaling only after compact spacing is exhausted. The output remains exactly one page and exposes measured fit metadata for regression checks.
- A representative current resume should place its final visible content between 93% and 98% of page height. Sparse resumes are not stretched into visually absurd layouts.
- Emphasis is deterministic presentation metadata. Each bullet may keep at most two literal highlights: an existing small heading before a colon and the strongest existing quantitative result. Existing valid highlights remain first; no new fact or wording is created.

## Model connection decisions

- Presets: OpenAI / ChatGPT, Anthropic / Claude, DeepSeek, and Alibaba Cloud Bailian. Each preset owns its official base URL and exposes an editable model ID.
- Custom relay is explicitly OpenAI-compatible. The user supplies `base_url`, API key and model; the application does not silently append `/v1`, but it appends `/chat/completions` when the supplied URL is only a base.
- OpenAI, DeepSeek, Bailian and custom share the OpenAI-compatible adapter. Anthropic uses the native Messages API with `x-api-key` and `anthropic-version` headers and normalizes its response into the application's completion contract.
- Connection tests send synthetic short text only. Failed tests preserve the previous working configuration, and keys never appear in responses or files outside the existing optional system keyring behavior.
- The UI uses clear provider choices, shows the model field without hiding it behind an advanced disclosure, and shows the base URL only for custom relays.

## Constraints

- Preserve the current resume content and all unrelated dirty-worktree changes.
- Do not send a real resume during connection tests.
- Do not claim a provider is fully verified without a real authorized end-to-end credential test.
- Keep direct PDF and Word download behavior from the previous iteration.

## Success criteria

- The current preview executes the fitting program under the existing CSP and reports `data-fit-ready=true`.
- The current downloaded PDF and preview use the same 8 mm content geometry and no longer differ because the preview script was blocked.
- The representative PDF is one A4 page, reaches the target bottom band, and does not create a one- or two-character terminal line caused by width-narrowing expansion.
- Small headings and strong metrics are visibly bold when they already exist in the bullet text.
- OpenAI and Claude presets appear in the UI and backend preset API; OpenAI-compatible and Anthropic-native probe/generation envelopes are covered by tests.
- A custom HTTPS relay accepts user-entered base URL, API key and model.
