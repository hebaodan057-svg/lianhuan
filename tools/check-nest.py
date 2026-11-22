# -*- coding: utf-8 -*-
"""栈式检查 div 嵌套：深度不能变负，最后必须归零。"""
import io
import re

h = io.open('core/web/index.html', encoding='utf-8').read()
body = re.sub(r'<script[\s\S]*?</script>', '', h)
body = re.sub(r'<style[\s\S]*?</style>', '', body)
body = re.sub(r'<!--[\s\S]*?-->', '', body)

depth = 0
bad = []
for m in re.finditer(r'<div\b[^>]*?(/?)>|</div>', body):
    tag = m.group(0)
    if tag == '</div>':
        depth -= 1
        if depth < 0:
            line = body[:m.start()].count('\n') + 1
            bad.append('第 %d 行附近多了一个 </div>' % line)
            depth = 0
    elif m.group(1) != '/':
        depth += 1

print('结束时深度:', depth, '（应为 0）')
for b in bad[:5]:
    print('  ✗', b)
if depth != 0:
    print('  ✗ 有 %d 个 div 没闭合' % depth)

# 再看美化页那一段自己的结构
i = h.index('<div class="sub" id="beautypage">')
j = h.index('<div class="sub" id="histpage">')
seg = h[i:j]
seg_body = re.sub(r'<!--[\s\S]*?-->', '', seg)
d2 = 0
for m in re.finditer(r'<div\b[^>]*?(/?)>|</div>', seg_body):
    if m.group(0) == '</div>':
        d2 -= 1
    elif m.group(1) != '/':
        d2 += 1
print('美化页这一段自己的深度:', d2, '（应为 0）')
print('美化页里的 swrow 数:', seg.count('class="swrow"'))
