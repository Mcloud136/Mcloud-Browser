#!/usr/bin/env python3
"""asset_server.py - loopback-only static server with CORS, used so the GitHub
release page (same browser session) can read the local installer bytes and push
them through GitHub's own release-asset upload flow.

Binds 127.0.0.1 only. Serves exactly the two files passed on the command line.
Stop it as soon as the upload finishes.
"""
import http.server
import os
import sys

ALLOW = [os.path.basename(p) for p in sys.argv[1:]]
ROOT = os.path.dirname(os.path.abspath(sys.argv[0]))
PORT = int(os.environ.get("ASSET_PORT", "8765"))


class Handler(http.server.BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        # Chrome Private Network Access: a public/secure page fetching a loopback
        # resource gets blocked unless the preflight explicitly allows it. Without
        # this header the GitHub page's fetch fails with "Failed to fetch".
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "600")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_HEAD(self):
        self.do_GET(head_only=True)

    def do_GET(self, head_only=False):
        name = self.path.lstrip("/").split("?")[0]
        if name not in ALLOW or not os.path.isfile(os.path.join(ROOT, name)):
            self.send_response(403)
            self._cors()
            self.end_headers()
            self.wfile.write(b"forbidden")
            return
        size = os.path.getsize(os.path.join(ROOT, name))
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.end_headers()
        if head_only:
            return
        with open(os.path.join(ROOT, name), "rb") as f:
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def log_message(self, fmt, *args):
        sys.stderr.write("asset_server: " + fmt % args + "\n")


if not ALLOW:
    print("usage: ASSET_PORT=8765 asset_server.py <file> [<file>...]")
    sys.exit(2)

httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
print(f"serving {ALLOW} from {ROOT} on http://127.0.0.1:{PORT}/ (loopback only)")
sys.stdout.flush()
httpd.serve_forever()
