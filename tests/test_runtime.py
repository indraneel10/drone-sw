import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from water_monitor.model import Store
from water_monitor.runtime import DatabaseLease
from water_monitor.server import Application


class RuntimeTests(unittest.TestCase):
    def test_close_finalizes_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'survey.sqlite3'
            store = Store(path)
            store.start()
            store.close()
            with sqlite3.connect(path) as db:
                self.assertIsNotNone(db.execute('SELECT ended FROM sessions').fetchone()[0])

    def test_database_error_marks_sampler_degraded(self):
        class FailingStore:
            def append(self, value):
                raise sqlite3.OperationalError('simulated disk failure')
        app = Application(FailingStore())
        with self.assertLogs(level='ERROR'):
            app.worker.start()
            app.worker.join(timeout=3)
        self.assertEqual(app.health()['status'], 'degraded')
        self.assertIsNotNone(app.health()['sampler_error'])

    def test_lock_rejects_other_process_and_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'survey.sqlite3'
            code = 'from water_monitor.runtime import DatabaseLease; import sys; lease=DatabaseLease(sys.argv[1]); lease.__enter__(); lease.__exit__()'
            with DatabaseLease(path):
                result = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('database lock', result.stderr)
            result = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_cli_options_do_not_create_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'survey.sqlite3'
            for option in [('--interval', 'nan'), ('--port', '0'), ('--profile', 'bad')]:
                result = subprocess.run([sys.executable, '-m', 'water_monitor', '--database', str(path), *option], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(path.exists())

    def test_port_conflict_releases_database_lease(self):
        with tempfile.TemporaryDirectory() as directory, socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            path = Path(directory) / 'survey.sqlite3'
            result = subprocess.run([sys.executable, '-m', 'water_monitor', '--database', str(path), '--port', str(listener.getsockname()[1])], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            self.assertIn('Unable to start', result.stderr)
            with DatabaseLease(path):
                pass

    @unittest.skipIf(os.name == 'nt', 'SIGTERM cleanup applies to POSIX; Windows uses Ctrl+C')
    def test_sigterm_closes_active_session_and_process(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'survey.sqlite3'
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            process = subprocess.Popen([sys.executable, '-m', 'water_monitor', '--database', str(path), '--port', str(port), '--interval', '0.1'], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 10
                while True:
                    try:
                        with urlopen(f'http://127.0.0.1:{port}/api/health', timeout=1) as response:
                            self.assertEqual(json.load(response)['status'], 'ok')
                        break
                    except URLError:
                        if process.poll() is not None or time.monotonic() > deadline:
                            self.fail('CLI did not become healthy')
                        time.sleep(0.05)
                request = Request(f'http://127.0.0.1:{port}/api/sessions/start', method='POST', headers={'X-Monitor-Request': '1'})
                with urlopen(request, timeout=2) as response:
                    self.assertEqual(response.status, 200)
                process.send_signal(signal.SIGTERM)
                _, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stderr)
                with sqlite3.connect(path) as db:
                    self.assertIsNotNone(db.execute('SELECT ended FROM sessions').fetchone()[0])
                with DatabaseLease(path):
                    pass
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)


class RuntimeHTTPTests(unittest.TestCase):
    import test_monitor as _http
    setUp = _http.HTTPTests.setUp
    tearDown = _http.HTTPTests.tearDown
    fetch = _http.HTTPTests.fetch

    def test_recording_database_failure_returns_503(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        with patch.object(self.store, 'start', side_effect=sqlite3.OperationalError('simulated failure')):
            with self.assertLogs(level='ERROR'):
                with self.assertRaises(HTTPError) as error:
                    self.fetch('/api/sessions/start', 'POST', {'X-Monitor-Request': '1'})
            self.assertEqual(error.exception.code, 503)
            self.assertIn('Database operation failed', error.exception.read().decode())
            error.exception.close()
