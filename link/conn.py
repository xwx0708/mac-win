"""两台电脑之间的一条长连接：分帧、通道复用、心跳、握手认证、断线自动重连。

帧格式：4 字节大端头长度 + JSON 头 + 可选二进制负载（长度写在头的 size 里）。
JSON 头里的 ch 字段区分通道：
    ctl     握手与心跳
    file    文件操作（请求带 id，对方用 re=id 回复）
    notify  变化通知（对方收到后回执，没回执的重连后重发）

谁来拨号：设备 ID 较小的一方主动连接，另一方只监听。双方都监听，所以哪边先启动都行。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import deque

from tsauth import Identity, Tailscale, authorize

PROTOCOL = "macwin-link/2"
MAX_HEADER = 1 << 20
MAX_PAYLOAD = 16 << 20
HEARTBEAT_SECONDS = 10
DEAD_AFTER_SECONDS = 35     # 这么久没收到任何帧就当断线
HANDSHAKE_TIMEOUT = 10
MAX_BACKOFF = 30

log = logging.getLogger("macwin_link")


class ProtocolError(Exception):
    pass


class RemoteError(Exception):
    """对方执行请求时出错。"""


# ---------------------------------------------------------------- 分帧

def encode_frame(header: dict, payload: bytes = b"") -> bytes:
    if payload:
        header = {**header, "size": len(payload)}
    h = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return len(h).to_bytes(4, "big") + h + payload


async def read_frame(reader: asyncio.StreamReader):
    n = int.from_bytes(await reader.readexactly(4), "big")
    if n > MAX_HEADER:
        raise ProtocolError(f"帧头过大：{n}")
    header = json.loads((await reader.readexactly(n)).decode("utf-8"))
    size = int(header.get("size", 0))
    if size > MAX_PAYLOAD:
        raise ProtocolError(f"负载过大：{size}")
    payload = await reader.readexactly(size) if size else b""
    return header, payload


# ---------------------------------------------------------------- 单条连接

class Peer:
    """一条已认证的连接。run() 在连接断开时返回。"""

    def __init__(self, reader, writer, who: dict, handlers: dict) -> None:
        self.reader, self.writer = reader, writer
        self.who = who
        self.handlers = handlers
        self.pending: dict = {}
        self.next_id = 1
        self.wlock = asyncio.Lock()
        self.last_rx = time.monotonic()
        self.rtt_ms = None
        self.closed = False

    async def send(self, header: dict, payload: bytes = b"") -> None:
        if self.closed:
            raise ConnectionError("连接已断开")
        async with self.wlock:
            self.writer.write(encode_frame(header, payload))
            await self.writer.drain()

    async def request(self, ch: str, op: str, args: dict = None, payload: bytes = b"", timeout: float = 60):
        rid = self.next_id
        self.next_id += 1
        fut = asyncio.get_running_loop().create_future()
        self.pending[rid] = fut
        try:
            await self.send({"ch": ch, "op": op, "id": rid, "args": args or {}}, payload)
            header, data = await asyncio.wait_for(fut, timeout)
        finally:
            self.pending.pop(rid, None)
        if not header.get("ok"):
            raise RemoteError(header.get("error", "对方出错"))
        return header.get("result"), data

    async def run(self) -> None:
        hb = asyncio.ensure_future(self._heartbeat())
        try:
            while True:
                header, payload = await read_frame(self.reader)
                self.last_rx = time.monotonic()
                if "re" in header:
                    fut = self.pending.get(header["re"])
                    if fut and not fut.done():
                        fut.set_result((header, payload))
                    continue
                ch = header.get("ch")
                if ch == "ctl":
                    await self._on_ctl(header)
                elif ch in self.handlers:
                    asyncio.ensure_future(self._serve(header, payload))
                else:
                    log.warning("未知通道：%s", ch)
        except (asyncio.IncompleteReadError, ConnectionError, OSError, ProtocolError, ValueError) as e:
            log.debug("连接读结束：%r", e)
        finally:
            hb.cancel()
            await self.close()

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        for fut in self.pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("连接已断开"))
        try:
            self.writer.close()
        except Exception:
            pass

    async def _on_ctl(self, header: dict) -> None:
        op = header.get("op")
        if op == "ping":
            await self.send({"ch": "ctl", "op": "pong", "t": header.get("t")})
        elif op == "pong" and header.get("t"):
            self.rtt_ms = round((time.time() - float(header["t"])) * 1000, 1)

    async def _heartbeat(self) -> None:
        try:
            while not self.closed:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                if time.monotonic() - self.last_rx > DEAD_AFTER_SECONDS:
                    log.warning("心跳超时，断开重连")
                    await self.close()
                    return
                await self.send({"ch": "ctl", "op": "ping", "t": time.time()})
        except (ConnectionError, OSError):
            await self.close()

    async def _serve(self, header: dict, payload: bytes) -> None:
        handler = self.handlers[header["ch"]]
        rid = header.get("id")
        try:
            result, out = await handler(header, payload)
            reply = {"re": rid, "ok": True, "result": result}
        except Exception as e:
            reply, out = {"re": rid, "ok": False, "error": f"{type(e).__name__}: {e}"}, b""
        if rid is None:
            return  # 单向消息不回复
        try:
            await self.send(reply, out or b"")
        except (ConnectionError, OSError):
            pass


async def handshake(reader, writer, me: Identity, expect_device: str) -> None:
    """双方互发 hello。对方自报的设备 ID 必须和 Tailscale 查到的一致。"""
    writer.write(encode_frame({"ch": "ctl", "op": "hello", "protocol": PROTOCOL,
                               "device_id": me.device_id, "name": me.name}))
    await writer.drain()
    header, _ = await asyncio.wait_for(read_frame(reader), HANDSHAKE_TIMEOUT)
    if header.get("op") != "hello":
        raise ProtocolError("对方没有发 hello")
    if header.get("protocol") != PROTOCOL:
        raise ProtocolError(f"协议版本不一致：{header.get('protocol')}")
    if header.get("device_id") != expect_device:
        raise ProtocolError(f"对方自称 {header.get('device_id')}，与 Tailscale 查到的 {expect_device} 不符")


# ---------------------------------------------------------------- 收到的通知

class EventLog:
    """对方推来的变化通知，按序号保存最近 1000 条，供本机命令行长轮询。线程安全。"""

    def __init__(self, maxlen: int = 1000) -> None:
        self.items = deque(maxlen=maxlen)
        self.seq = 0
        self.epoch = f"{time.time():.0f}"   # 服务每次启动不同；客户端带着旧 epoch 来就从头给
        self.cond = threading.Condition()

    def add(self, events: list) -> None:
        with self.cond:
            for e in events:
                self.seq += 1
                self.items.append({"seq": self.seq, **e})
            self.cond.notify_all()

    def since(self, seq: int, wait: float, epoch: str = None) -> dict:
        deadline = time.monotonic() + wait
        with self.cond:
            if seq < 0:          # -1 表示"从现在开始"
                return {"epoch": self.epoch, "seq": self.seq, "events": []}
            if epoch and epoch != self.epoch:
                seq = 0          # 服务重启过，序号重新计数
            while self.seq <= seq and time.monotonic() < deadline:
                self.cond.wait(deadline - time.monotonic())
            return {"epoch": self.epoch, "seq": self.seq, "events": [e for e in self.items if e["seq"] > seq]}


# ---------------------------------------------------------------- 连接管理

class Link:
    def __init__(self, cfg: dict, ts: Tailscale, me: Identity, files, watcher, events: EventLog,
                 on_state=None) -> None:
        self.cfg, self.ts, self.me = cfg, ts, me
        self.files, self.watcher, self.events = files, watcher, events
        self.on_state = on_state or (lambda: None)
        others = [d for d in cfg["allowed_devices"] if d != me.device_id]
        if len(others) != 1:
            raise SystemExit("allowed_devices 里除本机外应恰好有一台设备")
        self.peer_id = others[0]
        self.peer_label = cfg["allowed_devices"][self.peer_id]
        self.peer: Peer = None
        self.connected_since = None
        self.reconnects = 0
        self.last_error = None
        self.outbox: dict = {}   # 还没送出去的本机变化，按路径合并，断线期间也攒着
        self._flushing = False
        self.handlers = {"file": self._on_file, "notify": self._on_notify, "agent": self._on_agent}

    @property
    def dialer(self) -> bool:
        return self.me.device_id < self.peer_id

    async def start(self) -> None:
        await asyncio.start_server(self._on_accept, self.me.ip, self.cfg["port"])
        log.info("监听 %s:%s；本机%s", self.me.ip, self.cfg["port"],
                 "主动连接对方" if self.dialer else "等待对方连接")
        if self.dialer:
            asyncio.ensure_future(self._dial_loop())
        asyncio.ensure_future(self._watch_loop())

    # ------------------------------------------------ 建立连接

    async def _on_accept(self, reader, writer) -> None:
        ip = writer.get_extra_info("peername")[0]
        try:
            who = await asyncio.to_thread(authorize, self.ts, self.me, self.cfg["allowed_devices"], ip)
            if who["device_id"] == self.me.device_id:
                raise PermissionError("拒绝本机连自己")
            await handshake(reader, writer, self.me, who["device_id"])
        except Exception as e:
            log.warning("拒绝来自 %s 的连接：%s", ip, e)
            writer.close()
            return
        await self._run_peer(reader, writer, who)

    async def _dial_loop(self) -> None:
        delay = 1
        while True:
            try:
                await asyncio.to_thread(self.me.refresh)
                info = self.me.peers.get(self.peer_id)
                if not info or not info["ip"]:
                    raise ConnectionError("Tailscale 网络里找不到对方")
                if not info["online"]:
                    raise ConnectionError("Tailscale 显示对方离线")
                who = await asyncio.to_thread(authorize, self.ts, self.me, self.cfg["allowed_devices"], info["ip"])
                if who["device_id"] != self.peer_id:
                    raise PermissionError(f"地址 {info['ip']} 现在属于 {who['device_id']}")
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(info["ip"], self.cfg["port"]), 5)
                try:
                    await handshake(reader, writer, self.me, self.peer_id)
                except Exception:
                    writer.close()
                    raise
                delay = 1
                await self._run_peer(reader, writer, who)
            except Exception as e:
                msg = str(e) or type(e).__name__
                if msg != self.last_error:
                    log.warning("连不上 %s：%s（%s 秒后重试，之后最长每 %s 秒一次）",
                                self.peer_label, msg, delay, MAX_BACKOFF)
                self.last_error = msg
                self.on_state()
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_BACKOFF)

    async def _run_peer(self, reader, writer, who: dict) -> None:
        old = self.peer
        if old is not None:
            log.info("新连接替换旧连接")
            await old.close()
        p = Peer(reader, writer, who, self.handlers)
        self.peer = p
        self.connected_since = time.time()
        self.last_error = None
        self.reconnects += 1
        log.info("已连接 %s（第 %s 次）", self.peer_label, self.reconnects)
        self.on_state()
        asyncio.ensure_future(self._flush_outbox())
        await p.run()
        if self.peer is p:
            self.peer = None
            self.connected_since = None
            self.last_error = "连接断开"
            log.warning("与 %s 的连接断开", self.peer_label)
            self.on_state()

    # ------------------------------------------------ 文件通道

    async def call(self, op: str, args: dict, payload: bytes = b"", timeout: float = 120, ch: str = "file"):
        """本机发起的请求（文件操作或智能体任务），在对方那边执行。"""
        p = self.peer
        if p is None:
            raise ConnectionError(f"还没连上 {self.peer_label}")
        return await p.request(ch, op, args, payload, timeout)

    async def _on_file(self, header: dict, payload: bytes):
        args = header.get("args") or {}
        source = args.pop("_source", None)
        op = header.get("op")
        if op == "activity":   # 对方要看本机的操作记录（App 用来标出智能体做过的操作）
            act = getattr(self, "activity", None)
            return {"items": act.tail(int(args.get("n", 200))) if act else []}, b""
        try:
            result = await asyncio.to_thread(self.files.dispatch, op, args, payload)
        except Exception as e:
            self._record(source, op, args, ok=False, error=f"{type(e).__name__}: {e}")
            raise
        self._record(source, op, args)
        return result

    def _record(self, source, op, args, ok=True, error="") -> None:
        """对方发来的写操作记进操作记录（读操作太多，不记）。"""
        if op in ("list", "stat", "read", "roots", "watch", "activity") or (op == "write" and not args.get("final") and ok):
            return
        act = getattr(self, "activity", None)
        if act is not None:
            src = dict(source or {"kind": "human"})
            src["via"] = "peer"
            detail = {k: v for k, v in args.items() if k in ("path", "src", "dst", "if_version")}
            act.add(src, op, "self", detail, ok, error)

    # ------------------------------------------------ 智能体通道

    async def _on_agent(self, header: dict, payload: bytes):
        from agents import run_agent
        if not self.cfg.get("agents_enabled", True):
            raise PermissionError("本机关闭了智能体通道")
        args = header.get("args") or {}
        op = header.get("op")
        if op in ("start", "get", "cancel"):
            return await asyncio.to_thread(self._task_op, op, args), b""
        cwd = self.files.resolve(args.get("cwd", ""), write=True)
        limit = float(self.cfg.get("agent_timeout_seconds", 600))
        timeout = min(float(args.get("timeout", limit)), limit)
        log.info("对方让本机 %s 执行任务（目录 /%s）：%s", args.get("agent"),
                 self.files.relpath(cwd), (args.get("prompt") or "")[:80])
        result = await asyncio.to_thread(run_agent, args.get("agent"), args.get("prompt"), cwd, timeout)
        log.info("任务结束：%s，%s 秒", "成功" if result["ok"] else "失败", result["seconds"])
        return result, b""

    def _task_op(self, op: str, args: dict) -> dict:
        """后台任务：start 立即返回，get 查进度，cancel 取消。"""
        runner = self.runner
        if op == "get":
            return runner.public(args["task_id"])
        if op == "cancel":
            log.info("对方取消任务 %s", args["task_id"])
            return runner.cancel(args["task_id"])
        if args.get("delegated"):
            raise PermissionError("对方的这个智能体本身就是被委托的，不能再委托（防止两台电脑循环委托）")
        cwd = self.files.resolve(args.get("cwd", ""), write=True)
        limit = float(self.cfg.get("agent_timeout_seconds", 600))
        timeout = min(float(args.get("timeout", limit)), limit)
        log.info("对方派来任务 %s：%s（目录 /%s）：%s", args["task_id"], args.get("agent"),
                 self.files.relpath(cwd), (args.get("prompt") or "")[:80])
        rec = runner.start(args["task_id"], args.get("agent"), args.get("prompt"), cwd, timeout, args.get("_source"))
        act = getattr(self, "activity", None)
        if act is not None:
            act.add(dict(args.get("_source") or {}, via="peer"), "task_start", "self",
                    {"task_id": args["task_id"], "agent": args.get("agent"), "prompt": (args.get("prompt") or "")[:200]})
        return rec

    # ------------------------------------------------ 通知通道

    async def _on_notify(self, header: dict, payload: bytes):
        evs = header.get("args", {}).get("events", [])
        if evs:
            self.events.add(evs)
            for e in evs[:5]:
                log.info("对方变化：%s %s%s", e["kind"], e["path"], "（本机改的）" if e.get("by_peer") else "")
            if len(evs) > 5:
                log.info("……另有 %s 条", len(evs) - 5)
        return None, b""

    async def _watch_loop(self) -> None:
        interval = float(self.cfg.get("watch_interval_seconds", 1))
        while True:
            await asyncio.sleep(interval)
            try:
                for e in await asyncio.to_thread(self.watcher.poll):
                    self.outbox[e["path"]] = e
            except Exception:
                log.exception("扫描共享目录出错")
            if self.outbox and self.peer is not None:
                await self._flush_outbox()

    async def _flush_outbox(self) -> None:
        """发出攒着的变化，等对方确认收到才从 outbox 删掉。

        静默断线时 send 只是写进了系统缓冲区，并不代表对方收到，所以必须等回执。
        回执丢了会重发，对方可能收到重复通知（至少一次送达）。
        """
        if self._flushing:
            return
        p = self.peer
        if p is None or not self.outbox:
            return
        self._flushing = True
        try:
            batch = list(self.outbox.values())
            try:
                await p.request("notify", "changes", {"events": batch}, timeout=15)
            except (ConnectionError, OSError, asyncio.TimeoutError, RemoteError):
                return  # 留在 outbox，下次或重连后再发
            for e in batch:
                if self.outbox.get(e["path"]) is e:
                    del self.outbox[e["path"]]
        finally:
            self._flushing = False

    # ------------------------------------------------ 状态

    def state(self) -> dict:
        p = self.peer
        return {
            "self": {"device_id": self.me.device_id, "name": self.me.name, "ip": self.me.ip,
                     "shared_dir": str(self.files.root)},
            "peer": {"device_id": self.peer_id, "label": self.peer_label},
            "connected": p is not None,
            "connected_since": self.connected_since,
            "rtt_ms": p.rtt_ms if p else None,
            "role": "dialer" if self.dialer else "listener",
            "connections": self.reconnects,
            "last_error": self.last_error,
            "pending_notifications": len(self.outbox),
            "updated_at": time.time(),
        }
