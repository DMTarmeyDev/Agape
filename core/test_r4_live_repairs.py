from __future__ import annotations
import os, shutil, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))

import test_planner

plan=test_planner.plan_tests(str(ROOT))
assert plan.get('ok') is True, plan
assert plan.get('reason') == 'python_selftest', plan
assert plan.get('command') == 'python SELFTEST.py', plan
assert all(x not in plan.get('command','') for x in ('&&','||',';','|','`','<','>')), plan
print('R4_ROOT_LEVEL_TEST_PLANNER=PASS')

sandbox=Path(tempfile.mkdtemp(prefix='agape-r4-queue-'))
os.environ['DMT_DATA_ROOT']=str(sandbox/'data')
# reload DB after env is set
for name in ['config','db']:
    sys.modules.pop(name,None)
import db
db.init_db(); p=db.create_project('R4 queue test',kind='system',archived=True)
item=db.enqueue_autodev_task(int(p['id']),'proof','python SELFTEST.py',1)
updated=db.update_autodev_queue(int(item['id']),'completed','R4-PROOF')
assert updated.get('status')=='completed',updated
try:
    db.update_autodev_queue(int(item['id']),'complete','R4-BAD')
except ValueError as exc:
    assert str(exc)=='AUTODEV_QUEUE_STATUS_INVALID'
else:
    raise AssertionError('INVALID_QUEUE_STATUS_WAS_ACCEPTED')
print('R4_QUEUE_COMPLETED_CONTRACT=PASS')

import providers
captured={}
def fake_json_request(url, body, timeout):
    captured['body']=dict(body)
    return {'message':{'content':'{"name":"shell","arguments":{"cmd":"Write-Output OK"}}'}}
orig=providers._json_request
providers._json_request=fake_json_request
try:
    reply=providers.ollama_chat('qwen-test',[{'role':'user','content':'proof'}],json_only=True)
    assert captured['body'].get('format')=='json',captured
    assert reply.content.startswith('{'),reply.content
finally:
    providers._json_request=orig
print('R4_SINGLE_TOOL_JSON_MODE=PASS')
shutil.rmtree(sandbox,ignore_errors=True)
