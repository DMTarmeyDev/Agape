from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def catalog_payload() -> dict[str, Any]:
    return {
        'data': [
            {
                'id': 'acme/general-free',
                'name': 'General Free',
                'context_length': 65536,
                'pricing': {'prompt': '0', 'completion': '0', 'request': '0'},
                'architecture': {'output_modalities': ['text']},
                'supported_parameters': ['response_format'],
            },
            {
                'id': 'acme/coder-free',
                'name': 'Coder Free',
                'context_length': 131072,
                'pricing': {'prompt': '0.0', 'completion': '0.000', 'request': None},
                'architecture': {'output_modalities': ['text']},
                'supported_parameters': ['tools', 'structured_outputs'],
            },
            {
                'id': 'acme/paid-model',
                'name': 'Paid Model',
                'context_length': 999999,
                'pricing': {'prompt': '1.0', 'completion': '2.0', 'request': '0'},
                'architecture': {'output_modalities': ['text']},
                'supported_parameters': ['tools'],
            },
            {
                'id': 'acme/free-image-only',
                'name': 'Image Only',
                'context_length': 8192,
                'pricing': {'prompt': '0', 'completion': '0', 'request': '0'},
                'architecture': {'output_modalities': ['image']},
                'supported_parameters': [],
            },
        ]
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send(self, payload, status=200):
        data=json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers();self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith('/api/v1/models'):
            return self._send(catalog_payload())
        return self._send({'error':'not found'},404)

    def do_POST(self):
        length=int(self.headers.get('Content-Length','0') or 0)
        body=json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
        if self.path == '/api/v1/chat/completions':
            if self.headers.get('Authorization') != 'Bearer test-key':
                return self._send({'error':'missing auth'},401)
            model=str(body.get('model') or '')
            if model == 'acme/paid-model':
                return self._send({'error':'paid blocked by fake server'},400)
            return self._send({'choices':[{'message':{'role':'assistant','content':'FREE_PROVIDER_PASS'}}]})
        return self._send({'error':'not found'},404)


@contextmanager
def fake_openrouter():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True
    server.block_on_close=False
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_address[1]}/api/v1'
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
