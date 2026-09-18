# Deploy Agape V5.6.1 R2.5.1

Use `AGAPE-V5.6.1-R2.5.1-ALL-PLATFORMS-PUSH-DEPLOY.ps1` from Windows for the full safe preview deployment.

The deployment flow:

1. validates the exact packaged source and runs the Mainframe + Workflow Bridge regression suites;
2. checks the README/release-link contract;
3. backs up and updates the local Agape V5.6.1 source;
4. restarts Mainframe on port `8850` while preserving internal Document Studio/Workflow Bridge ports `8851` and `8852`;
5. checks `https://agape-alpha.tail2a2d28.ts.net/` and preserves a healthy Tailscale Funnel;
6. creates a new GitHub release/test branch and pull request without merging `main`;
7. updates or creates an Agape GitHub Codespace on that branch;
8. starts the Codespace preview with `scripts/deploy_codespace_preview.sh`;
9. triggers the **Cross-platform preview build** workflow;
10. waits for Windows, macOS, Linux, Android and iOS Simulator build jobs;
11. downloads the successful artifacts and verifies the Android APK contains `classes.dex` and the iOS Simulator ZIP contains `Agape.app`.

The deployment script intentionally leaves `main` unmerged. Test the branch and downloaded artifacts first, then merge the pull request when you are satisfied.

A physical-device iOS IPA is not created unless Apple Developer signing is configured. The default iOS CI artifact is an unsigned Simulator build, which verifies the iOS source compiles without exposing signing credentials.
