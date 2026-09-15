$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$InstallerVersion = 'AGAPE-ARTIFACTS-R3.1-ONEFILE'
$AgapePort = 8797
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$BackupDir = $null
$Project = $null
$DataPath = $null
$Database = $null
$Index = $null
$IndexBackup = $null
$ArtifactStarter = $null
$AppPy = $null
$AppPyBackup = $null
$AppPyRepairState = 'NOT_NEEDED'
$Succeeded = $false
$PreviouslyExisting = @{}

Write-Host ''
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host ' AGAPE ARTIFACTS R3.1 - ONE FILE POWERSHELL INSTALLER' -ForegroundColor Cyan
Write-Host ' Embedded payload. No CMD. No secondary downloads.' -ForegroundColor Cyan
Write-Host ' Does NOT modify the main Agape PowerShell starter.' -ForegroundColor Cyan
Write-Host '================================================================' -ForegroundColor Cyan

function Get-LiveVersion {
    foreach ($Port in @($AgapePort,8787)) {
        try {
            $Version = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/api/version" -f $Port) -TimeoutSec 2
            if ($Version) {
                return [pscustomobject]@{
                    Port = $Port
                    Version = $Version
                }
            }
        }
        catch {}
    }
    return $null
}

function Find-AgapeInstall {
    param([object]$Live)

    if (
        $Live -and
        $Live.Version.project_path -and
        (Test-Path -LiteralPath ([string]$Live.Version.project_path) -PathType Container)
    ) {
        return [IO.Path]::GetFullPath([string]$Live.Version.project_path)
    }

    $Candidates = @(
        (Join-Path $env:LOCALAPPDATA 'DMT-Core-V3.1\SecondBrain\dmt-second-brain'),
        (Join-Path $env:LOCALAPPDATA 'DMT-Core-V3.1-Early-Alpha\SecondBrain\dmt-second-brain')
    )

    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate -PathType Container) {
            return [IO.Path]::GetFullPath($Candidate)
        }
    }

    throw 'AGAPE_V31_INSTALL_NOT_FOUND'
}

function Find-AgapeData {
    param([object]$Live)

    if (
        $Live -and
        $Live.Version.data_path -and
        (Test-Path -LiteralPath ([string]$Live.Version.data_path) -PathType Container)
    ) {
        return [IO.Path]::GetFullPath([string]$Live.Version.data_path)
    }

    $Candidates = @(
        (Join-Path $HOME 'Documents\DMT-CORE-V3.1\second-brain-data'),
        (Join-Path $HOME 'Documents\DMT-CORE-V3.0\second-brain-data'),
        (Join-Path $HOME 'Documents\DMT-AI-BUILDER-STUDIO\second-brain-data')
    )

    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate -PathType Container) {
            return [IO.Path]::GetFullPath($Candidate)
        }
    }

    throw 'AGAPE_DATA_PATH_NOT_FOUND'
}

function Get-PythonExecutable {
    $Python = Get-Command python -ErrorAction SilentlyContinue
    if ($Python) {
        return [IO.Path]::GetFullPath($Python.Source)
    }

    $Known = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe')
    )

    foreach ($Candidate in $Known) {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
            return [IO.Path]::GetFullPath($Candidate)
        }
    }

    throw 'PYTHON_NOT_FOUND'
}

function Test-PortFree {
    param([int]$Port)

    try {
        $Connections = @(
            Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        )
        return ($Connections.Count -eq 0)
    }
    catch {
        try {
            $Client = New-Object System.Net.Sockets.TcpClient
            $Async = $Client.BeginConnect('127.0.0.1',$Port,$null,$null)
            $Connected = $Async.AsyncWaitHandle.WaitOne(150)
            if ($Connected) {
                $Client.EndConnect($Async)
                $Client.Close()
                return $false
            }
            $Client.Close()
            return $true
        }
        catch {
            return $true
        }
    }
}

try {
    if ($MyInvocation.MyCommand.Path) {
        Unblock-File -LiteralPath $MyInvocation.MyCommand.Path -ErrorAction SilentlyContinue
    }

    $Live = Get-LiveVersion
    $Project = Find-AgapeInstall $Live
    $DataPath = Find-AgapeData $Live
    $PythonExe = Get-PythonExecutable

    $Index = Join-Path $Project 'index.html'
    $Manifest = Join-Path $Project 'manifest.json'

    foreach ($Required in @($Index,$Manifest)) {
        if (!(Test-Path -LiteralPath $Required -PathType Leaf)) {
            throw "REQUIRED_FILE_NOT_FOUND=$Required"
        }
    }

    $Database = @(
        (Join-Path $DataPath 'dmt_core.sqlite3'),
        (Join-Path $DataPath 'dmt_memory.sqlite3')
    ) | Where-Object {
        Test-Path -LiteralPath $_ -PathType Leaf
    } | Select-Object -First 1

    if (-not $Database) {
        throw 'AGAPE_DATABASE_NOT_FOUND'
    }

    Write-Host "INSTALL=$Project"
    if ($Live) {
        Write-Host "LIVE_BUILD=$($Live.Version.build)"
        Write-Host "LIVE_PORT=$($Live.Port)"
    }
    else {
        Write-Host 'LIVE_AGAPE=NOT_RUNNING'
    }
    Write-Host "DATA_PATH=$DataPath"
    Write-Host "DATABASE=$Database"
    Write-Host "PYTHON=$PythonExe"

    # ------------------------------------------------------------
    # Backup user data and every file this installer may replace.
    # ------------------------------------------------------------
    $BackupDir = Join-Path (Join-Path $DataPath 'artifact-manager-backups') $Stamp
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

    $IndexBackup = Join-Path $BackupDir 'index.html'
    $DatabaseBackup = Join-Path $BackupDir 'database-before-artifacts-r31.sqlite3'
    Copy-Item -LiteralPath $Index -Destination $IndexBackup -Force
    Copy-Item -LiteralPath $Database -Destination $DatabaseBackup -Force

    if (
        (Get-FileHash -LiteralPath $Database -Algorithm SHA256).Hash -ne
        (Get-FileHash -LiteralPath $DatabaseBackup -Algorithm SHA256).Hash
    ) {
        throw 'DATABASE_BACKUP_HASH_MISMATCH'
    }

    $ManagedNames = @(
        'agape_artifacts_tool.py',
        'START-AGAPE-ARTIFACTS.ps1',
        'agape-artifacts-config.json'
    )

    foreach ($Name in $ManagedNames) {
        $Current = Join-Path $Project $Name
        $PreviouslyExisting[$Name] = Test-Path -LiteralPath $Current -PathType Leaf

        if ($PreviouslyExisting[$Name]) {
            Copy-Item -LiteralPath $Current -Destination (Join-Path $BackupDir ("previous-" + $Name)) -Force
        }
    }

    Write-Host "BACKUP_DIR=$BackupDir"
    Write-Host 'BACKUP=PASS' -ForegroundColor Green

    # ------------------------------------------------------------
    # Stop only an existing Agape Artifacts sidecar.
    # Main Agape is never stopped by this installer.
    # ------------------------------------------------------------
    $InstalledToolPath = Join-Path $Project 'agape_artifacts_tool.py'
    $Needle = $InstalledToolPath.ToLowerInvariant()

    $OldProcesses = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and $_.CommandLine.ToLowerInvariant().Contains($Needle)
        }
    )

    foreach ($Process in $OldProcesses) {
        try {
            Stop-Process -Id ([int]$Process.ProcessId) -Force -ErrorAction Stop
            Write-Host "OLD_ARTIFACT_PROCESS_STOPPED=$($Process.ProcessId)"
        }
        catch {}
    }

    Start-Sleep -Milliseconds 400

    # ------------------------------------------------------------
    # Embedded installer payload. No internet/download step.
    # ------------------------------------------------------------
    $PayloadBase64 = @'
