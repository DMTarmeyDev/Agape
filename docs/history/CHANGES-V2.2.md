# Agape Mainframe V2.2

## Installer security and clarity

- One obvious root launcher: `INSTALL AGAPE - DOUBLE CLICK THIS.cmd`.
- Normal installer path no longer uses `-ExecutionPolicy Bypass`.
- Before changing the computer, the installer asks **Did you start this Agape installation?**
- Choices: **Allow once**, **Trust this exact installer version**, or **Trust signed publisher** when Windows validates a real Authenticode signature.
- The current test release is unsigned, so publisher trust is intentionally unavailable; exact-version trust is based on SHA-256.
- Package files are checked against `PACKAGE-MANIFEST.json` before installation. Modified/missing files stop the install.
- Approvals and an audit log are stored under `%LOCALAPPDATA%\Agape\Security`.
- Settings now includes **Approved installers**, where exact/publisher approvals can be reviewed and revoked.
- No Microsoft Defender disabling, no blanket exclusions, no silent Windows Security changes.

## Existing V2 workflow retained

- Paste text or upload document.
- AI fills the brief.
- AI can research missing information.
- Change completed brief with AI.
- Create Now / Gold Standard.
- Change finished document with AI while keeping version lineage.
- Technical/legacy controls remain under Advanced or are removed when superseded.
