# Agape AI Studio V0.3 R2 - Parts Map

## Integrated and tested parts

| Area | Part | Responsibility | Status |
|---|---|---|---:|
| Core | Studio shell | One-page Home / Workspace | PASS |
| Core | Projects/files | Create/open/recent/list/read/write with path guard | PASS |
| Core | Terminal | Controlled argv execution and persistent history | PASS |
| Core | AI | Provider abstraction, local model routing and history | PASS |
| Core | Extensions | Out-of-process deterministic development helpers | PASS |
| Core | Persistence | SQLite state, restart persistence and additive migrations | PASS |
| Free AI | OpenRouter Free | Live catalogue and strict zero-cost text filtering | PASS |
| Free AI | Free model router | Task-aware ranking and best-free selection | PASS |
| Free AI | Fallback | Local failure -> allowed free-online model | PASS |
| Free AI | Connection tests | Provider/model test outcomes persisted | PASS |
| Quality | Passed ledger | Requirement IDs and permanent evidence | PASS |
| Quality | Markdown process | Compact terminal gates + detailed AI repair report | PASS |
| Aider | CLI adapter | Optional external repo-aware coding engine | PASS |
| Aider | Model bridge | Ollama -> `ollama_chat/`; OpenRouter -> `openrouter/` | PASS |
| Aider | Planner | Select Aider only for suitable coding work | PASS |
| Aider | Safety | Registered + clean Git repo, explicit run, no shell/auto-commit | PASS |
| Aider | Evidence | Tool run results persisted in SQLite | PASS |
| Aider | Fallback | Missing Aider does not break Studio | PASS |
| Aider | UI | Visible status and explicit Run Aider control | PASS |

## Still deliberately deferred

These remain future product layers and are not silently half-enabled:

- Monaco/Code-OSS editor integration
- Broader VS Code extension compatibility/marketplace work
- Rich Git workbench UI
- Language server/debug adapter integration
- Full Studio-owned AutoDev edit -> test -> repair -> retest loop
- Long-running autonomous development
- Stable Beta release process

## Production rule

Every new part gets a requirement ID, narrow tests, a live integration template and Markdown evidence. It moves into **Passed** only after the packaged-source release gate proves it without breaking previous parts.
