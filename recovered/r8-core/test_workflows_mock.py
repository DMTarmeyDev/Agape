import os,sys,tempfile,shutil
from pathlib import Path
sandbox=Path(tempfile.mkdtemp(prefix='dmt-v13-workflows-'))
os.environ['DMT_DATA_ROOT']=str(sandbox/'data')
os.environ['DMT_WORKFLOW_ROOT']=str(sandbox/'workflows')
sys.path.insert(0,str(Path(__file__).resolve().parent))
import db,workflows

db.init_db()

def fake_models(): return [{'name':'qwen2.5-coder:1.5b-instruct'},{'name':'qwen2.5-coder:7b'}]
job=[0]
ai_calls=[0]
def fake_ps(command,project_id=None):
    job[0]+=1
    jid=f'TERM-MOCK-{job[0]}'
    db.terminal_job_create(jid,project_id,command,'normal')
    stdout=''
    exit_code=0
    if "DMT_TEMPLATE1_TERMINAL_OK" in command: stdout='DMT_TEMPLATE1_TERMINAL_OK\n'
    elif 'deliberately-missing.txt' in command: exit_code=1
    elif 'FromBase64String' in command:
        import re,base64
        path=re.search(r"WriteAllBytes\('([^']+)'",command).group(1).replace("''", "'")
        data=re.search(r"FromBase64String\('([^']+)'\)",command).group(1)
        Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_bytes(base64.b64decode(data));stdout='DMT_SNAKE_BUILD_OK\n'
    elif 'Set-Content' in command:
        import re
        m=re.search(r"Set-Content -LiteralPath '([^']+)' -Value '([^']+)' -Encoding UTF8",command)
        if m: Path(m.group(1)).parent.mkdir(parents=True,exist_ok=True);Path(m.group(1)).write_text(m.group(2),encoding='utf-8');stdout=m.group(2)
    elif 'WriteAllText' in command:
        import re
        m=re.search(r"WriteAllText\('([^']+)'\s*,\s*'([^']+)'",command)
        if m: Path(m.group(1)).parent.mkdir(parents=True,exist_ok=True);Path(m.group(1)).write_text(m.group(2),encoding='utf-8');stdout=m.group(2)
    elif 'Get-Content' in command:
        import re
        m=re.search(r"LiteralPath\s+'([^']+)'",command)
        if m and Path(m.group(1)).exists(): stdout=Path(m.group(1)).read_text(encoding='utf-8')
    elif 'Start-Process' in command: stdout='DMT_SNAKE_LAUNCH_REQUESTED\n'
    db.terminal_job_finish(jid,exit_code,stdout,'' if exit_code==0 else 'EXPECTED')
    return {'ok':exit_code==0,'executed':True,'job_id':jid,'exit_code':exit_code,'stdout':stdout,'stderr':'' if exit_code==0 else 'EXPECTED','risk':'normal','reason':'SAFE_NON_ADMIN_COMMAND'}

def fake_chat(project_id,message,provider,model,request_id=None,**kwargs):
    assert kwargs.get('single_tool') is True
    ai_calls[0]+=1
    # Prove workflow escalation: fast model fails; 7B succeeds.
    if model == 'qwen2.5-coder:1.5b-instruct':
        raise RuntimeError('FAST_MODEL_TOOL_BOUNDARY_MISS')
    assert model == 'qwen2.5-coder:7b'
    import re
    command=re.search(r'Use this exact PowerShell 5\.1 command:\n(.+?)\nUse Set-Content',message,re.S).group(1).strip()
    assert ';' in command
    assert 'Get-Content -LiteralPath' in command
    assert ' && ' not in command and ' || ' not in command
    m=re.search(r"Set-Content -LiteralPath '([^']+)' -Value '([^']+)' -Encoding UTF8",command)
    assert m
    path=m.group(1).replace("''", "'")
    value=m.group(2).replace("''", "'")
    Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_text(value,encoding='utf-8')
    return {'ok':True,'request_id':request_id,'execution':{'requested':True,'proven':True,'succeeded':True,'mode':'single_tool','tool_events':[{'call':{'name':'shell','arguments':{'cmd':command}},'result':{'executed':True,'job_id':'TERM-MOCK-AI','exit_code':0,'stdout':value+'\n'}}]}}

workflows.ollama_models=fake_models
workflows.run_powershell=fake_ps
workflows.run_chat=fake_chat
r1=workflows.run_template_1(); assert r1['ok'],r1
r2=workflows.run_template_2(launch=False); assert r2['ok'],r2
assert Path(r2['snake_file']).is_file()
print('TEMPLATE_1_WORKFLOW_MOCK=PASS')
print('TEMPLATE_2_WORKFLOW_MOCK=PASS')
print('TEMPLATE_REPORTS=PASS')
print('TEMPLATE_2_SNAKE_BUILD=PASS')
shutil.rmtree(sandbox,ignore_errors=True)
