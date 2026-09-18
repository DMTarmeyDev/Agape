param(
    [string]$Root = "$env:USERPROFILE\Agape-Latest-Complete",
    [int]$Port = 8850
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$ExpectedBuild = "AGAPE-MAINFRAME-V5.5-UX-DOWNLOAD-QA"
$HealthUrl = "http://127.0.0.1:$Port/api/health"
$AppUrl = "http://127.0.0.1:$Port/"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"

function Pass([string]$Text) { Write-Host "[PASS] $Text" -ForegroundColor Green }
function Info([string]$Text) { Write-Host "[INFO] $Text" -ForegroundColor Cyan }
function Warn([string]$Text) { Write-Host "[WARN] $Text" -ForegroundColor Yellow }

function Get-Python {
    $known = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe")
    )
    foreach ($path in $known) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            return $path
        }
    }

    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        $old = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $resolved = (& $py.Source -3 -c "import sys;print(sys.executable)" 2>$null | Select-Object -First 1)
        $code = $LASTEXITCODE
        $ErrorActionPreference = $old
        if ($code -eq 0 -and $resolved -and (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            return $resolved.Trim()
        }
    }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    if ($python) { return $python.Source }

    throw "PYTHON_NOT_FOUND"
}

function Get-Health {
    try {
        return Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 2
    } catch {
        return $null
    }
}

function Get-ListenerPid {
    try {
        $row = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
            Select-Object -First 1
        if ($row) { return [int]$row.OwningProcess }
    } catch {}

    try {
        $line = netstat -ano | Select-String -Pattern "[:.]$Port\s+.*LISTENING\s+(\d+)$" |
            Select-Object -First 1
        if ($line -and $line.Matches.Count -gt 0) {
            return [int]$line.Matches[0].Groups[1].Value
        }
    } catch {}

    return 0
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " AGAPE V5.5 - WINDOWS LAUNCHER REPAIR + START" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
    throw "AGAPE_SOURCE_NOT_FOUND=$Root"
}

$Main = Join-Path $Root "main.py"
if (-not (Test-Path -LiteralPath $Main -PathType Leaf)) {
    throw "AGAPE_MAIN_NOT_FOUND=$Main"
}

$Python = Get-Python
Pass "PYTHON=$Python"

$Logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Path $Logs -Force | Out-Null

# If the correct V5.5 server is already running, just open it.
$health = Get-Health
if ($health -and [string]$health.build -eq $ExpectedBuild) {
    Pass "AGAPE_ALREADY_RUNNING BUILD=$($health.build)"
    Start-Process $AppUrl
    exit 0
}

# Only terminate an old listener when it identifies itself as Agape.
if ($health -and [string]$health.build -like "AGAPE-MAINFRAME*") {
    $oldPid = Get-ListenerPid
    if ($oldPid -gt 0) {
        Warn "Stopping older Agape process PID=$oldPid BUILD=$($health.build)"
        Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
} else {
    $listenerPid = Get-ListenerPid
    if ($listenerPid -gt 0) {
        throw "PORT_${Port}_IS_IN_USE_BY_NON_AGAPE_PROCESS_PID=$listenerPid"
    }
}

$OutLog = Join-Path $Logs "agape-start-$Stamp.log"
$ErrLog = Join-Path $Logs "agape-start-$Stamp.err.log"

Info "Starting Agape V5.5..."
$proc = Start-Process `
    -FilePath $Python `
    -ArgumentList @("`"$Main`"","--port","$Port","--no-browser") `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

Info "PID=$($proc.Id)"
Info "HEALTH=$HealthUrl"

$ready = $false
$lastHealth = $null

for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500

    if ($proc.HasExited) { break }

    $lastHealth = Get-Health
    if ($lastHealth -and [string]$lastHealth.build -eq $ExpectedBuild) {
        $ready = $true
        break
    }
}

if (-not $ready) {
    Write-Host ""
    Write-Host "[FAIL] AGAPE_DID_NOT_REACH_EXPECTED_HEALTH" -ForegroundColor Red
    Write-Host "EXPECTED_BUILD=$ExpectedBuild"
    if ($lastHealth) {
        Write-Host "ACTUAL_BUILD=$($lastHealth.build)"
    }
    Write-Host "STDOUT_LOG=$OutLog"
    Write-Host "STDERR_LOG=$ErrLog"

    if (Test-Path -LiteralPath $ErrLog) {
        $err = Get-Content -LiteralPath $ErrLog -Tail 40 -ErrorAction SilentlyContinue
        if ($err) {
            Write-Host ""
            Write-Host "=== LAST ERROR LINES ===" -ForegroundColor Yellow
            $err | ForEach-Object { Write-Host $_ }
        }
    }

    throw "AGAPE_START_FAILED"
}

Pass "HEALTH=PASS"
Pass "BUILD=$($lastHealth.build)"
Pass "VERSION=$($lastHealth.version)"
Pass "PID=$($lastHealth.pid)"

# Replace the stale launcher in the installed source with a simple correct launcher.
$CmdPath = Join-Path $Root "OPEN AGAPE.cmd"
$Cmd = @"
@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0START-AGAPE-LATEST.ps1"
"@
[IO.File]::WriteAllText($CmdPath,$Cmd,(New-Object Text.UTF8Encoding($false)))

$SelfTarget = Join-Path $Root "START-AGAPE-LATEST.ps1"
if ($MyInvocation.MyCommand.Path -and
    ([IO.Path]::GetFullPath($MyInvocation.MyCommand.Path) -ne [IO.Path]::GetFullPath($SelfTarget))) {
    Copy-Item -LiteralPath $MyInvocation.MyCommand.Path -Destination $SelfTarget -Force
}
Pass "LAUNCHER_REPAIRED=$CmdPath"

Start-Process $AppUrl

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " AGAPE V5.5 = RUNNING" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "URL=$AppUrl"
Write-Host "SOURCE=$Root"
Write-Host "STDOUT_LOG=$OutLog"
Write-Host "STDERR_LOG=$ErrLog"
