//go:build windows

package main

import (
	"archive/zip"
	"bufio"
	"crypto/sha256"
	"embed"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
	"time"
	"unicode/utf16"
)

//go:embed payload/Agape.exe
var payloadFS embed.FS

const (
	buildName              = "AGAPE-WINDOWS-NATIVE-WEBVIEW-R6"
	expectedBuild          = "DMT-CORE-V3.1-EARLY-ALPHA-R8"
	appURL                 = "http://127.0.0.1:8797/"
	webViewPackageVersion  = "1.0.4191.47"
	webViewNugetURL        = "https://www.nuget.org/api/v2/package/Microsoft.Web.WebView2/1.0.4191.47"
	webViewBootstrapperURL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
	uninstallKey           = `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Agape`
)

type versionInfo struct {
	Build       string `json:"build"`
	ProjectPath string `json:"project_path"`
}
type systemTest struct {
	OK     bool `json:"ok"`
	Passed int  `json:"passed"`
	Total  int  `json:"total"`
}

func programsRoot() string          { return filepath.Join(os.Getenv("LOCALAPPDATA"), "Programs") }
func installRoot() string           { return filepath.Join(programsRoot(), "Agape") }
func appPath() string               { return filepath.Join(installRoot(), "Agape.exe") }
func loaderPath(root string) string { return filepath.Join(root, "WebView2Loader.dll") }
func uninstallerPath() string       { return filepath.Join(installRoot(), "Agape-Uninstall.exe") }
func say(k, v string)               { fmt.Printf("%s=%s\n", k, v) }
func shaFile(p string) (string, error) {
	f, e := os.Open(p)
	if e != nil {
		return "", e
	}
	defer f.Close()
	h := sha256.New()
	if _, e = io.Copy(h, f); e != nil {
		return "", e
	}
	return strings.ToUpper(hex.EncodeToString(h.Sum(nil))), nil
}
func validCore(p string) bool {
	if p == "" {
		return false
	}
	for _, n := range []string{"app.py", "index.html", "START-DMT-SECOND-BRAIN.ps1"} {
		st, e := os.Stat(filepath.Join(p, n))
		if e != nil || st.IsDir() {
			return false
		}
	}
	return true
}
func httpJSON(url string, out any, timeout time.Duration) error {
	c := &http.Client{Timeout: timeout}
	r, e := c.Get(url)
	if e != nil {
		return e
	}
	defer r.Body.Close()
	if r.StatusCode != 200 {
		return fmt.Errorf("HTTP_%d", r.StatusCode)
	}
	return json.NewDecoder(r.Body).Decode(out)
}
func getVersion() (*versionInfo, error) {
	var v versionInfo
	if e := httpJSON("http://127.0.0.1:8797/api/version", &v, 4*time.Second); e != nil {
		return nil, e
	}
	return &v, nil
}
func findCore() (string, error) {
	if v, e := getVersion(); e == nil && validCore(v.ProjectPath) {
		return filepath.Clean(v.ProjectPath), nil
	}
	la := os.Getenv("LOCALAPPDATA")
	if la == "" {
		return "", errors.New("LOCALAPPDATA_NOT_SET")
	}
	for _, p := range []string{filepath.Join(la, "DMT-Core-V3.1", "SecondBrain", "dmt-second-brain"), filepath.Join(la, "DMT-Core-V3.1-Early-Alpha", "SecondBrain", "dmt-second-brain")} {
		if validCore(p) {
			return p, nil
		}
	}
	return "", errors.New("AGAPE_V3_1_CORE_NOT_FOUND")
}
func localUIPreflight(core string) error {
	b, e := os.ReadFile(filepath.Join(core, "index.html"))
	if e != nil {
		return e
	}
	s := string(b)
	markers := []string{"data-page=\"chat\"", "data-page=\"settings\"", "workspace-manage-projects", "project-instructions-text", "project-document-choose", "Choose Document"}
	n := 0
	for _, m := range markers {
		if strings.Contains(s, m) {
			n++
		}
	}
	say("CURRENT_R8_UI_MARKERS", fmt.Sprintf("%d/%d", n, len(markers)))
	if n < 4 {
		return fmt.Errorf("CURRENT_R8_UI_MARKERS_MISSING=%d/%d", n, len(markers))
	}
	h := sha256.Sum256(b)
	say("CURRENT_INDEX_SHA256", strings.ToUpper(hex.EncodeToString(h[:])))
	for _, p := range []string{"app.py", "manifest.json"} {
		x := filepath.Join(core, p)
		if st, e := os.Stat(x); e == nil && !st.IsDir() {
			if h, e := shaFile(x); e == nil {
				say(strings.ToUpper(strings.TrimSuffix(p, filepath.Ext(p)))+"_SHA256", h)
			}
		}
	}
	return nil
}
func psEncoded(script string) error {
	r := utf16.Encode([]rune(script))
	b := make([]byte, len(r)*2)
	for i, v := range r {
		binary.LittleEndian.PutUint16(b[i*2:], v)
	}
	enc := base64.StdEncoding.EncodeToString(b)
	out, e := exec.Command("powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc).CombinedOutput()
	if e != nil {
		return fmt.Errorf("POWERSHELL_FAILED=%v OUTPUT=%s", e, strings.TrimSpace(string(out)))
	}
	return nil
}
func copySelf(dst string) error {
	src, e := os.Executable()
	if e != nil {
		return e
	}
	in, e := os.Open(src)
	if e != nil {
		return e
	}
	defer in.Close()
	out, e := os.Create(dst)
	if e != nil {
		return e
	}
	_, e1 := io.Copy(out, in)
	e2 := out.Close()
	if e1 != nil {
		return e1
	}
	return e2
}
func createShortcuts() error {
	exe := strings.ReplaceAll(appPath(), "'", "''")
	root := strings.ReplaceAll(installRoot(), "'", "''")
	s := fmt.Sprintf(`$ErrorActionPreference='Stop';$w=New-Object -ComObject WScript.Shell;$d=[Environment]::GetFolderPath('Desktop');$p=Join-Path ([Environment]::GetFolderPath('Programs')) 'Agape';New-Item -ItemType Directory -Force -Path $p|Out-Null;foreach($x in @((Join-Path $d 'Agape.lnk'),(Join-Path $p 'Agape.lnk'))){$l=$w.CreateShortcut($x);$l.TargetPath='%s';$l.WorkingDirectory='%s';$l.IconLocation='%s,0';$l.Description='Agape native Windows desktop app';$l.Save()}`, exe, root, exe)
	return psEncoded(s)
}
func removeShortcuts() {
	_ = psEncoded(`$d=[Environment]::GetFolderPath('Desktop');$p=Join-Path ([Environment]::GetFolderPath('Programs')) 'Agape';Remove-Item -LiteralPath (Join-Path $d 'Agape.lnk') -Force -ErrorAction SilentlyContinue;Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue`)
}
func regAdd(n, v, t string) error {
	out, e := exec.Command("reg.exe", "add", uninstallKey, "/v", n, "/t", t, "/d", v, "/f").CombinedOutput()
	if e != nil {
		return fmt.Errorf("REG_ADD_%s_FAILED=%v OUTPUT=%s", n, e, strings.TrimSpace(string(out)))
	}
	return nil
}
func regDelete() { _, _ = exec.Command("reg.exe", "delete", uninstallKey, "/f").CombinedOutput() }

func exportOldRegistry() string {
	p := filepath.Join(os.TempDir(), "Agape-previous-uninstall-"+time.Now().Format("20060102-150405")+".reg")
	if out, e := exec.Command("reg.exe", "export", uninstallKey, p, "/y").CombinedOutput(); e == nil {
		if st, x := os.Stat(p); x == nil && !st.IsDir() {
			say("PREVIOUS_UNINSTALL_REGISTRY_BACKUP", p)
			return p
		}
	} else {
		_ = out
	}
	return ""
}
func restoreOldRegistry(p string) {
	regDelete()
	if p != "" {
		_, _ = exec.Command("reg.exe", "import", p).CombinedOutput()
	}
}
func registerUninstall() error {
	for _, v := range [][3]string{{"DisplayName", "Agape", "REG_SZ"}, {"DisplayVersion", "3.1-Native-R6", "REG_SZ"}, {"Publisher", "DMT", "REG_SZ"}, {"InstallLocation", installRoot(), "REG_SZ"}, {"DisplayIcon", appPath() + ",0", "REG_SZ"}, {"UninstallString", "\"" + uninstallerPath() + "\" --uninstall", "REG_SZ"}, {"NoModify", "1", "REG_DWORD"}, {"NoRepair", "1", "REG_DWORD"}} {
		if e := regAdd(v[0], v[1], v[2]); e != nil {
			return e
		}
	}
	return nil
}
func tail(path string, max int) string {
	f, e := os.Open(path)
	if e != nil {
		return ""
	}
	defer f.Close()
	a := []string{}
	s := bufio.NewScanner(f)
	for s.Scan() {
		a = append(a, s.Text())
		if len(a) > max {
			a = a[1:]
		}
	}
	return strings.Join(a, " | ")
}

func download(url, dst string) error {
	c := &http.Client{Timeout: 3 * time.Minute}
	r, e := c.Get(url)
	if e != nil {
		return e
	}
	defer r.Body.Close()
	if r.StatusCode < 200 || r.StatusCode >= 300 {
		return fmt.Errorf("HTTP_%d", r.StatusCode)
	}
	f, e := os.Create(dst)
	if e != nil {
		return e
	}
	n, e1 := io.Copy(f, r.Body)
	e2 := f.Close()
	if e1 != nil {
		return e1
	}
	if e2 != nil {
		return e2
	}
	if n < 10000 {
		return fmt.Errorf("DOWNLOAD_TOO_SMALL=%d", n)
	}
	return nil
}
func copyFile(src, dst string) error {
	in, e := os.Open(src)
	if e != nil {
		return e
	}
	defer in.Close()
	out, e := os.Create(dst)
	if e != nil {
		return e
	}
	_, e1 := io.Copy(out, in)
	e2 := out.Close()
	if e1 != nil {
		return e1
	}
	return e2
}

func findCachedLoader() string {
	candidates := []string{loaderPath(installRoot())}
	home, _ := os.UserHomeDir()
	if home != "" {
		exact := filepath.Join(home, ".nuget", "packages", "microsoft.web.webview2", webViewPackageVersion, "runtimes", "win-x64", "native", "WebView2Loader.dll")
		candidates = append(candidates, exact)
		root := filepath.Join(home, ".nuget", "packages", "microsoft.web.webview2")
		dirs, _ := os.ReadDir(root)
		names := []string{}
		for _, d := range dirs {
			if d.IsDir() {
				names = append(names, d.Name())
			}
		}
		sort.Sort(sort.Reverse(sort.StringSlice(names)))
		for _, n := range names {
			candidates = append(candidates, filepath.Join(root, n, "runtimes", "win-x64", "native", "WebView2Loader.dll"))
		}
	}
	for _, p := range candidates {
		if st, e := os.Stat(p); e == nil && !st.IsDir() && st.Size() > 50000 {
			return p
		}
	}
	return ""
}

func acquireWebViewLoader(candidate string) error {
	dst := loaderPath(candidate)
	if src := findCachedLoader(); src != "" {
		say("WEBVIEW2_LOADER_SOURCE", "CACHE:"+src)
		return copyFile(src, dst)
	}
	tmp := filepath.Join(os.TempDir(), "Microsoft.Web.WebView2-"+webViewPackageVersion+".nupkg")
	say("WEBVIEW2_LOADER_SOURCE", "NUGET_"+webViewPackageVersion)
	if e := download(webViewNugetURL, tmp); e != nil {
		return fmt.Errorf("WEBVIEW2_NUGET_DOWNLOAD_FAILED=%w", e)
	}
	defer os.Remove(tmp)
	z, e := zip.OpenReader(tmp)
	if e != nil {
		return fmt.Errorf("WEBVIEW2_NUGET_OPEN_FAILED=%w", e)
	}
	defer z.Close()
	var target *zip.File
	for _, f := range z.File {
		n := strings.ToLower(filepath.ToSlash(f.Name))
		if strings.HasSuffix(n, "runtimes/win-x64/native/webview2loader.dll") {
			target = f
			break
		}
	}
	if target == nil {
		return errors.New("WEBVIEW2_LOADER_NOT_FOUND_IN_NUGET")
	}
	r, e := target.Open()
	if e != nil {
		return e
	}
	defer r.Close()
	out, e := os.Create(dst)
	if e != nil {
		return e
	}
	n, e1 := io.Copy(out, r)
	e2 := out.Close()
	if e1 != nil {
		return e1
	}
	if e2 != nil {
		return e2
	}
	if n < 50000 {
		return fmt.Errorf("WEBVIEW2_LOADER_EXTRACT_TOO_SMALL=%d", n)
	}
	return nil
}

func hiddenCmd(name string, args ...string) *exec.Cmd {
	c := exec.Command(name, args...)
	c.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000}
	return c
}
func checkCandidate(candidate string, mode string) error {
	c := hiddenCmd(filepath.Join(candidate, "Agape.exe"), mode)
	c.Dir = candidate
	return c.Run()
}
func ensureWebViewRuntime(candidate string) error {
	if e := checkCandidate(candidate, "--webview-check"); e == nil {
		say("WEBVIEW2_RUNTIME", "PASS_EXISTING")
		return nil
	}
	say("WEBVIEW2_RUNTIME", "INSTALLING_EVERGREEN")
	boot := filepath.Join(os.TempDir(), "MicrosoftEdgeWebview2Setup.exe")
	if e := download(webViewBootstrapperURL, boot); e != nil {
		return fmt.Errorf("WEBVIEW2_BOOTSTRAPPER_DOWNLOAD_FAILED=%w", e)
	}
	defer os.Remove(boot)
	c := hiddenCmd(boot, "/silent", "/install")
	if out, e := c.CombinedOutput(); e != nil {
		return fmt.Errorf("WEBVIEW2_RUNTIME_INSTALL_FAILED=%v OUTPUT=%s", e, strings.TrimSpace(string(out)))
	}
	if e := checkCandidate(candidate, "--webview-check"); e != nil {
		return fmt.Errorf("WEBVIEW2_RUNTIME_STILL_UNAVAILABLE=%w", e)
	}
	say("WEBVIEW2_RUNTIME", "PASS_AFTER_INSTALL")
	return nil
}

