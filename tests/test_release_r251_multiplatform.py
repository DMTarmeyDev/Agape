from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_readme_has_no_scraped_svg_or_github_dom_links():
    text = read("README.md")
    for bad in (
        "[svg]",
        "**svg**",
        "## Aboutsvg",
        "#readme-ov-file",
        "#License-1-ov-file",
        "#coc-ov-file",
        "#contributing-ov-file",
        "#security-ov-file",
    ):
        assert bad not in text


def test_readme_uses_release_page_not_brittle_latest_asset_urls():
    text = read("README.md")
    assert "https://github.com/DMTarmeyDev/Agape/releases/latest" in text
    assert "releases/latest/download/" not in text


def test_readme_current_version_and_all_platforms():
    text = read("README.md")
    assert "V5.6.1 / R2.5.1" in text
    for platform in ("Windows", "macOS", "Linux", "Android", "iPhone/iPad", "GitHub Codespaces"):
        assert platform in text


def test_readme_relative_links_exist():
    text = read("README.md")
    targets = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text)
    for raw in targets:
        target = raw.split(" ", 1)[0].strip("<>")
        if target.startswith(("https://", "http://", "mailto:", "tel:", "#")):
            continue
        target = target.split("#", 1)[0].split("?", 1)[0]
        if target:
            assert (ROOT / target).exists(), target


def test_android_version_and_secure_base_url_contract():
    gradle = read("android-app/app/build.gradle.kts")
    java = read("android-app/app/src/main/java/dev/dmtarmey/agape/MainActivity.java")
    manifest = read("android-app/app/src/main/AndroidManifest.xml")
    assert "versionCode = 251" in gradle
    assert 'versionName = "5.6.1-r2.5.1-alpha"' in gradle
    assert "AGAPE_BASE_URL" in gradle
    assert "https://agape-alpha.tail2a2d28.ts.net/" in gradle
    assert "AgapeAndroid/5.6.1-r2.5.1" in java
    assert 'android:usesCleartextTraffic="false"' in manifest
    assert "handler.cancel()" in java


def test_ios_project_and_secure_wrapper_contract():
    swift = read("ios-app/AgapeMobile/AgapeMobileApp.swift")
    project = read("ios-app/AgapeMobile.xcodeproj/project.pbxproj")
    scheme = ROOT / "ios-app/AgapeMobile.xcodeproj/xcshareddata/xcschemes/AgapeMobile.xcscheme"
    assert scheme.is_file()
    assert "WKWebView" in swift
    assert "https://agape-alpha.tail2a2d28.ts.net/" in swift
    assert 'candidate.scheme?.lowercased() == "https"' in swift
    assert "AgapeIOS/5.6.1-r2.5.1" in swift
    assert "CURRENT_PROJECT_VERSION = 251" in project
    assert "MARKETING_VERSION = 5.6.1" in project
    assert "IPHONEOS_DEPLOYMENT_TARGET = 15.0" in project
    assert 'SUPPORTED_PLATFORMS = "iphoneos iphonesimulator"' in project


def test_preview_workflow_builds_all_five_platform_targets():
    workflow = read(".github/workflows/cross-platform-preview.yml")
    for value in (
        "windows-latest",
        "macos-latest",
        "ubuntu-latest",
        "Agape-Android",
        "Agape-iOS-Simulator",
        "xcodebuild",
        "android-36",
    ):
        assert value in workflow


def test_release_workflow_publishes_all_release_assets():
    workflow = read(".github/workflows/release.yml")
    for asset in (
        "Agape-Windows.exe",
        "Agape-macOS.zip",
        "Agape-Linux-x86_64",
        "Agape-Android-debug.apk",
        "Agape-iOS-Simulator.zip",
        "SHA256SUMS.txt",
    ):
        assert asset in workflow
    assert "needs: [build, android, ios]" in workflow


def test_codespace_contract_keeps_agape_ports():
    devcontainer = json.loads(read(".devcontainer/devcontainer.json"))
    deploy = read("scripts/deploy_codespace_preview.sh")
    assert devcontainer["forwardPorts"] == [8850, 8851, 8852]
    assert 'PORT="${AGAPE_PORT:-8850}"' in deploy
    assert "CODESPACE_AGAPE=PASS" in deploy


def test_current_publish_docs_no_longer_default_to_v55():
    publish = read("PUBLISH-TO-GITHUB.ps1")
    docs = read("PUBLISH-TO-GITHUB.md")
    assert "v5.5.0" not in publish
    assert "v5.5.0" not in docs
