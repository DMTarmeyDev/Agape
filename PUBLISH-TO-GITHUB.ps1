param(
    [string]$Repository='DMTarmeyDev/Agape',
    [ValidateSet('public','private')][string]$Visibility='public',
    [string]$Tag='v5.6.1-r2.5.1'
)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot

function Run([string]$File,[string[]]$Args){
    & $File @Args
    if($LASTEXITCODE -ne 0){throw "COMMAND_FAILED: $File $($Args -join ' ')"}
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is required.' }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Python is required.' }

Run 'gh' @('auth','status','-h','github.com')
Run 'python' @('scripts/public_audit.py')
Run 'python' @('scripts/check_repository_links.py')
Run 'python' @('-m','pytest','-q','tests')
Push-Location 'recovered/unified-r24'
try { Run 'python' @('-m','pytest','-q','tests') } finally { Pop-Location }

if (-not (Test-Path '.git')) {
    Run 'git' @('init')
    Run 'git' @('branch','-M','main')
}

Run 'git' @('add','-A')
Run 'git' @('diff','--cached','--check')
$pending = git diff --cached --name-only
if ($pending) {
    Run 'git' @('commit','-m','Agape V5.6.1 R2.5.1 all-platform mobile and release-link repair')
}

$remote = git remote get-url origin 2>$null
if (-not $remote) {
    if ($Visibility -eq 'public') { Run 'gh' @('repo','create',$Repository,'--public','--source','.','--remote','origin','--push') }
    else { Run 'gh' @('repo','create',$Repository,'--private','--source','.','--remote','origin','--push') }
} else {
    Run 'git' @('push','-u','origin','HEAD')
}

if (-not (git tag -l $Tag)) { Run 'git' @('tag',$Tag) }
Run 'git' @('push','origin',$Tag)
Write-Host "Published source and tag $Tag. GitHub Actions will run QA and build Windows, macOS, Linux, Android and iOS Simulator release assets." -ForegroundColor Green