func writeCandidate(candidate string) error {
	if e := os.MkdirAll(candidate, 0755); e != nil {
		return e
	}
	payload, e := payloadFS.ReadFile("payload/Agape.exe")
	if e != nil {
		return e
	}
	if e = os.WriteFile(filepath.Join(candidate, "Agape.exe"), payload, 0755); e != nil {
		return e
	}
	if e = acquireWebViewLoader(candidate); e != nil {
		return e
	}
	if h, e := shaFile(filepath.Join(candidate, "Agape.exe")); e == nil {
		say("CANDIDATE_AGAPE_EXE_SHA256", h)
	}
	if h, e := shaFile(loaderPath(candidate)); e == nil {
		say("CANDIDATE_WEBVIEW2_LOADER_SHA256", h)
	}
	return nil
}

func atomicCutover(candidate string) (string, error) {
	root := installRoot()
	backup := ""
	if st, e := os.Stat(root); e == nil && st.IsDir() {
		backup = filepath.Join(programsRoot(), "Agape-Desktop-LastKnownGood-"+time.Now().Format("20060102-150405"))
		if e = os.Rename(root, backup); e != nil {
			return "", fmt.Errorf("CLOSE_RUNNING_AGAPE_AND_RETRY: could not stage previous install: %w", e)
		}
		say("PREVIOUS_DESKTOP_BACKUP", backup)
	}
	if e := os.Rename(candidate, root); e != nil {
		if backup != "" {
			_ = os.Rename(backup, root)
		}
		return "", fmt.Errorf("CANDIDATE_CUTOVER_FAILED=%w", e)
	}
	return backup, nil
}
func restoreCutover(backup, registryBackup string) {
	root := installRoot()
	removeShortcuts()
	_ = os.RemoveAll(root)
	if backup != "" {
		_ = os.Rename(backup, root)
		_ = createShortcuts()
	}
	restoreOldRegistry(registryBackup)
}

