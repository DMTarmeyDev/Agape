& {
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Build = 'AGAPE-MAIN-HOST-R1'
$ServiceName = 'AgapeMainHost'
$DisplayName = 'Agape Main Host'
$TaskName = 'Agape Main Host User Worker'
$TaskPath = '\Agape\'

$CorePort = 8797
$WorkPort = 8820
$CoreUrl = 'http://localhost:8797/'
$WorkUrl = 'http://localhost:8820/'

$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
$IsAdmin = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $IsAdmin) {
    Write-Host 'ADMIN_ELEVATION=REQUIRED' -ForegroundColor Yellow
    Write-Host 'Approve the Windows UAC prompt once.' -ForegroundColor Yellow

    $PowerShellExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $ArgLine = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath.Replace('"','""') + '"'

    $Elevated = Start-Process `
        -FilePath $PowerShellExe `
        -ArgumentList $ArgLine `
        -Verb RunAs `
        -Wait `
        -PassThru

    Write-Host ('ELEVATED_INSTALL_EXIT_CODE=' + $Elevated.ExitCode)
    exit $Elevated.ExitCode
}

Write-Host 'ADMIN_ELEVATION=PASS' -ForegroundColor Green

$UserIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$UserAccount = $env:USERDOMAIN + '\' + $env:USERNAME
$UserSid = ([Security.Principal.NTAccount]$UserAccount).Translate([Security.Principal.SecurityIdentifier]).Value

$LocalAppData = [Environment]::GetFolderPath('LocalApplicationData')
$Documents = [Environment]::GetFolderPath('MyDocuments')
$Programs = [Environment]::GetFolderPath('Programs')
$Desktop = [Environment]::GetFolderPath('Desktop')
$Startup = [Environment]::GetFolderPath('Startup')

$CoreRoot = Join-Path $LocalAppData 'DMT-Core-V3.1\SecondBrain\dmt-second-brain'
$CoreLauncher = Join-Path $CoreRoot 'START-DMT-SECOND-BRAIN.ps1'
$WorkLauncher = Join-Path $CoreRoot 'OPEN-AGAPE-WORK-ENGINE.ps1'
$WorkRoot = Join-Path $CoreRoot 'agape-systems-engine'

$HostRoot = Join-Path $env:ProgramData 'Agape\MainHost'
$LogRoot = Join-Path $HostRoot 'logs'
$BackupRoot = Join-Path $HostRoot ('backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$ConfigPath = Join-Path $HostRoot 'main-host-config.json'
$WorkerPath = Join-Path $HostRoot 'AGAPE-MAIN-HOST-USER-WORKER.ps1'
$ServiceSourcePath = Join-Path $HostRoot 'AgapeMainHostService.cs'
$ServiceExe = Join-Path $HostRoot 'AgapeMainHostService.exe'
$HeartbeatPath = Join-Path $HostRoot 'heartbeat.json'
$StatusPath = Join-Path $HostRoot 'status.json'
$StopRequestPath = Join-Path $HostRoot 'stop.request'
$OpenMainPath = Join-Path $HostRoot 'OPEN-AGAPE-MAIN.ps1'
$OpenWorkPath = Join-Path $HostRoot 'OPEN-AGAPE-BACKGROUND-JOBS.ps1'
$StatusHelperPath = Join-Path $HostRoot 'STATUS-AGAPE-MAIN-HOST.ps1'
$RestorePath = Join-Path $HostRoot 'RESTORE-PREVIOUS-AUTOSTART.ps1'
$InstallResultPath = Join-Path $HostRoot 'INSTALL-RESULT.json'
$StatePath = Join-Path $HostRoot 'previous-autostart-state.json'

$OldBackgroundService = 'AgapeBackground'
$OldBackgroundTaskName = 'Agape Background User Worker'
$OldBackgroundTaskPath = '\Agape\'
$OldWorkTaskName = 'Agape Work Engine'
$HostModeWatchdogTask = 'Agape-HostMode-Watchdog'
$OldStartupWork = Join-Path $Startup 'Agape Work Engine.cmd'

function Say([string]$Name,[string]$Value,[string]$Color='Cyan') {
    Write-Host ("{0}={1}" -f $Name,$Value) -ForegroundColor $Color
}

function Write-Utf8NoBom([string]$Path,[string]$Text) {
    [IO.File]::WriteAllText($Path,$Text,[Text.UTF8Encoding]::new($false))
}

function Test-Json([string]$Url,[int]$Timeout=3) {
    try {
        return Invoke-RestMethod -Uri $Url -TimeoutSec $Timeout
    }
    catch {
        return $null
    }
}

function Wait-Json([string]$Url,[int]$Seconds=45) {
    $Deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $Deadline) {
        $R = Test-Json $Url 2
        if ($R) { return $R }
        Start-Sleep -Milliseconds 500
    }
    return $null
}

function Get-PortPid([int]$Port) {
    $Rows = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    if ($Rows.Count -eq 0) { return $null }
    $Ids = @($Rows | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($Ids.Count -ne 1) {
        throw ("MULTIPLE_PIDS_ON_PORT_" + $Port + "=" + ($Ids -join ','))
    }
    return [int]$Ids[0]
}

function Stop-VerifiedCore {
    $PidValue = Get-PortPid $CorePort
    if (-not $PidValue) { return }

    $Version = Test-Json 'http://127.0.0.1:8797/api/version' 3
    if (-not $Version) {
        throw ("REFUSE_STOP_UNVERIFIED_CORE_PID=" + $PidValue)
    }

    $ProjectPath = ''
    try { $ProjectPath = [IO.Path]::GetFullPath([string]$Version.project_path) } catch {}

    if ($ProjectPath -and $ProjectPath -ne [IO.Path]::GetFullPath($CoreRoot)) {
        throw ("REFUSE_STOP_WRONG_CORE PROJECT=" + $ProjectPath)
    }

    Stop-Process -Id $PidValue -Force -ErrorAction Stop
    Say 'OLD_CORE_STOP' ("PASS_PID_" + $PidValue) 'Yellow'
    Start-Sleep -Seconds 1
}

function Stop-VerifiedWork {
    $PidValue = Get-PortPid $WorkPort
    if (-not $PidValue) { return }

    $Health = Test-Json 'http://127.0.0.1:8820/api/health' 3
    if (-not $Health -or -not $Health.ok) {
        throw ("REFUSE_STOP_UNVERIFIED_WORK_PID=" + $PidValue)
    }

    $Proc = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $PidValue) -ErrorAction SilentlyContinue
    $Cmd = [string]$Proc.CommandLine

    if (
        -not $Cmd -or
        (
            $Cmd.IndexOf($CoreRoot,[StringComparison]::OrdinalIgnoreCase) -lt 0 -and
            $Cmd.IndexOf('agape-systems-engine',[StringComparison]::OrdinalIgnoreCase) -lt 0
        )
    ) {
        throw ("REFUSE_STOP_WORK_IDENTITY PID=" + $PidValue + " COMMAND=" + $Cmd)
    }

    Stop-Process -Id $PidValue -Force -ErrorAction Stop
    Say 'OLD_WORK_STOP' ("PASS_PID_" + $PidValue) 'Yellow'
    Start-Sleep -Seconds 1
}

function Get-TaskState([string]$Name,[string]$Path='\') {
    $T = Get-ScheduledTask -TaskName $Name -TaskPath $Path -ErrorAction SilentlyContinue
    if (-not $T) { return $null }
    return [ordered]@{
        exists = $true
        state = [string]$T.State
        enabled = ([string]$T.State -ne 'Disabled')
    }
}

function Disable-TaskIfPresent([string]$Name,[string]$Path='\') {
    $T = Get-ScheduledTask -TaskName $Name -TaskPath $Path -ErrorAction SilentlyContinue
    if (-not $T) {
        Say ("DISABLE_TASK_" + $Name) 'NOT_INSTALLED' 'DarkGray'
        return
    }

    Stop-ScheduledTask -TaskName $Name -TaskPath $Path -ErrorAction SilentlyContinue
    Disable-ScheduledTask -TaskName $Name -TaskPath $Path -ErrorAction SilentlyContinue | Out-Null
    Say ("DISABLE_TASK_" + $Name) 'PASS' 'Green'
}

function Restore-PreviousAutostartInline {
    try {
        if (!(Test-Path -LiteralPath $StatePath -PathType Leaf)) { return }
        $State = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json

        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        Stop-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Confirm:$false -ErrorAction SilentlyContinue
        & sc.exe delete $ServiceName | Out-Null

        if ($State.old_background_service -and $State.old_background_service.exists) {
            $Mode = [string]$State.old_background_service.start_mode
            if ($Mode -eq 'Auto' -or $Mode -eq 'Automatic') {
                Set-Service -Name $OldBackgroundService -StartupType Automatic -ErrorAction SilentlyContinue
            }
            elseif ($Mode -eq 'Manual') {
                Set-Service -Name $OldBackgroundService -StartupType Manual -ErrorAction SilentlyContinue
            }
            elseif ($Mode -eq 'Disabled') {
                Set-Service -Name $OldBackgroundService -StartupType Disabled -ErrorAction SilentlyContinue
            }

            if ([string]$State.old_background_service.status -eq 'Running') {
                Start-Service -Name $OldBackgroundService -ErrorAction SilentlyContinue
            }
        }

        foreach ($Entry in @(
            @{n=$OldBackgroundTaskName;p=$OldBackgroundTaskPath;s=$State.old_background_task},
            @{n=$OldWorkTaskName;p='\';s=$State.old_work_engine_task},
            @{n=$HostModeWatchdogTask;p='\';s=$State.host_mode_watchdog}
        )) {
            if ($Entry.s -and $Entry.s.exists -and $Entry.s.enabled) {
                Enable-ScheduledTask -TaskName $Entry.n -TaskPath $Entry.p -ErrorAction SilentlyContinue | Out-Null
            }
        }

        $OldStartupBackup = Join-Path $BackupRoot 'Agape Work Engine.cmd'
        if (Test-Path -LiteralPath $OldStartupBackup -PathType Leaf) {
            Copy-Item -LiteralPath $OldStartupBackup -Destination $OldStartupWork -Force
        }

        Say 'AUTOMATIC_ROLLBACK_AUTOSTART' 'PASS' 'Yellow'
    }
    catch {
        Say 'AUTOMATIC_ROLLBACK_AUTOSTART' ('FAIL ' + $_.Exception.Message) 'Red'
    }
}

try {
    Write-Host ''
    Write-Host '================================================================' -ForegroundColor Cyan
    Write-Host ' AGAPE MAIN HOST R1' -ForegroundColor Cyan
    Write-Host ' Core + Work Engine + cron + Start Menu + Windows Service' -ForegroundColor Cyan
    Write-Host '================================================================' -ForegroundColor Cyan

    foreach ($Required in @($CoreRoot,$CoreLauncher,$WorkLauncher,$WorkRoot)) {
        if (!(Test-Path -LiteralPath $Required)) {
            throw ("REQUIRED_PATH_MISSING=" + $Required)
        }
    }
    Say 'PREFLIGHT_FILES' 'PASS' 'Green'

    $Tokens=$null
    $ParseErrors=$null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $CoreLauncher,[ref]$Tokens,[ref]$ParseErrors
    )
    if (@($ParseErrors).Count -gt 0) {
        throw ('CORE_LAUNCHER_PARSE_FAIL=' + (@($ParseErrors | ForEach-Object {$_.Message}) -join '; '))
    }

    $Tokens=$null
    $ParseErrors=$null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $WorkLauncher,[ref]$Tokens,[ref]$ParseErrors
    )
    if (@($ParseErrors).Count -gt 0) {
        throw ('WORK_LAUNCHER_PARSE_FAIL=' + (@($ParseErrors | ForEach-Object {$_.Message}) -join '; '))
    }
    Say 'LAUNCHER_PARSE' 'PASS' 'Green'

    New-Item -ItemType Directory -Path $HostRoot,$LogRoot,$BackupRoot -Force | Out-Null

    # Allow the signed-in user to write heartbeat/status/log files.
    $Acl = Get-Acl -LiteralPath $HostRoot
    $SidObj = New-Object Security.Principal.SecurityIdentifier($UserSid)
    $Rule = New-Object Security.AccessControl.FileSystemAccessRule(
        $SidObj,
        'Modify',
        'ContainerInherit,ObjectInherit',
        'None',
        'Allow'
    )
    $Acl.SetAccessRule($Rule)
    Set-Acl -LiteralPath $HostRoot -AclObject $Acl
    Say 'MAIN_HOST_DATA_ACL' 'PASS' 'Green'

    # Capture old autostart state before replacing it.
    $OldSvc = Get-Service -Name $OldBackgroundService -ErrorAction SilentlyContinue
    $OldSvcCim = Get-CimInstance Win32_Service -Filter ("Name='" + $OldBackgroundService + "'") -ErrorAction SilentlyContinue

    $Previous = [ordered]@{
        captured_at = (Get-Date).ToString('o')
        old_background_service = if($OldSvc){
            [ordered]@{
                exists=$true
                status=[string]$OldSvc.Status
                start_mode=if($OldSvcCim){[string]$OldSvcCim.StartMode}else{[string]$OldSvc.StartType}
            }
        } else { [ordered]@{exists=$false} }
        old_background_task = Get-TaskState $OldBackgroundTaskName $OldBackgroundTaskPath
        old_work_engine_task = Get-TaskState $OldWorkTaskName '\'
        host_mode_watchdog = Get-TaskState $HostModeWatchdogTask '\'
        startup_work_file = [ordered]@{
            exists = (Test-Path -LiteralPath $OldStartupWork -PathType Leaf)
            path = $OldStartupWork
        }
    }
    Write-Utf8NoBom $StatePath ($Previous | ConvertTo-Json -Depth 8)

    if (Test-Path -LiteralPath $OldStartupWork -PathType Leaf) {
        Copy-Item -LiteralPath $OldStartupWork -Destination (Join-Path $BackupRoot 'Agape Work Engine.cmd') -Force
    }

    # Stop old supervisors before re-homing Core/Work under the new worker.
    if ($OldSvc) {
        try { Stop-Service -Name $OldBackgroundService -Force -ErrorAction SilentlyContinue } catch {}
        try { Set-Service -Name $OldBackgroundService -StartupType Disabled -ErrorAction Stop } catch {}
        Say 'OLD_BACKGROUND_SERVICE' 'DISABLED' 'Yellow'
    } else {
        Say 'OLD_BACKGROUND_SERVICE' 'NOT_INSTALLED' 'DarkGray'
    }

    Disable-TaskIfPresent $OldBackgroundTaskName $OldBackgroundTaskPath
    Disable-TaskIfPresent $OldWorkTaskName '\'
    Disable-TaskIfPresent $HostModeWatchdogTask '\'

    if (Test-Path -LiteralPath $OldStartupWork -PathType Leaf) {
        Remove-Item -LiteralPath $OldStartupWork -Force
        Say 'OLD_WORK_STARTUP_FILE' 'DISABLED' 'Yellow'
    }

    # Remove/recreate the new task/service cleanly on reinstall.
    Stop-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Confirm:$false -ErrorAction SilentlyContinue

    $ExistingNewSvc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($ExistingNewSvc) {
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
        & sc.exe delete $ServiceName | Out-Null
        Start-Sleep -Seconds 2
    }

    # Stop currently running Core/Work so the new normal-user worker owns them.
    Stop-VerifiedWork
    Stop-VerifiedCore

    Remove-Item -LiteralPath $StopRequestPath -Force -ErrorAction SilentlyContinue

    $Config = [ordered]@{
        schema = 1
        build = $Build
        installed_at = (Get-Date).ToString('o')
        service_name = $ServiceName
        service_display_name = $DisplayName
        user_account = $UserAccount
        user_sid = $UserSid
        core_root = $CoreRoot
        core_launcher = $CoreLauncher
        core_port = $CorePort
        core_url = $CoreUrl
        work_launcher = $WorkLauncher
        work_root = $WorkRoot
        work_port = $WorkPort
        work_url = $WorkUrl
        heartbeat_path = $HeartbeatPath
        status_path = $StatusPath
        stop_request_path = $StopRequestPath
        worker_path = $WorkerPath
        task_name = ($TaskPath + $TaskName)
        browser_required = $false
        cron_engine = 'Agape Work Engine'
        master_service = $true
        note = 'Communications/Account Manager remains separate. This host owns the main Core and Work Engine only.'
    }
    Write-Utf8NoBom $ConfigPath ($Config | ConvertTo-Json -Depth 8)
    Say 'CONFIG_WRITE' 'PASS' 'Green'

    $Worker = @'
#requires -version 5.1
$ErrorActionPreference='SilentlyContinue'

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath=Join-Path $Root 'main-host-config.json'
if(!(Test-Path -LiteralPath $ConfigPath)){exit 2}

$c=Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$Core=[string]$c.core_root
$CoreLauncher=[string]$c.core_launcher
$WorkLauncher=[string]$c.work_launcher
$Heartbeat=[string]$c.heartbeat_path
$Status=[string]$c.status_path
$StopRequest=[string]$c.stop_request_path
$Log=Join-Path $Root 'logs\main-host-worker.log'

function Utc(){[DateTime]::UtcNow.ToString('o')}

function Log([string]$Text){
    try{Add-Content -LiteralPath $Log -Value ((Get-Date).ToString('s')+' '+$Text)}catch{}
}

function Json([string]$Url,[int]$Timeout=3){
    try{return Invoke-RestMethod -Uri $Url -TimeoutSec $Timeout}catch{return $null}
}

function WaitHealth([string]$Url,[int]$Seconds){
    $d=(Get-Date).AddSeconds($Seconds)
    while((Get-Date)-lt $d){
        $r=Json $Url 2
        if($r){return $r}
        if(Test-Path -LiteralPath $StopRequest){return $null}
        Start-Sleep -Milliseconds 500
    }
    return $null
}

function StartPs([string]$Script,[string[]]$Extra=@()){
    if(!(Test-Path -LiteralPath $Script -PathType Leaf)){return $false}
    try{
        $args=@('-NoProfile','-ExecutionPolicy','Bypass','-File',$Script)+$Extra
        Start-Process powershell.exe -ArgumentList $args -WorkingDirectory (Split-Path -Parent $Script) -WindowStyle Hidden | Out-Null
        return $true
    }catch{
        Log ('START_FAIL '+$Script+' '+$_.Exception.Message)
        return $false
    }
}

function EnsureCore{
    $v=Json 'http://127.0.0.1:8797/api/version' 2
    if($v){return $true}

    Log 'CORE_START_REQUESTED'
    [void](StartPs $CoreLauncher @('-Port','8797','-NoBrowser'))
    $v=WaitHealth 'http://127.0.0.1:8797/api/version' 45
    return [bool]$v
}

function EnsureWork{
    $h=Json 'http://127.0.0.1:8820/api/health' 2
    if($h -and $h.ok){return $true}

    Log 'WORK_START_REQUESTED'
    [void](StartPs $WorkLauncher @('-NoBrowser'))
    $h=WaitHealth 'http://127.0.0.1:8820/api/health' 45
    return [bool]($h -and $h.ok)
}

function StopOwnedPort([int]$Port,[string[]]$Markers){
    foreach($row in @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)){
        $pidValue=[int]$row.OwningProcess
        if($pidValue -le 0){continue}
        try{
            $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$pidValue) -ErrorAction Stop
            $cmd=[string]$p.CommandLine
            $owned=$false
            foreach($m in $Markers){
                if($cmd -and $cmd.IndexOf($m,[StringComparison]::OrdinalIgnoreCase) -ge 0){$owned=$true;break}
            }
            if($owned){
                Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
                Log ('STOP_PORT_'+$Port+'_PID='+$pidValue)
            } else {
                Log ('REFUSE_STOP_PORT_'+$Port+'_PID='+$pidValue+'_CMD='+$cmd)
            }
        }catch{
            Log ('STOP_PORT_'+$Port+'_ERROR='+$_.Exception.Message)
        }
    }
}

Log ('WORKER_START PID='+$PID)
Remove-Item -LiteralPath $StopRequest -Force -ErrorAction SilentlyContinue

while($true){
    if(Test-Path -LiteralPath $StopRequest){
        Log 'STOP_REQUEST_SEEN'
        break
    }

    $core=EnsureCore
    $work=EnsureWork

    $schedules=0
    try{
        $st=Json 'http://127.0.0.1:8820/api/status' 3
        if($st -and $st.schedules){$schedules=@($st.schedules).Count}
    }catch{}

    $row=[ordered]@{
        build=[string]$c.build
        updated_at_utc=Utc
        worker_pid=$PID
        windows_user=[Security.Principal.WindowsIdentity]::GetCurrent().Name
        core=$core
        core_port=8797
        work_engine=$work
        work_port=8820
        schedules=$schedules
        stop_requested=$false
    }

    try{[IO.File]::WriteAllText($Heartbeat,($row|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))}catch{}
    try{[IO.File]::WriteAllText($Status,($row|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))}catch{}

    Start-Sleep -Seconds 5
}

# Services.msc Stop should stop the background jobs and main Core that this host owns.
StopOwnedPort 8820 @($Core,'agape-systems-engine')
StopOwnedPort 8797 @($Core,'app.py')

$row=[ordered]@{
    build=[string]$c.build
    updated_at_utc=Utc
    worker_pid=$PID
    windows_user=[Security.Principal.WindowsIdentity]::GetCurrent().Name
    core=$false
    core_port=8797
    work_engine=$false
    work_port=8820
    schedules=0
    stop_requested=$true
}
try{[IO.File]::WriteAllText($Status,($row|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))}catch{}
Log 'WORKER_STOP'
'@
    Write-Utf8NoBom $WorkerPath $Worker
    Say 'USER_WORKER_WRITE' 'PASS' 'Green'

    # Normal-user worker: keeps provider/OAuth/DPAPI/user-file access without creating elevated Python children.
    $Action = New-ScheduledTaskAction `
        -Execute 'powershell.exe' `
        -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $WorkerPath)

    $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserAccount

    $TaskPrincipal = New-ScheduledTaskPrincipal `
        -UserId $UserAccount `
        -LogonType Interactive `
        -RunLevel Limited

    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit ([TimeSpan]::Zero)

    Register-ScheduledTask `
        -TaskName $TaskName `
        -TaskPath $TaskPath `
        -Action $Action `
        -Trigger $Trigger `
        -Principal $TaskPrincipal `
        -Settings $Settings `
        -Description 'Agape Main Host user worker. Runs Core and Work Engine for durable cron/background jobs.' `
        -Force | Out-Null

    Say 'MAIN_HOST_USER_TASK' 'PASS_LIMITED_USER' 'Green'

    $HeartbeatCs = $HeartbeatPath.Replace('"','""')
    $StopCs = $StopRequestPath.Replace('"','""')
    $TaskCs = ($TaskPath + $TaskName).Replace('"','""')

    $ServiceSource = @"
using System;
using System.Diagnostics;
using System.IO;
using System.ServiceProcess;
using System.Threading;

public sealed class AgapeMainHostService : ServiceBase
{
    private Timer timer;
    private readonly string taskName = @"$TaskCs";
    private readonly string heartbeat = @"$HeartbeatCs";
    private readonly string stopRequest = @"$StopCs";

    public AgapeMainHostService()
    {
        ServiceName = "$ServiceName";
        CanStop = true;
        CanShutdown = true;
        AutoLog = true;
    }

    protected override void OnStart(string[] args)
    {
        try { if (File.Exists(stopRequest)) File.Delete(stopRequest); } catch { }
        EnsureWorker();
        timer = new Timer(CheckWorker, null, 15000, 30000);
    }

    protected override void OnStop()
    {
        try { if (timer != null) timer.Dispose(); } catch { }

        try
        {
            File.WriteAllText(stopRequest, DateTime.UtcNow.ToString("o"));
        }
        catch { }

        // Give the user worker time to stop Core and Work Engine cleanly.
        Thread.Sleep(10000);

        RunHidden("schtasks.exe", "/End /TN \"" + taskName + "\"");
    }

    protected override void OnShutdown()
    {
        OnStop();
        base.OnShutdown();
    }

    private void CheckWorker(object state)
    {
        try
        {
            bool stale = !File.Exists(heartbeat);
            if (!stale)
            {
                var age = DateTime.UtcNow - File.GetLastWriteTimeUtc(heartbeat);
                stale = age.TotalSeconds > 60;
            }
            if (stale) EnsureWorker();
        }
        catch
        {
            EnsureWorker();
        }
    }

    private void EnsureWorker()
    {
        try { if (File.Exists(stopRequest)) File.Delete(stopRequest); } catch { }
        RunHidden("schtasks.exe", "/Run /TN \"" + taskName + "\"");
    }

    private static int RunHidden(string exe, string args)
    {
        try
        {
            var p = new Process();
            p.StartInfo.FileName = exe;
            p.StartInfo.Arguments = args;
            p.StartInfo.UseShellExecute = false;
            p.StartInfo.CreateNoWindow = true;
            p.StartInfo.WindowStyle = ProcessWindowStyle.Hidden;
            p.Start();
            p.WaitForExit(15000);
            return p.HasExited ? p.ExitCode : 0;
        }
        catch
        {
            return -1;
        }
    }

    public static void Main()
    {
        ServiceBase.Run(new AgapeMainHostService());
    }
}
"@

    Write-Utf8NoBom $ServiceSourcePath $ServiceSource

    if (Test-Path -LiteralPath $ServiceExe) {
        Remove-Item -LiteralPath $ServiceExe -Force
    }

    $Compiled = $false
    try {
        Add-Type `
            -TypeDefinition $ServiceSource `
            -Language CSharp `
            -ReferencedAssemblies @('System.dll','System.Core.dll','System.ServiceProcess.dll') `
            -OutputAssembly $ServiceExe `
            -OutputType WindowsApplication `
            -ErrorAction Stop

        $Compiled = Test-Path -LiteralPath $ServiceExe
    }
    catch {
        Say 'ADD_TYPE_COMPILE' ('FALLBACK ' + $_.Exception.Message) 'Yellow'
    }

    if (-not $Compiled) {
        $Csc = @(
            "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
            "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe"
        ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

        if (-not $Csc) { throw 'C_SHARP_COMPILER_NOT_FOUND' }

        $Out = & $Csc `
            /nologo `
            /target:winexe `
            /optimize+ `
            /reference:System.ServiceProcess.dll `
            /reference:System.dll `
            /reference:System.Core.dll `
            (('/out:"{0}"' -f $ServiceExe)) `
            $ServiceSourcePath 2>&1

        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $ServiceExe)) {
            throw ('SERVICE_COMPILE_FAIL=' + ($Out -join ' '))
        }
    }
    Say 'SERVICE_COMPILE' 'PASS' 'Green'

    $Bin = '"' + $ServiceExe + '"'
    & sc.exe create $ServiceName binPath= $Bin start= auto DisplayName= ('"' + $DisplayName + '"') | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'SERVICE_CREATE_FAILED' }

    & sc.exe description $ServiceName 'Agape main application host. Keeps Core and the durable Work Engine/cron scheduler alive in the signed-in user context.' | Out-Null
    & sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/15000/restart/30000 | Out-Null
    & sc.exe failureflag $ServiceName 1 | Out-Null

    try {
        New-ItemProperty `
            -Path ('HKLM:\SYSTEM\CurrentControlSet\Services\' + $ServiceName) `
            -Name DelayedAutostart `
            -PropertyType DWord `
            -Value 1 `
            -Force | Out-Null
    } catch {}

    Say 'WINDOWS_SERVICE_INSTALL' 'PASS_AUTO_DELAYED' 'Green'

    $OpenMain = @'
$ErrorActionPreference='SilentlyContinue'
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
$c=Get-Content -LiteralPath (Join-Path $Root 'main-host-config.json') -Raw | ConvertFrom-Json

function Healthy {
    try {
        $v=Invoke-RestMethod -Uri 'http://127.0.0.1:8797/api/version' -TimeoutSec 2
        return [bool]$v
    } catch { return $false }
}

if(-not (Healthy)){
    try{
        Start-ScheduledTask -TaskName 'Agape Main Host User Worker' -TaskPath '\Agape\' -ErrorAction Stop
    }catch{}
    for($i=0;$i -lt 60;$i++){
        Start-Sleep -Milliseconds 500
        if(Healthy){break}
    }
}

if(Healthy){
    Start-Process 'http://localhost:8797/'
}else{
    Add-Type -AssemblyName PresentationFramework -ErrorAction SilentlyContinue
    try{[System.Windows.MessageBox]::Show('Agape Main Host is not running. Open Services and start "Agape Main Host".','Agape Main Host')|Out-Null}catch{}
}
'@
    Write-Utf8NoBom $OpenMainPath $OpenMain

    $OpenWork = @'
$ErrorActionPreference='SilentlyContinue'
try{
    $h=Invoke-RestMethod -Uri 'http://127.0.0.1:8820/api/health' -TimeoutSec 2
    if($h.ok){Start-Process 'http://localhost:8820/';exit 0}
}catch{}
try{Start-ScheduledTask -TaskName 'Agape Main Host User Worker' -TaskPath '\Agape\'}catch{}
Start-Sleep -Seconds 4
Start-Process 'http://localhost:8820/'
'@
    Write-Utf8NoBom $OpenWorkPath $OpenWork

    $StatusHelper = @'
$ErrorActionPreference='SilentlyContinue'
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
$c=Get-Content -LiteralPath (Join-Path $Root 'main-host-config.json') -Raw | ConvertFrom-Json
$s=Get-Service -Name ([string]$c.service_name) -ErrorAction SilentlyContinue
$t=Get-ScheduledTask -TaskName 'Agape Main Host User Worker' -TaskPath '\Agape\' -ErrorAction SilentlyContinue
$h=$null
if(Test-Path -LiteralPath ([string]$c.heartbeat_path)){try{$h=Get-Content -LiteralPath ([string]$c.heartbeat_path)-Raw|ConvertFrom-Json}catch{}}
$core=$false;$work=$false;$schedules=0
try{$v=Invoke-RestMethod -Uri 'http://127.0.0.1:8797/api/version' -TimeoutSec 2;if($v){$core=$true}}catch{}
try{$w=Invoke-RestMethod -Uri 'http://127.0.0.1:8820/api/health' -TimeoutSec 2;if($w.ok){$work=$true}}catch{}
try{$st=Invoke-RestMethod -Uri 'http://127.0.0.1:8820/api/status' -TimeoutSec 2;if($st.schedules){$schedules=@($st.schedules).Count}}catch{}
[ordered]@{
    service=if($s){[string]$s.Status}else{'NOT_INSTALLED'}
    task=if($t){[string]$t.State}else{'NOT_INSTALLED'}
    core_8797=$core
    work_engine_8820=$work
    cron_schedules=$schedules
    heartbeat=$h
} | ConvertTo-Json -Depth 8
'@
    Write-Utf8NoBom $StatusHelperPath $StatusHelper

    $Restore = @'
#requires -version 5.1
$ErrorActionPreference='SilentlyContinue'
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
$State=Get-Content -LiteralPath (Join-Path $Root 'previous-autostart-state.json') -Raw | ConvertFrom-Json

Stop-Service -Name 'AgapeMainHost' -Force -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName 'Agape Main Host User Worker' -TaskPath '\Agape\' -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName 'Agape Main Host User Worker' -TaskPath '\Agape\' -Confirm:$false -ErrorAction SilentlyContinue
sc.exe delete AgapeMainHost | Out-Null

if($State.old_background_service.exists){
    if([string]$State.old_background_service.start_mode -eq 'Auto'){
        Set-Service -Name 'AgapeBackground' -StartupType Automatic -ErrorAction SilentlyContinue
    } elseif([string]$State.old_background_service.start_mode -eq 'Manual'){
        Set-Service -Name 'AgapeBackground' -StartupType Manual -ErrorAction SilentlyContinue
    }
    if([string]$State.old_background_service.status -eq 'Running'){
        Start-Service -Name 'AgapeBackground' -ErrorAction SilentlyContinue
    }
}

foreach($x in @(
    @{n='Agape Background User Worker';p='\Agape\';s=$State.old_background_task},
    @{n='Agape Work Engine';p='\';s=$State.old_work_engine_task},
    @{n='Agape-HostMode-Watchdog';p='\';s=$State.host_mode_watchdog}
)){
    if($x.s -and $x.s.exists -and $x.s.enabled){
        Enable-ScheduledTask -TaskName $x.n -TaskPath $x.p -ErrorAction SilentlyContinue | Out-Null
    }
}

$Backup=Get-ChildItem -LiteralPath $Root -Directory -Filter 'backup-*' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if($Backup){
    $Old=Join-Path $Backup.FullName 'Agape Work Engine.cmd'
    if(Test-Path -LiteralPath $Old){
        $Startup=[Environment]::GetFolderPath('Startup')
        Copy-Item -LiteralPath $Old -Destination (Join-Path $Startup 'Agape Work Engine.cmd') -Force
    }
}

Write-Host 'PREVIOUS_AUTOSTART_RESTORE=PASS' -ForegroundColor Green
'@
    Write-Utf8NoBom $RestorePath $Restore

    # Start Menu + Desktop. Main Agape shortcut opens Core, never Communications.
    $AgapePrograms = Join-Path $Programs 'Agape'
    New-Item -ItemType Directory -Path $AgapePrograms -Force | Out-Null

    $Shell = New-Object -ComObject WScript.Shell

    function New-Link([string]$Path,[string]$Target,[string]$Arguments,[string]$Working,[string]$Description) {
        $L=$Shell.CreateShortcut($Path)
        $L.TargetPath=$Target
        $L.Arguments=$Arguments
        $L.WorkingDirectory=$Working
        $L.Description=$Description
        $L.Save()
    }

    $PowerShellExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

    New-Link `
        (Join-Path $AgapePrograms 'Agape.lnk') `
        $PowerShellExe `
        ('-NoProfile -ExecutionPolicy Bypass -File "' + $OpenMainPath + '"') `
        $HostRoot `
        'Open the main Agape application'

    New-Link `
        (Join-Path $AgapePrograms 'Agape Background Jobs.lnk') `
        $PowerShellExe `
        ('-NoProfile -ExecutionPolicy Bypass -File "' + $OpenWorkPath + '"') `
        $HostRoot `
        'Open Agape Work Engine and cron jobs'

    New-Link `
        (Join-Path $AgapePrograms 'Agape Main Host Status.lnk') `
        $PowerShellExe `
        ('-NoExit -NoProfile -ExecutionPolicy Bypass -File "' + $StatusHelperPath + '"') `
        $HostRoot `
        'Show Agape Main Host service and cron status'

    New-Link `
        (Join-Path $AgapePrograms 'Agape Services.lnk') `
        "$env:WINDIR\System32\services.msc" `
        '' `
        $HostRoot `
        'Open Windows Services'

    New-Link `
        (Join-Path $Desktop 'Agape - Main App.lnk') `
        $PowerShellExe `
        ('-NoProfile -ExecutionPolicy Bypass -File "' + $OpenMainPath + '"') `
        $HostRoot `
        'Open the main Agape application'

    Say 'START_MENU_SHORTCUTS' 'PASS_MAIN_APP_8797' 'Green'

    # Start the master service. It triggers the user worker.
    Start-Service -Name $ServiceName
    Say 'MAIN_HOST_SERVICE_START' 'PASS' 'Green'

    try {
        Start-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath
    } catch {}

    $CoreLive = Wait-Json 'http://127.0.0.1:8797/api/version' 60
    if (-not $CoreLive) { throw 'CORE_8797_START_FAILED' }
    Say 'CORE_8797' 'PASS' 'Green'

    $WorkLive = Wait-Json 'http://127.0.0.1:8820/api/health' 60
    if (-not $WorkLive -or -not $WorkLive.ok) { throw 'WORK_ENGINE_8820_START_FAILED' }
    Say 'WORK_ENGINE_8820' 'PASS' 'Green'

    # Ensure useful baseline cron jobs exist once. Existing schedules are preserved.
    $SchedulesAdded = @()
    try {
        $Status = Invoke-RestMethod -Uri 'http://127.0.0.1:8820/api/status' -TimeoutSec 8
        $Names = @($Status.schedules | ForEach-Object { [string]$_.name })

        if ($Names -notcontains 'Service health every 15 minutes') {
            $Body = @{
                name='Service health every 15 minutes'
                kind='service_health'
                payload=@{recover=$true}
                schedule_type='interval'
                schedule_value='900'
                priority=25
            } | ConvertTo-Json -Depth 5

            Invoke-RestMethod `
                -Uri 'http://127.0.0.1:8820/api/schedules' `
                -Method Post `
                -ContentType 'application/json' `
                -Body $Body `
                -TimeoutSec 8 | Out-Null

            $SchedulesAdded += 'Service health every 15 minutes'
        }

        if ($Names -notcontains 'Nightly incremental code index') {
            $Body = @{
                name='Nightly incremental code index'
                kind='code_index'
                payload=@{root=$CoreRoot;max_files=5000}
                schedule_type='daily'
                schedule_value='02:00'
                priority=10
            } | ConvertTo-Json -Depth 5

            Invoke-RestMethod `
                -Uri 'http://127.0.0.1:8820/api/schedules' `
                -Method Post `
                -ContentType 'application/json' `
                -Body $Body `
                -TimeoutSec 8 | Out-Null

            $SchedulesAdded += 'Nightly incremental code index'
        }

        Say 'CRON_BASELINE' 'PASS' 'Green'
    }
    catch {
        Say 'CRON_BASELINE' ('WARN ' + $_.Exception.Message) 'Yellow'
    }

    $FinalStatus = $null
    try { $FinalStatus = Invoke-RestMethod -Uri 'http://127.0.0.1:8820/api/status' -TimeoutSec 8 } catch {}
    $ScheduleCount = if($FinalStatus -and $FinalStatus.schedules){@($FinalStatus.schedules).Count}else{0}

    $Service = Get-Service -Name $ServiceName -ErrorAction Stop
    $Task = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction Stop

    if ($Service.Status -ne 'Running') { throw 'MAIN_HOST_SERVICE_NOT_RUNNING' }
    if ([string]$Task.State -notin @('Running','Ready')) { throw ('MAIN_HOST_TASK_BAD_STATE=' + [string]$Task.State) }

    $Result = [ordered]@{
        overall='PASS'
        build=$Build
        main_app_url=$CoreUrl
        work_engine_url=$WorkUrl
        service_name=$ServiceName
        service_display_name=$DisplayName
        service_status=[string]$Service.Status
        startup='Automatic Delayed Start'
        user_worker_task=($TaskPath+$TaskName)
        user_worker_runlevel='Limited'
        browser_required=$false
        core_8797=$true
        work_engine_8820=$true
        cron_ready=$true
        cron_schedule_count=$ScheduleCount
        cron_schedules_added=$SchedulesAdded
        old_background_service_disabled=$true
        old_work_engine_autostart_disabled=$true
        host_mode_watchdog_disabled=$true
        communications_8806_role='separate optional app'
        start_menu=(Join-Path $AgapePrograms 'Agape.lnk')
        desktop=(Join-Path $Desktop 'Agape - Main App.lnk')
        status_helper=$StatusHelperPath
        rollback=$RestorePath
        config=$ConfigPath
    }

    Write-Utf8NoBom $InstallResultPath ($Result | ConvertTo-Json -Depth 8)

    # Open the MAIN app, not the Communications Hub.
    Start-Process $CoreUrl

    Write-Host ''
    Write-Host '================ CHATGPT_RESULT_BEGIN ================' -ForegroundColor Cyan
    $Result | ConvertTo-Json -Depth 8
    Write-Host '================= CHATGPT_RESULT_END =================' -ForegroundColor Cyan
}
catch {
    $Message = $_.Exception.Message
    Write-Host ('INSTALL_FAIL=' + $Message) -ForegroundColor Red

    Restore-PreviousAutostartInline

    $Fail = [ordered]@{
        overall='FAIL'
        build=$Build
        error=$Message
        host_root=$HostRoot
        rollback=$RestorePath
    }

    try {
        if (Test-Path -LiteralPath $InstallResultPath) {
            Remove-Item -LiteralPath $InstallResultPath -Force -ErrorAction SilentlyContinue
        }
        Write-Utf8NoBom $InstallResultPath ($Fail | ConvertTo-Json -Depth 6)
    } catch {}

    Write-Host '================ CHATGPT_RESULT_BEGIN ================'
    $Fail | ConvertTo-Json -Depth 6
    Write-Host '================= CHATGPT_RESULT_END ================='

    throw
}
}