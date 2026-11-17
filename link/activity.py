"""操作记录：每次文件操作、任务委托都记一行，标明是人还是智能体做的。

App 以后用它来播放"智能体操作回放"。记录写在 state/activity.jsonl，超过 5MB 轮换一次。
来源格式：{"kind": "agent", "agent": "claude" | "codex", "session": "<会话 ID>"}
          {"kind": "human"}  命令行或 App
          {"kind": "peer-agent", ...}  对方的智能体经长连接发来的
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

MAX_BYTES = 5_000_000


class ActivityLog:
    def __init__(self, path: Path, device_id: str) -> None:
        self.path = path
        self.device_id = device_id
        self.lock = threading.Lock()
        self.seq = 0
        path.parent.mkdir(exist_ok=True)

    def add(self, source: dict, action: str, target: str, detail: dict = None, ok: bool = True, error: str = "") -> None:
        source = source or {"kind": "unknown"}
        with self.lock:
            self.seq += 1
            rec = {"seq": self.seq, "time": time.time(), "device": self.device_id, "target": target,
                   "action": action, "source": source, "ok": ok}
            if detail:
                rec["detail"] = detail
            if error:
                rec["error"] = error
            try:
                if self.path.exists() and self.path.stat().st_size > MAX_BYTES:
                    os.replace(self.path, self.path.with_suffix(".1.jsonl"))
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except OSError:
                pass

    def tail(self, n: int = 100) -> list:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()[-n:]
        except OSError:
            return []
        return [json.loads(x) for x in lines if x.strip()]
