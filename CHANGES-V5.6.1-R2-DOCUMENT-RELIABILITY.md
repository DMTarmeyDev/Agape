# Agape V5.6.1 R2.2 Document Reliability

- Routes AI-provider and LibreOffice subprocesses through a verified Windows working directory.
- Retries WinError 3 once with a safe temporary working directory.
- Correctly invokes .cmd/.bat provider launchers through cmd.exe on Windows.
- Reports the exact document-creation stage and traceback tail when an async job fails.
- Wraps template-instantiation and document-conversion failures with explicit stage labels.
- Requires Document Studio build `R31.16-document-path-reliability-r2.2` before Mainframe adopts it.
- Keeps R2 fixes for current-job-only downloads, truthful creation-failure guidance, duplicate-section validation and generated-artifact cleanup.
- Installer performs a real DOCX smoke creation against port 8851 before starting Mainframe.
