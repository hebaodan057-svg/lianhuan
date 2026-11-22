#!/usr/bin/env python3
"""扫 Java 源码里那些「不像人写的」痕迹，防再出现 ""nonce"" 这种引号加倍。

背景：改 Java 时如果经过 shell/Python 的转义层，引号很容易变成 ""，
而这类错误只有到了 CI 编译阶段才会炸（本地只有 JRE，没有 javac）。

用法：python3 tools/lint-java-quotes.py
"""
import os
import re
import sys

SUSPECTS = [
    # 真正要抓的形态：""word"" —— 引号被转义层吞了一层
    (re.compile(r'""\w'), '引号加倍在词前（如 ""nonce""）'),
    (re.compile(r'\w""'), '引号加倍在词后（如 ""nonce""）'),
]


def main(root="."):
    bad = 0
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in
                       ('.git', '.venv', 'build', 'node_modules', '__pycache__', 'data')]
        for fn in filenames:
            if not fn.endswith('.java'):
                continue
            p = os.path.join(dirpath, fn)
            n += 1
            for i, line in enumerate(open(p, encoding='utf-8', errors='ignore'), 1):
                for pat, why in SUSPECTS:
                    if pat.search(line):
                        print(f'✗ {p}:{i}  {why}\n    {line.strip()}')
                        bad += 1
                        break
    print(f'\n扫了 {n} 个 .java 文件，可疑 {bad} 处')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else '.'))