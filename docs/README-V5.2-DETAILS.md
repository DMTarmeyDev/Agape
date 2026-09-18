# Agape Mainframe V3.0 — Human First

**Build:** `AGAPE-MAINFRAME-V4.8-CODING-TOOLS`
**Version:** `4.8.0`
**Main UI:** `http://127.0.0.1:8850/`

Agape V3.0 is a human-first consolidation of the Mainframe, Unified workflow bridge and Document Studio. The normal path is deliberately limited to three steps and stops carrying irrelevant branches after the user makes a choice.

## The three-step workflow

1. **Source** — choose exactly one source: paste text, upload a document, or use a saved project. Tell Agape what result you want. The other source paths are disabled and ignored immediately.
2. **Review** — Agape fills the brief with AI. Missing or important items are shown first; already-resolved details stay collapsed under **Review all completed details**. Spelling and grammar findings are shown without silently changing names, figures or facts. Creating automatically saves the current edits.
3. **Result** — progress, finished downloads, versions and **Change this result with AI** stay in one place. Previous versions are preserved.

There is no separate quality/setup/save stage in the normal workflow. Standard mode is the default for speed. Gold Standard remains available when deeper review is useful; the default is 3 reviewers, with 2–10 selectable.

## Writing quality

Every pasted source, uploaded source and saved-project text passes through the same writing-quality layer. Browser text fields use native spellchecking. The backend applies only high-confidence mechanical corrections to the AI-facing text and reports uncertain spelling/grammar suggestions for review. Original uploaded files are never overwritten.

The checker is UK-English aware and preserves company names, product names, IDs, amounts and other factual content rather than guessing.

## Speed and logic changes

Document work now uses route-first checks and starts Document Studio without probing unrelated development services. The bundled Python Document Studio is preferred over the legacy PowerShell launcher. Health checks are fast, long document generation is asynchronous, and the browser can resume saved jobs after a restart.

Once a source type or route is chosen, inactive logic is discarded rather than kept alive in parallel. Technical setup/status checks are deferred until Settings or an incomplete setup actually needs them.

## Settings

Normal Settings contains current user-facing choices. Model/provider routing, capability switches, diagnostics and optional support tools remain under **Advanced**. Automatic multi-model routing remains part of Agape and is not reduced to a single provider.

## Data safety

V3 stores Mainframe data under `%LOCALAPPDATA%\Agape-Mainframe-V3\data`. On first use it non-destructively copies current settings/database from V2 when available, falling back to V1. Older data is not deleted.

## Included capabilities

The package retains the current capability source needed by the application: R8 modular core, Unified R4.7 targeted-validation workflow bridge, Document Studio R31.16, Systems/Work Engine, Artifacts, Communications Hub and Aider integration. Legacy launchers are compatibility fallbacks only and are not the preferred normal route.

## Release gate

- Mainframe/human-first tests: 56/56 PASS
- Unified workflow/document/version tests: 49/49 PASS
- Python compile: PASS
- JavaScript syntax: PASS
- HTTP smoke: verified again on the final package before release

See `CHANGES-V3.1-PROGRESS.md`, `CHANGES-V3.0-HUMAN-FIRST.md`, `LOGIC-AUDIT-V3.0.md` and `TEST-REPORT.txt`.

## Installer security

The clear installer verifies the payload SHA-256 and asks whether the user initiated the install. Exact-version trust can be recorded and revoked in Agape Settings. It does not disable Microsoft Defender, add antivirus exclusions or use `ExecutionPolicy Bypass` in the normal install path.


## V3.3 saved-project reliability
Saved projects are read directly from the local Core SQLite database in read-only mode first. Core port 8797 is no longer required to prepare a saved project as a document source. Once selected, the project is snapshotted into the intake so later document work remains self-contained.


## V3.4 installer isolation repair
Installer validation no longer reads the user's live Core database. `AGAPE_CORE_DB` is now an authoritative override, and install-time tests point it at an isolated temporary path. The saved-project service-path test explicitly disables the local-database fallback so real project IDs/names cannot alter test results.

## V3.5 project recovery
V3.5 restores missing historic user projects from known Agape/DMT SQLite backups into the live Core database. It creates a safety backup first, merges by project name rather than old numeric ID, deduplicates messages, ignores test/template/system data, and leaves every source backup untouched. The installer runs recovery automatically after tests pass, and Projects has a **Recover past projects** button for later rescans.


