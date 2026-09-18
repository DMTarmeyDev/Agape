# Agape V5.6.1 R2.4.6 - projectless document job repair

- Prepared document/research intakes are submitted to the workflow engine with `project_id=0`.
- The Projects database id remains provenance only and is no longer a hard dependency for document creation.
- Workflow Bridge falls back to the self-contained intake if a supplied Core project id is missing or Core is unavailable.
- Development/project-loop work still requires its real project id.
- Fixes the UI-visible `WORK_SUBMIT_FAILED: {"error":"PROJECT_NOT_FOUND"}` path after pasted/uploaded source is auto-saved as a Project.
