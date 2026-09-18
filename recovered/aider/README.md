# Agape AI Studio V0.3 R2 - Windows Reliability + Aider Tooling

Agape AI Studio now has a clean one-page Studio foundation, local + free-online AI routing, a persistent quality ledger, and an **optional Aider coding engine** behind the Studio tool boundary.

## Why Aider is included

Aider is useful for repo-aware coding work because it already supplies repository mapping, git-aware editing and one-shot coding workflows. Agape does not hand control of the product to Aider. Studio keeps ownership of project scope, model selection, deterministic formatting/linting, testing, evidence, checkpoints and release promotion.

Aider is therefore a **replaceable coding engine**, not a core dependency.

## Aider routing rules

- Formatting, spelling and routine linting -> deterministic Studio extensions.
- Explanation/light code questions -> Agape AI.
- Suitable repo-wide/multi-file/refactor/test-repair task + Aider ready + registered clean Git repo -> Aider is recommended.
- Aider execution always requires the explicit **Run Aider** action in V0.3.
- Dirty or unregistered repositories are blocked from Aider execution.
- Aider auto-commit, auto-test and auto-lint are disabled; Studio owns those gates.
- Local Ollama models are mapped to `ollama_chat/<model>`.
- Free OpenRouter models are mapped to `openrouter/<provider>/<model>` form.
- API keys remain in environment variables; they are never placed on Aider's command line.
- If Aider is absent/unhealthy, Studio continues using Agape AI.

## Existing working parts

- One-page Home / Workspace UI
- Recent projects and persistent state
- File explorer/read/write editor API
- Resizable bottom terminal
- Formatter, spell-checker and code-cleaner extensions
- SQLite Studio state
- Ollama local provider
- OpenRouter zero-cost text-model discovery
- Automatic best-free-model ranking
- Local -> free-online fallback
- Saved provider/model test outcomes
- AI Model Manager
- Passed menu / quality ledger
- Aider status, planner bridge, safe execution and run evidence
- Narrow post-patch tests
- Template-driven full live test suite
- Compact terminal gates + detailed Markdown AI repair report
- Temp-first install/test/promote/rollback process

## Fast development commands

After a patch:

```powershell
.\TEST-AFTER-PATCH.ps1
```

Before promotion:

```powershell
.\RUN-ALL-TESTS.ps1
```

Install/test/promote from a candidate copy under `%TEMP%`:

```powershell
.\INSTALL-TEST-REPORT.ps1
```

Start Studio:

```powershell
.\START-STUDIO.ps1
```

## Release rule

No code becomes current merely because its component test passed. Promotion requires the full required suite to pass from the exact packaged source. Only then are closed requirements published into the Studio **Passed** menu.


## R2 Windows reliability repair

R2 closes faults found by the first real Windows install gate:

- Project file writes are byte-exact UTF-8, so LF input is not silently rewritten to CRLF.
- Ollama discovery uses a short timeout while real generation gets a longer warm-model timeout; the health probe prefers the installed 1.5B coder when available.
- Aider uses Agape's isolated managed install first. Unmanaged PATH copies are ignored unless `AGAPE_AIDER_ALLOW_PATH=1` is explicitly set.
- The real Ollama and real Aider environment probes remain optional diagnostics; required release quality is determined by deterministic component and integration gates.
