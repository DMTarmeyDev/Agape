# V4.6 Safe Runtime Cutover

V4.6 fixes a Windows upgrade race introduced by the visible Mainframe watchdog.

During upgrades, the previous `AGAPE SERVER - KEEP OPEN.cmd` could observe `main.py` being stopped and immediately restart it, re-binding port 8850 before the installer completed cutover. V4.6 adds an explicit runtime stop marker, teaches the visible watchdog to honour that marker, and adds legacy watchdog-parent detection so V4.3-V4.5 runtimes can be stopped safely even though they do not understand the marker.

The installer continues to verify Agape ownership before terminating a listener and never blanket-kills unrelated Python or cmd.exe processes.
