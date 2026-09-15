AGAPE WINDOWS 10/11 - NATIVE R6
===============================

RUN THIS:
  Agape-Setup-Native-R6.exe

WHAT THIS BUILD IS
- A real Windows x64 GUI executable named Agape.exe.
- Agape owns a native Win32 application window.
- Microsoft WebView2 is embedded inside that window.
- The exact currently installed Agape V3.1/R8 browser frontend remains the UI source of truth.
- The existing Python backend runs locally/hidden on port 8797.
- The main Agape window is NOT Edge/Chrome app mode and has no browser address bar.

CURRENT CODEBASE GATE
- Core: DMT-CORE-V3.1-EARLY-ALPHA-R8
- Document Studio baseline: R31.10
- Work Engine baseline: R1.3
- Latest rebuild reference: AGAPE-V3.1-FULL-REBUILD-R1.6

SAFE INSTALL PROCESS
1. Finds the current Agape V3.1 core.
2. Checks current R8 UI markers.
3. Builds a separate candidate desktop install folder.
4. Gets WebView2Loader.dll from local NuGet cache or Microsoft NuGet.
5. Checks/installs the Evergreen WebView2 Runtime if needed.
6. Runs Agape.exe --validate against the live R8 backend and /api/system-test.
7. Only after PASS, backs up the previous desktop shell and cuts over.
8. Creates Desktop + Start Menu shortcuts and uninstall registration.
9. Re-validates and opens Agape in its own Windows window.

WHAT IT DOES NOT CHANGE
- It does not replace app.py, index.html, manifest.json, Document Studio, Work Engine or your database.
- It does not delete your current Agape source or data.
- If desktop cutover fails, it restores the previous desktop install where possible.

NETWORK NOTE
The first install may need internet access to obtain WebView2Loader.dll and, only if absent,
the Microsoft Evergreen WebView2 Runtime. Most Windows 10/11 systems already have the runtime.

EXTERNAL LINKS
Agape's main/local pages stay inside the application window. A deliberate link to a public website
can still open the normal system browser; that is separate from the main Agape application window.

DIAGNOSTIC LOG
  %LOCALAPPDATA%\Programs\Agape\Agape-native.log

If installation fails, copy the ERROR= line back to ChatGPT.
