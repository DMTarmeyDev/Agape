"""End-to-end R2.4 proof: incomplete upload -> AI gap research -> Gold Standard -> validated final file."""
from __future__ import annotations
import json, os, tempfile, threading, time, urllib.request, base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]

class Fake(BaseHTTPRequestHandler):
    jobs=[]
    review={}
    agent_create_calls=0
    def log_message(self,*a): pass
    def sendj(self,n,obj):
        b=json.dumps(obj).encode();self.send_response(n);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def body(self):
        n=int(self.headers.get('Content-Length','0') or 0);return json.loads(self.rfile.read(n) or b'{}')
    def do_GET(self):
        port=self.server.server_address[1]
        if port==18797:
            if self.path.startswith('/api/version'): return self.sendj(200,{'build':'DMT-CORE-V3.1-EARLY-ALPHA-R8','data_path':self.server.data_path})
            if self.path.startswith('/api/projects'): return self.sendj(200,{'projects':[{'id':5,'name':'GreenStep Commercial Interiors Business Plan 2027','kind':'user','archived':False}]})
            if self.path.startswith('/api/project-template/status'): return self.sendj(200,{'active':True,'template':{'system_instruction':'Create a complete business plan.'}})
            if self.path.startswith('/api/project-loop/settings'): return self.sendj(200,{'settings':{}})
            if self.path.startswith('/api/project-loop/runs'): return self.sendj(200,{'runs':[]})
            if self.path.startswith('/api/messages'): return self.sendj(200,{'messages':[]})
            if self.path.startswith('/api/models/recommend'): return self.sendj(200,{'ok':True,'model':'qwen2.5-coder:1.5b-instruct','task_type':'coding','reason':'PROJECT_AWARE_ROUTER'})
        if port==18820:
            if self.path.startswith('/api/health'): return self.sendj(200,{'ok':True,'version':'R1.3'})
            if self.path.startswith('/api/status'): return self.sendj(200,{'jobs':self.jobs})
        if port==18800:
            if self.path.startswith('/api/health'): return self.sendj(200,{'ok':True,'version':'R31.16'})
            if self.path.startswith('/api/provider-connections/status'):
                return self.sendj(200,{'ok':True,'providers':[
                    {'id':'chatgpt','name':'ChatGPT / OpenAI','recommended_model':'top-a','review_score':10.0,'connected':True},
                    {'id':'claude','name':'Claude / Anthropic','recommended_model':'top-b','review_score':9.9,'connected':True},
                    {'id':'gemini','name':'Google Gemini','recommended_model':'top-c','review_score':9.8,'connected':True},
                    {'id':'xai','name':'Grok / xAI','recommended_model':'top-d','review_score':9.7,'connected':True},
                    {'id':'deepseek','name':'DeepSeek','recommended_model':'top-e','review_score':9.6,'connected':True},
                    {'id':'mistral','name':'Mistral AI','recommended_model':'top-f','review_score':9.5,'connected':True},
                    {'id':'cohere','name':'Cohere','recommended_model':'top-g','review_score':9.4,'connected':True},
                    {'id':'openrouter','name':'OpenRouter','recommended_model':'top-h','review_score':9.3,'connected':True},
                    {'id':'groq','name':'GroqCloud','recommended_model':'top-i','review_score':9.2,'connected':True},
                    {'id':'huggingface','name':'Hugging Face','recommended_model':'top-j','review_score':9.1,'connected':True}
                ]})
            if self.path.startswith('/api/multi-review/status'):
                return self.sendj(200,Fake.review or {'state':'working','stage':'Reviewing','progress':50})
        return self.sendj(404,{'error':'not found'})
    def do_POST(self):
        port=self.server.server_address[1]
        if port==18820 and self.path=='/api/jobs':
            jid='FAKE-WORK-1';self.jobs[:]=[{'id':jid,'state':'PASS','kind':'service_health'}];return self.sendj(202,{'job_id':jid})
        if port==18800:
            if self.path=='/api/upload-instruction':
                b=self.body();assert b.get('data_base64');return self.sendj(200,{'ok':True,'upload':{'id':'UP-ONE','name':b.get('name'),'preview':'Organisation: GreenStep. Purpose: complete business plan.'}})
            if self.path=='/api/ai-fill-form':
                b=self.body();assert b.get('force_fill_missing') is True
                deep=bool(b.get('research_enabled')) and b.get('research_depth')=='deep'
                names=['organisation_proposer','recipient_decision_maker','industry_sector','market_geography','product_service','problem_need','document_purpose','decision_action_requested','target_audience','value_proposition','budget_pricing_commercial_terms','timeline_target_date','success_measures','competitors_alternatives','constraints','tone','research_focus']
                fields={name:{'value':('Researched competitors and alternatives' if deep and name=='competitors_alternatives' else ('None' if name=='competitors_alternatives' else 'Filled '+name)),'status':('researched' if deep and name=='competitors_alternatives' else 'supplied')} for name in names}
                return self.sendj(200,{'ok':True,'title':'GreenStep Commercial Interiors Business Plan 2027','fields':fields,'design':{'app':'writer','doc_type':'Business Proposal','theme':'Executive Navy','template_id':'T1','template_name':'Business Plan Master','format':'docx','filename':'greenstep-gold-plan'},'best_model_selection':{'provider':'chatgpt','model':'top-a','utility_score':10}})
            if self.path=='/api/agent-create':
                b=self.body();assert len(b.get('structured_form') or {})==17
                Fake.agent_create_calls+=1
                if Fake.agent_create_calls==1:
                    return self.sendj(500,{'error':'GENERATED_DOCUMENT_VALIDATION_FAILED={\"missing\": [\"Recommendation / Next Step\", \"Sources / Evidence\"], \"short\": [\"TAM / SAM / SOM\", \"Customer Personas\"]}'})
                repair_text=b.get('instructions','')
                for marker in ('Recommendation / Next Step','Sources / Evidence','TAM / SAM / SOM','Customer Personas','AGAPE TARGETED VALIDATION REPAIR PASS'):
                    assert marker in repair_text,repair_text
                out=Path(self.server.data_path)/'first.docx';out.write_bytes(b'first');return self.sendj(200,{'ok':True,'draft':'# Executive Summary\nStrong repaired first draft.\n# TAM / SAM / SOM\nSubstantive analysis.\n# Customer Personas\nDetailed personas.\n# Recommendation / Next Step\nConcrete action.\n# Sources / Evidence\nEvidence register.','audit':{'ok':True},'model_trace':[{'provider':'chatgpt','model':'top-a'}],'files':[{'ok':True,'file':str(out),'name':out.name,'engine':'fake'}]})
            if self.path=='/api/multi-review/start':
                b=self.body();reviewers=b.get('reviewers') or [];assert len(reviewers)==3,reviewers;assert b.get('lead_reviewer')=='auto',b;Fake.review={'state':'ready','stage':'Lead synthesis complete','progress':100,'average_score':9.7,'reviews':[{'provider':rid,'provider_name':rid.title(),'model':'model-'+rid,'scores':{'overall':9.5+(i%5)*0.1}} for i,rid in enumerate(reviewers)],'lead':{'lead_provider':'chatgpt','lead_provider_name':'ChatGPT','lead_model':'top-a','final_summary':'Merged the strongest evidence and structure.','accepted_changes':['Sharper executive summary','Stronger risk section'],'revised_draft':'# Executive Summary\nGold revised draft.\n# Strategy\nBest combined strategy.'}};return self.sendj(202,{'job_id':'REV-1'})
            if self.path=='/api/review/recreate':
                b=self.body();assert 'Gold revised draft' in b.get('content','');out=Path(self.server.data_path)/'Gold-Final.docx';out.write_bytes(b'gold');pdf=Path(self.server.data_path)/'Gold-Final.pdf';pdf.write_bytes(b'pdf');return self.sendj(200,{'ok':True,'files':[{'ok':True,'file':str(out),'name':out.name,'engine':'fake'},{'ok':True,'file':str(pdf),'name':pdf.name,'engine':'fake'}]})
            if self.path=='/api/open-file': return self.sendj(200,{'ok':True})
        return self.sendj(404,{'error':'not found'})

