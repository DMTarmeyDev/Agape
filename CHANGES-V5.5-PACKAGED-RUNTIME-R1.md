# V5.5 Packaged Runtime Repair R1

This repair fixes the packaged Windows/macOS/Linux runtime path without changing the normal human-first workflow.

## What changed

- Frozen Agape builds no longer try to execute Python service scripts by passing them to `sys.executable` (which is the frozen Agape binary under PyInstaller).
- Agape now has a private `--agape-internal-service` mode. Frozen builds relaunch themselves in this mode for Document Studio and Workflow Bridge; source builds continue to launch the service scripts with Python.
- Document Studio and Workflow Bridge assets are explicitly bundled into every release target.
- Bundled-service runtime dependencies are declared in `requirements-runtime.txt` and included by the release build.
- Document/Workflow service data and logs are written under Agape's user-data directory rather than the temporary PyInstaller extraction directory.
- Document Studio accepts explicit runtime data/template/output/settings paths and resolves its default paths relative to its own source folder.
- LibreOffice discovery now supports Windows, Linux and the standard macOS app-bundle locations.
- Release builds now start the frozen Document Studio and Workflow Bridge and probe their health endpoints before artifacts are published.
- Optional developer-tool installers no longer use the frozen Agape executable as `python -m pip`; source mode keeps normal pip behaviour, CLI tools can use a separately validated Python installation, and unsupported in-process extensions fail with a clear message.
- `pyproject.toml` is aligned with the V5.5 application version.
- A Python invalid-escape warning in full dummy QA was removed.
- `.gitattributes` now gives the repository deterministic line-ending rules.

## Verification

- Regression tests: 123/123 PASS.
- Full dummy-data QA: 22/22 PASS.
- Public release audit: PASS.
- Source-mode internal-service smoke test: Document Studio R31.16 PASS; Workflow Bridge R4.7 PASS.
- A local frozen build could not be executed in the ChatGPT container because outbound package installation is unavailable. GitHub release CI now performs this frozen-build smoke test on Windows, macOS and Linux before publishing.
