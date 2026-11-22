#!/usr/bin/env python3
"""拆开 APK 看两件事：改动真的进去了吗，前端有没有还留着删掉的东西。

为什么要这一步：之前在 proot 里"看着改动生效"，其实是 APK 开着开发服的页面，
改动从来没进过包。所以打完包必须直接查包里的东西，不能只看日志绿了。

Chaquopy 把 Python 部分（连同 core/web 的静态文件）打进了
assets/chaquopy/app.imy —— 那本身又是个 zip，源码是 .pyc。所以要往里钻一层。

用法：python3 tools/verify-apk.py 路径/lianhuan-full-vX.apk
"""
from __future__ import annotations

import io
import re
import sys
import zipfile

# 已经删掉的东西，包里不该出现
GONE = ['id="splash"', 'data-sub="桌宠"', 'applyCrabWhere', 'crab', 'core/web/pet/']
# 必须还在的东西
ALIVE = ['api/android/hello', 'core/web/index.html']


def load_tree(apk):
    """返回 {名字: bytes} —— 把 APK 里 chaquopy 的那层嵌套 zip 也展开。"""
    files = {}
    z = zipfile.ZipFile(apk)
    for n in z.namelist():
        if n.endswith('/'):
            continue
        try:
            files[n] = z.read(n)
        except Exception:
            continue
    imy = 'assets/chaquopy/app.imy'
    if imy in files:
        try:
            inner = zipfile.ZipFile(io.BytesIO(files[imy]))
            for n in inner.namelist():
                if n.endswith('/'):
                    continue
                files['imy:' + n] = inner.read(n)
        except Exception as e:
            print(f'  ! 打不开 {imy}：{e}')
    return files


def main(path):
    files = load_tree(path)
    print(f'APK：{path}')
    print(f'展开后一共 {len(files)} 个文件')

    web = [n for n in files if n.endswith('index.html')]
    back = [n for n in files if n.endswith('android_boot.pyc') or n.endswith('server.pyc')]
    print('\n=== 包里的前端（静态文件原样打进去）===')
    for n in web:
        print(f'  {n}  {len(files[n]) / 1024:.0f} KB')
    print('=== 包里的后端（编译成 .pyc）===')
    for n in back:
        print(f'  {n}  {len(files[n]) / 1024:.0f} KB')

    bad = 0
    print('\n=== 该删掉的，包里不该有 ===')
    for needle in GONE:
        nb = needle.encode()
        hit = [n for n, b in files.items() if nb in b]
        if hit:
            print(f'  ✗ 「{needle}」还在：{", ".join(hit[:4])}')
            bad += 1
        else:
            print(f'  ✓ 「{needle}」不在')

    print('\n=== 该在的，包里必须有 ===')
    for needle in ALIVE:
        nb = needle.encode()
        hit = [n for n, b in files.items() if nb in b]
        if hit:
            print(f'  ✓ 「{needle}」在 {", ".join(hit[:3])}')
        else:
            print(f'  ✗ 「{needle}」找不到')
            bad += 1

    # 前端行数，跟工作区对一下就知道是不是同一份
    for n in web:
        txt = files[n].decode('utf-8', 'ignore')
        print(f'\n=== {n} ===')
        print(f'  行数 {len(txt.splitlines())}，大小 {len(txt) / 1024:.0f} KB')
        for k in ('splash', '桌宠', 'crab'):
            print(f'  含「{k}」：{"是" if k in txt else "否"}')

    print('\n=== 签名 ===')
    certs = [n for n in files if re.match(r'META-INF/.*\.(RSA|DSA|EC)$', n)]
    print('  v1 签名块：', ', '.join(certs) if certs else '无（纯 v2/v3 签名也算正常）')

    print('\n=== 结论 ===')
    if bad:
        print(f'✗ {bad} 项不对，这个包别装。')
        return 1
    print('✓ 该删的没了，该在的都在。')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))