func finalHttpChecks() error {
	v, e := getVersion()
	if e != nil {
		return fmt.Errorf("FINAL_VERSION_CHECK_FAILED=%w", e)
	}
	if v.Build != expectedBuild {
		return fmt.Errorf("FINAL_BUILD_WRONG=%s", v.Build)
	}
	say("FINAL_BUILD", v.Build)
	var t systemTest
	if e = httpJSON("http://127.0.0.1:8797/api/system-test", &t, 120*time.Second); e != nil {
		return fmt.Errorf("FINAL_SYSTEM_TEST_REQUEST_FAILED=%w", e)
	}
	if !t.OK {
		return fmt.Errorf("FINAL_SYSTEM_TEST_FAILED PASSED=%d TOTAL=%d", t.Passed, t.Total)
	}
	say("FINAL_SYSTEM_TEST", fmt.Sprintf("PASS_%d_OF_%d", t.Passed, t.Total))
	c := &http.Client{Timeout: 10 * time.Second}
	r, e := c.Get(appURL)
	if e != nil {
		return fmt.Errorf("FINAL_UI_CHECK_FAILED=%w", e)
	}
	defer r.Body.Close()
	if r.StatusCode != 200 {
		return fmt.Errorf("FINAL_UI_STATUS=%d", r.StatusCode)
	}
	b, _ := io.ReadAll(io.LimitReader(r.Body, 2*1024*1024))
	if !strings.Contains(string(b), "project-instructions-text") {
		return errors.New("FINAL_UI_R8_MARKER_MISSING")
	}
	say("FINAL_UI", "PASS_HTTP_200_R8")
	return nil
}

