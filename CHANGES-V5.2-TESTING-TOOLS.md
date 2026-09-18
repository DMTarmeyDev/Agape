# V5.2 Optional Testing Tools

- Adds Settings -> Testing tools with status, plain-language purpose, install size/impact and per-tool install controls.
- Adds recommended set: axe accessibility testing, Schemathesis API testing, OWASP ZAP security scanning and Lighthouse CI.
- Adds optional specialist tools: Grafana k6 load testing, Appium Windows desktop testing and Appium Android testing.
- Installer asks whether to install the recommended set, all tools, choose individually, or skip.
- Every optional tool remains opt-in. Failure to install an optional tool does not fail Agape installation.
- No Windows Defender exclusions or silent trust changes are added.