UEsDBBQAAAAIAAZyK10sMi8prAIAAN4FAAAZAAAAU1RBUlQtQUdBUEUtQVJUSUZBQ1RTLnBzMaWU
W0/bMBSA3/0rvCpSWoHTwjRtYkJaBy0rohc1qfaAUGYStzGkduacUiLGf99J0qSUwS5aKkXOuflc
vtOEG75sEorPZbqWEERX1kh/NnqdCkNahFg9Y7TpBiC1mhgxF0aoQNBjarugE5tYE6MXRqTpM6WM
hYI4O9EKpFoJGyNNtQbUuUksgU04RBTf6AHUGmYDdacDnt/iDNFrueQqdHIjYmGMuVwUDsf0XEtV
OpfxbL7giWDcgJzzAFIWFNbOTaoVZudpHf/W0689fUBbJ8kwVTmnzTdNT6RVnhcShOFlpKf5FGov
SwS9EHzeatGHopUQYQOp3T3rTnp+d+oN+t0Tzz8Zj/qDM3809vz+eDY6tckjqarD/M4EsLxdeUNe
v3DK1/QHRcmdMNA3esnOsVJizUyMMRoRQHLUbh8cvnc6+Ds4spqXUsHVJoaTaAOtBiFgsk2uVu9e
pjijPIV8CLeCTbHwoYBIh5TNjKSNPHqbJ7Id8jS61tyEDco8uRR6Ba4I6CEpQuVt24ZjOEGECgx+
XNViZ6nDVSwoE983DWJVg1w2fesc2FUTq4hM4bC2UD5V548LOEGGFAYIIc0zrdWP9UncS6AdUgof
CYIWRPQhb3/XLFKs/FO5AzUv+8WnzVhi9I0IwN7fllK1stTUliEH/oJZLt6xueapeMUuV21vxlG9
dC2K88Xcrftb4cX6uHYFJ81f3DKcp2pVhlj2aomkXeBUaNmEjearNrfoeCoNFqcRk3JbKq1UoV67
kOEIv8gwFAppHK+AjVZxTMhcG0RAHnc+UktSFgP9UBz39qqxlWm7sRAJZUMZxzIVuLJhSg/fdUqM
tmwWI5kKHmb/D2cNaBlvl85C9m9o/iWef0B0F9NnqG6V5bvGFsF98S/G9V0Pz743GPbGM8/+CVBL
AwQUAAAACAA8citdm9cBHbM1AACk0QAAFwAAAGFnYXBlX2FydGlmYWN0c190b29sLnB57X1rc9tG
suh3/QocpLIkE5B62Y6XMuWiJdrWRqJ0SCrZlKNCgQQoYQUSNADqEUX//XT3vPEgqSRbd++9x6mK
CMxMT89Md093T09jmsQzy3Wny2yZBK5rhbNFnGSWN5/HmZeF8Tzd2hLvkuuFl6SBeJ6kd+LnjZfe
ROFYPP4rjefid5yKX4lsmQaTJMhkQfo1CrNgXz4ux4skngRpujVF7HwvC7JwFgjcxLNj4f9/i+cB
q3eTZYtWGiR3QSKqfvDS4PNodDEIvi6DNPvszf0oSBxrdJMEnh/Or7FwSE0YjIWX4UBE+wt4ZAXL
JIL3LZoAUUoP7tfUwVI2NVtn58eXpz2rY9ndT92LXrM7GJ187B6Nhs3BfmvX3roYnP+jdzSCCn1E
/Lg76rqD83PjxYfusCeeL84Hsmx0/mOvDw98+lpZfBvMXeg79aZBfX+vsbUlunNHv1z0hlD3acuC
f/aHy5PTY9ux7EHvtAfg8efR597RjxfnJ/0RPomO3Q/dox8vL2yHNRz1hiN30EM0sNaod3Zx2h1R
+5P+cDS4PBqdnPeHojofnju8PDvrDn7BasOjQa/XH34+JwC9fwpQ56PPvQG0e97a+ql7enLsDkfd
0aWG89HlYNBjyJ12AYsf++c/991P5+fmQFjl7uDo88lPPSr62D05xV8Ienh+OTjqub1/jgAHxFTB
by0esXbrXyn9maTs7002i+jHIt1lBTOf/o69zCaQP55cuMcnA7ffPdPn2HUXjxNvcgNsxNo/ZkBz
Lr3CF/PYD9xZ7C+jIBVot67DjCrfBfM7/CH+ylZZMFuwofjB1FpmE3ce39cbbWoPZLBM5pIjWlgk
mKIFdRutMI2ncTLzsnqDQZjE83kwyQQEeESKYhzYEoVpltQFQTQYn8XLrLO/0xCNWkl87069SRYn
jxqAQXyvIwYVWa+ZN44CdxJHy9k8rcNrh70yx8EmEv8hAtDDl92rhnwH47DgnRUS3FbwEEyWWVCf
1i4G3U9nXd5HOJ/GdfuJHp7tRq3RmgbZ5MaLojoDxWcymKco8RhKGkaONfdQtkCdcB6iBOQ4hlMq
sUAwIgprRiSmSWApX9JIat3TUW9gwQSDrJDIWt3jY+vo/PTyrA8vsTN496QQea5JKHwxqcCLwt8C
F2jAG4O4MxdWrja9y5LHcuxs2zYQBJYFJuf4nXy0+iCgev88GY6GsAtkIa57apljoinyLZAmvU8w
tIvBCQoA68feL1b3cgRSBmCeATs7hVYg7P8FOLrQegR8WqwgunSzx0VAdQih/uXpqXXc+9i9PB1Z
NRIntWJjWjOjTQkGIObX1UlvvL3XbyowTHEFxsjvYgKKdWCPSWERKyCAHABims3CbEWFceLNJzcV
FWBPADHgAxpu5qW3FbVIJKWwtS/Tqpm87JOkLZnL1e24vC5bgxhnpgKhxAMqnl+7QRReh8AHkoQK
PexUD9rL1q0fTH84DVXVYo3L/sl/X/bqSAwOX+6GUUk9Ab8AB4onFEx5oYEi4slobSNg9zac+3Yb
N9J/jmwTBxu1KHcWZDdxZZU0XiaTwI0TmKt5VSU/TCcxjPeRL3RVvchDWghAh4CdraLOzJuHU6SZ
8TKMKtFC4kyCRby6fAZkUFXDW2axKxAPqKNqOiggGaYpkNALGwWZh0LTRW21BK3nFuxos7SuCXT8
V7Jv2FIm2iW7h6KTPylx3QCUg79Q7kq4qnmxEvVZIniLNX2YzzCqYvMqRt2IwYyJ4zN10j/u/TM3
U6H/4Mq1IKTdZG/XOu+rXatubCYNu/EnO2EcVuyGvf/z8BUvF7rIs/mf74wkVKEffJuHzbYqrlYA
qYN6lVMtJlGMyghXtpCKGLNoVOdo1OUI+unAyksNppRdwO7ogVEEJHu+hjf0vrSueE+OokmlV1lg
i1yCVl9/79B/bITQvWPVK1FHbVWQP+wFMAJHaeoNPgdsR3GnYRSwKWWjvAEtjZvPLVaFz+p9CEoJ
VmzFi2Bet5Ox3bC81JqqecaNZ3KznN/ibgPSKqlH3mzse21r2kIDt767s/fK+s7CP4DSWE6t+HfT
Wi7QeKgTlIaui9+0boIHP7wG2V9vQLUFQOcj8cMkIMUfBjO/DpJFEsLqamMSmwYMjVSrbbWPtEja
CoVavg0ewhRIDQY499XbMGXTpWHNsdMnU1SHEcqWyBGANu5voJqBiD7r9k8+oi07/NyFlvbW6snP
4syLoHCHnmClkxA0mI715Yo1ZLZInDk4GaljISIprkKctu696FafDfyHtb60rxCCT419rIxvcRr8
VhTf4/wK48I0Ma/U6KFL4lIAhL6JOr4o0UQQBqFkLvcCmikQ21TVqGAYCGrKcSaQxhdAVZGXhXeB
m8VsiA14tYi8CbDor7+ivbptNwoQcA2QFnLLUtQFada/71ilpXwVWh7Q4tyv1wEXh2o2zB6Dh0mw
yKwe/YEduDiihZem2joKODhraZyASKjzvrQVXChiZjMfRKpbyUfwthXMJ2Dp1+1lNm2+hSkJkiRO
QK7xibIbJe3G9u92yWucdBqhBOqlkzDcAERhJb+xzgIPFe3pMpKC0Rov0SOWwgs0bJMZynErxT8t
6zMwhpXdBGGSAwSCOSNpm8ZcrZ6QqxBFeICWYQp01aQZDfwQnrM4bhkwgOap+F3HQqOKSSj+p7hc
ajp0EbpiTogKojRYAWpsn3YHn3rux5PTnnvWG3XJE3feP/1Fm8TVlKTB+twdfnYv+92fuienqMGV
reXY/nUulJpVMtZhbIAuuZNB72h0PvjFPToH/ayvCS8UwxXCF+aWdo3NhCc1dFiLgtCkyeF98kc7
3wfIsLoh6HA0jJ9AHpMxA5yzYsvIY1cGQZ8MhgFYjWlgfYQh9OPsYwxk3EM2I45hgolNEm6DrtgW
BKIGc/BucV8CMez5qalD1IXHtrCJNWiPdbPgIasTKcLIOozrgfivNRpgv6qpSbi/uGtK2lwkwgXS
d160RCmaG1HrOsjqNtXkPaKjCrcRMIlgRecgmqkpblWTrEgN0Kv+ZLjgbsvEe5uK7kzH3K1j3aH8
pK6E5aT729SgQOkCC2rDcfHKtqGbfEEEHhrU8YPs9QpHXhx1BJpFg8QB7d6MKCbLJMVtjOqk9Xj8
L2a5CYlPv6VrV0zHQ0Ns1Gpamjgrrm3OBiFFMPgUsAKgUk2HQExIV7jTFiU3hMKiafONk0yDLzdU
8d9t8Mi37ttNUNeQwJZiDEW4cjhiM0YMinBodGZREBVGSAtUHKEcXrF7De6WfIY1NIiE8BOSMgHC
kxRIi16noZGl7i2jTJkd2DejSei8QCk5KjWphs8da81VuToe3cA8w1x/uXKA23JD5dhSGx19jleO
edLlbOYlj/Wiop1DjBtmEVFxXqCwQs5aRrnkza1yoWALN1DplD7xYjrHIG+n/eyQOaQAeMnkJkQ1
AfqpgmNM0JPZxGEgCDAdpnhJcxInQfNuV5mIeofp5CaYea5AaLMuc40cAQa7/XtpN+h7j8L5pmOS
1R3V1JWzh298l3UsSn0XDyIBAdONdXw2ah6dD3rNn/ZbO83u6cXnbnOwq/mxdCQ5UbmLJL4L/SDZ
ENlCM0BL/saFiCMwPL3y+Z+ilxFWKog27E1r4PDmXshf5Ef/9T6Y77VeN1ERTNq7rdfjJoqWZDnJ
KqZAnDa8BCOzjYPzeGc8BFG8mKE/YBMsfxhXoJYl3uQW15k287YVgdlPv43pZCzqTkC8ZaISZ9uS
eghH/NSZgvmRCboLyr9yAkH9jx5slk7p5g1aW3CdhNmjUqUI5yohA70C4RgbqU3qLcecN9cRn3kZ
sHdb9/bbkxsPtEY/91a5ffW3wcMC1gqmkeFKlonLAODgQAirusu5rM27kJNv1OM9FQqfc1akgEYH
hGxoxc0ZLUmlVCpjUt9CcPNYSK9IfsfAOf0ih3+FFvPuqioc7yuxWxu2K/5Diy6cwwZUxKHEjChv
UbA4YedMgCdQATHstg3Nq1KcOExhK1kdpt2IeZdGVMWMEWmVzFexr29gCf3ggaIBQF9RK5vFoJJN
p0Fi3d8Ec7SPrWGQQevr1Iq85Ry2iUSDcuOl1jgI8DwINJ4oAgjjR6srD1ExKqSljxA9CEWdWzqI
YMC2wsw2x1nqvkH7hJwvq62VEj9FmV7IwlpcGdbiDvZ33WFvNDrpfxq6H3qfTvo2UT/0U643isVY
yafVpFpYMv3lS1w/Oi5CvuRIQxRXigkTTV1lYk25ubGcu9dhVscTMsf6zkuuUy2mIMbIqEVcsMu4
x9tYU4yLQn6SEVItgG3uVl9sHlLSPLKZZxqhN3i/V+bONPEWtJnEy2yxzDqjZBmYFXAZy17zgJDX
OXDoUIdpn0beddopnlNpeLMzCbd/7v580j8+/7mM1uK0Rc5MpHnY6wpVyKbbMV5rG0nBsYBdt9LM
B8ThTxIugJ3QkYGvWRXcn7G3HQaar8Bau93mDpl5ADspbIDiNFT3yihhSE7EvAOFdUivFh5WlPuK
S2YIEl19d8+0M+oC6DYPJGpU7hgsGodVL5OnrFMcO39jAhjDwt7KN2osZnOd/ilgjWYFZ0Octeoz
gjMEIMonbS13PNnivJl0ZAqMEE/scEo8qXNnu8LTIUApZtHUegHZZGLxHvmsmd7E900+FYatIxHJ
NU6CuybFC2L7z73usdFKIlxoRe/h13WQNZcJKZ88EqBhqGvAtAmeU3HzhUxdzbqFGc6ChEIUFI8m
dv192Ph1fPer/339ffvXFvxt4K8vTbd1leDT+191zVU0wCJZoBEebbZkmLbSAE22Ou+X2cwNnQyp
binNUknrOomXi/qOYd8LrptEINLD6aNOW0xsMH7C32L7ZBKVbYjSU2gUpsvpNHwQbdmTrCCossL3
iSxpKv4JGEZjUANt4UsxivGoENSFye0ihj2wsg4NAJSHJEvxTLBuj4MpGry5Dbq0JvS9XOg1yyWD
HguqD8ebP9alL0t5turEMUnG2As3OjLLlz7befzQu57HaRZO8ClAM3E+IcL96tmNCgz0QFMdBegg
CsAEltMjBkrbgg/izi4HKAJEDWDMwhagyhuyWFmjGWz/ONzV7Xhoa2F3YIGukng4hWF8kN3icZMU
AuqP7Wc6/1REZIuoviZbSalayRpIQ6KSyyqlq2s1V9bS+jFokco43RmFRYdyIZRYDl0a0tyNZayp
KGzmC4sd5KOMZQfazAk3ALpvSkcjcEkoHndVlWZJlZJhG/HQaswYwBt5WbBiPDKqupxIFvNrFqi8
EH+D6yKppKB9BXPYizJzWiX/Getdgr8WqK2wr6T8PNWXLEGec425FfZQUl4M6gNskZNb77qiPVRw
11VAJb0afHVpErDAmrVLLmVM6br9Fi5ovX74jf5csz8gnulvmMYsrDwkN18riKb2c7ELLo2MnU9I
FBYDnCrvlebW0bfD3HlXpO1+oPmmcXQX0LmAOtvnHKZKqw/616rH5E4ybaMIZ6jgMJLjAW0zkh6p
srNNiRZuAkLcqLcVKBggdLXADNbMHfPpvutrbxHoEWZxHNEtAo0LcfdtUsWmrMiuEuTgqOIm2LLT
8LrYneyI3RpQXRXppGSE0nNDkmIDMikHJ4wHQ82y/quTJ8PZLICNPwvARIY9NsGo0tTl8QUY+pV5
4Rzv3hgBeI7FFFgHTNG5H+JBec42li1VjBAqAEZJURVjSG8VqV8ghyzAQj00MKCdEhwHj786LJbK
WrSthUEtm5G98gxSl3RrgfetqhJEzo1U2jB1TT4POa2SH3vEbEuiBgW90p9lzU3q/fornq1kIfB0
daVtVmd7RZUsnD96YUmFtX5DtEJx6CWrSA0kXXyRs6SJJQypYi8rKGudo/Mb6zSOwfZmZ2UsTiGi
s0/Pup3H93OLOUdgKSMfFmvmPcJyhVFkjQNrJkNqlA8PI7zRNBb8wtZVHy7VUAz0h8eLcNQwZVCI
7yK1+typ40r6TussYm3mPbg+EO1NZ5/P9b03z8iHn7OJk4zHjmt3wPI1VlZA02AVCLyN0Nysmru+
GlgX1YVknaxqrayWVbWkNrVq2KT2EBTzlppeXFHKDJrSIrJdCCq/zac5GqQVSeX6zT4N9Qe5ouIW
nnAa4B8kDjOskJMr+WDgRUEA08sq2auFSpphDyQSmbNERE+6hfBJQkCT2qy+EfrI360IeSMih+p4
0KRDMDQd6gkdWFm66cmEgLujpIgW32lWNYM9jbL1gZ9GddzEC/WfiDdSdlEwJesb9E928IeH1rCl
CTU65e4v/HdliF82nsOOkgy58arBXRkFRWkqR4tBHXVsmBPnLCLFN3wuGio87IQJpKL33og5MdbU
2rZAFrJ2XwDKVYNvod9Yx0HTXy4iDFIMrDnMEoi6GwxLHD8yRYnqLefhV4pDenqWZMquApnXz0Ie
WaKQYy2/FDVqJqxLgBh+LJopBqPFg0waQprLzUApnYLTbmJycSErtPA3n8sonoDujAER6pSRu2d1
L63aZdiI6SX26Pl+GcZym9HOIjReNAP5xNkhorbKIV2qBhVdchzk/0NKUG74uS1/QyLSdn5G57st
6+ebOAos4XXcZs4crrngOeQEiQZsX0ttGFbgTTgLIMmjh8h0DJtE5GiLJiltW/iNUm2/UVfbt5Up
0wQbBGRR0izWJ4KGqsfxZImxFLBg2zy8RW5nw6KbmRMb4l3YoOhlhVqZPz4s7B6G6s4gCfugKJiE
sbJCka3sWU0o4wIGpOC2znVXPF3Df6bHuUil4l+J63llZSrcwAm9uknBGy3+VUwVCiOu6+ayFagn
98Nl/9iIuF69easD4G+svZY1CLzIEq5Ri1MlMOjMwys1wJeg7y0pKp5FuuNNbXU3SvGNP3ZJgTJY
x2CBgv+1glUK3twqkuddVojYzQh8QZoJB5RcR/G4bn+XvyXE+1zkPAqL3PFIhUu7emkXZWknCq+G
f2hp91syyMLiii9dcoDfoAmEGbfq+AqyGi5Xgcsll1CfhVqstSlZgurZ1tutliiVwTf5SVRJNWT+
D/bqj83dq5Z1wTzfFho7WZg9biM5gWyxfCGdYRsBpmgSJbKbIxZzKzFLms0rb+Xykz9UNjT/cP40
wCmeAZQE7jFnvJP3zpfU1I8AtPrGa9VKe52KxBvkt+f8V9wi+c7oKIJZsy/9YQ7dcPtZSzBr957F
2n2nwPXSEmnxPCnZQ8bzqrB5bz16PKPKI/+bxfCjQjBUohiucHW/dLj8aJMS6Mi9j6ZbvsqTbkUX
eW/Ponw/XOf10f9xrmbeHXnWhVeABuenf4ihX7es4/h+Trdb2pawB7flEQxj5hb3hGnxrFY6ScIF
is65z2FZLIcE95ehSA3pNhggQNskYBUtfTCxKG0SXuufga09seRtZSYZfIEP3sCUmh9/J2WsrPUi
Cata/WewDPZTZ05/pWkJA0W9eSkCfB1dEd9XuhvnzqDE4RM/i8IzqOciyoIuXB5HIcMAFJ88mJqO
/k872nPkA8Wq8BM5Rzt/K2YKIBD68Z+jHcg5yn9WVCLL5ZU2S4B3vTBPGEZABzTsmMQY+5p9Vzjp
SDaZk8YCyGTarePzn/un591j9wJ0mu6nP6auvkF1Fbck3+rSCVKQeGLT5ZtbyuRWOF5mAduh6QKn
4clWjKxcw2A6AuPHzIhJvPuIt2PQtznHk2MJGC8Q+3vC0CFlJlX+IVASTL4WFh2Vov2pCs/nwXES
3gV2rqbmhKFgMyQ3hOtg++I+y10cf2anlcYeh/UfZe4VrKkK3kOXhxc2yVfMGJC/SWDx1Qs02ylm
h4RSCStVxe5q6y38cLkDjk3pWVyhZ9esNLiqAa1Kxckhu+K+9rBjPzeS1ceUhUGr3gtFpjOmUIzC
oTvqHbvnl6OLS2mmlmRGkd4fs8yMJyYvoapa8BSCoRgkGRsAOYu2KnDk562sGHZnLbpXJeLq2CRg
OLaUvqlj8yctg1TH5rmieJF4KzP3sQb5DE8dfsGELw13JJpuLyZHjKvAWnokdmHZ5cpX+ZXi6xC3
xWL0KRVqF+eKd+v4oO+hUGbx2BL2jJFUjY/PiNAO7sJ4mbJqlel+hrBzHI2s76yPg/Mz5U8w6vwM
amKPBtp5bxScD457A+vDL5j357g3PDIKT0/OTkZaDDtLXSI9q06DJ8QDKaqfMqdsp/8rcba6/WN+
9eOvHACniopxYAxOIUJv1ajw3+XFMSbIKR8SG/qoVB6qvG+d9+WajJZ2rKqKnoarqk4+10+nNuh9
OhmOYLaPSxKu4T9+96dTkjUN/0kGqupSY7eqKkY2sqpKZgaxqloi/Ht1OQZAr6rBAq5X1WBx2zl6
xH+MckH0mUWM+kpU5Iwl5nBQUPD/ySnNySpd5JbNDLvqLi9/YvYgQPULC0u/kg8U/X1VBEPFPNRc
1Obh6fBImAJHfLFD375q5PaYQnSEmdlJ/EtIGFbms6SJqhAP2sSWbH71PHp5BHUmNzASySJADgN2
pgQQQvivlwJiizsCtb+UxmC0fVGplktbW7NGqrS0de902LNqIpdtrVCn1z9+GeHSlshnQ05xQz+3
5nIFMxZTFpOjz93+p96xrc8jt2b6vZ9tLSnbMlmzYZQl6ipLX6f0DsdUWCiXHmkzbBtxlLytzK/p
KDngKIZ3ctkxVybGdPgf0nucgvqyKrmdo8l7R8kDXRwUWhtS1MlLekffHqplCJOujhCjjpKXTi61
YgkMtlM4RkbEnC6qP4kUaQVAPGfay/6r6KhE8Gp0YrxfoYnLUE/ztdImjNdc3zQNBinpjdf5Kzay
o1w9UzgXi6SgNpkXUze6xyfDo/OfeoNfiBlxGTkjnnX7l91Tl6kAgy5GnOdkq07NuZEX3zE6N17t
Yo/F1Kzsxl2+9f2aF4oPjNeVTFG2X0q2WNNX9Z5anHu+v5YVlO21u+Yq5KYh90jphPzlbJHWnwp8
Ysv8rVWqQS4X7Er5YSSWrZjrZ/1ipCb/9RygHaJ1EOstFDmwqYa6VV+RwVGti6WlXhKtDIVCvl2j
TbxckzAyM+ojLTURCqoDvlyfw3KRLOeBS8IU3ZGJn9Zvg2BB0UfidEC9wLAanBAWHtPQ4jmUn1rV
FhcTZzCVvkw7CLS89CIXdmH6qoGvQs7WJvcuaYqLW6kPVapzR+eX/VH9u0b5WuS2ls6OqQDo8/9l
R8WOmbSQt5VLiQEWlvwEG6GhZ4LR07/Lt1oqeUQg76ICFtIuCWIeeuIx+4pn9zRFbdmle3YiCtuG
z4HIMCmCrNNDbltZd4HdgCwBbhn1yD0pqxmUVgRYDOLDf0XBQNNAGuQLqOgYVg90amPVRK5Wvnaq
o3ILoYK38d+fxWSdcbJx14JzKXtAufTDF6uFDAPEb8gQPKfAx9zbl068uXA4l34DgIsJPcqvNJaw
KLXKQtC0YEhu33JtlQ5KZSdXuhQr4o70ulKGMqTjMVZn355RGVgpN4USgBXRmcLWNvFacWbI3aYr
QDnKS5q7b6vjaaSNWM3EfCiKVIr30eNb2MnNrAu2Wj498492a0arq6OGSob2qMeDEyJQzn4YsfJq
gVxaM1QtxMKqenyFVU2+0lA5v/hGHDs6291FHIWTR4xG5x7yj+enx73B0O0O3eFJ/9OplmXEiJAH
XWgcewn2In/X1QV4YhB0l2t0zi6gowvbXGR6I7zWtqbNqHRw9zcBxdLyo62Fl3gzPRMwOhwJulrl
r2hMf2tb3/MS+AGPspggisOTvM1clFx0nHh68mPPem+dD5i3XD2yTyuw50JTKOefrVANDGtzRUNl
QJZVymVqFw9sdkAKZzi2L1+vQIl7o+7NG3PfrpgQc4HeF6HzirmIarkYtJpVwPlaV0PlqdQlOEkR
VRALntlq2LIqB59+xZuYVequulRKHar+sRlID5tvXkhnNvna7da/4nBep+paF1Q373IXbvadnR17
Q52yRFUD8A4fZOE7O9QkL9qIYkrEG73XBRt2lttytc8stK0vUn3PK3Oa1fa8oWpP6SUwuQ8iwIyc
aRhEPhcB0Dq+z9+PMsiP7lqwb22Yd3nM73A4+Q94GBdwwinrVURU8W6LqU+eK/YNoazuMD1VnM01
2lJ/2+BzSsaUTwVxPhFmz06VOfBpcH55geTFK1Yo4Hy0lEReie5VekwZZRZJkxZunY2zxqSxN7BW
hEdkbVcl7uXVvReqM+Yunp2aictQ+m5gZL2IDdllYyhj37LLlYq14fly1FfCynlVaiv0N1epMDpZ
W5TkGqD3FtmtXcayOZbMYzTWPodT1poXljSTfFzRssDneRjCKcX0otxpc0VdlWpRb6XlX8y1E3F3
rogEQiFZYgadjawzdiXmfFhi89ijcP7YPbHKC48+n4xGJ2Ulg/7xydDatsZeEjTRkRxZ8yC7j5Nb
TFFoNvgDEprc6o8uErlmlAn5XLBV9TobipD/w04pec/yPndViPKc/4TRHizBuQrx7p+jznzZP7YN
VkddnDKu6+4t/Gd8N4KqCbdGSe7J6rtbf8kxWvE8++xkiFr/msPs3Q1O2StEacUJmYzwMBybebdM
hffT/qk3OPn4i8uRt0udoGLSio5Q/Fcqmwk9ks9aLlajkK3NigrMZcxzqVZCQZJCE0wOwKjzrB8U
lmXlXxmAg/9EEjCTmViiNaRA5qZnRord4O41+bUZvU2nw3EolG74ha2VdIk0uSZUo6joV56klcVc
rA4VWRmNYURiGKUllF1ybqZI3KR/FUJiyyRs/ITJOAre6ECseOZQdl6hc49aQG0FGafleWcDIDQi
zo4X3eGwMCRetmJk+eO/RoUr7w/qVZJlS8oMbqW/uQppFidAmpxT2lYZ++TNKX49WrYpO97MHTTl
1+yF+zNp+e3NzMmQYv+/FGiLWTAm81fYKupwoEKXN63Rqw0Ggy8wRpXMPZ7sFYMEGWObDkhd70Cf
o5/qthpPfF2huRR3fmrAFpRTSm7jFTiYvsaIcgartholNfLnGjSsXPP8V3LEmF/qn9SzesNMGCnX
oWM6msT+tfeEqkrtzX/p/kWZ4FuEKOgWpPQ+XsNswY6AlokWUqof4WARmx5SeORGw9PAbmnrIJtq
a1nQwS66o8/uoPfflycoPCXZmBfi+UlP8LDw5v4ylXvWahWrorOCsmcGQ7Nhqt1ajjdnE+HAc5mc
cCp4Jidsqn3rjSNr9sSdE+aHxhX6ebSM7If8+7H5NRFWE6EiYodNLUA69kT/+ifDNdeY6ECCeQkJ
C9yhRA+nVvyT3VRsRMXAEx6jkdth6CihRBnTIq9z5CoL+PSwuOycqGcB2mZLeicpvTI6JNdKK+Ft
pRdJfp8qp8pxKMWwkqLvYhzHkd5ZvgJoLjQ5Dd1cMng+DQR65tcYudu2XSQz/lCiWW5IU0WGPOnr
NQsM+b9WqDa1eLsqFwaZT3j1F4Zlym9QV9iAGp8VzUQKV6+I3CwxHFlYgOLPKyOwsnoJ8+PR8X+/
YiE5ixlWaqmuWmmscnqV3LJGu2XfrfP/A0J1njRxbYhpcnJwPBub6qr4OVU6cS5xJW1yCLLJhFTH
qpTNSV5YVE7M+gHiizIufgkHL4QWk4t+aZj6y+bKi/AuKPxyqf2N63yVV3K1zwdc0Ddx6SMSERhG
mBySDmG20yCClXOEJ6ahGRJFXXc9QAnEUCMMcqS5afOaMgE75XigD3WIUfB3fphslmJC1W/NbvGC
IbuWmLILWxZNvhvf8sgEsfHNcPGQH/ATDS2y+lHLneJj3f72l29n3/rNbz9/e/atyA2BkYoisZqG
47Y1LeQpfaIOnrVv+E7Suxe2hRZcKUNFALOzmUf1jS/aOR8/Y5cotu6TMAvYR0zkSmqhlgjSoS+3
zLPOniM+1k4fCOV6l/zgG8yKxma5T6LIpA+c5YKIrFWeMlTpkbfBo/ytf7QOETEKeGIzLG/Bb/lx
RPEFO/zYs5hM/sHne/yafHCP3/6i4ITSb0zmvghN80Nx+eld6xik48/0oj7lJ5r0tboOG08j14pN
7k3g+YZ7LT8sk4X0piAq9K/ycR1aLl55ohLQk7ufwEJwNOW4obcXs/KS5i9Q+omWGftKTI1vOAC9
smKBiNJIP4/OTvELB6i2vPsvP56Q0YMf5jncekdfDoo8XK9gbuMLmFn4g4cjaOsmoMsKahOvcXk6
9l0Y3LOs2/xLux37PvSzm44f3IWToEkPDj8vbaYTD48FEUYWZlFwSCZC7hND77ZZ2da7NHvEv+PY
f3yaecl1OG/vHGCqITzZmvvtb3Z+2N3Z9Q8mMcjB9jfBD4E/fXMwBUSaU28WwsaTPoK5PWsuQ2cY
XMeBdXnidBPAxEm9edpM0d/xvMXI6Gnh+Uiy7d23iwdr79XiwexqsvvD3g8H4zjxMSVYnGXxrL0L
NdM4Ai36m703+29eTQ4WcRpSHBUm57x9PMjiBeD8W5PEa3tfdGbd7KoREcLopmzv7S8eZBX6tLHT
msHG7T/xIf79lbc/fvu8hSmfAMADm9/27uudHcBXQCT6OhDj2dtBoK2Jl/hPxoj83bd7b/mIjKF4
+97rHTHUxPPDZdreBdQkyN03sjc5Fa+ol+sk9J/8MF1E3mMbHw7wf02RoKYJ41jO5mk7CRaBB5oE
INqchpkzC+cwnPruW0DW2Z0mjcYBkEZ7l+EOBJeEEwP73d3d6f7uxtjv6NjvaUCtsUR3HMWTW201
sJ6grb/ve6/GXm7Mr3U46cKbP2mNf6BCkDMS/jQKHmhUQGAH+NC8T+AJ/3fggVk5b9L319oTYKMg
ed4aL6GXOTDPYpk5XFnA7QT2Vs+cC2CCvTwbFGfm1c7r/Td+bmbeahODhM9mnHX9hB8UBZCUeE1h
1FokIZ4Hmzj4rwL/raxyHccmte2+efN6/9XzlhwAp9ydnW8PYPGbN0F4fZO1f6DuM0xdptfgOE/w
440gatviR261oOWNk0HHlVz6w/7bV74+4IM7ENwhyKUmLUEbGPYAceSPUTDNEOpTOWMX+QnWPJ1g
ZrsnPICZRqDYEjcis/Ixvtm7u0FWgSlqYleCud++ge1+AiVjzyyYTrzX3msouPeSuVniB2/eelCC
wv4J55FN2j7Jg3v8FGkTCHMStFmQ9YFAipGeN3+kCCwAgA7OJ110LsPmLJ7H1No5iucwg17qyFdI
20tYJD7VOE/tfTXRIKX2gAj5RLPiXU1GAXdYO89b77a5jH+3zbccFPZ8AwqSQ9i93t3sVmwTUIDl
JCcPP1DGYccSGY0dLW8kPPAEdQ75k1LH0jNosQxxPIuYSJoMmBFcjhni8g6l7uHW1js/vGOeyY6N
UtUmNLSXwPT0Dt4ydhAFnHFsK55PIiAjqLqcDylA2j485od2oJIOAoyafrfNWpugZFPmre/isYF9
+BM9WPC0phVTfU+Ytm8f9ujRouc1LTFNEe9tEEyTIL3JNUAJiDajDXpbSt+64MOmLcw+hCmFGjRZ
2zBbOLX0p2JCb/YOZVq8YxGBBauxJ6cb+1IhtgICbjjY2WZdDFlOmrtUkZfRh1hSDDM6HN0EKh0D
S7yY0mcVWahcU4a88C8yWn2WbU58eVTPOkf5qCg3okj4iyczWazwaHHkyzDpeZMbmTxV5HsPMRsk
hTFTjnQvpfw1Kv+kNPDB+AWsE0AdVuwGpFcSgM0QTxUuZoK8FYgopmTEO17Nh/n0lYwhLZ7BHZ+Y
opBjUbBuKQYpxAL19RjGutwUXYWlDCNyLBk05FgsRIhglMYC8SyMepIwJonUVeTxozDSWptS3Gl4
F1hnnIoK9Czjr0rJWauoYq4skqHYlJQT3JlwM9ycBwb8WEqSXhkHMDwYp5NKItBdehFPwWizT4OL
jCwWfYPlhmizY4s6QliQPqPBGOGhzyE3Zt7FdBvhkJJSvdvmT+Itz2VVeK8oXRbl4OXydRYgaGny
S8rYl4+qYOvfVCo0zn0GqlCuPmhUBZ4ZlIWGdGZltnnHPUtVMz1kZyb5Drg/utBDzr9chV/VoogM
AYWCj92T097xy1AfIWfke+bHPsU57w6LC4G9Fl6iWxGXfhU6JgeWsNwOslwFf6DfTbRhGhponJM6
6rZW09oDbm3k2OXjMopI+uJxEJfv5L57KS5C4dbQ6dN5m9kfvQPVY7FMQNUNUHiIlmaPkTcOokM+
RHYxhST8OH6w9ZXiB2b2odUTV7LRPTNdUmI2EcCkwpRxZ0gDED2sg80Gt069YrgI+cZUF/Zb111e
qo6UawhK6VPLzy7V5KZ6yF4WaRyWGzArE4RCsMJ+C2SBs55W8eH/isy/VGSyNSkXmeaqsJOq6oX5
z5avbJzHMnx85VCV/oODrh5yv/dzCSWKSL5CkR7vVijkBzMrx1Nqsih3vX3IWK+E93PMzEz4as2K
i1Z0U8gxZ8yCFd7Yd1miHqj48ARGBX/wJzK5fOh7M/XASE0+yhWhNzmAI9Igec2fWHoP+fwj2CDy
4Zwu8ZTBGIa/qc4/hQre8HN37/Ub+Yh7mHzoMrXchAdPcshYok3HuwzteiI0YYN8gBe0yzCLnzcS
M5oXydvC9mZZfg+3oiCzRuc/9vqdWu1ga2u6nBNKFljO9bsGOtK5T32YJbC91O86nTlsqe9rtfad
+j7g9pe/vTu0a1fb186kc8gPS2p/q7Vrf/Nmi4OaU3uHv6MMfx7iz2v6aePPr8sYH+yaDQ/f7P/9
AI/en79MrhqNg61nDadZeo04iXzkGFHSiwL8+eHxxK/XuL1ca7Rwyz3ijvS7A4DhpY/ziSUhQct/
pPG8vkwiGuMEFgGsp45374WZRaevVHYgy3xeltBJWJ1Kwmn9v5JWfGv9/rvlw99OpzOlwwgwCPHQ
eB7cW+xM1G9R2DVWrNc+j0YXVu17Su2JZ/IES2SooBHnsAVFQqLr4DKvwtlhk8+iOtu1i/PhiAfY
M/9L2hanIzU+Q01kIlgIb8GMVuhyGwcp4/Jr/2yy5LNSBjRHmDO71ibKYUcjrDJi1/7H8LxPcXbz
a4w5w3e///70jEc8z/8hU4oSbQjkgnl8tNkUKAn6qG17ixBkI1WsEVTGLH6LsoZXgT5WN93WAZeO
l5o+NSH0oF9DwvlTxWnGitlozbIZNi1eHspV0uqwki3LquQrDcVWOJ8HCR6CdRiP69KeefBBGI11
FW98SB6tw9r3KFP8lnlNrPF9jfuzmIyqfb8Sbj+4L0AMW7A//v77zgtBfYZRWUcsALUEpr6Jvhz4
GQteLYHL99+Xgzz1YOF+pKTOn+K4gHKatXIa0Mu7EMaGNDWKq1dxf+8PzJDw/31E11i+o1nYouji
PwH3DAOiSyFTqHQZ5NVsIBhmcy4gZ7pEQGhB2lnLPipBHK8WufxeONpugp+oAs0NjMHCSFueVvpC
wEOYu5lXBJnSe5ED7YVAP4BlirENm08Jb/DCfi6SGI8fkiL63MmINyapxgsBf0QePIv9IFo1hD19
CFPM5TfDJi8fBJ2kvKw7EZ34R3r8GHj0GcHitE1ZSYXIJrZBRRLVLsERY3EkILegNsK1JA40GuEU
FWd49uFZd3T02VrBq9bv5TDkoZ59eNkHkxVs3t6xxSW4AsivHGwEUhwg2sJq0vBiAt4AwyYCVBis
EDwsYB0Cn2/BpFbxmw+wY3+5arSiYH6d3TSYOkY3F77v4MQlhwYS/NSnx+Fpx3caZH6Toi3GYVkc
z1VosNwRNceqNYxB8FuAfCDLuYTB5459u3PtIMaHl7KpuOlh0IBEsqoLHUGJVqV8loRmCGjEqUpN
02xapabxxDGV3bBy6INM+d9/r9WUXkV+vMqWyi9V3ppHBK9pzwzbcggqmc0aINIcNuFU6qqMOUhh
laF67/lMAU9gmFpwOTg5imeLeI6xyKyswbnqbzQxpRUplYuoJmKxSyEy1V5UVUMtra0lXrGshjYy
tEaqZ0e3qplCjvU1cuKzpOmxnBGmcYKHiXWvc8iYgVNEojpjOWN5f/ValrAe5PKDNO/0l7NxkNS9
lro8ijLmcHfn1dvXP7zhfPPeqpdUbGzzWmAAxx/Dh8Cv7wFjW2cfRDB7G7WimxZFWpRBwK4AyN4r
bPbjBzZWgd91mHXE3T2vpRLtIuk4xnsWWA5YcqeB/rbRSpdjZhzWd5zdnQYgVWP4XbUYcdY/xHEU
ePMG539r26o1DsTVibzyhUI78/lW5bVCpkLRm7JyM4fQyqqU23VlDUGTq+rkLxGvrq3dxlldUdfA
KivJO8ZrhqFnqFlVlS4BryiHZS4tFnsZRsfYFsUldmzZO11WhXZCi5FUw0qQvnJUs9dY2Q074NEn
oQpp6XSrVcSFnM+Deu17ySpEXTJORDpArZWQMLa3As45FK2GomlI2oFMGmRsHygAdX7N32T5FTsi
65HbjZvgvLID4SsnyGSC3AUSrjbFNOOccUmOsqxYR/gZlnqWsD29UbY7y3gelKVZ8sidWul1vYbv
0QJttVqm/BR7lnSXce8N1K85T8+8LsGQ2x80nS1AdSXNyW/pafNAAt4Gi8yhgpL0eFA+j8P0keUH
5mUqFSK2qkqWB01ZkSVfiaGwIcgYIZqhCerA9aDxRLj3BoPzAaIbtLjDs3HwXDKFin5h2YxpXOWO
Yq3eh375toppMjiiEUZq+y11+RjkfQ29Jhap8DWU6/TIVfCNRsigaiPL164eKZUXyYVx6gvohUFr
elGUpxoGqm3hgTitL15vBoaQF6jxnX7DGcvEFW6iB/b7L19qIWC0hS4dGtaDQYV+O/SfERTmC62a
+bKOlFQIfZ4y35zycg5kGivvmLdrsz/Pf4gqynDLn1EXSUGUmcRQirK4YV5zhLdcXftrr/IQqSge
oVlL1cjIhLgGhm4kCAB83ta0NM0D0VZTK9Z2zVxcRnPcQtcOG+rk29GN5HUNKWSigHDez7gWbd4A
AFEcRcC+XmkwsIyDFMv775C7RmToCrmbozjWLC9yWFwp2M0kP/CcBPaO3+lhkt795bhLGIgwAwvU
DGIraGFejS+5sw0nZ0Rfsb28TlDrDWYJ5WSDcfKyKf7DUXcwurywKsbRwEbvtsWZJqgiLPp5m93L
wbs6dEePbvvAjgubWRrUQUb7EX5kjl0hw72us7ezw+/uJR7e+ixcNFt3vazFNs06v+XDrjXxnlop
KD+qf6xXUs5vY9n66Rx9ty93PHcgbxRVdiVBgWEaNI/Y520R1jxuUnaZlY14/6fk4eEXIylPp3ff
aJgNVTtxy02U3KMjh90Vo4ZsIXBdCgthTDzady+YS1y3zacSfUJEG/83z2ECdemzLbn5Yx45no9A
gOCAWRKGAlb2Dsv8sCNv+3Ig7zrWTlkyUrVOooOEcESc6twluKU1ITai7/PiAFp+YKxrA3tEcJS1
6elZfHwhzsgnmBtfukRGoEvqpaOrOKxmnwTRkUqDCfxK8Ro83rN1Wa4kugEt+miwFaMzX7zqT8aY
9Zl1W8fjDDx5HgRfl9Dys4EmpaSOr10up+ppEOGNzBkYFN95ybX+cWmGz5Zs5sfup96IWmi1Fkio
OOplEtFvqtAyk6/JDytiXSqTRYAjffOJytyvaZ1XovdGwtNcwnT6oi6C7Vj2dslHrPl0mjxNyBc+
UaDgTL27EG+xw/9KQNLI8hz+qviVVKpXZJwidisw0U74qwdn7hxsLYv5+/BfVS4wWb4y16qsReEF
CAhJr1jnedXcGmEFLxuTlqJ3XQ9aaubNeigdKHVbWpK7JF5ah0EgL3Sd6JhnF2KRoSTTvtj2FSbJ
Le8E/5nZx3U4KoHSeijcdW2goSXVWQ9AObR1GCoR7QZgGsXX61aRWbv/piXUEqHpYxKZjcRg1qO9
GTKcLfUsmlq+S5Xz4tmxXu28MprruVRyn3LA+z/wrv1XI4QbC8BtEDY7ZdjwvQBDuIqbAcn5kq2A
CX1ZUWTukJtpDtALB1N4WzXbw95weHLed0l+qbxpz0UIr3b2899Zqd6LeAIJpfus22eEB/BlYpB9
bGUz3kFP0cug65kT1/UhLNWX9VCaJ2/tNPFU2f8WUaBl8VLZwFAQOFYxK9wfkGPo2nrZHKmcQCZC
a+eJWeov68zMDvP/vXRjuRxD+UGj6ygee5HFryo4KlcO+4n3JhwLLyGItIsg8zDlCSjS9LvVTa7J
OXRBJVwNZNVanu+DHsHK63azyT15Nl6u/LoM8eth6lM/FW2QRF7cgHLmv6QR0VWugcOCCsCYY03R
dhBafNJiyjy+E5mg+ByKfE5YJIKCGrlvrauMRHplkhUlNXERChVxiPnKuE4yHR72DqMSaaCqP1xF
xyC4pqMblO7h/BpNqyG9rdft3b0fWjvw367NCAHkhrC3OE1QKmq7+6l7oX1FyB3sdwa97vEv0Gwa
LdMbfRFYC4TWoS/34DfbGOiKqmIaZHX1KQSjiTagFv1xp3ES3LEUmyBPXBePll2XZIrrIie4Lhco
jC3+B1BLAwQUAAAACAAGcitdAA8rLdkCAAC6BQAAFQAAAHNldHRpbmdzLXNuaXBwZXQuaHRtbJVU
bW/aMBD+zq9w+ZJkJaGApk6QRKIt65BaWgH7NE2RsQ9wmziZ7dCxtf99ZyCUVnvpEilxLvfy3N1z
Fx75Pulf9m8HSX88HX7sn08nybjTSiaD6XQ4upwkZ4PL4Yj4flwLNVOiMHHNnZeSGZFL1/tZc0oN
RBslmHF6NTF3H4Tk+UOQJH91m3hEgSmV7NXeaBAZVUKvtqKKfB5fRc7SmKLbbLbap8EJ3q1usjdN
bm/G0yRpIqAKKsnyUhoLmOCFMHnOygykCRZgBinY49l6yF2HLmgBPlVGzCkz2ledlq/BGCEX2mdU
ccersJMtJOvRwqq0oj/65plhfkEXsPfoeOTxkewNvpWg1hNIgZlcuc4Xwd9F9Uq3/tXxehX+o0q6
BzOnqT5AY6E+I2EKqIEdGAQiVpUvqxcIHr0h8QMDllKtRzSDaJvU6/9CSlCfptfYqHDZifuVVzLu
BK2wiSLneKNNiBMW8VkpUq4bmEoKVAOe2BLYfZELafCDU0NnKCczyu7LAiUGtNm8siLFxPAoJLKw
3DRbEyo5KVR+h3UksBIcJIMgbBYvoiJt1ylE9bygTJh1Nzht9+a5NL4WP6Dbahff6/EoVxlNic5L
xYDMRQoaQWZU2OYjGOBktiYZlWKOiII7jVSzwakCInNDeFmkgiFCFCGsqgyvscxKY9DSrAvEs/2o
E2xK/XdNyQuQ9fgGn2Rf17C5tYp3TagaF9AC9fj5Euvr2s7suv5f9LcBHS/IJcNc7qOD8Se74bUa
Lo5l47U9sow8bUO+mJmn58mcwULIajItc3GZgI5OnqlsRAYqwpSG0oBa0fTFBiK7a2N2fNzbC3BK
dlNvZ2zzO/5w4hGGHFN7Vxvnu6o8NdrvTzyL7nBD4Ojw9cRgE6MoctKccqwsDu5egXI+WOHhSmgD
yHvXubi5PkcmWRmqA3camyyxGJBaGm9TxkCefYbNarWG/9zHg9HFZhv/AlBLAQIUAxQAAAAIAAZy
K10sMi8prAIAAN4FAAAZAAAAAAAAAAAAAACkgQAAAABTVEFSVC1BR0FQRS1BUlRJRkFDVFMucHMx
UEsBAhQDFAAAAAgAPHIrXZvXAR2zNQAApNEAABcAAAAAAAAAAAAAAKSB4wIAAGFnYXBlX2FydGlm
YWN0c190b29sLnB5UEsBAhQDFAAAAAgABnIrXQAPKy3ZAgAAugUAABUAAAAAAAAAAAAAAKSByzgA
AHNldHRpbmdzLXNuaXBwZXQuaHRtbFBLBQYAAAAAAwADAM8AAADXOwAAAAA=
'@

    $Work = Join-Path $env:TEMP ("AGAPE-ARTIFACTS-R3-" + $Stamp)
    $Extract = Join-Path $Work 'payload'
    $ZipPath = Join-Path $Work 'payload.zip'

    New-Item -ItemType Directory -Path $Extract -Force | Out-Null

    $PayloadText = $PayloadBase64 -replace '\s',''
    [IO.File]::WriteAllBytes(
        $ZipPath,
        [Convert]::FromBase64String($PayloadText)
    )

    Expand-Archive -LiteralPath $ZipPath -DestinationPath $Extract -Force

    $PayloadTool = Join-Path $Extract 'agape_artifacts_tool.py'
    $PayloadStarter = Join-Path $Extract 'START-AGAPE-ARTIFACTS.ps1'
    $PayloadSettings = Join-Path $Extract 'settings-snippet.html'

    foreach ($Required in @($PayloadTool,$PayloadStarter,$PayloadSettings)) {
        if (!(Test-Path -LiteralPath $Required -PathType Leaf)) {
            throw "PAYLOAD_FILE_MISSING=$Required"
        }
    }

    Write-Host 'EMBEDDED_PAYLOAD=PASS' -ForegroundColor Green

    # Validate both embedded code files BEFORE installing them.
    & $PythonExe -m py_compile $PayloadTool
    if ($LASTEXITCODE -ne 0) {
        throw "PYTHON_PAYLOAD_COMPILE_FAILED=$LASTEXITCODE"
    }

    $StarterTokens = $null
    $StarterErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $PayloadStarter,
        [ref]$StarterTokens,
        [ref]$StarterErrors
    ) | Out-Null

    if ($StarterErrors.Count -gt 0) {
        throw "ARTIFACT_STARTER_PARSE_FAILED=$($StarterErrors[0].Message)"
    }

    Write-Host 'PAYLOAD_VALIDATION=PASS' -ForegroundColor Green

    # ------------------------------------------------------------
    # Choose a local port.
    # ------------------------------------------------------------
    $ArtifactPort = $null
    foreach ($CandidatePort in 8799..8808) {
        if (Test-PortFree $CandidatePort) {
            $ArtifactPort = $CandidatePort
            break
        }
    }

    if (-not $ArtifactPort) {
        throw 'NO_FREE_ARTIFACT_PORT_8799_TO_8808'
    }

    Write-Host "ARTIFACT_PORT=$ArtifactPort"

    # ------------------------------------------------------------
    # Install module files.
    # ------------------------------------------------------------
    $ToolPath = Join-Path $Project 'agape_artifacts_tool.py'
    $ArtifactStarter = Join-Path $Project 'START-AGAPE-ARTIFACTS.ps1'
    $ConfigPath = Join-Path $Project 'agape-artifacts-config.json'

    Copy-Item -LiteralPath $PayloadTool -Destination $ToolPath -Force
    Copy-Item -LiteralPath $PayloadStarter -Destination $ArtifactStarter -Force

    [ordered]@{
        module = 'AGAPE-ARTIFACTS-R3.1'
        port = $ArtifactPort
        project = $Project
        data = $DataPath
        database = $Database
        python = $PythonExe
    } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $ConfigPath -Encoding UTF8

    & $PythonExe -m py_compile $ToolPath
    if ($LASTEXITCODE -ne 0) {
        throw "INSTALLED_PYTHON_COMPILE_FAILED=$LASTEXITCODE"
    }

    $InstalledStarterTokens = $null
    $InstalledStarterErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $ArtifactStarter,
        [ref]$InstalledStarterTokens,
        [ref]$InstalledStarterErrors
    ) | Out-Null

    if ($InstalledStarterErrors.Count -gt 0) {
        throw "INSTALLED_STARTER_PARSE_FAILED=$($InstalledStarterErrors[0].Message)"
    }

    Write-Host 'MODULE_INSTALL=PASS' -ForegroundColor Green

    # ------------------------------------------------------------
    # Update Settings only. Do NOT edit app.py or Agape main starter.
    # ------------------------------------------------------------
    $Html = Get-Content -LiteralPath $Index -Raw

    $CleanupPatterns = @(
        '(?s)\s*<!-- AGAPE_ARTIFACTS_R1_UI_BEGIN -->.*?<!-- AGAPE_ARTIFACTS_R1_UI_END -->\s*',
        '(?s)\s*<!-- AGAPE_ARTIFACTS_R2_SETTINGS_BEGIN -->.*?<!-- AGAPE_ARTIFACTS_R2_SETTINGS_END -->\s*',
        '(?s)\s*<!-- AGAPE_ARTIFACTS_R2[12]_SETTINGS_BEGIN -->.*?<!-- AGAPE_ARTIFACTS_R2[12]_SETTINGS_END -->\s*',
        '(?s)\s*<!-- AGAPE_ARTIFACTS_R3_SETTINGS_BEGIN -->.*?<!-- AGAPE_ARTIFACTS_R3_SETTINGS_END -->\s*',
        '(?s)\s*<!-- AGAPE_ARTIFACTS_R31_SETTINGS_BEGIN -->.*?<!-- AGAPE_ARTIFACTS_R31_SETTINGS_END -->\s*'
    )

    foreach ($Pattern in $CleanupPatterns) {
        $Html = [regex]::Replace($Html,$Pattern,"`r`n")
    }

    $SettingsBlock = Get-Content -LiteralPath $PayloadSettings -Raw
    $SettingsBlock = $SettingsBlock.Replace('__ARTIFACT_PORT__',[string]$ArtifactPort)

    $BodyPos = $Html.ToLowerInvariant().LastIndexOf('</body>')
    if ($BodyPos -lt 0) {
        throw 'INDEX_BODY_END_NOT_FOUND'
    }

    $PatchedHtml =
        $Html.Substring(0,$BodyPos) +
        "`r`n" +
        $SettingsBlock +
        "`r`n" +
        $Html.Substring($BodyPos)

    [IO.File]::WriteAllText(
        $Index,
        $PatchedHtml,
        (New-Object System.Text.UTF8Encoding($false))
    )

    $IndexCheck = Get-Content -LiteralPath $Index -Raw
    if (-not $IndexCheck.Contains('AGAPE_ARTIFACTS_R31_SETTINGS_BEGIN')) {
        throw 'SETTINGS_PATCH_VERIFY_FAILED'
    }

    Write-Host 'SETTINGS_ARTIFACTS_LINK=PASS' -ForegroundColor Green
    Write-Host 'MAIN_AGAPE_STARTER_MODIFIED=NO' -ForegroundColor Green
    Write-Host 'APP_PY_MODIFIED_BY_MODULE_INSTALL=NO' -ForegroundColor Green

    # ------------------------------------------------------------
    # Start Artifacts using its own validated PS1 starter.
    # ------------------------------------------------------------
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ArtifactStarter -NoBrowser

    if ($LASTEXITCODE -ne 0) {
        throw "ARTIFACT_STARTER_EXIT=$LASTEXITCODE"
    }

    $ArtifactBase = "http://127.0.0.1:$ArtifactPort"
    $Ready = $null

    for ($i=0; $i -lt 80; $i++) {
        Start-Sleep -Milliseconds 250
        try {
            $Ready = Invoke-RestMethod -Uri "$ArtifactBase/api/dashboard" -TimeoutSec 2
            if ($Ready -and [string]$Ready.module -eq 'AGAPE-ARTIFACTS-R3.1') {
                break
            }
        }
        catch {}
    }

    if (-not $Ready) {
        throw 'ARTIFACT_SERVICE_START_FAILED'
    }

    Write-Host 'ARTIFACT_SERVICE=PASS' -ForegroundColor Green

    # ------------------------------------------------------------
    # Initial discovery and live validation.
    # ------------------------------------------------------------
    $Session = Invoke-RestMethod -Uri "$ArtifactBase/api/session" -TimeoutSec 5
    if (-not $Session.token) {
        throw 'ARTIFACT_SESSION_TOKEN_FAILED'
    }

    $Headers = @{
        'X-Agape-Artifacts-Token' = [string]$Session.token
    }

    $Scan = Invoke-RestMethod `
        -Uri "$ArtifactBase/api/scan" `
        -Method Post `
        -Headers $Headers `
        -ContentType 'application/json' `
        -Body '{}' `
        -TimeoutSec 300

    if (-not $Scan.ok) {
        throw 'INITIAL_ARTIFACT_DISCOVERY_FAILED'
    }

    $Dashboard = Invoke-RestMethod -Uri "$ArtifactBase/api/dashboard" -TimeoutSec 60
    $Page = Invoke-WebRequest -Uri $ArtifactBase -UseBasicParsing -TimeoutSec 15

    if ($Page.Content -notmatch '<title>Agape Artifacts R3\.1</title>') {
        throw 'ARTIFACT_PAGE_VERIFY_FAILED'
    }

    Write-Host "ARTIFACT_DISCOVERY=PASS OBSERVATIONS=$($Scan.observations)" -ForegroundColor Green
    Write-Host "AUTO_ARTIFACTS_PRUNED=$($Scan.auto_records_pruned)"
    Write-Host "MANUAL_RECORDS_PRESERVED=$($Scan.manual_records_preserved)"
    Write-Host "ARTIFACT_CANDIDATES=$($Scan.candidate_count)"
    Write-Host 'ARTIFACT_PAGE=PASS' -ForegroundColor Green

    # ------------------------------------------------------------
    # Remove the legacy R1 app.py hook only by restoring an app.py
    # whose SHA256 exactly matches manifest.json. No guessed edits.
    # ------------------------------------------------------------
    $AppPy = Join-Path $Project 'app.py'
    $ManifestData = Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
    $ExpectedAppHash = $null

    if ($ManifestData.files) {
        $AppProperty = @(
            $ManifestData.files.PSObject.Properties |
            Where-Object {
                (($_.Name -replace '\\','/').ToLowerInvariant()) -eq 'app.py'
            }
        ) | Select-Object -First 1

        if ($AppProperty) {
            $ExpectedAppHash = [string]$AppProperty.Value
        }
    }

    if (
        $ExpectedAppHash -and
        (Test-Path -LiteralPath $AppPy -PathType Leaf)
    ) {
        $CurrentAppHash = (Get-FileHash -LiteralPath $AppPy -Algorithm SHA256).Hash

        if ($CurrentAppHash -eq $ExpectedAppHash) {
            $AppPyRepairState = 'ALREADY_MANIFEST_CLEAN'
        }
        else {
            $CurrentAppText = Get-Content -LiteralPath $AppPy -Raw

            if (
                $CurrentAppText.Contains('# AGAPE_ARTIFACTS_R1_HOOK_BEGIN') -and
                $CurrentAppText.Contains('# AGAPE_ARTIFACTS_R1_HOOK_END')
            ) {
                $LocalCore = Split-Path (Split-Path $Project -Parent) -Parent
                $CandidateApps = @()

                $CoreBackups = Join-Path $LocalCore 'backups'
                if (Test-Path -LiteralPath $CoreBackups -PathType Container) {
                    $CandidateApps += @(
                        Get-ChildItem -LiteralPath $CoreBackups -Directory -ErrorAction SilentlyContinue |
                        Where-Object { $_.Name -like 'before-artifacts-r1-*' } |
                        Sort-Object LastWriteTime -Descending |
                        ForEach-Object { Join-Path $_.FullName 'app.py' }
                    )
                }

                $SecondBrain = Split-Path $Project -Parent
                $CandidateApps += @(
                    Get-ChildItem -LiteralPath $SecondBrain -Directory -ErrorAction SilentlyContinue |
                    Where-Object { $_.Name -like 'rollback-before-*' } |
                    Sort-Object LastWriteTime -Descending |
                    ForEach-Object { Join-Path $_.FullName 'app.py' }
                )

                $VerifiedCleanApp = $null

                foreach ($CandidateApp in $CandidateApps) {
                    if (!(Test-Path -LiteralPath $CandidateApp -PathType Leaf)) {
                        continue
                    }

                    try {
                        $CandidateHash = (Get-FileHash -LiteralPath $CandidateApp -Algorithm SHA256).Hash
                        if ($CandidateHash -eq $ExpectedAppHash) {
                            $VerifiedCleanApp = $CandidateApp
                            break
                        }
                    }
                    catch {}
                }

                if ($VerifiedCleanApp) {
                    $AppPyBackup = Join-Path $BackupDir 'app.py.before-r1-cleanup'
                    Copy-Item -LiteralPath $AppPy -Destination $AppPyBackup -Force
                    Copy-Item -LiteralPath $VerifiedCleanApp -Destination $AppPy -Force

                    $RestoredHash = (Get-FileHash -LiteralPath $AppPy -Algorithm SHA256).Hash
                    if ($RestoredHash -ne $ExpectedAppHash) {
                        Copy-Item -LiteralPath $AppPyBackup -Destination $AppPy -Force
                        throw 'APP_PY_MANIFEST_RESTORE_VERIFY_FAILED_ROLLBACK_APPLIED'
                    }

                    $AppPyRepairState = 'PASS_MANIFEST_VERIFIED_RESTORE'
                }
                else {
                    $AppPyRepairState = 'SKIPPED_NO_MANIFEST_MATCHING_BACKUP'
                }
            }
            else {
                $AppPyRepairState = 'SKIPPED_CHANGED_FOR_NON_R1_REASON'
            }
        }
    }
    else {
        $AppPyRepairState = 'SKIPPED_MANIFEST_APP_HASH_NOT_FOUND'
    }

    Write-Host "APP_PY_R1_REPAIR=$AppPyRepairState"

    # ------------------------------------------------------------
    # PowerShell-only desktop shortcut. No CMD file.
    # ------------------------------------------------------------
    try {
        $ShortcutPath = Join-Path $HOME 'Desktop\Agape Artifacts.lnk'
        $Shell = New-Object -ComObject WScript.Shell
        $Shortcut = $Shell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath = 'powershell.exe'
        $Shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $ArtifactStarter + '"'
        $Shortcut.WorkingDirectory = $Project
        $Shortcut.Save()
        Write-Host "DESKTOP_SHORTCUT=PASS PATH=$ShortcutPath" -ForegroundColor Green
    }
    catch {
        Write-Host "DESKTOP_SHORTCUT=WARN ERROR=$($_.Exception.Message)" -ForegroundColor Yellow
    }

    $Dashboard = Invoke-RestMethod -Uri $ArtifactBase/api/dashboard -TimeoutSec 60

    $Succeeded = $true

    Write-Host ''
    Write-Host '================================================================' -ForegroundColor Green
    Write-Host ' AGAPE ARTIFACTS R3.1 ONE-FILE INSTALL = PASS' -ForegroundColor Green
    Write-Host '================================================================' -ForegroundColor Green
    Write-Host "MODULE=$($Dashboard.module)"
    Write-Host "AGAPE_BUILD=$($Dashboard.manifest.build)"
    Write-Host "ARTIFACT_COUNT=$($Dashboard.artifact_count)"
    Write-Host "MANIFEST_TRACKED_FILES=$($Dashboard.manifest.tracked_files)"
    Write-Host "MANIFEST_UNEXPECTED_CHANGED=$($Dashboard.manifest_integrity.changed)"
    Write-Host "MANIFEST_MISSING=$($Dashboard.manifest_integrity.missing)"
    Write-Host "ARTIFACT_URL=$ArtifactBase"
    Write-Host "DATABASE=$Database"
    Write-Host "DATABASE_BACKUP=$DatabaseBackup"
    Write-Host "APP_PY_R1_REPAIR=$AppPyRepairState"
    Write-Host 'MAIN_AGAPE_STARTER_CHANGED=NO'
    Write-Host 'CMD_FILES_USED=NO'
    Write-Host 'SECONDARY_DOWNLOADS=NO'
    Write-Host 'SETTINGS_ACCESS=Agape -> Settings -> Artifacts'
    Write-Host "AUTO_ARTIFACTS_PRUNED=$($Scan.auto_records_pruned)"
    Write-Host "MANUAL_RECORDS_PRESERVED=$($Scan.manual_records_preserved)"
    Write-Host 'DISCOVERY_POLICY=BUNDLED_MEANINGFUL_OUTPUTS_ONLY'
    Write-Host 'AFTER_REBOOT=Use Desktop shortcut Agape Artifacts'

    Start-Process $ArtifactBase
}
catch {
    Write-Host ''
    Write-Host '================================================================' -ForegroundColor Red
    Write-Host ' AGAPE ARTIFACTS R3.1 ONE-FILE INSTALL = FAIL' -ForegroundColor Red
    Write-Host '================================================================' -ForegroundColor Red
    Write-Host "ERROR=$($_.Exception.Message)" -ForegroundColor Red

    if ($IndexBackup -and $Index -and (Test-Path -LiteralPath $IndexBackup -PathType Leaf)) {
        try {
            Copy-Item -LiteralPath $IndexBackup -Destination $Index -Force
            Write-Host 'INDEX_ROLLBACK=PASS' -ForegroundColor Yellow
        }
        catch {
            Write-Host "INDEX_ROLLBACK=FAIL ERROR=$($_.Exception.Message)" -ForegroundColor Red
        }
    }

    if ($AppPyBackup -and $AppPy -and (Test-Path -LiteralPath $AppPyBackup -PathType Leaf)) {
        try {
            Copy-Item -LiteralPath $AppPyBackup -Destination $AppPy -Force
            Write-Host 'APP_PY_ROLLBACK=PASS' -ForegroundColor Yellow
        }
        catch {
            Write-Host "APP_PY_ROLLBACK=FAIL ERROR=$($_.Exception.Message)" -ForegroundColor Red
        }
    }

    if ($BackupDir -and $Project) {
        foreach ($Name in @(
            'agape_artifacts_tool.py',
            'START-AGAPE-ARTIFACTS.ps1',
            'agape-artifacts-config.json'
        )) {
            try {
                $Target = Join-Path $Project $Name
                $Previous = Join-Path $BackupDir ("previous-" + $Name)

                if ($PreviouslyExisting.ContainsKey($Name) -and $PreviouslyExisting[$Name]) {
                    if (Test-Path -LiteralPath $Previous -PathType Leaf) {
                        Copy-Item -LiteralPath $Previous -Destination $Target -Force
                    }
                }
                else {
                    Remove-Item -LiteralPath $Target -Force -ErrorAction SilentlyContinue
                }
            }
            catch {}
        }

        Write-Host 'MANAGED_FILE_ROLLBACK=ATTEMPTED' -ForegroundColor Yellow
        Write-Host "ROLLBACK_BACKUP=$BackupDir"
    }

    Write-Host 'MAIN_AGAPE_STARTER_CHANGED=NO'
    Write-Host "APP_PY_R1_REPAIR=$AppPyRepairState"
    Write-Host 'CMD_FILES_USED=NO'
    Write-Host 'SECONDARY_DOWNLOADS=NO'

    throw
}
finally {
    if ($Succeeded) {
        Write-Host 'INSTALL_COMPLETE=YES' -ForegroundColor Green
    }
}
