#!/usr/bin/env sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$HERE"
PYTHON=${PYTHON:-python3}
exec "$PYTHON" main.py "$@"
