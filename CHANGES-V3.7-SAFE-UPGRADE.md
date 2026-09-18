# Agape V3.7 - Safe Side-by-Side Windows Upgrade

- No longer deletes the live V3.6 program folder during upgrade.
- Installs V3.7 side-by-side and retains V3.6 as rollback.
- Verifies Agape ownership before stopping listeners on ports 8850, 8851 and 8852.
- Stops Mainframe, Document Studio and Workflow Bridge before switching runtime.
- Never blanket-kills all python.exe processes.
- Persistent data remains in the existing Agape-Mainframe-V3 data folder.
