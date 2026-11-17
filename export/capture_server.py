"""只在本机监听的小服务：提供 render.html，并把它渲染出的每一帧 PNG 存到 frames/<段名>/NNNN.png。"""
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).parent
SEGMENTS = {"intro", "loop", "outro", "check"}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        seg, idx = q.get("seg", [""])[0], q.get("i", [""])[0]
        if u.path != "/save" or seg not in SEGMENTS or not re.fullmatch(r"\d{1,5}", idx):
            self.send_error(400)
            return
        data = self.rfile.read(int(self.headers["Content-Length"]))
        if not data.startswith(b"\x89PNG"):
            self.send_error(400)
            return
        out = HERE / "frames" / seg
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{int(idx):04d}.png").write_bytes(data)
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8733), Handler).serve_forever()
