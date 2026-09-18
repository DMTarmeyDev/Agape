# Publish Agape V5.6.1 R2.5.1 to GitHub

For normal preview/testing, use the all-platform push/deploy script so work goes to a new branch and `main` stays unchanged.

After that branch has been tested and merged, the release publisher can create the release tag:

```powershell
.\PUBLISH-TO-GITHUB.ps1 -Repository "DMTarmeyDev/Agape" -Visibility public -Tag "v5.6.1-r2.5.1"
```

Before pushing, it runs:

- public-release secret/private-file audit;
- README/release-link audit;
- Mainframe pytest suite;
- Workflow Bridge pytest suite;
- Git staged-diff whitespace checks.

Pushing the tag triggers `.github/workflows/release.yml`. That workflow performs the full QA gate and builds Windows, macOS, Linux, Android and an iOS Simulator artifact, then publishes SHA-256 checksums with the GitHub Release.

The iOS Simulator artifact proves the iOS project compiles. A signed iPhone/iPad IPA requires Apple Developer signing credentials and provisioning, which should be stored as protected CI secrets rather than committed to the repository.
