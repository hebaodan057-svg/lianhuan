"""连环 · 安卓完整体的起点。Java 那边开机时调一次 start()，后端就在这个进程里跑起来。

数据全在应用自己的沙箱（filesDir/data）：SQLite、上传、secrets.json 都在那儿。
卸载 app 就一起没了；要搬家先在设置里导出 JSON。
"""
from __future__ import annotations

import os
import secrets
import socket
import threading

_started: dict = {}


def start(files_dir: str, port: int = 8420) -> str:
    """把后端起在回环；随机票由原生 WebView 放进 HttpOnly Cookie。"""
    if _started.get("url"):
        return _started["url"]
    data = os.path.join(files_dir, "data")
    os.makedirs(data, exist_ok=True)
    os.environ.setdefault("LIANHUAN_DB", os.path.join(data, "lianhuan.db"))
    token = secrets.token_urlsafe(32)
    os.environ["LIANHUAN_ANDROID_TOKEN"] = token

    import uvicorn
    from core.server import app

    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", loop="asyncio")
    srv = uvicorn.Server(cfg)

    # ★★ 端口先自己试一下。踩过的坑：8420 被别的进程（比如一个跑在 8420 的开发服）
    #    先占着时，uvicorn 在子线程里绑定失败抛的是 SystemExit(3) —— 子线程里没人接，
    #    _started["url"] 照样写上，Java 那边 20 秒后看到「端口能连」就开页，
    #    结果开的是**别人的**页面。所以这里先把端口抢一次：抢不到就直接报错，
    #    让 Java 弹一句人话，而不是静默把别人的东西当自己的开起来。
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind(("127.0.0.1", port))
    except OSError as e:
        raise RuntimeError(
            f"端口 {port} 已经被别的进程占了（{e}）。连环要的是它自己那个后端，"
            "现在这个端口上坐着的不是它 —— 关掉占着它的东西再开一次。"
        ) from e
    finally:
        probe.close()

    _started["boot_error"] = ""

    def _run():
        try:
            srv.run()
        except BaseException as e:                      # noqa: BLE001
            # SystemExit(3) 就是「绑定失败」。这里不吞，記下来给 Java 看。
            _started["boot_error"] = f"{type(e).__name__}: {e}"

    # ★ 不是主线程：uvicorn 在非主线程里会自己跳过信号处理，这正是这儿要的
    t = threading.Thread(target=_run, name="lianhuan-uvicorn", daemon=True)
    t.start()
    _started["url"] = f"http://127.0.0.1:{port}/"
    _started["token"] = token
    _started["server"] = srv
    return _started["url"]


def token() -> str:
    """只给同进程的 Java 启动代码取；不会进 URL、日志或页面脚本。"""
    return _started.get("token", "")


def boot_error() -> str:
    """后台起步失败了没有；空串 = 正常。Java 拿它决定要不要弹人话。"""
    return _started.get("boot_error", "")


def nonce() -> str:
    """给 Java 比对的指纹。★ 不是票本身 —— 票只往 HttpOnly Cookie 里放，
    指纹只用于回答一个问题：「8420 上那个后端是不是我自己起的那个」。"""
    import hashlib
    t = _started.get("token", "")
    return hashlib.sha256(t.encode()).hexdigest()[:16] if t else ""
