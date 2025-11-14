from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        self.send_response(404)


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    with HTTPServer((host, port), Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    run()
