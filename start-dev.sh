#!/bin/sh
# 连环 · 本机开发服
#
# ★ 绝不能占 8420。安卓完整体 APK 自己的后端就跑在 127.0.0.1:8420，
#   而它的 WebView 打开的就是 http://127.0.0.1:8420/ ——
#   这个端口先被谁占，用户在 APK 里看到的就是谁，写进去的话也进了谁的库。
#   踩过：开发服占着 8420 时，APK 的 WebView 直接连到了开发服上，
#   页面是改过的、数据库却是 data/lianhuan.db，而 APK 沙箱里那份一个字没动。
#
# 用 PORT 推翻：PORT=8602 ./start-dev.sh
set -e
cd "$(dirname "$0")"
PORT="${PORT:-8601}"
if [ "$PORT" = "8420" ]; then
  echo "✗ 8420 是安卓完整体的端口，开发服不能占。换个号：PORT=8601 ./start-dev.sh" >&2
  exit 2
fi
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q --disable-pip-version-check fastapi uvicorn httpx 2>/dev/null || true
exec .venv/bin/python -m core.server --port "$PORT"
