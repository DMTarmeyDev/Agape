from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _wait_port_free(port: int) -> None:
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"QA_PORT_IN_USE:{port}: {exc}") from exc


def _make_docx(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''
    rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''
    safe = text.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    document = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{safe}</w:t></w:r></w:p><w:sectPr/></w:body></w:document>'''
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/document.xml', document)


def _make_pdf(path: Path, text: str) -> None:
    stream = f"BT /F1 12 Tf 72 720 Td ({text.replace('(', '[').replace(')', ']')}) Tj ET".encode('latin-1', errors='replace')
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n"); offsets=[0]
    for i,obj in enumerate(objs,1):
        offsets.append(len(out)); out.extend(f"{i} 0 obj\n".encode()); out.extend(obj); out.extend(b"\nendobj\n")
    xref=len(out); out.extend(f"xref\n0 {len(objs)+1}\n".encode()); out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]: out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()); path.write_bytes(out)


FIELDS = [
    'organisation_proposer','recipient_decision_maker','industry_sector','market_geography','product_service','problem_need',
    'document_purpose','decision_action_requested','target_audience','value_proposition','budget_pricing_commercial_terms',
    'timeline_target_date','success_measures','competitors_alternatives','constraints','tone','research_focus'
]


def base_intake() -> dict[str, Any]:
    values = {
        'organisation_proposer':'Northstar Workplace Ltd','recipient_decision_maker':'None',
        'industry_sector':'Commercial interiors and flooring','market_geography':'North West England',
        'product_service':'Commercial flooring installation and workspace refurbishment',
        'problem_need':'Customers need reliable fit-out delivery with clearer programme and cost control.',
        'document_purpose':'Bank-ready expansion business plan','decision_action_requested':'Approve growth funding',
        'target_audience':'Bank lending team and directors','value_proposition':'Single accountable contractor for flooring and workplace delivery',
        'budget_pricing_commercial_terms':'£185,000 investment budget','timeline_target_date':'Launch expansion programme by March 2027',
        'success_measures':'20% revenue growth, 90% on-time projects, positive operating cash flow',
        'competitors_alternatives':'None','constraints':'Do not invent signed contracts; preserve supplied prices and dates.',
        'tone':'Professional, evidence-led and concise','research_focus':'None',
    }
    fields={}
    for key in FIELDS:
        value=values[key]
        reason='Recipient must come from the user' if key=='recipient_decision_maker' else ('Needs public research' if value=='None' else 'Source document')
        fields[key]={'value':value,'status':'unresolved' if value=='None' else 'supplied','reason':reason}
    return {
        'id':'QA-INTAKE-1','project_id':0,'field_count':17,'established_count':14,'ai_fill':{'fields':fields},
        'unresolved_questions':[
            {'field_id':'recipient_decision_maker','question':'Who is the intended decision-maker?','researchable':False},
            {'field_id':'competitors_alternatives','question':'Which alternatives should be compared?','researchable':True},
            {'field_id':'research_focus','question':'Which public evidence should be researched?','researchable':True},
        ],
        'extra_information_opportunities':[
            {'field_id':'competitors_alternatives','label':'Competitors / alternatives','question':'Find current competitors.','reason':'Public competitor evidence could strengthen the project.','researchable':True},
            {'field_id':'research_focus','label':'Additional useful public information','question':'Find current market and industry evidence.','reason':'Current public evidence could strengthen the project.','researchable':True},
        ],
        'upload':{'writing_check':{'ok':True,'safe_corrections_applied':2,'spelling_issue_count':2,'grammar_issue_count':2,'structured_lines_skipped':1,'dictionary_available':True,'spelling_suggestions':[{'word':'buget','suggestion':'budget'}],'grammar_suggestions':[{'text':'we was planning growth','suggestion':'Consider: we were planning growth'}]}},
    }


def improved_intake(row: dict[str, Any]) -> dict[str, Any]:
    out=json.loads(json.dumps(row))
    out['ai_fill']['fields']['competitors_alternatives']={'value':'Local fit-out contractors, direct flooring specialists and in-house procurement','status':'researched','reason':'Public research QA result'}
    out['ai_fill']['fields']['research_focus']={'value':'Current UK commercial interiors demand, lending context and competitor positioning','status':'researched','reason':'Public research QA result'}
    questions=[]
    recipient=out['ai_fill']['fields'].get('recipient_decision_maker',{})
    if str(recipient.get('value') or '').strip().lower() in {'','none'}:
        questions.append({'field_id':'recipient_decision_maker','question':'Who is the intended decision-maker?','researchable':False})
    out['unresolved_questions']=questions
    out['extra_information_opportunities']=[]
    out['established_count']=17-len(questions)
    return out


def revised_intake(row: dict[str, Any]) -> dict[str, Any]:
    out=json.loads(json.dumps(row)); out['ai_fill']['fields']['tone']={'value':'Formal bank lending tone','status':'revised','reason':'Applied from AI brief-change instruction'}; return out


class FakeWorkflow(BaseHTTPRequestHandler):
    intake: dict[str, Any] = {}
    job_polls=0; downloads: dict[int,int]={}; files:list[Path]=[]
    def log_message(self,*args): return
    def send_json(self,status,payload):
        raw=json.dumps(payload).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def body(self):
        n=int(self.headers.get('Content-Length','0') or 0); return json.loads(self.rfile.read(n) or b'{}')
    def do_GET(self):
        u=urllib.parse.urlparse(self.path)
        if u.path=='/api/health': return self.send_json(200,{'ok':True,'build':'AGAPE-UNIFIED-R4.7-TARGETED-VALIDATION-REPAIR'})
        if u.path.startswith('/api/intakes/'): return self.send_json(200,{'ok':True,'intake':self.__class__.intake})
        if u.path.startswith('/api/jobs/') and u.path.endswith('/download'):
            q=urllib.parse.parse_qs(u.query); idx=int((q.get('index') or ['0'])[0]); self.__class__.downloads[idx]=self.__class__.downloads.get(idx,0)+1
            if idx==1 and self.__class__.downloads[idx]==1: return self.send_json(503,{'error':'QA_FORCED_FIRST_DOWNLOAD_FAILURE'})
            if idx<0 or idx>=len(self.__class__.files): return self.send_json(404,{'error':'RESULT_FILE_NOT_FOUND'})
            target=self.__class__.files[idx]; raw=target.read_bytes(); ctype='application/pdf' if target.suffix.lower()=='.pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            self.send_response(200); self.send_header('Content-Type',ctype); self.send_header('Content-Disposition',f'attachment; filename="{target.name}"'); self.send_header('Content-Length',str(len(raw))); self.end_headers()
            for pos in range(0,len(raw),1024): self.wfile.write(raw[pos:pos+1024]); self.wfile.flush(); time.sleep(.005)
            return
        if u.path.startswith('/api/jobs/'):
            self.__class__.job_polls+=1; n=self.__class__.job_polls
            stages=[('RUNNING',18,'Reading project brief','Reading project brief'),('RUNNING',34,'Planning document structure','Planning document structure'),('RUNNING',55,'AI drafting','Starting AI draft'),('RUNNING',78,'Validating','Validating Findings and Analysis'),('RUNNING',94,'Creating PDF','Creating PDF copy')]
            if n<=len(stages):
                status,progress,stage,message=stages[n-1]; return self.send_json(200,{'ok':True,'job':{'id':'QA-JOB-1','status':status,'progress':progress,'stage':stage,'message':message}})
            files=[{'ok':True,'file':str(p),'name':p.name} for p in self.__class__.files]; return self.send_json(200,{'ok':True,'job':{'id':'QA-JOB-1','status':'PASS','progress':100,'stage':'Document ready','message':'Document ready','result':{'ok':True,'files':files}}})
        return self.send_json(404,{'error':'NOT_FOUND'})
    def do_POST(self):
        u=urllib.parse.urlparse(self.path)
        if u.path=='/api/document/intake':
            payload=self.body(); assert payload.get('data_base64'); self.__class__.intake=base_intake(); return self.send_json(200,{'ok':True,'intake':self.__class__.intake})
        if u.path.endswith('/answers') and u.path.startswith('/api/intakes/'):
            payload=self.body(); answers=payload.get('answers') or {}
            for key,value in answers.items():
                if key in self.__class__.intake.get('ai_fill',{}).get('fields',{}): self.__class__.intake['ai_fill']['fields'][key]={'value':str(value),'status':'user','reason':'User supplied during QA'}
            return self.send_json(200,{'ok':True,'intake':self.__class__.intake})
        if u.path.endswith('/improve') and u.path.startswith('/api/intakes/'):
            time.sleep(1.4); self.__class__.intake=improved_intake(self.__class__.intake); return self.send_json(200,{'ok':True,'intake':self.__class__.intake})
        if u.path.endswith('/revise') and u.path.startswith('/api/intakes/'):
            payload=self.body(); assert payload.get('instruction'); self.__class__.intake=revised_intake(self.__class__.intake); return self.send_json(200,{'ok':True,'intake':self.__class__.intake})
        if u.path=='/api/jobs':
            payload=self.body(); assert payload.get('intake_id')=='QA-INTAKE-1'; self.__class__.job_polls=0; return self.send_json(202,{'ok':True,'job_id':'QA-JOB-1','job':{'id':'QA-JOB-1','status':'QUEUED'}})
        if u.path=='/api/open-result-folder':
            payload=self.body(); idx=int(payload.get('index') or 0); return self.send_json(200,{'ok':True,'simulated':True,'folder':str(self.__class__.files[idx].parent)})
        return self.send_json(404,{'error':'NOT_FOUND'})


class FakeDocumentStudio(BaseHTTPRequestHandler):
    def log_message(self,*args): return
    def do_GET(self):
        if self.path.startswith('/api/health'):
            raw=json.dumps({'ok':True,'version':'R31.16'}).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw); return
        self.send_error(404)


def _start(handler,port):
    srv=ThreadingHTTPServer(('127.0.0.1',port),handler); threading.Thread(target=srv.serve_forever,daemon=True).start(); return srv


def _http(method,url,payload=None,timeout=20):
    data=None if payload is None else json.dumps(payload).encode(); headers={'Content-Type':'application/json'} if data is not None else {}
    req=urllib.request.Request(url,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r: return int(r.status),r.read(),dict(r.headers)
    except urllib.error.HTTPError as exc: return int(exc.code),exc.read(),dict(exc.headers)


def _http_json(method,url,payload=None,timeout=20):
    status,raw,headers=_http(method,url,payload,timeout); return status,json.loads(raw.decode() or '{}'),headers


def _validate_docx(path:Path):
    if path.stat().st_size<=0 or not zipfile.is_zipfile(path): raise AssertionError(f'DOCX_INVALID:{path}')
    with zipfile.ZipFile(path) as z:
        xml=z.read('word/document.xml').decode()
        if 'Agape full dummy QA result' not in xml: raise AssertionError('DOCX_CONTENT_MISSING')


def _validate_pdf(path:Path):
    raw=path.read_bytes()
    if len(raw)<100 or not raw.startswith(b'%PDF-') or b'%%EOF' not in raw: raise AssertionError(f'PDF_INVALID:{path}')


def _record(report,name,fn,group):
    started=time.perf_counter()
    try:
        detail=fn(); report['steps'].append({'group':group,'name':name,'status':'PASS','ms':round((time.perf_counter()-started)*1000),'detail':str(detail or '')}); return detail
    except Exception as exc:
        report['steps'].append({'group':group,'name':name,'status':'FAIL','ms':round((time.perf_counter()-started)*1000),'detail':f'{type(exc).__name__}: {exc}'}); raise


def run(output_root:Path|None=None)->dict[str,Any]:
    work=output_root or Path(tempfile.mkdtemp(prefix='agape-v55-full-qa-')); work.mkdir(parents=True,exist_ok=True)
    data=work/'mainframe-data'; security=work/'security'; downloads=work/'downloads'; generated=work/'generated'
    for d in (data,security,downloads,generated): d.mkdir(parents=True,exist_ok=True)
    os.environ.update({'AGAPE_MAINFRAME_DATA':str(data),'AGAPE_SECURITY_ROOT':str(security),'AGAPE_CORE_DB':str(work/'isolated-core.sqlite3'),'AGAPE_QA_NO_EXTERNAL_OPEN':'1'})
    source=work/'QA-UPLOAD-WITH-ERRORS.docx'; _make_docx(source,'Northstar Workplace Ltd buget is £185,000. we was planning growth and dont want private facts invented.')
    result_docx=generated/'Northstar-QA-Business-Plan.docx'; result_pdf=generated/'Northstar-QA-Business-Plan.pdf'; _make_docx(result_docx,'Agape full dummy QA result - validated document.'); _make_pdf(result_pdf,'Agape full dummy QA result')
    FakeWorkflow.files=[result_docx,result_pdf]; FakeWorkflow.downloads={}; FakeWorkflow.job_polls=0; FakeWorkflow.intake=base_intake()
    report={'status':'FAIL','steps':[],'work':str(work),'browser_mode':'intercepted-dummy','backend_mode':'real-mainframe-http-to-8852'}
    _wait_port_free(8851); _wait_port_free(8852); doc_srv=_start(FakeDocumentStudio,8851); flow_srv=_start(FakeWorkflow,8852); main_srv=None
    try:
        import sys
        if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
        from agape_mainframe import server,state
        state.save_settings({'setup_complete':True,'experience':'standard','quality':'standard'})
        main_srv=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler); threading.Thread(target=main_srv.serve_forever,daemon=True).start(); base=f'http://127.0.0.1:{main_srv.server_port}'

        # Backend integration: real Mainframe HTTP -> fake current bridge on 8852.
        def backend_flow():
            status,h,_=_http_json('GET',base+'/api/health'); assert status==200 and h.get('ok')
            payload={'prepare_request_id':'QA-BACKEND-1','source_mode':'upload','file_name':source.name,'file_data_base64':base64.b64encode(source.read_bytes()).decode(),'project_id':0,'instruction':'Create a bank-ready expansion business plan.','also_pdf':True}
            status,started,_=_http_json('POST',base+'/api/intake/start',payload); assert status==202 and started.get('prepare_job_id'); jid=started['prepare_job_id']
            deadline=time.time()+15; prepared=None
            while time.time()<deadline:
                _,prepared,_=_http_json('GET',base+'/api/intake-prepare/'+urllib.parse.quote(jid));
                if str(prepared.get('status','')).upper()=='COMPLETE': break
                if str(prepared.get('status','')).upper() in {'FAIL','FAILED','ERROR'}: raise AssertionError(prepared)
                time.sleep(.1)
            intake=(prepared.get('result') or {}).get('intake') or (prepared.get('result') or {}); assert intake.get('id')=='QA-INTAKE-1'
            _http_json('POST',base+'/api/intake/QA-INTAKE-1/answers',{'answers':{'recipient_decision_maker':'Regional lending committee','research_focus':'Research UK demand and competitor positioning.'}})
            st,improved,_=_http_json('POST',base+'/api/intake/QA-INTAKE-1/improve',{}); assert st==200 and (improved.get('intake') or improved)['established_count']==17
            st,revised,_=_http_json('POST',base+'/api/intake/QA-INTAKE-1/revise',{'instruction':'Use a formal bank lending tone.'}); assert st==200 and 'bank lending' in (revised.get('intake') or revised)['ai_fill']['fields']['tone']['value'].lower()
            st,run,_=_http_json('POST',base+'/api/run',{'task':'Create a bank-ready expansion business plan.','intake_id':'QA-INTAKE-1','file_name':'prepared-intake.txt','quality':'standard','also_pdf':True}); assert st==202 and run.get('job_id')=='QA-JOB-1'
            deadline=time.time()+15; job=None
            while time.time()<deadline:
                _,wrap,_=_http_json('GET',base+'/api/work/QA-JOB-1'); job=wrap.get('job') or wrap
                if str(job.get('status','')).upper()=='PASS': break
                time.sleep(.1)
            assert job and job.get('status')=='PASS'
            st,raw,headers=_http('GET',base+'/api/work/QA-JOB-1/download?index=0'); assert st==200 and raw==result_docx.read_bytes() and 'Northstar-QA-Business-Plan.docx' in headers.get('Content-Disposition','')
            (downloads/('backend-'+result_docx.name)).write_bytes(raw)
            st,raw,_=_http('GET',base+'/api/work/QA-JOB-1/download?index=1'); assert st==503 and b'QA_FORCED_FIRST_DOWNLOAD_FAILURE' in raw
            st,raw,headers=_http('GET',base+'/api/work/QA-JOB-1/download?index=1'); assert st==200 and raw==result_pdf.read_bytes() and 'Northstar-QA-Business-Plan.pdf' in headers.get('Content-Disposition','')
            (downloads/('backend-'+result_pdf.name)).write_bytes(raw)
            st,opened,_=_http_json('POST',base+'/api/work/QA-JOB-1/open-folder?index=0',{}); assert st==200 and opened.get('simulated') is True
            return 'source -> research -> brief change -> create -> DOCX/PDF proxy -> retry -> open folder'
        _record(report,'real_mainframe_complete_workflow',backend_flow,'backend')
        _record(report,'validate_backend_docx',lambda:_validate_docx(downloads/('backend-'+result_docx.name)) or 'valid DOCX','backend')
        _record(report,'validate_backend_pdf',lambda:_validate_pdf(downloads/('backend-'+result_pdf.name)) or 'valid PDF','backend')

        # Browser UI click-through with dummy responses intercepted before network.
        FakeWorkflow.downloads={}; FakeWorkflow.job_polls=0; browser_intake=base_intake(); browser_job_polls={'n':0}; browser_downloads={0:0,1:0}; prep_polls={'n':0}
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            executable=shutil.which('chromium') or None; browser=p.chromium.launch(headless=True,executable_path=executable); ctx=browser.new_context(accept_downloads=True,viewport={'width':1440,'height':1000}); page=ctx.new_page(); page_errors=[]; console_errors=[]
            page.on('pageerror',lambda exc: page_errors.append(str(exc))); page.on('console',lambda msg: console_errors.append(msg.text) if msg.type=='error' else None)

            def fulfill_json(route,status,payload): route.fulfill(status=status,content_type='application/json',body=json.dumps(payload))
            def route_handler(route):
                nonlocal browser_intake
                req=route.request; u=urllib.parse.urlparse(req.url); path=u.path
                if path=='/': return route.fulfill(status=200,content_type='text/html',body=(ROOT/'web'/'index.html').read_text())
                if path=='/styles.css': return route.fulfill(status=200,content_type='text/css',body=(ROOT/'web'/'styles.css').read_text())
                if path=='/app.js': return route.fulfill(status=200,content_type='application/javascript',body=(ROOT/'web'/'app.js').read_text())
                if path=='/api/health': return fulfill_json(route,200,{'ok':True,'build':'AGAPE-MAINFRAME-V5.5-FULL-QA','instance_id':'QA-BROWSER','settings':{'setup_complete':True,'experience':'standard','quality':'standard'}})
                if path=='/api/projects': return fulfill_json(route,200,{'ok':True,'projects':[{'id':1,'name':'QA Saved Project'}]})
                if path=='/api/recent': return fulfill_json(route,200,{'ok':True,'items':[]})
                if path=='/api/intake/start': return fulfill_json(route,202,{'ok':True,'prepare_job_id':'PREP-QA-BROWSER'})
                if path.startswith('/api/intake-prepare/'):
                    prep_polls['n']+=1
                    if prep_polls['n']<2: return fulfill_json(route,200,{'status':'RUNNING','progress':55,'message':'Filling brief with AI'})
                    return fulfill_json(route,200,{'status':'COMPLETE','progress':100,'message':'Source prepared','result':{'intake':browser_intake}})
                if path.endswith('/answers') and path.startswith('/api/intake/'):
                    try: payload=json.loads(req.post_data or '{}'); answers=payload.get('answers') or {}
                    except Exception: answers={}
                    for key,value in answers.items():
                        if key in browser_intake['ai_fill']['fields']: browser_intake['ai_fill']['fields'][key]={'value':str(value),'status':'user','reason':'User supplied during QA'}
                    return fulfill_json(route,200,{'ok':True,'intake':browser_intake})
                if path.endswith('/improve') and path.startswith('/api/intake/'):
                    time.sleep(1.4); browser_intake=improved_intake(browser_intake); return fulfill_json(route,200,{'ok':True,'intake':browser_intake})
                if path.endswith('/revise') and path.startswith('/api/intake/'):
                    browser_intake=revised_intake(browser_intake); return fulfill_json(route,200,{'ok':True,'intake':browser_intake})
                if path=='/api/run': browser_job_polls['n']=0; return fulfill_json(route,202,{'ok':True,'job_id':'QA-JOB-1'})
                if path=='/api/work/QA-JOB-1':
                    browser_job_polls['n']+=1; n=browser_job_polls['n']; stages=[(18,'Reading project brief','Reading project brief'),(34,'Planning document structure','Planning document structure'),(55,'AI drafting','Starting AI draft'),(78,'Validating','Validating Findings and Analysis'),(94,'Creating PDF','Creating PDF copy')]
                    if n<=len(stages):
                        progress,stage,message=stages[n-1]; return fulfill_json(route,200,{'ok':True,'job':{'id':'QA-JOB-1','status':'RUNNING','progress':progress,'stage':stage,'message':message}})
                    files=[{'ok':True,'file':str(result_docx),'name':result_docx.name},{'ok':True,'file':str(result_pdf),'name':result_pdf.name}]; return fulfill_json(route,200,{'ok':True,'job':{'id':'QA-JOB-1','status':'PASS','progress':100,'stage':'Document ready','message':'Document ready','result':{'ok':True,'files':files}}})
                if path=='/api/work/QA-JOB-1/download':
                    q=urllib.parse.parse_qs(u.query); idx=int((q.get('index') or ['0'])[0]); browser_downloads[idx]=browser_downloads.get(idx,0)+1
                    if idx==1 and browser_downloads[idx]==1: return fulfill_json(route,503,{'error':'QA_FORCED_FIRST_DOWNLOAD_FAILURE'})
                    target=[result_docx,result_pdf][idx]; ctype='application/pdf' if idx==1 else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'; return route.fulfill(status=200,headers={'Content-Type':ctype,'Content-Disposition':f'attachment; filename="{target.name}"','Content-Length':str(target.stat().st_size)},body=target.read_bytes())
                if path=='/api/work/QA-JOB-1/open-folder': return fulfill_json(route,200,{'ok':True,'simulated':True,'folder':str(generated)})
                return fulfill_json(route,404,{'error':'QA_ROUTE_NOT_FOUND:'+path})

            # This environment blocks browser navigation to local/test hosts by policy.
            # Keep the test as real Chromium clicks, but load the actual Agape HTML/CSS/JS
            # directly into the page and stub fetch() in-page. Backend HTTP integration is
            # tested separately above against the real Mainframe and Workflow Bridge.
            browser_intake_json = json.dumps(base_intake())
            result_docx_b64 = base64.b64encode(result_docx.read_bytes()).decode('ascii')
            result_pdf_b64 = base64.b64encode(result_pdf.read_bytes()).decode('ascii')
            mock_fetch_js = f"""
<script>
(() => {{
  let intake = {browser_intake_json};
  let prepPolls = 0, jobPolls = 0;
  const downloads = {{0:0, 1:0}};
  const delay = ms => new Promise(r => setTimeout(r, ms));
  const jsonResponse = (status, payload) => new Response(JSON.stringify(payload), {{status, headers:{{'Content-Type':'application/json'}}}});
  const bytesFromB64 = b64 => Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const improve = row => {{
    const out = JSON.parse(JSON.stringify(row));
    out.ai_fill.fields.competitors_alternatives = {{value:'Local fit-out contractors, direct flooring specialists and in-house procurement',status:'researched',reason:'Public research QA result'}};
    out.ai_fill.fields.research_focus = {{value:'Current UK commercial interiors demand, lending context and competitor positioning',status:'researched',reason:'Public research QA result'}};
    const recipient = String(out.ai_fill.fields.recipient_decision_maker?.value || '').trim().toLowerCase();
    out.unresolved_questions = recipient && recipient !== 'none' ? [] : [{{field_id:'recipient_decision_maker',question:'Who is the intended decision-maker?',researchable:false}}];
    out.extra_information_opportunities = [];
    out.established_count = 17 - out.unresolved_questions.length;
    return out;
  }};
  const revise = row => {{
    const out = JSON.parse(JSON.stringify(row));
    out.ai_fill.fields.tone = {{value:'Formal bank lending tone',status:'revised',reason:'Applied from AI brief-change instruction'}};
    return out;
  }};
  window.fetch = async (input, opt={{}}) => {{
    const raw = typeof input === 'string' ? input : input.url;
    const u = new URL(raw, 'http://agape.test/');
    const path = u.pathname;
    if (path === '/api/health') return jsonResponse(200, {{ok:true,build:'AGAPE-MAINFRAME-V5.5-FULL-QA',instance_id:'QA-BROWSER',settings:{{setup_complete:true,experience:'standard',quality:'standard'}}}});
    if (path === '/api/projects') return jsonResponse(200, {{ok:true,projects:[{{id:1,name:'QA Saved Project'}}]}});
    if (path === '/api/recent') return jsonResponse(200, {{ok:true,items:[]}});
    if (path === '/api/intake/start') return jsonResponse(202, {{ok:true,prepare_job_id:'PREP-QA-BROWSER'}});
    if (path.startsWith('/api/intake-prepare/')) {{
      prepPolls += 1;
      if (prepPolls < 2) return jsonResponse(200, {{status:'RUNNING',progress:55,message:'Filling brief with AI'}});
      return jsonResponse(200, {{status:'COMPLETE',progress:100,message:'Source prepared',result:{{intake}}}});
    }}
    if (path.startsWith('/api/intake/') && path.endsWith('/answers')) {{
      try {{
        const payload = JSON.parse(opt.body || '{{}}');
        for (const [key,value] of Object.entries(payload.answers || {{}})) {{
          if (intake.ai_fill.fields[key]) intake.ai_fill.fields[key] = {{value:String(value),status:'user',reason:'User supplied during QA'}};
        }}
      }} catch (_) {{}}
      return jsonResponse(200, {{ok:true,intake}});
    }}
    if (path.startsWith('/api/intake/') && path.endsWith('/improve')) {{
      await delay(1400); intake = improve(intake); return jsonResponse(200, {{ok:true,intake}});
    }}
    if (path.startsWith('/api/intake/') && path.endsWith('/revise')) {{
      intake = revise(intake); return jsonResponse(200, {{ok:true,intake}});
    }}
    if (path === '/api/run') {{ jobPolls = 0; return jsonResponse(202, {{ok:true,job_id:'QA-JOB-1'}}); }}
    if (path === '/api/work/QA-JOB-1') {{
      jobPolls += 1;
      const stages = [
        [18,'Reading project brief','Reading project brief'],
        [34,'Planning document structure','Planning document structure'],
        [55,'AI drafting','Starting AI draft'],
        [78,'Validating','Validating Findings and Analysis'],
        [94,'Creating PDF','Creating PDF copy']
      ];
      if (jobPolls <= stages.length) {{
        const [progress,stage,message] = stages[jobPolls-1];
        return jsonResponse(200, {{ok:true,job:{{id:'QA-JOB-1',status:'RUNNING',progress,stage,message}}}});
      }}
      return jsonResponse(200, {{ok:true,job:{{id:'QA-JOB-1',status:'PASS',progress:100,stage:'Document ready',message:'Document ready',result:{{ok:true,files:[
        {{ok:true,file:'{str(result_docx).replace('\\','/')}',name:'{result_docx.name}'}},
        {{ok:true,file:'{str(result_pdf).replace('\\','/')}',name:'{result_pdf.name}'}}
      ]}}}}}});
    }}
    if (path === '/api/work/QA-JOB-1/download') {{
      const idx = Number(u.searchParams.get('index') || 0);
      downloads[idx] = (downloads[idx] || 0) + 1;
      if (idx === 1 && downloads[idx] === 1) return jsonResponse(503, {{error:'QA_FORCED_FIRST_DOWNLOAD_FAILURE'}});
      const isPdf = idx === 1;
      const bytes = bytesFromB64(isPdf ? '{result_pdf_b64}' : '{result_docx_b64}');
      const name = isPdf ? '{result_pdf.name}' : '{result_docx.name}';
      const type = isPdf ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
      return new Response(bytes, {{status:200,headers:{{'Content-Type':type,'Content-Disposition':`attachment; filename="${{name}}"`,'Content-Length':String(bytes.byteLength)}}}});
    }}
    if (path === '/api/work/QA-JOB-1/open-folder') return jsonResponse(200, {{ok:true,simulated:true,folder:'QA generated folder'}});
    return jsonResponse(404, {{error:'QA_ROUTE_NOT_FOUND:'+path}});
  }};
}})();
</script>
"""
            html = (ROOT/'web'/'index.html').read_text(encoding='utf-8')
            css = (ROOT/'web'/'styles.css').read_text(encoding='utf-8')
            project_templates_js = (ROOT/'web'/'project_templates.js').read_text(encoding='utf-8').replace('</script>', '<\\/script>')
            app_js = (ROOT/'web'/'app.js').read_text(encoding='utf-8').replace('</script>', '<\\/script>')
            html = html.replace('<link rel="stylesheet" href="/styles.css">', '<style>'+css+'</style>')
            html = html.replace('<script src="/project_templates.js"></script>', '<script>'+project_templates_js+'</script>')
            html = html.replace('<script src="/app.js"></script>', mock_fetch_js+'<script>'+app_js+'</script>')
            def open_inline_ui():
                page.set_content(html, wait_until='load', timeout=30000)
                page.wait_for_function("document.getElementById('status') && document.getElementById('status').textContent === 'Ready'", timeout=10000)
                return 'Agape UI loaded directly in Chromium with in-page dummy APIs'
            _record(report,'open_agape_ui',open_inline_ui,'browser')
            _record(report,'choose_upload_source',lambda:(page.locator('[data-source-mode="upload"]').click(),page.locator('#file').set_input_files(str(source)),page.locator('#fileLabel').inner_text())[-1],'browser')
            _record(report,'fill_task',lambda:page.locator('#task').fill('Create a bank-ready expansion business plan. Preserve supplied facts and research safe public gaps.'),'browser')
            _record(report,'prepare_with_ai',lambda:(page.locator('#analyse').click(),page.locator('#intakeCard').wait_for(state='visible',timeout=15000),page.locator('#intakeSummary').inner_text())[-1],'browser')
            _record(report,'missing_menu_closed_by_default',lambda:(_ for _ in ()).throw(AssertionError('missing menu unexpectedly open')) if page.locator('#missingDetails').get_attribute('open') is not None else page.locator('#missingSummary').inner_text(),'browser')
            _record(report,'open_missing_menu',lambda:(page.locator('#missingSummary').click(),page.locator('#missingDetails[open]').wait_for(state='visible',timeout=3000),page.locator('#priorityFields textarea').count())[-1],'browser')
            _record(report,'fill_private_missing_field',lambda:(page.locator('[data-field="recipient_decision_maker"]').fill('Regional lending committee'),page.locator('[data-field="recipient_decision_maker"]').input_value())[-1],'browser')
            _record(report,'extra_information_menu_collapsed_by_default',lambda:(_ for _ in ()).throw(AssertionError('extra information menu unexpectedly open')) if page.locator('#extraInfoDetails').get_attribute('open') is not None else page.locator('#extraInfoSummary').inner_text(),'browser')
            _record(report,'open_extra_information_menu',lambda:(page.locator('#extraInfoDetails > summary').click(),page.locator('#extraInfoDetails[open]').wait_for(state='visible',timeout=3000),page.locator('#extraInfoList .research-opportunity').count())[-1],'browser')
            def research_ui():
                page.locator('#findMissing').click(); page.locator('#researchProgress').wait_for(state='visible',timeout=3000); first=page.locator('#researchPercent').inner_text(); page.wait_for_function("document.getElementById('researchPercent').textContent==='100%'",timeout=10000); return first+' -> '+page.locator('#researchStage').inner_text()
            _record(report,'research_own_progress_bar',research_ui,'browser')
            def extra_hidden_after_research():
                hidden=page.locator('#extraInfoDetails').evaluate("el => el.classList.contains('hidden')")
                if not hidden: raise AssertionError('extra information section should hide after research resolves all public gaps')
                return 'hidden'
            _record(report,'extra_information_hides_after_research',extra_hidden_after_research,'browser')
            _record(report,'brief_change_menu_closed',lambda:(_ for _ in ()).throw(AssertionError('brief change unexpectedly open')) if page.locator('#briefChangeDetails').get_attribute('open') is not None else 'closed','browser')
            _record(report,'open_fill_apply_brief_change',lambda:(page.locator('#briefChangeDetails summary').click(),page.locator('#formRevision').fill('Use a formal bank lending tone and preserve the £185,000 budget.'),page.locator('#reviseForm').click(),page.wait_for_function("!document.getElementById('briefChangeDetails').open",timeout=10000),'applied and collapsed')[-1],'browser')
            def create_ui():
                page.locator('#createDocument').click(); page.locator('#downloadManagerButton').wait_for(state='visible',timeout=5000); page.locator('#downloadManagerButton').click(); page.locator('#downloadManagerPanel').wait_for(state='visible',timeout=3000); page.wait_for_timeout(1700); return page.locator('#downloadManagerItems').inner_text()
            _record(report,'create_and_open_download_manager',create_ui,'browser')
            _record(report,'result_finishes',lambda:(page.wait_for_function("document.getElementById('progressTitle').textContent==='Finished'",timeout=20000),page.locator('[data-result-download]').count())[-1],'browser')
            saved_docx=downloads/result_docx.name
            def dl_docx():
                with page.expect_download(timeout=10000) as info: page.locator('[data-result-download="0"]').click()
                info.value.save_as(str(saved_docx)); return saved_docx.stat().st_size
            _record(report,'download_finished_docx_real_click',dl_docx,'browser'); _record(report,'validate_browser_docx',lambda:_validate_docx(saved_docx) or 'valid DOCX','browser')
            def pdf_fail():
                page.wait_for_function("document.querySelector('[data-dm-download=\"1\"]')",timeout=3000); page.locator('[data-dm-download="1"]').click(); page.wait_for_function("document.querySelector('[data-dm-download=\"1\"]') && document.querySelector('[data-dm-download=\"1\"]').textContent.includes('Retry')",timeout=5000); return 'retry visible'
            _record(report,'forced_pdf_failure_shows_retry',pdf_fail,'browser')
            saved_pdf=downloads/result_pdf.name
            def dl_pdf_retry():
                with page.expect_download(timeout=10000) as info: page.locator('[data-dm-download="1"]').click()
                info.value.save_as(str(saved_pdf)); return saved_pdf.stat().st_size
            _record(report,'retry_pdf_download_real_click',dl_pdf_retry,'browser'); _record(report,'validate_browser_pdf',lambda:_validate_pdf(saved_pdf) or 'valid PDF','browser')
            _record(report,'open_folder_action',lambda:(page.locator('[data-dm-open="0"]').click(),page.wait_for_timeout(250),page.locator('#status').inner_text())[-1],'browser')
            _record(report,'download_again_button_present',lambda:page.locator('[data-dm-download="0"]').inner_text(),'browser')
            page.screenshot(path=str(work/'full-qa-final.png'),full_page=True); report['console_errors']=console_errors; report['page_errors']=page_errors; ctx.close(); browser.close()

        failures=[x for x in report['steps'] if x['status']!='PASS']; report['status']='PASS' if not failures and not report.get('page_errors') else 'FAIL'; report['ok']=report['status']=='PASS'; report['pass_count']=sum(x['status']=='PASS' for x in report['steps']); report['fail_count']=len(failures); report['downloads']=[{'name':p.name,'bytes':p.stat().st_size} for p in sorted(downloads.glob('*'))]
    finally:
        if main_srv: main_srv.shutdown(); main_srv.server_close()
        flow_srv.shutdown(); flow_srv.server_close(); doc_srv.shutdown(); doc_srv.server_close(); (work/'FULL-QA-REPORT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--output',default=''); a=ap.parse_args(); out=run(Path(a.output).resolve() if a.output else None); print(json.dumps(out,indent=2)); raise SystemExit(0 if out.get('ok') else 2)
