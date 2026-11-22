#!/bin/bash
# 起连环的开发服（默认 8601）。给「后台被清掉、服务没了」这种情况用。
#
# 用法：
#   tools/dev-up.sh            # 起在 8601
#   tools/dev-up.sh 8602       # 换端口
#   tools/dev-up.sh --status   # 只看在不在跑
#
# 为什么要 setsid：Operit 清后台时会把整个 proot 会话的进程组一起收掉。
# `nohup ... &` 挡不住这个（nohup 只挡 SIGHUP），setsid 能让它脱离当前会话，
# 至少不会跟着这个终端一起没。真要彻底常驻，那是 APK 自己的事 —— 开发服只用来看效果。
set -u

cd "$(dirname "$0")/.." || exit 1

PORT="${1:-8601}"
if [ "$PORT" = "--status" ]; then
  PORT=8601
  CHECK_ONLY=1
else
  CHECK_ONLY=0
fi

probe() {
  ./.venv/bin/python - "$1" <<'PY' 2>/dev/null
import sys, urllib.request
try:
    r = urllib.request.urlopen('http://127.0.0.1:%s/' % sys.argv[1], timeout=6)
    print(r.status)
except Exception:
    sys.exit(1)
PY
}

if [ "$CHECK_ONLY" = "1" ]; then
  if probe "$PORT" > /dev/null; then
    echo "✓ 在跑（端口 $PORT）"
    exit 0
  fi
  echo "✗ 没在跑（端口 $PORT）"
  exit 1
fi

# 已经跑着就别再起一个，否则第二个会因端口占用静默退出（踩过）
if probe "$PORT" > /dev/null; then
  echo "已经在跑了，不用再起（端口 $PORT）"
  echo "  http://127.0.0.1:$PORT/"
  exit 0
fi

LOG="${TMPDIR:-/tmp}/lianhuan-dev-$PORT.log"
setsid nohup ./.venv/bin/python -m core.server --port "$PORT" \
  > "$LOG" 2>&1 < /dev/null &

# 等它真能应答再报成功 —— 光看进程在不算数（uvicorn 在子线程里绑定失败会无声退出）
for _ in $(seq 1 20); do
  sleep 0.6
  if probe "$PORT" > /dev/null; then
    echo "✓ 起来了：http://127.0.0.1:$PORT/"
    echo "  日志：$LOG"
    exit 0
  fi
done

echo "✗ 20 秒还没应答，看日志：$LOG"
tail -20 "$LOG"
exit 1