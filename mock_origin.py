import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping


def build_echo_response(method: str, path: str, headers: Mapping[str, str]) -> bytes:
    payload = {
        "method": method,
        "path": path,
        "headers": dict(headers),
        "message": "local mock origin received the rewritten request",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


class EchoHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self._send_echo()

    def do_POST(self) -> None:
        self._send_echo()

    def _send_echo(self) -> None:
        body = build_echo_response(self.command, self.path, self.headers)
        self.send_response(200)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[mock-origin] {self.address_string()} - {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local mock origin for rewrite MITM tests.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=9000, type=int)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), EchoHandler)
    print(f"mock origin listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
