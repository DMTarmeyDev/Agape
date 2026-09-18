package dev.dmtarmey.agape;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.SslErrorHandler;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.net.http.SslError;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.util.Locale;

public class MainActivity extends Activity {

    private static final String AGAPE_BASE = BuildConfig.AGAPE_BASE_URL;
    private static final String AGAPE_HOST = Uri.parse(AGAPE_BASE).getHost().toLowerCase(Locale.ROOT);
    private static final String PREFS = "agape_android";
    private static final String PREF_VIEW = "preferred_view";
    private static final int FILE_CHOOSER_REQUEST = 6011;

    private WebView webView;
    private FrameLayout webContainer;
    private LinearLayout errorPanel;
    private TextView statusText;
    private ValueCallback<Uri[]> pendingFileCallback;
    private SharedPreferences preferences;
    private String currentViewMode = "webapp";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        getWindow().setStatusBarColor(Color.rgb(17, 17, 17));
        getWindow().setNavigationBarColor(Color.rgb(17, 17, 17));

        preferences = getSharedPreferences(PREFS, MODE_PRIVATE);

        buildInterface();
        configureWebView();

        if (savedInstanceState != null && webView.restoreState(savedInstanceState) != null) {
            updateStatus("Online");
            return;
        }

        String saved = preferences.getString(PREF_VIEW, null);
        if (saved != null) {
            currentViewMode = saved;
            loadAgape();
            return;
        }

