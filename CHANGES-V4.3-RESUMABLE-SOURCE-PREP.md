# Agape V4.3 - Resumable Source Preparation

V4.3 fixes source preparation becoming stuck on repeated `Agape connection interrupted — reconnecting to source preparation…` messages when Mainframe exits or restarts mid-job.

## Changes
- Persist the in-flight source-preparation request outside SQLite until the job reaches a terminal state.
- Track worker instance, attempt count and heartbeat in the source-preparation job table.
- Resume abandoned QUEUED/RUNNING preparation jobs after a Mainframe restart, with a bounded maximum of three worker attempts.
- Make workflow document intake idempotent by `prepare_request_id` so restart recovery cannot duplicate the intake.
- Add Mainframe instance ID, PID and active source jobs to `/api/health`.
- Bound browser reconnect retries and surface a clear action if Mainframe is truly offline.
- Restart the visible Mainframe server automatically after an unexpected process exit, while preserving safe installer shutdown behaviour.

## Validation
- Mainframe: 75/75 PASS
- Workflow bridge: 51/51 PASS
- Restart/resume regression: PASS
- Intake idempotency regression: PASS
- JavaScript syntax: PASS
