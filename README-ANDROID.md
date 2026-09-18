# Agape Android R1

This is a small native Android shell for the live Agape server at:

`https://agape-alpha.tail2a2d28.ts.net/`

## Behaviour

- Phone: opens Agape in touch-friendly `?view=webapp` mode.
- Tablet: first launch offers **Web App** or **Full App**.
- **View** in the toolbar lets the user switch later.
- Android back button navigates through Agape history.
- File uploads use Android's system file picker.
- Normal HTTPS downloads are handed to Android Download Manager.
- External links open in the normal browser/app.
- Only the exact Agape host is allowed to navigate inside the WebView.
- Cleartext HTTP is disabled.
- SSL errors are never bypassed.
- If the server is offline, the app shows a Retry screen.

## Requirements

- Android 10 (API 29) or later.
- Internet access.
- The Agape server and Tailscale Funnel must be running for the app to connect.

## Build without Android Studio

Copy the `android-app` directory and `.github/workflows/android-apk.yml` into the root of the Agape GitHub repository and push them.

GitHub Actions will build an installable debug APK named:

`Agape-Android-debug.apk`

Download the `Agape-Android-APK` artifact from the **Build Agape Android APK** workflow.

## Install on Android

1. Copy/download `Agape-Android-debug.apk` to the phone.
2. Open the APK.
3. Android may ask you to allow installation from that browser/files app. Allow it for this install.
4. Install **Agape**.
5. Open the app.

This R1 APK is debug-signed for Alpha testing. For Play Store/public distribution, create a protected release signing key and build a release/AAB instead.
