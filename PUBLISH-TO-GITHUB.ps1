param(
    [string]$RepoName = "agape-recovered",
    [ValidateSet("private","public")]
    [string]$Visibility = "private"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "============================================================"
Write-Host " AGAPE - CREATE GITHUB REPOSITORY + PUSH"
Write-Host "============================================================"
Write-Host "SOURCE=$Root"
Write-Host "REPO=$RepoName"
Write-Host "VISIBILITY=$Visibility"

function Has-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

try {
    if (!(Has-Command "git")) {
        if (!(Has-Command "winget")) { throw "Git is missing and winget is unavailable." }
        Write-Host "INSTALLING_GIT=YES"
        winget install --id Git.Git -e --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw "Git installation failed." }
        $env:Path += ";$env:ProgramFiles\Git\cmd"
    }

    if (!(Has-Command "gh")) {
        if (!(Has-Command "winget")) { throw "GitHub CLI is missing and winget is unavailable." }
        Write-Host "INSTALLING_GITHUB_CLI=YES"
        winget install --id GitHub.cli -e --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw "GitHub CLI installation failed." }
        $env:Path += ";$env:ProgramFiles\GitHub CLI"
    }

    Write-Host "SECRET_FILE_CHECK=START"
    $bad = Get-ChildItem -LiteralPath $Root -Recurse -File -Force -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match '^(\.env|credentials\.json|secrets\.json|FIRST-LOGIN\.txt)$' -or
        $_.Extension -in @('.pem','.pfx','.p12','.key')
    }
    if ($bad) {
        Write-Host "SECRET_FILE_CHECK=FAIL"
        $bad | ForEach-Object { Write-Host "BLOCKED_FILE=$($_.FullName)" }
        throw "Potential secret files exist. Remove or review them before publishing."
    }
    Write-Host "SECRET_FILE_CHECK=PASS"

    gh auth status *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "GITHUB_LOGIN=REQUIRED"
        Write-Host "A browser login will open. Sign in to the GitHub account that should own Agape."
        gh auth login --hostname github.com --git-protocol https --web
        if ($LASTEXITCODE -ne 0) { throw "GitHub login failed." }
    }
    Write-Host "GITHUB_LOGIN=PASS"

    if (!(Test-Path -LiteralPath (Join-Path $Root ".git"))) {
        git init
        git branch -M main
    }

    git add .
    $status = git status --porcelain
    if ($status) {
        git commit -m "Recover Agape V3.1 source codebase"
        if ($LASTEXITCODE -ne 0) {
            $name = gh api user --jq .login
            git config user.name $name
            git config user.email "$name@users.noreply.github.com"
            git commit -m "Recover Agape V3.1 source codebase"
        }
    }

    $existing = gh repo view $RepoName --json nameWithOwner -q .nameWithOwner 2>$null
    if ($LASTEXITCODE -eq 0 -and $existing) {
        Write-Host "GITHUB_REPO_EXISTS=$existing"
        $remote = git remote get-url origin 2>$null
        if (!$remote) { git remote add origin "https://github.com/$existing.git" }
    }
    else {
        if ($Visibility -eq "public") {
            gh repo create $RepoName --public --source . --remote origin
        }
        else {
            gh repo create $RepoName --private --source . --remote origin
        }
        if ($LASTEXITCODE -ne 0) { throw "GitHub repository creation failed." }
    }

    git push -u origin main
    if ($LASTEXITCODE -ne 0) { throw "Git push failed." }

    $url = gh repo view --json url -q .url
    Write-Host "GITHUB_PUSH=PASS"
    Write-Host "REPOSITORY=$url"
    Write-Host "FINAL_RESULT=PASS"
    Start-Process $url
}
catch {
    Write-Host "FINAL_RESULT=FAIL"
    Write-Host "ERROR=$($_.Exception.Message)"
    exit 1
}
