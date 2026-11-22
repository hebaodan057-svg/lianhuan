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

    def test_viewport_asks_the_browser_to_resize_content(self):
        m = re.search(r'<meta name="viewport" content="([^"]+)"', self.h)
        self.assertIsNotNone(m)
        self.assertIn("interactive-widget=resizes-content", m.group(1))

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
    def test_both_copies_stay_identical(self):
        """app/index.html 是 core/web/index.html 的副本，CI 里 diff 钉着，这儿也钉一道。"""
        other = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(self.h, other, "两份前端漂开了")


if __name__ == "__main__":
    unittest.main()
