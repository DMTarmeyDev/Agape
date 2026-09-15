from __future__ import annotations
import ast, hashlib, json, re, time
from pathlib import Path

TEXT_EXT={'.py','.ps1','.js','.ts','.html','.css','.json','.md','.txt','.toml','.yaml','.yml','.ini','.cfg','.bat','.cmd','.sql'}
SKIP={'.git','.venv','venv','node_modules','__pycache__','.pytest_cache','dist','build'}

def sha256_bytes(b):return hashlib.sha256(b).hexdigest()

def safe_files(root,max_files=5000):
    root=Path(root).resolve();count=0
    for p in root.rglob('*'):
        if count>=max_files:break
        try:
            if not p.is_file() or p.is_symlink():continue
            rel=p.resolve().relative_to(root)
        except Exception:continue
        if any(x in SKIP for x in rel.parts):continue
        if p.suffix.lower() not in TEXT_EXT:continue
        count+=1;yield p,rel.as_posix()

def _symbols_python(text,path):
    out=[]
    try:tree=ast.parse(text)
    except Exception:return out
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            kind='class' if isinstance(n,ast.ClassDef) else 'function'
            sig=''
            if kind=='function':
                try:sig=n.name+'('+','.join(a.arg for a in n.args.args)+')'
                except Exception:sig=n.name
            else:sig=n.name
            out.append((path,n.name,kind,int(getattr(n,'lineno',1)),int(getattr(n,'end_lineno',getattr(n,'lineno',1))),sig))
    return out

def index_root(db,root,max_files=5000,chunk_lines=80):
    root=Path(root).resolve();now=time.time();indexed=0;skipped=0;changed=0
    with db.connect() as c:
        known={r['path']:dict(r) for r in c.execute('SELECT * FROM code_files').fetchall()}
    seen=set()
    for p,rel in safe_files(root,max_files=max_files):
        seen.add(rel)
        st=p.stat();old=known.get(rel)
        if old and int(old['size'])==st.st_size and int(old['mtime_ns'])==st.st_mtime_ns:
            skipped+=1;continue
        raw=p.read_bytes();h=sha256_bytes(raw);text=raw.decode('utf-8','replace');lang=p.suffix.lower().lstrip('.') or 'text'
        lines=text.splitlines()
        chunks=[]
        for i in range(0,len(lines),chunk_lines):
            body='\n'.join(lines[i:i+chunk_lines])
            if body.strip():chunks.append((rel,i+1,min(len(lines),i+chunk_lines),body))
        symbols=_symbols_python(text,rel) if p.suffix.lower()=='.py' else []
        with db.connect() as c:
            c.execute('BEGIN')
            c.execute('INSERT OR REPLACE INTO code_files(path,size,mtime_ns,sha256,language,updated_at) VALUES(?,?,?,?,?,?)',(rel,st.st_size,st.st_mtime_ns,h,lang,now))
            c.execute('DELETE FROM code_symbols WHERE path=?',(rel,));c.execute('DELETE FROM code_chunks WHERE path=?',(rel,))
            c.executemany('INSERT INTO code_symbols(path,name,kind,line,end_line,signature) VALUES(?,?,?,?,?,?)',symbols)
            c.executemany('INSERT INTO code_chunks(path,line_start,line_end,text) VALUES(?,?,?,?)',chunks)
            c.execute('COMMIT')
        indexed+=1;changed+=1
    deleted=set(known)-seen
    if deleted:
        with db.connect() as c:
            for rel in deleted:
                c.execute('DELETE FROM code_files WHERE path=?',(rel,));c.execute('DELETE FROM code_symbols WHERE path=?',(rel,));c.execute('DELETE FROM code_chunks WHERE path=?',(rel,))
    return {'ok':True,'root':str(root),'indexed':indexed,'unchanged':skipped,'deleted':len(deleted),'changed':changed}

def _tokens(q):return [x.lower() for x in re.findall(r'[A-Za-z_][A-Za-z0-9_./-]{1,}',q or '')][:20]

def search(db,query,limit=20):
    toks=_tokens(query);rows=[]
    if not toks:return []
    with db.connect() as c:
        syms=c.execute('SELECT path,name,kind,line,end_line,signature FROM code_symbols').fetchall()
        chunks=c.execute('SELECT path,line_start,line_end,text FROM code_chunks').fetchall()
    for r in syms:
        hay=(r['name']+' '+r['path']+' '+(r['signature'] or '')).lower();score=sum(8 for t in toks if t in hay)
        if score:rows.append({'type':'symbol','score':score,**dict(r)})
    for r in chunks:
        hay=(r['path']+' '+r['text']).lower();score=sum(1 for t in toks if t in hay)
        exact=sum(3 for t in toks if re.search(r'\b'+re.escape(t)+r'\b',hay))
        score+=exact
        if score:rows.append({'type':'chunk','score':score,'path':r['path'],'line_start':r['line_start'],'line_end':r['line_end'],'text':r['text'][:8000]})
    rows.sort(key=lambda x:(-x['score'],x['path'],x.get('line_start',x.get('line',0))))
    return rows[:limit]

def context_pack(db,query,max_chars=12000,limit=30):
    hits=search(db,query,limit);parts=[];used=0
    for h in hits:
        if h['type']=='symbol':
            s=f"SYMBOL {h['kind']} {h['name']} @ {h['path']}:{h['line']}-{h.get('end_line')} signature={h.get('signature','')}"
        else:
            s=f"FILE {h['path']}:{h['line_start']}-{h['line_end']}\n{h['text']}"
        if used+len(s)>max_chars:continue
        parts.append(s);used+=len(s)+2
    return {'query':query,'chars':used,'hits':len(parts),'text':'\n\n'.join(parts),'sources':[{'path':h['path'],'type':h['type'],'score':h['score']} for h in hits[:len(parts)]]}
