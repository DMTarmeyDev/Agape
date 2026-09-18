from __future__ import annotations
import json,sys,traceback,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests import live_cases

def main()->int:
    if len(sys.argv)!=2:
        print('RESULT_JSON='+json.dumps({'status':'FAIL','detail':'CASE_NAME_REQUIRED'}));return 2
    name=sys.argv[1]
    try:
        outcome=live_cases.CASES[name]()
        if isinstance(outcome,tuple):status,detail=outcome
        else:status,detail='PASS',str(outcome)
        print('RESULT_JSON='+json.dumps({'status':status,'detail':detail},ensure_ascii=False))
        return 0 if status in ('PASS','SKIP') else 1
    except Exception:
        print('RESULT_JSON='+json.dumps({'status':'FAIL','detail':traceback.format_exc()},ensure_ascii=False))
        return 1
if __name__=='__main__':
    rc=main();sys.stdout.flush();sys.stderr.flush();os._exit(rc)
