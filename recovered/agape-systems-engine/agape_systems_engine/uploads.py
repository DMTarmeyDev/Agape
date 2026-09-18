from __future__ import annotations
import hashlib, os, shutil, time, uuid
from pathlib import Path

def _sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

class UploadManager:
    def __init__(self,db,root):
        self.db=db;self.root=Path(root);self.chunks=self.root/'chunks';self.objects=self.root/'objects';self.completed=self.root/'completed'
        for p in (self.chunks,self.objects,self.completed):p.mkdir(parents=True,exist_ok=True)
    def start(self,filename,total_size,chunk_size=4*1024*1024,total_sha256=None):
        uid=uuid.uuid4().hex[:20];now=time.time();d=self.chunks/uid;d.mkdir(parents=True,exist_ok=True)
        with self.db.connect() as c:c.execute('INSERT INTO uploads(upload_id,filename,total_size,chunk_size,total_sha256,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(uid,Path(filename).name,int(total_size),int(chunk_size),total_sha256,'UPLOADING',now,now))
        return {'upload_id':uid,'chunk_size':int(chunk_size)}
    def put_chunk(self,uid,index,data,sha256_expected=None):
        actual=hashlib.sha256(data).hexdigest()
        if sha256_expected and actual.lower()!=sha256_expected.lower():raise ValueError('CHUNK_HASH_MISMATCH')
        d=self.chunks/uid
        if not d.exists():raise KeyError('UPLOAD_NOT_FOUND')
        p=d/f'{int(index):08d}.part';tmp=p.with_suffix('.tmp');tmp.write_bytes(data);os.replace(tmp,p)
        with self.db.connect() as c:c.execute('INSERT OR REPLACE INTO upload_chunks(upload_id,chunk_index,size,sha256,state,path,updated_at) VALUES(?,?,?,?,?,?,?)',(uid,int(index),len(data),actual,'PASS',str(p),time.time()));c.execute('UPDATE uploads SET updated_at=? WHERE upload_id=?',(time.time(),uid))
        return {'index':int(index),'size':len(data),'sha256':actual}
    def status(self,uid):
        with self.db.connect() as c:
            u=c.execute('SELECT * FROM uploads WHERE upload_id=?',(uid,)).fetchone();rows=c.execute('SELECT chunk_index,size,sha256,state FROM upload_chunks WHERE upload_id=? ORDER BY chunk_index',(uid,)).fetchall()
        if not u:raise KeyError('UPLOAD_NOT_FOUND')
        return {'upload':dict(u),'chunks':[dict(x) for x in rows],'received_bytes':sum(int(x['size']) for x in rows)}
    def finalize(self,uid):
        st=self.status(uid);u=st['upload'];rows=st['chunks'];expected_size=int(u['total_size'])
        if st['received_bytes']!=expected_size:raise ValueError(f'UPLOAD_INCOMPLETE:{st["received_bytes"]}/{expected_size}')
        tmp=self.root/f'{uid}.assembling';h=hashlib.sha256()
        with open(tmp,'wb') as out:
            for r in rows:
                p=self.chunks/uid/f'{int(r["chunk_index"]):08d}.part'
                b=p.read_bytes()
                if hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('CHUNK_REVERIFY_FAILED')
                out.write(b);h.update(b)
        full=h.hexdigest();expected=(u.get('total_sha256') or '').lower()
        if expected and full.lower()!=expected:tmp.unlink(missing_ok=True);raise ValueError('FULL_HASH_MISMATCH')
        obj=self.objects/full[:2]/full;obj.parent.mkdir(parents=True,exist_ok=True)
        existed=obj.exists()
        if existed:tmp.unlink(missing_ok=True)
        else:os.replace(tmp,obj)
        dest=self.completed/Path(u['filename']).name
        if dest.exists():
            stem=dest.stem;suf=dest.suffix;i=1
            while dest.exists():dest=self.completed/f'{stem}-{i}{suf}';i+=1
        try:os.link(obj,dest)
        except Exception:shutil.copy2(obj,dest)
        with self.db.connect() as c:c.execute("UPDATE uploads SET state='COMPLETE',object_path=?,updated_at=? WHERE upload_id=?",(str(obj),time.time(),uid))
        shutil.rmtree(self.chunks/uid,ignore_errors=True)
        return {'ok':True,'sha256':full,'object_path':str(obj),'file_path':str(dest),'deduplicated':existed}
