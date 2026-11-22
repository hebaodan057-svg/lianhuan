"""软键盘：输入框和最后一条消息不许被键盘盖住。

★ 为什么要有这几条：这一份前端被四个壳共用（网页 PWA、iOS 加主屏、安卓壳、安卓完整体）。
  iOS 上键盘**不改**布局视口 —— 100dvh 一动不动，而输入条是贴着 .app 底边绝对定位的，
  于是整条被盖住。安卓的 adjustResize 只能覆盖其中一部分，靠它不够。
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def app_html() -> str:
    return (ROOT / "core" / "web" / "index.html").read_text(encoding="utf-8")


class TestSoftKeyboard(unittest.TestCase):
    def setUp(self):
        self.h = app_html()

    def test_viewport_lets_the_keyboard_overlay_instead_of_resizing(self):
        """viewport 必须让键盘「盖上去」，而不是把布局视口缩小。

        ★ 这条原来是 `interactive-widget=resizes-content`，那是另一种做法：
          键盘弹出时把布局视口缩小，整个应用跟着变矮 ——
          底栏和输入框**一起**被顶上去，而且跟 --kb 叠在一起，
          表现就是「底栏只抬了一半」。

          用户要的是「只顶输入条，底栏和背景留在原位（被键盘盖住）」，
          所以契约改成 overlays-content。改这两个值里的任何一个，
          这条测试会立刻红，提醒你别把病根又放回去。
        """
        m = re.search(r'<meta name="viewport" content="([^"]+)"', self.h)
        self.assertIsNotNone(m)
        self.assertIn("interactive-widget=overlays-content", m.group(1))
        self.assertNotIn("interactive-widget=resizes-content", m.group(1),
                         "resizes-content 会让底栏跟着键盘抬，别再放回来")

    def test_html_body_height_does_not_follow_the_viewport(self):
        """html/body 的高度不能是 100%。

        ★ 100% 参考视口高度。键盘一弹（或 WebView 被缩），它跟着变短，
          于是 .app 的底边提前收住 —— 表现就是「底栏和输入栏只抬了一半」，
          而 .app 上写 --vvh 也没用，因为父级已经把高度定死了。
          改成 var(--vvh, 100vh)：--vvh 由壳层给（不含键盘）。
        """
        m = re.search(r"html,body\{([^}]*)\}", self.h)
        self.assertIsNotNone(m, "找不到 html,body 的样式")
        block = m.group(1)
        self.assertIn("--vvh", block, "html/body 的高度要接 --vvh，否则会跟着键盘变矮")
        self.assertNotRegex(block, r"height:\s*100%\s*;",
                            "html/body 别再写 height:100%（它跟着视口变）")

    def test_app_height_is_guarded_by_vvh(self):
        """.app 的高度要有 --vvh 兜底，不能只有 100dvh。"""
        m = re.search(r"\.app\{([^}]*height:[^}]*)\}", self.h)
        self.assertIsNotNone(m)
        self.assertIn("--vvh", m.group(1),
                      ".app 的高度要接 --vvh（壳层推的不含键盘的真实高度）")

    def test_the_keyboard_only_lifts_the_composer(self):
        """键盘弹出时只把输入条顶上来，app 本身不缩短。

        ★ 这条原来是「.app 的高度必须扣掉 --kb」—— 那是另一种做法：整个应用缩短，
          底栏和输入框**一起**被顶上去。用户明确要求改成「只顶输入条，
          底栏和背景待在原地（让键盘盖住）」，所以契约跟着变了：
            · .app 的高度不再出现 --kb
            · 改由 .app.kb-open 下的输入条自己抬起来
        """
        # 1) app 的任何一条高度都不该再扣键盘
        heights = re.findall(r"height:\s*([^;]*dvh[^;]*)", self.h)
        self.assertGreaterEqual(len(heights), 1, "找不到 .app 的高度：" + str(heights))
        for hh in heights:
            self.assertNotIn("var(--kb", hh, "app 的高度不该再扣键盘了：" + hh)

        # 2) 输入条必须靠 --kb 抬到键盘上方
        m = re.search(r"\.app\.kb-open\s+\.composer\{[^}]*bottom:\s*calc\(\s*var\(--kb", self.h)
        self.assertIsNotNone(m, "键盘弹出时没有把输入条抬起来")

        # 3) 那条脚本还得在算 --kb，否则上面那条 CSS 是死的
        self.assertIn("--kb", self.h)
        self.assertIn("kb-open", self.h)

    def test_keyboard_inset_comes_from_visual_viewport(self):
        self.assertIn("visualViewport", self.h)
        self.assertIn("--kb", self.h)
        self.assertIn("kb-open", self.h)

    def test_zoom_is_not_mistaken_for_a_keyboard(self):
        """双指放大也会让 visualViewport 变矮 —— 那不是键盘，扣了就白掉一块。"""
        self.assertRegex(self.h, r"vv\.scale\s*>\s*1", "没有排掉缩放")

    @unittest.skipUnless((ROOT / "app" / "index.html").exists(),
                         "create.py 的产物不带 app/，这条只在源码仓库里跑")
    def test_both_copies_differ_only_by_viewport_fit(self):
        """两份前端只允许差一处：安卓那份没有 viewport-fit=cover。

        ★ 旧约定是「逐字节一致」。但安卓必须去掉 cover ——
          否则 Chromium 进入 passthrough 缩放模式，setPadding 和 insets
          全部失效，键盘处理无从下手（Capacitor #8622，同机型同 WebView）。
          iOS/PWA 那份需要 cover 处理刘海，且 WKWebView 没有这个 bug。
        """
        from _copies import assert_copies_agree
        assert_copies_agree(self)


if __name__ == "__main__":
    unittest.main()
