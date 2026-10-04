"""Verify wheel installation, bundled assets and CLI from outside the checkout.

Usage: python tests/installed_smoke.py [path-to-installed-python]
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def main():
    python = str(Path(sys.argv[1]).absolute()) if len(sys.argv) > 1 else sys.executable
    cli = Path(python).parent / ('water-monitor.exe' if os.name == 'nt' else 'water-monitor')
    with tempfile.TemporaryDirectory() as directory:
        # Isolated mode and a separate working directory prevent source imports.
        assets = subprocess.run([python, '-I', '-c',
            "from importlib.resources import files; root=files('water_monitor')/'static'; "
            "assert all((root/name).is_file() for name in ('index.html','app.js','style.css'))"],
            cwd=directory, capture_output=True, text=True, timeout=10)
        if assets.returncode:
            raise RuntimeError(assets.stderr)
        help_result = subprocess.run([str(cli), '--help'], cwd=directory, capture_output=True, text=True, timeout=10)
        if help_result.returncode or '--profile' not in help_result.stdout:
            raise RuntimeError('Installed launch command failed: ' + help_result.stderr)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen([python, '-I', '-m', 'water_monitor', '--port', str(port), '--interval', '0.1'], cwd=directory, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    with urlopen(f'http://127.0.0.1:{port}/api/health', timeout=1) as response:
                        assert json.load(response)['status'] == 'ok'
                    break
                except URLError:
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('Installed app did not become healthy')
                    time.sleep(0.05)
            for route, expected in [('/', 'SIMULATED DATA'), ('/app.js', 'renderTrends'), ('/style.css', 'trend-grid')]:
                with urlopen(f'http://127.0.0.1:{port}{route}', timeout=2) as response:
                    assert expected in response.read().decode('utf-8')
            print('PASS: installed CLI, packaged dashboard assets, and healthy server outside checkout')
        finally:
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=10)


if __name__ == '__main__':
    main()
