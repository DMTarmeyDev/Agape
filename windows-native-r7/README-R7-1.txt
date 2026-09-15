Agape Windows 11 Main Project Native Desktop R7.1

Fix from R7:
- Project API archived field now accepts JSON booleans, numeric 0/1, and common string forms.
- This fixes: json: cannot unmarshal number into Go struct field projectRecord.projects.archived of type bool
- Native embedded WebView2 architecture unchanged.
- Existing Agape V3.1 Core, database, model router and project data remain external/live and are not replaced.
