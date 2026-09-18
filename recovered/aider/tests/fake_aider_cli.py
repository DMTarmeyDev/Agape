from __future__ import annotations

import os
import sys
from pathlib import Path


def arg_value(name: str) -> str:
    try:
        i = sys.argv.index(name)
        return sys.argv[i + 1]
    except (ValueError, IndexError):
        return ''


if '--version' in sys.argv:
    print('aider 0.86.0-test')
    raise SystemExit(0)

if os.environ.get('AGAPE_FAKE_AIDER_FAIL') == '1':
    print('fake aider forced failure', file=sys.stderr)
    raise SystemExit(7)

message = arg_value('--message')
model = arg_value('--model')
if not message or not model:
    print('missing message/model', file=sys.stderr)
    raise SystemExit(2)

root = Path.cwd()
target = root / 'aider_target.py'
old = target.read_text(encoding='utf-8') if target.exists() else ''
if '# AIDER_EDIT_PASS' not in old:
    target.write_text(old.rstrip() + '\n# AIDER_EDIT_PASS\n', encoding='utf-8')
print('AIDER_FAKE=PASS')
print('MODEL=' + model)
print('TASK_BYTES=' + str(len(message.encode('utf-8'))))
raise SystemExit(0)
