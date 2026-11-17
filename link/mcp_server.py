"""macwin MCP 服务：让 Claude Code / Codex 直接调用 Mac↔Windows 互联服务。

只是一层包装：收到工具调用后转发给本机核心服务的 HTTP 接口（127.0.0.1:47111），再把结果交回。
stdio 方式运行（每行一条 JSON-RPC 消息），只用 Python 标准库，Mac 和 Windows 用同一份。

每个请求都带 X-Source 头：{"kind":"agent","agent":"claude|codex","session":"<会话 ID>"}，
核心服务据此把操作记为"智能体操作"，写进 state/activity.jsonl，供 App 播放操作回放。

启动：python mcp_server.py --agent claude   （或 --agent codex）
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER_NAME = "macwin"
SERVER_VERSION = "1.0.0"
PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"]
CHUNK = 1 << 20
MAX_TEXT_READ = 256 * 1024          # read_file 一次默认最多返回这么多
LOCAL = "mac" if sys.platform == "darwin" else "windows"
DELEGATED = os.environ.get("MACWIN_DELEGATED") == "1"


def _port() -> int:
    try:
        return int(json.loads((HERE / "config.json").read_text(encoding="utf-8")).get("local_api_port", 47111))
    except Exception:
        return 47111


API = f"http://127.0.0.1:{_port()}"


# ================================================================ 来源标记

def _detect_agent() -> str:
    if "--agent" in sys.argv:
        return sys.argv[sys.argv.index("--agent") + 1]
    return "unknown"


SOURCE = {
    "kind": "agent",
    "agent": _detect_agent(),
    # 两边的 CLI 不一定把会话 ID 传给 MCP 子进程；拿不到时用本进程的 ID（一个会话启动一个 MCP 进程）
    "session": (os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CODEX_SESSION_ID")
                or os.environ.get("CODEX_THREAD_ID") or "mcp-" + uuid.uuid4().hex[:12]),
}
if DELEGATED:
    SOURCE["delegated_task"] = os.environ.get("MACWIN_TASK_ID", "")


def _hdr(extra: dict = None) -> dict:
    h = {"X-Source": json.dumps(SOURCE, ensure_ascii=True)}
    if DELEGATED:
        h["X-Delegated"] = "1"
    h.update(extra or {})
    return h


# ================================================================ 出错原因翻译成中文

class ToolError(Exception):
    pass


def _explain(code: int, msg: str) -> str:
    m = msg or ""
    if code == 503 or "还没连上" in m or "连接已断开" in m:
        return f"对方离线：两台电脑之间的长连接现在没有连上（{m}）。可以先用 peer_status 查看"
    if "VersionConflict" in m:
        return m.split(": ", 1)[-1]
    if "FileNotFoundError" in m or "No such file" in m:
        return "文件或目录不存在：" + m.split(": ", 1)[-1]
    if "FileExistsError" in m:
        return "目标已存在，不会覆盖：" + m.split(": ", 1)[-1]
    if "PermissionError" in m or code == 403:
        return "没有权限：" + m.split(": ", 1)[-1]
    if "NotADirectoryError" in m:
        return "不是目录：" + m.split(": ", 1)[-1]
    if "IsADirectoryError" in m:
        return "这是一个目录，不能当文件读写：" + m.split(": ", 1)[-1]
    if code == 404:
        return m or "找不到"
    return m or f"出错（HTTP {code}）"


def _http(method: str, path: str, body: bytes = None, headers: dict = None, timeout: float = 200):
    req = urllib.request.Request(API + path, data=body, method=method, headers=_hdr(headers))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            msg = json.loads(raw.decode("utf-8")).get("error", "")
        except Exception:
            msg = raw.decode("utf-8", "replace")
        raise ToolError(_explain(e.code, msg)) from None
    except urllib.error.URLError as e:
        raise ToolError(f"本机的互联服务没有运行（{e.reason}），请先启动 macwin_link.py serve") from None
    except TimeoutError:
        raise ToolError("等待本机互联服务回应超时") from None


def _json_call(method: str, path: str, obj: dict = None, timeout: float = 200) -> dict:
    body = json.dumps(obj or {}, ensure_ascii=False).encode("utf-8") if obj is not None else None
    _, _, raw = _http(method, path, body, {"Content-Type": "application/json; charset=utf-8"}, timeout)
    return json.loads(raw.decode("utf-8"))


def _target(device: str) -> str:
    d = (device or "").lower()
    if d not in ("mac", "windows"):
        raise ToolError("device 只能是 mac 或 windows")
    return "self" if d == LOCAL else "peer"


def _file(device: str, op: str, args: dict, payload: bytes = b""):
    # X-Result-Body：没有二进制数据要回时，结果放在响应体里，避免大结果撑爆响应头
    hdr = {"X-Op": op, "X-Args": json.dumps(args, ensure_ascii=True), "X-Target": _target(device),
           "Content-Type": "application/octet-stream", "X-Result-Body": "1"}
    _, h, data = _http("POST", "/file", payload, hdr)
    if h.get("X-Result-In-Body") == "1":
        return json.loads(data.decode("utf-8")), b""
    return json.loads(h.get("X-Result") or "null"), data


# ================================================================ 工具实现

LIST_DEFAULT = 300


def t_list_dir(a):
    limit = max(1, min(int(a.get("limit", LIST_DEFAULT)), 1000))
    res, _ = _file(a["device"], "list", {"path": a.get("path", ""), "offset": int(a.get("offset", 0)), "limit": limit})
    if res.get("next_offset") is not None:
        res["note"] = f"共 {res['total']} 项，这里是第 {res['offset'] + 1}–{res['next_offset']} 项。要看后面的，用 offset={res['next_offset']} 再调一次"
    return res


def t_stat(a):
    res, _ = _file(a["device"], "stat", {"path": a["path"]})
    return res


def t_read_file(a):
    offset = int(a.get("offset", 0))
    want = int(a.get("max_bytes", MAX_TEXT_READ))
    chunks, size, version, eof = [], 0, None, False
    while want > 0:
        res, data = _file(a["device"], "read", {"path": a["path"], "offset": offset, "length": min(want, CHUNK)})
        chunks.append(data)
        size, version, eof = res["size"], res.get("version"), res["eof"]
        offset += len(data)
        want -= len(data)
        if eof or not data:
            break
    raw = b"".join(chunks)
    out = {"path": a["path"], "size": size, "version": version, "offset": int(a.get("offset", 0)),
           "bytes_returned": len(raw), "complete": eof}
    if a.get("encoding") == "base64":
        out["content_base64"] = base64.b64encode(raw).decode()
    else:
        try:
            out["content"] = raw.decode("utf-8")
        except UnicodeDecodeError:
            out["content_base64"] = base64.b64encode(raw).decode()
            out["note"] = "不是 UTF-8 文本，已按 base64 返回"
    if not eof:
        out["note"] = (out.get("note", "") + f" 文件还没读完，下次从 offset={offset} 继续").strip()
    return out


def _upload(device: str, path: str, data: bytes, if_version=None, mtime=None) -> dict:
    upload_id = uuid.uuid4().hex[:12]
    offset, res = 0, None
    while True:
        part = data[offset:offset + CHUNK]
        final = offset + len(part) >= len(data)
        args = {"path": path, "offset": offset, "upload_id": upload_id, "final": final}
        if if_version is not None:
            args["if_version"] = if_version
        if mtime:
            args["mtime"] = mtime
        res, _ = _file(device, "write", args, part)
        offset += len(part)
        if final:
            return res


def t_write_file(a):
    if "content_base64" in a:
        data = base64.b64decode(a["content_base64"])
    else:
        data = (a.get("content") or "").encode("utf-8")
    res = _upload(a["device"], a["path"], data, a.get("if_version"))
    return {"written": True, **res}


def _transfer(src_dev, src, dst_dev, dst) -> dict:
    """跨设备复制单个文件：从源读出，分块写到目标。目标已存在就报错，不覆盖。"""
    info, _ = _file(src_dev, "stat", {"path": src})
    if not info.get("exists"):
        raise ToolError(f"文件或目录不存在：{src_dev} 上的 {src}")
    if info["type"] == "dir":
        raise ToolError("跨设备目前只能传单个文件，不能传整个文件夹")
    buf, offset = bytearray(), 0
    while True:
        res, data = _file(src_dev, "read", {"path": src, "offset": offset, "length": CHUNK})
        buf += data
        offset += len(data)
        if res["eof"] or not data:
            break
    out = _upload(dst_dev, dst, bytes(buf), if_version="new", mtime=info.get("mtime"))
    return {"bytes": len(buf), **out}


def t_copy(a):
    dst_dev = a.get("dest_device") or a["device"]
    if dst_dev.lower() == a["device"].lower():
        res, _ = _file(a["device"], "copy", {"src": a["src"], "dst": a["dst"]})
        return {"copied": True, "device": a["device"], **res}
    res = _transfer(a["device"], a["src"], dst_dev, a["dst"])
    return {"copied": True, "from": f"{a['device']}:{a['src']}", "to": f"{dst_dev}:{a['dst']}", **res}


def t_move(a):
    dst_dev = a.get("dest_device") or a["device"]
    if dst_dev.lower() == a["device"].lower():
        res, _ = _file(a["device"], "move", {"src": a["src"], "dst": a["dst"]})
        return {"moved": True, "device": a["device"], **res}
    res = _transfer(a["device"], a["src"], dst_dev, a["dst"])
    try:   # 目标写好之后，源文件移进源设备的回收区（不永久删除）
        trash, _ = _file(a["device"], "delete", {"path": a["src"]})
    except ToolError as e:
        return {"moved": False, "copied": True, "to": f"{dst_dev}:{a['dst']}",
                "note": f"已复制到目标，但源文件没能移进回收区：{e}。现在两边各有一份"}
    return {"moved": True, "from": f"{a['device']}:{a['src']}", "to": f"{dst_dev}:{a['dst']}",
            "source_trashed_to": trash["trashed_to"], **res}


def t_mkdir(a):
    res, _ = _file(a["device"], "mkdir", {"path": a["path"]})
    return {"created": True, **res}


def t_delete(a):
    res, _ = _file(a["device"], "delete", {"path": a["path"]})
    return {"deleted": "已移进回收区，可以恢复", **res}


def t_list_roots(a):
    res, _ = _file(a["device"], "roots", {})
    return res


def t_peer_status(_a):
    s = _json_call("GET", "/status", None, timeout=10)
    return {"this_device": LOCAL, "peer": s["peer"]["label"], "online": s["connected"],
            "latency_ms": s.get("rtt_ms"), "connected_since": s.get("connected_since"),
            "last_error": s.get("last_error"), "pending_notifications": s.get("pending_notifications")}


def t_delegate_task(a):
    if DELEGATED:
        raise ToolError("你是被另一台电脑委托来执行任务的智能体，不能再委托任务（防止两台电脑循环委托）。请自己完成")
    wait = bool(a.get("wait", True))
    timeout = float(a.get("timeout_seconds", 600))
    body = {"agent": a["agent"], "prompt": a["prompt"], "cwd": a.get("cwd", ""), "timeout": timeout, "wait": wait}
    return _json_call("POST", "/task/start", body, timeout=(timeout + 90) if wait else 60)


def t_get_task(a):
    return _json_call("GET", "/task?id=" + urllib.parse.quote(a["task_id"]), None, timeout=60)


def t_cancel_task(a):
    return _json_call("POST", "/task/cancel", {"task_id": a["task_id"]}, timeout=60)


# ================================================================ 工具描述

DEV = {"type": "string", "enum": ["mac", "windows"],
       "description": f"在哪台电脑上操作：mac 或 windows。本机是 {LOCAL}。"}
REL = ("路径用 / 分隔，两种写法：绝对路径（Windows 如 \"E:/工作区/x.txt\"，Mac 如 \"/Users/wx/Desktop/x.txt\"），"
       "或相对该电脑共享目录的路径（Windows 共享目录 E:/收件箱/Mac互传，Mac 是 ~/Windows互传）。"
       "开放范围：Windows 的 C、D、E 盘，Mac 的整个磁盘；系统和程序目录只读；E:/隐私数据、密钥、钥匙串等永远不开放。"
       "不知道有哪些盘和常用文件夹时先调 list_roots。")

TOOLS = [
    ("list_dir", t_list_dir,
     "列出某台电脑上一个文件夹的内容。" + REL +
     "返回 {path, abs, writable, entries:[{name, type: file|dir, size, mtime, version, hidden}]}。"
     "version 是文件版本号，写回文件时可用来检测冲突；hidden 表示系统里标成隐藏的；writable=false 表示这里只读。"
     "大目录分页返回：带 total 和 next_offset，next_offset 不为空时用它作 offset 再调一次取下一页。",
     {"device": DEV, "path": {"type": "string", "description": "要列的文件夹，空字符串表示共享目录本身", "default": ""},
      "offset": {"type": "integer", "default": 0, "description": "从第几项开始（分页）"},
      "limit": {"type": "integer", "default": 300, "description": "最多返回多少项，上限 1000"}},
     ["device"]),
    ("stat", t_stat,
     "查看一个文件或文件夹的信息。" + REL + "返回 {exists, name, type, size, mtime, version}；不存在时只返回 {exists:false}。",
     {"device": DEV, "path": {"type": "string"}}, ["device", "path"]),
    ("read_file", t_read_file,
     "读取文件内容。" + REL + "UTF-8 文本放在 content 里，其他内容放在 content_base64。"
     "返回里的 version 是读取时的版本号，之后想改这个文件，把它传给 write_file 的 if_version，就能发现别人在中间改过。"
     "大文件用 offset 和 max_bytes 分段读（默认最多 256KB），complete=false 表示还没读完。",
     {"device": DEV, "path": {"type": "string"},
      "offset": {"type": "integer", "default": 0, "description": "从第几个字节开始读"},
      "max_bytes": {"type": "integer", "default": MAX_TEXT_READ, "description": "最多读多少字节"},
      "encoding": {"type": "string", "enum": ["text", "base64"], "default": "text"}},
     ["device", "path"]),
    ("write_file", t_write_file,
     "写入（新建或整个覆盖）一个文件，自动建上级目录。" + REL +
     "冲突检测：if_version 传 read_file/stat/list_dir 拿到的版本号，如果文件在这期间被改过，就不写入并报错“文件已被修改”；"
     "传 \"new\" 表示只允许新建，文件已存在就报错；不传则直接覆盖。返回 {written, path, size, version}。",
     {"device": DEV, "path": {"type": "string"},
      "content": {"type": "string", "description": "UTF-8 文本内容"},
      "content_base64": {"type": "string", "description": "二进制内容（base64），和 content 二选一"},
      "if_version": {"type": "string", "description": "期望的当前版本号，或 \"new\""}},
     ["device", "path"]),
    ("move", t_move,
     "移动或重命名。" + REL + "同一台电脑内可移动文件或文件夹；dest_device 和 device 不同时是跨设备移动"
     "（目前只支持单个文件）：先把文件完整写到目标电脑，成功后再把源文件移进源电脑的回收区。目标已存在时报错，不覆盖。",
     {"device": DEV, "src": {"type": "string"}, "dst": {"type": "string"},
      "dest_device": {"type": "string", "enum": ["mac", "windows"], "description": "目标在哪台电脑，默认和 device 相同"}},
     ["device", "src", "dst"]),
    ("copy", t_copy,
     "复制文件或文件夹。" + REL + "dest_device 和 device 不同时是跨设备复制（目前只支持单个文件）。目标已存在时报错，不覆盖。",
     {"device": DEV, "src": {"type": "string"}, "dst": {"type": "string"},
      "dest_device": {"type": "string", "enum": ["mac", "windows"], "description": "目标在哪台电脑，默认和 device 相同"}},
     ["device", "src", "dst"]),
    ("mkdir", t_mkdir, "新建文件夹（含上级）。" + REL + "已存在也算成功。",
     {"device": DEV, "path": {"type": "string"}}, ["device", "path"]),
    ("delete", t_delete,
     "删除文件或文件夹，只会进回收站，可以恢复，不提供永久删除：共享目录里的移进共享目录下的 .trash（文件名前加时间），"
     "其他位置的移进系统回收站（Windows 回收站 / Mac 废纸篓）。不能删整个盘、用户主目录、共享目录本身。" + REL +
     "返回 {trashed_to}。",
     {"device": DEV, "path": {"type": "string"}}, ["device", "path"]),
    ("list_roots", t_list_roots,
     "列出某台电脑开放了哪些盘和常用位置。返回 {platform, home, drives:[{path, label, writable, total, free}], "
     "places:[{name, path}]（桌面、文档、下载、互传等的实际路径）, deny（永远不开放的位置）, writable（可写范围）}。"
     "浏览另一台电脑的文件前先调这个，就知道从哪里开始。",
     {"device": DEV}, ["device"]),
    ("peer_status", t_peer_status,
     "查看另一台电脑是否在线、延迟多少。返回 {this_device, peer, online, latency_ms, connected_since, last_error}。"
     "对另一台电脑做任何操作前不确定它在不在线时先调这个。", {}, []),
    ("delegate_task", t_delegate_task,
     "把一个任务派给另一台电脑上的智能体（Claude Code 或 Codex）执行，它相当于你在那台电脑上的子 agent。"
     "它在对方共享目录（或 cwd 指定的子目录）里工作，能读写那里的文件、在那台电脑上执行命令。"
     "prompt 要写完整，对方看不到你的对话上下文。wait=true 等它做完再返回结果；wait=false 立即返回 task_id，之后用 get_task 查。"
     "返回 {task_id, status, output, error, seconds, note}。status 取值：运行中、完成、失败、超时、已取消、"
     "未送达（对方离线，任务没送出去）、不确定（送出后失去联系，无法确认对方是否在执行）。"
     "被委托执行任务的智能体不能再调用本工具。",
     {"agent": {"type": "string", "enum": ["claude", "codex"], "description": "用对方电脑上的哪个智能体"},
      "prompt": {"type": "string", "description": "完整的任务说明"},
      "cwd": {"type": "string", "default": "", "description": "对方电脑上的工作目录：绝对路径，或相对对方共享目录的路径；默认是对方共享目录。必须在对方的可写范围内"},
      "wait": {"type": "boolean", "default": True},
      "timeout_seconds": {"type": "number", "default": 600, "description": "最长运行时间，上限 600 秒"}},
     ["agent", "prompt"]),
    ("get_task", t_get_task,
     "查询 delegate_task 派出的任务的进度和结果。返回内容同 delegate_task。对方离线时 status 会是“不确定”，并在 note 里写明最后已知的状态。",
     {"task_id": {"type": "string"}}, ["task_id"]),
    ("cancel_task", t_cancel_task,
     "取消一个正在运行的委托任务（结束对方电脑上的智能体进程）。对方离线时取消请求送不到，会在 cancel/note 里如实说明。",
     {"task_id": {"type": "string"}}, ["task_id"]),
]
IMPL = {name: fn for name, fn, *_ in TOOLS}


def tool_list() -> list:
    out = []
    for name, _fn, desc, props, req in TOOLS:
        if DELEGATED and name == "delegate_task":
            continue   # 被委托的智能体看不到委托工具
        out.append({"name": name, "description": desc,
                    "inputSchema": {"type": "object", "properties": props, "required": req, "additionalProperties": False}})
    return out


# ================================================================ JSON-RPC over stdio

def summarize(name: str, res) -> str:
    return json.dumps(res, ensure_ascii=False, indent=1)


def handle(msg: dict):
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        want = params.get("protocolVersion")
        client = (params.get("clientInfo") or {}).get("name", "")
        if SOURCE["agent"] == "unknown" and client:
            SOURCE["agent"] = "claude" if "claude" in client.lower() else "codex" if "codex" in client.lower() else client
        return {"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": "Mac↔Windows 互联服务。操作两台电脑共享目录里的文件时优先用这些工具，不要绕过它们直接改文件；"
                                "把任务交给另一台电脑的智能体时用 delegate_task。"}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": tool_list()}
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        fn = IMPL.get(name)
        if fn is None or (DELEGATED and name == "delegate_task"):
            if name == "delegate_task":
                return {"content": [{"type": "text", "text": "被委托执行任务的智能体不能再委托任务（防止两台电脑循环委托）。"}],
                        "isError": True}
            raise LookupError(f"没有这个工具：{name}")
        try:
            res = fn(args)
            return {"content": [{"type": "text", "text": summarize(name, res)}], "isError": False}
        except ToolError as e:
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}
        except KeyError as e:
            return {"content": [{"type": "text", "text": f"缺少参数：{e}"}], "isError": True}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"出错：{type(e).__name__}: {e}"}], "isError": True}
    if mid is None:   # 通知（如 notifications/initialized），不需要回复
        return None
    raise LookupError(f"不支持的方法：{method}")


def main() -> None:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line.decode("utf-8"))
        except ValueError:
            continue
        if "method" not in msg:   # 客户端发来的回复，忽略
            continue
        try:
            result = handle(msg)
            if msg.get("id") is None:
                continue
            reply = {"jsonrpc": "2.0", "id": msg["id"], "result": result}
        except LookupError as e:
            if msg.get("id") is None:
                continue
            reply = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": str(e)}}
        except Exception as e:
            if msg.get("id") is None:
                continue
            reply = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}}
        stdout.write((json.dumps(reply, ensure_ascii=False) + "\n").encode("utf-8"))
        stdout.flush()


if __name__ == "__main__":
    main()
