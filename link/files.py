"""文件通道：对方（以及本机的 MCP / App）能操作本机的哪些文件、怎么操作；通知通道的变化检测。

路径有两种写法：
  相对路径  如 "测试/a.txt"，相对本机共享目录（老写法，保持不变）
  绝对路径  如 "E:/工作区/x.txt"、"/Users/wx/Desktop"，可以是开放范围内的任何位置（见 scope.py）

删除不会真删：共享目录里的移进共享目录下的 .trash；其他位置的移进系统回收站（Windows 回收站 / Mac 废纸篓）。

变化检测：共享目录整个递归扫描；其他位置只扫描对方订阅了的目录（op_watch，不递归），
订阅超时不续就自动取消。这样对方开着哪个文件夹，哪个文件夹的变化就会被推过去。
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from scope import Scope, is_absolute, posix

CHUNK = 1 << 20          # 单次读写最多 1 MiB，大文件分块传，不会堵住通知
LIST_PAGE_MAX = 1000     # 列目录分页时一页最多这么多项
TRASH = ".trash"
PART_SUFFIX = ".part"    # 上传中的临时文件
REMOTE_ECHO_SECONDS = 5  # 对方刚写过的路径，本地检测到变化时标成"对方改的"
WATCH_TTL = 120          # 目录订阅默认 2 分钟，对方要定时续
MAX_WATCH_DIRS = 32
MAX_WATCH_ENTRIES = 5000  # 单个订阅目录超过这么多项就不再逐项比较


class VersionConflict(Exception):
    """写入时发现文件版本和调用方读到的不一致。"""


def version_of(st) -> str:
    """文件版本号：修改时间（纳秒）+ 大小。内容一变，两者至少有一个会变。"""
    return f"{st.st_mtime_ns:x}-{st.st_size:x}"


def _is_hidden_internal(rel: str) -> bool:
    first = rel.split("/", 1)[0]
    return first == TRASH or rel.endswith(PART_SUFFIX)


def move_to_system_trash(p: Path) -> str:
    """移进系统回收站，返回说明。失败就抛异常，绝不退化成永久删除。"""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                        ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
        FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
        op = SHFILEOPSTRUCTW(None, FO_DELETE, str(p) + "\0", None,
                             FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI, False, None, None)
        rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if rc != 0 or op.fAnyOperationsAborted or p.exists():
            raise OSError(f"移进回收站失败（代码 {rc}），文件没有动")
        return "Windows 回收站"
    trash = Path.home() / ".Trash"
    target = trash / p.name
    if target.exists():
        target = trash / f"{p.stem} {datetime.now():%H.%M.%S}{p.suffix}"
    shutil.move(str(p), str(target))
    return "废纸篓"


class FileService:
    def __init__(self, root: Path, scope: Scope = None) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.scope = scope or Scope()
        self._remote_touched: dict = {}
        self._lock = threading.Lock()
        self.watch_dirs: dict = {}   # 解析后的目录 → 到期时间
        self.baselines: dict = {}    # 刚订阅的目录 → 订阅时的快照

    # ------------------------------------------------------------ 路径

    def resolve(self, rel: str, write: bool = False) -> Path:
        raw = (rel or "").replace("\\", "/")
        if is_absolute(raw):
            if len(raw) == 2 and raw[1] == ":":
                raw += "/"
            if any(part == ".." for part in raw.split("/")):
                raise PermissionError(f"路径不允许：{rel}")
            p = Path(raw).resolve()
        else:
            parts = [x for x in raw.strip("/").split("/") if x not in ("", ".")]
            if any(x == ".." for x in parts):
                raise PermissionError(f"路径不允许：{rel}")
            p = (self.root.joinpath(*parts)).resolve()
            if p != self.root and self.root not in p.parents:
                raise PermissionError(f"路径跳出了共享目录：{rel}")
        self.scope.check(p, write, rel or "（共享目录）")
        return p

    def in_share(self, p: Path) -> bool:
        return p == self.root or self.root in p.parents

    def relpath(self, p: Path) -> str:
        """共享目录里的返回相对路径（老格式），其他位置返回绝对路径。"""
        if self.in_share(p):
            return p.relative_to(self.root).as_posix()
        return posix(p)

    def _touched(self, *paths: Path) -> None:
        now = time.monotonic()
        with self._lock:
            for p in paths:
                self._remote_touched[self.relpath(p)] = now

    def touched_by_remote(self, rel: str) -> bool:
        with self._lock:
            t = self._remote_touched.get(rel)
        return t is not None and time.monotonic() - t < REMOTE_ECHO_SECONDS

    def hidden(self, p: Path) -> bool:
        """列目录和变化检测时不显示的：禁区、上传临时文件、共享目录的回收区。"""
        if p.name.endswith(PART_SUFFIX) or self.scope.denied(p):
            return True
        return self.in_share(p) and _is_hidden_internal(self.relpath(p))

    # ------------------------------------------------------------ 操作

    @staticmethod
    def _entry(p: Path) -> dict:
        st = p.stat()
        is_dir = p.is_dir()
        e = {"name": p.name, "type": "dir" if is_dir else "file",
             "size": 0 if is_dir else st.st_size, "mtime": st.st_mtime}
        if not is_dir:
            e["version"] = version_of(st)
        if p.is_symlink():
            e["link"] = True
        # 系统里标成隐藏的（Windows 的隐藏/系统属性，Mac 的点开头或 hidden 标记），由界面决定显不显示
        attrs = getattr(st, "st_file_attributes", 0)
        if attrs & 0x6 or p.name.startswith(".") or getattr(st, "st_flags", 0) & 0x8000:
            e["hidden"] = True
        return e

    def _check_version(self, p: Path, want, rel: str) -> None:
        """if_version：None 不检查；"new" 要求文件还不存在；其他值要求和当前版本号一致。"""
        if want is None:
            return
        if want == "new":
            if p.exists():
                raise VersionConflict(f"文件已存在：{rel}（要求只新建，但这台电脑上已有同名文件）")
            return
        if not p.exists():
            raise VersionConflict(f"文件已被删除或移走：{rel}")
        cur = version_of(p.stat())
        if cur != want:
            raise VersionConflict(f"文件已被修改：{rel}（你读到的版本 {want}，现在是 {cur}）")

    def dispatch(self, op: str, args: dict, payload: bytes):
        fn = getattr(self, "op_" + op, None)
        if fn is None:
            raise ValueError(f"未知的文件操作：{op}")
        return fn(args, payload)

    def op_roots(self, args, _):
        """本机开放的盘、常用位置、禁区和可写范围。"""
        return self.scope.locations(self.root), b""

    def op_list(self, args, _):
        d = self.resolve(args.get("path", ""))
        if not d.is_dir():
            raise NotADirectoryError(f"不是目录：{args.get('path', '')}")
        items, skipped = [], 0
        try:
            children = list(d.iterdir())
        except PermissionError:
            raise PermissionError(f"系统不允许读取这个目录：{args.get('path', '')}（Mac 上可能需要给 Python 完全磁盘访问权限）")
        visible = [p for p in sorted(children, key=lambda x: (not _safe_isdir(x), x.name.lower())) if not self.hidden(p)]
        # 分页（可选）：带 limit 时只返回 [offset, offset+limit) 这一页，并给出 total 和 next_offset。
        # 不带 limit 时和以前一样返回全部，老的调用方不受影响。大目录请分页，否则一条消息可能装不下。
        page = visible
        offset = 0
        if args.get("limit") is not None:
            offset = max(0, int(args.get("offset", 0)))
            limit = max(1, min(int(args["limit"]), LIST_PAGE_MAX))
            page = visible[offset:offset + limit]
        for p in page:
            try:
                items.append(self._entry(p))
            except OSError:
                skipped += 1
        out = {"path": self.relpath(d), "abs": posix(d), "writable": self.scope.can_write(d), "entries": items}
        if args.get("limit") is not None:
            end = offset + len(page)
            out.update(total=len(visible), offset=offset, next_offset=end if end < len(visible) else None)
        if skipped:
            out["skipped"] = skipped
        return out, b""

    def op_stat(self, args, _):
        p = self.resolve(args["path"])
        if not p.exists():
            return {"exists": False}, b""
        return {"exists": True, "abs": posix(p), "writable": self.scope.can_write(p), **self._entry(p)}, b""

    def op_read(self, args, _):
        p = self.resolve(args["path"])
        offset = int(args.get("offset", 0))
        length = min(int(args.get("length", CHUNK)), CHUNK)
        with open(p, "rb") as f:
            st = os.fstat(f.fileno())
            f.seek(offset)
            data = f.read(length)
        return {"size": st.st_size, "offset": offset, "eof": offset + len(data) >= st.st_size,
                "version": version_of(st)}, data

    def op_write(self, args, payload):
        """分块上传：先写进同目录的临时文件，最后一块 final=true 时原子替换成目标文件。"""
        p = self.resolve(args["path"], write=True)
        upload = "".join(c for c in str(args.get("upload_id", "x")) if c.isalnum())[:32] or "x"
        tmp = p.with_name(f".{p.name}.{upload}{PART_SUFFIX}")
        offset = int(args.get("offset", 0))
        if offset == 0:   # 第一块就检查版本，省得传完才发现冲突
            self._check_version(p, args.get("if_version"), args["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "r+b" if offset and tmp.exists() else "wb") as f:
            f.seek(offset)
            f.write(payload)
        if args.get("final"):
            if p.is_dir():
                tmp.unlink(missing_ok=True)
                raise IsADirectoryError(f"目标是目录：{args['path']}")
            try:   # 替换前再查一次：传输期间可能有人改了
                self._check_version(p, args.get("if_version"), args["path"])
            except VersionConflict:
                tmp.unlink(missing_ok=True)
                raise
            os.replace(tmp, p)
            if args.get("mtime"):
                os.utime(p, (time.time(), float(args["mtime"])))
            self._touched(p)
            return {"path": self.relpath(p), "size": p.stat().st_size, "version": version_of(p.stat())}, b""
        return {"received": offset + len(payload)}, b""

    def op_mkdir(self, args, _):
        p = self.resolve(args["path"], write=True)
        p.mkdir(parents=True, exist_ok=True)
        self._touched(p)
        return {"path": self.relpath(p)}, b""

    def _protect(self, p: Path, what: str) -> None:
        if p == self.root:
            raise PermissionError(f"不能{what}共享目录本身")
        if any(p == r for r in self.scope.roots):
            raise PermissionError(f"不能{what}整个磁盘")
        if p == Path.home().resolve():
            raise PermissionError(f"不能{what}用户主目录本身")

    def op_move(self, args, _):
        src, dst = self.resolve(args["src"], write=True), self.resolve(args["dst"], write=True)
        self._protect(src, "移动")
        if not src.exists():
            raise FileNotFoundError(f"不存在：{args['src']}")
        if dst.exists():
            raise FileExistsError(f"目标已存在：{args['dst']}")
        if src.is_dir() and src in dst.parents:
            raise PermissionError("不能把文件夹移进它自己里面")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        self._touched(src, dst)
        return {"src": self.relpath(src), "dst": self.relpath(dst)}, b""

    def op_copy(self, args, _):
        src, dst = self.resolve(args["src"]), self.resolve(args["dst"], write=True)
        if not src.exists():
            raise FileNotFoundError(f"不存在：{args['src']}")
        if dst.exists():
            raise FileExistsError(f"目标已存在：{args['dst']}")
        if src == self.root or self.root / TRASH in dst.parents:
            raise PermissionError("不能复制共享目录本身，也不能复制进回收区")
        if src.is_dir() and (dst == src or src in dst.parents):
            raise PermissionError("不能把文件夹复制进它自己里面")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():   # 文件夹里的禁区不复制
            shutil.copytree(src, dst, ignore=lambda d, names: [n for n in names if self.scope.denied(Path(d) / n)])
        else:
            shutil.copy2(src, dst)
        self._touched(dst)
        return {"src": self.relpath(src), "dst": self.relpath(dst)}, b""

    def op_delete(self, args, _):
        """不真删：共享目录里的移进 .trash（文件名前加时间），其他位置的移进系统回收站。"""
        p = self.resolve(args["path"], write=True)
        self._protect(p, "删除")
        if not p.exists():
            raise FileNotFoundError(f"不存在：{args['path']}")
        if self.in_share(p):
            trash = self.root / TRASH
            trash.mkdir(exist_ok=True)
            target = trash / f"{datetime.now():%Y%m%d-%H%M%S}_{p.name}"
            shutil.move(str(p), str(target))
            self._touched(p)
            return {"trashed_to": self.relpath(target)}, b""
        where = move_to_system_trash(p)
        self._touched(p)
        return {"trashed_to": where}, b""

    def op_watch(self, args, _):
        """订阅目录变化（不递归）。paths 是完整的订阅列表，会替换上一次的；ttl 秒内不续就失效。"""
        ttl = min(float(args.get("ttl", WATCH_TTL)), 600)
        new, errors = {}, {}
        for raw in (args.get("paths") or [])[:MAX_WATCH_DIRS]:
            try:
                d = self.resolve(raw)
                if not d.is_dir():
                    raise NotADirectoryError("不是目录")
                if not self.in_share(d):   # 共享目录本来就整个在监视
                    new[d] = time.monotonic() + ttl
            except Exception as e:
                errors[raw] = str(e)
        with self._lock:
            fresh = [d for d in new if d not in self.watch_dirs]
            self.watch_dirs = new
        for d in fresh:   # 新订阅的目录立刻建立基准，订阅之后马上发生的变化也能报出来
            snap = self.shallow(d)
            with self._lock:
                self.baselines[posix(d)] = snap
        return {"watching": [self.relpath(d) for d in new], "ttl": ttl, "errors": errors}, b""

    def shallow(self, d: Path) -> dict:
        """一层目录的快照：绝对路径 → (是否目录, 大小, 修改时间)。"""
        snap = {}
        try:
            with os.scandir(d) as it:
                for i, e in enumerate(it):
                    if i >= MAX_WATCH_ENTRIES:
                        break
                    p = Path(e.path)
                    if self.hidden(p):
                        continue
                    try:
                        st = e.stat()
                        is_dir = e.is_dir()
                    except OSError:
                        continue
                    snap[posix(p)] = (is_dir, 0 if is_dir else st.st_size, 0 if is_dir else st.st_mtime_ns)
        except OSError:
            pass
        return snap

    def take_baselines(self) -> dict:
        with self._lock:
            b, self.baselines = self.baselines, {}
        return b

    def active_watches(self) -> list:
        now = time.monotonic()
        with self._lock:
            self.watch_dirs = {d: t for d, t in self.watch_dirs.items() if t > now}
            return list(self.watch_dirs)


def _safe_isdir(p: Path) -> bool:
    try:
        return p.is_dir()
    except OSError:
        return False


class Watcher:
    """轮询：共享目录整个递归，订阅的目录只看一层。比较前后两次快照，得出新增 / 修改 / 删除。"""

    def __init__(self, files: FileService) -> None:
        self.files = files
        self.snapshot = self.scan()

    def scan(self) -> dict:
        root = self.files.root
        snap = {}
        for dirpath, dirnames, filenames in os.walk(root):
            base = Path(dirpath)
            if base == root:
                dirnames[:] = [d for d in dirnames if d != TRASH]
            for name in dirnames + filenames:
                p = base / name
                rel = p.relative_to(root).as_posix()
                if _is_hidden_internal(rel):
                    continue
                try:
                    st = p.stat()
                except OSError:
                    continue
                is_dir = name in dirnames
                snap[rel] = (is_dir, 0 if is_dir else st.st_size, 0 if is_dir else st.st_mtime_ns)
        for d in self.files.active_watches():
            snap.update(self.files.shallow(d))
        return snap

    def poll(self) -> list:
        old_watch = set(getattr(self, "_watched", set()))
        base = self.files.take_baselines()
        new = self.scan()
        old = dict(self.snapshot)
        for d, snap in base.items():   # 刚订阅的目录：用订阅那一刻的快照做对比基准
            old.update(snap)
            old_watch.add(d)
        self.snapshot = new
        cur_watch = {posix(d) for d in self.files.active_watches()}
        self._watched = cur_watch
        events = []
        for rel, v in new.items():
            if rel not in old:
                # 刚订阅的目录第一次扫描出来的不是"新增"，跳过
                if is_absolute(rel) and posix(Path(rel).parent) not in old_watch:
                    continue
                kind = "created"
            elif old[rel] != v:
                kind = "modified"
            else:
                continue
            events.append(self._event(kind, rel, v))
        for rel, v in old.items():
            if rel not in new:
                # 取消订阅导致的消失也不是"删除"
                if is_absolute(rel) and posix(Path(rel).parent) not in cur_watch:
                    continue
                events.append(self._event("deleted", rel, v))
        return events

    def _event(self, kind: str, rel: str, v) -> dict:
        return {"kind": kind, "path": rel, "type": "dir" if v[0] else "file", "size": v[1],
                "by_peer": self.files.touched_by_remote(rel), "time": time.time()}
