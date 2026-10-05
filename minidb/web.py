"""Local web UI and JSON HTTP API."""
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engine import Database, DatabaseError

MAX_BODY = 1024 * 1024


def make_server(database, host="127.0.0.1", port=8080, token=None):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, data, content_type="application/json"):
            body = data.encode() if isinstance(data, str) else json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            if token and not hmac.compare_digest(self.headers.get("Authorization", "").encode(), ("Bearer " + token).encode()):
                self.reply(401, {"error": "A valid bearer token is required."})
                return False
            return True

        def do_GET(self):
            if self.path == "/":
                self.reply(200, Path(__file__).with_name("static").joinpath("index.html").read_text(), "text/html")
            elif self.path == "/api/tables":
                if self.authorized():
                    self.run_command({"op": "tables"})
            else:
                self.reply(404, {"error": "Not found"})

        def run_command(self, command):
            try:
                self.reply(200, database.execute(command))
            except DatabaseError as exc:
                self.reply(400, {"error": str(exc)})
            except OSError:
                self.reply(500, {"error": "Database storage is unavailable."})

        def do_POST(self):
            if self.path != "/api/execute":
                self.reply(404, {"error": "Not found"})
                return
            if not self.authorized():
                return
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                self.reply(415, {"error": "Use Content-Type: application/json"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    self.reply(413, {"error": "Body must be 1 byte to 1 MiB."})
                    return
                command = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                self.reply(400, {"error": "Invalid JSON request."})
                return
            self.run_command(command)

    return ThreadingHTTPServer((host, port), Handler)
