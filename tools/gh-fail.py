#!/usr/bin/env python3
"""拿某次运行的失败原因：优先读 check-run 的 annotations（里面有 ::error:: 原文）。

GitHub 的 job 日志下载地址是 302 到 blob 存储的签名链接，带着 token 去请求
那个链接会被 403。所以这里手动处理一次重定向，到目标时把 Authorization 去掉。

用法：
  python3 tools/gh-fail.py RUN_ID
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

OWNER = "hebaodan057-svg"
REPO = "lianhuan"
TOKEN_FILE = os.path.expanduser("~/.lianhuan/token")


def tok():
    return open(TOKEN_FILE).read().strip()


def get(path, auth=True, redirect=True):
    url = path if path.startswith("http") else "https://api.github.com" + path
    req = urllib.request.Request(url)
    if auth:
        req.add_header("Authorization", "token " + tok())
    req.add_header("Accept", "application/vnd.github+json")
    opener = urllib.request.build_opener(
        urllib.request.HTTPRedirectHandler if redirect else NoRedirect)
    try:
        with opener.open(req, timeout=90) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw.decode() or "{}")
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode() or "{}")
        except Exception:
            return e.code, raw


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main(run_id):
    st, jobs = get(f"/repos/{OWNER}/{REPO}/actions/runs/{run_id}/jobs")
    if st != 200:
        print("取 jobs 失败 HTTP", st, jobs)
        return 1
    for j in jobs.get("jobs", []):
        print(f"== job {j['name']} = {j['status']} / {j.get('conclusion')}")
        bad = [s for s in j.get("steps", []) if s.get("conclusion") == "failure"]
        for s in bad:
            print(f"   失败步骤：{s['name']}")
        st2, ann = get(f"/repos/{OWNER}/{REPO}/check-runs/{j['id']}/annotations")
        if st2 == 200 and ann:
            print("   --- annotations ---")
            for a in ann:
                path = a.get("path") or ""
                print(f"   [{a.get('annotation_level')}] {path}:{a.get('start_line')}")
                print(f"   {a.get('message')}")
        else:
            print("   annotations HTTP", st2, "（空就先看日志）")
        # 日志：先拿 302 上的 Location，再去掉 token 请求正文
        loc = None
        req = urllib.request.Request(
            f"https://api.github.com/repos/{OWNER}/{REPO}/actions/jobs/{j['id']}/logs")
        req.add_header("Authorization", "token " + tok())
        req.add_header("Accept", "application/vnd.github+json")
        try:
            urllib.request.build_opener(NoRedirect).open(req, timeout=90)
        except urllib.error.HTTPError as e:
            loc = e.headers.get("Location")
        except Exception as e:
            print("   取日志地址出错：", e)
        if loc:
            print("   --- 日志末尾 ---")
            st4, blob = get(loc, auth=False)
            if isinstance(blob, bytes):
                lines = [l for l in blob.decode("utf-8", "ignore").splitlines() if l.strip()]
                print("\n".join(lines[-90:]))
            else:
                print("   日志内容拿不到 HTTP", st4)
        else:
            print("   拿不到日志重定向")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))