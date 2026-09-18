# Agape V3.5 - Past Project Recovery

V3.5 adds the missing recovery/migration phase for historic Agape projects.

## What changed

- Finds the newest healthy live `dmt_core.sqlite3` instead of using the first old copy found.
- Scans known historic Agape/DMT project database locations for `dmt_core.sqlite3` and `dmt_memory.sqlite3`.
- Skips installer fixtures, isolated test data, template/system/test projects and known mock projects.
- Creates a SQLite-consistent safety backup of the current live Core database before any recovery write.
- Merges missing user projects by normalised project name, never by historic numeric ID.
- Merges missing project messages without duplicating messages already present.
- Restores loop settings only when the current project has none.
- Missing historic projects are restored as visible user projects; existing projects keep their current state.
- Recovery is idempotent: running it again does not duplicate projects or messages.
- Installer runs recovery automatically after all staged tests pass.
- Projects page includes **Recover past projects** for later rescans.
- Writes a JSON recovery report plus the path of the safety backup.

The recovery step does not delete or overwrite the historic source databases.
