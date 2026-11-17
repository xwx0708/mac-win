"""Mac 与 Windows 之间的后台互联服务（入口与命令行）。

两台电脑各跑一份 `serve`，经 Tailscale 保持一条长连接，里面分出两个通道：
    文件通道  在对方的共享目录里列目录、读写文件、建目录、移动、删除（删除=移进 .trash）
    通知通道  共享目录有变化时推给对方；断线期间的变化攒着，重连后补发
断线后自动重连。设备认证交给 Tailscale（whois 查设备 ID + 白名单），详见 README.md。

用法：
    python macwin_link.py serve                  后台服务本体（开机自启跑的就是它）
    python macwin_link.py status                 连接状态
    python macwin_link.py whoami                 本机的 Tailscale 设备 ID
    python macwin_link.py ls [对方路径]           列对方共享目录
    python macwin_link.py get <对方路径> [本地路径] 从对方共享目录下载
    python macwin_link.py put <本地路径> [对方路径] 上传到对方共享目录
    python macwin_link.py mkdir <对方路径>
    python macwin_link.py mv <对方路径> <对方新路径>
    python macwin_link.py rm <对方路径>           移进对方共享目录的 .trash，不真删
    python macwin_link.py watch                  持续显示对方共享目录的变化
    python macwin_link.py ask <claude|codex> "<任务>" [对方子目录]
                                                 让对方电脑上的终端版智能体在它的共享目录里执行任务

除 serve 和 whoami 外，命令都通过本机后台服务（127.0.0.1 上的控制端口）执行。
只用 Python 标准库，Windows 与 macOS 通用。
"""

from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from activity import ActivityLog  # noqa: E402
from conn import EventLog, Link, RemoteError  # noqa: E402
from tasks import (FAILED, SENDING, TERMINAL, UNCERTAIN, UNDELIVERED,  # noqa: E402
                   TaskRegistry, TaskRunner, new_task_id)
from files import CHUNK, FileService, Watcher  # noqa: E402
from scope import Scope  # noqa: E402
from tsauth import Identity, Tailscale  # noqa: E402

CONFIG_PATH = HERE / "config.json"
STATE_DIR = HERE / "state"
LOG_DIR = HERE / "logs"
STATUS_PATH = STATE_DIR / "status.json"

log = logging.getLogger("macwin_link")


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("port", 47110)
    cfg.setdefault("local_api_port", 47111)
    cfg.setdefault("watch_interval_seconds", 1)
    if not cfg.get("allowed_devices"):
        raise SystemExit("config.json 里 allowed_devices 不能为空")
    return cfg


def shared_dir_for(cfg: dict, device_id: str) -> Path:
    raw = (cfg.get("shared_dirs") or {}).get(device_id)
    if not raw:
        raise SystemExit(f"config.json 的 shared_dirs 里没有本机（{device_id}）的共享目录")
    return Path(os.path.expanduser(raw))


# ================================================================ 服务端

