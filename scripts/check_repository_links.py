from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
PREVIEW = ROOT / ".github" / "workflows" / "cross-platform-preview.yml"

EXPECTED_RELEASE_ASSETS = {
    "Agape-Windows.exe",
    "Agape-macOS.zip",
    "Agape-Linux-x86_64",
    "Agape-Android-debug.apk",
    "Agape-iOS-Simulator.zip",
    "SHA256SUMS.txt",
}

BAD_README_MARKERS = (
    "[svg]",
    "**svg**",
    "## Aboutsvg",
    "#readme-ov-file",
    "#License-1-ov-file",
    "#coc-ov-file",
    "#contributing-ov-file",
    "#security-ov-file",
)


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    raise SystemExit(1)


def markdown_targets(text: str) -> list[str]:
    # Good enough for the repository's normal Markdown links and image links.
    return [m.group(1).strip() for m in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", text)]


def validate_local_target(target: str) -> None:
    target = target.split(" ", 1)[0].strip("<>")
    if not target or target.startswith(("http://", "https://", "mailto:", "tel:", "#")):
        return
    target = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not target:
        return
    candidate = (ROOT / target).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        fail(f"README local link escapes repository root: {target}")
    if not candidate.exists():
        fail(f"README local link target does not exist: {target}")


def main() -> int:
    text = README.read_text(encoding="utf-8")

    for marker in BAD_README_MARKERS:
        if marker in text:
            fail(f"README contains scraped/broken GitHub marker: {marker}")

    if "releases/latest/download/" in text:
        fail("README contains a brittle direct latest-release asset URL")

    if "V5.6.1 / R2.5.1" not in text:
        fail("README does not identify the current V5.6.1 / R2.5.1 line")

    for target in markdown_targets(text):
        validate_local_target(target)

    release = RELEASE.read_text(encoding="utf-8")
    preview = PREVIEW.read_text(encoding="utf-8")
    combined = release + "\n" + preview

    for asset in sorted(EXPECTED_RELEASE_ASSETS - {"SHA256SUMS.txt"}):
        if asset not in combined:
            fail(f"build workflows do not stage expected asset: {asset}")
    if "SHA256SUMS.txt" not in release:
        fail("release workflow does not produce SHA256SUMS.txt")

    for workflow in ("ci.yml", "test.yml", "codeql.yml"):
        if not (ROOT / ".github" / "workflows" / workflow).is_file():
            fail(f"README badge workflow is missing: {workflow}")

    if not (ROOT / "ios-app" / "AgapeMobile.xcodeproj" / "project.pbxproj").is_file():
        fail("iOS Xcode project is missing")
    if not (ROOT / "android-app" / "app" / "build.gradle.kts").is_file():
        fail("Android project is missing")

    print("REPOSITORY_LINK_AUDIT=PASS")
    print(f"README_LINKS_CHECKED={len(markdown_targets(text))}")
    print("RELEASE_ASSET_CONTRACT=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
