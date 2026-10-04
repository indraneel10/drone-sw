# Water Monitor 1.0 — Completion and run guide

## Delivered scope

This release is a local, civilian environmental monitoring simulator. All sensor
readings and coordinates are synthetic. The software runs on a laptop without
any vessel or sensor hardware.

| Area | Delivered behavior |
| --- | --- |
| Sensor simulation | Temperature, pH, dissolved oxygen and turbidity; three profiles |
| Sampling | Independent background sampling, configurable from 0.1 to 60 seconds |
| Dashboard | Latest readings, fixed simulated station and connection/health status |
| Survey recording | Start/stop, durable SQLite history and interrupted-session recovery |
| Analysis | Per-survey count, minimum, mean, maximum and four recent trend charts |
| Export | Complete JSON and CSV recordings with simulation flags and profiles |
| Installation | Python wheel, bundled dashboard assets and `water-monitor` command |
| Process lifecycle | Single CLI owner per database, shutdown finalization, concise startup errors |
| Automated checks | Unit/API/process tests, Windows/Linux installation checks, browser acceptance |
| Security checks | Bandit, Python/JavaScript CodeQL and weekly Actions dependency checks |

The workflow status on GitHub is the current verification result. Windows skips
one POSIX SIGTERM test; graceful Windows shutdown is exercised through shared
cleanup logic and process installation checks. Chromium acceptance runs on Linux.
It checks interaction and mobile overflow and saves desktop/mobile screenshots.
It does not certify every browser or device.

## Windows quick start

From PowerShell in your local repository folder:

```powershell
git pull
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\water-monitor.exe --profile turbid --database survey.sqlite3
```

Open http://127.0.0.1:8080. Record some samples, choose **View survey**, inspect the
summary/charts, stop recording, and download JSON or CSV. Exit with Ctrl+C.
Relaunch with the same database path to verify history persists.

To update an existing installation after pulling code:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade .
```

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip wheel . --no-deps --wheel-dir dist
.\.venv\Scripts\python.exe tests/check_install.py dist
```

Use an empty `dist` directory when testing a different version; the installation
check expects exactly one application wheel. CI starts from a clean checkout.

Browser verification requires Node.js and development-only Playwright tooling:

```bash
npm install --no-save --ignore-scripts playwright@1.58.2
npx playwright install chromium
node tests/browser_smoke.cjs
```

Linux machines may require `npx playwright install --with-deps chromium`.
Browser tooling is not an application runtime dependency.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Port is occupied | Launch with `--port 8090` and open the matching URL |
| Database is locked | Stop the other monitor using that database, or select a different file |
| Database path cannot be opened | Select an existing writable local folder |
| Different survey history appears | Use the same `--database` path; relative paths depend on the working folder |
| Dashboard says stale/degraded | Inspect the terminal for database errors, then restart after resolving the cause |
| Installed command not found | Use the full `.venv\Scripts\water-monitor.exe` path or activate the venv |

For backup, exit the app and copy the SQLite file. Keep recordings on local
storage. The neighboring `.lock` file can remain after exit and is not survey data.
The lock protects app CLI instances; external database tools must be managed
separately.

## Limits and remaining work

- Browser/server access is local to the machine; authentication and network hosting
  are not delivered.
- Sensor calibration and physical measurements are not delivered. Synthetic
  readings cannot establish water safety or drinking-water suitability.
- Position is a fixed fictional station. There is no motion model or vehicle
  integration.
- CSV/JSON full exports are held in memory; large or long-running datasets need
  further scalability work.
- Real sensors, camera observation, production operations and hardware acceptance
  are separate projects with separate requirements and validation.

The completion claim applies to the monitoring simulator described above.
