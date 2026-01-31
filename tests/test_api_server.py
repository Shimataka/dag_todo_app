import json
import socket
import threading
import unittest
from http import client
from http.server import HTTPServer

from dandori.api.server import Handler


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestApiServerHandler(unittest.TestCase):
    """Handler を BaseHTTPRequestHandler のテスト用に呼び出すのは難しいため、
    run() でサーバーを起動して HTTP で検証する."""

    def test_get_health_200(self) -> None:
        port = _find_free_port()
        server_ready: threading.Event = threading.Event()
        shutdown_requested: threading.Event = threading.Event()

        def serve() -> None:
            with HTTPServer(("127.0.0.1", port), Handler) as httpd:
                server_ready.set()
                while not shutdown_requested.is_set():
                    httpd.handle_request()

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        server_ready.wait(timeout=2.0)
        conn = client.HTTPConnection("127.0.0.1", port, timeout=2.0)
        try:
            conn.request("GET", "/health")
            resp = conn.getresponse()
            assert resp.status == 200
            body = json.loads(resp.read().decode())
            assert body == {"ok": True}
        finally:
            shutdown_requested.set()
            conn.close()

    def test_get_other_404(self) -> None:
        port = _find_free_port()
        server_ready: threading.Event = threading.Event()
        shutdown_requested: threading.Event = threading.Event()

        def serve() -> None:
            with HTTPServer(("127.0.0.1", port), Handler) as httpd:
                server_ready.set()
                while not shutdown_requested.is_set():
                    httpd.handle_request()

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        server_ready.wait(timeout=2.0)
        conn = client.HTTPConnection("127.0.0.1", port, timeout=2.0)
        try:
            conn.request("GET", "/other")
            resp = conn.getresponse()
            assert resp.status == 404
            body = json.loads(resp.read().decode())
            assert body == {"error": "not_found"}
        finally:
            shutdown_requested.set()
            conn.close()


if __name__ == "__main__":
    unittest.main()
