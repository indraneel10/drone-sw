# Survey planning — Water Monitor 1.1

Survey planning saves observation locations and schedules, then labels synthetic
recordings for later comparison. Existing surveys remain available without labels.

## Use the planner

1. Install the updated app with `python -m pip install --upgrade .` in your venv,
   then launch `water-monitor` with your usual database path.
2. In **Add sampling location**, enter a unique name, latitude, longitude and
   optional notes. Saved markers appear in the offline coordinate overview.
3. Choose a location and observation time in **Schedule an observation**. The
   browser converts your local time to UTC for storage, then displays it locally.
4. Select that plan under **Optional planning label for this synthetic recording**.
   Start and stop recording manually using the existing recording controls.
5. Review the survey summary/trends, compare the synthetic means under each
   location label, or download survey JSON and the planner JSON.

The coordinate overview is a schematic latitude/longitude plot with an automatic
scale, not a shoreline basemap. Markers are numbered and full coordinates are in
the list below. Identical/nearby locations may overlap; the list preserves them.
There is no network dependency for the plot.

## Recording labels and data

Planning coordinates identify intended observation locations. Assigning a label
only associates the recording with that location; it does not change sensor
samples or their fixed simulated coordinates. Location comparisons are explicitly
synthetic, combine all tagged samples, and may include different simulation
profiles. Means are weighted by sample count, not by number of sessions. Empty
locations show no measurements. Unassigned surveys are excluded from location
comparisons and remain available in recording history.

The planner does not start recordings at scheduled times. A passed scheduled time
is informational. There is no connection to a physical vessel.

## Plan status

| Status | Meaning |
| --- | --- |
| planned | Observation label/schedule saved; recording has not started |
| recording | A manually started synthetic survey is linked to this plan |
| completed | The linked recording was explicitly stopped by the operator |
| interrupted | The app closed or restarted during the linked recording |
| cancelled | Operator cancelled a planned/interrupted observation |

Planned or interrupted observations can be selected for a new recording or
cancelled. Completed and cancelled plans cannot be recorded again; create a new
plan for a repeat observation. A recording shutdown preserves its samples and
marks the plan interrupted. A retry creates a separate survey linked to the same
plan. Status describes software recording activity, not completion of physical
fieldwork. A completed recording may contain zero samples if stopped immediately.

## Validation and persistence

Location names are unique without regard to case and contain 1–80 characters.
Latitude is between -90 and 90, longitude between -180 and 180; values must be
finite numbers. Notes contain up to 500 characters. Schedules require an ISO
8601 timestamp with a timezone. Past timestamps are allowed for retrospective
organization. IDs must be positive integers and refer to existing records.

The same SQLite backup preserves plans, locations and recordings. Existing
records migrate automatically with no assigned location/plan. This release adds
creation and cancellation; editing/deleting locations or schedules and importing
planner JSON are not implemented. Planner JSON is an export, not a control file.

## API

POST requests require `X-Monitor-Request: 1`, `Content-Type: application/json`,
a JSON object, and a body of at most 4096 bytes. Invalid fields return 400,
missing records 404, and state conflicts 409. Existing empty-body start/stop
requests still work for unassigned surveys.

| Method | Path | JSON fields / response |
| --- | --- | --- |
| GET | `/api/locations` | Saved locations |
| POST | `/api/locations` | `name`, `latitude`, `longitude`, optional `notes` |
| GET | `/api/plans` | Plans with UTC timestamps and status |
| POST | `/api/plans` | `location_id`, `scheduled_for`, optional `notes` |
| POST | `/api/plans/cancel` | `plan_id` |
| POST | `/api/sessions/start` | Optional `location_id` or `plan_id` |
| GET | `/api/comparison` | Per-location sample-weighted synthetic means and counts |
| GET | `/api/planning/export` | Download locations/plans as JSON |

A `plan_id` resolves its saved location automatically. If both IDs are supplied,
they must match. Survey JSON adds a `planning` object with `location_id`,
`plan_id` and `association_only: true`. CSV retains the existing sample schema;
use survey JSON or the session/summary API for planning associations.
