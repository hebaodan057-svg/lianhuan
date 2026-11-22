#!/usr/bin/env python3
"""握手测试：证明「端口应答了 ≠ 应答的是我」这条已经堵上。

跑法：  .venv/bin/python tools/test-handshake.py
"""
import hashlib
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HOST = "127.0.0.1"
PORT = 8611
TOKEN = "TESTTOKEN_abcdefghijklmnop"

# 模拟「完整体自己起的后端」：带票
os.environ["LIANHUAN_ANDROID_TOKEN"] = TOKEN

import uvicorn  # noqa: E402
from core.server import app  # noqa: E402

cfg = uvicorn.Config(app, host=HOST, port=PORT, log_level="critical")
srv = uvicorn.Server(cfg)


def wait_up():
    for _ in range(60):
        s = socket.socket()
        s.settimeout(0.2)
        try:
            s.connect((HOST, PORT))
            s.close()
            return True
        except OSError:
            time.sleep(0.2)
        finally:
            try:
                s.close()
            except OSError:
                pass
    return False


threading.Thread(target=srv.run, daemon=True).start()
if not wait_up():
    print("✗ 服务没起来")
    raise SystemExit(1)

import urllib.error  # noqa: E402
import urllib.request  # noqa: E402


def _text(raw, n):
    """只取前 n 字节做展示。★ 不能直接 raw[:n].decode()：
    中文是多字节的，切在第 300 个字节中间会抛 UnicodeDecodeError —— 那是脚本自己的
    毛病，会让人以为被测的东西坏了。errors='replace' 就够了，这里只为打印。"""
    return raw[:n].decode("utf-8", "replace")


def get(path, cookie=None, port=None):
    port = port or PORT
    req = urllib.request.Request("http://%s:%d%s" % (HOST, port, path))
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        r = urllib.request.urlopen(req, timeout=5)
        return r.status, _text(r.read(400), 300)
    except urllib.error.HTTPError as e:
        return e.code, _text(e.read(400), 200)


st1, body1 = get("/api/android/hello")
print("① hello 不带票 ->", st1, body1[:80])
assert st1 == 200, "握手端点必须免票，否则循环依赖"

st2, _ = get("/")
print("② 首页不带票 ->", st2, "(应为 401)")
assert st2 == 401

st3, _ = get("/", "lh_android=" + TOKEN)
print("③ 首页带票   ->", st3, "(应为 200)")
assert st3 == 200

want = hashlib.sha256(TOKEN.encode()).hexdigest()[:16]
print("④ nonce 对上 ->", want in body1, "| 期望", want)
assert want in body1

# 没有票的后端（就是开发服的样子）：hello 回 404，完整体据此拒绝开页
print("\n⑤ 开发服（没票）的 hello 应当 404：")
os.environ.pop("LIANHUAN_ANDROID_TOKEN", None)
os.system("pkill -f 'port 8611' 2>/dev/null")
time.sleep(1)

srv.should_exit = True
time.sleep(0.6)

PORT2 = 8612
cfg2 = uvicorn.Config(app, host=HOST, port=PORT2, log_level="critical")
srv2 = uvicorn.Server(cfg2)
threading.Thread(target=srv2.run, daemon=True).start()
time.sleep(2.5)
st5, body5 = None, ""
try:
    req = urllib.request.Request("http://%s:%d/api/android/hello" % (HOST, PORT2))
    r = urllib.request.urlopen(req, timeout=5)
    st5, body5 = r.status, r.read(200).decode()
except urllib.error.HTTPError as e:
    st5, body5 = e.code, e.read(200).decode()
print("   ->", st5, body5[:80], "(应为 404)")
assert st5 == 404

print("\n全部通过。")
srv2.should_exit = True
time.sleep(0.4)