def start(port,data):
    s=ThreadingHTTPServer(('127.0.0.1',port),Fake);s.data_path=str(data);threading.Thread(target=s.serve_forever,daemon=True).start();return s

def getj(url):
    with urllib.request.urlopen(url,timeout=5) as r:return json.loads(r.read())

def postj(url,obj,timeout=15):
    req=urllib.request.Request(url,data=json.dumps(obj).encode(),headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read())

def main():
    temp=Path(tempfile.mkdtemp(prefix='agu-r2-int-'));(temp/'security').mkdir();(temp/'security'/'local-session-token.txt').write_text('test')
    servers=[start(18797,temp),start(18820,temp),start(18800,temp)]
    # Isolate both the R2.4 data root and LOCALAPPDATA. Without this, the fake
    # integration test can see a real R2.2 settings.json on the user's machine and
    # correctly migrate setup_complete=True, which is valid live behaviour but not
    # a clean first-run test.
    fake_local=temp/'localappdata';fake_local.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env.update({'AGAPE_CORE_URL':'http://127.0.0.1:18797','AGAPE_WORK_URL':'http://127.0.0.1:18820','AGAPE_DOC_URL':'http://127.0.0.1:18800','AGAPE_UNIFIED_DATA':str(temp/'unified'),'LOCALAPPDATA':str(fake_local)})
    import subprocess,sys
    p=subprocess.Popen([sys.executable,str(BASE/'app.py'),'--port','18840'],env=env)
    try:
        for _ in range(50):
            try:
                if getj('http://127.0.0.1:18840/api/health').get('ok'):break
            except Exception:time.sleep(.1)
        setup=getj('http://127.0.0.1:18840/api/settings');assert setup['settings']['router']=='agape' and setup['settings']['setup_complete'] is False,setup
        rt=postj('http://127.0.0.1:18840/api/router/test',{'router':'agape'});assert rt['ok'] and rt['router']=='agape',rt
        saved=postj('http://127.0.0.1:18840/api/settings',{'router':'agape','setup_complete':True});assert saved['settings']['setup_complete'] is True and saved['settings']['router']=='agape',saved
        research=getj('http://127.0.0.1:18840/api/research/recommend?q=UK%20technology%20company%20business%20plan%20investment');assert research['selected_count']==10 and len(research['sources'])==10,research
        intake=postj('http://127.0.0.1:18840/api/document/intake',{'project_id':5,'project_info':'Saved facts','name':'source.docx','data_base64':base64.b64encode(b'one source').decode(),'format':'docx','also_pdf':True})['intake']
        assert intake['field_count']==17,intake
        assert intake['router']=='agape',intake
        assert intake['none_count']==1,intake
        assert intake['research_plan']['selected_count']==10,intake
        assert len(intake['unresolved_questions'])==1,intake
        improved=postj('http://127.0.0.1:18840/api/intakes/'+intake['id']+'/improve',{})['intake']
        assert improved['none_count']==0,improved
        assert improved['last_gap_fill']['resolved']==1,improved
        intake=improved
        q=getj('http://127.0.0.1:18840/api/quality-status');assert q['gold_ready'] and q['connected_count']==10 and q['default_reviewer_count']==3,q
        started=postj('http://127.0.0.1:18840/api/jobs',{'project_id':5,'intake_id':intake['id'],'quality_mode':'gold','format':'docx','document_theme':'auto','also_pdf':True,'reviewer_count':3,'reviewer_ids':[],'lead_reviewer':'auto'})
        jid=started['job_id'];deadline=time.time()+12;job=None
        while time.time()<deadline:
            job=getj('http://127.0.0.1:18840/api/jobs/'+jid)['job']
            if job['status'] in ('PASS','FAIL','BLOCKED'):break
            time.sleep(.15)
        assert job and job['status']=='PASS',job
        assert job['router']=='agape',job
        assert job['result']['quality_mode']=='gold',job
        assert len(job['result']['validation_repairs'])==1,job
        assert Fake.agent_create_calls==2,Fake.agent_create_calls
        assert len(job['result']['files'])==2,job
        assert Path(job['result']['files'][0]['file']).name=='Gold-Final.docx'
        assert len(job['result']['review']['reviewers'])==3
        assert job['result']['review']['requested_count']==3
        assert job['result']['review']['used_count']==3
        print('R2_4_SETUP_ROUTER_HTTP=PASS')
        print('R2_4_RESEARCH_ROUTER_HTTP=PASS')
        print('R2_4_MISSING_INFO_AI_RECOVERY=PASS')
        print('R2_4_VALIDATION_AUTO_REPAIR=PASS')
        print('V3_1_GOLD_REVIEWER_SELECTOR=PASS')
        print('R2_4_FAKE_GOLD_INTEGRATION=PASS')
    finally:
        p.terminate();p.wait(timeout=5)
        for s in servers:s.shutdown();s.server_close()
if __name__=='__main__':main()
