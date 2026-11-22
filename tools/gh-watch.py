#!/usr/bin/env python3
"""看 GitHub Actions 跑到哪了，并能把产物下载下来。

用法：
  python3 tools/gh-watch.py                    # 列最近几次运行
  python3 tools/gh-watch.py --wait             # 盯着跑，直到结束（默认只看 android-full）
  python3 tools/gh-watch.py --logs RUN_ID      # 某个运行失败时，把失败步骤的日志打出来
  python3 tools/gh-watch.py --dl RUN_ID        # 把这次运行的 APK 产物下到 ./download/

为什么要这个脚本：手机上没有 gh CLI，构建一次十几分钟，
盯构建得能"等它自己结束再返回"，不能靠不停手敲 curl。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

OWNER = "hebaodan057-svg"
REPO = "lianhuan"
TOKEN_FILE = os.path.expanduser("~/.lianhuan/token")


def token() -> str:
    t = os.environ.get("GH_TOKEN") or ""
    if not t and os.path.exists(TOKEN_FILE):
        t = open(TOKEN_FILE).read().strip()
    if not t:
        sys.exit(f"✗ 没有 token（{TOKEN_FILE}）")
    return t


def api(method: str, path: str, body: dict | None = None, raw: bool = False):
    url = path if path.startswith("http") else f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {token()}")
    req.add_header("Accept", "application/vnd.github+json")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            payload = r.read()
            if raw:
                return r.status, payload
            txt = payload.decode()
            return r.status, (json.loads(txt) if txt.strip() else {})
    except urllib.error.HTTPError as e:
        if raw:
            return e.code, e.read()
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except urllib.error.URLError as e:
        return 0, {"error": str(e.reason)}


def runs(limit=8):
    st, d = api("GET", f"/repos/{OWNER}/{REPO}/actions/runs?per_page={limit}")
    if st != 200:
        sys.exit(f"✗ 取运行列表失败 HTTP {st}：{d}")
    return d.get("workflow_runs", [])


ICON = {"success": "✓", "failure": "✗", "cancelled": "⊘", "skipped": "·"}


def show(rs):
    for r in rs:
        state = r["status"] if r["status"] != "completed" else (ICON.get(r["conclusion"], "?") + " " + str(r["conclusion"]))
        print(f"  #{r['run_number']:<5} {r['name']:<16} {state:<22} "
              f"{r['head_sha'][:7]} {r['created_at']}  id={r['id']}")


def detail(run_id: int):
    st, d = api("GET", f"/repos/{OWNER}/{REPO}/actions/runs/{run_id}/jobs")
    if st != 200:
        print(f"✗ 取 jobs 失败 HTTP {st}")
        return
    for j in d.get("jobs", []):
        print(f"  · job {j['name']}: {j['status']} / {j.get('conclusion')}")
        for s in j.get("steps", []):
            mark = ICON.get(s.get("conclusion") or "", "…")
            print(f"      {mark} {s['name']}")


def wait(run_id: int | None, timeout_min: int = 60):
    t0 = time.time()
    while True:
        rs = runs(5)
        target = None
        for r in rs:
            if run_id and r["id"] == run_id:
                target = r
                break
            if not run_id and r["name"] == "android-full":
                target = r
                break
        if not target:
            print(f"… {int(time.time() - t0)}s：还没看到目标运行")
        else:
            el = int(time.time() - t0)
            print(f"… {el}s  #{target['run_number']} {target['status']}"
                  f"{' / ' + str(target['conclusion']) if target['conclusion'] else ''}")
            if target["status"] == "completed":
                print("\n最终状态：", target["conclusion"], "  ", target["html_url"])
                detail(target["id"])
                return 0 if target["conclusion"] == "success" else 1
            run_id = target["id"]
        if time.time() - t0 > timeout_min * 60:
            print("… 超时了，它可能还在跑，待会再看")
            return 2
        time.sleep(20)


def logs(run_id: int):
    st, d = api("GET", f"/repos/{OWNER}/{REPO}/actions/runs/{run_id}/jobs")
    if st != 200:
        sys.exit(f"✗ 取 jobs 失败 HTTP {st}")
    for j in d.get("jobs", []):
        for s in j.get("steps", []):
            if s.get("conclusion") in ("failure", "cancelled"):
                print(f"\n===== 失败步骤：{s['name']} =====")
                st2, blob = api("GET", f"/repos/{OWNER}/{REPO}/actions/jobs/{j['id']}/logs", raw=True)
                if st2 in (200, 302) and isinstance(blob, bytes):
                    txt = blob.decode("utf-8", "ignore")
                    lines = [l for l in txt.splitlines() if l.strip()]
                    print("\n".join(lines[-80:]))
                else:
                    print(f"（拿不到日志 HTTP {st2}）")


def download(run_id: int, outdir="download"):
    st, d = api("GET", f"/repos/{OWNER}/{REPO}/actions/runs/{run_id}/artifacts")
    if st != 200:
        sys.exit(f"✗ 取产物失败 HTTP {st}")
    arts = d.get("artifacts", [])
    if not arts:
        print("这次运行没有产物")
        return 1
    os.makedirs(outdir, exist_ok=True)
    for a in arts:
        print(f"下载 {a['name']}（{a['size_in_bytes'] / 1048576:.1f} MB）…")
        st2, blob = api("GET", a["archive_download_url"], raw=True)
        if st2 != 200:
            print(f"✗ HTTP {st2}")
            continue
        zpath = os.path.join(outdir, a["name"] + ".zip")
        open(zpath, "wb").write(blob)
        with zipfile.ZipFile(zpath) as z:
            for n in z.namelist():
                z.extract(n, outdir)
                print("  解出", n, f"{os.path.getsize(os.path.join(outdir, n)) / 1048576:.1f} MB")
        os.remove(zpath)
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--wait", action="store_true")
    p.add_argument("--run-id", type=int, default=None)
    p.add_argument("--logs", type=int, default=None)
    p.add_argument("--dl", type=int, default=None)
    p.add_argument("--timeout-min", type=int, default=60)
    a = p.parse_args()
    if a.logs:
        return logs(a.logs) or 0
    if a.dl:
        return download(a.dl)
    if a.wait:
        return wait(a.run_id, a.timeout_min)
    print(f"{OWNER}/{REPO} 最近几次运行：")
    show(runs())
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)