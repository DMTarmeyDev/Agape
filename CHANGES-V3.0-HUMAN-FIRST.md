# Agape V3.0 — Human-First 3-Step Release

## User workflow

- Reduced normal document creation to **Source → Review → Result**.
- Source selection is mutually exclusive: Paste, Upload or Saved Project.
- After a source is chosen, the other source branches are hidden and excluded from the backend payload.
- Removed the separate quality, continue and manual-save stages from the normal path.
- Review shows unresolved/important items first and collapses already-resolved details.
- Current edits are saved automatically before creation.
- Result contains progress, downloads, versions and AI revision in one place.

## Writing quality

- Added native browser spellcheck/autocapitalisation to editable prose fields.
- Added UK-English backend writing-quality checks to pasted, uploaded and saved-project source text.
- Applies only high-confidence mechanical fixes to the AI-facing extracted text.
- Uncertain spelling/grammar findings are suggestions, not silent replacements.
- Original uploaded files are preserved unchanged.

## Speed and logic

- New installs default to Standard rather than Gold for faster normal work.
- Gold Standard default reviewer count reduced from 10 to 3; 2–10 remains selectable.
- Document jobs no longer probe Work Engine/development services before starting.
- Bundled Python Document Studio is preferred over legacy PowerShell activation.
- Full system setup probes are deferred from normal page boot unless setup is incomplete.
- Existing fast health, async long-document jobs, resume-after-restart and validation-repair logic retained.

## Data and compatibility

- Mainframe persistent data moves to `Agape-Mainframe-V3\data`.
- First use migrates V2 settings/database non-destructively; V1 is fallback.
- Previous data/installations are not deleted.
