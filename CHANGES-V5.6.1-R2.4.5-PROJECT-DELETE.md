# Agape V5.6.1 R2.4.5 - Project delete

- Adds a visible Delete action beside each saved user project on the Projects page.
- Requires explicit browser confirmation before deletion.
- Adds Mainframe POST /api/projects/delete.
- Deletes only kind=user projects; internal/system/template/test/autodev projects are rejected.
- Enables SQLite foreign keys so Core project-owned rows use their existing cascade/set-null rules.
- Keeps generated Mainframe Results & versions history intact.
- Refreshes Projects immediately after deletion and refreshes Workspace when open.
