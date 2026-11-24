"""视觉模型看图：四层链路每一层都要在。

背景：我们仓库原来这四层**一层都没有**，所以配了视觉模型也看不见图——
模型只收到一段文字「先用 Read 工具看看 /path/x.jpg」，而 Read 是文本工具，
永远不会把像素交给视觉模型。

链路（缺任何一层都看不见）：
  ① 前端压缩        compress() 1280px / JPEG 0.82      （本来就有）
  ② 前端把图发过去   pushStaged 留 dataURL + send 带 images
  ③ 后端收图        /chat 读 body.images，空消息也放行
  ④ 引擎拼格式      openai_compat 把 content 换成 [text, image_url]

这几条测试就是钉住 ②③④ 三层，谁再删掉会立刻红。
"""
import io
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class TestVisionPipeline(unittest.TestCase):
    def test_turn_has_images_field(self):
        """Turn 必须带 images 字段，且默认空列表（老调用零风险）。"""
        t = read("core/engines/base.py")
        self.assertRegex(t, r"images:\s*list\[str\]\s*=\s*field\(default_factory=list\)",
                         "Turn 缺 images 字段：引擎拿不到图")

    def test_chat_endpoint_accepts_images(self):
        """/chat 要读 body.images，且「只发图不说话」要放行。"""
        t = read("core/server.py")
        self.assertIn('body.get("images")', t, "/chat 没读 body.images")
        self.assertIn('startswith("data:")', t,
                      "只该收 data: 开头的内联图（URL 模型读不到）")
        # 空消息 + 有图 → 不能 400
        self.assertRegex(t, r"if not msg and not images:",
                         "空消息判断没考虑 images —— 只发图会被 400 顶回来")

    def test_turn_construction_passes_images(self):
        """构造 Turn 时必须把 images 带进去，否则引擎那层永远是空的。"""
        t = read("core/server.py")
        self.assertRegex(t, r"EngineTurn\([^)]*images=images",
                         "构造 Turn 时没传 images —— 图到这一层就断了")

    def test_openai_compat_builds_image_url(self):
        """引擎层要把 content 从字符串换成 [text, image_url] 数组。"""
        t = read("core/engines/openai_compat.py")
        self.assertIn('"type": "image_url"', t, "没拼 image_url，视觉模型看不见")
        self.assertIn('"type": "text"', t, "没拼 text 块")
        # 没图必须走老路（新功能不许动老逻辑）
        self.assertRegex(t, r"else:\s*\n\s*msgs\.append\(\{\"role\": \"user\", \"content\": turn\.message\}\)",
                         "没图时的 else 分支被动了 —— 老逻辑必须一字不改")

    def test_frontend_sends_dataurl_and_images(self):
        """前端：pushStaged 要留 dataURL，CHAT.send 要带 images。"""
        h = read("core/web/index.html")
        self.assertIn("dataURL: s.dataURL", h,
                      "pushStaged 没保留 dataURL —— 图的数据在上传后丢了")
        self.assertRegex(h, r"images:\s*imgs\.map\(",
                         "CHAT.send 没带 images")
        self.assertIn("const hasImg = !!(", h,
                      "send 里没放行「有图没字」")

    def test_anthropic_has_no_image_support_documented(self):
        """Anthropic 引擎没实现图片支持 —— 这条不是要求实现，是**提醒**。

        用 Claude 系模型时看不见图，是已知限制（格式跟 OpenAI 完全不同）。
        哪天要加，照 openai_compat 加对称分支，media_type 必须单独切出来。
        这条测试钉住「别以为它支持了」。
        """
        t = read("core/engines/anthropic_api.py")
        self.assertNotIn("image_url", t,
                         "anthropic_api.py 里出现了 image_url —— "
                         "Anthropic 的格式不是这个，要么改格式要么删掉")


if __name__ == "__main__":
    unittest.main()
