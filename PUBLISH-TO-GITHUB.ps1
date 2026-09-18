param(
    [Parameter(Mandatory=$true)][string]$Repository,
    [ValidateSet('public','private')][string]$Visibility='public',
    [string]$Tag='v5.5.0'
)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is required.' }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
gh auth status | Out-Host
python scripts/public_audit.py
if ($LASTEXITCODE -ne 0) { throw 'Public release audit failed. Fix findings before publishing.' }
if (-not (Test-Path '.git')) { git init; git branch -M main }
git add .
$pending = git status --porcelain
if ($pending) { git commit -m "Agape V5.5 review, download and full-QA reliability update" }
$remote = git remote get-url origin 2>$null
if (-not $remote) {
    if ($Visibility -eq 'public') { gh repo create $Repository --public --source . --remote origin --push }
    else { gh repo create $Repository --private --source . --remote origin --push }
} else {
    git push -u origin HEAD
}
if (-not (git tag -l $Tag)) { git tag $Tag }
git push origin $Tag
Write-Host "Published source and tag $Tag. GitHub Actions will test/build Windows, macOS and Linux release assets." -ForegroundColor Green
