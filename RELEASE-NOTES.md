# Agape V5.5 Public Alpha

V5.5 focuses on the human Review/Result workflow and release reliability.

## V5.5 changes

- Missing-information review is collapsed by default and opens on demand.
- **Change the brief with AI** is collapsed by default and closes again after applying a change.
- Public-information research has its own progress bar/status.
- Result creation exposes a **Download Manager** with stage, progress, estimated remaining time and clear next-step instructions.
- Finished-document downloads now proxy to the active Workflow Bridge on port **8852** instead of the obsolete 8840 endpoint.
- Download failures expose **Retry download**; completed items expose **Download again** and **Open folder**.
- A 22-step isolated dummy-data QA exercises upload, brief preparation, missing-info controls, research, AI brief changes, document creation, DOCX/PDF download, forced download failure, retry, open-folder and file validation.
- GitHub test/release workflows run the full dummy QA as a release gate.

## Validation

- 111/111 automated regression tests PASS.
- 22/22 full dummy QA steps PASS.
- Downloaded DOCX and PDF payloads validated as readable expected formats.
- Browser console errors: 0; page errors: 0.

# Cross-platform release packaging

This repository uses one shared Python/web codebase and builds native downloadable packages on GitHub's Windows, macOS and Linux runners.

## Downloads

- Windows: `Agape-Windows.exe`
- macOS: `Agape-macOS.zip`
- Linux x86_64: `Agape-Linux-x86_64`
- SHA-256 hashes: `SHA256SUMS.txt`

Windows-specific integrations such as winget and pywinauto remain optional Windows capabilities. The shared core, Workspace, document workflow, model routing and browser UI remain common across platforms.
