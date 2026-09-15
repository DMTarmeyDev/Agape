from __future__ import annotations
import json, os, socket, subprocess, time
from pathlib import Path


def tcp_check(host, port, timeout=0.5):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True, ''
    except Exception as e:
        return False, str(e)


class Supervisor:
    def __init__(self, db):
        self.db = db

    def register(self, name, host, port, expected_state='COLD', start_cmd=None):
        with self.db.connect() as c:
            c.execute(
                'INSERT OR REPLACE INTO services(name,host,port,expected_state,start_cmd_json,last_state,last_checked_at,last_error) VALUES(?,?,?,?,?,?,?,?)',
                (name, host, int(port), expected_state, json.dumps(start_cmd) if start_cmd else None, None, None, None),
            )

    def _spawn(self, spec):
        if isinstance(spec, list):
            return subprocess.Popen(spec, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not isinstance(spec, dict):
            raise RuntimeError('INVALID_START_SPEC')
        cmd = list(spec.get('cmd') or [])
        if not cmd:
            raise RuntimeError('EMPTY_START_COMMAND')
        cwd = spec.get('cwd') or None
        env = os.environ.copy()
        for k, v in (spec.get('env') or {}).items():
            env[str(k)] = str(v)
        stdout = subprocess.DEVNULL
        stderr = subprocess.DEVNULL
        out_handle = err_handle = None
        try:
            if spec.get('stdout_path'):
                p = Path(spec['stdout_path']); p.parent.mkdir(parents=True, exist_ok=True)
                out_handle = open(p, 'a', encoding='utf-8')
                stdout = out_handle
            if spec.get('stderr_path'):
                p = Path(spec['stderr_path']); p.parent.mkdir(parents=True, exist_ok=True)
                err_handle = open(p, 'a', encoding='utf-8')
                stderr = err_handle
            return subprocess.Popen(cmd, cwd=cwd, env=env, stdout=stdout, stderr=stderr)
        finally:
            if out_handle: out_handle.close()
            if err_handle: err_handle.close()

    def check(self, name, recover=False):
        with self.db.connect() as c:
            r = c.execute('SELECT * FROM services WHERE name=?', (name,)).fetchone()
        if not r:
            raise KeyError(name)
        d = dict(r)
        up, err = tcp_check(d['host'], d['port'])
        expected = d['expected_state']
        state = 'ACTIVE' if up else ('COLD' if expected in ('COLD', 'DISABLED') else 'DOWN')
        recovered = False
        recovery_attempted = False
        recovery_error = ''
        if recover and state == 'DOWN':
            if not d.get('start_cmd_json'):
                recovery_error = 'NO_SAFE_START_COMMAND'
            else:
                recovery_attempted = True
                try:
                    spec = json.loads(d['start_cmd_json'])
                    proc = self._spawn(spec)
                    deadline = time.time() + 45.0
                    while time.time() < deadline:
                        up, err = tcp_check(d['host'], d['port'], 0.5)
                        if up:
                            state = 'ACTIVE'; recovered = True; break
                        if proc.poll() is not None:
                            recovery_error = f'PROCESS_EXITED={proc.returncode}'
                            break
                        time.sleep(0.25)
                    if not recovered and not recovery_error:
                        recovery_error = 'RECOVERY_TIMEOUT'
                except Exception as e:
                    recovery_error = str(e)
                if recovery_error:
                    err = recovery_error
        healthy = (state == 'ACTIVE') if expected == 'ACTIVE' else state in ('ACTIVE', 'COLD')
        with self.db.connect() as c:
            c.execute(
                'UPDATE services SET last_state=?,last_checked_at=?,last_error=? WHERE name=?',
                (state, time.time(), str(err or '')[:1000], name),
            )
        return {
            'name': name, 'expected': expected, 'state': state, 'healthy': healthy,
            'recovered': recovered, 'recovery_attempted': recovery_attempted,
            'error': str(err or ''),
        }

    def check_all(self, recover=False):
        with self.db.connect() as c:
            names = [x['name'] for x in c.execute('SELECT name FROM services ORDER BY name').fetchall()]
        return [self.check(x, recover=recover) for x in names]

    def summary(self, recover=False):
        rows = self.check_all(recover=recover)
        required_unhealthy = [r['name'] for r in rows if r['expected'] == 'ACTIVE' and not r['healthy']]
        return {'ok': not required_unhealthy, 'required_unhealthy': required_unhealthy, 'services': rows}
