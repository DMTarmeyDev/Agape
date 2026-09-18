from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from .api import make_server
from .config import StudioConfig
from .context import build_context


def main() -> int:
    parser = argparse.ArgumentParser(description='Agape AI Studio V0.2')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8797)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config = StudioConfig.default(root)
    server = make_server(build_context(config), args.host, args.port)
    url = f'http://{args.host}:{server.server_address[1]}/'
    print('AGAPE_AI_STUDIO=STARTING')
    print('URL=' + url)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
