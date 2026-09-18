# Agape V4.9 - Real Click QA

V4.9 turns UI automation into a visible release-quality feature instead of relying only on unit/API tests.

## Added

- Python Playwright real-browser QA engine.
- Safe real-click regression that opens Agape in Chromium and physically clicks the main navigation, source-mode controls, coding-model/agent/manager selectors, save controls and diagnostics.
- Settings -> Real click testing panel with Run, Refresh and Chromium setup controls.
- Per-run screenshots plus JSON evidence under the Agape data QA folder.
- Last-run PASS/FAIL status surfaced inside Settings.
- Windows desktop automation bridge based on optional pywinauto.
- Optional VS Code and Theia Full launch/window probes on Windows.
- Coding-tool launches now report their process ID so Windows UI Automation can bind to the launched editor.
- pywinauto added to the explicit optional-support allowlist.

## Safety boundary

The safe click gate deliberately does not press AI submission, installer/download, project-recovery or other externally consequential controls. Those controls remain separately testable with mocked integration tests or explicit user-authorized desktop test flows.

## Release requirement

A build must pass the existing Python regression suite, JavaScript syntax validation, HTTP smoke testing and the new Playwright real-click gate before it can be described as UI-tested.
