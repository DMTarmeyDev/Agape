from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agape_studio.database import StudioDatabase


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--data-root',required=True)
    ap.add_argument('--quality-json',required=True)
    ap.add_argument('--report-path',default='')
    args=ap.parse_args()
    payload=json.loads(Path(args.quality_json).read_text(encoding='utf-8'))
    if payload.get('overall')!='PASS':
        raise SystemExit('QUALITY_REPORT_NOT_PASS')
    db=StudioDatabase(Path(args.data_root)/'agape_studio.sqlite3')
    for item in payload.get('items',[]):
        db.set_quality_item(item['id'],item['area'],item['title'],item['status'],item.get('detail',''),args.report_path)
    status=db.quality_status()
    print(f"QUALITY_PUBLISHED={status['passed_count']}/{status['total']} PASS")
    return 0

if __name__=='__main__':
    raise SystemExit(main())
