param(
    [switch]$SkipCandidateBatchDemo,
    [switch]$KeepStage
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Build = 'AGAPE-V3.1-FULL-REBUILD-R1.6'
$ExpectedCoreBuild = 'DMT-CORE-V3.1-EARLY-ALPHA-R8'
$ExpectedWorkEngine = 'R1.3'
$TargetStudioVersion = 'R31.10'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$CorePort = 8797
$StudioPort = 8800
$WorkPort = 8820
$CandidateCorePort = 18977
$CandidateStudioPort = 18800
$CandidateWorkPort = 18820

function Say([string]$Name,[string]$Value,[string]$Color='Cyan') {
    Write-Host ("{0}={1}" -f $Name,$Value) -ForegroundColor $Color
}
function Assert-True($Condition,[string]$Message) { if(-not $Condition){ throw $Message } }
function Sha([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant() }
function Write-Utf8([string]$Path,[string]$Text) { [IO.File]::WriteAllText($Path,$Text,[Text.UTF8Encoding]::new($false)) }
function Get-Python {
    $p = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if(Test-Path -LiteralPath $p -PathType Leaf){ return $p }
    $c=Get-Command python.exe -ErrorAction SilentlyContinue; if($c){return $c.Source}
    $c=Get-Command python -ErrorAction SilentlyContinue; if($c){return $c.Source}
    throw 'PYTHON_NOT_FOUND'
}
function Get-Json([string]$Uri,[int]$Timeout=15) {
    try { return Invoke-RestMethod -Uri $Uri -TimeoutSec $Timeout }
    catch { return $null }
}
function Wait-Json([string]$Uri,[int]$Seconds=30) {
    $deadline=(Get-Date).AddSeconds($Seconds)
    while((Get-Date)-lt $deadline){
        $j=Get-Json $Uri 3
        if($j){return $j}
        Start-Sleep -Milliseconds 350
    }
    return $null
}
function Find-Core {
    $v=Get-Json 'http://127.0.0.1:8797/api/version' 4
    if($v -and $v.project_path -and (Test-Path -LiteralPath ([string]$v.project_path) -PathType Container)){
        return [IO.Path]::GetFullPath([string]$v.project_path)
    }
    foreach($c in @(
        (Join-Path $env:LOCALAPPDATA 'DMT-Core-V3.1\SecondBrain\dmt-second-brain'),
        (Join-Path $env:LOCALAPPDATA 'DMT-Core-V3.1-Early-Alpha\SecondBrain\dmt-second-brain')
    )){
        if((Test-Path -LiteralPath $c -PathType Container) -and (Test-Path -LiteralPath (Join-Path $c 'app.py') -PathType Leaf)){return [IO.Path]::GetFullPath($c)}
    }
    throw 'AGAPE_CORE_NOT_FOUND'
}
function Run-Python([string[]]$ProcessArgs,[string]$LogPath) {
    # R1.4: never leak child-process stdout into the function return stream.
    # R1/R1.1 used Tee-Object without a terminal sink, so callers received
    # [stdout lines..., exit_code] instead of a single integer.  In PowerShell,
    # `if($rc -ne 0)` then became true even when Python exited 0.
    $old=$ErrorActionPreference
    $ErrorActionPreference='Continue'
    try {
        & $script:Python @ProcessArgs 2>&1 |
            Tee-Object -FilePath $LogPath |
            Out-Host
        $code=$LASTEXITCODE
        if($null -eq $code){ return 9001 }
        return [int]$code
    }
    finally {
        $ErrorActionPreference=$old
    }
}
function Copy-Tree([string]$Source,[string]$Destination) {
    if(Test-Path -LiteralPath $Destination){Remove-Item -LiteralPath $Destination -Recurse -Force}
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $args=@($Source,$Destination,'/E','/COPY:DAT','/DCOPY:DAT','/R:1','/W:1','/XJ','/NFL','/NDL','/NP','/XD','__pycache__','.git','.venv','node_modules','/XF','*.pyc','*.pyo')
    & robocopy.exe @args | Out-Null
    $rc=$LASTEXITCODE
    if($rc -gt 7){throw "ROBOCOPY_FAILED=$rc SOURCE=$Source DEST=$Destination"}
}
function Copy-DataForCandidate([string]$Source,[string]$Destination,[string]$DbPath) {
    if(Test-Path -LiteralPath $Destination){Remove-Item -LiteralPath $Destination -Recurse -Force}
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $args=@($Source,$Destination,'/E','/COPY:DAT','/DCOPY:DAT','/R:1','/W:1','/XJ','/NFL','/NDL','/NP','/XD','document-studio','systems-engine','release-backups','artifact-exports','workflow-output','/XF','dmt_core.sqlite3','dmt_core.sqlite3-wal','dmt_core.sqlite3-shm','*.log')
    & robocopy.exe @args | Out-Null
    if($LASTEXITCODE -gt 7){throw "CANDIDATE_DATA_COPY_FAILED=$LASTEXITCODE"}
    $DestDb=Join-Path $Destination 'dmt_core.sqlite3'
    $code=@'
import sqlite3,sys
src,dst=sys.argv[1:3]
a=sqlite3.connect(src); b=sqlite3.connect(dst)
try: a.backup(b)
finally: b.close(); a.close()
print('SQLITE_BACKUP=PASS')
'@
    $helper=Join-Path $script:Stage 'sqlite-backup.py'; Write-Utf8 $helper $code
    $rc=Run-Python -ProcessArgs @($helper,$DbPath,$DestDb) -LogPath (Join-Path $script:ReportRoot 'candidate-db-backup.log')
    if($rc -ne 0){throw 'CANDIDATE_SQLITE_BACKUP_FAILED'}
}
function Start-BackgroundPython([string[]]$ProcessArgs,[string]$Out,[string]$Err,[hashtable]$EnvVars=$null) {
    $saved=@{}
    if($EnvVars){foreach($k in $EnvVars.Keys){$saved[$k]=[Environment]::GetEnvironmentVariable($k,'Process');[Environment]::SetEnvironmentVariable($k,[string]$EnvVars[$k],'Process')}}
    try {
        $quoted=@(); foreach($x in $ProcessArgs){$s=[string]$x;if($s -match '[\s"]'){$quoted+='"'+($s -replace '"','\"')+'"'}else{$quoted+=$s}}
        return Start-Process -FilePath $script:Python -ArgumentList ($quoted -join ' ') -WindowStyle Hidden -PassThru -RedirectStandardOutput $Out -RedirectStandardError $Err
    }
    finally {
        if($EnvVars){foreach($k in $EnvVars.Keys){[Environment]::SetEnvironmentVariable($k,$saved[$k],'Process')}}
    }
}
function Stop-ProcessSafe($Proc) { if($Proc){try{if(-not $Proc.HasExited){$Proc.Kill();$Proc.WaitForExit(5000)|Out-Null}}catch{}} }
function Stop-OwnedPort([int]$Port,[string]$OwnerRoot) {
    $conns=@(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    foreach($c in $conns){
        $pidValue=[int]$c.OwningProcess
        if($pidValue -le 0){continue}
        $p=Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue" -ErrorAction SilentlyContinue
        $cmd=if($p){[string]$p.CommandLine}else{''}
        if($cmd -and $cmd.IndexOf($OwnerRoot,[StringComparison]::OrdinalIgnoreCase) -ge 0){
            Stop-Process -Id $pidValue -Force -ErrorAction Stop
            Say "STOP_PORT_$Port" "PASS_PID_$pidValue" 'Yellow'
        } else {
            throw "PORT_${Port}_OWNED_BY_UNEXPECTED_PROCESS PID=$pidValue CMD=$cmd"
        }
    }
}
function Ensure-Core([string]$Core) {
    $v=Get-Json 'http://127.0.0.1:8797/api/version' 3
    if($v){return $v}
    $launcher=Join-Path $Core 'START-DMT-SECOND-BRAIN.ps1'; Assert-True (Test-Path -LiteralPath $launcher) "CORE_LAUNCHER_MISSING=$launcher"
    Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$launcher) -WorkingDirectory $Core | Out-Null
    $v=Wait-Json 'http://127.0.0.1:8797/api/version' 45
    Assert-True $v 'CORE_START_FAILED'; return $v
}
function Ensure-Studio([string]$Core) {
    $h=Get-Json 'http://127.0.0.1:8800/api/health' 3
    if($h){return $h}
    $tool=Join-Path $Core 'agape-document-studio\document_studio.py'; Assert-True (Test-Path -LiteralPath $tool) "DOCUMENT_STUDIO_TOOL_MISSING=$tool"
    $dataRoot=Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'DMT-CORE-V3.1\second-brain-data\document-studio'; New-Item -ItemType Directory -Path $dataRoot -Force|Out-Null
    Start-BackgroundPython -ProcessArgs @($tool,'--port','8800','--no-browser') -Out (Join-Path $dataRoot 'full-rebuild-stdout.log') -Err (Join-Path $dataRoot 'full-rebuild-stderr.log') | Out-Null
    $h=Wait-Json 'http://127.0.0.1:8800/api/health' 45; Assert-True $h 'DOCUMENT_STUDIO_START_FAILED'; return $h
}
function Ensure-WorkEngine([string]$Core) {
    $h=Get-Json 'http://127.0.0.1:8820/api/health' 3
    if($h){return $h}
    $launcher=Join-Path $Core 'OPEN-AGAPE-WORK-ENGINE.ps1'; Assert-True (Test-Path -LiteralPath $launcher) "WORK_ENGINE_LAUNCHER_MISSING=$launcher"
    Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$launcher,'-NoBrowser') -WorkingDirectory $Core | Out-Null
    $h=Wait-Json 'http://127.0.0.1:8820/api/health' 45; Assert-True $h 'WORK_ENGINE_START_FAILED'; return $h
}
function Refresh-Manifest([string]$Root) {
    $helper=@'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); p=root/'manifest.json'
m=json.loads(p.read_text(encoding='utf-8-sig'))
files={}
for f in sorted(root.iterdir(),key=lambda x:x.name.lower()):
    if f.is_file() and f.name!='manifest.json' and f.suffix.lower() in ('.py','.html','.md','.ps1'):
        files[f.name]=hashlib.sha256(f.read_bytes()).hexdigest().upper()
m['files']=files
features=list(m.get('features') or [])
for x in ['document-studio-r31.10','quotation-document-type','pptx-ingestion-list-slice-fix','unicode-section-normalisation','duplicate-aware-section-repair','full-physical-browser-release-gate']:
    if x not in features: features.append(x)
m['features']=features
m['installer_generation']='agape-v3.1-full-rebuild-r1.4'
p.write_text(json.dumps(m,indent=2,ensure_ascii=False),encoding='utf-8')
print('MANIFEST_REFRESH=PASS')
print('MANIFEST_FILE_COUNT='+str(len(files)))
'@
    $path=Join-Path $script:Stage 'refresh-manifest.py'; Write-Utf8 $path $helper
    $rc=Run-Python -ProcessArgs @($path,$Root) -LogPath (Join-Path $script:ReportRoot 'manifest-refresh.log')
    if($rc -ne 0){throw 'MANIFEST_REFRESH_FAILED'}
}
function Tree-Snapshot([string]$Root,[string]$Out) {
    # R1.4: Windows-safe, diagnostic snapshotter.  R1 used Path.rglob/read_bytes
    # with no per-file protection, so any long/reparse/transient path collapsed to
    # a generic TREE_SNAPSHOT_FAILED before candidate testing began.
    $helper=@'
import hashlib, json, os, sys, time, traceback
from pathlib import Path

root_raw=os.path.abspath(sys.argv[1])
out_raw=os.path.abspath(sys.argv[2])
excluded_dirs={'__pycache__','.git','.venv','node_modules'}
ignored_suffixes={'.pyc','.pyo','.log','.tmp','.lock'}
source_suffixes={
    '.py','.html','.htm','.js','.mjs','.cjs','.css','.md','.ps1','.psm1','.psd1',
    '.json','.toml','.yaml','.yml','.txt','.ini','.cfg','.sql'
}

def long_path(path):
    path=os.path.abspath(path)
    if os.name!='nt' or path.startswith('\\\\?\\'):
        return path
    if path.startswith('\\\\'):
        return '\\\\?\\UNC\\'+path[2:]
    return '\\\\?\\'+path

def is_junction(path):
    fn=getattr(os.path,'isjunction',None)
    try:
        return bool(fn and fn(path))
    except OSError:
        return False

def sha256_file(path):
    last=None
    for attempt in range(3):
        try:
            h=hashlib.sha256()
            with open(path,'rb') as f:
                while True:
                    chunk=f.read(1024*1024)
                    if not chunk: break
                    h.update(chunk)
            return h.hexdigest().upper()
        except OSError as e:
            last=e
            time.sleep(0.08*(attempt+1))
    raise last

root_scan=long_path(root_raw)
rows={}
errors=[]
stack=[root_scan]
while stack:
    current=stack.pop()
    try:
        entries=list(os.scandir(current))
    except OSError as e:
        errors.append({'path':current,'stage':'scandir','error':repr(e)})
        continue
    for ent in entries:
        try:
            if ent.is_dir(follow_symlinks=False):
                if ent.name in excluded_dirs or ent.is_symlink() or is_junction(ent.path):
                    continue
                stack.append(ent.path)
                continue
            if not ent.is_file(follow_symlinks=False):
                continue
            suffix=os.path.splitext(ent.name)[1].lower()
            if suffix in ignored_suffixes or suffix not in source_suffixes:
                continue
            rel=os.path.relpath(ent.path,root_scan).replace('\\','/')
            rows[rel]=sha256_file(ent.path)
        except OSError as e:
            errors.append({'path':getattr(ent,'path',current),'stage':'file','error':repr(e)})
        except Exception as e:
            errors.append({'path':getattr(ent,'path',current),'stage':'unexpected','error':repr(e),'trace':traceback.format_exc(limit=3)})

out=Path(out_raw)
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(rows,indent=2,sort_keys=True),encoding='utf-8')
print('SNAPSHOT_ROOT='+root_raw)
print('SNAPSHOT_FILES='+str(len(rows)))
if errors:
    err_path=out.with_suffix(out.suffix+'.errors.json')
    err_path.write_text(json.dumps(errors,indent=2,ensure_ascii=False),encoding='utf-8')
    print('SNAPSHOT_ERRORS='+str(len(errors)))
    print('SNAPSHOT_ERROR_FILE='+str(err_path))
    for item in errors[:12]:
        print('SNAPSHOT_ERROR='+json.dumps(item,ensure_ascii=False))
    raise SystemExit(8)
print('SNAPSHOT_ERRORS=0')
'@
    $path=Join-Path $script:Stage 'snapshot-tree.py'; Write-Utf8 $path $helper
    $log=Join-Path $script:ReportRoot ('snapshot-'+[IO.Path]::GetFileName($Out)+'.log')
    $rc=Run-Python -ProcessArgs @($path,$Root,$Out) -LogPath $log
    if($rc -ne 0){
        $detail=''
        try{$detail=(@(Get-Content -LiteralPath $log -Tail 18 -ErrorAction SilentlyContinue)-join ' | ')}catch{}
        throw ("TREE_SNAPSHOT_FAILED ROOT={0} LOG={1} DETAIL={2}" -f $Root,$log,$detail)
    }
    if(!(Test-Path -LiteralPath $Out -PathType Leaf)){throw "TREE_SNAPSHOT_OUTPUT_MISSING=$Out"}
}
function Compare-SnapshotExact([string]$Expected,[string]$Actual) {
    $helper=@'
import json,sys
exp=json.load(open(sys.argv[1],encoding='utf-8')); act=json.load(open(sys.argv[2],encoding='utf-8'))
keys=sorted(set(exp)|set(act))
changed=[k for k in keys if exp.get(k)!=act.get(k)]
print('EXACT_COMPARE_FILES='+str(len(keys)))
print('EXACT_COMPARE_CHANGED='+str(len(changed)))
if changed:
    for x in changed[:30]: print('EXACT_DIFF='+x)
    raise SystemExit(9)
'@
    $path=Join-Path $script:Stage 'compare-snapshot-exact.py'; Write-Utf8 $path $helper
    $log=Join-Path $script:ReportRoot 'candidate-copy-exact-compare.log'
    $rc=Run-Python -ProcessArgs @($path,$Expected,$Actual) -LogPath $log
    if($rc -ne 0){throw "CANDIDATE_COPY_NOT_EXACT SEE=$log"}
}
function Check-Allowed-Diff([string]$Before,[string]$After) {
    $helper=@'
import json,sys
b=json.load(open(sys.argv[1],encoding='utf-8')); a=json.load(open(sys.argv[2],encoding='utf-8'))
keys=sorted(set(b)|set(a)); changed=[k for k in keys if b.get(k)!=a.get(k)]
allowed={'index.html','agape-document-studio/document_studio.py','OPEN-AGAPE-DOCUMENT-STUDIO.ps1','agape-systems-engine/agape_systems_engine/app.py','agape-systems-engine/agape_systems_engine/__init__.py','manifest.json'}
unexpected=[k for k in changed if k not in allowed]
print('CHANGED='+','.join(changed)); print('UNEXPECTED='+','.join(unexpected))
if unexpected: raise SystemExit(9)
'@
    $path=Join-Path $script:Stage 'diff-tree.py'; Write-Utf8 $path $helper
    $rc=Run-Python -ProcessArgs @($path,$Before,$After) -LogPath (Join-Path $script:ReportRoot 'candidate-source-diff.log')
    if($rc -ne 0){throw 'CANDIDATE_UNEXPECTED_SOURCE_DIFF'}
}
function Ensure-Playwright {
    $old=$ErrorActionPreference;$ErrorActionPreference='Continue'; & $script:Python -c 'import playwright' *> $null; $rc=$LASTEXITCODE; $ErrorActionPreference=$old
    if($rc -ne 0){
        Say 'PLAYWRIGHT_PACKAGE' 'INSTALLING' 'Yellow'
        & $script:Python -m pip install --user playwright
        if($LASTEXITCODE -ne 0){throw 'PLAYWRIGHT_INSTALL_FAILED'}
    }
    Say 'PLAYWRIGHT_PACKAGE' 'PASS' 'Green'
}
function Run-PhysicalQA([string]$Mode,[string]$CoreUrl,[string]$StudioUrl,[string]$WorkUrl,[string]$CoreRoot,[string]$OutDir) {
    $qaArgs=@($script:QaPy,'--core',$CoreUrl,'--studio',$StudioUrl,'--work',$WorkUrl,'--core-root',$CoreRoot,'--out',$OutDir,'--mode',$Mode)
    $log=Join-Path $script:ReportRoot ("$Mode-physical-qa.log")
    $rc=Run-Python -ProcessArgs $qaArgs -LogPath $log
    if($rc -eq 10){
        Say 'PLAYWRIGHT_BROWSER' 'INSTALLING_CHROMIUM' 'Yellow'
        & $script:Python -m playwright install chromium
        if($LASTEXITCODE -ne 0){throw 'PLAYWRIGHT_CHROMIUM_INSTALL_FAILED'}
        $rc=Run-Python -ProcessArgs $qaArgs -LogPath $log
    }
    if($rc -ne 0){throw ("PHYSICAL_QA_${Mode}_FAILED_EXIT=$rc")}
    Say ("PHYSICAL_QA_"+$Mode.ToUpperInvariant()) 'PASS' 'Green'
}

