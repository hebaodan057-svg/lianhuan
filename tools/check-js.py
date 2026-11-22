#!/usr/bin/env python3
"""把 index.html 里每一段内联 <script> 抽出来，交给 node 验语法。

为什么需要：这个项目的前端是**一个 900KB 的 HTML**，CSS/DOM/JS 全在文件里，
写错一个引号整块脚本就不执行了，而浏览器只在控制台里报一句 —— 手机上看不见。
`tools/checkhtml.py` 只验标签配平，管不到 JS。

用法：
  python3 tools/check-js.py                # 检查 core/web/index.html
  python3 tools/check-js.py 某个文件.html
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.S | re.I)


def main(path="core/web/index.html"):
    html = open(path, encoding="utf-8").read()
    blocks = []
    for m in SCRIPT_RE.finditer(html):
        attrs, body = m.group(1), m.group(2)
        if "src=" in attrs:                       # 外链脚本不在这儿验
            continue
        if "application/json" in attrs or "importmap" in attrs:
            continue                              # 不是 JS
        line = html[:m.start()].count("\n") + 1
        blocks.append((line, body))

    if not blocks:
        print("没找到内联脚本")
        return 0

    bad = 0
    for idx, (line, body) in enumerate(blocks, 1):
        ok = False
        last = ""
        for suffix in (".js", ".mjs"):            # 先按普通脚本验，再按模块验
            with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False,
                                             encoding="utf-8") as f:
                f.write(body)
                tmp = f.name
            try:
                r = subprocess.run(["node", "--check", tmp],
                                   capture_output=True, text=True)
                if r.returncode == 0:
                    ok = True
                    break
                last = (r.stderr or "").strip().splitlines()
                last = last[0] if last else ""
            finally:
                os.unlink(tmp)
        tag = f"第 {idx} 段（HTML 第 {line} 行起，{len(body)} 字节）"
        if ok:
            print(f"✓ {tag}")
        else:
            print(f"✗ {tag}\n    {last}")
            bad += 1

    print(f"\n共 {len(blocks)} 段内联脚本，语法错误 {bad} 段")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "core/web/index.html"))