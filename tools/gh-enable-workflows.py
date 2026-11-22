#!/usr/bin/env python3
"""把仓库的 Actions 打开、把 workflow 启用、手动触发一次 android-full。

为什么需要它：fork 过来的仓库，workflow 文件虽然是 active，但 push 未必会
真的跑起来（GitHub 对 fork 默认要"启用一次"）。这个脚本把这三步一次做完，
然后报告 runs 里到底出现了什么。

用法：
  python3 tools/gh-enable-workflows.py            # 开权限 + 启用 workflow + 触发 android-full
  python3 tools/gh-enable-workflows.py --dry      # 只看状态，不触发
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

OWNER = "hebaodan057-svg"
REPO = "lianhuan"
WF = "android-full.yml"
TOKEN_FILE = os.path.expanduser("~/.lianhuan/token")


def call(method, path, body=None):
    tok = open(TOKEN_FILE).read().strip()
    url = path if path.startswith("http") else "https://api.github.com" + path
    req = urllib.request.Request(
        url, method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Authorization", "token " + tok)
    req.add_header("Accept", "application/vnd.github+json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:300]}
    except urllib.error.URLError as e:
        return 0, {"error": str(e.reason)}


def status():
    print("== 现状 ==")
    st, d = call("GET", f"/repos/{OWNER}/{REPO}/actions/permissions")
    print("  Actions 开关：HTTP", st, "enabled =", d.get("enabled"))
    st, d = call("GET", f"/repos/{OWNER}/{REPO}/actions/workflows")
    for w in d.get("workflows", []):
        print(f"  workflow {w['name']:<12} state={w['state']}")
    st, d = call("GET", f"/repos/{OWNER}/{REPO}/actions/runs?per_page=5")
    print("  最近运行数 total_count =", d.get("total_count"))
    for r in d.get("workflow_runs", [])[:5]:
        print(f"    #{r['run_number']} {r['name']} {r['status']} {r['conclusion']}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry", action="store_true")
    a = p.parse_args()
    status()
    if a.dry:
        return 0

    print("\n== 打开 ==")
    print("  PUT actions/permissions:", call(
        "PUT", f"/repos/{OWNER}/{REPO}/actions/permissions", {"enabled": True}))
    print("  PUT workflow enable  :", call(
        "PUT", f"/repos/{OWNER}/{REPO}/actions/workflows/{WF}/enable"))

    print("\n== 触发 ==")
    st, d = call("POST", f"/repos/{OWNER}/{REPO}/actions/workflows/{WF}/dispatches",
                 {"ref": "main"})
    print("  dispatch HTTP", st, "" if st < 300 else d)

    for i in range(6):
        time.sleep(10)
        st, d = call("GET", f"/repos/{OWNER}/{REPO}/actions/runs?per_page=5")
        n = d.get("total_count")
        print(f"  +{(i + 1) * 10}s  total_count = {n}")
        if n:
            for r in d.get("workflow_runs", [])[:5]:
                print(f"    #{r['run_number']} {r['name']} {r['status']} {r['conclusion']} id={r['id']}")
            return 0
    print("\n✗ 还是没有运行。这基本只剩一种可能：账号层面被拦（新账号要验证，或 Actions 被限）。")
    return 1


if __name__ == "__main__":
    sys.exit(main())