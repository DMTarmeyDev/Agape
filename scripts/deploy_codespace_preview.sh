#!/usr/bin/env bash
set -euo pipefail
BRANCH="${1:-${AGAPE_BRANCH:-main}}"
ROOT="${CODESPACE_VSCODE_FOLDER:-$(pwd)}"
PORT="${AGAPE_PORT:-8850}"
cd "$ROOT"
printf '[INFO] CODESPACE_ROOT=%s\n' "$ROOT"
printf '[INFO] BRANCH=%s\n' "$BRANCH"
git fetch origin "$BRANCH"
git switch "$BRANCH" 2>/dev/null || git switch -c "$BRANCH" --track "origin/$BRANCH"
git reset --hard "origin/$BRANCH"
python -m pip install -q -r requirements-runtime.txt
python -m compileall -q agape_mainframe main.py SETUP-API-KEYS.py
export AGAPE_MAINFRAME_DATA="${AGAPE_MAINFRAME_DATA:-$HOME/.agape-codespace-data}"
export AGAPE_SECURITY_ROOT="${AGAPE_SECURITY_ROOT:-$HOME/.agape-codespace-security}"
mkdir -p "$AGAPE_MAINFRAME_DATA" "$AGAPE_SECURITY_ROOT" "$HOME/.agape-run"
PIDFILE="$HOME/.agape-run/mainframe.pid"
if [[ -f "$PIDFILE" ]]; then
  old="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ "$old" =~ ^[0-9]+$ ]]; then kill "$old" 2>/dev/null || true; fi
fi
nohup python main.py --no-browser --port "$PORT" >"$HOME/.agape-run/mainframe.log" 2>&1 &
echo $! > "$PIDFILE"
for i in $(seq 1 60); do
  if python - "$PORT" <<'HEALTHPY'
import sys, urllib.request
port=sys.argv[1]
try:
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=2) as r:
        raise SystemExit(0 if r.status==200 else 1)
except Exception:
    raise SystemExit(1)
HEALTHPY
  then
    echo "CODESPACE_AGAPE=PASS"
    echo "CODESPACE_LOCAL=http://127.0.0.1:${PORT}/"
    exit 0
  fi
  sleep 1
done
echo "CODESPACE_AGAPE=FAIL"
tail -80 "$HOME/.agape-run/mainframe.log" || true
exit 1
