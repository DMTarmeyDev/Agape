# Agape V2.9 - Document Job Timeout Fix

- Document Studio document creation now supports background jobs via `/api/agent-create/start` and `/api/agent-create/status`.
- Mainframe no longer holds one HTTP socket open across long planning, research, drafting and validation-repair work.
- Validation failures are still returned to Mainframe and can trigger the targeted validation repair loop.
- Older Document Studio builds remain supported through a synchronous compatibility fallback.
- Temporary status-connection failures are retried and reported as job events.
