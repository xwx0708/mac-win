#!/usr/bin/env python3
"""Tiny static server for the splash alpha-video test.

usage: python3 tools/serve.py [port=8766]

- listens on 127.0.0.1 only; document root is the parent of this script's dir
- supports HTTP Range (206 / Accept-Ranges / Content-Range) for Safari/WKWebView
- POST /report?name=<[A-Za-z0-9_]+>  -> writes body to results/<name>.json, 204
- GET  /quit                         -> 200, then the server shuts down
Compatible with the macOS system python3 (3.9).
"""

import http.server
import json
import os
import re
import socket
import sys
import threading
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT, "results")
NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
MAX_REPORT_BYTES = 50 * 1024 * 1024
CHUNK = 256 * 1024

CONTENT_TYPES = {
    ".mov": "video/quicktime",
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".png": "image/png",
}


class Handler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def guess_type(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext in CONTENT_TYPES:
            return CONTENT_TYPES[ext]
        return super().guess_type(path)

    # ---------------------------------------------------------------- GET/HEAD
    def do_GET(self):
        self._serve(head=False)

    def do_HEAD(self):
        self._serve(head=True)

    def _serve(self, head):
        route = urllib.parse.urlsplit(self.path).path
        if route == "/quit":
            self._quit(head)
            return

        path = self.translate_path(self.path)
        if os.path.isdir(path):
            # directory redirect / index.html / listing: use the stock implementation
            if head:
                super().do_HEAD()
            else:
                super().do_GET()
            return

        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return

        with f:
            st = os.fstat(f.fileno())
            size = st.st_size
            start, end = 0, size - 1
            status = 200

            range_header = self.headers.get("Range")
            if range_header is not None:
                parsed = self._parse_range(range_header, size)
                if parsed is None:
                    self.send_response(416)
                    self.send_header("Content-Range", "bytes */%d" % size)
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if parsed != "ignore":
                    start, end = parsed
                    status = 206

            length = (end - start + 1) if size > 0 else 0
            self.send_response(status)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == 206:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            self.send_header("Last-Modified", self.date_time_string(st.st_mtime))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if head or length == 0:
                return

            f.seek(start)
            remaining = length
            try:
                while remaining > 0:
                    chunk = f.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # Safari routinely aborts media requests; not an error
                self.close_connection = True

    @staticmethod
    def _parse_range(header, size):
        """Returns (start, end), "ignore" (serve whole file), or None (416)."""
        m = RANGE_RE.match(header.strip())
        if not m:
            return "ignore"  # malformed or multi-range: RFC allows serving full content
        s, e = m.group(1), m.group(2)
        if s == "" and e == "":
            return "ignore"
        if size == 0:
            return None
        if s == "":
            n = int(e)
            if n == 0:
                return None
            return (max(0, size - n), size - 1)
        start = int(s)
        end = int(e) if e != "" else size - 1
        if end >= size:
            end = size - 1
        if start >= size or start > end:
            return None
        return (start, end)

    def _quit(self, head):
        body = b"bye\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if not head:
            self.wfile.write(body)
        self.wfile.flush()
        self.close_connection = True
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    # -------------------------------------------------------------------- POST
    def do_POST(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != "/report":
            self.close_connection = True
            self.send_error(404, "Not found")
            return
        qs = urllib.parse.parse_qs(parsed.query)
        name = (qs.get("name") or [""])[0]
        if not NAME_RE.match(name):
            self.close_connection = True
            self.send_error(400, "name must match [A-Za-z0-9_]+")
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.close_connection = True
            self.send_error(411, "Content-Length required")
            return
        if length < 0 or length > MAX_REPORT_BYTES:
            self.close_connection = True
            self.send_error(413, "Payload too large")
            return

        body = self.rfile.read(length)
        try:
            data = json.loads(body.decode("utf-8"))
            out = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
        except ValueError:
            out = body  # not valid JSON: store raw so nothing is lost

        os.makedirs(RESULTS_DIR, exist_ok=True)
        final_path = os.path.join(RESULTS_DIR, name + ".json")
        tmp_path = os.path.join(RESULTS_DIR, "." + name + ".json.tmp")
        with open(tmp_path, "wb") as fh:
            fh.write(out)
        os.replace(tmp_path, final_path)  # atomic: watchers never see a half-written file

        self.send_response(204)
        self.end_headers()


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError,
                            ConnectionAbortedError, socket.timeout)):
            return
        super().handle_error(request, client_address)


def main():
    port = 8766
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    httpd = Server(("127.0.0.1", port), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