$script:Python=Get-Python
$script:Core=Find-Core
$Docs=[Environment]::GetFolderPath('MyDocuments')
$Downloads=Join-Path $env:USERPROFILE 'Downloads'
$DataBase=Join-Path $Docs 'DMT-CORE-V3.1\second-brain-data'
$BackupRoot=Join-Path $DataBase 'release-backups'
$script:Stage=Join-Path $env:TEMP ("AGR14-$Stamp")
$Candidate=Join-Path $Stage 'candidate-core'
$CandidateCoreData=Join-Path $Stage 'candidate-core-data'
$CandidateStudioData=Join-Path $Stage 'candidate-document-studio-data'
$CandidateWorkData=Join-Path $Stage 'candidate-work-engine-data'
$script:ReportRoot=Join-Path $Downloads ("AGAPE-FULL-REBUILD-R1.6-RESULTS-$Stamp")
$BackupDir=Join-Path $BackupRoot ("before-full-rebuild-r1.6-$Stamp")
$OldSwap=$Core+'.pre-full-rebuild-'+$Stamp
$ReleaseZip=Join-Path $Downloads ("AGAPE-V3.1-R8-FULL-REBUILD-R1.6-SOURCE-$Stamp.zip")
$ResultPath=Join-Path $Downloads ("AGAPE-FULL-REBUILD-R1.6-RESULT-$Stamp.json")
foreach($d in @($Stage,$ReportRoot,$BackupRoot,$BackupDir,$CandidateCoreData,$CandidateStudioData,$CandidateWorkData)){New-Item -ItemType Directory -Path $d -Force|Out-Null}

$script:PatcherPy=Join-Path $Stage 'patch-r31.10.py'
$script:CoreUiPatcherPy=Join-Path $Stage 'patch-r8-core-ui-r1.6.py'
$script:WorkEnginePatcherPy=Join-Path $Stage 'patch-work-engine-r1.3.py'
$script:QaPy=Join-Path $Stage 'physical-qa.py'
$script:RegressionPy=Join-Path $Stage 'r31.10-regression.py'

Write-Utf8 $CoreUiPatcherPy @'
from pathlib import Path
import re, sys
p=Path(sys.argv[1])
text=p.read_text(encoding='utf-8-sig')
marker='<!-- AGAPE_R16_CORE_UI_COMPAT_BEGIN -->'
required=('data-page="chat"','data-page="settings"','id="workspace-manage-projects"','id="project-instructions-text"')
missing=[x for x in required if x not in text]
if missing: raise SystemExit('R8_NATIVE_UI_MARKERS_MISSING='+','.join(missing))

