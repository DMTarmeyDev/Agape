# Agape V4.2 - Windows SQLite Handle Fix

V4.2 fixes a Windows-only installer test failure in terminal activity synchronisation.

## Root cause

`sqlite3.Connection` used as `with connection:` commits or rolls back but does not close the connection. Mainframe's `db()` returned a raw connection, so test code left `mainframe.sqlite3` open until garbage collection. Linux permits deletion of open files; Windows returns WinError 32.

## Fix

- `state.db()` is now a real `contextmanager`.
- It always commits on success, rolls back on failure, and closes in `finally`.
- Existing `with db() as con:` callers retain the same transaction behaviour while deterministically releasing the file handle.
- Added regression coverage proving the connection is closed after context exit.

No cleanup errors are ignored or suppressed.
