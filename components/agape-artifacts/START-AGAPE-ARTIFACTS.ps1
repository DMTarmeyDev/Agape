param(
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $Root 'agape-artifacts-config.json'
$ToolPath = Join-Path $Root 'agape_artifacts_tool.py'

if (!(Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw 'AGAPE_ARTIFACT_CONFIG_NOT_FOUND'
}

$Config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$Url = "http://127.0.0.1:$([int]$Config.port)"

try {
    $Existing = Invoke-RestMethod -Uri "$Url/api/dashboard" -TimeoutSec 2

    if ($Existing -and [string]$Existing.module -eq 'AGAPE-ARTIFACTS-R3.1') {
        if (-not $NoBrowser) {
            Start-Process $Url
        }
        exit 0
    }
}
catch {}

$Args = @(
    $ToolPath,
    '--project', [string]$Config.project,
    '--data', [string]$Config.data,
    '--database', [string]$Config.database,
    '--port', [string]$Config.port
)

Start-Process `
    -FilePath ([string]$Config.python) `
    -ArgumentList $Args `
    -WorkingDirectory $Root `
    -WindowStyle Hidden | Out-Null

for ($i=0; $i -lt 80; $i++) {
    Start-Sleep -Milliseconds 250

    try {
        $Ready = Invoke-RestMethod -Uri "$Url/api/dashboard" -TimeoutSec 2

        if ($Ready -and [string]$Ready.module -eq 'AGAPE-ARTIFACTS-R3.1') {
            if (-not $NoBrowser) {
                Start-Process $Url
            }
            exit 0
        }
    }
    catch {}
}

throw 'AGAPE_ARTIFACTS_START_TIMEOUT'