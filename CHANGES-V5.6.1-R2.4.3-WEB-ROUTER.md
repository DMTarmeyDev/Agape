# Agape V5.6.1 R2.4.3 - Web router reliability

- Serves all bundled web assets, including project_templates.js.
- Direct navigation to Create, Projects, Results, Workspace and Settings returns the Agape UI instead of JSON NOT_FOUND.
- Health endpoint exposes web_revision so the launcher cannot accept a stale process with the same core build marker.
- Launcher verifies both the root UI and project_templates.js before opening the browser.
- Replaces the remaining reserved PowerShell $pid assignment with $listenerPid.
