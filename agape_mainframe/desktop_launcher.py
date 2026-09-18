from __future__ import annotations
import argparse, threading, webbrowser
from .server import serve
from .service_runtime import dispatch_internal_service

def _open(url: str) -> None:
    try:
        webbrowser.open(url, new=1)
    except Exception:
        pass

def main() -> int:
    internal = dispatch_internal_service()
    if internal is not None:
        return int(internal)
    ap = argparse.ArgumentParser(description="Agape desktop launcher")
    ap.add_argument("--port", type=int, default=8850)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    if not args.no_browser:
        threading.Timer(1.0, _open, args=(f"http://127.0.0.1:{args.port}/",)).start()
    serve(args.port)
    return 0
