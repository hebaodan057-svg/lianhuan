#!/usr/bin/env python3
"""删掉开屏枫叶水面（含设置里那两行）。

    python3 tools/strip-splash.py            # 改 core/web/index.html
    python3 tools/strip-splash.py --check    # 只看有没有残留，不动手

幂等：删过的再跑一遍什么也不做。提上游新代码后想重新抹掉，再跑一次就行。
为什么用锚点而不是行号：index.html 一万八千行，行号隔三差五就飘。
"""
import re
import sys

P = 'core/web/index.html'

# 区块 = (名字, 开锤前缀, 结尾锚点)。从结尾锚点往后找，取第一个匹配。
BLOCKS = [
    # ① CSS：整段开屏样式，从注释头到 prefers-reduced-motion 那块结束的 }
    ('CSS #splash 样式',
     '/* ══ 开屏 · 枫叶水面',
     '  #splash, #splash #sp-water, #splash .sp-vig{transition-duration:.2s}\n}\n'),
    # ② HTML：盖在 app 上那层布
    ('HTML #splash 节点',
     '<!-- ══ 开屏 ══',
     '<div class="sp-track" aria-hidden="true"><i class="sp-fill" id="sp-fill"></i></div>\n</div>'),
    # ③ 设置：画质三档 + 枫叶配色/密度/风 + 「现在看一眼」
    ('设置 › 开屏画质 / 枫叶',
     '<!-- ══ 开屏 · 枫叶水面（0810）══',
     '<button id="wpeek"'),
]

# ④ ⑤”：两段 <script>（开屏控制 / 设置面板）
SCRIPTS = [
    ('JS 开屏控制', '/* ══ 开屏控制（0810）══'),
    ('JS 设置面板', '/* ══ 设置 › 开屏水面（0810）══'),
]


def strip_block(s, head, tail):
    """删掉从 head 开头、到 tail 结尾（含）的一块。找不到就原样返回。"""
    i = s.find(head)
    if i < 0:
        return s, False
    j = s.find(tail, i)
    if j < 0:
        raise SystemExit(f'✗ 找到了头却找不到尾（{head[:30]}…），不敢下刀，先人工看一眼')
    return s[:i] + s[j + len(tail):], True


def strip_script(s, mark):
    """删掉包含 mark 的整个 <script>…</script>。"""
    i = s.find(mark)
    if i < 0:
        return s, False
    a = s.rfind('<script>', 0, i)
    b = s.find('</script>', i)
    if a < 0 or b < 0:
        raise SystemExit(f'✗ {mark[:24]}… 外面包不成一个 <script>，停手')
    b += len('</script>')
    while b < len(s) and s[b] in '\r\n':
        b += 1
    return s[:a] + s[b:], True


def main():
    check = '--check' in sys.argv
    s = open(P, encoding='utf-8').read()
    before = len(s)
    hits = []

    for name, head, tail in BLOCKS:
        s, done = strip_block(s, head, tail)
        hits.append((name, done))
    for name, mark in SCRIPTS:
        s, done = strip_script(s, mark)
        hits.append((name, done))

    for name, done in hits:
        print(('  删了' if done else '  没有') + '  ' + name)

    if check:
        left = [k for k in ('id="splash"', 'sp-water', 'wqpick', 'wppick', 'wdens',
                            'wwind', 'wpeek', 'maple-water', 'MapleWater', 'lh.water')
                if k in s]
        print('\n残留：', left or '干净')
        return

    if s == open(P, encoding='utf-8').read():
        print('\n本来就干净，什么都没改。')
        return

    open(P, 'w', encoding='utf-8').write(s)
    print(f'\n{before} → {len(s)} 字节（少了 {before - len(s)}）')
    print('重启服务就能看到：浏览器会自己拿新文件（/ 的响应带 no-cache）')


if __name__ == '__main__':
    main()