## V3.6 Windows recovery-test fix
V3.6 fixes the Windows-only installer failure where recovery fixtures under `%TEMP%` were skipped because the scanner rejected every path containing `\Temp\`. Recovery still excludes known test/cache folders by name, but an explicit legitimate recovery root is now allowed under the OS temporary directory. This makes install-time recovery tests deterministic on Windows without weakening normal recovery scanning.


## V3.8 live progress heartbeat
V3.8 keeps the V3.7 side-by-side safe upgrade and fixes long AI stages that appeared frozen. Document Studio now reports planning, research, drafting, validation, export and finalisation milestones, with monotonic heartbeat progress inside long provider calls. Mainframe also shows elapsed still-active status when a precise percentage has not changed.

## V3.7 safe Windows upgrade
V3.7 installs into a new versioned program folder instead of deleting the currently running Agape folder. The previous V3.6 program folder is retained as rollback. Immediately before starting the new release, the installer verifies Agape ownership of ports 8850, 8851 and 8852 by their health endpoints, stops only those verified Agape processes, waits for the ports to release, and then starts V3.7. This prevents Windows file-lock failures caused by the Mainframe, Document Studio or workflow bridge still using the previous installation.


## V3.9 truthful progress and writing cleanup
V3.9 normalises escaped prose line-break markers before spelling/grammar analysis, preventing false words such as `nAgape` and `nBefore`. Common prose typos including `complate`, `dont` and `eption` are handled as safe corrections. Progress is now bounded by the active concrete stage, so an early planning step cannot be displayed as 94% complete; long stages still retain monotonic heartbeat activity.


## V4.1 human source + draft progress
Saved projects now become clean human-readable source notes instead of raw JSON. Technical/structured lines are excluded from prose suggestions, and document drafting reports specialist/section/Lead Editor sub-stages so the progress display does not remain falsely labelled as Researching.


## V4.2 Windows SQLite handle fix

- Mainframe database access now uses a real closing context manager.
- Every transaction commits or rolls back and always closes the SQLite connection.
- Fixes WinError 32 during installer test TemporaryDirectory cleanup on Windows.
- Adds a regression test proving the connection is closed after the context exits.
- Provider reliability and terminal activity sync from V4.1 are preserved.


## V4.3 resumable source preparation

- Source-preparation requests are persisted in the Agape data folder while they are running.
- If Mainframe exits or restarts, the next status poll can resume an abandoned source-preparation job from the saved request.
- The workflow bridge treats `prepare_request_id` as an idempotency key, preventing duplicate intake records after a restart.
- Mainframe health exposes a process instance ID so the browser can tell a real restart from a brief connection interruption.
- The browser no longer reconnects forever: it checks Mainframe health, recognises restarts, and gives a clear offline action after a bounded retry window.
- The visible server launcher automatically restarts Mainframe after an unexpected exit, up to three times.
- V4.2's explicit SQLite close fix remains in place.
## V4.4 Gold review failover reliability

V4.4 makes Gold Standard review non-destructive. Reviewer connections are runtime-preflighted before review begins. Stale ChatGPT/Codex paths, invalid API keys, and providers without usable quota are skipped. When fewer than two selected reviewers are actually ready, Agape can add healthy local Ollama as a reviewer. If online reviewers pass a status endpoint but fail during generation, Ollama gets one fallback attempt. If no reviewer or lead synthesis can run, Agape returns the already-created validated document with a review-unavailable diagnostic instead of failing the entire document job.

Release validation: 79/79 Mainframe tests and 52/52 workflow tests PASS.



## V4.5 saved-project context reliability

V4.5 prevents a saved project from becoming an all-None brief when an AI form-fill response is weak or unavailable. High-confidence facts are deterministically seeded from the project title and labelled user context before AI runs, then preserved after AI completion. Substantive assistant project summaries can be used as secondary context, while raw JSON and generic assistant boilerplate remain excluded. The human review screen now says how many fields are established and how many need attention instead of counting literal None values as completed.

Release validation: 81/81 Mainframe tests and 54/54 workflow tests PASS. Document Studio remains R31.15.


## V4.6 safe runtime cutover

V4.6 prevents the visible server watchdog from restarting Mainframe during an installer cutover. The installer requests a clean runtime stop, terminates a verified legacy Agape watchdog parent when needed, and verifies ports 8850/8851/8852 are free before starting the new build.


## V4.7 targeted validation repair

V4.7 fixes document jobs that reached final validation but failed because present sections such as **Findings** or **Analysis** were still below the quality-length threshold. Document Studio R31.16 repairs weak sections one at a time, provides the exact validator minimum plus a higher repair target, retries a section when the model returns an undersized response, and revalidates after replacement. Missing required headings remain a hard failure. If every required heading exists but a section is still short after all repair attempts, Agape preserves the generated document and returns a visible validation warning instead of discarding the entire result.

Release validation: 81/81 Mainframe tests and 56/56 workflow/document tests PASS.

## V4.9 real-click QA

V4.9 adds a visible **Settings -> Real click testing** area. Agape can launch Chromium through Playwright, click the major safe UI controls, verify persisted coding settings and diagnostics, and save screenshots plus JSON evidence. The safe unattended gate deliberately does not start AI work, install external software or run project recovery.

On Windows, an optional `pywinauto` bridge can launch and verify VS Code or Theia Full windows. This lets browser/UI validation and native coding-tool validation remain separate but visible in one QA area.


## V5.0 Workspace

The main navigation now includes **Workspace**. It provides a lightweight VS Code-style filing view for saved projects/results, a centre preview area, and a persistent to-do plus recent jobs panel. Full code editing can still be delegated to VS Code or Theia from Coding Tools.


## V5.1 Right-click menus

Workspace supports context-sensitive right-click actions for projects, results/jobs, to-do items and the blank file-tree area.


## V5.2 optional testing tools

Settings now includes an optional Testing Tools manager. The installer also offers a plain-language opt-in step for accessibility, API edge-case, security, browser-quality, load, Windows desktop and Android testing tools. The recommended set is axe + Schemathesis + OWASP ZAP + Lighthouse CI. Optional tools never block the core Agape install if their own installation fails.
