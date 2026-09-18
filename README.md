# Agape

<!-- AGAPE_GITHUB_BADGES_BEGIN -->
[![CI](https://github.com/DMTarmeyDev/Agape/actions/workflows/ci.yml/badge.svg)](https://github.com/DMTarmeyDev/Agape/actions/workflows/ci.yml)
[![CodeQL](https://github.com/DMTarmeyDev/Agape/actions/workflows/codeql.yml/badge.svg)](https://github.com/DMTarmeyDev/Agape/actions/workflows/codeql.yml)
[![GitHub stars](https://img.shields.io/github/stars/DMTarmeyDev/Agape?style=flat)](https://github.com/DMTarmeyDev/Agape/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/DMTarmeyDev/Agape)](https://github.com/DMTarmeyDev/Agape/issues)
[![Last commit](https://img.shields.io/github/last-commit/DMTarmeyDev/Agape)](https://github.com/DMTarmeyDev/Agape/commits/main)
<!-- AGAPE_GITHUB_BADGES_END -->


Human-first AI workspace for projects, documents, coding, automation, testing and model/tool routing.

## Download Agape

### Windows

**Current public application line: V5.5 Public Alpha**

[**Download the latest Windows EXE**](../../releases/latest/download/Agape-Windows.exe)

If the direct EXE link is not yet present, open the [latest GitHub Release](../../releases/latest) and choose the Windows asset. The repository release workflow builds `Agape-Windows.exe` on a native GitHub Windows runner from the same source code in this repository.

> Windows SmartScreen may warn about unsigned community builds until code-signing is configured. Check the SHA-256 file attached to the release before running a downloaded build.

### macOS

[Download the latest macOS build](../../releases/latest/download/Agape-macOS.zip)

The macOS build is generated from the same source code on a native GitHub macOS runner. Apple signing/notarisation should be configured before describing a public macOS build as trusted/no-warning.

### Linux

[Download the latest Linux x86_64 build](../../releases/latest/download/Agape-Linux-x86_64)

The Linux executable is generated on GitHub's Ubuntu runner. Make it executable after download if required: `chmod +x Agape-Linux-x86_64`.

## Public Alpha

Agape is currently a **public Alpha**. Windows is the primary Alpha platform. Linux is an Alpha/technical-preview target and macOS is a development-preview target until native validation is complete. Alpha means the project is usable for testing and development, but interfaces and packaging can still change.

## API keys

API keys are optional. Agape can run with local-model features without a cloud-provider key. There are three supported setup paths:

1. **First-run setup:** Agape offers providers one at a time. Add one key, add another, or skip everything.
2. **Settings > AI provider keys:** add, replace, import, or remove individual provider keys later.
3. **Template file:** copy `API-KEYS.template.json` to `API-KEYS.local.json`, fill only the providers you use, and start Agape. Missing keys are imported without overwriting keys already saved in Agape.

`API-KEYS.local.json` is ignored by Git and must never be committed. Saved keys use the operating system credential store when the packaged build has a usable keyring backend (for example Windows Credential Manager or macOS Keychain). If no OS credential backend is available, Agape falls back to a private local key file in its user-data directory rather than the public source tree. Agape's key-status API reports only whether a provider is configured; it never returns the key value. Environment variables such as `OPENAI_API_KEY` remain supported.

You can also run:

```bash
python SETUP-API-KEYS.py
```

This asks about one provider at a time and hides pasted key values while typing.

## Source code

Agape uses **one shared source codebase** for Windows, macOS and Linux. Platform-specific functions are kept behind platform-aware adapters rather than maintaining three separate copies of Agape.

The shared code includes:

- the human-first project/document workflow;
- Workspace with project/results filing, to-do and job panels;
- right-click context menus;
- automatic AI/model routing;
- coding-engine support for Agape Native, Aider, OpenHands and Open Interpreter;
- optional VS Code/Theia code-management integration;
- browser real-click testing with Playwright;
- optional accessibility, API, security, quality and load testing tools;
- checkpoints/recovery and persistent local state.

Some capabilities are intentionally platform-specific. For example, `winget` and `pywinauto` are Windows integrations and are not treated as required macOS/Linux dependencies.

## R2.5.0 cross-platform preview

The R2.5.0 preview line builds Windows, macOS, Linux and Android from one shared source branch. Android is a secure WebView wrapper for the configured Agape HTTPS endpoint; GitHub Actions verifies that the produced APK contains executable DEX code before publishing the artifact. The default Android endpoint is the existing Agape Tailscale Funnel URL and can be overridden at build time.

## Platform status

| Platform | Shared source | Automated build | Download format | Status |
|---|---|---|---|---|
| Windows 10/11 | Yes | GitHub Windows runner | `.exe` | Primary release platform |
| macOS | Yes | GitHub macOS runner | `.app` inside `.zip` | Cross-platform build path ready; native validation/signing still required |
| Linux x86_64 | Yes | GitHub Ubuntu runner | standalone binary | Cross-platform build path ready; distro validation still required |

Windows remains the primary validation target until it reaches the desired stability. macOS/Linux should not be labelled fully validated until their GitHub native-runner tests and real-machine checks pass.

## Running from source

Requires Python 3.11+ (3.12 recommended).

```bash
python -m pip install -U pytest
python main.py
```

Agape opens at `http://127.0.0.1:8850/` and the desktop launcher opens the default browser automatically.

On Linux/macOS you can also use:

```bash
./platform/start-agape.sh
```

On Windows:

```text
platform\START-AGAPE-WINDOWS.cmd
```

## Testing

Run the active test suite with:

```bash
python -m pytest -q tests
```

GitHub Actions runs the suite on Windows, macOS and Linux on every push/pull request. Tagged releases are built only after the platform test job succeeds.

## Creating a release

Push the source to GitHub, then create and push a version tag:

```bash
git tag v5.5.0
git push origin v5.5.0
```

The release workflow then:

1. tests the repository on native runners;
2. builds `Agape-Windows.exe`;
3. builds `Agape-macOS.zip`;
4. builds `Agape-Linux-x86_64`;
5. creates `SHA256SUMS.txt`;
6. publishes the files to GitHub Releases.

GitHub Releases is the preferred binary distribution location. The source repository should contain source code; executable builds belong in Releases rather than being committed into Git history.

## Current Windows feature line

V5.5 includes the Workspace/right-click work from V5.0/V5.1, optional Testing Tools from V5.2, the cross-platform release structure from V5.3, public-release/API-key onboarding from V5.4, and the V5.5 Review/download reliability pass. V5.5 collapses missing-information and brief-change panels by default, adds a dedicated research progress display and Download Manager, fixes finished-result downloads to use the active Workflow Bridge on port 8852, and adds an isolated 22-step full dummy QA release gate.

The first-run flow keeps API setup optional and deliberately asks for one provider at a time to avoid confusing users with a wall of credential fields. Keys can always be added later in Settings.

For detailed development history and previous release notes, see [`docs/README-V5.2-DETAILS.md`](docs/README-V5.2-DETAILS.md) and the `CHANGES-*.md` files.

## Security

Agape does not require Microsoft Defender to be disabled and should not silently add antivirus exclusions. Release binaries should be accompanied by SHA-256 hashes. For public distribution, Windows code signing and Apple signing/notarisation should be added before presenting builds as production-trusted packages.


## Licence

See [`LICENSE`](LICENSE). The current Alpha repository is source-available. Third-party dependencies retain their own licences.

<!-- AGAPE_GITHUB_COMMUNITY_BEGIN -->
## Community, support and project status

Agape is under active **alpha** development. The project is focused on human-first AI workflows, model/provider flexibility, safe automation, testing, checkpoints, and rollback.

- **Questions and ideas:** use [GitHub Discussions](https://github.com/DMTarmeyDev/Agape/discussions).
- **Bugs and feature requests:** use [GitHub Issues](https://github.com/DMTarmeyDev/Agape/issues).
- **Contributing:** see [CONTRIBUTING.md](CONTRIBUTING.md).
- **Support:** see [SUPPORT.md](SUPPORT.md).
- **Security:** see [SECURITY.md](SECURITY.md) and avoid posting vulnerabilities publicly.
- **Roadmap:** see [ROADMAP.md](ROADMAP.md).

If Agape is useful to you, starring the repository helps other people discover the project.
<!-- AGAPE_GITHUB_COMMUNITY_END -->
