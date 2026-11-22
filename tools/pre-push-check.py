#!/usr/bin/env python3
"""push 之前的最后一道自检：暂存区里不能有私钥、口令、token。

为什么单独写个文件跑：手机终端的 shell 会吃掉/改写长命令里的部分字符，
把敏感串直接写在命令行里既不安全也不可靠，所以拼起来再比。
"""
import os
import subprocess
import sys

NEEDLES = [
    "3mf" + "6uPl9",          # keystore 口令片段
    "zzz" + "_not_used",      # 隐私闸占位词
    "ghp" + "_4IL",           # GitHub token 片段
    "BEGIN " + "RSA PRIVATE",
    "BEGIN " + "PRIVATE KEY",
    "MII" + "EvQI",           # PKCS12 的典型开头
]


def main(root="."):
    os.chdir(root)
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, check=True).stdout.splitlines()
    print("=== 类型变更(T) / 重命名(R) ===")
    flagged = [l for l in out if l[:1] in ("T", "R")]
    print("\n".join("  " + l for l in flagged) if flagged else "  无")

    names = [l.split("\t", 1)[1] for l in out if l[:1] != "D" and "\t" in l]
    print(f"=== 扫暂存区 {len(names)} 个文件 ===")
    hits = {n: [] for n in NEEDLES}
    for f in names:
        if not os.path.isfile(f):
            continue
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for n in NEEDLES:
            if n in txt:
                hits[n].append(f"{f}×{txt.count(n)}")
    bad = 0
    for n, v in hits.items():
        label = n[:12] + "…" if len(n) > 12 else n
        if v:
            print(f"  ✗ {label:<16} {' , '.join(v)}")
            bad += 1
        else:
            print(f"  · {label:<16} 无")

    print("=== 最大的几个文件（防手滑带进二进制）===")
    sized = sorted(((os.path.getsize(f), f) for f in names if os.path.isfile(f)), reverse=True)[:5]
    for s, f in sized:
        print(f"  {s / 1024:9.1f} KB  {f}")

    print("=== 结论 ===")
    if bad:
        print("✗ 有命中，别 push，先清掉。")
        return 1
    print("✓ 暂存区干净：没有 keystore、口令、token 的痕迹。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
