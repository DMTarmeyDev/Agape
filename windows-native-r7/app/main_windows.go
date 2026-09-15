//go:build windows

package main

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
	"unicode/utf16"
	"unsafe"
)

const (
	expectedBuild = "DMT-CORE-V3.1-EARLY-ALPHA-R8"
	corePort      = 8797
	backendURL    = "http://127.0.0.1:8797/"

	wmDestroy = 0x0002
	wmSize    = 0x0005
	wmClose   = 0x0010
	wmApp     = 0x8000
	wmReady   = wmApp + 41
	wmFailed  = wmApp + 42

	wsOverlappedWindow = 0x00CF0000
	wsVisible          = 0x10000000
	swShow             = 5

	coinitApartmentThreaded = 0x2
	sOK                     = 0
	eNoInterface            = 0x80004002
)

type guid struct {
	Data1 uint32
	Data2 uint16
	Data3 uint16
	Data4 [8]byte
}

type rect struct{ Left, Top, Right, Bottom int32 }

type point struct{ X, Y int32 }

type msg struct {
	Hwnd     uintptr
	Message  uint32
	WParam   uintptr
	LParam   uintptr
	Time     uint32
	Pt       point
	LPrivate uint32
}

type wndClassEx struct {
	CbSize        uint32
	Style         uint32
	LpfnWndProc   uintptr
	CbClsExtra    int32
	CbWndExtra    int32
	HInstance     uintptr
	HIcon         uintptr
	HCursor       uintptr
	HbrBackground uintptr
	LpszMenuName  *uint16
	LpszClassName *uint16
	HIconSm       uintptr
}

type handlerVtbl struct{ QueryInterface, AddRef, Release, Invoke uintptr }
type comHandler struct {
	Vtbl *handlerVtbl
	IID  guid
	Ref  int32
}

type versionInfo struct {
	Build       string `json:"build"`
	ProjectPath string `json:"project_path"`
}

type systemTest struct {
	OK     bool `json:"ok"`
	Passed int  `json:"passed"`
	Total  int  `json:"total"`
}

type flexibleBool bool

func (b *flexibleBool) UnmarshalJSON(data []byte) error {
	s := strings.TrimSpace(string(data))
	switch strings.ToLower(s) {
	case "true", "1", "\"true\"", "\"1\"", "\"yes\"":
		*b = true
		return nil
	case "false", "0", "null", "", "\"false\"", "\"0\"", "\"no\"", "\"\"":
		*b = false
		return nil
	default:
		return fmt.Errorf("unsupported boolean value %q", s)
	}
}

type projectRecord struct {
	ID        int          `json:"id"`
	Name      string       `json:"name"`
	Kind      string       `json:"kind"`
	Archived  flexibleBool `json:"archived"`
	Path      string       `json:"path"`
	Workspace string       `json:"workspace"`
}

type projectCatalog struct {
	Projects []projectRecord `json:"projects"`
}

var (
	user32   = syscall.NewLazyDLL("user32.dll")
	kernel32 = syscall.NewLazyDLL("kernel32.dll")
	ole32    = syscall.NewLazyDLL("ole32.dll")
	shell32  = syscall.NewLazyDLL("shell32.dll")

	pRegisterClassExW = user32.NewProc("RegisterClassExW")
	pCreateWindowExW  = user32.NewProc("CreateWindowExW")
	pDefWindowProcW   = user32.NewProc("DefWindowProcW")
	pShowWindow       = user32.NewProc("ShowWindow")
	pUpdateWindow     = user32.NewProc("UpdateWindow")
	pGetMessageW      = user32.NewProc("GetMessageW")
	pTranslateMessage = user32.NewProc("TranslateMessage")
	pDispatchMessageW = user32.NewProc("DispatchMessageW")
	pPostQuitMessage  = user32.NewProc("PostQuitMessage")
	pPostMessageW     = user32.NewProc("PostMessageW")
	pDestroyWindow    = user32.NewProc("DestroyWindow")
	pGetClientRect    = user32.NewProc("GetClientRect")
	pSetWindowTextW   = user32.NewProc("SetWindowTextW")
	pLoadCursorW      = user32.NewProc("LoadCursorW")
	pMessageBoxW      = user32.NewProc("MessageBoxW")
	pSetDpiContext    = user32.NewProc("SetProcessDpiAwarenessContext")

	pGetModuleHandleW = kernel32.NewProc("GetModuleHandleW")
	pCreateMutexW     = kernel32.NewProc("CreateMutexW")
	pGetLastError     = kernel32.NewProc("GetLastError")

	pCoInitializeEx = ole32.NewProc("CoInitializeEx")
	pCoUninitialize = ole32.NewProc("CoUninitialize")
	pCoTaskMemFree  = ole32.NewProc("CoTaskMemFree")
	pShellExecuteW  = shell32.NewProc("ShellExecuteW")

	mainHwnd   uintptr
	controller uintptr
	webview    uintptr
	loaderDLL  *syscall.DLL

	stateMu         sync.Mutex
	startupErr      error
	coreRoot        string
	homeURL         = backendURL
	bridgeServer    *http.Server
	windowClassName = "AgapeWindows11MainProjectR71"
)

