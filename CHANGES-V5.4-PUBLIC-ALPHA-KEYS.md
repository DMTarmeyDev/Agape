# V5.4 Public Alpha + API Key Setup

- Prepared the repository for a public Alpha source release.
- Added `API-KEYS.template.json` with blank values only.
- Added automatic import of `API-KEYS.local.json` without overwriting existing saved keys.
- Added one-key-at-a-time provider setup during first-run onboarding.
- Added Settings > AI provider keys for adding, importing, checking, and removing keys later.
- API key status never returns secret values.
- Saved keys are stored outside the source tree in Agape's private user-data directory and exported to provider environment variables at runtime.
- Added `SETUP-API-KEYS.py` for optional terminal-based one-key-at-a-time setup.
- Added public-release Git ignore rules for local key files, private keys, databases, caches, and build output.
- Removed development database/cache artifacts from the public package.
- Sanitised a historical personal Windows path in a recovered test fixture.
- Added an explicit source-available Alpha licence notice pending the owner's final long-term licence choice.
