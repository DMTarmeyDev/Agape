# Agape V5.6.1 — Canonical Status Sync

- One canonical server-side status feed for Results, Projects and Workspace.
- `/api/recent` refreshes unfinished local Workflow Bridge jobs before returning history.
- `/api/projects` decorates projects with the latest canonical work status.
- New work records persist project/intake identity from the moment the job is queued.
- All pages render the same human labels: Queued, Working, Complete, Needs attention, Failed.
- Results, Projects and Workspace refresh every 5 seconds while visible and on browser focus/visibility return.
- Fixes cross-device/Tailscale cases where one browser showed Complete while another still showed Working.
