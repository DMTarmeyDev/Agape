# Agape V5.6.1 R2.4.2 - Installer Test Isolation

- Fixes the R2.4.1 installer failure when a user has saved `coding_model_mode=manual`.
- The coding metadata default test now mocks factory settings instead of reading the user's live Settings file.
- The installer runs pytest with `AGAPE_MAINFRAME_DATA` pointed at a temporary isolated directory.
- User projects, databases, API keys and personal coding preferences are not used as release-test fixtures.
- Rollback remains enabled if any validation step fails.
