from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import BUILD, __version__
from .context import StudioContext


class StudioHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, server_address, RequestHandlerClass, context: StudioContext):
        self.context = context
        super().__init__(server_address, RequestHandlerClass)


class Handler(BaseHTTPRequestHandler):
    server: StudioHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _json_body(self) -> dict[str, Any]:
        length = int(self.headers.get('Content-Length', '0') or '0')
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode('utf-8'))

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, exc: Exception, status: int = 400) -> None:
        self._send_json({'ok': False, 'error': str(exc)}, status)

    def do_GET(self) -> None:
        ctx = self.server.context
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path == '/':
                return self._send_file(ctx.config.ui_root / 'index.html', 'text/html; charset=utf-8')
            if path == '/app.js':
                return self._send_file(ctx.config.ui_root / 'app.js', 'application/javascript; charset=utf-8')
            if path == '/styles.css':
                return self._send_file(ctx.config.ui_root / 'styles.css', 'text/css; charset=utf-8')
            if path == '/api/health':
                return self._send_json({
                    'ok': ctx.db.quick_check(),
                    'build': BUILD,
                    'version': __version__,
                    'database': ctx.db.quick_check(),
                    'counts': ctx.db.table_counts(),
                })
            if path == '/api/projects':
                return self._send_json({'ok': True, 'projects': ctx.projects.recent()})
            if path == '/api/extensions':
                return self._send_json({'ok': True, 'extensions': ctx.extensions.discover()})
            if path == '/api/ai/status':
                return self._send_json(ctx.ai.status())
            if path == '/api/ai/free-models':
                task = (query.get('task') or ['general'])[0]
                models = ctx.ai.free_models(task)
                return self._send_json({'ok': True, 'models': models, 'count': len(models)})
            if path == '/api/ai/recommend':
                task = (query.get('task') or ['general'])[0]
                mode = (query.get('mode') or ['auto'])[0]
                return self._send_json({'ok': True, 'recommendation': ctx.ai.recommend(task, mode)})
            if path == '/api/connections/tests':
                limit = int((query.get('limit') or ['100'])[0])
                return self._send_json(ctx.connections.history(limit))
            if path == '/api/quality/status':
                return self._send_json(ctx.db.quality_status())
            if path == '/api/tools/aider/status':
                return self._send_json({'ok': True, 'aider': ctx.aider.status()})
            if path == '/api/tools/runs':
                limit = int((query.get('limit') or ['100'])[0])
                return self._send_json({'ok': True, 'runs': ctx.db.tool_run_history(limit)})
            return self._send_json({'ok': False, 'error': 'NOT_FOUND'}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            return self._error(exc, 500)

    def do_POST(self) -> None:
        ctx = self.server.context
        path = urlparse(self.path).path
        try:
            body = self._json_body()
            if path == '/api/projects/create':
                return self._send_json({'ok': True, 'project': ctx.projects.create(str(body.get('name', '')))})
            if path == '/api/projects/open':
                return self._send_json({'ok': True, 'project': ctx.projects.open(str(body.get('path', '')))})
            if path == '/api/files/list':
                return self._send_json({'ok': True, 'files': ctx.projects.list_files(str(body.get('project_path', '')))})
            if path == '/api/files/read':
                content = ctx.projects.read_file(str(body.get('project_path', '')), str(body.get('path', '')))
                return self._send_json({'ok': True, 'content': content})
            if path == '/api/files/write':
                result = ctx.projects.write_file(str(body.get('project_path', '')), str(body.get('path', '')), str(body.get('content', '')))
                return self._send_json(result)
            if path == '/api/terminal/run':
                result = ctx.terminal.run(str(body.get('project_path', '')), list(body.get('argv') or []), int(body.get('timeout', 30)))
                return self._send_json(result)
            if path == '/api/ai/chat':
                result = ctx.ai.chat(
                    str(body.get('project_path') or '') or None,
                    str(body.get('message', '')),
                    str(body.get('task', 'general')),
                    str(body.get('context', '')),
                    str(body.get('mode', 'auto')),
                )
                return self._send_json(result)
            if path == '/api/connections/test':
                provider = str(body.get('provider', ''))
                generation = bool(body.get('generation', False))
                if provider:
                    result = ctx.connections.test_provider(provider, str(body.get('task', 'general')), generation)
                else:
                    result = ctx.connections.test_all(generation)
                return self._send_json(result)
            if path == '/api/extensions/run':
                result = ctx.extensions.run(str(body.get('extension_id', '')), str(body.get('action', '')), dict(body.get('payload') or {}))
                return self._send_json(result)
            if path == '/api/tools/plan':
                result = ctx.planner.plan(
                    str(body.get('project_path') or '') or None,
                    str(body.get('task', '')),
                    str(body.get('mode', 'auto')),
                )
                return self._send_json(result)
            if path == '/api/tools/aider/run':
                project_path = str(body.get('project_path') or '')
                task = str(body.get('task', ''))
                if not project_path or not task:
                    raise ValueError('PROJECT_AND_TASK_REQUIRED')
                route = ctx.planner.plan(project_path, task, str(body.get('mode', 'auto')))
                if route.get('tool') != 'aider':
                    return self._send_json({'ok': False, 'error': 'AIDER_NOT_RECOMMENDED_OR_READY', 'plan': route}, 409)
                result = ctx.aider.run_task(
                    project_path, task, str(route['provider']), str(route['model']), str(route['tier']), int(body.get('timeout', 300))
                )
                return self._send_json(result, 200 if result.get('ok') else 502)
            return self._send_json({'ok': False, 'error': 'NOT_FOUND'}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            return self._error(exc, 400)


def make_server(context: StudioContext, host: str | None = None, port: int | None = None) -> StudioHTTPServer:
    return StudioHTTPServer((host or context.config.host, context.config.port if port is None else int(port)), Handler, context)
