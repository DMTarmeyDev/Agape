param(
    [switch]$NoPrereqInstall,
    [switch]$BuildOnly,
    [switch]$KeepStage
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Build = 'AGAPE-WINDOWS-DESKTOP-R1'
$Port = 8797
$WebView2PackageVersion = '1.0.4191.47'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Downloads = Join-Path $env:USERPROFILE 'Downloads'
$Stage = Join-Path $env:TEMP ("AGAPE-WINDOWS-DESKTOP-R1-$Stamp")
$ProjectDir = Join-Path $Stage 'AgapeDesktop'
$PublishDir = Join-Path $Stage 'publish'
$ReportDir = Join-Path $Downloads ("AGAPE-WINDOWS-DESKTOP-R1-RESULTS-$Stamp")
$SetupName = 'AGAPE-WINDOWS-10-11-R1-SETUP'
$ResultJson = Join-Path $Downloads ("AGAPE-WINDOWS-DESKTOP-R1-RESULT-$Stamp.json")

function Say([string]$Name,[string]$Value,[string]$Color='Cyan') {
    Write-Host ("{0}={1}" -f $Name,$Value) -ForegroundColor $Color
}
function Pass([string]$Name,[string]$Value='PASS') { Say $Name $Value 'Green' }
function Warn([string]$Name,[string]$Value) { Say $Name $Value 'Yellow' }
function Fail([string]$Message) { throw $Message }
function Assert-True($Condition,[string]$Message) { if(-not $Condition){ Fail $Message } }
function Sha([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant() }
function Write-Utf8([string]$Path,[string]$Text) {
    [IO.File]::WriteAllText($Path,$Text,[Text.UTF8Encoding]::new($false))
}
function Get-Json([string]$Uri,[int]$Timeout=10) {
    try { Invoke-RestMethod -Uri $Uri -TimeoutSec $Timeout }
    catch { $null }
}
function Wait-Json([string]$Uri,[int]$Seconds=60) {
    $deadline=(Get-Date).AddSeconds($Seconds)
    while((Get-Date)-lt $deadline){
        $v=Get-Json $Uri 3
        if($v){return $v}
        Start-Sleep -Milliseconds 400
    }
    return $null
}
function Find-Core {
    $v=Get-Json "http://127.0.0.1:$Port/api/version" 4
    if($v -and $v.project_path -and (Test-Path -LiteralPath ([string]$v.project_path) -PathType Container)){
        return [IO.Path]::GetFullPath([string]$v.project_path)
    }
    foreach($p in @(
        (Join-Path $env:LOCALAPPDATA 'DMT-Core-V3.1\SecondBrain\dmt-second-brain'),
        (Join-Path $env:LOCALAPPDATA 'DMT-Core-V3.1-Early-Alpha\SecondBrain\dmt-second-brain')
    )){
        if((Test-Path -LiteralPath $p -PathType Container) -and (Test-Path -LiteralPath (Join-Path $p 'app.py') -PathType Leaf)){
            return [IO.Path]::GetFullPath($p)
        }
    }
    Fail 'AGAPE_LATEST_CORE_NOT_FOUND'
}
function Ensure-Core([string]$Core) {
    $v=Get-Json "http://127.0.0.1:$Port/api/version" 3
    if($v){return $v}
    $launcher=Join-Path $Core 'START-DMT-SECOND-BRAIN.ps1'
    Assert-True (Test-Path -LiteralPath $launcher -PathType Leaf) "CORE_LAUNCHER_NOT_FOUND=$launcher"
    Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$launcher) -WorkingDirectory $Core -WindowStyle Hidden | Out-Null
    $v=Wait-Json "http://127.0.0.1:$Port/api/version" 60
    Assert-True $v 'AGAPE_CORE_START_FAILED'
    return $v
}
function Get-DotNet {
    $cmd=Get-Command dotnet.exe -ErrorAction SilentlyContinue
    if($cmd){return $cmd.Source}
    $p=Join-Path $env:ProgramFiles 'dotnet\dotnet.exe'
    if(Test-Path -LiteralPath $p){return $p}
    return $null
}
function Ensure-DotNet10 {
    $dotnet=Get-DotNet
    if($dotnet){
        $sdks=@(& $dotnet --list-sdks 2>$null)
        if($sdks | Where-Object {$_ -match '^10\.'}){return $dotnet}
    }
    if($NoPrereqInstall){Fail 'DOTNET_10_SDK_NOT_FOUND_AND_INSTALL_DISABLED'}
    $winget=Get-Command winget.exe -ErrorAction SilentlyContinue
    Assert-True $winget 'WINGET_NOT_FOUND_CANNOT_INSTALL_DOTNET_10_SDK'
    Say 'DOTNET_10_SDK' 'INSTALLING'
    & $winget.Source install --id Microsoft.DotNet.SDK.10 -e --silent --accept-package-agreements --accept-source-agreements
    Assert-True ($LASTEXITCODE -in @(0,-1978335189)) "DOTNET_10_INSTALL_FAILED_EXIT=$LASTEXITCODE"
    $dotnet=Get-DotNet
    Assert-True $dotnet 'DOTNET_10_SDK_INSTALL_FINISHED_BUT_DOTNET_NOT_FOUND'
    $sdks=@(& $dotnet --list-sdks 2>$null)
    Assert-True ($sdks | Where-Object {$_ -match '^10\.'}) 'DOTNET_10_SDK_STILL_NOT_FOUND'
    return $dotnet
}
function Find-Iscc {
    $cmd=Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if($cmd){return $cmd.Source}
    foreach($root in @(${env:ProgramFiles(x86)},$env:ProgramFiles)){
        if(!$root){continue}
        $hit=Get-ChildItem -LiteralPath $root -Filter ISCC.exe -Recurse -ErrorAction SilentlyContinue |
            Where-Object {$_.FullName -match 'Inno Setup'} | Select-Object -First 1
        if($hit){return $hit.FullName}
    }
    return $null
}
function Ensure-Inno {
    $iscc=Find-Iscc
    if($iscc){return $iscc}
    if($NoPrereqInstall){Fail 'INNO_SETUP_NOT_FOUND_AND_INSTALL_DISABLED'}
    $winget=Get-Command winget.exe -ErrorAction SilentlyContinue
    Assert-True $winget 'WINGET_NOT_FOUND_CANNOT_INSTALL_INNO_SETUP'
    Say 'INNO_SETUP' 'INSTALLING'
    & $winget.Source install --id JRSoftware.InnoSetup -e --silent --accept-package-agreements --accept-source-agreements
    Assert-True ($LASTEXITCODE -in @(0,-1978335189)) "INNO_SETUP_INSTALL_FAILED_EXIT=$LASTEXITCODE"
    $iscc=Find-Iscc
    Assert-True $iscc 'INNO_SETUP_INSTALL_FINISHED_BUT_ISCC_NOT_FOUND'
    return $iscc
}
function Try-DownloadWebViewBootstrapper([string]$Destination) {
    try {
        Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $Destination -UseBasicParsing -TimeoutSec 60
        if((Test-Path -LiteralPath $Destination -PathType Leaf) -and (Get-Item -LiteralPath $Destination).Length -gt 100000){return $true}
    } catch {}
    Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
    return $false
}

$Result=[ordered]@{
    build=$Build
    overall='FAIL'
    timestamp=$Stamp
    source=[ordered]@{}
    gates=[ordered]@{}
    output=[ordered]@{}
}

try {
    New-Item -ItemType Directory -Path $ProjectDir,$PublishDir,$ReportDir -Force | Out-Null

    Write-Host '======================================================================' -ForegroundColor Cyan
    Write-Host ' AGAPE WINDOWS 10/11 DESKTOP - SAME BROWSER UI / WEBVIEW2' -ForegroundColor Cyan
    Write-Host '======================================================================' -ForegroundColor Cyan

    $os=Get-CimInstance Win32_OperatingSystem
    $caption=[string]$os.Caption
    $arch=[string]$os.OSArchitecture
    Say 'WINDOWS' $caption
    Say 'ARCHITECTURE' $arch
    Assert-True ($caption -match 'Windows 10|Windows 11') "UNSUPPORTED_WINDOWS=$caption"
    Assert-True ($arch -match '64') "R1_REQUIRES_X64_WINDOWS=$arch"
    Pass 'WINDOWS_10_11_GATE'

    $Core=Find-Core
    $Index=Join-Path $Core 'index.html'
    $AppPy=Join-Path $Core 'app.py'
    $Manifest=Join-Path $Core 'manifest.json'
    $Launcher=Join-Path $Core 'START-DMT-SECOND-BRAIN.ps1'
    foreach($required in @($Index,$AppPy,$Manifest,$Launcher)){
        Assert-True (Test-Path -LiteralPath $required -PathType Leaf) "REQUIRED_LIVE_SOURCE_MISSING=$required"
    }
    Say 'LIVE_CORE' $Core

    $Version=Ensure-Core $Core
    $Result.source.build=[string]$Version.build
    $Result.source.project_path=$Core
    $Result.source.index_sha256=Sha $Index
    $Result.source.app_sha256=Sha $AppPy
    $Result.source.manifest_sha256=Sha $Manifest
    Say 'LIVE_BUILD' ([string]$Version.build)

    $System=Get-Json "http://127.0.0.1:$Port/api/system-test" 120
    Assert-True ($System -and [bool]$System.ok) 'LIVE_SYSTEM_TEST_FAILED'
    $Result.gates.core_system='PASS'
    if($System.PSObject.Properties.Name -contains 'passed'){$Result.source.system_passed=[int]$System.passed}
    if($System.PSObject.Properties.Name -contains 'total'){$Result.source.system_total=[int]$System.total}
    if($System.PSObject.Properties.Name -contains 'checks' -and $System.checks.PSObject.Properties.Name -contains 'source_manifest'){
        Assert-True ([bool]$System.checks.source_manifest) 'LIVE_SOURCE_MANIFEST_NOT_CLEAN'
    }
    Pass 'LIVE_CORE_SYSTEM_TEST'

    # Prove the desktop shell will render the exact file the browser currently renders.
    $ServedIndex=Join-Path $Stage 'served-index.html'
    Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -OutFile $ServedIndex -UseBasicParsing -TimeoutSec 30
    $diskHash=Sha $Index
    $servedHash=Sha $ServedIndex
    Say 'INDEX_DISK_SHA256' $diskHash
    Say 'INDEX_SERVED_SHA256' $servedHash
    if($diskHash -eq $servedHash){
        $Result.gates.browser_ui_source_identity='PASS_EXACT_BYTES'
        Pass 'BROWSER_UI_SOURCE_IDENTITY' 'PASS_EXACT_BYTES'
    } else {
        $diskText=[IO.File]::ReadAllText($Index,[Text.Encoding]::UTF8).Replace("`r`n","`n")
        $servedText=[IO.File]::ReadAllText($ServedIndex,[Text.Encoding]::UTF8).Replace("`r`n","`n")
        Assert-True ($diskText -eq $servedText) 'BROWSER_UI_SOURCE_IDENTITY_FAILED_SERVED_ROOT_DIFFERS_FROM_INDEX_HTML'
        $Result.gates.browser_ui_source_identity='PASS_TEXT_EQUIVALENT'
        Pass 'BROWSER_UI_SOURCE_IDENTITY' 'PASS_TEXT_EQUIVALENT'
    }

    $Studio=Get-Json 'http://127.0.0.1:8800/api/health' 4
    $Work=Get-Json 'http://127.0.0.1:8820/api/health' 4
    $Result.source.document_studio=if($Studio){[string]$Studio.version}else{'NOT_RUNNING_AT_BUILD_TIME'}
    $Result.source.work_engine=if($Work){[string]$Work.version}else{'NOT_RUNNING_AT_BUILD_TIME'}
    Say 'DOCUMENT_STUDIO' $Result.source.document_studio
    Say 'WORK_ENGINE' $Result.source.work_engine

    $Csproj=@'
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net10.0-windows</TargetFramework>
    <UseWindowsForms>true</UseWindowsForms>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
    <AssemblyName>Agape</AssemblyName>
    <RootNamespace>AgapeDesktop</RootNamespace>
    <ApplicationManifest>app.manifest</ApplicationManifest>
    <RuntimeIdentifier>win-x64</RuntimeIdentifier>
    <SelfContained>true</SelfContained>
    <PublishSingleFile>true</PublishSingleFile>
    <IncludeNativeLibrariesForSelfExtract>true</IncludeNativeLibrariesForSelfExtract>
    <PublishTrimmed>false</PublishTrimmed>
    <DebugType>none</DebugType>
    <Version>3.1.0.0</Version>
    <FileVersion>3.1.0.0</FileVersion>
    <Product>Agape</Product>
    <Company>DMT</Company>
    <Description>Agape desktop host for the verified browser UI</Description>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.Web.WebView2" Version="__WEBVIEW_VERSION__" />
  </ItemGroup>
</Project>
'@
    $Csproj=$Csproj.Replace('__WEBVIEW_VERSION__',$WebView2PackageVersion)
    Write-Utf8 (Join-Path $ProjectDir 'AgapeDesktop.csproj') $Csproj

    $ManifestXml=@'
<?xml version="1.0" encoding="utf-8"?>
<assembly manifestVersion="1.0" xmlns="urn:schemas-microsoft-com:asm.v1">
  <assemblyIdentity version="1.0.0.0" name="Agape.app"/>
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security><requestedPrivileges><requestedExecutionLevel level="asInvoker" uiAccess="false"/></requestedPrivileges></security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/>
      <supportedOS Id="{4f476546-9374-4f9f-9b8a-0c4a8f5076f1}"/>
    </application>
  </compatibility>
</assembly>
'@
    Write-Utf8 (Join-Path $ProjectDir 'app.manifest') $ManifestXml

    $Program=@'
using System.Diagnostics;
using System.Drawing;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using Microsoft.Win32;

namespace AgapeDesktop;

internal static class Program
{
    [STAThread]
    static void Main()
    {
        using var single = new Mutex(true, @"Local\AgapeDesktopR1", out bool first);
        if (!first) return;
        ApplicationConfiguration.Initialize();
        Application.Run(new AgapeForm());
    }
}

internal sealed class AgapeForm : Form
{
    private const string Home = "http://127.0.0.1:8797/";
    private readonly WebView2 web = new() { Dock = DockStyle.Fill };
    private readonly Label status = new()
    {
        Dock = DockStyle.Fill,
        TextAlign = ContentAlignment.MiddleCenter,
        Font = new Font("Segoe UI", 12F),
        Text = "Starting Agape..."
    };

    public AgapeForm()
    {
        Text = "Agape";
        Width = 1440;
        Height = 920;
        MinimumSize = new Size(980, 680);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.White;
        Controls.Add(status);
        Shown += async (_, _) => await StartAsync();
    }

    private async Task StartAsync()
    {
        try
        {
            status.Text = "Checking Agape services...";
            string core = await CoreLocator.EnsureRunningAsync();
            status.Text = "Starting secure browser view...";

            string profile = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Agape", "WebView2", "UserData");
            Directory.CreateDirectory(profile);

            var env = await CoreWebView2Environment.CreateAsync(null, profile);
            Controls.Clear();
            Controls.Add(web);
            await web.EnsureCoreWebView2Async(env);

            web.CoreWebView2.Settings.AreDevToolsEnabled = true;
            web.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
            web.CoreWebView2.Settings.AreBrowserAcceleratorKeysEnabled = true;
            web.CoreWebView2.Settings.IsZoomControlEnabled = true;
            web.CoreWebView2.Settings.IsStatusBarEnabled = false;

            web.CoreWebView2.NewWindowRequested += (_, e) =>
            {
                try
                {
                    var u = new Uri(e.Uri);
                    if (u.IsLoopback)
                    {
                        e.Handled = true;
                        web.CoreWebView2.Navigate(e.Uri);
                    }
                    else
                    {
                        e.Handled = true;
                        Process.Start(new ProcessStartInfo(e.Uri) { UseShellExecute = true });
                    }
                }
                catch { }
            };

            web.Source = new Uri(Home);
        }
        catch (Exception ex)
        {
            Controls.Clear();
            var box = new TextBox
            {
                Multiline = true,
                ReadOnly = true,
                Dock = DockStyle.Fill,
                Font = new Font("Consolas", 10F),
                Text = "Agape desktop could not start.\r\n\r\n" + ex
            };
            Controls.Add(box);
        }
    }
}

internal static class CoreLocator
{
    private const string VersionUrl = "http://127.0.0.1:8797/api/version";
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(4) };

    public static async Task<string> EnsureRunningAsync()
    {
        string? live = await GetLiveProjectPathAsync();
        if (IsCore(live)) return live!;

        string core = FindOnDisk() ?? throw new InvalidOperationException(
            "Agape V3.1 core was not found. Expected the verified core under LocalAppData\\DMT-Core-V3.1\\SecondBrain\\dmt-second-brain.");

        string appPy = Path.Combine(core, "app.py");
        string? python = FindPython();
        if (python is not null)
        {
            var py = new ProcessStartInfo
            {
                FileName = python,
                WorkingDirectory = core,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            py.ArgumentList.Add(appPy);
            py.ArgumentList.Add("--port");
            py.ArgumentList.Add("8797");
            Process.Start(py);
        }
        else
        {
            string launcher = Path.Combine(core, "START-DMT-SECOND-BRAIN.ps1");
            if (!File.Exists(launcher)) throw new FileNotFoundException("Agape launcher is missing", launcher);
            var psi = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                WorkingDirectory = core,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            psi.ArgumentList.Add("-NoProfile");
            psi.ArgumentList.Add("-ExecutionPolicy");
            psi.ArgumentList.Add("Bypass");
            psi.ArgumentList.Add("-File");
            psi.ArgumentList.Add(launcher);
            Process.Start(psi);
        }

        for (int i = 0; i < 120; i++)
        {
            await Task.Delay(500);
            live = await GetLiveProjectPathAsync();
            if (IsCore(live)) return live!;
        }
        throw new TimeoutException("Agape backend did not become ready on 127.0.0.1:8797.");
    }


    private static string? FindPython()
    {
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string[] candidates =
        {
            Path.Combine(local, "Programs", "Python", "Python312", "python.exe"),
            Path.Combine(local, "Programs", "Python", "Python313", "python.exe"),
            Path.Combine(local, "Programs", "Python", "Python314", "python.exe")
        };
        foreach (var candidate in candidates) if (File.Exists(candidate)) return candidate;
        return null;
    }

    private static bool IsCore(string? p) => !string.IsNullOrWhiteSpace(p)
        && Directory.Exists(p)
        && File.Exists(Path.Combine(p, "app.py"))
        && File.Exists(Path.Combine(p, "index.html"));

    private static string? FindOnDisk()
    {
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string[] candidates =
        {
            Path.Combine(local, "DMT-Core-V3.1", "SecondBrain", "dmt-second-brain"),
            Path.Combine(local, "DMT-Core-V3.1-Early-Alpha", "SecondBrain", "dmt-second-brain")
        };
        return candidates.FirstOrDefault(IsCore);
    }

    private static async Task<string?> GetLiveProjectPathAsync()
    {
        try
        {
            using var response = await Http.GetAsync(VersionUrl);
            if (!response.IsSuccessStatusCode) return null;
            using JsonDocument doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
            if (doc.RootElement.TryGetProperty("project_path", out var p)) return p.GetString();
        }
        catch { }
        return null;
    }
}
'@
    Write-Utf8 (Join-Path $ProjectDir 'Program.cs') $Program
    Pass 'DESKTOP_SOURCE_GENERATED'

    $DotNet=Ensure-DotNet10
    Say 'DOTNET' $DotNet
    & $DotNet restore (Join-Path $ProjectDir 'AgapeDesktop.csproj') --nologo
    Assert-True ($LASTEXITCODE -eq 0) "DOTNET_RESTORE_FAILED=$LASTEXITCODE"
    Pass 'DOTNET_RESTORE'

    & $DotNet publish (Join-Path $ProjectDir 'AgapeDesktop.csproj') -c Release -r win-x64 --self-contained true -o $PublishDir --nologo
    Assert-True ($LASTEXITCODE -eq 0) "DOTNET_PUBLISH_FAILED=$LASTEXITCODE"
    $Exe=Join-Path $PublishDir 'Agape.exe'
    Assert-True (Test-Path -LiteralPath $Exe -PathType Leaf) 'AGAPE_EXE_NOT_CREATED'
    $Result.output.exe=$Exe
    $Result.output.exe_sha256=Sha $Exe
    Pass 'AGAPE_DESKTOP_EXE_BUILD'
    Say 'AGAPE_EXE_SHA256' $Result.output.exe_sha256

    $WebViewBootstrapper=Join-Path $Stage 'MicrosoftEdgeWebview2Setup.exe'
    $HaveBootstrapper=Try-DownloadWebViewBootstrapper $WebViewBootstrapper
    if($HaveBootstrapper){Pass 'WEBVIEW2_BOOTSTRAPPER_DOWNLOAD'}else{Warn 'WEBVIEW2_BOOTSTRAPPER_DOWNLOAD' 'SKIPPED_OR_FAILED_SETUP_WILL_USE_EXISTING_RUNTIME'}

    $Iscc=Ensure-Inno
    Say 'ISCC' $Iscc
    $Iss=Join-Path $Stage 'Agape.iss'
    $webviewFiles=''
    $webviewRun=''
    if($HaveBootstrapper){
        $webviewFiles="Source: `"$WebViewBootstrapper`"; DestDir: `"{tmp}`"; Flags: deleteafterinstall"
        $webviewRun="Filename: `"{tmp}\MicrosoftEdgeWebview2Setup.exe`"; Parameters: `"/silent /install`"; Flags: waituntilterminated runhidden; StatusMsg: `"Checking Microsoft Edge WebView2 Runtime...`""
    }
    $IssText=@"
[Setup]
AppId={{8DBE6576-6BD0-47D9-A193-B28A327D9311}
AppName=Agape
AppVersion=3.1
AppPublisher=DMT
DefaultDirName={localappdata}\Programs\Agape
DefaultGroupName=Agape
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=$Downloads
OutputBaseFilename=$SetupName
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Agape
SetupLogging=yes

[Files]
Source: "$Exe"; DestDir: "{app}"; DestName: "Agape.exe"; Flags: ignoreversion
$webviewFiles

[Icons]
Name: "{group}\Agape"; Filename: "{app}\Agape.exe"
Name: "{autodesktop}\Agape"; Filename: "{app}\Agape.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
$webviewRun
Filename: "{app}\Agape.exe"; Description: "Launch Agape"; Flags: nowait postinstall skipifsilent
"@
    Write-Utf8 $Iss $IssText

    & $Iscc $Iss | Tee-Object -FilePath (Join-Path $ReportDir 'inno-build.log') | Out-Host
    Assert-True ($LASTEXITCODE -eq 0) "INNO_SETUP_BUILD_FAILED=$LASTEXITCODE"
    $Setup=Join-Path $Downloads ($SetupName+'.exe')
    Assert-True (Test-Path -LiteralPath $Setup -PathType Leaf) 'SETUP_EXE_NOT_CREATED'
    $Result.output.setup=$Setup
    $Result.output.setup_sha256=Sha $Setup
    Pass 'WINDOWS_10_11_SINGLE_INSTALLER_BUILD'
    Say 'SETUP' $Setup
    Say 'SETUP_SHA256' $Result.output.setup_sha256

    # Final release gate: source remains unchanged and live app still healthy after packaging.
    Assert-True ((Sha $Index) -eq $diskHash) 'LIVE_INDEX_CHANGED_DURING_BUILD'
    Assert-True ((Sha $AppPy) -eq $Result.source.app_sha256) 'LIVE_APP_CHANGED_DURING_BUILD'
    $FinalSystem=Get-Json "http://127.0.0.1:$Port/api/system-test" 120
    Assert-True ($FinalSystem -and [bool]$FinalSystem.ok) 'FINAL_LIVE_SYSTEM_TEST_FAILED'
    $Result.gates.final_source_unchanged='PASS'
    $Result.gates.final_system_test='PASS'
    Pass 'FINAL_SOURCE_UNCHANGED'
    Pass 'FINAL_SYSTEM_TEST'

    $Result.overall='PASS'
    Write-Utf8 $ResultJson ($Result|ConvertTo-Json -Depth 20)
    Copy-Item -LiteralPath (Join-Path $ProjectDir 'AgapeDesktop.csproj') -Destination $ReportDir -Force
    Copy-Item -LiteralPath (Join-Path $ProjectDir 'Program.cs') -Destination $ReportDir -Force
    Copy-Item -LiteralPath $Iss -Destination $ReportDir -Force

    if(!$BuildOnly){
        Say 'INSTALLING_NEW_DESKTOP_SHELL' $Setup
        $p=Start-Process -FilePath $Setup -ArgumentList @('/SILENT','/NORESTART','/CLOSEAPPLICATIONS') -Wait -PassThru
        Assert-True ($p.ExitCode -eq 0) "SETUP_INSTALL_FAILED_EXIT=$($p.ExitCode)"
        Pass 'DESKTOP_SHELL_INSTALL'
        $InstalledExe=Join-Path $env:LOCALAPPDATA 'Programs\Agape\Agape.exe'
        Assert-True (Test-Path -LiteralPath $InstalledExe -PathType Leaf) 'INSTALLED_AGAPE_EXE_NOT_FOUND'
        Start-Process -FilePath $InstalledExe | Out-Null
        Pass 'AGAPE_DESKTOP_LAUNCH'
    }

    Write-Host ''
    Write-Host '====================== FINAL RESULT ======================' -ForegroundColor Green
    Write-Host ($Result|ConvertTo-Json -Depth 20)
    Write-Host '==========================================================' -ForegroundColor Green
}
catch {
    $Result.overall='FAIL'
    $Result.error=$_.Exception.Message
    try{Write-Utf8 $ResultJson ($Result|ConvertTo-Json -Depth 20)}catch{}
    Write-Host ''
    Write-Host '====================== BUILD FAILED ======================' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "RESULT=$ResultJson" -ForegroundColor Yellow
    Write-Host '==========================================================' -ForegroundColor Red
    exit 1
}
finally {
    if(!$KeepStage){Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction SilentlyContinue}
}
