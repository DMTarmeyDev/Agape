# Agape V3.4 installer test isolation

- Fixed install-time test failure caused by a real Core database overriding a mocked saved-project fixture.
- `AGAPE_CORE_DB` is now authoritative when set; no fallback to profile/OneDrive databases occurs.
- The saved-project service-path unit test explicitly disables local DB fallback.
- Installer validation points Core DB discovery at an isolated temporary location.
- Runtime saved-project read-only fallback remains unchanged when no override is supplied.