# R1.6: protect direct lookup.onclick assignments anywhere in compact scripts.
patterns=[
 (re.compile(r"\$\((?P<q>['\"])(?P<id>[^'\"]+)(?P=q)\)\s*\.onclick\s*="),lambda m:"($(%s%s%s)||{}).onclick="%(m.group('q'),m.group('id'),m.group('q'))),
 (re.compile(r"document\.getElementById\((?P<q>['\"])(?P<id>[^'\"]+)(?P=q)\)\s*\.onclick\s*="),lambda m:"(document.getElementById(%s%s%s)||{}).onclick="%(m.group('q'),m.group('id'),m.group('q'))),
 (re.compile(r"document\.querySelector\((?P<q>['\"])(?P<sel>[^'\"]+)(?P=q)\)\s*\.onclick\s*="),lambda m:"(document.querySelector(%s%s%s)||{}).onclick="%(m.group('q'),m.group('sel'),m.group('q'))),
]
counts=[]
for pat,fn in patterns:
 text,n=pat.subn(fn,text);counts.append(n)
# Also guard simple cached-node variable assignments at statement starts.
var_pat=re.compile(r'(?m)(?P<i>(?:^|[;{}])[ \t]*)(?P<v>[A-Za-z_$][A-Za-z0-9_$]*)\s*\.onclick\s*=')
def vr(m):
 v=m.group('v')
 return m.group(0) if v in ('this','window','document') else f"{m.group('i')}if({v}) {v}.onclick="
text,var_count=var_pat.subn(vr,text)
# Direct lookup.onclick must be gone.
checks=[r"\$\(['\"][^'\"]+['\"]\)\s*\.onclick\s*=",r"document\.getElementById\(['\"][^'\"]+['\"]\)\s*\.onclick\s*=",r"document\.querySelector\(['\"][^'\"]+['\"]\)\s*\.onclick\s*="]
left=sum(len(re.findall(x,text)) for x in checks)
if left: raise SystemExit('UNSAFE_DIRECT_ONCLICK_REMAINS='+str(left))
if marker not in text:
 pos=text.lower().rfind('</body>')
 if pos<0: raise SystemExit('CORE_UI_BODY_END_NOT_FOUND')
 note='\n'+marker+'\n<!-- Native R8 navigation retained; null-safe DOM onclick compatibility guard R1.6. -->\n<!-- AGAPE_R16_CORE_UI_COMPAT_END -->\n'
 text=text[:pos]+note+text[pos:]
p.write_text(text,encoding='utf-8')
print('CORE_UI_PATCH=PASS')
print('CORE_UI_DIRECT_DOLLAR_GUARDS='+str(counts[0]))
print('CORE_UI_GETELEMENT_GUARDS='+str(counts[1]))
print('CORE_UI_QUERYSELECTOR_GUARDS='+str(counts[2]))
print('CORE_UI_VARIABLE_GUARDS='+str(var_count))
print('CORE_UI_UNSAFE_DIRECT_ONCLICK=0')
print('CORE_UI_NATIVE_NAV=PROJECT_WORKSPACE_SETTINGS')
'@

Write-Utf8 $WorkEnginePatcherPy @'
from pathlib import Path
import sys
app=Path(sys.argv[1]); init=Path(sys.argv[2])
text=app.read_text(encoding='utf-8-sig'); init_text=init.read_text(encoding='utf-8-sig')
if "version':'R1.3'" in text and 'refreshSchedules' in text:
 print('WORK_ENGINE_PATCH=ALREADY_R1_3'); raise SystemExit(0)
if "version':'R1.1'" not in text and "version':'R1.2'" not in text: raise SystemExit('UNEXPECTED_WORK_ENGINE_VERSION')
needle="if u.path=='/api/status':return jsend(self,200,RUNTIME.status())"
route="if u.path=='/api/schedules':return jsend(self,200,{'schedules':RUNTIME.scheduler.list()})"
if route not in text:
 if needle not in text: raise SystemExit('STATUS_GET_ROUTE_NOT_FOUND')
 text=text.replace(needle,needle+'\n            '+route,1)
start=text.find('async function addSchedule()')
if start<0: raise SystemExit('ADD_SCHEDULE_FUNCTION_NOT_FOUND')
end=text.find('\nasync function',start+1)
if end<0: end=text.find('</script>',start+1)
if end<0: raise SystemExit('ADD_SCHEDULE_FUNCTION_END_NOT_FOUND')
new_js='''async function refreshSchedules(){let s=await api('/api/schedules');let rows=(s&&s.schedules)||[];$('schedules').innerHTML=rows.map(x=>`<tr data-schedule-id="${x.id}"><td>${x.name}</td><td>${x.schedule_type}:${x.schedule_value}</td><td>${new Date((x.next_run_at||0)*1000).toLocaleString()}</td></tr>`).join('');return rows}
async function addSchedule(){let created=await api('/api/schedules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'Service health every 15 minutes',kind:'service_health',payload:{recover:true},schedule_type:'interval',schedule_value:'900'})});let sid=created.schedule_id||'';for(let i=0;i<40;i++){let rows=await refreshSchedules();if(rows.some(x=>x.id===sid))return created;await new Promise(r=>setTimeout(r,100))}throw new Error('SCHEDULE_NOT_VISIBLE_AFTER_CREATE='+sid)}'''
text=text[:start]+new_js+text[end:]
old_tab="function tab(id){document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));$(id).classList.add('active');refresh()}"
new_tab="function tab(id){document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));$(id).classList.add('active');if(id==='schedule')refreshSchedules();else refresh()}"
if old_tab in text: text=text.replace(old_tab,new_tab,1)
elif new_tab not in text: raise SystemExit('TAB_FUNCTION_PATTERN_NOT_FOUND')
for a in ('R1.1','R1.2'):
 text=text.replace('Agape Work Engine '+a,'Agape Work Engine R1.3').replace("'version':'"+a+"'","'version':'R1.3'").replace("__version__ = '"+a+"'","__version__ = 'R1.3'")
 init_text=init_text.replace("__version__ = '"+a+"'","__version__ = 'R1.3'")
if '# AGAPE_R1_3_SCHEDULE_DECOUPLE_FIX' not in text: text=text.replace('from __future__ import annotations\n','from __future__ import annotations\n# AGAPE_R1_3_SCHEDULE_DECOUPLE_FIX\n',1)
req=["version':'R1.3'",'async function refreshSchedules()','SCHEDULE_NOT_VISIBLE_AFTER_CREATE',route]
miss=[x for x in req if x not in text]
if miss: raise SystemExit('WORK_ENGINE_R13_PATCH_INCOMPLETE='+','.join(miss))
if "__version__ = 'R1.3'" not in init_text: raise SystemExit('WORK_ENGINE_INIT_VERSION_BUMP_FAILED')
app.write_text(text,encoding='utf-8');init.write_text(init_text,encoding='utf-8')
print('WORK_ENGINE_PATCH=PASS')
print('WORK_ENGINE_VERSION=R1.3')
print('SCHEDULE_GET_ENDPOINT=PASS')
print('SCHEDULE_RENDER_DECOUPLED_FROM_STATUS=PASS')
'@

Write-Utf8 $PatcherPy @'
from pathlib import Path
import re, sys, json

p = Path(sys.argv[1])
text = p.read_text(encoding='utf-8-sig')

if 'VERSION = "R31.10"' in text:
    print('DOCUMENT_STUDIO_PATCH=ALREADY_R31_10')
    raise SystemExit(0)
if 'VERSION = "R31.9"' not in text:
    raise SystemExit('UNEXPECTED_DOCUMENT_STUDIO_VERSION')

# Keep changes deliberately narrow and regression-testable.
text = text.replace('VERSION = "R31.9"', 'VERSION = "R31.10"', 1)
text = text.replace('Agape Document Studio R31.9', 'Agape Document Studio R31.10')
text = text.replace('AGAPE_DOCUMENT_STUDIO_R31_9=READY', 'AGAPE_DOCUMENT_STUDIO_R31_10=READY')

marker = '# AGAPE_R31_10_RELIABILITY_FIXES_BEGIN'
if marker in text:
    raise SystemExit('R31_10_MARKER_PRESENT_WITH_R31_9_VERSION')

insert_at = text.find('\ndef serve(port,open_browser=True):')
if insert_at < 0:
    raise SystemExit('SERVE_INSERT_POINT_NOT_FOUND')

