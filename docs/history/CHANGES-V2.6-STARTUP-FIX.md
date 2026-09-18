# Agape startup fix V2.6

- `/api/health` is now a lightweight liveness endpoint and no longer waits for optional services.
- Optional service probes run concurrently through `/api/services`.
- The installer can detect and replace a previous Agape listener on port 8850 before launching the repaired build.
