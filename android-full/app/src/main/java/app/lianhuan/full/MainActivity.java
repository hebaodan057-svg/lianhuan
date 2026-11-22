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
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.util.Base64;
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

        installKeyboardWatcher();   /* ★ 键盘只顶输入条，见方法上的注释 */

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

    /** 监听软键盘高度，把「键盘盖住了多少 CSS px」写进页面的 --kb。
     *
     *  为什么需要它：Manifest 已经改成 adjustNothing —— 键盘弹出时 WebView
     *  **不再被系统缩小**（这才是「底栏和背景留在原位」能成立的前提）。
     *  但前端要知道输入框该抬多高，就得有一个确切的数字。
     *  WebView 里没有 Compose 的 WindowInsets.ime 那种现成东西
     *  （cleos 是原生 Compose，抄不过来），只能在壳层算好推给页面。
     *
     *  ★ 为什么不 setDecorFitsSystemWindows(false)：
     *    那会让内容铺到状态栏下面。页面里到处用 env(safe-area-inset-top)，
     *    在没开 edge-to-edge 的 WebView 里那个值是 0 —— 顶栏会被状态栏压住。
     *    为了量一个键盘高度把整个顶栏搞乱，不值得。
     *    挂在 decorView 上照样能拿到 ime inset。
     */
    private int lastKbCss = -1;

    private void installKeyboardWatcher() {
        final float density = getResources().getDisplayMetrics().density;
        final float dp = (density == 0f ? 1f : density);

        android.view.View root = getWindow().getDecorView();
        root.setOnApplyWindowInsetsListener(new android.view.View.OnApplyWindowInsetsListener() {
            @Override
            public android.view.WindowInsets onApplyWindowInsets(android.view.View v,
                                                                android.view.WindowInsets insets) {
                int imePx = 0;
                if (android.os.Build.VERSION.SDK_INT >= 30) {
                    imePx = insets.getInsets(android.view.WindowInsets.Type.ime()).bottom;
                } else {
                    /* 老机器：ime 就是底部 systemWindowInset，减掉导航栏剩键盘本身 */
                    int sysB = insets.getSystemWindowInsetBottom();
                    int nav = (android.os.Build.VERSION.SDK_INT >= 26)
                            ? insets.getStableInsetBottom() : 0;
                    imePx = Math.max(0, sysB - nav);
                }
                int css = Math.max(0, Math.round(imePx / dp));
                if (css != lastKbCss) {
                    lastKbCss = css;
                    pushKeyboardHeight(css);
                }
                return v.onApplyWindowInsets(insets);
            }
        });
        root.requestApplyInsets();
    }

    /** 把键盘高度推给页面。前端收到后写 --kb 并切 .kb-open（见 index.html 末尾）。 */
    private void pushKeyboardHeight(final int css) {
        if (web == null) return;
        web.post(new Runnable() {
            public void run() {
                try {
                    web.evaluateJavascript(
                        "window.__kbSet && window.__kbSet(" + css + ")", null);
                } catch (Exception ignored) { }
            }
        });
    }

    /** 把选中的图读出来、缩到长边 1280、压 JPEG(0.82)、base64，交给页面。
     *
     *  为什么不让 WebView 自己读：在 APK 里这条路从没通过 —— 页面收到的是空东西，
     *  连 onerror 都不触发。而 Activity 手上这份临时读权限是有效的（能开相册、
     *  能拿到 Uri 就说明了）。所以在这里一次做完，交给页面一个 data: URL，
     *  页面对它跟对浏览器里挑完的 File 完全一样。
     *
     *  规格跟网页里的 compress() 对齐：长边 1280、JPEG 质量 0.82。
     */
    private void deliverFromJava(final Uri u) {
        new Thread(new Runnable() {
            public void run() {
                String b64;
                try {
                    /* 先只读尺寸，避免一亿像素的图直接把内存打爆 */
                    BitmapFactory.Options probe = new BitmapFactory.Options();
                    probe.inJustDecodeBounds = true;
                    java.io.InputStream is0 = getContentResolver().openInputStream(u);
                    if (is0 == null) { fail("打不开这个 Uri"); return; }
                    BitmapFactory.decodeStream(is0, null, probe);
                    is0.close();
                    if (probe.outWidth <= 0 || probe.outHeight <= 0) {
                        fail("解不出尺寸（可能不是图片）");
                        return;
                    }

                    /* 按 2 的幂采样，先砍到接近 1280 */
                    int mx = 1280, sample = 1;
                    while (probe.outWidth / (sample * 2) >= mx
                        || probe.outHeight / (sample * 2) >= mx) {
                        sample *= 2;
                    }
                    BitmapFactory.Options opt = new BitmapFactory.Options();
                    opt.inSampleSize = sample;
                    java.io.InputStream is1 = getContentResolver().openInputStream(u);
                    if (is1 == null) { fail("第二次也打不开"); return; }
                    Bitmap bmp = BitmapFactory.decodeStream(is1, null, opt);
                    is1.close();
                    if (bmp == null) { fail("解码失败"); return; }

                    /* 再精确缩到长边 1280，尽量少损画质 */
                    int w = bmp.getWidth(), h = bmp.getHeight();
                    float sc = Math.min((float) mx / w, (float) mx / h);
                    if (sc < 1f) {
                        Bitmap small = Bitmap.createScaledBitmap(bmp,
                                Math.max(1, (int) (w * sc)),
                                Math.max(1, (int) (h * sc)), true);
                        if (small != bmp) bmp.recycle();
                        bmp = small;
                    }

                    /* ★ 顺序要紧：先压进 ByteArrayOutputStream，再 recycle */
                    java.io.ByteArrayOutputStream bo = new java.io.ByteArrayOutputStream();
                    bmp.compress(Bitmap.CompressFormat.JPEG, 82, bo);
                    int ow = bmp.getWidth(), oh = bmp.getHeight();
                    bmp.recycle();
                    byte[] raw = bo.toByteArray();
                    bo.close();
                    b64 = Base64.encodeToString(raw, Base64.NO_WRAP);
                    final String note = ow + "x" + oh + " " + (raw.length / 1024) + "KB";
                    final String payload = b64;
                    web.post(new Runnable() {
                        public void run() {
                            web.evaluateJavascript(
                                "window.__pickArrived && window.__pickArrived('"
                                + payload + "','image/jpeg','照片.jpg','" + note + "')", null);
                        }
                    });
                } catch (SecurityException se) {
                    fail("没有读权限");
                } catch (OutOfMemoryError oe) {
                    fail("图太大，内存不够");
                } catch (Exception e) {
                    fail(e.getClass().getSimpleName() + ": " + e.getMessage());
                }
            }

            private void fail(String why) {
                final String w = (why == null ? "未知" : why)
                        .replace("'", "").replace("\n", " ").replace("\r", " ");
                web.post(new Runnable() {
                    public void run() {
                        web.evaluateJavascript(
                            "window.__pickFailed && window.__pickFailed('" + w + "')", null);
                    }
                });
            }
        }).start();
    }

    /** 把一句诊断话弹到页面上。debug 用：文件选择这条路在 WebView 里全是静默失败，
     *  不报出来根本不知道卡在 Java 还是 JS。
     *  ★ 这个帮手必须放在 onActivityResult 的 @Override 之前，否则会抢走那个注解。 */
    private void say(final String m){
        try {
            final String safe = m.replace("'", "").replace("\n", " ");
            web.post(new Runnable(){
                public void run(){
                    web.evaluateJavascript(
                        "window.toast && window.toast('' + '" + safe + "')", null);
                }
            });
        } catch (Exception ignored) { }
    }

    @Override
    protected void onActivityResult(int code, int result, Intent data) {
        if (code == REQ_FILE && filePick != null) {
            Uri[] uris = WebChromeClient.FileChooserParams.parseResult(result, data);

            /* ★ 诊断：resultCode / data 到底是什么样。
               上一版只说「没拿到 Uri」，根本不知道是用户取消、data 为 null、
               还是 data 里明明有值但 parseResult 不认（很可能就是最后这种）。 */
            StringBuilder dbg = new StringBuilder();
            dbg.append("result=").append(result);
            dbg.append(" data=").append(data == null ? "null" : "有");
            if (data != null) {
                Uri d0 = data.getData();
                dbg.append(" get=").append(d0 == null ? "null" : d0.getScheme());
                int cc = data.getClipData() == null ? 0 : data.getClipData().getItemCount();
                dbg.append(" clip=").append(cc);
                String tp = data.getType();
                dbg.append(" type=").append(tp == null ? "-" : tp);
            }
            final StringBuilder report = new StringBuilder();
            report.append("解析: ").append(dbg);

            /* ★ 自己抓一遍：不依赖 parseResult 的判定。
               有些 ROM 的相册返回 RESULT_CANCELED 却带着 data，
               有些把 Uri 放在 clipData 里单条，parseResult 都会漏。 */
            if (uris == null || uris.length == 0 || uris[0] == null) {
                java.util.ArrayList<Uri> got = new java.util.ArrayList<Uri>();
                if (data != null) {
                    Uri d1 = data.getData();
                    if (d1 != null) got.add(d1);
                    if (data.getClipData() != null) {
                        int cc = data.getClipData().getItemCount();
                        for (int i = 0; i < cc; i++) {
                            Uri ci = data.getClipData().getItemAt(i).getUri();
                            if (ci != null && !got.contains(ci)) got.add(ci);
                        }
                    }
                    if (got.isEmpty()) {
                        String ds = data.getDataString();
                        if (ds != null && ds.length() > 0) {
                            try { got.add(Uri.parse(ds)); } catch (Exception ignored) { }
                        }
                    }
                }
                if (!got.isEmpty()) {
                    uris = got.toArray(new Uri[0]);
                    report.append(" → 自己抓到 ").append(uris.length);
                } else {
                    report.append(" → data 里真没有 Uri");
                }
            }
            if (uris != null && uris.length > 0 && uris[0] != null) {
                say(report + " → 读 " + uris.length + " 张");
                /* ★ 多选：以前只 deliverFromJava(uris[0])，后面几张全丢。
                   deliverFromJava 内部是新线程，循环起多个互不阻塞；
                   每张读完各自调一次 __pickArrived，页面依次 staged.push。 */
                for (int i = 0; i < uris.length; i++) {
                    if (uris[i] == null) continue;
                    deliverFromJava(uris[i]);
                }
            } else {
                say(report + " → 最终为空");
            }
            /* WebView 的回调必须收尾，否则下次选图它不会再来问 */
            try { filePick.onReceiveValue(null); } catch (Exception ignored) { }
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