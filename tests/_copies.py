# -*- coding: utf-8 -*-
"""两份前端的比对规则（唯一的真相源）。

app/index.html 与 core/web/index.html 只允许差一处：
    **安卓那份没有 viewport-fit=cover**

原因（Capacitor #8622，同机型小米 MIUI / WebView 152 实测）：
  viewport-fit=cover 会让 Chromium 进入 passthrough 缩放模式，
  那条路上 View.setPadding() 和改写 insets **全部无效**，
  而且它缩的量跟 ime inset 报的值对不上（差额正好是导航栏高度）。
  结果就是：输入框被键盘挡住一点点、底栏跟着抬半截。

  去掉 cover → 退出 passthrough，缩放变得可控。
  iOS 的 WKWebView 没有这个 bug，而且需要 cover 处理刘海，所以 web 那份保留。

★ 任何检查「两份一致」的地方都必须用这里，别各写一遍 replace。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

ANDROID_ONLY_DIFF = "viewport-fit=cover, "


def web_copy() -> str:
    """core/web/index.html 的内容（iOS / PWA 用，带 cover）。"""
    return (ROOT / "core" / "web" / "index.html").read_text(encoding="utf-8")


def android_copy() -> str:
    """app/index.html 的内容（安卓构建用，不带 cover）。"""
    return (ROOT / "app" / "index.html").read_text(encoding="utf-8")


def web_without_cover() -> str:
    """web 那份把 cover 剥掉 —— 这才是安卓那份应该长成的样子。"""
    return web_copy().replace(ANDROID_ONLY_DIFF, "", 1)


def assert_copies_agree(testcase) -> None:
    """安卓那份必须等于「web 那份去掉 viewport-fit=cover」。

    ★ 断言的**方向**很重要：
        对：android == web.replace(cover, "")
              因为安卓本来就没有 cover，只有把 web 的剥掉才能对上。
        错：web == android.replace(cover, "")
              安卓没 cover，再 replace 一次等于没动，永远对不上。
    """
    a = android_copy()
    testcase.assertNotIn(
        "viewport-fit=cover", a,
        "安卓那份必须去掉 viewport-fit=cover，否则键盘处理会失效")
    testcase.assertEqual(
        web_without_cover(), a,
        "两份前端除了 viewport-fit=cover 之外还漂开了 —— "
        "cp core/web/index.html app/index.html 然后删掉 viewport-fit=cover, ")
