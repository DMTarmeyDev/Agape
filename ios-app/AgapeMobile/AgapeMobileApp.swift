import SwiftUI
import WebKit

@main
struct AgapeMobileApp: App {
    @StateObject private var browser = BrowserState()

    var body: some Scene {
        WindowGroup {
            NavigationView {
                ZStack {
                    AgapeWebView(state: browser)
                        .ignoresSafeArea(edges: .bottom)

                    if let message = browser.errorMessage {
                        VStack(spacing: 16) {
                            Text("Agape server is unavailable")
                                .font(.title2)
                                .bold()
                            Text(message)
                                .multilineTextAlignment(.center)
                                .foregroundColor(.secondary)
                            Button("Retry") {
                                browser.reload()
                            }
                            .buttonStyle(.borderedProminent)
                        }
                        .padding(28)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .background(Color(.systemBackground))
                    }
                }
                .navigationTitle("Agape")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItemGroup(placement: .navigationBarLeading) {
                        Button("Back") {
                            browser.goBack()
                        }
                        .disabled(!browser.canGoBack)
                    }
                    ToolbarItemGroup(placement: .navigationBarTrailing) {
                        if browser.isLoading {
                            ProgressView()
                        }
                        Button("Reload") {
                            browser.reload()
                        }
                    }
                    ToolbarItem(placement: .bottomBar) {
                        Text(browser.statusText)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .navigationViewStyle(.stack)
        }
    }
}

@MainActor
final class BrowserState: ObservableObject {
    @Published var canGoBack = false
    @Published var isLoading = true
    @Published var statusText = "Connecting"
    @Published var errorMessage: String?

    fileprivate var goBackHandler: (() -> Void)?
    fileprivate var reloadHandler: (() -> Void)?

    func goBack() {
        goBackHandler?()
    }

    func reload() {
        errorMessage = nil
        statusText = "Connecting"
        reloadHandler?()
    }
}

private enum AgapeConfiguration {
    static let fallbackURL = URL(string: "https://agape-alpha.tail2a2d28.ts.net/")!

    static var baseURL: URL {
        guard
            let raw = Bundle.main.object(forInfoDictionaryKey: "AGAPE_BASE_URL") as? String,
            let candidate = URL(string: raw),
            candidate.scheme?.lowercased() == "https",
            candidate.host != nil
        else {
            return fallbackURL
        }
        return candidate
    }

    static var appURL: URL {
        var parts = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
        var items = parts?.queryItems ?? []
        items.removeAll { $0.name == "view" || $0.name == "ios" }
        items.append(URLQueryItem(name: "view", value: "webapp"))
        items.append(URLQueryItem(name: "ios", value: "1"))
        parts?.queryItems = items
        return parts?.url ?? baseURL
    }
}

struct AgapeWebView: UIViewRepresentable {
    @ObservedObject var state: BrowserState

    func makeCoordinator() -> Coordinator {
        Coordinator(state: state)
    }

    func makeUIView(context: Context) -> WKWebView {
        let contentController = WKUserContentController()
        contentController.add(context.coordinator, name: "agapeDownload")
        contentController.addUserScript(
            WKUserScript(
                source: """
                document.addEventListener('click', function(event) {
                  var target = event.target;
                  while (target && target.tagName !== 'A') target = target.parentElement;
                  if (!target || !target.hasAttribute('download') || !target.href) return;
                  if (!target.href.startsWith('https://')) return;
                  event.preventDefault();
                  window.webkit.messageHandlers.agapeDownload.postMessage(target.href);
                }, true);
                """,
                injectionTime: .atDocumentEnd,
                forMainFrameOnly: false
            )
        )

        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.userContentController = contentController
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        webView.allowsLinkPreview = true
        webView.scrollView.keyboardDismissMode = .interactive
        webView.customUserAgent = "AgapeIOS/5.6.1-r2.5.1"

        context.coordinator.webView = webView
        state.goBackHandler = { [weak webView] in
            if webView?.canGoBack == true {
                webView?.goBack()
            }
        }
        state.reloadHandler = { [weak webView] in
            guard let webView else { return }
            if webView.url == nil {
                webView.load(URLRequest(url: AgapeConfiguration.appURL))
            } else {
                webView.reload()
            }
        }

        webView.load(URLRequest(url: AgapeConfiguration.appURL))
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        state.canGoBack = webView.canGoBack
    }

    static func dismantleUIView(_ webView: WKWebView, coordinator: Coordinator) {
        webView.stopLoading()
        webView.navigationDelegate = nil
        webView.uiDelegate = nil
        webView.configuration.userContentController.removeScriptMessageHandler(forName: "agapeDownload")
        coordinator.webView = nil
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
        let state: BrowserState
        weak var webView: WKWebView?

        init(state: BrowserState) {
            self.state = state
        }

        func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
            Task { @MainActor in
                state.isLoading = true
                state.statusText = "Loading"
                state.errorMessage = nil
                state.canGoBack = webView.canGoBack
            }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            Task { @MainActor in
                state.isLoading = false
                state.statusText = "Online"
                state.errorMessage = nil
                state.canGoBack = webView.canGoBack
            }
        }

        func webView(
            _ webView: WKWebView,
            didFailProvisionalNavigation navigation: WKNavigation!,
            withError error: Error
        ) {
            show(error: error, webView: webView)
        }

        func webView(
            _ webView: WKWebView,
            didFail navigation: WKNavigation!,
            withError error: Error
        ) {
            show(error: error, webView: webView)
        }

        private func show(error: Error, webView: WKWebView) {
            Task { @MainActor in
                state.isLoading = false
                state.statusText = "Offline"
                state.errorMessage = "Could not reach Agape. \(error.localizedDescription)"
                state.canGoBack = webView.canGoBack
            }
        }

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction,
            decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
        ) {
            guard let url = navigationAction.request.url else {
                decisionHandler(.cancel)
                return
            }

            if url.scheme == "about" {
                decisionHandler(.allow)
                return
            }

            let base = AgapeConfiguration.baseURL
            let isAgapeHost = url.scheme?.lowercased() == "https" &&
                url.host?.lowercased() == base.host?.lowercased()

            if isAgapeHost {
                decisionHandler(.allow)
                return
            }

            let externalSchemes = Set(["https", "http", "mailto", "tel"])
            if let scheme = url.scheme?.lowercased(), externalSchemes.contains(scheme) {
                UIApplication.shared.open(url)
            }
            decisionHandler(.cancel)
        }

        func userContentController(
            _ userContentController: WKUserContentController,
            didReceive message: WKScriptMessage
        ) {
            guard
                message.name == "agapeDownload",
                let raw = message.body as? String,
                let url = URL(string: raw),
                url.scheme?.lowercased() == "https",
                url.host?.lowercased() == AgapeConfiguration.baseURL.host?.lowercased()
            else {
                return
            }

            UIApplication.shared.open(url)
        }
    }
}
