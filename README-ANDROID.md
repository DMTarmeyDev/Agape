# Agape Android Alpha

The Android app is a small native shell for the same Agape backend used by the desktop and iOS versions.

Default endpoint:

`https://agape-alpha.tail2a2d28.ts.net/`

## Behaviour

- phones open the touch-friendly `?view=webapp&android=1` view;
- tablets can choose touch-friendly or full desktop layout;
- the **View** action changes that choice later;
- Android Back navigates Agape browser history;
- uploads use the Android system file picker;
- normal HTTPS downloads use Android Download Manager;
- external links open in the normal browser/app;
- only the configured Agape HTTPS host stays inside the WebView;
- cleartext HTTP is disabled;
- SSL/TLS errors are never bypassed;
- an offline/retry screen is shown when Agape cannot be reached.

## Requirements

- Android 10 / API 29 or later;
- internet access;
- a reachable Agape backend, normally through the configured Tailscale HTTPS endpoint.

## Build

The repository cross-platform workflow uses:

- Android SDK/API 36;
- Android Gradle Plugin 9.4.0;
- Gradle 9.6.0;
- JDK 17.

Manual build from the repository root:

```bash
gradle --no-daemon -p android-app :app:assembleDebug \
  -PagapeBaseUrl="https://agape-alpha.tail2a2d28.ts.net/"
```

Output:

`android-app/app/build/outputs/apk/debug/app-debug.apk`

The GitHub preview/release workflows verify `classes.dex` exists before publishing the APK.

## Install for Alpha testing

Use the `Agape-Android-debug.apk` artifact from GitHub Actions or GitHub Releases. It is debug-signed for Alpha testing. Public Play Store distribution should use a protected release signing key and an Android App Bundle (`.aab`).
