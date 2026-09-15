[CmdletBinding()]
param(
    [ValidateRange(1024,65535)][int]$Port = 8797,
    [string]$DataPath = '',
    [string]$RuntimePath = '',
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($DataPath) { $env:DMT_DATA_ROOT = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($DataPath)) }
$Python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
if (!(Test-Path -LiteralPath $Python -PathType Leaf)) {
    $Cmd = Get-Command python -ErrorAction Stop
    $Python = $Cmd.Source
}
$RuntimeRoot = if ($RuntimePath) { [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($RuntimePath)) } else { Join-Path $env:LOCALAPPDATA 'DMT-Core-V1.8-Runtime' }
$LogDir = Join-Path $RuntimeRoot 'logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$Out = Join-Path $LogDir "startup-$Stamp.log"
$Err = Join-Path $LogDir "startup-$Stamp.err.log"
$P = Start-Process -FilePath $Python -WorkingDirectory $Project -ArgumentList @('-u',(Join-Path $Project 'app.py'),'--port',[string]$Port) -RedirectStandardOutput $Out -RedirectStandardError $Err -PassThru -WindowStyle Hidden
for ($i=0; $i -lt 100; $i++) {
    Start-Sleep -Milliseconds 250
    try {
        $V = Invoke-RestMethod "http://127.0.0.1:$Port/api/version" -TimeoutSec 2
        if ([int]$V.pid -eq $P.Id) {
            Write-Host "DMT_READY=http://127.0.0.1:$Port" -ForegroundColor Green
            Write-Host "BUILD=$($V.build)"
            Write-Host "PID=$($V.pid)"
            Write-Host "PROJECT=$($V.project_path)"
            Write-Host "DATA_PATH=$($V.data_path)"
            if (!$NoBrowser) { Start-Process "http://127.0.0.1:$Port/first-run?fresh=1" }
            exit 0
        }
    } catch {}
    if ($P.HasExited) { throw "DMT_START_FAILED_EXIT=$($P.ExitCode) LOG=$Out ERR=$Err" }
}
throw "DMT_START_TIMEOUT PID=$($P.Id) LOG=$Out ERR=$Err"