override = r'''
# AGAPE_R31_10_RELIABILITY_FIXES_BEGIN
# Promoted from the R2.1 side-load regression work only after isolated testing.
# Scope: Quotation type, PPTX ingestion, section normalization/validation,
# and replacement (not duplication) of repaired weak sections.

QUOTATION_HEADINGS = [
    "Quotation",
    "Customer and Project",
    "Scope of Works",
    "Flooring Areas",
    "Pricing",
    "Programme and Timescale",
    "Payment Terms",
    "Quotation Validity",
    "Acceptance",
]
WRITER_TYPES["Quotation"] = list(QUOTATION_HEADINGS)
APP_TYPES["writer"] = list(WRITER_TYPES.keys())

_R310_ORIGINAL_EXTRACT_INSTRUCTION = _extract_instruction_document

def _r310_display_text(value):
    s = unicodedata.normalize("NFKC", str(value or ""))
    replacements = {
        "\u252c\u00fa": "\u00a3", "\u00c2\u00a3": "\u00a3", "\u00c2\u20ac": "\u20ac",
        "\u00e2\u20ac\u201c": "-", "\u00e2\u20ac\u201d": "-", "\u00e2\u20ac\u02dc": "'", "\u00e2\u20ac\u2122": "'", "\u00e2\u20ac\u0153": '"',
    }
    for bad, good in replacements.items():
        s = s.replace(bad, good)
    return s

def _r310_heading_key(value):
    s = _r310_display_text(value)
    try:
        s = clean_inline(s)
    except Exception:
        pass
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s).casefold()).strip()

def _r310_section_heading(value):
    if isinstance(value, dict):
        for key in ("heading", "title", "name", "section"):
            raw = value.get(key)
            if raw is not None and str(raw).strip():
                return _r310_display_text(raw).strip()
        return ""
    raw = _r310_display_text(value).strip()
    if raw.startswith("{") and raw.endswith("}"):
        try:
            import ast
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, dict):
                return _r310_section_heading(parsed)
        except Exception:
            pass
    return raw

def _r310_normalise_sections(values):
    if values is None:
        return []
    if isinstance(values, (str, dict)):
        values = [values]
    out, seen = [], set()
    for value in values:
        heading = _r310_section_heading(value)
        key = _r310_heading_key(heading)
        if heading and key and key not in seen:
            out.append(heading)
            seen.add(key)
    return out

def _extract_instruction_document(path, max_chars=250000):
    path = Path(path)
    if path.suffix.lower() != ".pptx":
        return _R310_ORIGINAL_EXTRACT_INSTRUCTION(path, max_chars)
    parts = []
    prs = Presentation(str(path))
    for idx, slide in enumerate(list(prs.slides)[:120], 1):
        parts.append(f"# SLIDE {idx}")
        for shape in slide.shapes:
            if hasattr(shape, "text") and str(shape.text).strip():
                parts.append(str(shape.text))
    return clean_text("\n".join(parts))[:max_chars]

def _required_sections(plan):
    sections = _r310_normalise_sections((plan or {}).get("required_sections") or [])
    if (plan or {}).get("doc_type") == "Business Proposal":
        existing = {_r310_heading_key(x) for x in sections}
        for h in REQUIRED_PROPOSAL_HEADINGS:
            if _r310_heading_key(h) not in existing:
                sections.append(h)
                existing.add(_r310_heading_key(h))
    return sections or ["Overview", "Findings", "Recommendations"]

def parse_headings(content):
    return [_r310_display_text(clean_inline(m.group(1))) for m in re.finditer(r"(?m)^#{1,3}\s+(.+?)\s*$", str(content or ""))]

def _r310_min_section_chars(doc_type, heading):
    key = _r310_heading_key(heading)
    compact = (
        "quotation validity", "proposal validity", "validity", "payment terms",
        "commercial terms", "pricing", "price", "subtotal", "total", "vat",
        "flooring areas", "areas", "acceptance", "signature", "decision requested",
    )
    if any(x in key for x in compact):
        return 8
    if doc_type == "Quotation":
        return 35
    if doc_type in ("Business Letter", "Meeting Minutes"):
        return 40
    if doc_type == "Project Plan":
        return 70
    if doc_type in ("Business Proposal", "Business Report", "Technical Report"):
        return 120
    return 80

def validate_generated_document(doc_type, content, required_sections):
    required = _r310_normalise_sections(required_sections)
    heads = parse_headings(content)
    found_keys = {_r310_heading_key(x) for x in heads}
    missing = [h for h in required if _r310_heading_key(h) not in found_keys]
    bodies = {}
    blocks = re.split(r"(?m)^#{1,3}\s+", str(content or ""))[1:]
    for block in blocks:
        lines = block.splitlines()
        heading = _r310_display_text(clean_inline(lines[0]) if lines else "")
        body = "\n".join(lines[1:]).strip()
        key = _r310_heading_key(heading)
        if key and (key not in bodies or len(body) > len(bodies[key])):
            bodies[key] = body
    short = []
    for h in required:
        key = _r310_heading_key(h)
        if key in found_keys and len(bodies.get(key, "")) < _r310_min_section_chars(doc_type, h):
            short.append(h)
    return {"ok": not missing and not short, "headings": heads, "missing": missing, "short": short, "chars": len(str(content or ""))}

def _r310_markdown_blocks(text):
    return list(re.finditer(r"(?ms)^(#{1,3})\s+(.+?)\s*\n(.*?)(?=^#{1,3}\s+|\Z)", str(text or "")))

def _merge_repaired_sections(draft, patch, targets):
    target_keys = {_r310_heading_key(x) for x in targets}
    patch_map = {}
    for match in _r310_markdown_blocks(patch):
        heading = _r310_display_text(match.group(2)).strip()
        key = _r310_heading_key(heading)
        if key in target_keys:
            patch_map[key] = "# " + heading + "\n" + match.group(3).strip()
    if not patch_map:
        return draft
    matches = _r310_markdown_blocks(draft)
    if not matches:
        return draft.rstrip() + "\n\n" + "\n\n".join(patch_map.values())
    prefix = draft[:matches[0].start()].rstrip()
    out = [prefix] if prefix else []
    used = set()
    for match in matches:
        heading = _r310_display_text(match.group(2)).strip()
        key = _r310_heading_key(heading)
        if key in patch_map:
            if key not in used:
                out.append(patch_map[key]); used.add(key)
            continue
        out.append(match.group(0).strip())
    for key, block in patch_map.items():
        if key not in used:
            out.append(block)
    return "\n\n".join(x for x in out if x).strip()

def repair_draft(ctx, plan, research, draft, requested_model="auto", max_rounds=2):
    sections = _required_sections(plan); models = []
    for round_index in range(max(1, int(max_rounds))):
        audit = validate_generated_document(plan.get("doc_type"), draft, sections)
        needs = []
        seen = set()
        for h in audit.get("missing", []) + audit.get("short", []):
            key = _r310_heading_key(h)
            if key and key not in seen:
                needs.append(h); seen.add(key)
        if not needs:
            return draft, audit, models
        system = (
            "You repair professional documents. Return only the exact missing or weak sections requested, "
            "each starting with an exact # heading. Replace weak sections with substantive content. "
            "Use provided facts and research only. Do not invent facts."
        )
        prompt = (
            "FORM_STATE:\n" + json.dumps(_ai_context_snapshot(ctx, 0, 32, False), ensure_ascii=False)
            + "\nPLAN:\n" + json.dumps(plan, ensure_ascii=False)
            + "\nRESEARCH:\n" + _research_for_prompt(research, 9000)
            + "\nCURRENT_DOCUMENT:\n" + draft[-14000:]
            + "\n\nREWRITE THESE SECTIONS COMPLETELY:\n"
            + "\n".join("# " + x for x in needs)
        )
        r = ai_generate(prompt, system, max_tokens=2400, requested_model=requested_model, timeout=240, task="repair")
        patch = str(r.get("content") or "").strip()
        models.append({"provider": r.get("provider"), "model": r.get("model"), "round": round_index + 1})
        draft = _merge_repaired_sections(draft, patch, needs)
    return draft, validate_generated_document(plan.get("doc_type"), draft, sections), models

# AGAPE_R31_10_RELIABILITY_FIXES_END
'''

