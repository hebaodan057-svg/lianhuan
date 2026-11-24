"""薄 MCP 客户端 —— 让 AI 用上用户配好的 MCP 工具（钓鱼、日历、任何 stdio server）。

原项目的 AI 有 28 只 MCP 手，走的就是这条路。开源版把它接到 API 引擎上：
`data/mcp.json` 里登记 server（**格式跟 Claude 的 .mcp.json 一样**，现成配置直接抄），
启动时连上、拉工具清单、并进 AI 的手；AI 调工具 = 这儿转发 JSON-RPC。

★ 安全边界：server 的启动命令是**用户自己贴的**（等于用户自己运行程序）。
  AI 只能用已登记的 server，**不能自己添加** —— 想要新的就写进装配单等人点头。

三种写法（格式跟 Claude 的 .mcp.json 一样）：

    {
      "mcpServers": {
        "本地服务": {"command": "npx", "args": ["-y", "some-mcp"], "env": {"K": "v"}},
        "远程服务": {"endpoint": "https://host/mcp", "headers": {"Authorization": "Bearer x"}},
        "临时关掉的": {"disabled": true, "command": "..."}
      }
    }

判断只看一个字段：**有 endpoint 就是远程 HTTP，没有就是本地 stdio**。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

_servers: dict = {}          # name -> _Server


def _cfg_file() -> Path:
    return Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "mcp.json"


def load_cfg() -> dict:
    try:
        return json.loads(_cfg_file().read_text(encoding="utf-8")).get("mcpServers") or {}
    except Exception:
        return {}


def _write_cfg(value: dict) -> None:
    f = _cfg_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(f.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(f)


def save_server(name: str, command: str = "", args: list | None = None,
                env: dict | None = None, endpoint: str = "",
                headers: dict | None = None) -> None:
    """登记一条 server。两种形态二选一：

      · 本地：command（+ args / env）
      · 远程：endpoint（+ headers，token 就放这里）

    ★ 保留原有的 disabled 标记 —— 用户在界面上关掉过的服务，
      改个地址不该把它悄悄打开。
    """
    f = _cfg_file()
    try:
        cfg = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    servers = cfg.setdefault("mcpServers", {})
    was = servers.get(name) or {}
    spec: dict = {}
    if endpoint:
        spec["endpoint"] = endpoint
        if headers:
            spec["headers"] = headers
    else:
        spec["command"] = command
        spec["args"] = list(args or [])
        spec["env"] = dict(env or {})
    if was.get("disabled"):
        spec["disabled"] = True
    servers[name] = spec
    _write_cfg(cfg)


def set_enabled(name: str, on: bool) -> bool:
    """开 / 关一条 server。关掉＝不连、不列工具、不占 token。

    返回 False 表示这条根本不存在。
    """
    f = _cfg_file()
    try:
        cfg = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return False
    servers = cfg.setdefault("mcpServers", {})
    if name not in servers:
        return False
    if on:
        servers[name].pop("disabled", None)
    else:
        servers[name]["disabled"] = True
    _write_cfg(cfg)
    return True


def drop_server(name: str) -> None:
    f = _cfg_file()
    try:
        cfg = json.loads(f.read_text(encoding="utf-8"))
        cfg.get("mcpServers", {}).pop(name, None)
        _write_cfg(cfg)
    except Exception:
        pass
    s = _servers.pop(name, None)
    if s:
        asyncio.get_event_loop().create_task(s.close())


class _HttpServer:
    """远程 streamable HTTP 的 MCP server。

    每个 JSON-RPC 一条 POST；响应可能是整块 JSON，也可能是 SSE 帧。
    ★ 三个必须的细节（都是实战踩出来的）：
       · Accept 必须同时声明 json 和 text/event-stream —— 只写 json 的话，
         严格实现的服务端直接 406（MCP 规范要求客户端声明能接 SSE）。
       · 有的服务端空闲时会单方面掐掉 keep-alive 连接，复用到死连接就抛
         RemoteProtocolError / ReadError。这不是我们的错，sleep 一下重连即可。
       · 响应要兼容三种形态：单个对象 / 数组 / SSE 帧。
    """

    def __init__(self, name: str, spec: dict):
        self.name, self.spec = name, spec
        self.tools: list = []
        self.err = ""
        self._id = 0
        self._sid = ""
        self._client = None
        self._lock = asyncio.Lock()
        self._started = False

    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        for k, v in (self.spec.get("headers") or {}).items():
            h[str(k)] = str(v)
        if self._sid:
            h["mcp-session-id"] = self._sid
        return h

    async def _post(self, payload: dict, timeout: float):
        import httpx
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=timeout)
        last = None
        for attempt in (0, 1):
            try:
                r = await self._client.post(self.spec["endpoint"], json=payload,
                                            headers=self._headers())
                sid = r.headers.get("mcp-session-id")
                if sid:
                    self._sid = sid
                return r.status_code, (r.text or "")
            except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError,
                    httpx.WriteError, httpx.PoolTimeout) as e:
                last = e
                if attempt == 0:
                    await asyncio.sleep(0.4)   # 让那条死连接彻底关掉再重来
                    continue
                raise
        raise last                                     # pragma: no cover

    @staticmethod
    def _pick_reply(text: str, rid: int):
        """响应可能是整块 JSON、JSON 数组，也可能是 SSE（`data: {...}` 一帧一行）。"""
        text = (text or "").strip()
        try:
            d = json.loads(text)
            if isinstance(d, list):
                for x in d:
                    if isinstance(x, dict) and x.get("id") == rid:
                        return x
                return d[0] if d and isinstance(d[0], dict) else None
            return d if isinstance(d, dict) else None
        except Exception:
            pass
        found = None
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                d = json.loads(raw)
            except Exception:
                continue
            if isinstance(d, dict):
                if d.get("id") == rid:
                    return d
                if d.get("result") is not None or d.get("error") is not None:
                    found = d
        return found

    async def _rpc(self, method: str, params: dict, timeout: float = 25):
        async with self._lock:
            self._id += 1
            rid = self._id
            payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
            code, text = await self._post(payload, timeout)
            if code >= 400:
                raise RuntimeError(f"HTTP {code}: {(text or '')[:120]}")
            d = self._pick_reply(text, rid)
            if not isinstance(d, dict):
                raise RuntimeError(f"没解析出 JSON-RPC 回复：{(text or '')[:120]}")
            if d.get("error"):
                raise RuntimeError(str(d["error"])[:160])
            return d.get("result")

    async def _notify(self, method: str, params: dict | None = None) -> None:
        payload = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params
        try:
            await self._post(payload, 15)
        except Exception:
            pass                                       # 通知没回执，失败也不拦

    async def start(self) -> None:
        try:
            await self._rpc("initialize", {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "lianhuan", "version": "0.1"}}, timeout=20)
            await self._notify("notifications/initialized")
            r = await self._rpc("tools/list", {}, timeout=20)
            self.tools = (r or {}).get("tools") or []
            self._started = True
        except Exception as e:
            self.err = f"{type(e).__name__}: {e}"[:160]
            await self.close()

    async def call(self, tool: str, args: dict):
        r = await self._rpc("tools/call", {"name": tool, "arguments": args or {}}, timeout=60)
        return r if isinstance(r, dict) else {"content": [{"type": "text", "text": str(r)}]}

    async def close(self) -> None:
        self.tools = []
        self._started = False
        try:
            if self._client is not None:
                await self._client.aclose()
        except Exception:
            pass
        self._client = None


def _make(name: str, spec: dict):
    """有 endpoint 就是远程 HTTP，否则本地 stdio。判断就这一行。"""
    return _HttpServer(name, spec) if (spec or {}).get("endpoint") else _Server(name, spec)


class _Server:
    def __init__(self, name: str, spec: dict):
        self.name, self.spec = name, spec
        self.proc: asyncio.subprocess.Process | None = None
        self.tools: list = []
        self.err = ""
        self._id = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        try:
            env = dict(os.environ)
            env.update(self.spec.get("env") or {})
            self.proc = await asyncio.create_subprocess_exec(
                self.spec["command"], *(self.spec.get("args") or []),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, env=env,
                limit=8 * 1024 * 1024)
            await self._rpc("initialize", {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "lianhuan", "version": "0.1"}}, timeout=20)
            await self._notify("notifications/initialized")
            r = await self._rpc("tools/list", {}, timeout=20)
            self.tools = (r or {}).get("tools") or []
        except Exception as e:
            self.err = f"{type(e).__name__}: {e}"[:160]
            await self.close()

    async def _send(self, msg: dict) -> None:
        self.proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode())
        await self.proc.stdin.drain()

    async def _notify(self, method: str) -> None:
        await self._send({"jsonrpc": "2.0", "method": method})

    async def _rpc(self, method: str, params: dict, timeout: float = 45) -> dict:
        async with self._lock:               # stdio 一条管道，请求要排队
            self._id += 1
            rid = self._id
            await self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
            loop = asyncio.get_running_loop()
            end = loop.time() + timeout
            while True:
                left = end - loop.time()
                if left <= 0:
                    raise TimeoutError(method)
                line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=left)
                if not line:
                    raise RuntimeError("server 退出了")
                try:
                    d = json.loads(line)
                except Exception:
                    continue                  # 有的 server 往 stdout 混日志，跳过
                if d.get("id") == rid:
                    if "error" in d:
                        raise RuntimeError(str(d["error"])[:200])
                    return d.get("result") or {}

    async def call(self, tool: str, args: dict) -> dict:
        r = await self._rpc("tools/call", {"name": tool, "arguments": args})
        # 把 content 摊平成文本，喂回模型
        out = []
        for c in (r or {}).get("content") or []:
            if c.get("type") == "text":
                out.append(c.get("text") or "")
        txt = "\n".join(out)[:4000] or json.dumps(r, ensure_ascii=False)[:2000]
        return {"ok": not (r or {}).get("isError"), "result": txt}

    async def close(self) -> None:
        p, self.proc = self.proc, None
        if p and p.returncode is None:
            try:
                p.kill()
                await p.wait()
            except Exception:
                pass


async def start_all() -> None:
    cfg = load_cfg()
    # 关掉的先从内存里撤掉：不连、不列工具、不占 token
    for name in list(_servers.keys()):
        if name not in cfg or (cfg.get(name) or {}).get("disabled"):
            old = _servers.pop(name, None)
            if old:
                try:
                    await old.close()
                except Exception:
                    pass
    for name, spec in cfg.items():
        if (spec or {}).get("disabled"):
            continue
        old = _servers.get(name)
        # 安装好一个之前失败的 server 后要能重试；配置换了也不能继续守着旧连接。
        if old and old.tools and old.spec == spec:
            continue
        if old:
            try:
                await old.close()
            except Exception:
                pass
        s = _make(name, spec)
        _servers[name] = s
        await s.start()


def status() -> list:
    """界面要用的状态。

    ★ 关掉的 server 也要列出来 —— 界面上「关着」和「不存在」是两件事，
      只列连上的话，用户一关就找不到它、也就没法再打开。
    """
    cfg = load_cfg()
    rows = []
    seen = set()
    for n, s in _servers.items():
        seen.add(n)
        spec = cfg.get(n) or {}
        rows.append({
            "name": n, "tools": [t["name"] for t in s.tools],
            "ok": bool(s.tools), "err": s.err,
            "type": "http" if spec.get("endpoint") else "stdio",
            "url": spec.get("endpoint") or (spec.get("command") or ""),
            "enabled": True,
        })
    for n, spec in cfg.items():
        if n in seen:
            continue
        spec = spec or {}
        off = bool(spec.get("disabled"))
        rows.append({
            "name": n, "tools": [], "ok": False,
            "err": "" if off else "还没连上",
            "type": "http" if spec.get("endpoint") else "stdio",
            "url": spec.get("endpoint") or (spec.get("command") or ""),
            "enabled": not off,
        })
    rows.sort(key=lambda x: (not x["enabled"], x["name"]))
    return rows


def _fn_name(server: str, tool: str) -> str:
    """openai 函数名只许 [A-Za-z0-9_-] 64 字内。"""
    return re.sub(r"[^A-Za-z0-9_-]", "_", f"{server}__{tool}")[:64]


def openai_tools() -> list:
    out = []
    for n, s in _servers.items():
        for t in s.tools:
            out.append({"type": "function", "function": {
                "name": _fn_name(n, t["name"]),
                "description": f"[{n}] " + (t.get("description") or "")[:400],
                "parameters": t.get("inputSchema") or {"type": "object", "properties": {}}}})
    return out


async def execute(fn_name: str, args: dict) -> dict | None:
    """认领得了就执行，认领不了返回 None（让内置的手接着试）。"""
    for n, s in _servers.items():
        for t in s.tools:
            if _fn_name(n, t["name"]) == fn_name:
                try:
                    return await s.call(t["name"], args)
                except Exception as e:
                    return {"ok": False, "err": f"{type(e).__name__}: {e}"[:200]}
    return None


async def call_tool(server: str, tool: str, args: dict) -> dict | None:
    """Call one named MCP tool without exposing the private server object to routes."""
    s = _servers.get(server)
    if not s or not any(t.get("name") == tool for t in s.tools):
        return None
    try:
        return await s.call(tool, args)
    except Exception as e:
        return {"ok": False, "err": f"{type(e).__name__}: {e}"[:200]}
