# Agape V5.6.1 R2.5.1

- Rebuilt README download guidance around the stable GitHub Releases page instead of assuming unpublished `latest/download` asset URLs.
- Removed scraped GitHub SVG/sidebar/footer link patterns and added an automated README/local-link/release-asset contract audit.
- Updated the current version/release instructions from stale V5.5 references to V5.6.1/R2.5.1.
- Kept Windows, macOS and Linux packaging on the shared V5.6.1 source.
- Updated Android wrapper to R2.5.1 and retained HTTPS-only/TLS-fail-closed behaviour.
- Added a native SwiftUI/WKWebView iPhone/iPad project with HTTPS host restriction, external-link handoff, retry/back/reload UI and configurable Agape endpoint.
- Added iOS Simulator compilation/artifacts to preview and tagged-release GitHub Actions.
- Updated Codespaces, Tailscale and publish/deployment documentation for the five platform targets.
- Kept the safe deployment rule: publish to a test/release branch and pull request first; do not auto-merge `main`.
