# Agape Latest Complete Reconstruction — 2026-09-18

Canonical source lineage used for this reconstruction:

- `9d8eb63` — Agape V5.5 review, download and full-QA reliability update.
- `a1e7406` — packaged runtime service launches and release smoke tests.
- Windows portability update — platform-neutral service-runtime path assertion.
- API-key QA isolation — credential tests no longer touch the real OS credential store.
- GitHub community/security update — contribution/support/conduct/roadmap files, issue forms, PR template, CODEOWNERS, CI, CodeQL, dependency review and Dependabot.
- Public website snapshot — gold site kept under `website/` and separate from the application UI.

The V5.5 application feature line is retained, including human-first workflows, model/provider routing, coding/workspace tools, right-click actions, testing tools, Document Studio integration, Workflow Bridge integration, Download Manager flows, API-key setup, cross-platform launchers and packaged-service release checks.

Repository corrections applied during reconstruction:

- CI runs the active `tests/` suite rather than collecting recovered legacy tests.
- CODEOWNERS targets `/agape_mainframe/` rather than the obsolete `/core/` path.
- The stale Dependabot `/core` entry is removed.
- GitHub Action versions include the newer Dependabot-proposed major versions observed on the remote branches.
- Credential tests are sandboxed from Windows Credential Manager / OS keyring.
- Service-runtime path tests are cross-platform.

The source-available alpha licence is preserved unchanged.
