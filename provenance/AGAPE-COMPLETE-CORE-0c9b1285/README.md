# DMT Core V1.4 AutoDev R2

Clean development-loop release built from the proven V1.3.1 R4 core.

## AutoDev flow

Project goal -> load project/workspace state -> auto-select local coding model -> inspect -> one bounded file edit -> run the configured test through the Core terminal runner -> feed failures back to the model -> repeat -> commit passing checkpoint or automatically restore unproven edits.

Safety: workspace confinement, path-traversal blocking, text-only edits, one file per AI edit, allowlisted test commands, terminal job audit history, backup journal before every edit, rollback after failing bounded runs, and restart recovery for interrupted edits.

The installer runs offline regression tests, a live HTTP/fake-provider integration test, then real Windows/Ollama Template 1, Template 2, Project Loop and system-test preflights before side-by-side cutover. V1.3.1 R4 is left available as rollback.

## R2 Windows runner fix

Project tests are launched directly from the allowlisted executable instead of through PowerShell -Command. This preserves Windows PowerShell 5.1 compatibility for quoted Python paths while keeping shell operators blocked.


## V1.8 Stages 31-40 release
Includes project catalog separation, safe database migration, development analysis tools, issue memory, model escalation, dependency/impact/test planning, risk gating, changelog and release comparison. System/template/test projects are preserved but hidden from the normal project list.

## V1.9 Stages 41-50 release
Adds persistent AutoDev sessions, validated task graphs, scope/drift locks, failure triage, model outcome scorecards, adaptive routing, safe resume decisions, acceptance aggregation, a tamper-evident run ledger, and a bounded resumable AutoDev cycle coordinator. The existing Project Loop remains the only execution engine for AI file edits and tests.

## V2.0 Stages 51-60 release
Adds requirements and acceptance traceability, bounded change budgets, stale-context detection, deterministic retry/backoff decisions, repair verification, dependency-aware task selection, evidence-based completion, regression planning, release-confidence scoring, and a quality-controlled bounded self-healing controller. The existing Project Loop remains the execution boundary; V2.0 adds stronger gates around it rather than bypassing it.

## V2.1 Stages 61-70 release
Adds runtime/source/database baseline attestation, secret-redacted failure evidence, deterministic root-cause ranking, safe minimal reproduction planning, repair-candidate scoring, persisted flaky-test observations, verified checkpoint selection, whole-run execution budgets, low-risk autonomous continuation with high-risk approval boundaries, and a governed end-to-end AutoDev controller. The governor composes the existing bounded Project Loop and V2.0 quality-controlled self-heal rather than bypassing them.

## V2.2 Stages 71-80 release
Adds durable work-plan construction, interruption recovery decisions, project-wide dependency state, confidence tracking, stale-failure suppression, safe parallelism advice, checkpoint cadence policy, regression memory, cryptographic completion proof, and a persistent bounded development supervisor. The supervisor composes the proven V2.1 AutoDev governor and existing Project Loop safety boundary; it does not permit unrestricted background or system execution.


## V3.0 Alpha completion - Stages 81-100
V3.0 completes the alpha-critical path in one release: provider abstraction and safe online-provider configuration, failover/request budgets, deferred work, verified backups, project portability, sanitized diagnostics, instance/schema/startup guards, tamper-evident audit events, provider resilience, user-readiness/safety/retention/resource gates, mission proof, and one final alpha release controller. Plaintext API keys are not stored; online provider connections reference an environment variable. Restore remains approval-gated and hard deletion remains disabled by default.


## V3.1 Early Alpha closure
V3.1 closes the historical acceptance checklist against the current superseding release. It adds a complete Database Manager UI for health, approved table browsing and verified backups; a saved connection-outcomes view; and one consolidated closure gate covering legacy V1.7 acceptance, dual-model routing, real bounded repair/retest, rollback proof, database management, connection-test persistence, menu/project/Agape branding, and stable early-alpha checkpointing.