text = text[:insert_at] + '\n' + override + text[insert_at:]
p.write_text(text, encoding='utf-8')
print('DOCUMENT_STUDIO_PATCH=PASS')
print('DOCUMENT_STUDIO_VERSION=R31.10')
'@
Write-Utf8 $QaPy @'
from __future__ import annotations
import argparse, json, re, sys, time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--core', required=True)
    ap.add_argument('--studio', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--core-root', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--mode', choices=['candidate','live'], default='candidate')
    a=ap.parse_args()
    out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    results=[]; failures=[]; notes=[]

    def rec(surface,name,status,detail=''):
        row={'surface':surface,'name':name,'status':status,'detail':str(detail)[:1200]}
        results.append(row)
        print(f"QA|{surface}|{name}|{status}|{detail}", flush=True)
        if status=='FAIL': failures.append(row)

    def screenshot(page,name):
        try: page.screenshot(path=str(out/name),full_page=True)
        except Exception as e: notes.append(f'screenshot {name}: {e}')

    with sync_playwright() as p:
        browser=None
        errors=[]
        for launch in (
            lambda: p.chromium.launch(channel='chrome',headless=True),
            lambda: p.chromium.launch(headless=True),
        ):
            try:
                browser=launch();break
            except Exception as e: errors.append(str(e))
        if browser is None:
            print(json.dumps({'overall':'FAIL','error':'BROWSER_LAUNCH_FAILED','details':errors},indent=2))
            return 10

        context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=False)

        # ---------------- CORE ----------------
        page=context.new_page(); page_errors=[]; page.on('pageerror',lambda e: page_errors.append(str(e)))
        try:
            r=page.goto(a.core,wait_until='domcontentloaded',timeout=30000)
            rec('Core','page_load','PASS' if r and r.ok else 'FAIL', getattr(r,'status',None))
            page.wait_for_timeout(900)
            body=page.locator('body').inner_text(timeout=5000)
            rec('Core','nonempty_ui','PASS' if len(body.strip())>50 else 'FAIL',f'chars={len(body)}')
            # Check that the repaired project information textarea is genuinely editable by a user.
            box=page.locator('#project-instructions-text')
            if box.count()==0:
                rec('Core','project_information_textarea','FAIL','selector missing')
            else:
                if not box.is_visible():
                    for sel in ('button[data-page=\"chat\"]','#workspace-manage-projects'):
                        try:
                            loc=page.locator(sel)
                            if loc.count() and loc.first.is_visible(): loc.first.click(timeout=4000); page.wait_for_timeout(400)
                        except Exception: pass
                    for pattern in ('Create Project','New Project','Project Information'):
                        try:
                            loc=page.get_by_role('button',name=re.compile(pattern,re.I))
                            if loc.count() and loc.first.is_visible(): loc.first.click(timeout=4000); page.wait_for_timeout(400); break
                        except Exception: pass
                try:
                    box.scroll_into_view_if_needed(timeout=3000)
                    box.click(timeout=5000)
                    test_text='AGAPE PHYSICAL FORM TEST - editable project instructions'
                    box.fill(test_text,timeout=5000)
                    val=box.input_value()
                    editable=box.is_enabled() and box.get_attribute('readonly') is None
                    rec('Core','project_information_textarea','PASS' if val==test_text and editable else 'FAIL',f'editable={editable} value={val[:80]}')
                except Exception as e:
                    rec('Core','project_information_textarea','FAIL',e)
            # R1.4: exercise the native R8 navigation, not historical dmtc-* controls
            # from older pre-R8 UI experiments.  Each click must produce the expected
            # visible DOM state, not merely dispatch a click event.
            clicked=0
            try:
                b=page.locator('button[data-page="chat"]')
                b.wait_for(state='visible',timeout=5000); b.click(timeout=5000); page.wait_for_timeout(150)
                active='active' in (page.locator('#page-chat').get_attribute('class') or '')
                rec('Core','nav_project_workspace','PASS' if active else 'FAIL','native R8 physical click')
                if active: clicked+=1
            except Exception as e: rec('Core','nav_project_workspace','FAIL',e)
            try:
                b=page.locator('button[data-page="settings"]')
                b.wait_for(state='visible',timeout=5000); b.click(timeout=5000); page.wait_for_timeout(150)
                active='active' in (page.locator('#page-settings').get_attribute('class') or '')
                rec('Core','nav_settings','PASS' if active else 'FAIL','native R8 physical click')
                if active: clicked+=1
            except Exception as e: rec('Core','nav_settings','FAIL',e)
            try:
                b=page.locator('.settings-nav button[data-setting="general"]')
                b.wait_for(state='visible',timeout=5000); b.click(timeout=5000); page.wait_for_timeout(120)
                active='active' in (page.locator('#settings-general').get_attribute('class') or '')
                rec('Core','settings_general_button','PASS' if active else 'FAIL','native R8 physical click')
                if active: clicked+=1
            except Exception as e: rec('Core','settings_general_button','FAIL',e)
            try:
                page.locator('button[data-page="chat"]').click(timeout=5000); page.wait_for_timeout(120)
                b=page.locator('#workspace-manage-projects')
                b.wait_for(state='visible',timeout=5000); b.click(timeout=5000)
                # R8 moves #page-projects into Settings during startup and renames it
                # #settings-projects.  Wait for the semantic state rather than assuming
                # the rename has happened at a fixed millisecond after the click.
                page.wait_for_function("""()=>{
                    const settings=document.querySelector('#page-settings');
                    const btn=document.querySelector('.settings-nav [data-setting=\"projects\"]');
                    const panel=[...document.querySelectorAll('.settings-panel')].find(p=>p.classList.contains('active')&&/project/i.test(p.id||''));
                    return !!(settings&&settings.classList.contains('active')&&btn&&btn.classList.contains('active')&&panel);
                }""",timeout=10000)
                state=page.evaluate("""()=>{const settings=document.querySelector('#page-settings');const btn=document.querySelector('.settings-nav [data-setting=\"projects\"]');const p=[...document.querySelectorAll('.settings-panel')].find(x=>x.classList.contains('active')&&/project/i.test(x.id||''));return {settings:!!(settings&&settings.classList.contains('active')),button:!!(btn&&btn.classList.contains('active')),panel:p?p.id:''}}""")
                rec('Core','manage_projects_button','PASS',f'state={state}')
                clicked+=1
            except Exception as e: rec('Core','manage_projects_button','FAIL',e)
            rec('Core','native_navigation_click_count','PASS' if clicked>=4 else 'FAIL',f'clicked={clicked}/4')
            low=body.casefold()
            typo=any(x in low for x in ('creat project','create porject','crate project'))
            rec('Core','create_project_spelling','PASS' if not typo else 'FAIL','no known misspelling' if not typo else 'misspelling found')
            screenshot(page,f'{a.mode}-core.png')
        except Exception as e:
            rec('Core','unhandled','FAIL',e); screenshot(page,f'{a.mode}-core-fail.png')
        if page_errors: rec('Core','page_errors','FAIL',' | '.join(page_errors[:10]))
        else: rec('Core','page_errors','PASS','0')
        page.close()

        # ---------------- DOCUMENT STUDIO ----------------
        page=context.new_page(); page_errors=[]; page.on('pageerror',lambda e: page_errors.append(str(e)))
        try:
            r=page.goto(a.studio,wait_until='domcontentloaded',timeout=30000)
            rec('DocumentStudio','page_load','PASS' if r and r.ok else 'FAIL',getattr(r,'status',None))
            page.wait_for_timeout(300)
            # Wait for the real startup refresh to finish.  Template discovery can scan
            # LibreOffice/user roots and legitimately take longer than the old fixed 1.2s.
            try:
                page.wait_for_function("""()=>{
                    const t=document.getElementById('template');
                    const err=document.getElementById('formRuntimeError');
                    return (t&&t.options&&t.options.length>0) || (err&&getComputedStyle(err).display!=='none'&&err.innerText.trim().length>0);
                }""",timeout=30000)
            except Exception:
                pass
            init_error=''
            try:
                err=page.locator('#formRuntimeError')
                if err.count() and err.is_visible(): init_error=err.inner_text().strip()
            except Exception: pass
            template_count=page.locator('#template option').count()
            rec('DocumentStudio','startup_templates','PASS' if template_count>0 else 'FAIL',f'templates={template_count} init_error={init_error[:300]}')
            # Every primary tab is physically clicked and must activate its matching panel.
            # Scope selectors to the tab bar and prefer stable IDs.  The Make new tab can
            # receive a CSS ::after missing-field badge (for example a missing-count badge), which
            # changes its accessible name and made exact role-name matching flaky.
            tabs=[
                ('#createTabBtn','Make new','create'),
                ('#recentTabBtn','Recent documents','recent'),
                (None,'Templates','templates'),
                (None,'History','history'),
                (None,'Open-source sources','sources'),
                ('#settingsTabBtn','Settings','settings'),
            ]
            tab_bar=page.locator('.tabs')
            for selector,label,panel in tabs:
                try:
                    if selector:
                        b=page.locator(selector)
                    else:
                        b=tab_bar.get_by_role('button',name=label,exact=False)
                    b.first.wait_for(state='visible',timeout=8000)
                    b.first.click(timeout=5000); page.wait_for_timeout(250)
                    active='active' in (page.locator('#'+panel).get_attribute('class') or '')
                    rec('DocumentStudio','tab_'+panel,'PASS' if active else 'FAIL','physical click')
                except Exception as e: rec('DocumentStudio','tab_'+panel,'FAIL',e)
            try:
                make_new=page.locator('#createTabBtn')
                make_new.wait_for(state='visible',timeout=8000)
                make_new.click(timeout=5000); page.wait_for_timeout(300)
                active='active' in (page.locator('#create').get_attribute('class') or '')
                rec('DocumentStudio','return_make_new','PASS' if active else 'FAIL','stable #createTabBtn physical click')
            except Exception as e:
                labels=[]
                try: labels=page.locator('.tabs button').all_inner_texts()
                except Exception: pass
                rec('DocumentStudio','return_make_new','FAIL',f'{e}; tabs={labels}')
                raise
            fields={
                '#title':'Physical QA Document', '#content':'Physical QA instructions. Do not send or publish.',
                '#sf_organisation':'M6 Flooring QA', '#sf_recipient':'QA Recipient', '#filename':'agape-physical-qa'
            }
            for sel,val in fields.items():
                try:
                    loc=page.locator(sel); loc.click(timeout=3000); loc.fill(val,timeout=3000)
                    rec('DocumentStudio','form_'+sel[1:],'PASS' if loc.input_value()==val else 'FAIL','typed via Playwright')
                except Exception as e: rec('DocumentStudio','form_'+sel[1:],'FAIL',e)
            # A blocked Create is a safe physical submit test: incomplete 17-field form must refuse creation.
            try:
                page.get_by_role('button',name='Create from completed AI form',exact=True).click(timeout=5000)
                page.wait_for_timeout(400)
                txt=page.locator('#createResult').inner_text(timeout=3000)
                rec('DocumentStudio','create_validation_button','PASS' if 'Cannot create yet' in txt else 'FAIL',txt[:250])
            except Exception as e: rec('DocumentStudio','create_validation_button','FAIL',e)
            # Cost/credential-bearing controls are verified actionable but deliberately not executed.
            for sel,name in [('#completeFullFormBtn','best_ai_button'),('#startMultiReviewBtn','multi_ai_review_button')]:
                try:
                    loc=page.locator(sel)
                    ok=loc.count()>0 and loc.is_visible() and loc.is_enabled()
                    rec('DocumentStudio',name,'PASS' if ok else 'FAIL','actionable; execution intentionally blocked by release QA policy')
                except Exception as e: rec('DocumentStudio',name,'FAIL',e)
            if a.mode=='candidate':
                # Real source upload against isolated candidate data.
                fixture=out/'qa-instructions.txt'; fixture.write_text('AGAPE QA source upload\nNo secrets.\n',encoding='utf-8')
                try:
                    page.locator('#instructionUploadInput').set_input_files(str(fixture))
                    page.wait_for_function("document.getElementById('instructionUploadList').innerText.indexOf('qa-instructions.txt')>=0",timeout=15000)
                    rec('DocumentStudio','instruction_upload','PASS','physical file upload')
                except Exception as e: rec('DocumentStudio','instruction_upload','FAIL',e)
                # Preview uses the real selected template + LibreOffice path but isolated candidate data.
                try:
                    sel=page.locator('#template')
                    page.wait_for_function("document.querySelectorAll('#template option').length>0",timeout=30000)
                    count=sel.locator('option').count()
                    if count<1:
                        raise RuntimeError('template discovery completed with zero options')
                    # Keep current auto-selected template when possible.
                    page.get_by_role('button',name='Preview selected template',exact=True).click(timeout=5000)
                    page.wait_for_function("getComputedStyle(document.getElementById('templatePreviewModal')).display!='none'",timeout=90000)
                    src=page.locator('#templatePreviewFrame').get_attribute('src') or ''
                    rec('DocumentStudio','template_preview_button','PASS' if 'template-preview' in src else 'FAIL',src[:240])
                    page.get_by_role('button',name='Close',exact=True).click(timeout=5000)
                    rec('DocumentStudio','template_preview_close','PASS','physical click')
                except Exception as e: rec('DocumentStudio','template_preview_button','FAIL',e)
            screenshot(page,f'{a.mode}-document-studio.png')
        except Exception as e:
            rec('DocumentStudio','unhandled','FAIL',e); screenshot(page,f'{a.mode}-document-studio-fail.png')
        if page_errors: rec('DocumentStudio','page_errors','FAIL',' | '.join(page_errors[:10]))
        else: rec('DocumentStudio','page_errors','PASS','0')
        page.close()

        # ---------------- WORK ENGINE ----------------
        page=context.new_page(); page_errors=[]; page.on('pageerror',lambda e: page_errors.append(str(e)))
        try:
            r=page.goto(a.work,wait_until='domcontentloaded',timeout=30000)
            rec('WorkEngine','page_load','PASS' if r and r.ok else 'FAIL',getattr(r,'status',None)); page.wait_for_timeout(700)
            tabs=[('Work Queue','work'),('Schedules','schedule'),('Code Intelligence','code'),('Providers','providers'),('Plugins','plugins'),('Services','services'),('Flight Recorder','events')]
            for label,panel in tabs:
                try:
                    page.get_by_role('button',name=label,exact=True).click(timeout=4000); page.wait_for_timeout(180)
                    active='active' in (page.locator('#'+panel).get_attribute('class') or '')
                    rec('WorkEngine','tab_'+panel,'PASS' if active else 'FAIL','physical click')
                except Exception as e: rec('WorkEngine','tab_'+panel,'FAIL',e)
            page.get_by_role('button',name='Work Queue',exact=True).click(timeout=4000)
            page.locator('#jobKind').select_option(label='sleep_test')
            page.locator('#jobPriority').fill('77')
            page.locator('#jobPayload').fill('{"seconds":1,"steps":5}')
            try:
                with page.expect_response(lambda x: x.url.rstrip('/').endswith('/api/jobs') and x.request.method=='POST',timeout=8000) as info:
                    page.get_by_role('button',name='Add to queue',exact=True).click(timeout=4000)
                jid=info.value.json()['job_id']
                row=page.locator(f"#jobs tr:has-text('{jid}')")
                row.wait_for(state='visible',timeout=8000)
                deadline=time.time()+15; state=''
                while time.time()<deadline:
                    txt=row.inner_text();
                    if 'PASS' in txt: state='PASS';break
                    if 'FAIL' in txt: state='FAIL';break
                    page.wait_for_timeout(350)
                rec('WorkEngine','queue_add_and_execute','PASS' if state=='PASS' else 'FAIL',f'job={jid} state={state or row.inner_text()}')
            except Exception as e: rec('WorkEngine','queue_add_and_execute','FAIL',e)
            if a.mode=='candidate':
                # Pause/resume is tested only on isolated candidate data.
                page.locator('#jobPayload').fill('{"seconds":4,"steps":20}')
                try:
                    with page.expect_response(lambda x: x.url.rstrip('/').endswith('/api/jobs') and x.request.method=='POST',timeout=8000) as info:
                        page.get_by_role('button',name='Add to queue',exact=True).click(timeout=4000)
                    jid=info.value.json()['job_id']; row=page.locator(f"#jobs tr:has-text('{jid}')"); row.wait_for(state='visible',timeout=8000)
                    page.wait_for_timeout(500)
                    row.get_by_role('button',name='Pause',exact=True).click(timeout=4000); page.wait_for_timeout(500)
                    paused='PAUSED' in row.inner_text()
                    rec('WorkEngine','queue_pause','PASS' if paused else 'FAIL',row.inner_text())
                    row.get_by_role('button',name='Resume',exact=True).click(timeout=4000)
                    deadline=time.time()+15; passed=False
                    while time.time()<deadline:
                        if 'PASS' in row.inner_text(): passed=True;break
                        page.wait_for_timeout(350)
                    rec('WorkEngine','queue_resume','PASS' if passed else 'FAIL',row.inner_text())
                except Exception as e: rec('WorkEngine','queue_pause_resume','FAIL',e)
            # Code intelligence physical form + buttons.
            page.get_by_role('button',name='Code Intelligence',exact=True).click(timeout=4000)
            page.locator('#codeRoot').fill(a.core_root)
            page.locator('#codeQuery').fill('provider failover')
            try:
                page.get_by_role('button',name='Index changed files',exact=True).click(timeout=4000)
                page.wait_for_function("document.getElementById('codeOut').innerText.length>10",timeout=30000)
                rec('WorkEngine','code_index_button','PASS',page.locator('#codeOut').inner_text()[:220])
                page.get_by_role('button',name='Search',exact=True).click(timeout=4000); page.wait_for_timeout(500)
                rec('WorkEngine','code_search_button','PASS' if len(page.locator('#codeOut').inner_text())>10 else 'FAIL',page.locator('#codeOut').inner_text()[:220])
                page.get_by_role('button',name='Build Context Pack',exact=True).click(timeout=4000); page.wait_for_timeout(500)
                rec('WorkEngine','context_pack_button','PASS' if len(page.locator('#codeOut').inner_text())>10 else 'FAIL',page.locator('#codeOut').inner_text()[:220])
            except Exception as e: rec('WorkEngine','code_intelligence_buttons','FAIL',e)
            page.get_by_role('button',name='Services',exact=True).click(timeout=4000)
            try:
                page.get_by_role('button',name='Check expected services',exact=True).click(timeout=4000)
                page.wait_for_function("document.getElementById('serviceOut').innerText.length>10",timeout=12000)
                rec('WorkEngine','service_check_button','PASS',page.locator('#serviceOut').inner_text()[:220])
            except Exception as e: rec('WorkEngine','service_check_button','FAIL',e)
            if a.mode=='candidate':
                page.get_by_role('button',name='Schedules',exact=True).click(timeout=4000)
                try:
                    before=page.locator('#schedules tr').count()
                    with page.expect_response(lambda x: x.url.rstrip('/').endswith('/api/schedules') and x.request.method=='POST',timeout=8000) as schedule_info:
                        page.get_by_role('button',name='Add 15-minute service-health job',exact=True).click(timeout=4000)
                    response=schedule_info.value
                    payload=response.json(); sid=payload.get('schedule_id')
                    deadline=time.time()+12; after=before; server_seen=False
                    while time.time()<deadline:
                        try:
                            sr=page.request.get(a.work.rstrip('/')+'/api/schedules',timeout=3000)
                            if sr.ok:
                                rows=(sr.json() or {}).get('schedules') or []
                                server_seen=any(str(x.get('id'))==str(sid) for x in rows)
                        except Exception:
                            server_seen=False
                        after=page.locator('#schedules tr').count()
                        dom_seen=bool(sid) and page.locator(f'#schedules tr[data-schedule-id="{sid}"]').count()>0
                        if server_seen and dom_seen and after>=before+1: break
                        page.wait_for_timeout(150)
                    dom_seen=bool(sid) and page.locator(f'#schedules tr[data-schedule-id="{sid}"]').count()>0
                    ok=response.status==201 and bool(sid) and server_seen and dom_seen and after>=before+1
                    rec('WorkEngine','schedule_add_button','PASS' if ok else 'FAIL',f'http={response.status} schedule_id={sid} server_seen={server_seen} dom_seen={dom_seen} before={before} after={after}')
                except Exception as e: rec('WorkEngine','schedule_add_button','FAIL',e)
            screenshot(page,f'{a.mode}-work-engine.png')
        except Exception as e:
            rec('WorkEngine','unhandled','FAIL',e); screenshot(page,f'{a.mode}-work-engine-fail.png')
        if page_errors: rec('WorkEngine','page_errors','FAIL',' | '.join(page_errors[:10]))
        else: rec('WorkEngine','page_errors','PASS','0')
        page.close(); context.close(); browser.close()

    summary={'overall':'PASS' if not failures else 'FAIL','mode':a.mode,'passed':sum(1 for x in results if x['status']=='PASS'),'failed':len(failures),'skipped':sum(1 for x in results if x['status']=='SKIP'),'results':results,'notes':notes}
    (out/f'{a.mode}-physical-qa.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    print('PHYSICAL_QA_RESULT='+json.dumps({k:summary[k] for k in ('overall','mode','passed','failed','skipped')},ensure_ascii=False),flush=True)
    return 0 if not failures else 9

if __name__=='__main__':
    raise SystemExit(main())
'@
Write-Utf8 $RegressionPy @'
from __future__ import annotations
import argparse, importlib.util, json, tempfile
from pathlib import Path


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--studio-py',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    p=Path(a.studio_py).resolve(); out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('agape_ds_release_test',p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    results=[]
    def check(name,cond,detail=''):
        results.append({'name':name,'status':'PASS' if cond else 'FAIL','detail':str(detail)[:500]})
        if not cond: raise AssertionError(name+': '+str(detail))
    check('version',m.VERSION=='R31.10',m.VERSION)
    check('quotation_type','Quotation' in m.WRITER_TYPES,m.WRITER_TYPES.keys())
    check('dict_required_section',m._required_sections({'doc_type':'Project Plan','required_sections':[{'heading':'Timeline'}]})==['Timeline'])
    content='# Route to \u252c\u00fa1m ARR\n'+('Evidence-based narrative. '*12)
    audit=m.validate_generated_document('Business Proposal',content,['Route to \u00a31m ARR'])
    check('unicode_heading_normalisation',audit.get('ok') is True,audit)
    quote='# Quotation\n'+('Commercial quotation summary. '*3)+'\n\n# Quotation Validity\nValid for 30 days.'
    qa=m.validate_generated_document('Quotation',quote,['Quotation','Quotation Validity'])
    check('quotation_compact_validation',qa.get('ok') is True,qa)
    draft='# Scope\nToo short.\n\n# Other\nKeep this section.'
    patch='# Scope\n'+('Replacement scope detail. '*12)
    merged=m._merge_repaired_sections(draft,patch,['Scope'])
    check('repair_replaces_weak_section',merged.count('# Scope')==1 and 'Too short.' not in merged and '# Other' in merged,merged)
    # Real python-pptx ingestion regression: this was the original R31.9 failure.
    td=Path(tempfile.mkdtemp(prefix='agape-r3110-reg-'))
    ppt=td/'sample.pptx'
    from pptx import Presentation
    prs=Presentation(); slide=prs.slides.add_slide(prs.slide_layouts[1]); slide.shapes.title.text='QA Slide'; slide.placeholders[1].text='PPTX extraction works'; prs.save(ppt)
    extracted=m._extract_instruction_document(ppt,5000)
    check('pptx_ingestion','QA Slide' in extracted and 'PPTX extraction works' in extracted,extracted)
    summary={'overall':'PASS','passed':len(results),'failed':0,'results':results}
    out.write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))
    return 0