func install() error {
	fmt.Println("============================================================")
	fmt.Println(" AGAPE WINDOWS 10/11 NATIVE DESKTOP R6")
	fmt.Println(" Native Win32 host + EMBEDDED WebView2 + Agape V3.1 R8")
	fmt.Println(" No Edge/Chrome app-mode window")
	fmt.Println("============================================================")
	say("BUILD", buildName)
	core, e := findCore()
	if e != nil {
		return e
	}
	say("CORE", core)
	if e = localUIPreflight(core); e != nil {
		return e
	}
	if v, x := getVersion(); x == nil {
		say("CURRENT_BUILD", v.Build)
		if v.Build != expectedBuild {
			return fmt.Errorf("WRONG_LIVE_BUILD=%s EXPECTED=%s", v.Build, expectedBuild)
		}
	} else {
		say("CORE_RUNNING", "NO - candidate will start it hidden")
	}

	candidate := filepath.Join(programsRoot(), "Agape-Native-R6-Candidate-"+time.Now().Format("20060102-150405"))
	_ = os.RemoveAll(candidate)
	if e = writeCandidate(candidate); e != nil {
		_ = os.RemoveAll(candidate)
		return fmt.Errorf("CANDIDATE_CREATE_FAILED=%w", e)
	}
	say("CANDIDATE", candidate)
	if e = ensureWebViewRuntime(candidate); e != nil {
		_ = os.RemoveAll(candidate)
		return e
	}

	say("CANDIDATE_RUNTIME_VALIDATION", "START")
	if e = checkCandidate(candidate, "--validate"); e != nil {
		d := tail(filepath.Join(candidate, "Agape-native.log"), 30)
		_ = os.RemoveAll(candidate)
		return fmt.Errorf("CANDIDATE_VALIDATION_FAILED=%v LOG=%s", e, d)
	}
	say("CANDIDATE_RUNTIME_VALIDATION", "PASS")

	registryBackup := exportOldRegistry()
	backup, e := atomicCutover(candidate)
	if e != nil {
		return e
	}
	if e = copySelf(uninstallerPath()); e != nil {
		restoreCutover(backup, registryBackup)
		return fmt.Errorf("WRITE_UNINSTALLER_FAILED=%w", e)
	}
	if e = createShortcuts(); e != nil {
		restoreCutover(backup, registryBackup)
		return e
	}
	say("SHORTCUTS", "PASS_NATIVE_EXE")
	if e = registerUninstall(); e != nil {
		restoreCutover(backup, registryBackup)
		return e
	}
	say("WINDOWS_UNINSTALL_ENTRY", "PASS")

	if e = hiddenCmd(appPath(), "--validate").Run(); e != nil {
		d := tail(filepath.Join(installRoot(), "Agape-native.log"), 35)
		restoreCutover(backup, registryBackup)
		return fmt.Errorf("INSTALLED_NATIVE_VALIDATION_FAILED=%v LOG=%s", e, d)
	}
	if e = finalHttpChecks(); e != nil {
		restoreCutover(backup, registryBackup)
		return e
	}
	say("EMBEDDED_WEBVIEW2_HOST", "PASS")
	say("EXTERNAL_BROWSER_MAIN_WINDOW", "NO")
	say("LIVE_SOURCE_MODIFIED", "NO")
	say("DATA_MODIFIED", "NO")
	say("INSTALL", "PASS")
	if e = exec.Command(appPath()).Start(); e != nil {
		return fmt.Errorf("FINAL_NATIVE_LAUNCH_FAILED=%w", e)
	}
	return nil
}

