# Agape V4.1 - Provider Reliability and Complete Activity

- Verifies provider execution paths before long document jobs.
- Invalid/stale ChatGPT Codex executable holds are discarded and re-detected.
- Ollama must produce a short live probe before it is trusted for document generation.
- Local Ollama fallback prefers the 1.5B coder model when available and uses bounded generation limits.
- If no provider is ready, the job stops quickly with ACTION_REQUIRED instead of retrying multi-minute timeouts.
- Mainframe Activity now mirrors delegated bridge PASS/FAIL/BLOCKED terminal states against the original run ID.
- Internal mock recovery projects are hidden/excluded without deleting user data.
