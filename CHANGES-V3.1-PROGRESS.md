# Agape V3.1 - Progress reliability

- Replaced polling-count progress with stage-based overall progress.
- Backend progress is monotonic: nested document/review workers cannot move the overall percentage backwards.
- Browser independently enforces a never-decrease rule.
- Added visible stage and percentage labels.
- Validation repair and Gold review are mapped into later overall progress bands rather than resetting to the start.
- Completion always ends at 100%.
- Failure is shown as a stopped red bar rather than a bouncing working bar.
