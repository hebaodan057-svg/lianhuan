#!/usr/bin/env python3
"""桌宠删完之后的收尾：清残留的 12 处。幂等。

    python3 tools/strip-pet-leftovers.py --check
    python3 tools/strip-pet-leftovers.py

★ 分两类，别混：
   · CODE  —— 真会被执行的（选择器、window.applyCrabWhere 调用）。不清会报错。
   · NOTE  —— 只是注释里提到「桌宠」。不清不影响运行，但留着会误导下一个读代码的人。
"""
from __future__ import annotations

import sys
from pathlib import Path

P = Path("core/web/index.html")

#: (说明, 原文, 替换成)
FIXES = [
    # ── 真代码：这一条不清，点设置里那几项就整个失效 ──────────────
    ("选择器里还挂着 [data-sub=\"桌宠\"]",
     "'[data-sub=\"名字 / 头像\"], [data-sub=\"桌宠\"], [data-sub=\"通知与频率\"], [data-sub=\"音色调校\"], '",
     "'[data-sub=\"名字 / 头像\"], [data-sub=\"通知与频率\"], [data-sub=\"音色调校\"], '"),

    # ── 真代码：桌宠没了，这行是个永远 false 的守卫 ────────────────
    ("通话收起时还调 applyCrabWhere",
     "  function shrink(){\n"
     "    host.classList.remove('on');          /* 只是推出去，iframe 照旧活着 */\n"
     "    if (window.applyCrabWhere) window.applyCrabWhere();\n",
     "  function shrink(){\n"
     "    host.classList.remove('on');          /* 只是推出去，iframe 照旧活着 */\n"),

    # ── 注释：指向一个已经不存在的东西 ───────────────────────────
    ("调参页的注释还列着桌宠",
     "  <!-- 设置里那几个调参数的，共用这一页：名字头像 / 桌宠 / 通知与频率 / 音色调校。",
     "  <!-- 设置里那几个调参数的，共用这一页：名字头像 / 通知与频率 / 音色调校。"),

    ("PREF 那段注释举例举的是桌宠",
     "   0805 验收时逮到的一整类毛病：个签在主页不生效、头像改不了、桌宠大小和漂浮物都不生效——",
     "   0805 验收时逮到的一整类毛病：个签在主页不生效、头像改不了、漂浮物大小也不生效——"),

    ("记忆星图注释里提桌宠剪影",
     "     这样桌宠和枫叶这两个剪影本身就带着原项目的身份，而不是一团中性的灰。",
     "     这样剪影本身就带着原项目的身份，而不是一团中性的灰。"),

    ("调参那四样：现在只剩三样了",
     "   名字头像 / 桌宠（黏人度）/ 通知与频率 / 音色调校，共用一个页面。",
     "   名字头像 / 通知与频率 / 音色调校，共用一个页面。"),

    ("「频率全收录」那段注释",
     "    /* ★ 0805 拍的板：**频率全收录到一页**，桌宠页只管桌宠自己。\n"
     "         0805 报的两条：想念骰子没有旋钮、桌宠页里放的却是黏人度——\n"
     "         黏人度管的是多久主动凑过去一次，那是频率，跟桌宠长多大没关系，摆错地方了。 */\n",
     "    /* ★ 0805 拍的板：**频率全收录到一页**。\n"
     "         0805 报的：想念骰子没有旋钮，而要频率的旋钮却被摆到了别的地方去。 */\n"),

    ("通话层那段留下的空注释",
     "    /* 通话那一层是 64，桌宠得抬到它上面 —— 桌宠删了，这条不用了 */\n",
     ""),

    ("「桌宠跟着在干嘛演」那整段说明（代码已经删了）",
     "  /* ══ 桌宠跟着「他此刻在干嘛」演（0810）══\n"
     "     0810 定的：桌宠要跟着当下这件事演（在想／打字／搜索／用工具），\n"
     "     不能只跟长期心情走——那样它常年只演开心。\n"
     "\n"
     "     ★ 单独订一份，不去动上面那个 switch —— 那条链路是聊天的命，\n"
     "       加装饰不该冒把它弄坏的风险。\n"
     "     ★ 三态各配一只姿势（映射在桌宠那段的 ACT_POSE 里）：\n"
     "         think 在想（送出去了／到他那了／翻记忆）→ idle-bubble 冒泡泡\n"
     "         tool  动手翻东西                        → idle-look   张望着找\n"
     "         talk  在说（想好了在写／正在吐字）      → working-typing 打字\n"
     "       说完（end / stop）交回 null，退回原来那套：长期心情 → 用户挑的那只。 */\n",
     ""),

    ("boot 那段注释还点着桌宠",
     "  /* 开页面就读一次：偏好（皮肤/漂浮物/桌宠/风…）和身份一起。",
     "  /* 开页面就读一次：偏好（皮肤/漂浮物/风…）和身份一起。"),
]


def main() -> None:
    check = "--check" in sys.argv
    s = P.read_text(encoding="utf-8")
    before = len(s)
    hit = 0

    for name, old, new in FIXES:
        if old in s:
            s = s.replace(old, new, 1)
            hit += 1
            print(f"  ✓  {name}")
        else:
            print(f"  ·  已干净  {name}")

    if check:
        left = [k for k in ("crab", "桌宠", "CRAB", "CRAB_POSES", "applyCrab",
                            "ACT_POSE", "POSE_BY_MOOD") if k in s]
        print(f"\n（dry-run，命中 {hit} 处）")
        print("残留：", left or "干净")
        return

    if s == P.read_text(encoding="utf-8"):
        print("\n本来就干净，什么都没改。")
        return

    P.write_text(s, encoding="utf-8")
    print(f"\n改了 {hit} 处：{before} → {len(s)} 字节（少了 {before - len(s)}）")


if __name__ == "__main__":
    main()