def setup_logging(to_file: bool) -> None:
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    if to_file:
        LOG_DIR.mkdir(exist_ok=True)
        h = logging.handlers.RotatingFileHandler(
            LOG_DIR / "link.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        h.setFormatter(fmt)
        log.addHandler(h)
    elif sys.stderr is not None:
        s = logging.StreamHandler()
        s.setFormatter(fmt)
        log.addHandler(s)


def write_status(state: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    tmp = STATUS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATUS_PATH)


def ascii_json(obj) -> str:
    """HTTP 头只能放 ASCII，中文路径用 \\u 转义。"""
    return json.dumps(obj, ensure_ascii=True, separators=(",", ":"))


class TaskAPI:
    """委托方的任务逻辑：派出任务、查询、取消。对方离线时如实报告，不假装成功。"""

    def __init__(self, link: Link, loop, registry: TaskRegistry) -> None:
        self.link, self.loop, self.reg = link, loop, registry

    def _peer(self, op: str, args: dict, timeout: float = 20):
        fut = asyncio.run_coroutine_threadsafe(self.link.call(op, args, b"", timeout=timeout, ch="agent"), self.loop)
        result, _ = fut.result(timeout=timeout + 5)
        return result

    def _merge(self, tid: str, remote: dict) -> dict:
        keep = ("status", "started_at", "ended_at", "exit_code", "output", "error", "seconds")
        return self.reg.update(tid, note="", last_known=remote.get("status"), **{k: remote[k] for k in keep if k in remote})

    def start(self, body: dict, source: dict, delegated: bool) -> dict:
        if delegated:
            raise PermissionError("你是被另一台电脑委托来执行任务的智能体，不能再委托任务（防止两台电脑循环委托）")
        agent = body.get("agent")
        if agent not in ("claude", "codex"):
            raise ValueError("agent 只能是 claude 或 codex")
        tid = new_task_id()
        timeout = float(body.get("timeout", 600))
        self.reg.add({"task_id": tid, "agent": agent, "prompt": body.get("prompt", ""), "cwd": body.get("cwd", ""),
                      "peer": self.link.peer_label, "status": SENDING, "created_at": time.time(),
                      "updated_at": time.time(), "source": source, "note": ""})
        try:
            remote = self._peer("start", {"task_id": tid, "agent": agent, "prompt": body.get("prompt", ""),
                                          "cwd": body.get("cwd", ""), "timeout": timeout, "_source": source})
        except ConnectionError as e:
            return self.reg.update(tid, status=UNDELIVERED, note=f"任务没有送出去：{e}（对方离线或长连接断开）")
        except (TimeoutError, asyncio.TimeoutError):
            return self.reg.update(tid, status=UNCERTAIN, note="任务已发出，但等对方确认时超时，不确定对方是否开始执行。稍后用 get_task 再查")
        except RemoteError as e:
            return self.reg.update(tid, status=FAILED, note="对方拒绝执行", error=str(e))
        rec = self._merge(tid, remote)
        if body.get("wait"):
            rec = self.wait(tid, timeout + 30)
        return rec

    def wait(self, tid: str, limit: float) -> dict:
        deadline = time.time() + limit
        rec = self.reg.get(tid)
        while rec["status"] not in TERMINAL and time.time() < deadline:
            time.sleep(2)
            rec = self.get(tid)
            if rec["status"] == UNCERTAIN:
                break
        if rec["status"] not in TERMINAL and rec["status"] != UNCERTAIN:
            rec = self.reg.update(tid, note="等待超时，任务可能还在运行，用 get_task 继续查")
        return rec

    def get(self, tid: str) -> dict:
        rec = self.reg.get(tid)
        if rec is None:
            raise KeyError(f"没有任务 {tid} 的记录")
        if rec["status"] in TERMINAL:
            return rec
        try:
            return self._merge(tid, self._peer("get", {"task_id": tid}))
        except ConnectionError:
            last = rec["status"] if rec["status"] != UNCERTAIN else (rec.get("last_known") or "未知")
            return self.reg.update(tid, status=UNCERTAIN, last_known=last if last != "未知" else rec.get("last_known"),
                                   note=f"对方离线，无法确认最新进度（最后已知：{last}）")
        except (TimeoutError, asyncio.TimeoutError):
            return self.reg.update(tid, status=UNCERTAIN, note="查询对方时超时，无法确认最新进度")
        except RemoteError as e:
            if "没有任务" in str(e):
                if rec["status"] in (SENDING, UNCERTAIN) and not rec.get("started_at"):
                    return self.reg.update(tid, status=UNDELIVERED, note="对方没有收到过这个任务")
                return self.reg.update(tid, status=UNCERTAIN, note="对方服务重启过，丢失了这个任务的记录，结果无法确认")
            raise

    def cancel(self, tid: str) -> dict:
        rec = self.reg.get(tid)
        if rec is None:
            raise KeyError(f"没有任务 {tid} 的记录")
        if rec["status"] in TERMINAL:
            return dict(rec, note=f"任务已经是「{rec['status']}」，不需要取消")
        try:
            return self._merge(tid, self._peer("cancel", {"task_id": tid}))
        except ConnectionError:
            return dict(rec, cancel="未送达", note="对方离线，取消请求没有送到，任务可能仍在对方电脑上运行")
        except (TimeoutError, asyncio.TimeoutError):
            return dict(rec, cancel="不确定", note="取消请求已发出，但对方没有确认，任务可能仍在运行")


def make_local_api(link: Link, loop: asyncio.AbstractEventLoop, events: EventLog,
                   tasks: TaskAPI = None, activity: ActivityLog = None):
    """本机控制接口，只监听 127.0.0.1，供命令行和本机其他程序调用。

    请求头（MCP 服务会带上，命令行不带）：
      X-Source      JSON，例如 {"kind":"agent","agent":"claude","session":"..."}；不带视为人工操作
      X-Target      /file 的执行位置：peer（默认，对方电脑）或 self（本机）
      X-Delegated   1 表示调用方本身是被委托的智能体，不允许它再委托任务
    """

    class Handler(BaseHTTPRequestHandler):
        def _source(self) -> dict:
            try:
                s = json.loads(self.headers.get("X-Source") or "null")
            except ValueError:
                s = None
            return s if isinstance(s, dict) else {"kind": "human"}

        def _body_json(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads((self.rfile.read(n) if n else b"{}").decode("utf-8") or "{}")

        def _task(self, fn) -> None:
            try:
                self._json(200, fn())
            except KeyError as e:
                self._json(404, {"error": str(e).strip("'\"")})
            except PermissionError as e:
                self._json(403, {"error": str(e)})
            except ValueError as e:
                self._json(400, {"error": str(e)})
            except RemoteError as e:
                self._json(502, {"error": str(e)})
            except Exception as e:
                self._json(500, {"error": f"{type(e).__name__}: {e}"})

        def _local_file(self, payload: bytes) -> None:
            op = self.headers["X-Op"]
            args = json.loads(self.headers.get("X-Args") or "{}")
            try:
                result, data = link.files.dispatch(op, args, payload)
            except Exception as e:
                if op not in ("list", "stat", "read", "roots", "watch", "activity"):
                    activity.add(self._source(), op, "self", args, False, f"{type(e).__name__}: {e}")
                self._json(502, {"error": f"{type(e).__name__}: {e}"})
                return
            if op not in ("list", "stat", "read", "roots", "watch", "activity") and not (op == "write" and not args.get("final")):
                activity.add(self._source(), op, "self", {k: v for k, v in args.items() if k in ("path", "src", "dst")})
            self._reply(200, data or b"", result=result)

        server_version = "macwin-link-local"
        sys_version = ""
        server_version = "macwin-link-local"
        sys_version = ""

        def _reply(self, code: int, body: bytes = b"", result=None, ctype="application/octet-stream"):
            # 请求带 X-Result-Body: 1、且没有二进制数据要回时，结果放进响应体（JSON）而不是 X-Result 响应头：
            # 结果大时（比如大目录的列表）响应头会超过客户端的长度上限
            if result is not None and not body and self.headers.get("X-Result-Body") == "1":
                body, ctype = json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8"
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Result-In-Body", "1")
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if result is not None:
                self.send_header("X-Result", ascii_json(result))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            self._reply(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                        ctype="application/json; charset=utf-8")

        def do_GET(self):  # noqa: N802
            url = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(url.query)
            if url.path == "/status":
                self._json(200, link.state())
            elif url.path == "/events":
                since = int(q.get("since", ["-1"])[0])
                wait = min(float(q.get("wait", ["25"])[0]), 60)
                self._json(200, events.since(since, wait, q.get("epoch", [None])[0]))
            elif url.path == "/activity":
                self._json(200, {"items": activity.tail(int(q.get("n", ["100"])[0]))})
            elif url.path == "/task":
                self._task(lambda: tasks.get(q.get("id", [""])[0]))
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path == "/task/start":
                body = self._body_json()
                src = self._source()
                detail = {"agent": body.get("agent"), "prompt": (body.get("prompt") or "")[:200]}

                def start():
                    try:
                        rec = tasks.start(body, src, self.headers.get("X-Delegated") == "1")
                    except Exception as e:
                        activity.add(src, "task_delegate", "peer", detail, False, str(e))
                        raise
                    activity.add(src, "task_delegate", "peer", dict(detail, task_id=rec["task_id"], status=rec["status"]),
                                 rec["status"] not in (UNDELIVERED, FAILED))
                    return rec
                self._task(start)
                return
            if self.path == "/task/cancel":
                body = self._body_json()
                activity.add(self._source(), "task_cancel", "peer", {"task_id": body.get("task_id")})
                self._task(lambda: tasks.cancel(body.get("task_id", "")))
                return
            if self.path not in ("/file", "/agent"):
                self._json(404, {"error": "not found"})
                return
            n = int(self.headers.get("Content-Length") or 0)
            payload = self.rfile.read(n) if n else b""
            if self.path == "/file" and self.headers.get("X-Target") == "self":
                self._local_file(payload)
                return
            try:
                if self.path == "/agent":   # 请求体是 JSON：{"agent","prompt","cwd","timeout"}
                    args = json.loads(payload.decode("utf-8"))
                    wait = float(args.get("timeout", 600)) + 30
                    coro = link.call("run", args, b"", timeout=wait, ch="agent")
                    payload = b""
                else:
                    wait = 180
                    args = json.loads(self.headers.get("X-Args") or "{}")
                    op = self.headers["X-Op"]
                    if self.headers.get("X-Source"):
                        args["_source"] = self._source()
                    if op not in ("list", "stat", "read", "roots", "watch", "activity") and not (op == "write" and not args.get("final")):
                        activity.add(self._source(), op, "peer", {k: v for k, v in args.items() if k in ("path", "src", "dst")})
                    coro = link.call(op, args, payload)
                fut = asyncio.run_coroutine_threadsafe(coro, loop)
                result, data = fut.result(timeout=wait + 10)
                if self.path == "/agent":
                    self._json(200, result)
                    return
            except ConnectionError as e:
                self._json(503, {"error": str(e)})
                return
            except RemoteError as e:
                self._json(502, {"error": str(e)})
                return
            except Exception as e:
                self._json(500, {"error": f"{type(e).__name__}: {e}"})
                return
            self._reply(200, data or b"", result=result)

        def log_message(self, fmt, *args):
            pass

    return Handler


def wait_for_tailscale(ts: Tailscale) -> Identity:
    delay = 5
    while True:
        try:
            return Identity(ts)
        except Exception as e:
            log.warning("等待 Tailscale：%s", e)
            time.sleep(delay)
            delay = min(delay * 2, 60)


async def serve_async(cfg: dict) -> None:
    ts = Tailscale()
    me = await asyncio.to_thread(wait_for_tailscale, ts)
    files = FileService(shared_dir_for(cfg, me.device_id), Scope((cfg.get("scope") or {}).get(me.device_id)))
    watcher = await asyncio.to_thread(Watcher, files)
    events = EventLog()

    link_holder = {}

    def on_state():
        try:
            write_status(link_holder["link"].state())
        except Exception:
            log.exception("写状态文件失败")

    link = Link(cfg, ts, me, files, watcher, events, on_state=on_state)
    link_holder["link"] = link
    link.runner = TaskRunner()
    link.activity = ActivityLog(STATE_DIR / "activity.jsonl", me.device_id)

    loop = asyncio.get_running_loop()
    task_api = TaskAPI(link, loop, TaskRegistry(STATE_DIR / "tasks.json"))
    api = ThreadingHTTPServer(("127.0.0.1", cfg["local_api_port"]),
                              make_local_api(link, loop, events, task_api, link.activity))
    api.daemon_threads = True
    threading.Thread(target=api.serve_forever, daemon=True).start()

    while True:
        try:
            await link.start()
            break
        except OSError as e:
            log.warning("无法监听 %s:%s（%s），30 秒后重试", me.ip, cfg["port"], e)
            await asyncio.sleep(30)
            await asyncio.to_thread(me.refresh)

    log.info("服务启动：%s（%s），共享目录 %s，本机控制端口 127.0.0.1:%s",
             me.name, me.device_id, files.root, cfg["local_api_port"])
    while True:
        on_state()
        await asyncio.sleep(30)


def cmd_serve(_args) -> int:
    setup_logging(to_file=True)
    cfg = load_config()
    try:
        asyncio.run(serve_async(cfg))
    except KeyboardInterrupt:
        pass
    log.info("服务停止")
    return 0


# ================================================================ 命令行

def api_url(path: str) -> str:
    return f"http://127.0.0.1:{load_config()['local_api_port']}{path}"


def api_get(path: str, timeout: float = 10) -> dict:
    with urllib.request.urlopen(api_url(path), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def remote(op: str, args: dict, payload: bytes = b""):
    req = urllib.request.Request(api_url("/file"), data=payload, method="POST",
                                 headers={"X-Op": op, "X-Args": ascii_json(args),
                                          "Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=200) as r:
            return json.loads(r.headers.get("X-Result") or "null"), r.read()
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("error")
        except Exception:
            msg = str(e)
        raise SystemExit(f"失败：{msg}") from None
    except urllib.error.URLError as e:
        raise SystemExit(f"本机后台服务没在运行（{e.reason}）") from None


def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def cmd_status(_args) -> int:
    try:
        s = api_get("/status")
    except urllib.error.URLError:
        print("本机后台服务没在运行")
        if STATUS_PATH.exists():
            s = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
            print(f"最后记录（{datetime.fromtimestamp(s['updated_at']):%m-%d %H:%M:%S}）：",
                  "已连接" if s["connected"] else f"未连接，{s.get('last_error')}")
        return 1
    me, peer = s["self"], s["peer"]
    print(f"本机：{me['name']}（{me['device_id']}）{me['ip']}")
    print(f"共享目录：{me['shared_dir']}")
    if s["connected"]:
        since = datetime.fromtimestamp(s["connected_since"]).strftime("%m-%d %H:%M:%S")
        rtt = f"，延迟 {s['rtt_ms']} ms" if s.get("rtt_ms") is not None else ""
        print(f"✓ 已连接 {peer['label']}，自 {since}{rtt}，累计连接 {s['connections']} 次")
    else:
        print(f"✗ 未连接 {peer['label']}：{s.get('last_error') or '等待对方连接'}")
    if s.get("pending_notifications"):
        print(f"  待发送的变化通知：{s['pending_notifications']} 条")
    return 0 if s["connected"] else 1


def cmd_whoami(_args) -> int:
    me = Identity(Tailscale())
    print(json.dumps({"device_id": me.device_id, "name": me.name, "ip": me.ip}, ensure_ascii=False, indent=2))
    return 0


def cmd_ls(args) -> int:
    res, _ = remote("list", {"path": args[0] if args else ""})
    print(f"对方 /{res['path']}")
    for e in res["entries"]:
        t = datetime.fromtimestamp(e["mtime"]).strftime("%m-%d %H:%M")
        size = "<目录>" if e["type"] == "dir" else fmt_size(e["size"])
        print(f"  {t}  {size:>10}  {e['name']}{'/' if e['type'] == 'dir' else ''}")
    return 0


def cmd_get(args) -> int:
    if not args:
        raise SystemExit("用法：get <对方路径> [本地路径]")
    src = args[0]
    dst = Path(args[1]) if len(args) > 1 else Path(Path(src).name)
    if dst.is_dir():
        dst = dst / Path(src).name
    info, _ = remote("stat", {"path": src})
    if not info.get("exists"):
        raise SystemExit(f"对方没有这个文件：{src}")
    if info["type"] == "dir":
        raise SystemExit("目前只能下载单个文件")
    tmp = dst.with_name(dst.name + ".part")
    t0, offset = time.time(), 0
    with open(tmp, "wb") as f:
        while True:
            res, data = remote("read", {"path": src, "offset": offset, "length": CHUNK})
            f.write(data)
            offset += len(data)
            if res["eof"] or not data:
                break
    os.replace(tmp, dst)
    os.utime(dst, (time.time(), info["mtime"]))
    print(f"已下载 {src} → {dst}（{fmt_size(offset)}，{time.time() - t0:.1f} 秒）")
    return 0


def cmd_put(args) -> int:
    if not args:
        raise SystemExit("用法：put <本地路径> [对方路径]")
    src = Path(args[0])
    if not src.is_file():
        raise SystemExit(f"本地没有这个文件：{src}")
    dst = args[1] if len(args) > 1 else src.name
    if dst.endswith("/"):
        dst += src.name
    upload_id = uuid.uuid4().hex[:12]
    size, mtime = src.stat().st_size, src.stat().st_mtime
    t0, offset = time.time(), 0
    with open(src, "rb") as f:
        while True:
            data = f.read(CHUNK)
            final = offset + len(data) >= size
            res, _ = remote("write", {"path": dst, "offset": offset, "upload_id": upload_id,
                                      "final": final, "mtime": mtime}, data)
            offset += len(data)
            if final:
                break
    print(f"已上传 {src} → 对方 /{res['path']}（{fmt_size(size)}，{time.time() - t0:.1f} 秒）")
    return 0


def cmd_mkdir(args) -> int:
    if not args:
        raise SystemExit("用法：mkdir <对方路径>")
    res, _ = remote("mkdir", {"path": args[0]})
    print(f"已建目录 对方 /{res['path']}")
    return 0


def cmd_mv(args) -> int:
    if len(args) != 2:
        raise SystemExit("用法：mv <对方路径> <对方新路径>")
    res, _ = remote("move", {"src": args[0], "dst": args[1]})
    print(f"已移动 对方 /{res['src']} → /{res['dst']}")
    return 0


def cmd_rm(args) -> int:
    if not args:
        raise SystemExit("用法：rm <对方路径>")
    res, _ = remote("delete", {"path": args[0]})
    print(f"已移进对方回收区 /{res['trashed_to']}")
    return 0


def cmd_watch(_args) -> int:
    names = {"created": "新增", "modified": "修改", "deleted": "删除"}
    print("显示对方共享目录的变化，Ctrl+C 退出")
    seq, epoch = -1, ""
    while True:
        try:
            r = api_get(f"/events?since={seq}&wait=25&epoch={epoch}", timeout=40)
        except (OSError, ValueError) as e:  # URLError、超时、连接被重置都算
            print(f"本机后台服务没响应（{e}），5 秒后重试")
            time.sleep(5)
            continue
        for e in r["events"]:
            t = datetime.fromtimestamp(e["time"]).strftime("%H:%M:%S")
            who = "（本机改的）" if e.get("by_peer") else ""
            print(f"{t}  {names.get(e['kind'], e['kind'])}  {e['path']}{'/' if e['type'] == 'dir' else ''}{who}")
        seq, epoch = r["seq"], r["epoch"]


def cmd_ask(args) -> int:
    """ask <claude|codex> "<任务>" [对方目录] [--timeout 秒]"""
    timeout = 600.0
    if "--timeout" in args:
        i = args.index("--timeout")
        timeout = float(args[i + 1])
        args = args[:i] + args[i + 2:]
    if len(args) < 2:
        raise SystemExit('用法：ask <claude|codex> "<任务>" [对方共享目录里的子目录] [--timeout 秒]')
    body = {"agent": args[0], "prompt": args[1], "cwd": args[2] if len(args) > 2 else "", "timeout": timeout}
    req = urllib.request.Request(api_url("/agent"), data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 method="POST", headers={"Content-Type": "application/json; charset=utf-8"})
    print(f"已发给对方的 {args[0]}，等待结果（最长 {timeout:.0f} 秒）……", flush=True)
    try:
        with urllib.request.urlopen(req, timeout=timeout + 60) as r:
            res = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("error")
        except Exception:
            msg = str(e)
        raise SystemExit(f"失败：{msg}") from None
    except urllib.error.URLError as e:
        raise SystemExit(f"本机后台服务没在运行（{e.reason}）") from None
    print(f"{'✓ 完成' if res['ok'] else '✗ 失败'}（{res['agent']}，{res['seconds']} 秒，退出码 {res['exit_code']}）")
    if res.get("output"):
        print("—— 输出 ——")
        print(res["output"])
    if res.get("error"):
        print("—— 错误 ——")
        print(res["error"])
    return 0 if res["ok"] else 1


COMMANDS = {
    "serve": cmd_serve, "status": cmd_status, "whoami": cmd_whoami, "ls": cmd_ls,
    "get": cmd_get, "put": cmd_put, "mkdir": cmd_mkdir, "mv": cmd_mv, "rm": cmd_rm,
    "watch": cmd_watch, "ask": cmd_ask,
}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd not in COMMANDS:
        print(__doc__)
        return 2
    try:
        return COMMANDS[cmd](sys.argv[2:])
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
