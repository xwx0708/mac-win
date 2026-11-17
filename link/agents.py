"""智能体通道：在本机用终端版 Claude Code 或 Codex 执行对方发来的任务。

只在本机共享目录（或它的子目录）里运行；Claude Code 用 acceptEdits（可以改文件，不能执行命令），
Codex 用 workspace-write 沙箱（只能写工作目录）。

在 macOS 上，Claude Code 的登录凭据在钥匙串里，只有图形登录会话里的进程读得到。
互联服务是 LaunchAgent，正好在图形会话里，所以能调用；用 SSH 直接调用会报未登录。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

OUTPUT_LIMIT = 20000
HOME = Path.home()
EXTRA_PATH = [
    str(HOME / ".local" / "bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
    str(HOME / "AppData" / "Roaming" / "npm"),
]


def _env() -> dict:
    env = dict(os.environ)
    parts = env.get("PATH", "").split(os.pathsep)
    env["PATH"] = os.pathsep.join(parts + [p for p in EXTRA_PATH if p not in parts])
    env.setdefault("TERM", "dumb")
    env.setdefault("HOME", str(HOME))
    # 别把调用方自己是 Claude Code 子进程的标记传下去
    for k in [k for k in env if k.startswith("CLAUDE_CODE_") or k == "CLAUDECODE"]:
        del env[k]
    return env


def _which(name: str, env: dict) -> str:
    p = shutil.which(name, path=env["PATH"])
    if not p:
        raise FileNotFoundError(f"本机找不到 {name} 命令")
    return p


def build_command(agent: str, prompt: str, env: dict) -> list:
    if agent == "claude":
        return [_which("claude", env), "-p", prompt, "--permission-mode", "acceptEdits"]
    if agent == "codex":
        if sys.platform == "win32":
            # 绕开 codex.cmd：批处理传中文和引号参数不可靠，直接用 node 跑
            js = HOME / "AppData/Roaming/npm/node_modules/@openai/codex/bin/codex.js"
            base = [_which("node", env), str(js)] if js.exists() else [_which("codex", env)]
        else:
            base = [_which("codex", env)]
        return base + ["exec", "--skip-git-repo-check", "-s", "workspace-write", prompt]
    raise ValueError(f"不支持的智能体：{agent}（可用 claude、codex）")


def run_agent(agent: str, prompt: str, cwd: Path, timeout: float) -> dict:
    if not prompt or not prompt.strip():
        raise ValueError("任务内容不能为空")
    env = _env()
    cmd = build_command(agent, prompt, env)
    cwd.mkdir(parents=True, exist_ok=True)
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    t0 = time.monotonic()
    try:
        out = subprocess.run(cmd, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                             capture_output=True, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired:
        return {"agent": agent, "ok": False, "exit_code": None, "seconds": round(time.monotonic() - t0, 1),
                "output": "", "error": f"超过 {timeout:.0f} 秒没完成，已终止"}
    stdout = out.stdout.decode("utf-8", "replace").strip()
    stderr = out.stderr.decode("utf-8", "replace").strip()
    return {
        "agent": agent,
        "ok": out.returncode == 0,
        "exit_code": out.returncode,
        "seconds": round(time.monotonic() - t0, 1),
        "output": stdout[-OUTPUT_LIMIT:],
        "error": "" if out.returncode == 0 else stderr[-4000:],
    }
