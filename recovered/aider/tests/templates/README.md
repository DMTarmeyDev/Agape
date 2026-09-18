# Live test templates

JSON templates define the live acceptance groups. The Python runner loads each case from `tests/live_cases.py`, runs the real HTTP boundary on isolated ports, and writes Markdown evidence.

Required groups cover core server/UI, projects/files, terminal, Agape AI, extensions, complete Studio journey, Free AI, quality/Passed ledger, and Aider tool integration.

Environment-specific probes for real Ollama, real OpenRouter catalogue access and a real Aider installation are optional. Their deterministic fake-provider/fake-Aider contracts are required and cannot be skipped.
