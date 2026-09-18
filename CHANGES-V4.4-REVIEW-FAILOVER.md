# Agape V4.4 - Review Failover Reliability

V4.4 fixes Gold Standard final review failing after a valid document has already been created when configured reviewer providers are stale, invalid, out of credit, or otherwise unable to generate.

Changes:
- Every selected reviewer is runtime-preflighted before final review.
- Stale ChatGPT/Codex paths and invalid API keys are skipped before review calls.
- Healthy local Ollama is automatically added as a fallback reviewer when fewer than two selected reviewers are actually usable.
- If online reviewer credentials pass a status endpoint but generation still fails, Agape tries healthy Ollama once.
- If no reviewer can run, the Gold review is marked unavailable instead of failed.
- An already-created, validated document is returned to the user with review diagnostics rather than discarded because optional reviewers are unavailable.
- Unified workflow recognises the non-fatal `unavailable` review state.
