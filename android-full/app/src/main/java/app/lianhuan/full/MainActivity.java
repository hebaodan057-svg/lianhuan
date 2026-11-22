package app.lianhuan.full;

/*
 * 连环的安卓完整体 —— 后端（Python）在这个进程里跑，前端在 WebView 里开它。
 * 数据在应用自己的沙箱里（filesDir/data），不连任何电脑或云。
 *
 * 跟隔壁那个壳（android/）比，只多了一件事：开机先把后端起在 127.0.0.1:8420，
 * 等它应答了再把页面打开。其余（返回键、麦克风、选文件）一样。
 */

import android.annotation.SuppressLint;
import android.app.DownloadManager;
import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.webkit.PermissionRequest;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.URLUtil;
import android.webkit.WebViewClient;
import android.widget.Toast;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends Activity {

    private static final int PORT = 8420;
    private static final String BASE = "http://127.0.0.1:" + PORT;

    private WebView web;
    private ValueCallback<Uri[]> filePick;
    private static final int REQ_FILE = 11;
    private static final int REQ_MIC = 12;
    private PermissionRequest pendingMic;
    /** 这次启动的随机票。★ 系统下载管理器是独立进程，不共享 WebView 的 Cookie，
        所以下载请求要自己把票带上，否则后端回 401，存下来的是一句错误 JSON。 */
    private volatile String androidToken = "";

    @Override
    @SuppressLint("SetJavaScriptEnabled")
    protected void onCreate(Bundle b) {
        super.onCreate(b);

        web = new WebView(this);
        setContentView(web);

        if ((getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            WebView.setWebContentsDebuggingEnabled(true);
        }

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        // 给页面一个「我在壳里」的记号。★ 只追加，不覆盖 —— 页面里那句 /Android/i 的判断照旧成立。
        s.setUserAgentString(s.getUserAgentString() + " LianhuanShell/1");

        /* 下载。★ 0903 真机验出来的：WebView 里 <a download> 配 blob: 什么都不会发生，
           而页面还会提示「下载好了」—— 假成功比坏掉更糟。
           这里接住下载，交给系统的下载管理器：存进公共「下载」文件夹、发通知、告诉用户文件名。 */
        web.setDownloadListener((url, ua, disposition, mime, len) -> {
            try {
                String name = URLUtil.guessFileName(url, disposition, mime);
                DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url));
                if (!androidToken.isEmpty()) {
                    req.addRequestHeader("Cookie", "lh_android=" + androidToken);
                }
                req.setMimeType(mime);
                req.setTitle(name);
                req.setDescription("连环的备份");
                req.setNotificationVisibility(
                    DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
                ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(req);
                Toast.makeText(this, "存好了：手机的「下载」文件夹 / " + name,
                               Toast.LENGTH_LONG).show();
            } catch (Throwable e) {
                // ★ 宁可吵，也不要再来一次假成功
                Toast.makeText(this, "没存下来：" + e, Toast.LENGTH_LONG).show();
            }
        });
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                String url = req.getUrl().toString();
                if (url.startsWith(BASE)) return false;
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, req.getUrl()));
                } catch (Exception ignored) { }
                return true;
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                for (String r : request.getResources()) {
                    if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(r)) {
                        if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO)
                                == android.content.pm.PackageManager.PERMISSION_GRANTED) {
                            request.grant(request.getResources());
                        } else {
                            pendingMic = request;
                            requestPermissions(
                                new String[]{android.Manifest.permission.RECORD_AUDIO}, REQ_MIC);
                        }
                        return;
                    }
                }
                request.deny();
            }

            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb,
                                             FileChooserParams p) {
                if (filePick != null) filePick.onReceiveValue(null);
                filePick = cb;
                try {
                    startActivityForResult(p.createIntent(), REQ_FILE);
                } catch (Exception e) {
                    filePick = null;
                    return false;
                }
                return true;
            }
        });

        if (android.os.Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,
                () -> {
                    if (web.canGoBack()) web.goBack();
                    else finish();
                });
        }

        web.loadDataWithBaseURL(null,
            "<html><body style='font-family:sans-serif;color:#6b5f57;background:#f7f2ea;"
            + "display:flex;height:100vh;align-items:center;justify-content:center;margin:0'>"
            + "<div>连环起来中…</div></body></html>", "text/html", "utf-8", null);

        bootBackend();
    }

    /** 起后端：Python 在本进程里跑 uvicorn，起来了就开首页。第一次开要几秒（解压 Python 包）。 */
    private void bootBackend() {
        new Thread(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
                com.chaquo.python.PyObject boot = Python.getInstance().getModule("android_boot");
                boot.callAttr("start", getFilesDir().getAbsolutePath(), PORT);
                String token = boot.callAttr("token").toString();
                androidToken = token;
                // ★ 这枚指纹只用来回答一个问题：8420 上那个后端是不是我自己起的。
                String want = boot.callAttr("nonce").toString();
                for (int i = 0; i < 100; i++) {          // 最多等 20 秒
                    String err = boot.callAttr("boot_error").toString();
                    if (err != null && !err.isEmpty()) {
                        runOnUiThread(() -> show(err));     // 端口被占，或起不来：直说
                        return;
                    }
                    String got = handshake();
                    if (got != null) {
                        if (!got.equals(want)) {
                            // ★ 最要紧的一条：端口应答了，但应答的不是我。
                            //   旧代码在这里就把页面开了 —— 开的是别人的后端，
                            //   说的话也进了别人的库。宁可不开，把话说清楚。
                            runOnUiThread(() -> show(
                                "8420 上跑的不是连环自己的后端（另一个程序占着这个端口）。"
                                + "连环没有打开它 —— 那样说的话会存到别人那里去。"
                                + "关掉占着 8420 的程序再开一次。"));
                            return;
                        }
                        runOnUiThread(() -> CookieManager.getInstance().setCookie(
                            BASE, "lh_android=" + token + "; Path=/; HttpOnly; SameSite=Strict",
                            ok -> {
                                CookieManager.getInstance().flush();
                                if (ok) web.loadUrl(BASE + "/");
                                else show("本机认证票没放好，完整体没有打开。请截图发给作者。");
                            }));
                        return;
                    }
                    Thread.sleep(200);
                }
                runOnUiThread(() -> show("后端没起来。把这个页面截图发给作者。"));
            } catch (Throwable e) {
                runOnUiThread(() -> show("后端起不来：" + e));
            }
        }, "lianhuan-boot").start();
    }

    /**
     * 问 8420 上那个后端：你是谁？
     *
     * <p>返回它自称的指纹；null = 还没起来（或根本不是连环）。
     *
     * <p>★ 旧版本这里只问「活着吗」（GET /manifest.json 回 200 就算）。
     * 可「端口能应答」不等于「应答的是我」——只要 8420 被别的进程占着，
     * 那一步就会把别人的页面当成自己的开起来。开发服占 8420 那次就这么中的。
     */
    private String handshake() {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(BASE + "/api/android/hello").openConnection();
            c.setConnectTimeout(300);
            c.setReadTimeout(400);
            int code = c.getResponseCode();
            if (code != 200) { c.disconnect(); return null; }
            java.io.InputStream in = c.getInputStream();
            java.io.ByteArrayOutputStream bo = new java.io.ByteArrayOutputStream();
            byte[] buf = new byte[512];
            int n;
            while ((n = in.read(buf)) > 0) bo.write(buf, 0, n);
            in.close();
            c.disconnect();
            // 只取 "nonce" 字段，不引第三方 JSON 库
            String body = bo.toString("UTF-8");
            int i = body.indexOf("nonce");
            if (i < 0) return "";                      // 有应答但不是连环的形状
            int q1 = body.indexOf('"', body.indexOf(':', i));
            int q2 = body.indexOf('"', q1 + 1);
            if (q1 < 0 || q2 < 0) return "";
            return body.substring(q1 + 1, q2);
        } catch (Exception e) {
            if (c != null) c.disconnect();
            return null;                               // 还没起来，等下再问
        }
    }

    private void show(String msg) {
        web.loadDataWithBaseURL(null,
            "<html><body style='font-family:sans-serif;padding:24px;color:#6b5f57;background:#f7f2ea'>"
            + android.text.Html.escapeHtml(msg) + "</body></html>", "text/html", "utf-8", null);
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] grants) {
        if (code == REQ_MIC && pendingMic != null) {
            if (grants.length > 0 && grants[0] == android.content.pm.PackageManager.PERMISSION_GRANTED) {
                pendingMic.grant(pendingMic.getResources());
            } else {
                pendingMic.deny();
            }
            pendingMic = null;
        }
    }

    @Override
    protected void onActivityResult(int code, int result, Intent data) {
        if (code == REQ_FILE && filePick != null) {
            Uri[] uris = WebChromeClient.FileChooserParams.parseResult(result, data);
            /* ★ 必须把选中的 content:// URI 显式授权给 WebView。
                 系统把结果交给 Activity 时带的是「只给这个 Activity」的临时权限，
                 WebView 那边拿 Uri 去读的时候不一定能继承到 —— 不给就会是
                 「选图成功、界面啥也没出现」。这是个很典型的坑，参见
                 .operit/attachments 里那份《照片功能修复教学》的坑 3。
                 （之前只调 parseResult 就回填，所以浏览器能用、APK 不能。） */
            /* ★★ 把 content:// 逐个复制成本地文件，再回填 file:// 路径。

               为什么不只靠 grantUriPermission：
                 · 「文件」那个入口返回的是 DocumentProvider 的 URI，权限能继承，一直好用；
                 · 「照片」走的是 Android 13+ 的 Photo Picker，返回 content://media/picker/…
                   那是一条**一次性授权**的 URI —— 系统交图的那一瞬间有效，
                   grantUriPermission 对它也没用（会抛 SecurityException，被 catch 吃掉），
                   等 WebView 稍后去读时已经无权了。
                   表现就是：选图成功、界面什么都不出现（JS 那边得到空 File）。

               复制成本地文件之后，WebView 读的是自己沙箱里的 File，跟权限彻底无关。
               WebView 的 onShowFileChooser 接受 file:// 形式的返回（官方就是这么设计的）。 */
            if (uris != null) {
                for (int i = 0; i < uris.length; i++) {
                    Uri u = uris[i];
                    if (u == null) continue;
                    String sch = u.getScheme();
                    if (sch != null && sch.startsWith("file")) continue;   // 已经是文件，不动
                    java.io.InputStream in = null;
                    java.io.OutputStream out = null;
                    try {
                        in = getContentResolver().openInputStream(u);
                        if (in == null) continue;
                        java.io.File dir = new java.io.File(getCacheDir(), "picked");
                        if (!dir.exists()) dir.mkdirs();
                        String nm = String.valueOf(System.currentTimeMillis()) + "_" + i + ".bin";
                        java.io.File dst = new java.io.File(dir, nm);
                        out = new java.io.FileOutputStream(dst);
                        byte[] buf = new byte[8192];
                        int n;
                        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
                        out.flush(); out.close(); out = null;
                        in.close(); in = null;
                        uris[i] = Uri.fromFile(dst);
                    } catch (Exception ignored) {
                        /* 复制不了就保留原 Uri，至少不比以前更差 */
                    } finally {
                        try { if (out != null) out.close(); } catch (Exception ignored) { }
                        try { if (in != null) in.close(); } catch (Exception ignored) { }
                    }
                }
            }
            filePick.onReceiveValue(uris);
            filePick = null;
            return;
        }
        super.onActivityResult(code, result, data);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
}