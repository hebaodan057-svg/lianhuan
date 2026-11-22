#!/usr/bin/env python3
"""桌宠删干净：create.py 里的问卷 + core/web/pet/ 那个空素材位。

    python3 tools/strip-pet-installer.py --check
    python3 tools/strip-pet-installer.py

★ 一件事先说清楚：`lianhuan.json` 里的 "pet" 这个键**保留**，值恒为 "none"。
  理由：core/server.py 装包时会读它（`for key in ("engine", "store", "pet", "blocks")`）。
  把键删掉，那份装配单就读不到，属于「删着删着把别的弄坏」。
  桌宠这个功能已经没了，所以它只能是 none —— 写死成常量，比留一个能选的东西诚实。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

CREATE = Path("create.py")
PET_DIR = Path("core/web/pet")

#: (说明, 原文, 替换成)
FIXES = [
    # ── ① 问卷里那道「桌宠？」题（连同它的选项表） ──────────────
    ("PETS 选项表",
     'PETS = [\n'
     '    ("none",  "不要桌宠", "默认。以后想加，设置里还有入口"),\n'
     '    ("crab",  "要只螃蟹", "★ 我们不发素材，只指路。装完 NEXT-STEPS.md 里会写去哪拿"),\n'
     '    ("mine",  "我自己画", "装完 NEXT-STEPS.md 里给你命名规则。GIF、SVG 随便传"),\n'
     ']\n\n',
     ''),

    ("提问那一行",
     '        pet    = ask_one("桌宠？", PETS)\n',
     ''),

    # ── ② --yes 那条路径上的四元组解包 ──────────────────────────
    ("--yes 的默认值",
     '        blocks, pet, engine, store = ["paper", "physics", "parts"], "none", "echo", "sqlite"',
     '        blocks, engine, store = ["paper", "physics", "parts"], "echo", "sqlite"'),

    # ── ③ 装配单里的 pet 键：保留，但写死 none ──────────────────
    ("装配单 json（键保留、值恒为 none）",
     '        {"blocks": blocks, "pet": pet, "engine": engine, "store": store}, ensure_ascii=False, indent=2),',
     '        # ★ "pet" 这个键留着：core/server.py 装包时要读它。桌宠功能已删，只能是 none。\n'
     '        {"blocks": blocks, "pet": "none", "engine": engine, "store": store}, ensure_ascii=False, indent=2),'),

    # ── ④ NEXT-STEPS.md 里那三段桌宠说明 ───────────────────────
    ("NEXT-STEPS 的三段桌宠说明",
     '    if pet == "crab":\n'
     '        todo += ["## 桌宠素材（你勾了「要只螃蟹」）\\n",\n'
     '                 "★ 我们**不分发素材**，只指路 —— 那个角色是别家公司的吉祥物，",\n'
     '                 "而它的粉丝项目是 AGPL-3.0，跟着开源分发会把你整个项目也传染成 AGPL。\\n",\n'
     '                 "要用就自己去拿：搜 `clawd-on-desk`（GitHub），把 GIF 放进 `core/web/pet/`，",\n'
     '                 "按状态名命名（`idle` / `happy` / `thinking` / `sleeping` …）。",\n'
     '                 "**自己玩没问题，别再往外分发。**\\n"]\n'
     '    if pet == "mine":\n'
     '        todo += ["## 桌宠素材（你勾了「我自己画」）\\n",\n'
     '                 "往 `core/web/pet/` 里丢图，按状态名命名：",\n'
     '                 "`idle.svg` / `happy.svg` / `thinking.svg` / `sleeping.svg`。",\n'
     '                 "SVG 自带 CSS 动画也行（会包在 `<img>` 里，样式不会污染页面）。GIF 也行。\\n"]\n'
     '    if pet == "none":\n'
     '        todo += ["## 桌宠\\n", "没装。以后想加，设置里还有入口。\\n"]\n',
     ''),
]


def main() -> None:
    check = "--check" in sys.argv
    s = CREATE.read_text(encoding="utf-8")
    before = len(s)
    hit = 0

    for name, old, new in FIXES:
        if old in s:
            s = s.replace(old, new, 1)
            hit += 1
            print(f"  ✓  {name}")
        else:
            print(f"  ·  已干净  {name}")

    # 合理性：改完不该还有 pet 变量被当值用
    left = [ln for ln in s.splitlines() if "pet" in ln.lower()]
    print("\ncreate.py 里剩下的 pet 字样：")
    for ln in left:
        print("    " + ln.strip()[:100])
    if not left:
        print("    （无）")

    if check:
        print(f"\n（dry-run，命中 {hit} 处）")
        print("core/web/pet 存在：", PET_DIR.exists())
        return

    CREATE.write_text(s, encoding="utf-8")
    print(f"\ncreate.py：{before} → {len(s)} 字节（少了 {before - len(s)}）")

    if PET_DIR.exists():
        shutil.rmtree(PET_DIR)
        print(f"core/web/pet/ 已删")
    else:
        print("core/web/pet/ 本来就不在")


if __name__ == "__main__":
    main()