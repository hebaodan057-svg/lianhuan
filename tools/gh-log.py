#!/usr/bin/env python3
"""把某个 job 的完整日志存下来（手机上看不完的，落盘再翻）。

用法：
  python3 tools/gh-log.py JOB_ID [输出路径]
JOB_ID 从 tools/gh-fail.py 打印的 `--- 日志 ---` 或者 gh-watch 的 job 列表里拿。
不传输出路径就存到 /tmp/gh-job-<id>.log，然后告诉你文件多大、末尾几行。
"""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request

OWNER = "hebaodan057-svg"
REPO = "lianhuan"
TOKEN_FILE = os.path.expanduser("~/.lianhuan/token")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def main(job_id, out=None):
    out = out or f"/tmp/gh-job-{job_id}.log"
    tok = open(TOKEN_FILE).read().strip()
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/jobs/{job_id}/logs"
    req = urllib.request.Request(url)
    req.add_header("Authorization", "token " + tok)
    req.add_header("Accept", "application/vnd.github+json")
    loc = None
    try:
        urllib.request.build_opener(NoRedirect).open(req, timeout=90)
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location")
    if not loc:
        print("✗ 拿不到日志地址")
        return 1
    try:
        with urllib.request.urlopen(loc, timeout=300) as r:
            blob = r.read()
    except Exception as e:
        print("✗ 下载日志失败：", e)
        return 1
    open(out, "wb").write(blob)
    text = blob.decode("utf-8", "ignore")
    lines = text.splitlines()
    print(f"✓ 存到 {out}（{len(blob) / 1024:.0f} KB，{len(lines)} 行）")
    print("--- 最后 15 行 ---")
    print("\n".join(lines[-15:]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))