"""Tailscale 身份：本机是谁、某个 IP 背后是哪台设备、是否在白名单里。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

WHOIS_CACHE_SECONDS = 60


def find_tailscale() -> str:
    candidates = [
        os.environ.get("TAILSCALE_BIN"),
        shutil.which("tailscale"),
        r"C:\Program Files\Tailscale\tailscale.exe",
        "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
        "/usr/local/bin/tailscale",
        "/opt/homebrew/bin/tailscale",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    raise RuntimeError("找不到 tailscale 命令行程序")


class Tailscale:
    """对 tailscale 命令行的薄封装（同步调用，异步代码里请放进线程）。"""

    def __init__(self) -> None:
        self.bin = find_tailscale()
        self._cache: dict = {}
        self._lock = threading.Lock()

    def _run_json(self, *args: str) -> dict:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # pythonw 下不弹黑窗
        # macOS 的 Tailscale.app 没有 TERM 时会当成要启动图形界面（launchd 下就没有 TERM）
        env = dict(os.environ)
        env.setdefault("TERM", "dumb")
        out = subprocess.run([self.bin, *args], capture_output=True, timeout=10, env=env, **kwargs)
        text = out.stdout.decode("utf-8", "replace")
        if out.returncode != 0:
            err = out.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError(f"tailscale {' '.join(args)} 失败：{err}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            err = (text + out.stderr.decode("utf-8", "replace")).strip()[:200]
            raise RuntimeError(f"tailscale {' '.join(args)} 没有返回 JSON：{err}") from None

    def status(self) -> dict:
        return self._run_json("status", "--json")

    def whois(self, ip: str) -> dict:
        """返回 {'device_id', 'name', 'user_id'}；查不到时抛异常。结果缓存一分钟。"""
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(ip)
            if hit and now - hit[0] < WHOIS_CACHE_SECONDS:
                return hit[1]
        d = self._run_json("whois", "--json", ip)
        info = {
            "device_id": d["Node"]["StableID"],
            "name": d["Node"].get("ComputedName") or d["Node"].get("Name", ""),
            "user_id": d["UserProfile"]["ID"],
        }
        with self._lock:
            self._cache[ip] = (now, info)
        return info


class Identity:
    """本机身份，以及 tailnet 里其他设备当前的地址和在线状态。"""

    def __init__(self, ts: Tailscale) -> None:
        self.ts = ts
        self.refresh()

    def refresh(self) -> None:
        st = self.ts.status()
        if st.get("BackendState") != "Running":
            raise RuntimeError(f"Tailscale 未连接（{st.get('BackendState')}）")
        me = st["Self"]
        ipv4 = [ip for ip in me.get("TailscaleIPs", []) if ":" not in ip]
        if not ipv4:
            raise RuntimeError("本机没有 Tailscale IPv4 地址")
        peers = {}
        for p in (st.get("Peer") or {}).values():
            ips = [ip for ip in p.get("TailscaleIPs", []) if ":" not in ip]
            peers[p["ID"]] = {
                "ip": ips[0] if ips else None,
                "online": bool(p.get("Online")),
                "name": (p.get("DNSName") or "").split(".")[0] or p.get("HostName", ""),
            }
        self.device_id: str = me["ID"]
        self.name: str = (me.get("DNSName") or "").split(".")[0] or me.get("HostName", "")
        self.user_id: int = me["UserID"]
        self.ip: str = ipv4[0]
        self.peers: dict = peers


def authorize(ts: Tailscale, me: Identity, allowed: dict, ip: str) -> dict:
    """确认 ip 背后是白名单设备、且属于同一个 Tailscale 账号。通过则返回对方身份，否则抛 PermissionError。"""
    try:
        who = ts.whois(ip)
    except Exception as e:
        raise PermissionError(f"{ip} 不是已知的 Tailscale 设备（{e}）") from e
    if who["device_id"] not in allowed:
        raise PermissionError(f"设备 {who['name']}（{who['device_id']}）不在白名单里")
    if who["user_id"] != me.user_id:
        raise PermissionError(f"设备 {who['name']} 不属于本机的 Tailscale 账号")
    return who
