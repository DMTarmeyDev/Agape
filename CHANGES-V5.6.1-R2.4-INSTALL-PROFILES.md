# Agape V5.6.1 R2.4 - Installation Profiles and Heavy Tool Setup

## Why
The Settings screen exposed three related problems:
- optional tools were shown individually without a coherent low/medium/high install plan;
- OWASP ZAP, Appium Android and OpenHands had incomplete prerequisite setup paths;
- the safe browser QA could close the Advanced details panel and then try to click a hidden diagnostics button.

## Changes
- Keeps the stored experience values `basic`, `standard`, `advanced` for backwards compatibility but labels them:
  - Essential / Low use
  - Standard / Medium use
  - Full Developer/Admin / High use
- Adds an Installation profile section in Settings with explicit one-click, confirmed profile setup.
- Standard profile installs/checks the common developer set: Git, VS Code, Node.js LTS, axe, Schemathesis, Lighthouse and Chromium QA.
- Full Developer/Admin adds Aider/Ollama support, ZAP, k6, Appium Android and OpenHands setup.
- ZAP setup now verifies Java 17+ and installs Temurin JDK 21 when needed before ZAP.
- Appium Android setup now verifies Node/npm versions, installs Appium, Java, Android platform tools and UiAutomator2, and finishes with `appium driver doctor uiautomator2`.
- OpenHands now has an in-app Install action. On Windows it detects WSL/Ubuntu and installs OpenHands in WSL using the current documented `uv tool install openhands --python 3.12` flow.
- OpenHands can be launched from Agape once ready.
- Heavy security/mobile tools are no longer labelled part of the Standard recommended testing set.
- Fixed browser QA Advanced diagnostics handling by checking the DOM boolean `open` property instead of truth-testing the empty-string HTML attribute value.

## Validation
- Mainframe tests: 155/155 PASS
- Unified workflow tests: 57/57 PASS
- Full dummy/backend/browser QA: 25/25 PASS
- Browser console errors: 0
- Browser page errors: 0
- JavaScript syntax check: PASS
