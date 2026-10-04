"""Install a built wheel into a fresh venv and exercise it outside the checkout."""
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main():
    wheelhouse = Path(sys.argv[1] if len(sys.argv) > 1 else 'dist').resolve()
    wheels = list(wheelhouse.glob('civilian_water_monitor-*.whl'))
    if len(wheels) != 1:
        raise RuntimeError('Expected exactly one built water monitor wheel')
    smoke = Path(__file__).with_name('installed_smoke.py').resolve()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / 'installed-env'
        venv.EnvBuilder(with_pip=True).create(root)
        python = root / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        subprocess.run([str(python), '-m', 'pip', 'install', '--no-index', '--no-deps', str(wheels[0])], check=True, timeout=60)
        subprocess.run([sys.executable, str(smoke), str(python)], check=True, timeout=45)


if __name__ == '__main__':
    main()
