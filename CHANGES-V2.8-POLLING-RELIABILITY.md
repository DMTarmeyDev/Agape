# Agape Mainframe V2.8 - Long-job polling reliability

- Removed the browser's fixed 600-poll / roughly 15-minute completion cutoff.
- Replaced overlapping async setInterval polling with one sequential status request at a time.
- Added a 20-second timeout to each individual status request.
- Temporary status/network failures now retry and show a reconnecting message instead of immediately failing the job.
- Backend-declared failed jobs still fail immediately and show their real error.
- Long-running AI/document jobs can continue for as long as the backend reports them running.
