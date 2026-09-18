# V5.5 Review, Download Manager and Full QA

## User-facing changes

- Missing-information fields live inside a closed-by-default disclosure menu.
- The disclosure summary always shows the number of items needing attention.
- Public-information research has its own progress bar and human-readable stage text.
- **Change the brief with AI** is closed by default and expands only when requested.
- Result creation exposes a deeper Download Manager with preparation/download state, progress, ETA, instructions, failures, retry, download-again and open-folder actions.

## Finished-document download fix

The Mainframe download proxy previously used legacy port 8840 while the active Workflow Bridge runs on port 8852. V5.5 resolves downloads through the configured/current `R24` endpoint, preserves upstream HTTP failures for useful retry behaviour, and disables response caching.

## QA gate

`scripts/full_dummy_qa.py` creates isolated synthetic data and exercises the complete user flow without touching real projects. It tests both browser interactions and a real Mainframe HTTP proxy connected to the fake Workflow Bridge on port 8852. Downloaded DOCX/PDF files are checked as actual file formats.

The V5.5 verification run completed 111/111 regression tests and 22/22 full dummy QA actions with zero browser console/page errors.
