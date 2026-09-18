# Agape V3.6 - Windows Recovery Test Fix

- Fixes the Windows-only Step 6 failure where legacy-recovery fixtures under `%TEMP%` were skipped.
- Removes the broad `\\Temp\\` path rejection from project recovery.
- Keeps explicit exclusions for known fixture/cache directories such as `test-data`, `_installer-test-data`, `isolated-data`, `startup-check`, `fixtures`, and `__pycache__`.
- Adds a regression test proving an explicit recovery root located under the OS temp directory is scanned and recovered correctly.
- Runtime project recovery behaviour remains non-destructive and idempotent.
