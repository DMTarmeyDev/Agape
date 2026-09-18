from __future__ import annotations
import re

def classify_task(task: str) -> str:
    text = str(task or "").lower()
    coding = ("fix", "repair", "debug", "test", "tests", "python", "code", "refactor", "implement", "api", "database", "project")
    return "coding" if any(k in text for k in coding) else "chat"

def _names(model_names):
    result=[]
    for item in model_names or []:
        name=str(item.get("name") or "") if isinstance(item,dict) else str(item)
        if name and name not in result: result.append(name)
    return result

def choose_model(model_names, task: str) -> dict:
    names=_names(model_names)
    if not names:
        return {"ok": False, "model": "", "task_type": classify_task(task), "reason": "NO_MODELS"}
    lower={n.lower():n for n in names}
    kind=classify_task(task)
    wanted=("qwen2.5-coder:7b","qwen2.5-coder:7b-instruct","qwen2.5-coder:3b","qwen2.5-coder:1.5b-instruct") if kind=="coding" else ("qwen2.5-coder:1.5b-instruct","qwen2.5-coder:1.5b","qwen2.5-coder:7b")
    for key in wanted:
        if key in lower:
            return {"ok": True, "model": lower[key], "task_type": kind, "reason": "TASK_ROUTER"}
    def score(name):
        m=re.search(r"(\d+(?:\.\d+)?)b",name.lower())
        size=float(m.group(1)) if m else 0.0
        return (1 if "coder" in name.lower() else 0, size)
    selected=max(names,key=score) if kind=="coding" else names[0]
    return {"ok": True, "model": selected, "task_type": kind, "reason": "BEST_AVAILABLE"}

