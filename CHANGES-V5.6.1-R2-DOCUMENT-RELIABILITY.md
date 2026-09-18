# Agape V5.6.1 R2 - Document Reliability Repair

- Prevents Windows `WinError 3` during LibreOffice conversion by always launching it from an explicit existing runtime directory.
- Rejects stale same-version Document Studio child services by checking a build marker as well as the version.
- Keeps Download Manager scoped to the current creation job so older completed files are not shown as outputs of a failed run.
- Creation failures now tell the user to fix the creation problem and run Create result again; only real download failures offer Retry download.
- Business-document validation now detects duplicate required sections and repairs/reconciles them instead of allowing multiple competing versions to pass.
- Removes the internal `User Safety: safe` marker from generated client documents and normalises raw deep Markdown headings.
- Updates the bundled launcher to expect the current V5.6.1 build.
- Includes the redesigned Gold public website in `website/index.html`.
