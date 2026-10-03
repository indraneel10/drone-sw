"""Local-only dashboard with independent sensor sampling."""
import argparse
import csv
import io
import json
import math
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .model import PROFILES, Store, reading

STATIC = Path(__file__).parent / 'static'


class Application:
    def __init__(self, store, profile='baseline', interval=1.0):
        if not math.isfinite(interval) or not 0.1 <= interval <= 60:
            raise ValueError('Sample interval must be between 0.1 and 60 seconds')
        self.store = store
        self.profile = profile
        self.interval = interval
        self.latest = reading(0, profile)
        self.finished = threading.Event()
        self.worker = threading.Thread(target=self.sample, daemon=True)

    def sample(self):
        index = 0
        while not self.finished.is_set():
            value = reading(index, self.profile)
            self.store.append(value)
            self.latest = value
            index += 1
            self.finished.wait(self.interval)

    def health(self):
        age = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(self.latest['timestamp'])).total_seconds())
        healthy = self.worker.is_alive() and age <= max(3, self.interval * 3)
        return {'status': 'ok' if healthy else 'degraded', 'mode': 'simulation',
                'profile': self.profile, 'sample_interval_seconds': self.interval,
                'sample_age_seconds': round(age, 2)}


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, content_type='application/json', filename=None):
            payload = body.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            url = urlsplit(self.path)
            path = url.path
            query = parse_qs(url.query, keep_blank_values=True)
            if path in ('/', '/app.js', '/style.css'):
                filename, mime = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}[path]
                self.send(200, (STATIC / filename).read_text(), mime)
            elif path == '/api/health':
                health = app.health()
                self.send(200 if health['status'] == 'ok' else 503, json.dumps(health))
            elif path == '/api/telemetry':
                self.send(200, json.dumps(app.latest))
            elif path == '/api/sessions':
                self.send(200, json.dumps(app.store.sessions()))
            elif path.startswith('/api/series/'):
                try:
                    if len(path.split('/')) != 4:
                        raise KeyError(path)
                    session_id = int(path.rsplit('/', 1)[1])
                    if set(query) - {'limit'} or len(query.get('limit', ['120'])) != 1:
                        raise ValueError('Only one limit parameter is supported')
                    series = app.store.series(session_id, int(query.get('limit', ['120'])[0]))
                except ValueError:
                    self.send(400, '{"error":"limit must be an integer between 1 and 500; only limit is supported"}')
                    return
                except KeyError:
                    self.send(404, '{"error":"Session not found"}')
                    return
                self.send(200, json.dumps(series))
            elif path.startswith('/api/summary/'):
                try:
                    summary = app.store.summary(int(path.rsplit('/', 1)[1]))
                except (ValueError, KeyError):
                    self.send(404, '{"error":"Session not found"}')
                    return
                self.send(200, json.dumps(summary))
            elif path.startswith('/api/export/'):
                try:
                    if len(path.split('/')) != 4:
                        raise KeyError(path)
                    session_id = int(path.rsplit('/', 1)[1])
                    columns, rows = app.store.export(session_id)
                except (ValueError, KeyError):
                    self.send(404, '{"error":"Session not found"}')
                    return
                if set(query) - {'format'} or len(query.get('format', ['csv'])) != 1 or query.get('format', ['csv'])[0] not in ('csv', 'json'):
                    self.send(400, '{"error":"format must be csv or json"}')
                    return
                if query.get('format') == ['json']:
                    samples = [dict(zip(columns, row)) for row in rows]
                    for sample in samples:
                        sample['simulated'] = bool(sample['simulated'])
                    self.send(200, json.dumps({'session_id': session_id, 'simulated': True, 'samples': samples}), filename=f'survey-{session_id}.json')
                    return
                output = io.StringIO(newline='')
                writer = csv.writer(output)
                writer.writerow(columns)
                writer.writerows(rows)
                self.send(200, output.getvalue(), 'text/csv; charset=utf-8', filename=f'survey-{session_id}.csv')
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
    parser.add_argument('--profile', choices=PROFILES, default='baseline')
    parser.add_argument('--interval', type=float, default=1.0, help='Sample interval in seconds (0.1–60)')
    args = parser.parse_args()
    if not math.isfinite(args.interval) or not 0.1 <= args.interval <= 60:
        parser.error('--interval must be between 0.1 and 60 seconds')
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    store = Store(args.database)
    app = Application(store, args.profile, args.interval)
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