def choose_project_model(model_names, task: str, project=None, messages=None, settings=None, runs=None, issues=None, code_index=None) -> dict:
    """Choose an installed model using the loaded project's accumulated context.

    This remains deterministic: no model is asked to choose another model.  The router
    considers project metadata, saved goal/workspace, codebase size/languages, recent
    conversation, open issues, current task and this project's prior loop outcomes.
    """
    names=_names(model_names)
    if not names:
        return {"ok":False,"model":"","reason":"NO_MODELS","project_loaded":bool(project)}
    if not project:
        result=choose_model(names,task)
        result.update({"project_loaded":False,"reason":"PROJECT_REQUIRED"})
        return result

    project=dict(project or {}); messages=list(messages or []); settings=dict(settings or {})
    runs=list(runs or []); issues=list(issues or []); idx=dict(code_index or {})
    files=list(idx.get('files') or []) if idx.get('ok') else []
    ext_counts={}
    total_bytes=0
    for f in files:
        path=str(f.get('path') or '')
        ext='.'+path.rsplit('.',1)[-1].lower() if '.' in path.rsplit('/',1)[-1] else '(none)'
        ext_counts[ext]=ext_counts.get(ext,0)+1
        total_bytes+=int(f.get('size') or 0)
    languages=[]
    lang_map={'.py':'Python','.js':'JavaScript','.mjs':'JavaScript','.cjs':'JavaScript','.ts':'TypeScript','.tsx':'TypeScript','.jsx':'JavaScript','.html':'HTML','.css':'CSS','.ps1':'PowerShell','.cmd':'Batch','.bat':'Batch','.c':'C','.h':'C/C++','.cpp':'C++','.hpp':'C++','.cs':'C#','.rs':'Rust','.go':'Go','.java':'Java','.kt':'Kotlin','.sql':'SQL'}
    for ext,count in sorted(ext_counts.items(),key=lambda kv:(-kv[1],kv[0])):
        if ext in lang_map and lang_map[ext] not in languages: languages.append(lang_map[ext])

    recent=' '.join(str(m.get('content') or '') for m in messages[-20:])
    issue_text=' '.join(str(x.get('title') or x.get('problem') or x.get('detail') or '') for x in issues if str(x.get('status') or '').lower() in {'','open','failed','fail'})
    combined=' '.join([str(project.get('name') or ''),str(settings.get('goal') or ''),str(task or ''),recent,issue_text]).lower()
    kind=classify_task(combined)
    coding_exts={'.py','.js','.mjs','.cjs','.ts','.tsx','.jsx','.html','.css','.ps1','.cmd','.bat','.c','.h','.cpp','.hpp','.cs','.rs','.go','.java','.kt','.sql'}
    code_files=sum(v for k,v in ext_counts.items() if k in coding_exts)
    open_issues=sum(1 for x in issues if str(x.get('status') or '').lower()=='open')
    failure_runs=sum(1 for r in runs if str(r.get('status') or r.get('overall') or '').upper() in {'FAIL','FAILED','ERROR'})
    complexity=0
    complexity_reasons=[]
    if code_files>=40: complexity+=3; complexity_reasons.append('large codebase')
    elif code_files>=12: complexity+=2; complexity_reasons.append('multi-file codebase')
    elif code_files>0: complexity+=1; complexity_reasons.append('code project')
    if total_bytes>=1_000_000: complexity+=2; complexity_reasons.append('large source volume')
    elif total_bytes>=200_000: complexity+=1; complexity_reasons.append('substantial source volume')
    if open_issues>=3: complexity+=2; complexity_reasons.append('multiple open issues')
    elif open_issues: complexity+=1; complexity_reasons.append('open issue')
    if failure_runs>=2: complexity+=2; complexity_reasons.append('repeated failed runs')
    elif failure_runs: complexity+=1; complexity_reasons.append('previous failed run')
    hard_words=('debug','repair','refactor','architecture','database','security','integration','failing','failure','crash','multi-file','project loop','implement')
    if any(k in combined for k in hard_words): complexity+=2; complexity_reasons.append('complex development intent')
    if len(str(task or ''))>600 or len(recent)>6000: complexity+=1; complexity_reasons.append('large working context')

    # Project-specific historical outcomes from this project's bounded loop runs.
    hist={}
    for r in runs:
        model=str(r.get('model') or '')
        if not model: continue
        h=hist.setdefault(model,{'total':0,'success':0,'fail':0})
        h['total']+=1
        state=str(r.get('status') or r.get('overall') or '').upper()
        if state in {'PASS','COMPLETED','COMPLETE','DONE','PAUSED_LIMIT'}: h['success']+=1
        elif state in {'FAIL','FAILED','ERROR'}: h['fail']+=1

    def model_size(name):
        m=re.search(r'(\d+(?:\.\d+)?)b',name.lower()); return float(m.group(1)) if m else 0.0
    scores=[]
    for name in names:
        low=name.lower(); size=model_size(name); score=0.0; why=[]
        if kind=='coding':
            if 'coder' in low: score+=4; why.append('coding-specialized')
            # Prefer greater capability when project complexity warrants it, smaller model for light work.
            if complexity>=4: score+=min(size,14.0)*0.8
            elif complexity>=2: score+=min(size,14.0)*0.45
            else: score+=max(0.0,3.0-abs(size-1.5))*0.45
        else:
            score+=max(0.0,4.0-abs(size-1.5))*0.55
            if 'coder' in low and code_files: score+=0.5
        h=hist.get(name) or {}
        if h.get('total'):
            rate=float(h.get('success',0))/float(h['total'])
            score+=(rate-0.5)*2.0
            why.append(f"project-history {h.get('success',0)}/{h['total']}")
        scores.append({'model':name,'score':round(score,3),'size_b':size,'signals':why})
    scores.sort(key=lambda x:(x['score'],x['size_b']),reverse=True)
    selected=scores[0]['model']
    context_summary={
        'project_id':int(project.get('id') or 0),'project_name':str(project.get('name') or ''),
        'goal':str(settings.get('goal') or ''),'workspace':str(settings.get('workspace') or ''),
        'indexed_files':len(files),'code_files':code_files,'source_bytes':total_bytes,
        'languages':languages[:8],'recent_messages':len(messages[-20:]),'open_issues':open_issues,
        'previous_loop_runs':len(runs),'failed_loop_runs':failure_runs,'task_type':kind,
        'complexity_score':complexity,'complexity_reasons':complexity_reasons,
    }
    reason='PROJECT_AWARE_ROUTER: '+(', '.join(complexity_reasons[:4]) if complexity_reasons else ('light project context' if kind=='coding' else 'general project chat'))
    return {'ok':True,'model':selected,'task_type':kind,'reason':reason,'project_loaded':True,'context':context_summary,'scores':scores}
