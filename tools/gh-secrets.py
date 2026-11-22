#!/usr/bin/env python3
"""把 Actions Secrets 一次性写进仓库（GitHub API + libsodium sealed box）。

为什么要这个脚本：GitHub 的 Secrets 接口不接受明文，值必须用仓库公钥做
libsodium 的 sealed box 加密后再 base64。手机上的 proot 里没有 pip / PyNaCl，
所以这里直接用 ctypes 调 libsodium.so，只依赖 `apk add libsodium`。

用法：
  python3 tools/gh-secrets.py --list              # 看现在有哪些、哪些还没填
  python3 tools/gh-secrets.py --apply             # 写入 values.json 里的全部条目
  python3 tools/gh-secrets.py --apply --only NAME # 只写一条

值从 secrets-temp/values.json 读（该目录在 .gitignore 里，不进仓库）：
  {
    "ANDROID_KEYSTORE_BASE64": "@file:$HOME/.lianhuan/ks.b64",
    "ANDROID_KEYSTORE_PASSWORD": "明文",
    ...
  }
"@file:" 前缀表示「读这个文件的内容」，用于 3624 字符的 base64。
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import json
import os
import sys
import urllib.error
import urllib.request

OWNER = "hebaodan057-svg"
REPO = "lianhuan"
TOKEN_FILE = os.path.expanduser("~/.lianhuan/token")
VALUES_FILE = "secrets-temp/values.json"

# 必须有这 5 个，流水线才肯出正式签名包
REQUIRED = [
    "ANDROID_KEYSTORE_BASE64",
    "ANDROID_KEYSTORE_PASSWORD",
    "ANDROID_KEY_ALIAS",
    "ANDROID_KEY_PASSWORD",
    "LIANHUAN_PRIVATE_MARKERS",
]

CRYPTO_BOX_SEALBYTES = 48


def die(msg: str, code: int = 1):
    print(f"✗ {msg}", file=sys.stderr)
    raise SystemExit(code)


def load_token() -> str:
    tok = os.environ.get("GH_TOKEN") or ""
    if not tok and os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            tok = f.read().strip()
    if not tok:
        die(f"没有 token。请放在 {TOKEN_FILE} 里，或用 GH_TOKEN 环境变量传。")
    return tok


def api(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:400]}
    except urllib.error.URLError as e:
        die(f"连不上 GitHub（网络抖动？）：{e.reason}")


class Sodium:
    """只包了 sealed box 需要的那几个符号。"""

    def __init__(self):
        last = None
        for so in ("libsodium.so.26", "libsodium.so.23", "libsodium.so"):
            try:
                self.lib = ctypes.CDLL(so)
                break
            except OSError as e:
                last = e
        else:
            die(f"加载不了 libsodium（{last}）。先跑：apk add libsodium")
        if self.lib.sodium_init() < 0:
            die("sodium_init 失败")
        self.lib.crypto_box_seal.argtypes = [
            ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulonglong, ctypes.c_char_p
        ]
        self.lib.crypto_box_seal.restype = ctypes.c_int

    def seal(self, message: bytes, pubkey: bytes) -> bytes:
        if len(pubkey) != 32:
            die(f"公钥长度不对：{len(pubkey)}（应为 32）")
        out = ctypes.create_string_buffer(len(message) + CRYPTO_BOX_SEALBYTES)
        rc = self.lib.crypto_box_seal(out, message, len(message), pubkey)
        if rc != 0:
            die(f"crypto_box_seal 返回 {rc}")
        return out.raw


def resolve(v: str) -> str:
    if isinstance(v, str) and v.startswith("@file:"):
        p = os.path.expandvars(os.path.expanduser(v[6:]))
        if not os.path.exists(p):
            die(f"@{p} 不存在")
        return open(p).read()
    return v


def do_list(token: str):
    st, data = api("GET", f"/repos/{OWNER}/{REPO}/actions/secrets", token)
    if st != 200:
        die(f"列 Secrets 失败 HTTP {st}：{data}")
    have = {s["name"]: s for s in data.get("secrets", [])}
    print(f"仓库 {OWNER}/{REPO} 现在有 {len(have)} 个 Secret：")
    for name, s in sorted(have.items()):
        mark = "✓" if name in REQUIRED else " "
        print(f"  [{mark}] {name:<28} 更新于 {s.get('updated_at', '?')}")
    missing = [n for n in REQUIRED if n not in have]
    if missing:
        print("\n还缺（缺了流水线只会出 debug 一次性包）：")
        for n in missing:
            print(f"  - {n}")
    else:
        print("\n5 个必需的都齐了，下次 push 会出正式签名包。")
    return 0 if not missing else 1


def do_apply(token: str, only: str | None):
    if not os.path.exists(VALUES_FILE):
        die(f"缺 {VALUES_FILE}")
    vals = json.load(open(VALUES_FILE))
    if only:
        if only not in vals:
            die(f"{VALUES_FILE} 里没有 {only}")
        vals = {only: vals[only]}

    st, key = api("GET", f"/repos/{OWNER}/{REPO}/actions/secrets/public-key", token)
    if st != 200:
        die(f"取仓库公钥失败 HTTP {st}：{key}")
    key_id = key["key_id"]
    pub = base64.b64decode(key["key"])
    print(f"仓库公钥 {key_id[:16]}…（{len(pub)} 字节）")
    sod = Sodium()

    bad = 0
    for name, raw in vals.items():
        val = resolve(raw)
        if val is None:
            bad += 1
            continue
        if name == "ANDROID_KEYSTORE_BASE64":
            val = "".join(val.split())  # base64 -d 不接受换行里的空白也无所谓，但干净点好
        if name in REQUIRED and not val.strip():
            print(f"✗ {name} 是空的，跳过")
            bad += 1
            continue
        sealed = sod.seal(val.encode(), pub)
        st, res = api(
            "PUT", f"/repos/{OWNER}/{REPO}/actions/secrets/{name}", token,
            {"encrypted_value": base64.b64encode(sealed).decode(), "key_id": key_id},
        )
        if st in (201, 204):
            print(f"✓ {name:<28} 写入成功（明文 {len(val)} 字符）")
        else:
            print(f"✗ {name:<28} 失败 HTTP {st}：{res}")
            bad += 1
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    token = load_token()
    if a.list:
        return do_list(token)
    if a.apply:
        return do_apply(token, a.only)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())