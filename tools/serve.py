#!/usr/bin/env python3
"""Local server for the roster editor.

Serves web/ at / and, when explicitly allowed, the repo ROM at /rom.

    python3 tools/serve.py                 # http://127.0.0.1:8080
    python3 tools/serve.py -p 9000
    python3 tools/serve.py --host 0.0.0.0  # container hosting (ROM disabled)

The ROM is only exposed on loopback (or with --allow-rom); hosting the game
itself is not the point of this project.
"""
import argparse
import glob
import mimetypes
import os
import posixpath
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")


def find_rom():
    preferred = os.path.join(ROOT, "Little League Baseball - Championship Series (USA).nes")
    if os.path.isfile(preferred):
        return preferred
    matches = sorted(glob.glob(os.path.join(ROOT, "*.nes")))
    return matches[0] if matches else None


class Handler(BaseHTTPRequestHandler):
    server_version = "RosterLab/1.0"
    allow_rom = True

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()}  {fmt % args}")

    def send_body(self, body, ctype, extra=None):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)

        if path == "/healthz":
            self.send_body(b"ok\n", "text/plain; charset=utf-8")
            return

        if path == "/rom":
            rom = find_rom() if self.allow_rom else None
            if not rom:
                self.send_error(404, "No ROM available")
                return
            with open(rom, "rb") as handle:
                body = handle.read()
            self.send_body(
                body,
                "application/octet-stream",
                {"X-Rom-Name": os.path.basename(rom)},
            )
            return

        if path == "/":
            path = "/index.html"

        relative = posixpath.normpath(path).lstrip("/")
        target = os.path.abspath(os.path.join(WEB, relative))
        if target != WEB and not target.startswith(WEB + os.sep):
            self.send_error(403, "Forbidden")
            return
        if not os.path.isfile(target):
            self.send_error(404, "Not found")
            return

        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        with open(target, "rb") as handle:
            body = handle.read()
        self.send_body(body, ctype)


def main():
    parser = argparse.ArgumentParser(description="Serve the roster editor.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default 127.0.0.1; use 0.0.0.0 in a container)")
    parser.add_argument("-p", "--port", type=int, default=int(os.environ.get("PORT", "8080")))
    parser.add_argument("--allow-rom", action="store_true",
                        help="serve /rom even when not bound to loopback")
    args = parser.parse_args()

    loopback = args.host in ("127.0.0.1", "localhost", "::1")
    Handler.allow_rom = bool(args.allow_rom or loopback)

    rom = find_rom()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    shown = "127.0.0.1" if loopback else args.host
    print(f"Roster Lab  ->  http://{shown}:{args.port}")
    if Handler.allow_rom:
        print(f"ROM         ->  {os.path.basename(rom) if rom else 'none found in repo root'}")
    else:
        print("ROM         ->  disabled (non-loopback bind; use --allow-rom to expose)")
    print("Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