var (
	iidIUnknown          = guid{0x00000000, 0x0000, 0x0000, [8]byte{0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46}}
	iidEnvHandler        = guid{0x4E8A3389, 0xC9D8, 0x4BD2, [8]byte{0xB6, 0xB5, 0x12, 0x4F, 0xEE, 0x6C, 0xC1, 0x4D}}
	iidControllerHandler = guid{0x6C4819F3, 0xC9B7, 0x4260, [8]byte{0x81, 0x27, 0xC9, 0xF5, 0xBD, 0xE7, 0xF6, 0x8C}}
	iidNewWindowHandler  = guid{0xD4C185FE, 0xC81C, 0x4989, [8]byte{0x97, 0xAF, 0x2D, 0x3F, 0xA7, 0xAB, 0x56, 0x51}}

	envVtbl           = handlerVtbl{}
	controllerVtbl    = handlerVtbl{}
	newWindowVtbl     = handlerVtbl{}
	envHandler        = comHandler{IID: iidEnvHandler, Ref: 1}
	controllerHandler = comHandler{IID: iidControllerHandler, Ref: 1}
	newWindowHandler  = comHandler{IID: iidNewWindowHandler, Ref: 1}
)

func exeDir() string {
	x, err := os.Executable()
	if err != nil {
		return "."
	}
	p, err := filepath.EvalSymlinks(x)
	if err == nil {
		x = p
	}
	return filepath.Dir(x)
}
func logPath() string { return filepath.Join(exeDir(), "Agape-native.log") }
func logLine(s string) {
	_ = os.MkdirAll(exeDir(), 0755)
	f, err := os.OpenFile(logPath(), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	if err == nil {
		defer f.Close()
		_, _ = fmt.Fprintln(f, time.Now().Format(time.RFC3339), s)
	}
}
func utf16Ptr(s string) *uint16 { p, _ := syscall.UTF16PtrFromString(s); return p }
func setTitle(s string) {
	if mainHwnd != 0 {
		pSetWindowTextW.Call(mainHwnd, uintptr(unsafe.Pointer(utf16Ptr(s))))
	}
}
func hresultFailed(hr uintptr) bool   { return int32(uint32(hr)) < 0 }
func hresultString(hr uintptr) string { return fmt.Sprintf("0x%08X", uint32(hr)) }
func method(obj uintptr, index uintptr) uintptr {
	vtbl := *(*uintptr)(unsafe.Pointer(obj))
	return *(*uintptr)(unsafe.Pointer(vtbl + index*unsafe.Sizeof(uintptr(0))))
}
func guidEqual(a, b guid) bool { return a == b }

func queryInterface(this, riid, ppv uintptr) uintptr {
	if ppv == 0 || riid == 0 {
		return uintptr(eNoInterface)
	}
	h := (*comHandler)(unsafe.Pointer(this))
	want := *(*guid)(unsafe.Pointer(riid))
	if guidEqual(want, iidIUnknown) || guidEqual(want, h.IID) {
		*(*uintptr)(unsafe.Pointer(ppv)) = this
		atomic.AddInt32(&h.Ref, 1)
		return sOK
	}
	*(*uintptr)(unsafe.Pointer(ppv)) = 0
	return uintptr(eNoInterface)
}
func addRef(this uintptr) uintptr {
	h := (*comHandler)(unsafe.Pointer(this))
	return uintptr(atomic.AddInt32(&h.Ref, 1))
}
func release(this uintptr) uintptr {
	h := (*comHandler)(unsafe.Pointer(this))
	n := atomic.AddInt32(&h.Ref, -1)
	if n < 1 {
		atomic.StoreInt32(&h.Ref, 1)
		return 1
	}
	return uintptr(n)
}

func envInvoke(this, errorCode, createdEnvironment uintptr) uintptr {
	logLine("WEBVIEW2_ENV_CALLBACK HRESULT=" + hresultString(errorCode))
	if hresultFailed(errorCode) || createdEnvironment == 0 {
		failAsync(fmt.Errorf("WEBVIEW2_ENVIRONMENT_CREATE_FAILED=%s", hresultString(errorCode)))
		return sOK
	}
	fn := method(createdEnvironment, 3) // ICoreWebView2Environment::CreateCoreWebView2Controller
	hr, _, _ := syscall.SyscallN(fn, createdEnvironment, mainHwnd, uintptr(unsafe.Pointer(&controllerHandler)))
	if hresultFailed(hr) {
		failAsync(fmt.Errorf("WEBVIEW2_CONTROLLER_REQUEST_FAILED=%s", hresultString(hr)))
	}
	return sOK
}

func controllerInvoke(this, errorCode, createdController uintptr) uintptr {
	logLine("WEBVIEW2_CONTROLLER_CALLBACK HRESULT=" + hresultString(errorCode))
	if hresultFailed(errorCode) || createdController == 0 {
		failAsync(fmt.Errorf("WEBVIEW2_CONTROLLER_CREATE_FAILED=%s", hresultString(errorCode)))
		return sOK
	}
	controller = createdController
	// Keep the COM controller alive after the completion callback returns.
	syscall.SyscallN(method(controller, 1), controller)
	// put_IsVisible(TRUE)
	hr, _, _ := syscall.SyscallN(method(controller, 4), controller, 1)
	if hresultFailed(hr) {
		logLine("WEBVIEW2_VISIBLE_WARN=" + hresultString(hr))
	}
	resizeWebView()
	var core uintptr
	hr, _, _ = syscall.SyscallN(method(controller, 25), controller, uintptr(unsafe.Pointer(&core)))
	if hresultFailed(hr) || core == 0 {
		failAsync(fmt.Errorf("WEBVIEW2_GET_CORE_FAILED=%s", hresultString(hr)))
		return sOK
	}
	webview = core
	// Match established pure-Go WebView2 bindings: retain the core interface we store.
	syscall.SyscallN(method(webview, 1), webview)

	// Prevent localhost links opened with target=_blank from becoming an external browser window.
	var token int64
	hr, _, _ = syscall.SyscallN(method(webview, 44), webview, uintptr(unsafe.Pointer(&newWindowHandler)), uintptr(unsafe.Pointer(&token)))
	if hresultFailed(hr) {
		logLine("WEBVIEW2_NEW_WINDOW_HANDLER_WARN=" + hresultString(hr))
	}

	if err := navigate(homeURL); err != nil {
		failAsync(err)
		return sOK
	}
	setTitle("Agape")
	logLine("EMBEDDED_WEBVIEW2=PASS HOME=" + homeURL)
	return sOK
}

func newWindowInvoke(this, sender, args uintptr) uintptr {
	if args == 0 {
		return sOK
	}
	var raw uintptr
	hr, _, _ := syscall.SyscallN(method(args, 3), args, uintptr(unsafe.Pointer(&raw))) // get_Uri
	if hresultFailed(hr) || raw == 0 {
		syscall.SyscallN(method(args, 6), args, 1) // put_Handled(TRUE)
		return sOK
	}
	u := utf16PtrToString((*uint16)(unsafe.Pointer(raw)))
	pCoTaskMemFree.Call(raw)
	logLine("NEW_WINDOW_REQUEST=" + u)
	parsed, err := url.Parse(u)
	if err == nil && (parsed.Hostname() == "127.0.0.1" || strings.EqualFold(parsed.Hostname(), "localhost") || parsed.Scheme == "about") {
		_ = navigate(u)
	} else if u != "" {
		shellOpen(u)
	}
	syscall.SyscallN(method(args, 6), args, 1) // handled
	return sOK
}

func navigate(u string) error {
	if webview == 0 {
		return errors.New("WEBVIEW2_CORE_NOT_READY")
	}
	p := utf16Ptr(u)
	hr, _, _ := syscall.SyscallN(method(webview, 5), webview, uintptr(unsafe.Pointer(p)))
	if hresultFailed(hr) {
		return fmt.Errorf("WEBVIEW2_NAVIGATE_FAILED=%s URL=%s", hresultString(hr), u)
	}
	return nil
}

func utf16PtrToString(p *uint16) string {
	if p == nil {
		return ""
	}
	a := make([]uint16, 0, 128)
	for i := uintptr(0); ; i++ {
		v := *(*uint16)(unsafe.Pointer(uintptr(unsafe.Pointer(p)) + i*2))
		if v == 0 {
			break
		}
		a = append(a, v)
	}
	return string(utf16.Decode(a))
}

func shellOpen(u string) {
	op := utf16Ptr("open")
	p := utf16Ptr(u)
	r, _, _ := pShellExecuteW.Call(mainHwnd, uintptr(unsafe.Pointer(op)), uintptr(unsafe.Pointer(p)), 0, 0, swShow)
	if r <= 32 {
		logLine(fmt.Sprintf("SHELLEXECUTE_WARN=%d URL=%s", r, u))
	}
}

func resizeWebView() {
	if mainHwnd == 0 || controller == 0 {
		return
	}
	var r rect
	ok, _, _ := pGetClientRect.Call(mainHwnd, uintptr(unsafe.Pointer(&r)))
	if ok == 0 {
		return
	}
	hr, _, _ := syscall.SyscallN(method(controller, 6), controller, uintptr(unsafe.Pointer(&r))) // put_Bounds(RECT)
	if hresultFailed(hr) {
		logLine("WEBVIEW2_RESIZE_WARN=" + hresultString(hr))
	}
}

func failAsync(err error) {
	stateMu.Lock()
	if startupErr == nil {
		startupErr = err
	}
	stateMu.Unlock()
	logLine("ASYNC_FAIL=" + err.Error())
	if mainHwnd != 0 {
		pPostMessageW.Call(mainHwnd, wmFailed, 0, 0)
	}
}

func initHandlerVtables() {
	qi := syscall.NewCallback(queryInterface)
	ar := syscall.NewCallback(addRef)
	rel := syscall.NewCallback(release)
	envVtbl = handlerVtbl{qi, ar, rel, syscall.NewCallback(envInvoke)}
	controllerVtbl = handlerVtbl{qi, ar, rel, syscall.NewCallback(controllerInvoke)}
	newWindowVtbl = handlerVtbl{qi, ar, rel, syscall.NewCallback(newWindowInvoke)}
	envHandler.Vtbl = &envVtbl
	controllerHandler.Vtbl = &controllerVtbl
	newWindowHandler.Vtbl = &newWindowVtbl
}

func loaderPath() string { return filepath.Join(exeDir(), "WebView2Loader.dll") }
func checkWebViewRuntime() (string, error) {
	lp := loaderPath()
	if st, err := os.Stat(lp); err != nil || st.IsDir() {
		return "", fmt.Errorf("WEBVIEW2_LOADER_MISSING=%s", lp)
	}
	dll, err := syscall.LoadDLL(lp)
	if err != nil {
		return "", fmt.Errorf("WEBVIEW2_LOADER_LOAD_FAILED=%w", err)
	}
	defer dll.Release()
	proc, err := dll.FindProc("GetAvailableCoreWebView2BrowserVersionString")
	if err != nil {
		return "", fmt.Errorf("WEBVIEW2_VERSION_PROC_MISSING=%w", err)
	}
	var out uintptr
	hr, _, _ := proc.Call(0, uintptr(unsafe.Pointer(&out)))
	if hresultFailed(hr) || out == 0 {
		return "", fmt.Errorf("WEBVIEW2_RUNTIME_NOT_AVAILABLE HRESULT=%s", hresultString(hr))
	}
	s := utf16PtrToString((*uint16)(unsafe.Pointer(out)))
	pCoTaskMemFree.Call(out)
	if strings.TrimSpace(s) == "" {
		return "", errors.New("WEBVIEW2_RUNTIME_VERSION_EMPTY")
	}
	return s, nil
}

func beginWebView() error {
	v, err := checkWebViewRuntime()
	if err != nil {
		return err
	}
	logLine("WEBVIEW2_RUNTIME=" + v)
	lp := loaderPath()
	dll, err := syscall.LoadDLL(lp)
	if err != nil {
		return err
	}
	loaderDLL = dll
	proc, err := dll.FindProc("CreateCoreWebView2EnvironmentWithOptions")
	if err != nil {
		return err
	}
	profile := filepath.Join(os.Getenv("LOCALAPPDATA"), "Agape", "WebView2", "UserData")
	if err := os.MkdirAll(profile, 0755); err != nil {
		return err
	}
	pp := utf16Ptr(profile)
	hr, _, _ := proc.Call(0, uintptr(unsafe.Pointer(pp)), 0, uintptr(unsafe.Pointer(&envHandler)))
	if hresultFailed(hr) {
		return fmt.Errorf("WEBVIEW2_ENVIRONMENT_REQUEST_FAILED=%s", hresultString(hr))
	}
	return nil
}

func httpGetJSON(u string, out any, timeout time.Duration) error {
	c := &http.Client{Timeout: timeout}
	r, e := c.Get(u)
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
	e := httpGetJSON(fmt.Sprintf("http://127.0.0.1:%d/api/version", corePort), &v, 4*time.Second)
	if e != nil {
		return nil, e
	}
	return &v, nil
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
func findCore() (string, error) {
	if v, e := getVersion(); e == nil && v.ProjectPath != "" && validCore(v.ProjectPath) {
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
func hiddenCommand(name string, args ...string) *exec.Cmd {
	c := exec.Command(name, args...)
	c.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000}
	return c
}
func findPython() string {
	la := os.Getenv("LOCALAPPDATA")
	for _, n := range []string{"Python312", "Python313", "Python314"} {
		p := filepath.Join(la, "Programs", "Python", n, "python.exe")
		if st, e := os.Stat(p); e == nil && !st.IsDir() {
			return p
		}
	}
	for _, n := range []string{"python.exe", "python"} {
		if p, e := exec.LookPath(n); e == nil {
			return p
		}
	}
	return ""
}
func powerShellPath() string {
	p := filepath.Join(os.Getenv("SystemRoot"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
	if _, e := os.Stat(p); e == nil {
		return p
	}
	return "powershell.exe"
}
func startLogged(cmd *exec.Cmd, label string) (string, error) {
	lp := filepath.Join(exeDir(), "backend-start-"+label+".log")
	f, e := os.OpenFile(lp, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0644)
	if e != nil {
		return lp, e
	}
	cmd.Stdout = f
	cmd.Stderr = f
	e = cmd.Start()
	_ = f.Close()
	if e == nil {
		logLine("BACKEND_START=" + label + " PID=" + fmt.Sprint(cmd.Process.Pid))
	}
	return lp, e
}
func waitCore(seconds int) (*versionInfo, error) {
	deadline := time.Now().Add(time.Duration(seconds) * time.Second)
	var last error
	for time.Now().Before(deadline) {
		v, e := getVersion()
		if e == nil {
			if v.Build != expectedBuild {
				return nil, fmt.Errorf("WRONG_LIVE_BUILD=%s EXPECTED=%s", v.Build, expectedBuild)
			}
			return v, nil
		}
		last = e
		time.Sleep(500 * time.Millisecond)
	}
	if last == nil {
		last = errors.New("NO_RESPONSE")
	}
	return nil, last
}
func tailFile(path string, max int) string {
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

func ensureCore(core string) (*versionInfo, error) {
	if v, e := getVersion(); e == nil {
		if v.Build != expectedBuild {
			return nil, fmt.Errorf("WRONG_LIVE_BUILD=%s EXPECTED=%s", v.Build, expectedBuild)
		}
		return v, nil
	}
	// First choice: direct Python, hidden, which cannot intentionally open a browser.
	if py := findPython(); py != "" {
		c := hiddenCommand(py, filepath.Join(core, "app.py"), "--port", fmt.Sprint(corePort))
		c.Dir = core
		lp, e := startLogged(c, "python")
		if e == nil {
			if v, x := waitCore(35); x == nil {
				logLine("CORE_START_MODE=PYTHON_DIRECT")
				return v, nil
			} else {
				logLine("PYTHON_START_NOT_READY=" + x.Error() + " LOG=" + tailFile(lp, 15))
			}
		}
	}
	// R8 compatibility launcher explicitly suppresses external browser startup.
	starter := filepath.Join(core, "START-DMT-SECOND-BRAIN.ps1")
	c := hiddenCommand(powerShellPath(), "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", starter, "-Port", fmt.Sprint(corePort), "-NoBrowser")
	c.Dir = core
	lp, e := startLogged(c, "powershell-nobrowser")
	if e != nil {
		return nil, fmt.Errorf("CORE_NOBROWSER_START_FAILED=%w", e)
	}
	if v, x := waitCore(50); x == nil {
		logLine("CORE_START_MODE=POWERSHELL_NOBROWSER")
		return v, nil
	} else {
		return nil, fmt.Errorf("AGAPE_CORE_DID_NOT_START_ON_8797 LAST=%v LOG=%s", x, tailFile(lp, 25))
	}
}

func verifyUI(core string) error {
	b, e := os.ReadFile(filepath.Join(core, "index.html"))
	if e != nil {
		return fmt.Errorf("INDEX_READ_FAILED=%w", e)
	}
	s := string(b)
	markers := []string{"data-page=\"chat\"", "data-page=\"settings\"", "workspace-manage-projects", "project-instructions-text", "project-document-choose", "Choose Document"}
	n := 0
	for _, m := range markers {
		if strings.Contains(s, m) {
			n++
		}
	}
	logLine(fmt.Sprintf("R8_UI_MARKERS=%d/%d", n, len(markers)))
	if n < 4 {
		return fmt.Errorf("CURRENT_R8_UI_MARKERS_MISSING=%d/%d", n, len(markers))
	}
	c := &http.Client{Timeout: 15 * time.Second}
	r, e := c.Get(backendURL)
	if e != nil {
		return fmt.Errorf("UI_NOT_REACHABLE=%w", e)
	}
	defer r.Body.Close()
	if r.StatusCode != 200 {
		return fmt.Errorf("UI_HTTP_STATUS=%d", r.StatusCode)
	}
	served, e := io.ReadAll(io.LimitReader(r.Body, 4*1024*1024))
	if e != nil {
		return e
	}
	if len(served) < 1000 {
		return fmt.Errorf("UI_RESPONSE_TOO_SMALL=%d", len(served))
	}
	if !strings.Contains(string(served), "project-instructions-text") {
		return errors.New("SERVED_UI_NOT_CURRENT_R8")
	}
	h := sha256.Sum256(b)
	logLine("INDEX_SHA256=" + strings.ToUpper(hex.EncodeToString(h[:])))
	return nil
}
func verifySystemTest() error {
	var t systemTest
	e := httpGetJSON("http://127.0.0.1:8797/api/system-test", &t, 120*time.Second)
	if e != nil {
		return fmt.Errorf("SYSTEM_TEST_REQUEST_FAILED=%w", e)
	}
	if !t.OK {
		return fmt.Errorf("SYSTEM_TEST_FAILED PASSED=%d TOTAL=%d", t.Passed, t.Total)
	}
	logLine(fmt.Sprintf("SYSTEM_TEST=PASS PASSED=%d TOTAL=%d", t.Passed, t.Total))
	return nil
}

func getProjects() ([]projectRecord, error) {
	var c projectCatalog
	if e := httpGetJSON("http://127.0.0.1:8797/api/projects?scope=all", &c, 12*time.Second); e != nil {
		// Older R8 builds may not accept scope=all; retry the normal project list.
		if e2 := httpGetJSON("http://127.0.0.1:8797/api/projects", &c, 12*time.Second); e2 != nil {
			return nil, fmt.Errorf("PROJECT_CATALOG_REQUEST_FAILED=%v RETRY=%v", e, e2)
		}
	}
	return c.Projects, nil
}

func chooseMainProject(items []projectRecord) (*projectRecord, error) {
	usable := make([]projectRecord, 0, len(items))
	for _, p := range items {
		if bool(p.Archived) {
			continue
		}
		k := strings.ToLower(strings.TrimSpace(p.Kind))
		if k == "" {
			k = "user"
		}
		if k == "user" {
			usable = append(usable, p)
		}
	}
	if len(usable) == 0 {
		return nil, errors.New("NO_ACTIVE_USER_PROJECTS")
	}
	preferred := strings.TrimSpace(os.Getenv("AGAPE_MAIN_PROJECT_NAME"))
	if preferred != "" {
		for i := range usable {
			if strings.EqualFold(strings.TrimSpace(usable[i].Name), preferred) {
				return &usable[i], nil
			}
		}
	}
	for _, exact := range []string{"agape main project", "agape main", "agape"} {
		for i := range usable {
			if strings.EqualFold(strings.TrimSpace(usable[i].Name), exact) {
				return &usable[i], nil
			}
		}
	}
	for i := range usable {
		n := strings.ToLower(usable[i].Name)
		if strings.Contains(n, "agape") && !strings.Contains(n, "test") && !strings.Contains(n, "template") && !strings.Contains(n, "demo") {
			return &usable[i], nil
		}
	}
	if len(usable) == 1 {
		return &usable[0], nil
	}
	// Prefer the project whose workspace/path points into the current Agape installation.
	for i := range usable {
		q := strings.ToLower(usable[i].Path + " " + usable[i].Workspace)
		if strings.Contains(q, "dmt-core-v3.1") || strings.Contains(q, "agape") {
			return &usable[i], nil
		}
	}
	// Do not silently bind to a system/template/test project; first active user project is the safe fallback.
	return &usable[0], nil
}

func verifyMainProject() (*projectRecord, error) {
	items, e := getProjects()
	if e != nil {
		return nil, e
	}
	p, e := chooseMainProject(items)
	if e != nil {
		return nil, e
	}
	logLine(fmt.Sprintf("MAIN_PROJECT=PASS ID=%d NAME=%s KIND=%s PATH=%s WORKSPACE=%s", p.ID, p.Name, p.Kind, p.Path, p.Workspace))
	return p, nil
}

func mainProjectInjection() string {
	return `<script id="agape-windows11-main-project-bridge">
(function(){
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const bad=n=>/\\b(test|template|demo|system)\\b/i.test(n||'');
  function choose(list){
    const usable=(list||[]).filter(p=>!Boolean(p.archived)&&String(p.kind||'user').toLowerCase()==='user');
    const saved=(localStorage.getItem('agape-windows-main-project-name')||'').trim();
    if(saved){const p=usable.find(x=>String(x.name||'').trim().toLowerCase()===saved.toLowerCase());if(p)return p;}
    for(const n of ['agape main project','agape main','agape']){const p=usable.find(x=>String(x.name||'').trim().toLowerCase()===n);if(p)return p;}
    let p=usable.find(x=>/agape/i.test(String(x.name||''))&&!bad(String(x.name||'')));if(p)return p;
    if(usable.length===1)return usable[0];
    p=usable.find(x=>/dmt-core-v3\\.1|agape/i.test(String(x.path||'')+' '+String(x.workspace||'')));return p||usable[0]||null;
  }
  async function loadMain(){
    for(let i=0;i<100;i++){
      try{
        if(typeof projects!=='undefined'&&Array.isArray(projects)&&projects.length&&typeof currentProject!=='undefined'){
          const p=choose(projects);if(!p)return;
          currentProject=Number(p.id);localStorage.setItem('agape-windows-main-project-name',String(p.name||''));
          if(typeof renderProjects==='function')renderProjects();
          if(typeof loadMessages==='function')await loadMessages();
          if(typeof refreshWorkspace==='function')await refreshWorkspace();
          if(typeof loadProjectTemplate==='function')await loadProjectTemplate();
          const sel=document.getElementById('workspace-project-select');if(sel)sel.value=String(p.id);
          const tab=[...document.querySelectorAll('.tabs button')].find(x=>x.dataset.page==='workspace');
          if(tab)tab.click();
          window.AGAPE_WINDOWS11_MAIN_PROJECT={id:p.id,name:p.name,kind:p.kind||'user'};
          document.title='Agape - '+String(p.name||'Main Project');
          return;
        }
      }catch(e){console.warn('AGAPE_WINDOWS_MAIN_PROJECT_LOAD',e)}
      await sleep(150);
    }
  }
  document.addEventListener('change',e=>{if(e.target&&e.target.id==='workspace-project-select'){try{const p=(projects||[]).find(x=>Number(x.id)===Number(e.target.value));if(p)localStorage.setItem('agape-windows-main-project-name',String(p.name||''));}catch(_){}}},true);
  document.addEventListener('click',()=>setTimeout(()=>{try{const p=(projects||[]).find(x=>Number(x.id)===Number(currentProject));if(p)localStorage.setItem('agape-windows-main-project-name',String(p.name||''));}catch(_){}},50),true);
  window.addEventListener('load',()=>setTimeout(loadMain,50));
})();
</script>`
}

func startDesktopBridge() error {
	target, _ := url.Parse(backendURL)
	proxy := httputil.NewSingleHostReverseProxy(target)
	origDirector := proxy.Director
	proxy.Director = func(r *http.Request) {
		origDirector(r)
		r.Host = target.Host
		r.Header.Del("Accept-Encoding")
		r.Header.Set("X-Agape-Windows-Host", "R7.1")
	}
	proxy.ModifyResponse = func(resp *http.Response) error {
		if resp.Request != nil && resp.Request.URL.Path == "/" && strings.Contains(strings.ToLower(resp.Header.Get("Content-Type")), "text/html") {
			b, e := io.ReadAll(io.LimitReader(resp.Body, 8*1024*1024))
			if e != nil {
				return e
			}
			_ = resp.Body.Close()
			t := string(b)
			inject := mainProjectInjection()
			lower := strings.ToLower(t)
			pos := strings.LastIndex(lower, "</body>")
			if pos >= 0 {
				t = t[:pos] + inject + t[pos:]
			} else {
				t += inject
			}
			resp.Body = io.NopCloser(strings.NewReader(t))
			resp.ContentLength = int64(len(t))
			resp.Header.Set("Content-Length", fmt.Sprint(len(t)))
			resp.Header.Del("Content-Encoding")
		}
		return nil
	}
	ln, e := net.Listen("tcp", "127.0.0.1:0")
	if e != nil {
		return fmt.Errorf("DESKTOP_BRIDGE_LISTEN_FAILED=%w", e)
	}
	bridgeServer = &http.Server{Handler: proxy, ReadHeaderTimeout: 10 * time.Second}
	homeURL = "http://" + ln.Addr().String() + "/"
	go func() {
		if e := bridgeServer.Serve(ln); e != nil && !errors.Is(e, http.ErrServerClosed) {
			logLine("DESKTOP_BRIDGE_FAIL=" + e.Error())
		}
	}()
	logLine("DESKTOP_BRIDGE=PASS URL=" + homeURL)
	return nil
}

func startOptionalSidecars(core string) {
	// Document Studio R31.10
	studioHealth := "http://127.0.0.1:8800/api/health"
	c := &http.Client{Timeout: 1200 * time.Millisecond}
	if r, e := c.Get(studioHealth); e == nil {
		r.Body.Close()
		if r.StatusCode == 200 {
			goto work
		}
	}
	if p := filepath.Join(core, "OPEN-AGAPE-DOCUMENT-STUDIO.ps1"); fileExists(p) {
		cmd := hiddenCommand(powerShellPath(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", p, "-NoBrowser")
		cmd.Dir = core
		_, _ = startLogged(cmd, "studio")
	} else if py := findPython(); py != "" {
		p := filepath.Join(core, "agape-document-studio", "document_studio.py")
		if fileExists(p) {
			cmd := hiddenCommand(py, p, "--port", "8800", "--no-browser")
			cmd.Dir = filepath.Dir(p)
			_, _ = startLogged(cmd, "studio-python")
		}
	}
work:
	workHealth := "http://127.0.0.1:8820/api/health"
	if r, e := c.Get(workHealth); e == nil {
		r.Body.Close()
		if r.StatusCode == 200 {
			return
		}
	}
	if p := filepath.Join(core, "OPEN-AGAPE-WORK-ENGINE.ps1"); fileExists(p) {
		cmd := hiddenCommand(powerShellPath(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", p, "-NoBrowser")
		cmd.Dir = core
		_, _ = startLogged(cmd, "work")
	}
}
func fileExists(p string) bool { st, e := os.Stat(p); return e == nil && !st.IsDir() }

func backendReady() {
	core, err := findCore()
	if err == nil {
		coreRoot = core
		var v *versionInfo
		v, err = ensureCore(core)
		if err == nil {
			logLine("LIVE_BUILD=" + v.Build)
			err = verifyUI(core)
		}
	}
	if err == nil {
		_, err = verifyMainProject()
	}
	if err == nil {
		err = startDesktopBridge()
	}
	if err != nil {
		stateMu.Lock()
		startupErr = err
		stateMu.Unlock()
		logLine("BACKEND_FAIL=" + err.Error())
		pPostMessageW.Call(mainHwnd, wmFailed, 0, 0)
		return
	}
	go startOptionalSidecars(coreRoot)
	pPostMessageW.Call(mainHwnd, wmReady, 0, 0)
}

func showError(err error) {
	msg := "Agape could not start.\r\n\r\n" + err.Error() + "\r\n\r\nDiagnostic log:\r\n" + logPath()
	pMessageBoxW.Call(mainHwnd, uintptr(unsafe.Pointer(utf16Ptr(msg))), uintptr(unsafe.Pointer(utf16Ptr("Agape startup error"))), 0x10)
}

func wndProc(hwnd uintptr, message uint32, wParam, lParam uintptr) uintptr {
	switch message {
	case wmSize:
		resizeWebView()
		return 0
	case wmReady:
		setTitle("Agape - loading interface...")
		if err := beginWebView(); err != nil {
			stateMu.Lock()
			startupErr = err
			stateMu.Unlock()
			pPostMessageW.Call(hwnd, wmFailed, 0, 0)
		}
		return 0
	case wmFailed:
		stateMu.Lock()
		e := startupErr
		stateMu.Unlock()
		if e == nil {
			e = errors.New("UNKNOWN_STARTUP_FAILURE")
		}
		showError(e)
		pDestroyWindow.Call(hwnd)
		return 0
	case wmClose:
		pDestroyWindow.Call(hwnd)
		return 0
	case wmDestroy:
		if bridgeServer != nil {
			_ = bridgeServer.Close()
		}
		if controller != 0 {
			syscall.SyscallN(method(controller, 24), controller)
		}
		if webview != 0 {
			syscall.SyscallN(method(webview, 2), webview)
			webview = 0
		}
		if controller != 0 {
			syscall.SyscallN(method(controller, 2), controller)
			controller = 0
		}
		pPostQuitMessage.Call(0)
		return 0
	}
	r, _, _ := pDefWindowProcW.Call(hwnd, uintptr(message), wParam, lParam)
	return r
}

func createWindow() error {
	hInst, _, _ := pGetModuleHandleW.Call(0)
	cursor, _, _ := pLoadCursorW.Call(0, 32512)
	cls := utf16Ptr(windowClassName)
	wc := wndClassEx{CbSize: uint32(unsafe.Sizeof(wndClassEx{})), LpfnWndProc: syscall.NewCallback(wndProc), HInstance: hInst, HCursor: cursor, HbrBackground: 6, LpszClassName: cls}
	a, _, e := pRegisterClassExW.Call(uintptr(unsafe.Pointer(&wc)))
	if a == 0 {
		return fmt.Errorf("REGISTER_WINDOW_CLASS_FAILED=%v", e)
	}
	title := utf16Ptr("Agape - starting...")
	hwnd, _, e := pCreateWindowExW.Call(0, uintptr(unsafe.Pointer(cls)), uintptr(unsafe.Pointer(title)), wsOverlappedWindow|wsVisible, 120, 80, 1440, 920, 0, 0, hInst, 0)
	if hwnd == 0 {
		return fmt.Errorf("CREATE_WINDOW_FAILED=%v", e)
	}
	mainHwnd = hwnd
	pShowWindow.Call(hwnd, swShow)
	pUpdateWindow.Call(hwnd)
	return nil
}
func messageLoop() {
	var m msg
	for {
		r, _, _ := pGetMessageW.Call(uintptr(unsafe.Pointer(&m)), 0, 0, 0)
		if int32(r) <= 0 {
			break
		}
		pTranslateMessage.Call(uintptr(unsafe.Pointer(&m)))
		pDispatchMessageW.Call(uintptr(unsafe.Pointer(&m)))
	}
}

func ensureSingleInstance() (uintptr, bool) {
	name := utf16Ptr("Local\\AgapeWindows11MainProjectR71")
	h, _, _ := pCreateMutexW.Call(0, 1, uintptr(unsafe.Pointer(name)))
	if h == 0 {
		return 0, true
	}
	last, _, _ := pGetLastError.Call()
	if last == 183 {
		return h, false
	}
	return h, true
}

func validate() error {
	core, e := findCore()
	if e != nil {
		return e
	}
	v, e := ensureCore(core)
	if e != nil {
		return e
	}
	if v.Build != expectedBuild {
		return fmt.Errorf("WRONG_BUILD=%s", v.Build)
	}
	if e = verifyUI(core); e != nil {
		return e
	}
	if e = verifySystemTest(); e != nil {
		return e
	}
	if _, e = verifyMainProject(); e != nil {
		return e
	}
	wv, e := checkWebViewRuntime()
	if e != nil {
		return e
	}
	logLine("WEBVIEW2_RUNTIME=" + wv)
	return nil
}

func main() {
	logLine("------------------------------------------------------------")
	logLine("AGAPE_WINDOWS11_MAIN_PROJECT_R7_1_START")
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	for _, a := range os.Args[1:] {
		if a == "--webview-check" {
			if v, e := checkWebViewRuntime(); e != nil {
				logLine("WEBVIEW_CHECK_FAIL=" + e.Error())
				os.Exit(2)
			} else {
				logLine("WEBVIEW_CHECK_PASS=" + v)
				os.Exit(0)
			}
		}
		if a == "--validate" {
			if e := validate(); e != nil {
				logLine("VALIDATE_FAIL=" + e.Error())
				os.Exit(3)
			}
			logLine("VALIDATE=PASS")
			os.Exit(0)
		}
	}

	mutex, first := ensureSingleInstance()
	_ = mutex
	if !first {
		logLine("SECOND_INSTANCE_BLOCKED=YES")
		return
	}
	// Per-monitor V2 when supported.
	if e := pSetDpiContext.Find(); e == nil {
		pSetDpiContext.Call(^uintptr(3))
	}
	hr, _, _ := pCoInitializeEx.Call(0, coinitApartmentThreaded)
	if hresultFailed(hr) {
		logLine("COINITIALIZE_FAILED=" + hresultString(hr))
		return
	}
	defer pCoUninitialize.Call()
	initHandlerVtables()
	if err := createWindow(); err != nil {
		logLine("WINDOW_CREATE_FAIL=" + err.Error())
		return
	}
	go backendReady()
	messageLoop()
	logLine("AGAPE_WINDOWS11_MAIN_PROJECT_R7_1_EXIT")
}
