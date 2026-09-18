# Agape V3.0 Logic Audit

## Rule used

A user decision should reduce the system's active logic. Once Agape knows the source, route or experience level, code for impossible alternatives should stop running rather than remain active in parallel.

## Active normal path

`Choose one source -> AI intake/writing check -> Review only what matters -> Create -> Result/revise`

### Source decision

- Paste selected: upload/project source is discarded.
- Upload selected: paste/project source is discarded.
- Saved project selected: paste/upload source is discarded.
- No source selected: remain at Step 1 with a human-readable prompt; do not create a failed result job.

### Route decision

- Document route checks Document Studio only.
- Development/project-loop route checks Core/Work Engine only when that route is used.
- Normal app boot uses fast health/settings and avoids full service probing when setup is already complete.

### Review decision

- Missing/important items are visible first.
- Completed details remain available but collapsed.
- No missing items means the missing-information action is removed from the active UI.
- Basic experience avoids unnecessary quality/model decisions.

### Creation decision

- Standard is the normal fast default.
- Gold Standard starts with 3 reviewers; larger reviewer counts are explicit user choices.
- Long document work uses background jobs and status polling instead of one long HTTP socket.

## Legacy logic policy

Recovered capability code is retained only when it is required for an active capability or rollback/provenance. Legacy launchers are not called in the normal path when a current Python entry point exists. Superseded normal-UI controls are removed rather than left visible in Settings.

## Compatibility-path note

Some internal recovered folders retain historical names (for example `recovered/unified-r24`) because current bridge code and recovery evidence reference those paths. Their **runtime build/version is V3.0**, and the historical folder name is not exposed in the normal UI. Renaming those directories solely for appearance would add migration risk without improving the human workflow.
