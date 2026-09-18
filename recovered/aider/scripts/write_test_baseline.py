from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'test-state'/'baseline-hashes.json'
EXCLUDE={'test-reports','test-state','__pycache__'}
rows={}
for path in sorted(ROOT.rglob('*')):
    if not path.is_file(): continue
    rel=path.relative_to(ROOT).as_posix()
    if any(part in EXCLUDE for part in path.relative_to(ROOT).parts): continue
    if rel in {'manifest.json'}: continue
    rows[rel]=hashlib.sha256(path.read_bytes()).hexdigest()
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps({'build':'AGAPE-AI-STUDIO-V0.3-AIDER-R2','files':rows},indent=2),encoding='utf-8')
print(f'BASELINE_HASHES={len(rows)}')
print('BASELINE=' + str(OUT))
