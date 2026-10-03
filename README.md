# Civilian Water Monitor — WM-SIM-001

Local environmental monitoring demo: synthetic sensor readings, browser dashboard,
SQLite survey recordings, and CSV exports. No physical vessel or control integration.

## Run
Requires Python 3.11+. No third-party runtime dependencies.

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell, use instead:
.\.venv\Scripts\Activate.ps1
python -m water_monitor
```

Open http://127.0.0.1:8080. Start recording, wait for samples, stop recording,
and download the CSV. Ctrl+C stops the application.

Optional: `python -m water_monitor --port 8090 --database survey.sqlite3`.
Recordings persist in the working-directory SQLite file. Restart closes interrupted
sessions and preserves samples. Back up this file to preserve survey history.

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
CodeQL scans Python and JavaScript. Dependabot checks Actions weekly. No third-party
runtime dependencies exist in this milestone. Hosted scans must finish before their
results can be confirmed.

Acceptance: simulated readings and position display; independent sampling;
durable start/stop sessions and CSV export; interrupted-session recovery; tests
cover persistence, ranges, HTTP errors and independent sampling.

Real sensors, calibration, camera imagery, and deployment remain future work.


## WM-SIM-002 — Profiles and survey analysis

```bash
python -m water_monitor --profile turbid --interval 0.5
python -m water_monitor --profile low-oxygen --database low-oxygen.sqlite3
```

Profiles: `baseline` (original readings), `turbid` (higher synthetic turbidity),
and `low-oxygen` (lower synthetic dissolved oxygen). Profiles are demonstration
scenarios, not calibrated models or water-safety classifications. The interval
must be between 0.1 and 60 seconds. All samples record the selected profile.

Click **View summary** beside a survey for sample count and minimum, mean, and
maximum of each sensor. The summary is a snapshot; click again to refresh during
recording. An empty survey displays blank statistics. JSON is available from
`GET /api/summary/{id}`; unknown surveys return 404.

`GET /api/health` returns sampling interval, profile, sample age and status.
A stopped sampler or an overdue reading returns HTTP 503 (`degraded`). The
browser marks readings as potentially stale when health checks fail.

Existing databases migrate automatically: original samples are assigned the
`baseline` profile without deleting history. CSV exports now add a `profile`
column at the end; downstream importers should match columns by header name.
