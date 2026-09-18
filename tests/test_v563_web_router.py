from __future__ import annotations
import threading, urllib.request, urllib.error
from pathlib import Path
from agape_mainframe.server import Handler, ThreadingHTTPServer, WEB_REVISION

ROOT=Path(__file__).resolve().parents[1]

def _get(base,path):
    try:
        with urllib.request.urlopen(base+path, timeout=4) as r:
            return r.status, r.headers.get("Content-Type",""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type",""), e.read()

def test_web_revision_marker_and_launcher_guard_present():
    server=(ROOT/"agape_mainframe"/"server.py").read_text(encoding="utf-8")
    launcher=(ROOT/"START-AGAPE-LATEST.ps1").read_text(encoding="utf-8")
    assert WEB_REVISION == "R2.4.4-TEMPLATES-SESSION"
    assert "project_templates.js" in launcher
    assert "$listenerPid" in launcher
    assert "$pid=" not in launcher.lower()

def test_root_and_all_bundled_web_assets_are_served():
    srv=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    thread=threading.Thread(target=srv.serve_forever,daemon=True); thread.start()
    base=f"http://127.0.0.1:{srv.server_port}"
    try:
        for path in ["/","/index.html","/app.js","/styles.css","/project_templates.js"]:
            status,ctype,body=_get(base,path)
            assert status==200,(path,status,body[:200])
            assert body
        status,ctype,body=_get(base,"/settings")
        assert status==200 and b"Agape" in body
        status,ctype,body=_get(base,"/api/definitely-not-a-route")
        assert status==404 and b"NOT_FOUND" in body
    finally:
        srv.shutdown();srv.server_close();thread.join(timeout=3)
