"""Local-only dashboard with independent sensor sampling."""
import argparse
import csv
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .model import Store, reading

STATIC = Path(__file__).parent / 'static'


class Application:
    def __init__(self, store):
        self.store = store
        self.latest = reading(0)
        self.finished = threading.Event()
        self.worker = threading.Thread(target=self.sample, daemon=True)

    def sample(self):
        index = 0
        while not self.finished.is_set():
            self.latest = reading(index)
            self.store.append(self.latest)
            index += 1
            self.finished.wait(1)


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, content_type='application/json'):
            payload = body.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ('/', '/app.js', '/style.css'):
                filename, mime = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}[path]
                self.send(200, (STATIC / filename).read_text(), mime)
            elif path == '/api/health':
                self.send(200, json.dumps({'status': 'ok', 'mode': 'simulation'}))
            elif path == '/api/telemetry':
                self.send(200, json.dumps(app.latest))
            elif path == '/api/sessions':
                self.send(200, json.dumps(app.store.sessions()))
            elif path.startswith('/api/export/'):
                try:
                    columns, rows = app.store.export(int(path.rsplit('/', 1)[1]))
                except (ValueError, KeyError):
                    self.send(404, '{"error":"Session not found"}')
                    return
                output = io.StringIO(newline='')
                writer = csv.writer(output)
                writer.writerow(columns)
                writer.writerows(rows)
                self.send(200, output.getvalue(), 'text/csv; charset=utf-8')
            else:
                self.send(404, '{"error":"Not found"}')

        def do_POST(self):
            # Require a custom header and same-origin browser requests to prevent
            # other websites from changing local recording state.
            if self.headers.get('X-Monitor-Request') != '1' or self.headers.get('Sec-Fetch-Site') not in (None, 'same-origin'):
                self.send(403, '{"error":"Request rejected"}')
                return
            if self.path not in ('/api/sessions/start', '/api/sessions/stop'):
                self.send(404, '{"error":"Not found"}')
                return
            try:
                action = app.store.start if self.path.endswith('/start') else app.store.stop
                self.send(200, json.dumps({'session_id': action()}))
            except ValueError as error:
                self.send(409, json.dumps({'error': str(error)}))
    return Handler


def main():
    parser = argparse.ArgumentParser(description='Local civilian water-monitoring simulator')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--database', default='water-monitor.sqlite3')
    args = parser.parse_args()
    store = Store(args.database)
    app = Application(store)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(app))
    app.worker.start()
    print(f'Dashboard: http://127.0.0.1:{args.port} — SIMULATED DATA', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.finished.set()
        app.worker.join()
        store.close()
