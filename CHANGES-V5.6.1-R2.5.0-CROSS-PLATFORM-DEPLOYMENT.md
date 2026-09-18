# Agape V5.6.1 R2.5.0 - cross-platform deployment release

- Combines the R2.4.4 template/session repair, R2.4.5 permanent Project Delete action and R2.4.6 projectless document-job repair.
- Keeps one shared application source for Windows, macOS and Linux.
- Adds Android wrapper source to the main repository and a verified GitHub Actions APK build.
- Android build uses AGP 9.4.0, Gradle 9.6.0, JDK 17 and Android SDK 36.
- Android endpoint is build-configurable and defaults to `https://agape-alpha.tail2a2d28.ts.net/`.
- Adds a repeatable GitHub Codespace devcontainer and preview deployment helper.
- Adds a manual cross-platform preview workflow that builds Windows, macOS, Linux and a real installable APK from the same branch.
- The Windows deployment orchestrator updates the validated branch, Codespace, local Mainframe and existing Tailscale Funnel without merging `main`.
