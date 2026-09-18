param(
    [string]$Root = $PSScriptRoot,
    [int]$Port = 8850
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$ExpectedBuild = "AGAPE-MAINFRAME-V5.6.1-CANONICAL-STATUS-SYNC"
$ExpectedWebRevision = "R2.4.3-WEB-ROUTER"
$HealthUrl = "http://127.0.0.1:$Port/api/health"
$AppUrl = "http://127.0.0.1:$Port/"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"

function Get-Python {
    foreach($p in @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe")
    )) { if(Test-Path -LiteralPath $p -PathType Leaf){ return $p } }
    $py=Get-Command py.exe -ErrorAction SilentlyContinue
    if($py){
        $resolved=(& $py.Source -3 -c "import sys;print(sys.executable)" 2>$null | Select-Object -First 1)
        if($LASTEXITCODE -eq 0 -and $resolved){ return $resolved.Trim() }
    }
    $p=Get-Command python.exe -ErrorAction SilentlyContinue
    if(-not $p){$p=Get-Command python -ErrorAction SilentlyContinue}
    if($p){return $p.Source}
    throw "PYTHON_NOT_FOUND"
}

function Get-Health {
    try { Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 2 } catch { $null }
}

function Get-ListenerPid {
    try {
        $row=Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop | Select-Object -First 1
        if($row){return [int]$row.OwningProcess}
    } catch {}
    return 0
}

function Test-WebUi {
    try {
        $root=Invoke-WebRequest -Uri $AppUrl -UseBasicParsing -TimeoutSec 3
        $templates=Invoke-WebRequest -Uri ("http://127.0.0.1:$Port/project_templates.js") -UseBasicParsing -TimeoutSec 3
        return ($root.StatusCode -eq 200 -and $root.Content -match '<title>Agape' -and $templates.StatusCode -eq 200)
    } catch { return $false }
}

if(!(Test-Path -LiteralPath $Root -PathType Container)){throw "AGAPE_SOURCE_NOT_FOUND=$Root"}
$Main=Join-Path $Root "main.py"
if(!(Test-Path -LiteralPath $Main -PathType Leaf)){throw "AGAPE_MAIN_NOT_FOUND=$Main"}
$Python=Get-Python
$Logs=Join-Path $Root "logs"; New-Item -ItemType Directory -Path $Logs -Force | Out-Null

$health=Get-Health
if($health -and [string]$health.build -eq $ExpectedBuild -and [string]$health.web_revision -eq $ExpectedWebRevision -and (Test-WebUi)){ Start-Process $AppUrl; exit 0 }
if($health -and [string]$health.build -like "AGAPE-MAINFRAME*"){
    $listenerPid=Get-ListenerPid
    if($listenerPid -gt 0){ Stop-Process -Id $listenerPid -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 1 }
} elseif((Get-ListenerPid) -gt 0){ throw "PORT_${Port}_IN_USE_BY_NON_AGAPE_PROCESS" }

$out=Join-Path $Logs "agape-start-$Stamp.log"
$err=Join-Path $Logs "agape-start-$Stamp.err.log"
$proc=Start-Process -FilePath $Python -ArgumentList @("`"$Main`"","--port","$Port","--no-browser") -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru

$ready=$false
for($i=0;$i -lt 60;$i++){
    Start-Sleep -Milliseconds 500
    if($proc.HasExited){break}
    $health=Get-Health
    if($health -and [string]$health.build -eq $ExpectedBuild -and [string]$health.web_revision -eq $ExpectedWebRevision -and (Test-WebUi)){$ready=$true;break}
}
if(!$ready){
    Write-Host "AGAPE_START_FAILED" -ForegroundColor Red
    Write-Host "STDOUT_LOG=$out"
    Write-Host "STDERR_LOG=$err"
    if(Test-Path $err){Get-Content $err -Tail 40 -ErrorAction SilentlyContinue}
    throw "AGAPE_START_FAILED_EXPECTED_BUILD=$ExpectedBuild"
}

Write-Host "AGAPE_V5_6_1_RUNNING=PASS" -ForegroundColor Green
Write-Host "BUILD=$($health.build)"
Write-Host "VERSION=$($health.version)"
Write-Host "URL=$AppUrl"
Start-Process $AppUrl