if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as e:
        print('R31_10_REGRESSION=FAIL '+repr(e)); raise
'@

$CandidateCoreProc=$null;$CandidateStudioProc=$null;$CandidateWorkProc=$null;$Cutover=$false;$OldMoved=$false
$Result=[ordered]@{build=$Build;overall='FAIL';core=$Core;preflight=[ordered]@{};changes=@();candidate=[ordered]@{};final=[ordered]@{};backup=$BackupDir;release_zip='';release_sha256='';report_dir=$ReportRoot;rollback='NOT_NEEDED'}

try {
    Write-Host '======================================================================' -ForegroundColor Cyan
    Write-Host ' AGAPE V3.1 FULL REBUILD R1.5 - VERIFY / CANDIDATE / PHYSICAL QA / CUTOVER' -ForegroundColor Cyan
    Write-Host '======================================================================' -ForegroundColor Cyan
    Say 'CORE' $Core; Say 'PYTHON' $Python; Say 'STAGE' $Stage; Say 'REPORT_DIR' $ReportRoot

    # --------------------------------------------------------------
    # 0. RUN-PYTHON WRAPPER SELF-TEST
    # --------------------------------------------------------------
    $RunPythonOkProbe=Join-Path $Stage 'run-python-ok-probe.py'
    $RunPythonFailProbe=Join-Path $Stage 'run-python-fail-probe.py'
    Write-Utf8 $RunPythonOkProbe "print('RUN_PYTHON_PROBE_STDOUT=OK')`nraise SystemExit(0)`n"
    Write-Utf8 $RunPythonFailProbe "print('RUN_PYTHON_PROBE_STDOUT=EXPECTED_NONZERO')`nraise SystemExit(7)`n"
    $ProbeOk=Run-Python -ProcessArgs @($RunPythonOkProbe) -LogPath (Join-Path $ReportRoot 'run-python-ok-probe.log')
    Assert-True ((@($ProbeOk).Count -eq 1) -and ([int]$ProbeOk -eq 0)) ("RUN_PYTHON_SCALAR_ZERO_PROBE_FAILED TYPE={0} COUNT={1} VALUE={2}" -f $ProbeOk.GetType().FullName,@($ProbeOk).Count,([string]$ProbeOk))
    $ProbeFail=Run-Python -ProcessArgs @($RunPythonFailProbe) -LogPath (Join-Path $ReportRoot 'run-python-fail-probe.log')
    Assert-True ((@($ProbeFail).Count -eq 1) -and ([int]$ProbeFail -eq 7)) ("RUN_PYTHON_SCALAR_NONZERO_PROBE_FAILED TYPE={0} COUNT={1} VALUE={2}" -f $ProbeFail.GetType().FullName,@($ProbeFail).Count,([string]$ProbeFail))
    Say 'RUN_PYTHON_WRAPPER' 'PASS_SCALAR_EXIT_CODES_0_AND_7' 'Green'

    # --------------------------------------------------------------
    # 1. LIVE SOURCE-OF-TRUTH PREFLIGHT
    # --------------------------------------------------------------
    $CoreV=Ensure-Core $Core
    Assert-True ([string]$CoreV.build -eq $ExpectedCoreBuild) "WRONG_CORE_BUILD=$($CoreV.build)"
    $System=Get-Json 'http://127.0.0.1:8797/api/system-test' 90
    Assert-True ($System -and [bool]$System.ok -and [int]$System.passed -eq 14 -and [int]$System.total -eq 14) ('LIVE_CORE_NOT_14_OF_14='+(@($System.failed)-join ','))
    Assert-True ([bool]$System.checks.source_manifest) 'LIVE_SOURCE_MANIFEST_NOT_CLEAN'
    $Result.preflight.core_system='14/14 PASS'
    $LiveDb=[string]$System.database.database; Assert-True (Test-Path -LiteralPath $LiveDb -PathType Leaf) "LIVE_DB_NOT_FOUND=$LiveDb"
    $LiveData=Split-Path $LiveDb -Parent

    $StudioH=Ensure-Studio $Core
    Assert-True ([string]$StudioH.version -in @('R31.9','R31.10')) "UNEXPECTED_DOCUMENT_STUDIO_VERSION=$($StudioH.version)"
    $Result.preflight.document_studio=[string]$StudioH.version
    $WorkH=Ensure-WorkEngine $Core
    Assert-True ([string]$WorkH.version -in @('R1.1','R1.2')) "UNEXPECTED_WORK_ENGINE_VERSION=$($WorkH.version)"
    $Result.preflight.work_engine=[string]$WorkH.version

    $Index=Join-Path $Core 'index.html';$Manifest=Join-Path $Core 'manifest.json';$ProviderFailover=Join-Path $Core 'provider_failover.py';$ModelRouter=Join-Path $Core 'model_router.py'
    foreach($f in @($Index,$Manifest,$ProviderFailover,$ModelRouter,(Join-Path $Core 'START-DMT-SECOND-BRAIN.ps1'),(Join-Path $Core 'OPEN-AGAPE-DOCUMENT-STUDIO.ps1'),(Join-Path $Core 'OPEN-AGAPE-WORK-ENGINE.ps1'))){Assert-True (Test-Path -LiteralPath $f -PathType Leaf) "REQUIRED_FILE_MISSING=$f"}
    $IndexText=Get-Content -LiteralPath $Index -Raw
    Assert-True ($IndexText -match 'project-instructions-text') 'R8_PROJECT_INFORMATION_TEXTAREA_MISSING'
    Assert-True ($IndexText -match 'agape-r8-text-entry-repair') 'R8_TEXT_ENTRY_REPAIR_MARKER_MISSING'
    $StudioPy=Join-Path $Core 'agape-document-studio\document_studio.py';Assert-True (Test-Path -LiteralPath $StudioPy) 'DOCUMENT_STUDIO_SOURCE_MISSING'
    $StudioText=Get-Content -LiteralPath $StudioPy -Raw
    foreach($m in @('previewSelectedTemplate','/api/template-preview/start','instructionUploadInput','completeFullFormBtn')){Assert-True ($StudioText -match [regex]::Escape($m)) "DOCUMENT_STUDIO_MARKER_MISSING=$m"}
    foreach($m in @('code_intel.py','provider_circuit.py','lanes.py','optimizer.py','scheduler.py','plugins.py','supervisor.py','uploads.py','telemetry.py','work_engine.py')){Assert-True (Test-Path -LiteralPath (Join-Path $Core ('agape-systems-engine\agape_systems_engine\'+$m))) "WORK_ENGINE_MODULE_MISSING=$m"}
    Say 'LIVE_CHANGE_CONTRACT' 'PASS' 'Green'

    # --------------------------------------------------------------
    # 2. CLEAN CANDIDATE COPY OF VERIFIED LIVE PROGRAM TREE
    # --------------------------------------------------------------
    $LiveSnap=Join-Path $ReportRoot 'live-before-rebuild.json'; Tree-Snapshot $Core $LiveSnap
    Copy-Tree $Core $Candidate
    $BeforeSnap=Join-Path $ReportRoot 'candidate-before.json'; Tree-Snapshot $Candidate $BeforeSnap
    Compare-SnapshotExact $LiveSnap $BeforeSnap
    $Result.candidate.copy_integrity='EXACT SOURCE/CONFIG MATCH'
    Say 'CANDIDATE_COPY' 'PASS_EXACT_HASH_MATCH' 'Green'

    # Promote only deterministic fixes covered by regression / physical QA.
    $CandidateIndex=Join-Path $Candidate 'index.html'
    $rc=Run-Python -ProcessArgs @($CoreUiPatcherPy,$CandidateIndex) -LogPath (Join-Path $ReportRoot 'core-ui-r1.4-patch.log')
    if($rc -ne 0){throw 'CORE_UI_R13_PATCH_FAILED'}

    $CandidateStudioPy=Join-Path $Candidate 'agape-document-studio\document_studio.py'
    $rc=Run-Python -ProcessArgs @($PatcherPy,$CandidateStudioPy) -LogPath (Join-Path $ReportRoot 'document-studio-patch.log')
    if($rc -ne 0){throw 'DOCUMENT_STUDIO_PATCH_FAILED'}
    $CandidateStudioLauncher=Join-Path $Candidate 'OPEN-AGAPE-DOCUMENT-STUDIO.ps1'
    $launcherText=Get-Content -LiteralPath $CandidateStudioLauncher -Raw
    $launcherText=$launcherText.Replace('R31.9','R31.10').Replace('R31_9','R31_10')
    Write-Utf8 $CandidateStudioLauncher $launcherText

    $CandidateWorkApp=Join-Path $Candidate 'agape-systems-engine\agape_systems_engine\app.py'
    $CandidateWorkInit=Join-Path $Candidate 'agape-systems-engine\agape_systems_engine\__init__.py'
    $rc=Run-Python -ProcessArgs @($WorkEnginePatcherPy,$CandidateWorkApp,$CandidateWorkInit) -LogPath (Join-Path $ReportRoot 'work-engine-r1.2-patch.log')
    if($rc -ne 0){throw 'WORK_ENGINE_R12_PATCH_FAILED'}

    Refresh-Manifest $Candidate
    $Result.changes=@(
        'Core R8 native navigation retained + direct and cached legacy onclick bindings made null-safe',
        'Document Studio R31.9 -> R31.10',
        'Quotation document type',
        'PPTX ingestion slice fix',
        'Unicode/required-section normalization',
        'Duplicate-aware section repair',
        'Work Engine R1.1 -> R1.3 dedicated schedule endpoint + deterministic UI refresh',
        'Physical browser release gate aligned to native R8 UI + startup readiness'
    )

    # Compile all source now, before runtime testing.
    $rc=Run-Python -ProcessArgs @('-m','compileall','-q',$Candidate) -LogPath (Join-Path $ReportRoot 'candidate-python-compile.log')
    if($rc -ne 0){throw 'CANDIDATE_PYTHON_COMPILE_FAILED'}
    Say 'CANDIDATE_PYTHON_COMPILE' 'PASS' 'Green'

    # Isolate Document Studio data for candidate testing. Preserve exact live config for final package.
    $CandidateStudioConfig=Join-Path $Candidate 'agape-document-studio\config.json'
    $OriginalStudioConfig=Get-Content -LiteralPath $CandidateStudioConfig -Raw
    $cfg=$OriginalStudioConfig|ConvertFrom-Json
    $cfg.data_root=$CandidateStudioData
    $cfg.template_library=Join-Path $CandidateStudioData 'templates'
    $cfg.output_root=Join-Path $CandidateStudioData 'outputs'
    Write-Utf8 $CandidateStudioConfig ($cfg|ConvertTo-Json -Depth 20)

    # Clone current Core data safely using SQLite backup API, not raw live DB copy.
    Copy-DataForCandidate $LiveData $CandidateCoreData $LiveDb
    $CandidateWorkflow=Join-Path $CandidateCoreData 'workflow-output';New-Item -ItemType Directory -Path $CandidateWorkflow -Force|Out-Null

    # --------------------------------------------------------------
    # 3. CANDIDATE CORE / DOCUMENT STUDIO / WORK ENGINE GATES
    # --------------------------------------------------------------
    $CandidateCoreProc=Start-BackgroundPython -ProcessArgs @((Join-Path $Candidate 'app.py'),'--port',([string]$CandidateCorePort)) -Out (Join-Path $ReportRoot 'candidate-core.out.log') -Err (Join-Path $ReportRoot 'candidate-core.err.log') -EnvVars @{DMT_DATA_ROOT=$CandidateCoreData;DMT_WORKFLOW_ROOT=$CandidateWorkflow}
    $CandidateCoreV=Wait-Json "http://127.0.0.1:$CandidateCorePort/api/version" 50;Assert-True $CandidateCoreV 'CANDIDATE_CORE_START_FAILED'
    Assert-True ([string]$CandidateCoreV.build -eq $ExpectedCoreBuild) "CANDIDATE_CORE_BUILD_WRONG=$($CandidateCoreV.build)"
    $CandidateSystem=Get-Json "http://127.0.0.1:$CandidateCorePort/api/system-test" 120
    Assert-True ($CandidateSystem -and [bool]$CandidateSystem.ok -and [int]$CandidateSystem.passed -eq 14) ('CANDIDATE_CORE_SYSTEM_FAIL='+(@($CandidateSystem.failed)-join ','))
    $Result.candidate.core='14/14 PASS'; Say 'CANDIDATE_CORE_SYSTEM' '14/14_PASS' 'Green'

    $CandidateStudioDir=Split-Path $CandidateStudioPy -Parent
    $rc=Run-Python -ProcessArgs @($CandidateStudioPy,'--self-test') -LogPath (Join-Path $ReportRoot 'candidate-document-studio-selftest.log');if($rc -ne 0){throw 'CANDIDATE_DOCUMENT_STUDIO_SELFTEST_FAILED'}
    Say 'CANDIDATE_DOCUMENT_STUDIO_SELFTEST' 'PASS' 'Green'
    $rc=Run-Python -ProcessArgs @($RegressionPy,'--studio-py',$CandidateStudioPy,'--out',(Join-Path $ReportRoot 'r31.10-regression.json')) -LogPath (Join-Path $ReportRoot 'candidate-r31.10-regression.log');if($rc -ne 0){throw 'CANDIDATE_R31_10_REGRESSION_FAILED'}
    Say 'CANDIDATE_R31_10_REGRESSION' 'PASS' 'Green'
    if(-not $SkipCandidateBatchDemo){
        $rc=Run-Python -ProcessArgs @($CandidateStudioPy,'--batch-demo') -LogPath (Join-Path $ReportRoot 'candidate-document-studio-batch-demo.log');if($rc -ne 0){throw 'CANDIDATE_DOCUMENT_STUDIO_BATCH_DEMO_FAILED'}
        Say 'CANDIDATE_DOCUMENT_STUDIO_BATCH_DEMO' 'PASS' 'Green'
    }
    $CandidateStudioProc=Start-BackgroundPython -ProcessArgs @($CandidateStudioPy,'--port',([string]$CandidateStudioPort),'--no-browser') -Out (Join-Path $ReportRoot 'candidate-studio.out.log') -Err (Join-Path $ReportRoot 'candidate-studio.err.log')
    $CandidateStudioH=Wait-Json "http://127.0.0.1:$CandidateStudioPort/api/health" 60;Assert-True ($CandidateStudioH -and [string]$CandidateStudioH.version -eq $TargetStudioVersion) 'CANDIDATE_DOCUMENT_STUDIO_HEALTH_FAILED'
    $Result.candidate.document_studio='R31.10 PASS'

    $CandidateEngineRoot=Join-Path $Candidate 'agape-systems-engine'
    $rc=Run-Python -ProcessArgs @((Join-Path $CandidateEngineRoot 'selftest_entry.py')) -LogPath (Join-Path $ReportRoot 'candidate-work-engine-selftest.log');if($rc -ne 0){throw 'CANDIDATE_WORK_ENGINE_SELFTEST_FAILED'}
    $CandidateWorkProc=Start-BackgroundPython -ProcessArgs @((Join-Path $CandidateEngineRoot 'engine_entry.py'),'--port',([string]$CandidateWorkPort),'--data-root',$CandidateWorkData,'--core-root',$Candidate,'--no-browser') -Out (Join-Path $ReportRoot 'candidate-work.out.log') -Err (Join-Path $ReportRoot 'candidate-work.err.log')
    $CandidateWorkH=Wait-Json "http://127.0.0.1:$CandidateWorkPort/api/health" 45;Assert-True ($CandidateWorkH -and [string]$CandidateWorkH.version -eq $ExpectedWorkEngine) 'CANDIDATE_WORK_ENGINE_HEALTH_FAILED'
    $rc=Run-Python -ProcessArgs @((Join-Path $CandidateEngineRoot 'integration_test.py'),'--base',"http://127.0.0.1:$CandidateWorkPort",'--core-root',$Candidate) -LogPath (Join-Path $ReportRoot 'candidate-work-engine-integration.log');if($rc -ne 0){throw 'CANDIDATE_WORK_ENGINE_INTEGRATION_FAILED'}
    $Result.candidate.work_engine='11/11 SELFTEST + 7/7 INTEGRATION PASS'

    Ensure-Playwright
    Run-PhysicalQA 'candidate' "http://127.0.0.1:$CandidateCorePort/" "http://127.0.0.1:$CandidateStudioPort/" "http://127.0.0.1:$CandidateWorkPort/" $Candidate (Join-Path $ReportRoot 'candidate-browser')
    $Result.candidate.physical_qa='PASS'

    # Stop candidate processes before restoring live config and packaging.
    Stop-ProcessSafe $CandidateWorkProc; $CandidateWorkProc=$null
    Stop-ProcessSafe $CandidateStudioProc; $CandidateStudioProc=$null
    Stop-ProcessSafe $CandidateCoreProc; $CandidateCoreProc=$null

    # Restore real Document Studio config into the candidate release tree.
    Write-Utf8 $CandidateStudioConfig $OriginalStudioConfig
    Remove-Item -LiteralPath (Join-Path $Candidate 'agape-document-studio\__pycache__') -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -LiteralPath $Candidate -Directory -Filter '__pycache__' -Recurse -ErrorAction SilentlyContinue|Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    $AfterSnap=Join-Path $ReportRoot 'candidate-after.json'; Tree-Snapshot $Candidate $AfterSnap; Check-Allowed-Diff $BeforeSnap $AfterSnap
    Say 'CANDIDATE_SOURCE_DIFF' 'PASS_APPROVED_ONLY' 'Green'

    # Create complete source package BEFORE cutover.
    if(Test-Path $ReleaseZip){Remove-Item $ReleaseZip -Force}
    Compress-Archive -Path (Join-Path $Candidate '*') -DestinationPath $ReleaseZip -Force
    $ReleaseSha=Sha $ReleaseZip; $Result.release_zip=$ReleaseZip; $Result.release_sha256=$ReleaseSha
    Say 'RELEASE_ZIP' $ReleaseZip; Say 'RELEASE_SHA256' $ReleaseSha

    # --------------------------------------------------------------
    # 4. FULL PROGRAM CUTOVER WITH WHOLE-TREE ROLLBACK
    # --------------------------------------------------------------
    New-Item -ItemType Directory -Path $BackupDir -Force|Out-Null
    Stop-OwnedPort $WorkPort $Core
    Stop-OwnedPort $StudioPort $Core
    Stop-OwnedPort $CorePort $Core
    for($i=0;$i -lt 30;$i++){if(-not (Get-NetTCPConnection -LocalPort $CorePort,$StudioPort,$WorkPort -State Listen -ErrorAction SilentlyContinue)){break};Start-Sleep -Milliseconds 250}
    if(Test-Path $OldSwap){Remove-Item $OldSwap -Recurse -Force}
    Move-Item -LiteralPath $Core -Destination $OldSwap; $OldMoved=$true
    Move-Item -LiteralPath $Candidate -Destination $Core; $Cutover=$true
    Say 'PROGRAM_CUTOVER' 'PASS' 'Green'

    # Start new live stack.
    $CoreV=Ensure-Core $Core
    Assert-True ([string]$CoreV.build -eq $ExpectedCoreBuild) 'FINAL_CORE_BUILD_WRONG'
    $FinalSystem=Get-Json 'http://127.0.0.1:8797/api/system-test' 120
    Assert-True ($FinalSystem -and [bool]$FinalSystem.ok -and [int]$FinalSystem.passed -eq 14 -and [bool]$FinalSystem.checks.source_manifest) ('FINAL_CORE_SYSTEM_FAIL='+(@($FinalSystem.failed)-join ','))
    $Result.final.core='14/14 PASS'

    $FinalStudio=Ensure-Studio $Core
    Assert-True ([string]$FinalStudio.version -eq $TargetStudioVersion) "FINAL_STUDIO_VERSION_WRONG=$($FinalStudio.version)"
    $Result.final.document_studio='R31.10 PASS'
    $FinalWork=Ensure-WorkEngine $Core
    Assert-True ([string]$FinalWork.version -eq $ExpectedWorkEngine) "FINAL_WORK_ENGINE_VERSION_WRONG=$($FinalWork.version)"
    $FinalEngineRoot=Join-Path $Core 'agape-systems-engine'
    $rc=Run-Python -ProcessArgs @((Join-Path $FinalEngineRoot 'integration_test.py'),'--base','http://127.0.0.1:8820','--core-root',$Core,'--require-core') -LogPath (Join-Path $ReportRoot 'final-work-engine-integration.log');if($rc -ne 0){throw 'FINAL_WORK_ENGINE_INTEGRATION_FAILED'}
    $Result.final.work_engine='7/7 PASS REQUIRE_CORE'

    Run-PhysicalQA 'live' 'http://127.0.0.1:8797/' 'http://127.0.0.1:8800/' 'http://127.0.0.1:8820/' $Core (Join-Path $ReportRoot 'live-browser')
    $Result.final.physical_qa='PASS'

    # Final integrity gate again after browser actions.
    $FinalSystem2=Get-Json 'http://127.0.0.1:8797/api/system-test' 120
    Assert-True ($FinalSystem2 -and [bool]$FinalSystem2.ok -and [int]$FinalSystem2.passed -eq 14 -and [bool]$FinalSystem2.checks.source_manifest) 'POST_BROWSER_SOURCE_INTEGRITY_FAILED'
    $Result.final.post_browser_core='14/14 PASS'
    Tree-Snapshot $Core (Join-Path $ReportRoot 'final-program-tree.json')
    Say 'FINAL_PROGRAM_TREE_MANIFEST' 'PASS' 'Green'

    # Preserve the complete old program tree as rollback evidence only after new release passes.
    $ProgramBackup=Join-Path $BackupDir 'dmt-second-brain'
    Move-Item -LiteralPath $OldSwap -Destination $ProgramBackup; $OldMoved=$false
    $Result.rollback='READY_AT_'+$ProgramBackup

    $receipt=[ordered]@{build=$Build;installed_at=(Get-Date).ToString('o');core_build=$ExpectedCoreBuild;document_studio=$TargetStudioVersion;work_engine=$ExpectedWorkEngine;release_zip=$ReleaseZip;release_sha256=$ReleaseSha;report_dir=$ReportRoot;backup=$ProgramBackup;candidate_physical_qa='PASS';live_physical_qa='PASS'}
    Write-Utf8 (Join-Path $DataBase ("full-rebuild-r1.2-receipt-$Stamp.json")) ($receipt|ConvertTo-Json -Depth 10)
    $Result.overall='PASS'
    Write-Utf8 $ResultPath ($Result|ConvertTo-Json -Depth 20)
    Write-Host ''
    Write-Host '================ CHATGPT_RESULT_BEGIN ================' -ForegroundColor Green
    $Result|ConvertTo-Json -Depth 20
    Write-Host '================= CHATGPT_RESULT_END =================' -ForegroundColor Green
    Start-Process 'http://127.0.0.1:8797/'
    Start-Process 'http://127.0.0.1:8820/'
}
catch {
    $ErrText=$_.Exception.Message
    Say 'FULL_REBUILD' ('FAIL '+$ErrText) 'Red'
    Stop-ProcessSafe $CandidateWorkProc;Stop-ProcessSafe $CandidateStudioProc;Stop-ProcessSafe $CandidateCoreProc
    if($Cutover){
        try{Stop-OwnedPort $WorkPort $Core}catch{}
        try{Stop-OwnedPort $StudioPort $Core}catch{}
        try{Stop-OwnedPort $CorePort $Core}catch{}
        try{if(Test-Path -LiteralPath $Core){Remove-Item -LiteralPath $Core -Recurse -Force}}catch{}
        if(Test-Path -LiteralPath $OldSwap){
            try{Move-Item -LiteralPath $OldSwap -Destination $Core;$OldMoved=$false;$Result.rollback='PROGRAM_TREE_RESTORED'}catch{$Result.rollback='ROLLBACK_MOVE_FAILED: '+$_.Exception.Message}
            try{Ensure-Core $Core|Out-Null}catch{}
            try{Ensure-Studio $Core|Out-Null}catch{}
            try{Ensure-WorkEngine $Core|Out-Null}catch{}
        }
    }
    $Result.overall='FAIL';$Result.error=$ErrText
    try{Write-Utf8 $ResultPath ($Result|ConvertTo-Json -Depth 20)}catch{}
    Write-Host ''
    Write-Host '================ CHATGPT_RESULT_BEGIN ================' -ForegroundColor Red
    $Result|ConvertTo-Json -Depth 20
    Write-Host '================= CHATGPT_RESULT_END =================' -ForegroundColor Red
    throw
}
finally {
    Stop-ProcessSafe $CandidateWorkProc;Stop-ProcessSafe $CandidateStudioProc;Stop-ProcessSafe $CandidateCoreProc
    if(-not $KeepStage -and $Result.overall -eq 'PASS'){
        try{if(Test-Path -LiteralPath $Stage){Remove-Item -LiteralPath $Stage -Recurse -Force}}catch{}
    }
}
