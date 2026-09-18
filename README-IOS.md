# Agape iPhone/iPad Alpha

The iOS project is a native SwiftUI/WKWebView shell for the same Agape backend used by desktop and Android.

Default endpoint:

`https://agape-alpha.tail2a2d28.ts.net/`

## Behaviour

- opens Agape in touch-friendly `?view=webapp&ios=1` mode;
- only the configured Agape HTTPS host navigates inside the embedded WebView;
- external HTTPS/HTTP/mail/tel links are handed to iOS;
- cleartext is not enabled by App Transport Security exceptions;
- TLS validation is left to WebKit and is never bypassed;
- normal WebKit file selection remains available;
- Agape download links are handed to iOS/Safari;
- provides Back, Reload, online/loading status and a retry screen.

## Build in Xcode

Open:

`ios-app/AgapeMobile.xcodeproj`

Select the **AgapeMobile** scheme and an iPhone/iPad Simulator, then Build/Run.

The endpoint can be overridden as the Xcode build setting `AGAPE_BASE_URL` and must use HTTPS.

## GitHub Actions

The cross-platform preview and tagged-release workflows compile an unsigned iOS Simulator build on a native GitHub macOS runner. The artifact is:

`Agape-iOS-Simulator.zip`

This proves the iOS source/project compiles, but the simulator package is not an installable iPhone IPA.

## Physical iPhone/iPad distribution

A real-device/TestFlight/App Store build requires an Apple Developer team, signing certificate and provisioning profile. Those credentials are intentionally not committed to this public repository. Add protected GitHub secrets/signing configuration before producing a signed IPA or submitting to TestFlight/App Store.
