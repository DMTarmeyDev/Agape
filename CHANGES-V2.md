# Agape Mainframe V2 changes

## Human-first document workflow

- Paste source text or upload a source document from the same Create page.
- AI fills the document brief/form instead of requiring manual completion first.
- Missing fields can be researched/completed with AI, while private facts remain questions for the user.
- The completed AI brief is visible and editable before generation.
- **Change the brief with AI** applies new instructions without discarding unaffected facts.
- **Create Now** and **Gold Standard** remain clear quality choices.
- Gold Standard supports 2–10 reviewers and stores the lead-reviewed final draft.
- **Change this document with AI** creates a new child version from the current result.
- Revision jobs keep `revision_of`, `lineage_root` and `revision_number` metadata rather than overwriting the prior result.

## Settings cleanup

- Removed old duplicate provider/model/review/RAG controls from the normal Settings surface.
- Kept current Experience and Default document quality as normal settings.
- Moved AI router, capabilities, support packages and diagnostics under **Advanced**.
- Automatic model routing remains a core capability; the app is not reduced to one provider/model.

## Consolidation

The source package now carries the active/recovered source for:

- R8 modular core
- Unified workflow bridge (promoted to R2.5 Versioned AI)
- Document Studio R31.11
- Systems/Work Engine
- Artifacts
- Communications Hub
- Aider integration

Historical installers remain only for recovery/provenance and are not normal UI controls.

## Reliability repairs

- Fixed Mainframe delegated-job polling to read the workflow bridge's nested job response correctly.
- Added bundled Document Studio startup fallback.
- Added a working Document Studio `config.json` for packaged use.
- V2 uses its own data directory and non-destructively migrates V1 settings/database on first start.
- Gold revisions now use the final lead-reviewed draft when available, not the earlier first draft.