func uninstall() error {
	fmt.Println("AGAPE_NATIVE_UNINSTALL=START")
	removeShortcuts()
	regDelete()
	root := installRoot()
	say("AGAPE_CORE_DELETED", "NO")
	say("AGAPE_DATA_DELETED", "NO")
	cmd := exec.Command("cmd.exe", "/c", "ping 127.0.0.1 -n 3 >nul & rmdir /s /q \""+root+"\"")
	if e := cmd.Start(); e != nil {
		return e
	}
	fmt.Println("AGAPE_NATIVE_UNINSTALL=PASS")
	return nil
}
func main() {
	u := false
	for _, a := range os.Args[1:] {
		if a == "--uninstall" {
			u = true
		}
	}
	var e error
	if u {
		e = uninstall()
	} else {
		e = install()
	}
	if e != nil {
		fmt.Println()
		fmt.Println("AGAPE INSTALL = FAIL")
		fmt.Println("ERROR=" + e.Error())
		fmt.Println()
		fmt.Println("Your Agape V3.1 source/database were not deleted or replaced.")
		fmt.Println("Press Enter to close.")
		var x string
		fmt.Scanln(&x)
		os.Exit(1)
	}
	if !u {
		fmt.Println()
		fmt.Println("AGAPE INSTALL = PASS")
		fmt.Println("NATIVE_WINDOW=WIN32")
		fmt.Println("UI_HOST=EMBEDDED_WEBVIEW2")
		fmt.Println("EXTERNAL_BROWSER_MAIN_WINDOW=NO")
		fmt.Println()
		fmt.Println("Agape is opening in its own Windows application window now.")
		fmt.Println("Press Enter to close this installer.")
		var x string
		fmt.Scanln(&x)
	}
}
