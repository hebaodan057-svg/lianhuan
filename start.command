#!/usr/bin/env bash
# 连环 —— 双击这个就能跑（macOS / Linux）。
#
# 它做四件事：建虚拟环境 → 装依赖 → 起服务 → 打开浏览器。
# 都做过一遍之后，以后每次双击就是几秒的事。
#
# ★ 要接模型的话，先在同目录建一个 .env 文件（照 .env.example 写）。
#   key 只在这台机器上，不会进任何仓库、不会进数据库、不会进导出的备份。
#
# ══ 为什么默认是 8601，不是 8420 ══════════════════════════════════
# 安卓完整体 APK（android-full）把后端**写死**在 127.0.0.1:8420，
# 它的 WebView 开机就去开 http://127.0.0.1:8420/。
# 也就是说：谁先占住 8420，用户在 APK 里看到的就是谁，写进去的话也进谁的库。
#
# 真踩过：在手机上把开发服起在 8420，然后打开 APK —— 页面是开发服那份（改过的），
# 数据库也是开发服的 data/lianhuan.db，而 APK 沙箱里那份一个字没动。
# 看起来像「改动进包了」，其实一个字都没进。见 docs/PORT.md。
#
# 所以这个脚本默认用 8601，并且在你**明确**要 8420 时先拦一下。
#
# ★ 所有检查都排在 pip install 之前 —— 配错了要**立刻**知道，
#   不该先等一分钟装完依赖再被告知端口不对。
set -euo pipefail
cd "$(dirname "$0")"

#: ★ 安卓完整体 APK 的端口。别改这个数字，要去 android-full 那边一起改。
APK_PORT=8420

PORT="${PORT:-8601}"

# ══ 门一：不许占 APK 的端口 ═══════════════════════════════
# 放在最前面：纯 bash，不碰 python、不碰网络，错了当场退。
if [ "$PORT" = "$APK_PORT" ] && [ "${LIANHUAN_ALLOW_8420:-0}" != "1" ]; then
  cat >&2 <<EOF

  ✗ 8420 是安卓完整体 APK 自己的后端端口，本机这份不能用它。

    这不是洁癖：APK 的 WebView 开机就去开 127.0.0.1:$APK_PORT。
    你在这里起一份，APK 打开时连到的就是这一份 —— 页面是这里的、
    数据库也是这里的（data/lianhuan.db），APK 沙箱里那份一个字不动。
    看起来像「改动生效了」，其实改的和看的不是同一个东西。

    换个端口就行：
        PORT=8601 ./start.command

    确实要在 8420 上跑（比如这台机器上根本没有 APK）：
        LIANHUAN_ALLOW_8420=1 PORT=8420 ./start.command

EOF
  exit 2
fi

# ══ 门二：python 在不在 ══════════════════════════════════
PY=$(command -v python3 || true)
if [ -z "$PY" ]; then
  echo "找不到 python3。"
  echo "macOS：装 Xcode 命令行工具（xcode-select --install）或去 python.org 下一个"
  echo "Linux：apt install python3 python3-venv / dnf install python3"
  read -rp "按回车关闭…" _; exit 1
fi

# ══ 门三：端口被占了就直说 ═══════════════════════════════
# ★ uvicorn 绑定失败抛的是 SystemExit(3)，在很多壳里会被吞掉、或者只剩一行英文。
#   先自己试一次绑定，失败了给一句人话。也排在 pip install 前面。
#   （用 `-c` 传一行代码而不是 heredoc：heredoc 会吃掉 stdin，
#     后面的 pip 安装有时候要读 stdin，容易出怪事。）
if ! "$PY" -c '
import socket, sys
port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(("127.0.0.1", port))
except OSError as e:
    print("\n  ✗ 端口 %d 被占了（%s）。\n" % (port, e), file=sys.stderr)
    print("    连环要的是它自己那一份。先看看是谁占着：", file=sys.stderr)
    print("      Linux：  ss -ltnp | grep :%d" % port, file=sys.stderr)
    print("      macOS：  lsof -nP -iTCP:%d -sTCP:LISTEN" % port, file=sys.stderr)
    print("\n    或者干脆换一个：PORT=%d ./start.command\n" % (port + 1), file=sys.stderr)
    sys.exit(1)
finally:
    s.close()
' "$PORT"; then
  exit 3
fi

# ══ 到这里才开始真的动手 ════════════════════════════════
if [ ! -d .venv ]; then
  echo "· 第一次跑，先建个干净的环境（一分钟左右）…"
  "$PY" -m venv .venv
fi

# ── 依赖分两批装 ─────────────────────────────────────────
# ★ 为什么不用一句 `pip install -r requirements.txt`：
#   requirements.txt 里第四个是 pywebpush（推到手机上用的）。它要装
#   http-ece，而 http-ece 只有 sdist、得**当场编译** build 依赖 ——
#   在手机上（proot/aarch64）或者网络不好的时候会卡在那里几分钟，
#   而前三个早就好了、聊天根本不需要它。
#
#   所以：必需的三个装不上就算失败（那是真坏了）；
#   pywebpush 装不上只提示一句，照常起服务。
echo "· 装依赖…"
if ! ./.venv/bin/pip install -q --disable-pip-version-check fastapi uvicorn httpx; then
  echo ""
  echo "  ✗ 前三个核心依赖没装上（fastapi / uvicorn / httpx）。"
  echo "    这仨是聊天和页面本身要的，没有它们服务起不来。"
  echo "    常见原因：网络不通，或者这台机器的 pip 源有问题。"
  echo "    手动试一次看真实报错："
  echo "        ./.venv/bin/pip install fastapi uvicorn httpx"
  echo ""
  exit 4
fi

#: 可选：推送到手机。装不上不影响使用，只是设置里那个「推到手机」按钮不工作。
if [ "${LH_NO_PUSH:-0}" != "1" ]; then
  if ! ./.venv/bin/pip install -q --disable-pip-version-check pywebpush 2>/dev/null; then
    echo "  · pywebpush 没装上（推到手机那项不可用，别的都正常）"
    echo "    它要现场编译 http-ece，手机上很容易卡。想跳过这条提示："
    echo "        LH_NO_PUSH=1 ./start.command"
  fi
else
  echo "  · 按 LH_NO_PUSH=1 跳过了 pywebpush"
fi

# key 从 .env 读。★ 只在这个进程里，不写库、不写日志
if [ -f .env ]; then
  set -a; . ./.env; set +a
  echo "· 读到 .env 了"
fi

URL="http://127.0.0.1:$PORT"

echo ""
echo "  连环跑起来了：$URL"
echo "  手机也要连的话，关掉这个窗口，改跑：PORT=$PORT ./start.command --lan"
echo "  停下来：在这个窗口按 Ctrl+C"
echo ""

( sleep 1.5
  command -v open >/dev/null && open "$URL" 2>/dev/null \
    || (command -v xdg-open >/dev/null && xdg-open "$URL" 2>/dev/null) || true ) &

exec ./.venv/bin/python -m core.server --port "$PORT" "$@"