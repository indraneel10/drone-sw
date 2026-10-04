# Civilian Water Monitor

Local environmental monitoring demo: synthetic sensor readings, browser dashboard,
SQLite survey recordings, and CSV exports. No physical vessel or control integration.

## Install and run
Requires Python 3.11+. The application has no third-party runtime dependencies.
Installation may download setuptools as a build tool.

Windows PowerShell, from your cloned `drone-sw` folder (activation is optional):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\water-monitor.exe --profile turbid
```

Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/water-monitor --profile turbid
```

Open http://127.0.0.1:8080. Start recording, wait for samples, stop recording,
and download the CSV or JSON. Choose **View survey** for summaries and trend charts.
Ctrl+C stops the application and closes any active recording. POSIX SIGTERM also
performs graceful cleanup; forced termination relies on recovery at next startup.

After installation, `water-monitor` (with the venv activated) or
`python -m water_monitor` can run from any directory. The database defaults to
`water-monitor.sqlite3` in that directory. Choose a consistent working directory
or an explicit `--database` path to keep using the same survey history.

Optional: `water-monitor --port 8090 --database survey.sqlite3 --interval 0.5`.
Keep the database and its folder writable. The app takes an operating-system lock
on a neighboring `.lock` file; another CLI process cannot use that database until
the first exits. A leftover lock file does not mean the database is still locked.
Do not remove the lock file while a process is running. Use local storage, with one
app instance per database. The lock protects this app's CLI instances; it does not
prevent other database tools from changing the file.

For a backup, stop the app, copy the SQLite database, and restart it. Restore by
pointing `--database` at the copied file. `.lock` files need not be backed up.
The source-folder launch `python -m water_monitor` remains available without
installation for development.

## Data and scope
Temperature (°C), pH, dissolved oxygen (mg/L), and turbidity (NTU) update once
per second independently of browser polling. Position represents a fixed fictional
observation station, with no vessel-motion model. API and CSV samples include a
simulation flag. Values cannot establish water safety or drinking-water suitability.
The dashboard marks connection loss and stale displayed readings.

The server binds only to localhost. This is a local demo, with no authentication
or production-network deployment support. POST recording requests require the
`X-Monitor-Request: 1` header and reject cross-site browser requests.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | /api/health | Process health |
| GET | /api/telemetry | Latest synthetic reading |
| GET | /api/sessions | Recording history |
| POST | /api/sessions/start | Start recording |
| POST | /api/sessions/stop | Stop recording |
| GET | /api/export/{id} | Download CSV |

## Verify
```bash
python -m unittest discover -s tests -v
python -m compileall -q water_monitor tests
```
CI tests Python 3.11/3.12 on Linux and Windows. Bandit scans application Python;
CI also builds a wheel and installs it into a fresh virtual environment on each
platform, then checks the installed CLI, health endpoint, and bundled dashboard
assets from outside the checkout. CodeQL scans Python and JavaScript. Dependabot checks Actions weekly. No third-party
runtime dependencies exist in this milestone. Hosted scans must finish before their
results can be confirmed.

Acceptance: simulated readings and position display; independent sampling;
durable start/stop sessions and CSV export; interrupted-session recovery; tests
cover persistence, ranges, HTTP errors and independent sampling.

Real sensors, calibration, camera imagery, and production deployment remain future work.


## WM-SIM-002 — Profiles and survey analysis

```bash
python -m water_monitor --profile turbid --interval 0.5
python -m water_monitor --profile low-oxygen --database low-oxygen.sqlite3
```

Profiles: `baseline` (original readings), `turbid` (higher synthetic turbidity),
and `low-oxygen` (lower synthetic dissolved oxygen). Profiles are demonstration
scenarios, not calibrated models or water-safety classifications. The interval
must be between 0.1 and 60 seconds. All samples record the selected profile.

Click **View survey** beside a survey for sample count and minimum, mean, and
maximum of each sensor. The selected survey refreshes during recording. An empty survey displays blank statistics. JSON is available from
`GET /api/summary/{id}`; unknown surveys return 404.

`GET /api/health` returns sampling interval, profile, sample age and status.
A stopped sampler or an overdue reading returns HTTP 503 (`degraded`). The
browser marks readings as potentially stale when health checks fail.

Existing databases migrate automatically: original samples are assigned the
`baseline` profile without deleting history. CSV exports now add a `profile`
column at the end; downstream importers should match columns by header name.

## WM-SIM-003 — Recorded trends and JSON export

Choose **View survey** beside any recording to display its summary and four
sensor trend charts. The selected survey refreshes automatically while recording.
Charts show up to the most recent 120 samples in chronological order, with sample
time on the horizontal axis and sensor units on the vertical axis. Each chart
uses its own automatic vertical scale. Single samples appear as a point; empty
surveys show an explicit message. Chart scales are not water-safety limits.

Both **Download CSV** and **Download JSON** preserve the full recording, including
simulation flags, UTC timestamps, and sensor profiles. JSON is suitable for
subsequent analysis and carries a session ID and sample array. Full exports are
built in memory; large recordings may require a later streaming implementation.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/series/{id}?limit=120` | Latest bounded sample window, oldest to newest |
| GET | `/api/export/{id}?format=json` | Complete survey as JSON |
| GET | `/api/export/{id}?format=csv` | Complete survey as CSV (default) |

The series limit must be an integer from 1 to 500. Unknown surveys return 404;
invalid or repeated query options return 400. Survey samples remain isolated
from other recordings. Download responses set attachment filenames.


## WM-SIM-004 — Installation and process lifecycle

The package installs the `water-monitor` command and includes HTML, JavaScript,
and CSS assets in the wheel. Closing the application finalizes its active survey;
startup still recovers recordings interrupted by a crash. Database recording
failures mark health degraded, log the exception, and prevent new recordings
until restart. Port conflicts, database locks, and unavailable database paths
produce a concise startup error instead of leaving resources open.

To verify the installation as CI does:

```bash
python -m pip wheel . --no-deps --wheel-dir dist
python tests/check_install.py dist
```

This installation check verifies serving packaged assets; it does not constitute
a browser visual-layout check. Browser layout remains to be verified separately.
