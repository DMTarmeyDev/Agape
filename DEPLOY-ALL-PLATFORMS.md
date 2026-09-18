# Deploy Agape V5.6.1 R2.5.0

The supported deployment path is `AGAPE-V5.6.1-R2.5.0-ALL-PLATFORMS-PUSH-DEPLOY.ps1`.

It creates a test/release branch, runs the full regression suite, pushes the branch to GitHub, updates or creates an Agape Codespace, restarts only the Mainframe preview in that Codespace, verifies the local Windows Mainframe, checks the existing Tailscale Funnel without resetting a healthy mapping, triggers the cross-platform GitHub Actions build, waits for it to finish and downloads the Windows/macOS/Linux/Android artifacts.

The script intentionally does not merge `main`. Test the branch and artifacts first.
