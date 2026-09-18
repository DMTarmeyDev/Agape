# Publish Agape to GitHub

This package contains the GitHub Actions needed to test on Windows/macOS/Linux and build release downloads from a version tag.

## Easiest Windows route

1. Install Git and GitHub CLI (`gh`).
2. Sign in with `gh auth login`.
3. Open PowerShell in this source folder.
4. Run:

```powershell
.\PUBLISH-TO-GITHUB.ps1 -Repository "YOUR-GITHUB-NAME/agape" -Visibility public -Tag v5.5.0
```

The script does not ask for or store a GitHub password/token. Authentication is handled by GitHub CLI.

After the tag is pushed, GitHub Actions will run the tests and then publish the release files if the native builds pass.


Before any commit is pushed, the publish script runs `scripts/public_audit.py`. It blocks obvious private keys, personal Windows user paths, databases, compiled Python files, and certificate/private-key files from the public release tree.
