"""开放范围：互联服务（人工和智能体同一套规则）能看到、能改本机的哪些位置。

三层规则，按顺序判断：
  deny      永远不开放：看不到、读不了、写不了，列目录时连名字都不显示（E:\\隐私数据、密钥、钥匙串等）
  roots     能看到、能读的范围（Windows 的各个盘，Mac 的整个磁盘）
  writable  能改（写入、新建、移动、复制到、删除）的范围；roots 里其余地方只读（系统和程序目录）

规则写在 config.json 的 "scope" 里，按设备 ID 分；没写就用下面的默认值。
路径比较一律先解析符号链接 / 联接点，再忽略大小写，防止绕道进入禁区。
"""

from __future__ import annotations

import os
import shutil
import string
import subprocess
import sys
from pathlib import Path

HOME = Path.home()

DEFAULTS = {
    "win32": {
        "roots": [f"{d}:/" for d in "CDE"],
        "writable": ["E:/", "D:/", "~"],
        "deny": [
            "E:/隐私数据",
            "~/.ssh", "~/.claude/.credentials.json", "~/.codex/auth.json",
            "~/AppData/Roaming/Microsoft/Credentials", "~/AppData/Local/Microsoft/Credentials",
            "~/AppData/Roaming/Microsoft/Protect", "C:/Windows/System32/config",
        ],
    },
    "darwin": {
        "roots": ["/"],
        "writable": ["~", "/Volumes", "/tmp", "/private/tmp"],
        "deny": [
            "~/Library/Keychains", "~/.ssh", "~/.codex/auth.json", "~/.claude/.credentials.json",
            "/private/var/db", "/Library/Keychains", "/System/Volumes",
        ],
    },
}


def _expand(p: str) -> Path:
    p = os.path.expanduser(p.replace("\\", "/"))
    try:
        return Path(p).resolve()
    except OSError:
        return Path(os.path.abspath(p))


def _key(p: Path) -> str:
    """比较用：统一分隔符、去掉末尾斜杠、忽略大小写（NTFS 和 APFS 默认都不分大小写）。"""
    s = str(p).replace("\\", "/").rstrip("/")
    return (s or "/").casefold()


def _under(p: str, base: str) -> bool:
    return p == base or p.startswith(base + "/") or base == "/" or (base.endswith(":") and p.startswith(base))


class Scope:
    def __init__(self, rules: dict = None) -> None:
        r = dict(DEFAULTS.get(sys.platform, DEFAULTS["darwin"]))
        r.update(rules or {})
        self.roots = [_expand(x) for x in r["roots"] if Path(_expand(x)).exists()]
        self.writable = [_expand(x) for x in r["writable"]]
        self.deny = [_expand(x) for x in r["deny"]]
        self._rk = [_key(x) for x in self.roots]
        self._wk = [_key(x) for x in self.writable]
        self._dk = [_key(x) for x in self.deny]

    def denied(self, p: Path) -> bool:
        k = _key(p)
        return any(_under(k, d) for d in self._dk)

    def visible(self, p: Path) -> bool:
        k = _key(p)
        return any(_under(k, r) for r in self._rk) and not self.denied(p)

    def can_write(self, p: Path) -> bool:
        k = _key(p)
        return self.visible(p) and any(_under(k, w) for w in self._wk)

    def check(self, p: Path, write: bool, shown: str) -> None:
        if self.denied(p):
            raise PermissionError(f"这个位置不对外开放：{shown}")
        if not self.visible(p):
            raise PermissionError(f"不在开放范围内：{shown}")
        if write and not self.can_write(p):
            raise PermissionError(f"这里是只读区域（系统或程序目录），不能修改：{shown}")

    # ------------------------------------------------------------ 给前端和智能体看的"位置"列表

    def locations(self, share: Path) -> dict:
        drives = []
        for r in self.roots:
            try:
                u = shutil.disk_usage(r)
                usage = {"total": u.total, "free": u.free}
            except OSError:
                usage = {}
            drives.append({"path": posix(r), "label": _drive_label(r), "fs": _drive_fs(r), "writable": self.can_write(r), **usage})
        places = [{"name": "互传", "path": posix(share)}]
        for name, p in _special_folders():
            if p and Path(p).exists() and self.visible(Path(p)):
                places.append({"name": name, "path": posix(Path(p).resolve())})
        return {"platform": "windows" if sys.platform == "win32" else "mac", "home": posix(HOME),
                "drives": drives, "places": places,
                "deny": [posix(d) for d in self.deny], "writable": [posix(w) for w in self.writable]}


