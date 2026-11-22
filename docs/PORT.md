# 端口：谁占着 8420 就是谁在说话

> 一句话：**8420 是安卓完整体 APK 自己的端口**。本机开发/试用请用 8601。
> 占着 8420 再打开 APK，你在 APK 里看到的是**另一个人**，写进去的话也进了**另一个库**。

## 这张表

| 谁 | 监听在 | 家（SQLite）在哪 |
|---|---|---|
| 安卓完整体 APK（`android-full/`） | `127.0.0.1:8420`（写死） | 应用沙箱 `filesDir/data/lianhuan.db` |
| 本机 / 开发服（`start.command`） | `127.0.0.1:8601`（默认） | 仓库里的 `data/lianhuan.db` |
| 云上 / Docker | `0.0.0.0:$PORT`（容器内 8420） | `/app/data/lianhuan.db` |
| 浏览器版（`apps/local/`） | 没有端口，Pyodide 在页面里 | 这台设备的 IndexedDB |

**只有第一行那个 8420 是特殊约定**，因为 APK 里的地址是编译进 Java 的：

```java
// android-full/app/src/main/java/app/lianhuan/full/MainActivity.java
private static final int PORT = 8420;
private static final String BASE = "http://127.0.0.1:" + PORT;
...
web.loadUrl(BASE + "/");
```

## 踩过的坑（真实的，不是假设）

```
09:xx  在手机上为了「改完立刻看效果」，把开发服起在 8420
        .venv/bin/python -m core.server --port 8420

09:xx  打开安卓完整体 APK
        APK 也起后端 → 绑定 8420 失败
        uvicorn 在子线程里抛 SystemExit(3)，没人接，静默
        Java 那边 alive() 只问「端口能应答吗」→ 能 → 开页
        开的是开发服那份页面

结果    用户在 APK 里看到的是改过的界面（开发服的）
        说的话进了开发服的 data/lianhuan.db
        APK 沙箱里的库一个字没动
        用户以为「改动进包了」—— 一个字都没进
```

**为什么它特别坏**：它不是报错，是**看起来成功了**。界面是你改的那一份，所以你会以为打进去了；只有等你发现「APK 里重开又变回原样」才会察觉。

## 已经堵上的四道口子

### ① `start.command` / `start.sh` 默认 8601，并且拦住 8420

```sh
PORT="${PORT:-8601}"
if [ "$PORT" = "$APK_PORT" ] && [ "${LIANHUAN_ALLOW_8420:-0}" != "1" ]; then
  echo "✗ 8420 是安卓完整体 APK 自己的后端端口，本机这份不能用它。" >&2
  exit 2
fi
```

确实需要（这台机器上没有 APK）：

```sh
LIANHUAN_ALLOW_8420=1 PORT=8420 ./start.command
```

### ② `core.server` 在 8420 上起时当场提醒

```python
if a.port == 8420 and not os.environ.get("LIANHUAN_ANDROID_TOKEN"):
    print("  ⚠ 8420 是安卓完整体 APK 的端口。在这儿跑开发服，APK 打开时会")
    print("    连到这份开发服上，不是它自己沙箱里的后端。换一个：--port 8601")
```

### ③ `android_boot.py` 先把端口抢一次，抢不到就说人话

```python
probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    probe.bind(("127.0.0.1", port))
except OSError as e:
    raise RuntimeError(f"端口 {port} 已经被别的进程占了（{e}）。…")
finally:
    probe.close()
```

同时把 uvicorn 那个静默的 `SystemExit(3)` 收进 `boot_error()`，Java 能读到。

### ④ `MainActivity.java` 不再问「活着吗」，改问「你是不是我」

```java
String want = boot.callAttr("nonce").toString();   // 我自己那枚票的指纹
String got  = handshake();                          // 8420 上那个自报的指纹
if (!got.equals(want)) {
    show("8420 上跑的不是连环自己的后端（另一个程序占着这个端口）。"
       + "连环没有打开它 —— 那样说的话会存到别人那里去。");
    return;                                        // 宁可不开
}
```

后端那一头是 `GET /api/android/hello`：

```
完整体自己起的后端  →  200 {"app":"lianhuan","android":true,"nonce":"862be7e9…"}
普通/开发服/云上    →  404 {"error":"这里不是安卓完整体"}
```

对不上就不开页。**打不开比打开错的强。**

## 怎么自查

```sh
# 谁占着 8420
ss -ltnp | grep :8420          # Linux
lsof -nP -iTCP:8420 -sTCP:LISTEN   # macOS
```

```sh
# 8420 上那个到底是不是完整体
curl -s http://127.0.0.1:8420/api/android/hello
#   {"app":"lianhuan","android":true,"nonce":"…"}   → 是
#   {"error":"这里不是安卓完整体"}                    → 不是，别在 APK 里用它
```

```sh
# 一条命令跑完整个握手检查
.venv/bin/python tools/test-handshake.py
```

## 一条容易搞混的事

**「端口是 8420」和「跑的是 APK 里的代码」是两件事。**

APK 里的前端是**打包时**塞进去的静态文件，改仓库里的 `core/web/index.html` 不会自动进包。要让改动真的进 APK，只有重新构建（见 `android-full/README.md`、`.github/workflows/android-full.yml`），或者干脆用本机那份（8601）当工作台。

在拿到新 APK 之前，把这两件事分清楚：

| | 用途 |
|---|---|
| `http://127.0.0.1:8601` | 我改的界面。刷新就是最新。 |
| APK（8420） | 你的家。数据在这。前端是 v0.1.31 那份。 |
