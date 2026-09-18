from __future__ import annotations
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SKIP_DIRS={'.git','.pytest_cache','__pycache__','build','dist','.venv','venv'}
SKIP_FILES={'API-KEYS.local.json','api-keys.json'}
TEXT_EXTS={'.py','.js','.html','.css','.json','.md','.txt','.toml','.yml','.yaml','.ps1','.cmd','.sh','.ini','.cfg','.env','.example'}
PATTERNS={
    'private_key': re.compile(r'BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY'),
    'github_token': re.compile(r'\bgh[pousr]_[A-Za-z0-9_]{20,}\b'),
    'aws_access_key': re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    'google_api_key': re.compile(r'\bAIza[0-9A-Za-z_-]{20,}\b'),
    'personal_windows_path': re.compile(r'C:\\Users\\(?!Example\\|test\\|Public\\)[^\\\s"\']+\\',re.I),
}

def files():
    for p in ROOT.rglob('*'):
        if not p.is_file() or p.name in SKIP_FILES: continue
        if any(x in SKIP_DIRS for x in p.parts): continue
        if p.suffix.lower() not in TEXT_EXTS and p.name not in {'.gitignore','LICENSE'}: continue
        yield p

def main():
    findings=[]
    for p in files():
        try: text=p.read_text(encoding='utf-8',errors='ignore')
        except Exception: continue
        for name,pattern in PATTERNS.items():
            for m in pattern.finditer(text):
                line=text.count('\n',0,m.start())+1
                findings.append((str(p.relative_to(ROOT)),line,name))
    forbidden=[]
    for p in ROOT.rglob('*'):
        if not p.is_file(): continue
        if any(x in SKIP_DIRS for x in p.parts): continue
        if p.suffix.lower() in {'.sqlite3','.db','.pyc','.p12','.pfx'}:
            forbidden.append(str(p.relative_to(ROOT)))
    if findings or forbidden:
        for row in findings: print('PUBLIC_AUDIT_FINDING',*row,sep=' | ')
        for row in forbidden: print('PUBLIC_AUDIT_FORBIDDEN_FILE | '+row)
        raise SystemExit(2)
    print('PUBLIC_AUDIT=PASS')

if __name__=='__main__': main()