def posix(p: Path) -> str:
    s = str(p).replace("\\", "/")
    return s if not (len(s) == 2 and s[1] == ":") else s + "/"


def _drive_label(p: Path) -> str:
    if sys.platform == "win32":
        import ctypes
        buf = ctypes.create_unicode_buffer(261)
        root = str(p).rstrip("\\/") + "\\"
        ok = ctypes.windll.kernel32.GetVolumeInformationW(root, buf, 261, None, None, None, None, 0)
        name = buf.value if ok else ""
        return f"{name} ({root[:2]})" if name else root[:2]
    if str(p) == "/":
        # 启动盘的名字由用户决定（默认叫 Macintosh HD），/Volumes 里指向 / 的那一项就是它
        try:
            for v in Path("/Volumes").iterdir():
                if os.path.realpath(v) == "/":
                    return v.name
        except OSError:
            pass
        return "启动盘"
    return p.name


def _drive_fs(p: Path) -> str:
    """盘的文件系统（NTFS、exFAT、APFS……），读不到就返回空字符串。"""
    if sys.platform == "win32":
        import ctypes
        fs = ctypes.create_unicode_buffer(261)
        root = str(p).rstrip("\\/") + "\\"
        ok = ctypes.windll.kernel32.GetVolumeInformationW(root, None, 0, None, None, None, fs, 261)
        return fs.value if ok else ""
    try:
        out = subprocess.run(["/sbin/mount"], capture_output=True, text=True, timeout=3).stdout
        for line in out.splitlines():   # 形如：/dev/disk3s1s1 on / (apfs, sealed, local, read-only, journaled)
            if f" on {p} (" in line:
                return line.split(" (", 1)[1].split(",", 1)[0].strip().upper()
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


_CLUSTER: dict = {}


def cluster_size(p: Path) -> int:
    """Windows 上文件所在盘的簇大小（字节），用来算"占用空间"；读不到返回 0。"""
    drive = p.drive.upper()
    if sys.platform != "win32" or not drive:
        return 0
    if drive not in _CLUSTER:
        import ctypes
        spc, bps, free, total = (ctypes.c_ulong() for _ in range(4))
        ok = ctypes.windll.kernel32.GetDiskFreeSpaceW(drive + "\\", ctypes.byref(spc), ctypes.byref(bps), ctypes.byref(free), ctypes.byref(total))
        _CLUSTER[drive] = spc.value * bps.value if ok else 0
    return _CLUSTER[drive]


def _special_folders():
    if sys.platform == "win32":
        import winreg
        keys = [("桌面", "Desktop"), ("文档", "Personal"), ("下载", "{374DE290-123F-4565-9164-39C4925E467B}"),
                ("图片", "My Pictures"), ("视频", "My Video"), ("音乐", "My Music")]
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        except OSError:
            return []
        out = []
        for name, val in keys:
            try:
                out.append((name, os.path.expandvars(winreg.QueryValueEx(k, val)[0])))
            except OSError:
                pass
        out.append(("主文件夹", str(HOME)))
        return out
    return [("桌面", HOME / "Desktop"), ("文稿", HOME / "Documents"), ("下载", HOME / "Downloads"),
            ("图片", HOME / "Pictures"), ("影片", HOME / "Movies"), ("音乐", HOME / "Music"),
            ("应用程序", Path("/Applications")), ("个人", HOME)]


def is_absolute(s: str) -> bool:
    s = s.replace("\\", "/")
    return s.startswith("/") or (len(s) >= 2 and s[1] == ":" and s[0] in string.ascii_letters)
