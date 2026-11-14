# Resume Delivery Quality Design

## Intent

Turn the workbench from a data-engineering demo into a generally usable resume product. A user uploads an old resume, gets an editable result, adjusts it either in the form or through the Agent, and downloads the current version without an approval ritual.

## Product decisions

- Export is user-controlled. Saving the current editor state is required; review, takeover and confirmation are advisory and never block PDF or Word download.
- A generated PDF targets exactly one A4 page when the content can fit legibly. The renderer measures the actual laid-out document and expands or contracts typography and spacing within bounded readable limits instead of selecting a density only from character count.
- Uploaded identity fields are parsed conservatively. An explicit label wins; otherwise a plausible standalone name at the top of a resume is accepted when nearby lines look like resume contact/role/education content.
- Highlights are presentation metadata, not new facts. Empty skill highlights receive a deterministic category highlight from the existing text before the first Chinese or English colon. Existing model-selected highlights remain unchanged.
- Role guidance is layered: universal evidence and writing rules always apply, while explicit role overlays add priorities. Frontend engineering and testing/QA become first-class overlays; unknown roles continue through the general rules rather than inheriting data-engineering assumptions.
- The right-side Agent uses the resume's stored generation Skill when available and infers a maintained overlay from the target title only for manual resumes that have no stored Skill.

## Constraints

- Never invent personal facts or use JD text as applicant evidence.
- Existing user edits and unrelated working-tree changes must be preserved.
- Blank resumes may still be rejected as unusable exports, but review state, unresolved AI warnings and confirmation state may not block export.
- PDF and DOCX remain editable/output-compatible with the existing API.

## Success criteria

- The supplied source beginning with `何明鑫` produces `name=何明鑫`.
- The representative generated resume renders as one PDF page and its last visible content reaches at least 82% of page height without clipping.
- Skill bullets visibly bold their category labels even when the model returned no highlights.
- One click on PDF or Word saves the current version and downloads it with no review modal or confirmation API call.
- Frontend and testing directions are selectable, validated by the backend schema, loaded by the Skill router, and recognized by chat/manual-Agent fallback routing.
