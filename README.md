# Agape

[![CI](https://github.com/DMTarmeyDev/Agape/actions/workflows/ci.yml/badge.svg)](https://github.com/DMTarmeyDev/Agape/actions/workflows/ci.yml)
[![Cross-platform tests](https://github.com/DMTarmeyDev/Agape/actions/workflows/test.yml/badge.svg)](https://github.com/DMTarmeyDev/Agape/actions/workflows/test.yml)
[![CodeQL](https://github.com/DMTarmeyDev/Agape/actions/workflows/codeql.yml/badge.svg)](https://github.com/DMTarmeyDev/Agape/actions/workflows/codeql.yml)
[![GitHub issues](https://img.shields.io/github/issues/DMTarmeyDev/Agape)](https://github.com/DMTarmeyDev/Agape/issues)
[![GitHub stars](https://img.shields.io/github/stars/DMTarmeyDev/Agape?style=flat)](https://github.com/DMTarmeyDev/Agape/stargazers)

**Agape V5.6.1 / R2.5.1 Public Alpha** is a human-first AI workspace for projects, documents, coding, automation, testing, model/tool routing, checkpoints and recovery.

## Download Agape

The safest download link is the GitHub Releases page. It remains valid even when a release asset name changes or a new platform build is added:

[**Open the latest Agape release**](https://github.com/DMTarmeyDev/Agape/releases/latest)

Expected release assets are:

| Platform | Release asset | Status |
|---|---|---|
| Windows 10/11 | `Agape-Windows.exe` | Primary Alpha desktop build |
| macOS | `Agape-macOS.zip` | Native desktop preview; signing/notarisation still required |
| Linux x86_64 | `Agape-Linux-x86_64` | Native technical preview |
| Android 10+ | `Agape-Android-debug.apk` | Installable Alpha APK; debug signed |
| iPhone/iPad | `Agape-iOS-Simulator.zip` | iOS Simulator preview; physical-device distribution requires Apple signing |
| All release files | `SHA256SUMS.txt` | SHA-256 verification list |

The release workflow creates these assets only after the repository QA gate and platform build jobs pass. Do not use a guessed direct latest-asset URL when an asset has not yet been published; use the Releases page above.

> Windows SmartScreen and Apple Gatekeeper may warn about unsigned Alpha builds. Public production distribution should use Windows code signing and Apple signing/notarisation.

## Platform status

| Platform | Shared Agape backend/source | Native wrapper/build | Automated validation |
|---|---:|---:|---:|
| Windows 10/11 | Yes | PyInstaller `.exe` | GitHub Windows runner |
| macOS | Yes | PyInstaller `.app` in `.zip` | GitHub macOS runner |
| Linux x86_64 | Yes | PyInstaller binary | GitHub Ubuntu runner |
| Android 10+ | Yes | Native Java WebView shell | GitHub Android SDK/Gradle build |
| iPhone/iPad | Yes | Native SwiftUI/WKWebView shell | GitHub macOS iOS Simulator build |
| GitHub Codespaces | Yes | Browser-hosted development preview | Devcontainer + deployment helper |

Windows remains the primary desktop validation target. Android is an Alpha mobile wrapper. The iOS project is built automatically for the iOS Simulator; a signed IPA/TestFlight/App Store build requires Apple Developer signing credentials and cannot be truthfully described as a public installable iPhone package until those credentials are configured.

## How Agape is structured

Agape keeps one shared Python/web application for the core workflow and uses platform-specific launchers around it. The shared code includes:

- Source -> Review -> Result document workflow;
- projects, results, workspace filing and right-click actions;
- automatic model/provider routing;
- local and cloud AI provider support;
- Aider, OpenHands, Open Interpreter and Agape Native coding-agent integration points;
- browser real-click QA with Playwright;
- optional accessibility, API, security, load and mobile testing tools;
- checkpoints, rollback/recovery and persistent local state;
- document creation and finished-result download management;
- public-research and brief-change flows;
- source templates, including the Agape end-to-end test template.

The normal interface is human-first. Technical services, models and diagnostics stay behind advanced controls unless they are needed.

## Mobile apps

### Android

Android source is in [`android-app/`](android-app/). The app opens the configured HTTPS Agape endpoint, defaults phones to the touch-friendly web-app view, supports the system file picker, uses Android Download Manager for normal HTTPS downloads, blocks cleartext traffic and never bypasses TLS errors.

See [`README-ANDROID.md`](README-ANDROID.md).

### iPhone and iPad

iOS source is in [`ios-app/`](ios-app/). It uses SwiftUI and WKWebView, keeps Agape navigation inside the configured HTTPS host, opens external links through iOS, supports normal WebKit file selection, and provides reload/back controls plus an offline/error state.

See [`README-IOS.md`](README-IOS.md).

Both mobile wrappers default to:

`https://agape-alpha.tail2a2d28.ts.net/`

The endpoint can be replaced at build time. The Agape backend must be reachable for the mobile wrappers to work.

## GitHub Codespaces

The repository contains [`.devcontainer/devcontainer.json`](.devcontainer/devcontainer.json) and [`scripts/deploy_codespace_preview.sh`](scripts/deploy_codespace_preview.sh).

Inside a Codespace:

```bash
bash scripts/deploy_codespace_preview.sh "$(git branch --show-current)"
```

The Mainframe uses port `8850`. Internal Document Studio and Workflow Bridge ports remain `8851` and `8852`.

## Tailscale

The current Alpha public endpoint is:

`https://agape-alpha.tail2a2d28.ts.net/`

The Windows all-platform deployment script checks the existing Tailscale Funnel first and does not reset a healthy mapping. If no mapping exists and Tailscale is connected, it can create a Funnel to Mainframe port `8850`.

## API keys

API keys are optional. Agape can use local-model features without a cloud-provider key.

Supported setup paths:

1. first-run setup asks for providers one at a time;
2. **Settings > AI provider keys** adds, replaces, imports or removes a provider later;
3. copy [`API-KEYS.template.json`](API-KEYS.template.json) to `API-KEYS.local.json` and fill only the providers you use.

`API-KEYS.local.json` is ignored by Git and must never be committed. You can also run:

```bash
python SETUP-API-KEYS.py
```

## Running from source

Python 3.11+ is supported; Python 3.12 is the release/CI reference version.

```bash
python -m pip install -r requirements-runtime.txt
python main.py --port 8850
```

Local Mainframe URL:

`http://127.0.0.1:8850/`

Windows launcher:

```text
platform\START-AGAPE-WINDOWS.cmd
```

Linux/macOS launcher:

```bash
./platform/start-agape.sh
```

## Testing

Main regression suite:

```bash
python -m pytest -q tests
```

Workflow Bridge regression suite:

```bash
cd recovered/unified-r24
python -m pytest -q tests
```

Full dummy/browser workflow QA:

```bash
python scripts/full_dummy_qa.py --output .agape-validation/full-qa
```

README/repository-link contract audit:

```bash
python scripts/check_repository_links.py
```

GitHub Actions also validates Windows, macOS and Linux Python behaviour, performs CodeQL analysis, builds the Android APK and compiles the iOS Simulator app.

## Preview build

The **Cross-platform preview build** workflow is manually dispatchable from GitHub Actions. It builds Windows, macOS, Linux, Android and iOS Simulator artifacts from the selected branch without merging it into `main`.

The one-command Windows deployment package uses the same workflow and also:

1. validates the exact source payload;
2. backs up the current local Agape source;
3. updates/restarts only Mainframe port `8850`;
4. preserves internal ports `8851` and `8852`;
5. verifies the existing Tailscale public path;
6. creates a new GitHub test/release branch and pull request;
7. updates or creates an Agape Codespace on that branch;
8. triggers and waits for the all-platform preview workflow;
9. downloads and verifies the produced artifacts.

The script deliberately leaves `main` unmerged so the branch and binaries can be tested first.

## Creating a GitHub release

After the release branch has been tested and merged, create a version tag:

```bash
git tag v5.6.1-r2.5.1
git push origin v5.6.1-r2.5.1
```

The release workflow then runs QA and publishes the desktop, Android, iOS Simulator and checksum assets to GitHub Releases.

## Current feature line

V5.6.1 keeps the V5.x human-first workflow and adds the current reliability work: canonical cross-page status synchronisation, saved-project context preservation, Source templates, loopback session compatibility, permanent project deletion, projectless document-job repair, cross-platform preview packaging, Android mobile packaging, iOS mobile source/build validation, Codespaces deployment and safer release/download links.

For older development history, see [`docs/README-V5.2-DETAILS.md`](docs/README-V5.2-DETAILS.md) and the historical `CHANGES-*.md` files.

## Security

Agape does not require Microsoft Defender to be disabled and should not silently add antivirus exclusions. Release binaries should carry SHA-256 hashes. API secrets, databases, certificate/private-key files and local credential files are excluded from public publishing by the repository audit.

See [`SECURITY.md`](SECURITY.md). Do not post vulnerabilities publicly.

## Project resources

- [Latest release](https://github.com/DMTarmeyDev/Agape/releases/latest)
- [All releases](https://github.com/DMTarmeyDev/Agape/releases)
- [GitHub Actions](https://github.com/DMTarmeyDev/Agape/actions)
- [Issues](https://github.com/DMTarmeyDev/Agape/issues)
- [Discussions](https://github.com/DMTarmeyDev/Agape/discussions)
- [Roadmap](ROADMAP.md)
- [Contributing](CONTRIBUTING.md)
- [Support](SUPPORT.md)
- [Code of conduct](CODE_OF_CONDUCT.md)
- [Licence](LICENSE)
