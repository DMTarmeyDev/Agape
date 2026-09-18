# Agape V3.3 saved-project reliability repair

- Saved projects are loaded directly from the local Core SQLite database in read-only mode before any HTTP fallback.
- The saved-project list also reads the local database first, so it remains fast when Core port 8797 is offline.
- Selecting a saved project creates a self-contained source snapshot before Document Studio is called.
- After that snapshot, document intake uses `project_id=0` plus provenance `source_project_id`, so Core is no longer a hard dependency for the document workflow.
- No project database is modified by this fallback.
- Existing service-based loading remains as a compatibility fallback when no readable database is found.
