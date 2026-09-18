from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--root',default='.');args=ap.parse_args()
    root=Path(args.root).resolve();manifest=root/'manifest.json'
    payload=json.loads(manifest.read_text(encoding='utf-8'))
    expected=payload.get('files',{})
    bad=[]
    for rel,want in expected.items():
        path=root/rel
        if not path.is_file(): bad.append(f'MISSING:{rel}');continue
        got=hashlib.sha256(path.read_bytes()).hexdigest().upper()
        if got!=str(want).upper(): bad.append(f'HASH:{rel}')
    if int(payload.get('file_count',-1))!=len(expected): bad.append('COUNT_FIELD')
    if bad:
        print('MANIFEST_VERIFY=FAIL')
        for item in bad[:20]:print(item)
        return 1
    print(f'MANIFEST_VERIFY={len(expected)}/{len(expected)} PASS')
    return 0
if __name__=='__main__':raise SystemExit(main())
