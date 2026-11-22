#!/usr/bin/env python3
"""删掉桌宠（crab）。幂等，提上游新代码后再跑一次就行。

跑法：
    python3 tools/strip-pet.py --check    # 只看还剩什么，不动手
    python3 tools/strip-pet.py            # 真删

★ 为什么是锚点不是行号：index.html 一万七千行，行号隔三差五就飘。
★ 每一处都先断言锚点存在，找不到就停手 —— 宁可什么都没改，
  也不能切歪一刀把别的功能一起带走。
"""
from __future__ import annotations

import sys
from pathlib import Path

P = Path("core/web/index.html")

#: (说明, 起始锚点, 结束锚点) —— 删 [起始, 结束) 这一段
BLOCKS = [
    # ── CSS ──────────────────────────────────────────────
    ("CSS .crab 本体",
     ".crab{\n  position:absolute;right:14px;bottom:calc(202px",
     "\n/* ── 底栏 ── */"),

    ("CSS .posegrid / .pose 十二格",
     "/* 桌宠的十二个动作，挑一个当常态。每张 SVG 自己会动，所以这一格就是活的预览。 */",
     ".tuner .fldlb{display:block;font-size:12px;color:var(--sub);margin:12px 0 0}"),

    # ── HTML ─────────────────────────────────────────────
    ("HTML 桌宠那个 div",
     "  <!-- 桌宠的位置（素材不在这儿，见 core/web/pet/README.md）",
     "  <!-- 底栏 -->"),

    ("HTML 设置里的「桌宠」入口行",
     '<button class="setrow" data-sub="桌宠">',
     '          <div class="swrow" style="border-bottom:0">'),

    ("HTML 设置里的「他多大只」滑杆行",
     '          <div class="swrow" style="border-bottom:0">\n            <div style="display:flex;align-items:center;gap:12px">\n              <div class="ic" style="margin:0"><svg class="i" viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0"/>',
     '        </div>\n      </div>\n\n      <div class="setgroup">'),

    # ── JS：拖动 / 跳跃 ───────────────────────────────────
    ("JS 桌宠拖动与点击跳",
     "  /* 桌宠会跳 */",
     # ★ 结尾锚点别带 " */"：原文那行是「……三档吸附 ──」收尾，
     #   "*/" 在下一行末尾。带上就永远匹配不到（第一次 dry-run 就是这么停的）。
     "  /* ── 思考链 sheet：跟手拖，三档吸附 ──\n"),

    # ── JS：大小 / 姿态 / 心情 / 动作 ──────────────────────
    ("JS 桌宠大小·十二动作·心情联动·通话联动",
     "  /* 桌宠：多大只 ＋ 演哪一出。",
     "  /* ══ 那颗星 · 逐帧（0820）══"),

    # ── JS：设置页那个「桌宠」页 ───────────────────────────
    ("JS 设置页 › 桌宠 渲染器",
     "    '桌宠': async function(){",
     "    /* 0807：把 0–100 翻译成「一天最多几句」"),

    # ── JS：十二个动作的清单 ───────────────────────────────
    ("JS CRAB_POSES 清单",
     "  /* 桌宠的十二个动作（`pet/*.svg`）。★ 仓库里**没有**素材，自己放进去就会出现。",
     "  /* λ 换成人话：多久没说话，我想你的机会到一半。"),
]

#: 零散的单行 / 小段（整段替换成空）
BITS = [
    # 切主 tab 时顺手让桌宠跟着换页 —— 这四行没了，下面的 inChat 判断照样用 inChat
    ("    /* ★ 0820 要的：桌宠不止在聊天页出现，翻到哪一页（打电话也算）都看得见。\n"
     "       —— 设置里那颗开关开着就全家都在，关着还是只在聊天页。 */\n"
     "    window.__inChat = inChat;\n"
     "    if (window.applyCrabWhere) window.applyCrabWhere();\n", ""),

    # 主页取到心情之后喂给桌宠
    ("    /* 桌上那只桌宠也吃这一份（0806）—— 它演的就该是我此刻的样子，不用另发一次请求 */\n"
     "    if (window.crabMood) window.crabMood(m);\n", ""),

    # 通话展开 / 收起 / 结束
    ("    /* 打电话时桌宠也换一出（戴耳机晃那几只），顺手把它抬到通话层上面 */\n"
     "    if (window.crabAct) window.crabAct('call');\n"
     "    if (window.applyCrabWhere) window.applyCrabWhere();\n",
     "    /* 通话那一层是 64，桌宠得抬到它上面 —— 桌宠删了，这条不用了 */\n"),

    ("    if (window.crabAct) window.crabAct(null);\n"
     "    if (window.applyCrabWhere) setTimeout(window.applyCrabWhere, 60);\n", ""),

    # 聊天事件 → 桌宠换姿势那一整段
    ("  CHAT.on(function(type, d){\n"
     "    if (!window.crabAct) return;\n"
     "    switch (type){\n"
     "      case 'sent': case 'sending': case 'recv': case 'stage': case 'resume':\n"
     "        window.crabAct('think'); break;\n"
     "      case 'tool':\n"
     "        /* d.done 是工具跑完的那一声 —— 收工了就回到「在想」，别一直张望 */\n"
     "        window.crabAct(d && d.done ? 'think' : 'tool'); break;\n"
     "      case 'os': case 'say':\n"
     "        window.crabAct('talk'); break;\n"
     "      case 'end': case 'stop': case 'room':\n"
     "        window.crabAct(null); break;\n"
     "    }\n"
     "  });\n\n", ""),

    # 首页「玩具厅」那张卡片的副标题写着「桌宠在里头」
    (">桌宠在里头<", ">小玩意在里头<"),
]


def main() -> None:
    check = "--check" in sys.argv
    s = P.read_text(encoding="utf-8")
    before_len = len(s)

    for name, head, tail in BLOCKS:
        i = s.find(head)
        if i < 0:
            print(f"  ·  没有   {name}（已经不在）")
            continue
        j = s.find(tail, i + len(head))
        if j < 0:
            raise SystemExit(f"  ✗ 找到头找不到尾：{name}\n    不敢下刀，先人工看一眼")
        n = s.count("\n", i, j)
        s = s[:i] + s[j:]
        print(f"  ✓  删了   {name}（{n} 行）")

    for old, new in BITS:
        if old in s:
            s = s.replace(old, new, 1)
            print(f"  ✓  改了   {old.strip().splitlines()[0][:46]}")
        else:
            print(f"  ·  没有   {old.strip().splitlines()[0][:46]}")

    if check:
        left = [k for k in ("id=\"crab\"", "applyCrab", "crabMood", "crabAct", "crabsize",
                            "crabval", "CRAB_POSES", "posegrid", "POSE_BY_MOOD",
                            "ACT_POSE", "crabEverywhere", "crabSize", "桌宠", "crab") if k in s]
        print("\n残留：", left or "干净")
        return

    if s == P.read_text(encoding="utf-8"):
        print("\n本来就干净，什么都没改。")
        return

    P.write_text(s, encoding="utf-8")
    print(f"\n{before_len} → {len(s)} 字节（少了 {before_len - len(s)}）")


if __name__ == "__main__":
    main()