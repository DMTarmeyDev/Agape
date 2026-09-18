import os, sys, tempfile, shutil
from pathlib import Path
sandbox=Path(tempfile.mkdtemp(prefix='dmt-v11-orch-'))
os.environ['DMT_DATA_ROOT']=str(sandbox/'data')
sys.path.insert(0,str(Path(__file__).resolve().parent))
import db, orchestrator
from providers import ProviderReply

db.init_db(); p=db.create_project('P')
assert 'never use && or ||' in orchestrator.CORRECTION.lower()
assert '&& or ||' in orchestrator.TOOL_SYSTEM
responses=[]
def fake_ollama(model,messages,num_predict=512,timeout=None,json_only=False):
    content=responses.pop(0)
    if json_only: assert isinstance(json_only,bool)
    return ProviderReply('ollama',model,content,0.01,{})
def fake_run(command,project_id=None):
    return {'ok':True,'executed':True,'job_id':'TERM-1','exit_code':0,'stdout':'OK\n','stderr':'','risk':'normal','reason':'SAFE_NON_ADMIN_COMMAND'}
orchestrator.ollama_chat=fake_ollama
orchestrator.run_powershell=fake_run
responses[:] = ['```json\n{"name":"shell","arguments":{"cmd":"Write-Output OK"}}\n```','done']
r=orchestrator.run_chat(int(p['id']),'Create a proof file now. Do not merely print PowerShell.','ollama','qwen')
assert r['execution']['requested'] is True
assert r['execution']['proven'] is True
assert r['execution']['succeeded'] is True
assert r['execution']['tool_events'][0]['call']['format']=='fenced_json'
# informational wording must not execute
responses[:] = ['Use Set-Content foo.txt']
r2=orchestrator.run_chat(int(p['id']),'How do I create a file in PowerShell?','ollama','qwen')
assert r2['execution']['requested'] is False
print('MOCK_ORCHESTRATOR_ACTION=PASS')
print('MOCK_FENCED_TOOL=PASS')
print('MOCK_EXECUTION_SUCCESS_SEMANTICS=PASS')
print('MOCK_INFORMATIONAL_NO_EXECUTION=PASS')

# deterministic single-tool mode must not call the model a second time after execution
responses[:] = ['```json\n{"name":"shell","arguments":{"cmd":"Write-Output OK"}}\n```']
r3=orchestrator.run_chat(int(p['id']),'Create one proof now.','ollama','qwen',single_tool=True)
assert r3['execution']['requested'] is True
assert r3['execution']['proven'] is True
assert r3['execution']['succeeded'] is True
assert r3['execution']['mode']=='single_tool'
assert len(r3['execution']['tool_events'])==1
assert responses==[]
print('MOCK_SINGLE_TOOL_MODE=PASS')
shutil.rmtree(sandbox,ignore_errors=True)
