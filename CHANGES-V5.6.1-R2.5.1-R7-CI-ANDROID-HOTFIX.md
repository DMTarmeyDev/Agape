# Agape V5.6.1 R2.5.1 - R7 CI / Android hotfix

Confirmed from GitHub Actions run 35394911861:

- validation failed during test collection with `ModuleNotFoundError: No module named 'requests'`;
- the validation job installed only `pip` and `pytest` instead of Agape's declared runtime requirements;
- Android uses a custom `BuildConfig.AGAPE_BASE_URL` value and now explicitly enables BuildConfig generation.

Changes:

1. validation installs `requirements-runtime.txt` and pytest;
2. validation runs `pip check` and a critical import smoke test;
3. Android `buildFeatures.buildConfig = true`;
4. Android SDK setup explicitly requests `platform-tools`;
5. no merge to `main` is performed by the repair.