        if (isTablet()) {
            showViewChoice(true);
        } else {
            currentViewMode = "webapp";
            loadAgape();
        }
    }

    private void buildInterface() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.WHITE);

        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setOrientation(LinearLayout.HORIZONTAL);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.setPadding(dp(14), dp(4), dp(8), dp(4));
        toolbar.setBackgroundColor(Color.rgb(17, 17, 17));

        TextView title = new TextView(this);
        title.setText("Agape");
        title.setTextColor(Color.WHITE);
        title.setTextSize(20);
        title.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.addView(title, new LinearLayout.LayoutParams(0, dp(48), 1f));

        statusText = new TextView(this);
        statusText.setText("Connecting");
        statusText.setTextColor(Color.LTGRAY);
        statusText.setTextSize(12);
        statusText.setGravity(Gravity.CENTER);
        toolbar.addView(statusText, new LinearLayout.LayoutParams(dp(78), dp(48)));

        Button viewButton = toolbarButton("View");
        viewButton.setOnClickListener(v -> showViewChoice(false));
        toolbar.addView(viewButton, new LinearLayout.LayoutParams(dp(70), dp(44)));

        Button refreshButton = toolbarButton("Reload");
        refreshButton.setOnClickListener(v -> retryCurrentPage());
        toolbar.addView(refreshButton, new LinearLayout.LayoutParams(dp(78), dp(44)));

        root.addView(toolbar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(56)
        ));

        webContainer = new FrameLayout(this);
        webView = new WebView(this);
        webContainer.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));

        errorPanel = buildErrorPanel();
        errorPanel.setVisibility(View.GONE);
        webContainer.addView(errorPanel, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));

        root.addView(webContainer, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1f
        ));

        setContentView(root);
    }

    private Button toolbarButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextSize(12);
        button.setAllCaps(false);
        button.setTextColor(Color.WHITE);
        button.setBackgroundColor(Color.TRANSPARENT);
        button.setPadding(dp(4), 0, dp(4), 0);
        return button;
    }

    private LinearLayout buildErrorPanel() {
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setGravity(Gravity.CENTER);
        panel.setPadding(dp(28), dp(28), dp(28), dp(28));
        panel.setBackgroundColor(Color.rgb(246, 246, 246));

        TextView heading = new TextView(this);
        heading.setText("Agape server is unavailable");
        heading.setTextSize(22);
        heading.setTextColor(Color.rgb(30, 30, 30));
        heading.setGravity(Gravity.CENTER);
        panel.addView(heading, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));

        TextView detail = new TextView(this);
        detail.setId(View.generateViewId());
        detail.setTag("error-detail");
        detail.setText("Check your internet connection and make sure the Agape server is online.");
        detail.setTextSize(15);
        detail.setTextColor(Color.DKGRAY);
        detail.setGravity(Gravity.CENTER);
        detail.setPadding(0, dp(14), 0, dp(18));
        panel.addView(detail, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));

        Button retry = new Button(this);
        retry.setText("Retry");
        retry.setAllCaps(false);
        retry.setOnClickListener(v -> retryCurrentPage());
        panel.addView(retry, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                dp(48)
        ));

        return panel;
    }

    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSupportMultipleWindows(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setUserAgentString(settings.getUserAgentString() + " AgapeAndroid/5.6.1-r2.5.0");

        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, false);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return handleNavigation(request.getUrl());
            }

            @Override
            public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                hideError();
                updateStatus("Loading");
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                updateStatus("Online");
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    showError("Could not reach Agape. " + error.getDescription());
                }
            }

            @Override
            public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse errorResponse) {
                if (request.isForMainFrame() && errorResponse.getStatusCode() >= 500) {
                    showError("Agape returned HTTP " + errorResponse.getStatusCode() + ".");
                }
            }

            @Override
            public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                handler.cancel();
                showError("Secure connection validation failed. Agape was not opened.");
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(
                    WebView webView,
                    ValueCallback<Uri[]> filePathCallback,
                    FileChooserParams fileChooserParams
            ) {
                if (pendingFileCallback != null) {
                    pendingFileCallback.onReceiveValue(null);
                }
                pendingFileCallback = filePathCallback;

                Intent intent;
                try {
                    intent = fileChooserParams.createIntent();
                    startActivityForResult(intent, FILE_CHOOSER_REQUEST);
                    return true;
                } catch (ActivityNotFoundException ex) {
                    pendingFileCallback = null;
                    Toast.makeText(MainActivity.this, "No file picker is available.", Toast.LENGTH_LONG).show();
                    return false;
                }
            }
        });

        webView.setDownloadListener(new DownloadListener() {
            @Override
            public void onDownloadStart(
                    String url,
                    String userAgent,
                    String contentDisposition,
                    String mimeType,
                    long contentLength
            ) {
                downloadFile(url, userAgent, contentDisposition, mimeType);
            }
        });
    }

    private boolean handleNavigation(Uri uri) {
        if (uri == null) return true;

        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
        String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase(Locale.ROOT);

        if ("https".equals(scheme) && AGAPE_HOST.equals(host)) {
            return false;
        }

        if ("https".equals(scheme) || "http".equals(scheme) || "mailto".equals(scheme) || "tel".equals(scheme)) {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, uri));
            } catch (ActivityNotFoundException ex) {
                Toast.makeText(this, "No app can open this link.", Toast.LENGTH_SHORT).show();
            }
            return true;
        }

        Toast.makeText(this, "Blocked unsupported link.", Toast.LENGTH_SHORT).show();
        return true;
    }

    private void downloadFile(String url, String userAgent, String contentDisposition, String mimeType) {
        if (url == null || !url.startsWith("https://")) {
            Toast.makeText(this, "Only secure HTTPS downloads are allowed.", Toast.LENGTH_LONG).show();
            return;
        }

        if (url.startsWith("blob:")) {
            Toast.makeText(this, "This download type is not supported by the Android wrapper yet.", Toast.LENGTH_LONG).show();
            return;
        }

        try {
            Uri uri = Uri.parse(url);
            String filename = URLUtil.guessFileName(url, contentDisposition, mimeType);

            DownloadManager.Request request = new DownloadManager.Request(uri);
            request.setTitle(filename);
            request.setDescription("Downloading from Agape");
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            request.setAllowedOverMetered(true);
            request.setAllowedOverRoaming(true);

            if (mimeType != null && !mimeType.isEmpty()) {
                request.setMimeType(mimeType);
            }

            String cookies = CookieManager.getInstance().getCookie(url);
            if (cookies != null && !cookies.isEmpty()) {
                request.addRequestHeader("Cookie", cookies);
            }
            if (userAgent != null && !userAgent.isEmpty()) {
                request.addRequestHeader("User-Agent", userAgent);
            }

            request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename);

            DownloadManager manager = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
            manager.enqueue(request);
            Toast.makeText(this, "Downloading " + filename, Toast.LENGTH_LONG).show();
        } catch (Exception ex) {
            Toast.makeText(this, "Download failed: " + ex.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private void showViewChoice(boolean firstLaunch) {
        String[] choices = {
                "Web App — touch-friendly",
                "Full App — desktop layout"
        };

        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("Choose Agape view")
                .setItems(choices, (d, which) -> {
                    currentViewMode = which == 0 ? "webapp" : "full";
                    preferences.edit().putString(PREF_VIEW, currentViewMode).apply();
                    loadAgape();
                })
                .create();

        dialog.setCanceledOnTouchOutside(!firstLaunch);
        dialog.setCancelable(!firstLaunch);
        dialog.show();
    }

    private void loadAgape() {
        if (!hasUsableNetwork()) {
            showError("This phone is offline. Connect to the internet and retry.");
            return;
        }
        hideError();
        updateStatus("Connecting");
        webView.loadUrl(AGAPE_BASE + "?view=" + currentViewMode + "&android=1");
    }

    private void retryCurrentPage() {
        hideError();
        if (!hasUsableNetwork()) {
            showError("This phone is offline. Connect to the internet and retry.");
            return;
        }
        String current = webView.getUrl();
        if (current == null || current.trim().isEmpty() || "about:blank".equals(current)) {
            loadAgape();
        } else {
            updateStatus("Loading");
            webView.reload();
        }
    }

    private boolean hasUsableNetwork() {
        ConnectivityManager manager = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        if (manager == null) return true;
        Network network = manager.getActiveNetwork();
        if (network == null) return false;
        NetworkCapabilities caps = manager.getNetworkCapabilities(network);
        return caps != null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
    }

    private boolean isTablet() {
        return getResources().getConfiguration().smallestScreenWidthDp >= 600;
    }

    private void updateStatus(String text) {
        statusText.setText(text);
    }

    private void hideError() {
        errorPanel.setVisibility(View.GONE);
        webView.setVisibility(View.VISIBLE);
    }

    private void showError(String message) {
        updateStatus("Offline");
        webView.setVisibility(View.GONE);
        errorPanel.setVisibility(View.VISIBLE);

        for (int i = 0; i < errorPanel.getChildCount(); i++) {
            View child = errorPanel.getChildAt(i);
            if (child instanceof TextView && "error-detail".equals(child.getTag())) {
                ((TextView) child).setText(message);
                break;
            }
        }
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);

        if (requestCode != FILE_CHOOSER_REQUEST || pendingFileCallback == null) return;

        Uri[] results = null;
        if (resultCode == Activity.RESULT_OK) {
            results = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
        }

        pendingFileCallback.onReceiveValue(results);
        pendingFileCallback = null;
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        webView.saveState(outState);
        super.onSaveInstanceState(outState);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (pendingFileCallback != null) {
            pendingFileCallback.onReceiveValue(null);
            pendingFileCallback = null;
        }

        if (webView != null) {
            webView.stopLoading();
            webView.loadUrl("about:blank");
            webView.clearHistory();
            webView.setWebChromeClient(null);
            webView.setWebViewClient(null);
            if (webView.getParent() instanceof ViewGroup) {
                ((ViewGroup) webView.getParent()).removeView(webView);
            }
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}
