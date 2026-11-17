"""智能体任务：可以后台运行、查询进度、取消。

分两边：
  TaskRunner     执行方。对方派来任务时，在本机后台启动 Claude Code / Codex，记录状态和输出。
  TaskRegistry   委托方。记下本机派出去的每个任务，对方离线时如实报告"未送达"或"不确定"。

被委托执行的智能体带着环境变量 MACWIN_DELEGATED=1 启动。它加载的 MCP 服务看到这个变量，
就拒绝再调用 delegate_task，防止两台电脑来回委托。
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from agents import OUTPUT_LIMIT, _env, build_command

# 状态取值
RUNNING, DONE, FAILED, CANCELLED, TIMEOUT = "运行中", "完成", "失败", "已取消", "超时"
UNDELIVERED, UNCERTAIN, SENDING = "未送达", "不确定", "发送中"
TERMINAL = {DONE, FAILED, CANCELLED, TIMEOUT, UNDELIVERED}


def new_task_id() -> str:
    return time.strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


# ================================================================ 执行方

class TaskRunner:
    def __init__(self) -> None:
        self.tasks: dict = {}
        self.lock = threading.Lock()

    def start(self, task_id: str, agent: str, prompt: str, cwd: Path, timeout: float, source: dict) -> dict:
        if not prompt or not prompt.strip():
            raise ValueError("任务内容不能为空")
        with self.lock:
            if task_id in self.tasks:   # 委托方重发了同一个任务（比如回执丢了），不重复执行
                return self.public(task_id)
        env = _env()
        env["MACWIN_DELEGATED"] = "1"
        env["MACWIN_TASK_ID"] = task_id
        cmd = build_command(agent, prompt, env)
        if agent == "claude":   # 非交互模式下 MCP 工具默认要授权，这里放行本服务自己的工具
            cmd += ["--allowedTools", "mcp__macwin"]
        cwd.mkdir(parents=True, exist_ok=True)
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True   # 自成进程组，取消时能连子进程一起结束
        proc = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
        rec = {"task_id": task_id, "agent": agent, "prompt": prompt, "cwd": str(cwd), "status": RUNNING,
               "started_at": time.time(), "ended_at": None, "exit_code": None, "output": "", "error": "",
               "source": source, "proc": proc}
        with self.lock:
            self.tasks[task_id] = rec
        threading.Thread(target=self._wait, args=(rec, timeout), daemon=True).start()
        return self.public(task_id)

    def _wait(self, rec: dict, timeout: float) -> None:
        proc = rec["proc"]
        try:
            out, err = proc.communicate(timeout=timeout)
            status = DONE if proc.returncode == 0 else FAILED
        except subprocess.TimeoutExpired:
            self._kill(proc)
            out, err = proc.communicate()
            status = TIMEOUT
            err = (err or b"") + f"\n超过 {timeout:.0f} 秒没完成，已终止".encode("utf-8")
        with self.lock:
            if rec["status"] == CANCELLED:   # 取消时已经定好状态
                status = CANCELLED
            rec.update(status=status, ended_at=time.time(), exit_code=proc.returncode,
                       output=out.decode("utf-8", "replace").strip()[-OUTPUT_LIMIT:],
                       error="" if status == DONE else err.decode("utf-8", "replace").strip()[-4000:])

    @staticmethod
    def _kill(proc) -> None:
        try:
            if sys.platform == "win32":   # 连同 node、子进程整棵树一起结束
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                os.killpg(proc.pid, signal.SIGTERM)
        except Exception:
            proc.kill()

    def cancel(self, task_id: str) -> dict:
        with self.lock:
            rec = self.tasks.get(task_id)
            if rec is None:
                raise KeyError(f"本机没有任务 {task_id} 的记录（可能本机服务重启过）")
            if rec["status"] != RUNNING:
                return self._public(rec)
            rec["status"] = CANCELLED
        self._kill(rec["proc"])
        return self.public(task_id)

    def public(self, task_id: str) -> dict:
        with self.lock:
            rec = self.tasks.get(task_id)
            if rec is None:
                raise KeyError(f"本机没有任务 {task_id} 的记录（可能本机服务重启过）")
            return self._public(rec)

    @staticmethod
    def _public(rec: dict) -> dict:
        d = {k: v for k, v in rec.items() if k != "proc"}
        end = rec["ended_at"] or time.time()
        d["seconds"] = round(end - rec["started_at"], 1)
        return d


# ================================================================ 委托方

class TaskRegistry:
    """本机派出去的任务。保存到 state/tasks.json，服务重启后还能查到最后已知的状态。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.tasks: dict = {}
        try:
            self.tasks = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
        for t in self.tasks.values():   # 上次服务停止时还没结束的任务，现在无法确认
            if t["status"] in (RUNNING, SENDING):
                t["last_known"] = t["status"]
                t["status"] = UNCERTAIN
                t["note"] = "本机服务重启过，之前的进度无法确认，请再查询一次"

    def add(self, rec: dict) -> None:
        with self.lock:
            self.tasks[rec["task_id"]] = rec
            self._save()

    def update(self, task_id: str, **kw) -> dict:
        with self.lock:
            rec = self.tasks[task_id]
            rec.update(kw)
            rec["updated_at"] = time.time()
            self._save()
            return dict(rec)

    def get(self, task_id: str):
        with self.lock:
            rec = self.tasks.get(task_id)
            return dict(rec) if rec else None

    def _save(self) -> None:
        keep = dict(sorted(self.tasks.items(), key=lambda kv: kv[1].get("created_at", 0))[-200:])
        self.tasks = keep
        self.path.parent.mkdir(exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)
