"""Deterministic synthetic readings and durable survey storage."""
import math
import sqlite3
import threading
from datetime import datetime, timezone
from .planning import InvalidInput, coordinate, identifier, scheduled_time, text

PROFILES = ('baseline', 'turbid', 'low-oxygen')
SENSOR_FIELDS = ('temperature_c', 'ph', 'dissolved_oxygen_mg_l', 'turbidity_ntu')
SAMPLE_FIELDS = ('timestamp', 'simulated', 'latitude', 'longitude', *SENSOR_FIELDS, 'profile')


def reading(sample, profile='baseline'):
    if not isinstance(sample, int) or sample < 0:
        raise ValueError('sample must be a nonnegative integer')
    if profile not in PROFILES:
        raise ValueError('Unknown simulation profile')
    phase = sample / 12
    return {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'simulated': True,
        'latitude': 22.5726,
        'longitude': 88.3639,
        'temperature_c': round(25 + math.sin(phase), 2),
        'ph': round(7.2 + 0.2 * math.sin(phase / 2), 2),
        'dissolved_oxygen_mg_l': round((3 if profile == 'low-oxygen' else 7) + 0.5 * math.cos(phase), 2),
        'turbidity_ntu': round((30 if profile == 'turbid' else 5) + 2 * math.sin(phase / 3), 2),
        'profile': profile,
    }


class Store:
    def __init__(self, path):
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY, started TEXT NOT NULL, ended TEXT);
            CREATE TABLE IF NOT EXISTS samples (
                id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL, simulated INTEGER NOT NULL,
                latitude REAL, longitude REAL, temperature_c REAL, ph REAL,
                dissolved_oxygen_mg_l REAL, turbidity_ntu REAL);
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                latitude REAL NOT NULL, longitude REAL NOT NULL, notes TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS observation_plans (
                id INTEGER PRIMARY KEY, location_id INTEGER NOT NULL,
                scheduled_for TEXT NOT NULL, notes TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'planned');
        ''')
        session_columns = {row[1] for row in self.db.execute('PRAGMA table_info(sessions)')}
        if 'location_id' not in session_columns:
            self.db.execute('ALTER TABLE sessions ADD COLUMN location_id INTEGER')
        if 'plan_id' not in session_columns:
            self.db.execute('ALTER TABLE sessions ADD COLUMN plan_id INTEGER')
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(samples)')}
        if 'profile' not in columns:
            self.db.execute("ALTER TABLE samples ADD COLUMN profile TEXT NOT NULL DEFAULT 'baseline'")
        self.db.execute('CREATE INDEX IF NOT EXISTS samples_session ON samples(session_id)')
        # A previous process cannot still own an active recording.
        self.db.execute("UPDATE observation_plans SET status='interrupted' WHERE status='recording'")
        self.db.execute('UPDATE sessions SET ended=? WHERE ended IS NULL', (self.now(),))
        self.db.commit()
        self.active = None

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    def start(self, location_id=None, plan_id=None):
        if location_id is not None:
            identifier(location_id, 'location_id')
        if plan_id is not None:
            identifier(plan_id, 'plan_id')
        with self.lock:
            if self.active is not None:
                raise ValueError('A session is already recording')
            if plan_id is not None:
                plan = self.db.execute('SELECT location_id,status FROM observation_plans WHERE id=?', (plan_id,)).fetchone()
                if plan is None:
                    raise KeyError('Plan not found')
                if plan[1] not in ('planned', 'interrupted'):
                    raise ValueError('Only planned or interrupted observations can be recorded')
                if location_id is not None and location_id != plan[0]:
                    raise InvalidInput('Selected location does not match the plan')
                location_id = plan[0]
            if location_id is not None and not self.db.execute('SELECT 1 FROM locations WHERE id=?', (location_id,)).fetchone():
                raise KeyError('Location not found')
            with self.db:
                session_id = self.db.execute('INSERT INTO sessions(started,location_id,plan_id) VALUES (?,?,?)', (self.now(), location_id, plan_id)).lastrowid
                if plan_id is not None:
                    self.db.execute("UPDATE observation_plans SET status='recording' WHERE id=?", (plan_id,))
            self.active = session_id
            return self.active

    def stop(self):
        with self.lock:
            if self.active is None:
                raise ValueError('No session is recording')
            session_id = self.active
            with self.db:
                self.db.execute('UPDATE sessions SET ended=? WHERE id=?', (self.now(), session_id))
                self.db.execute("UPDATE observation_plans SET status='completed' WHERE id=(SELECT plan_id FROM sessions WHERE id=?)", (session_id,))
            self.active = None
            return session_id

    def append(self, value):
        with self.lock:
            if self.active is not None:
                self.db.execute('''INSERT INTO samples(session_id,timestamp,simulated,latitude,
                    longitude,temperature_c,ph,dissolved_oxygen_mg_l,turbidity_ntu,profile)
                    VALUES (?,?,?,?,?,?,?,?,?,?)''', (self.active, *(value[field] for field in SAMPLE_FIELDS)))
                self.db.commit()

    def sessions(self):
        with self.lock:
            cursor = self.db.execute('''SELECT s.id,s.started,s.ended,s.location_id,s.plan_id,l.name
                FROM sessions s LEFT JOIN locations l ON l.id=s.location_id ORDER BY s.id DESC''')
            return [dict(zip(('id', 'started', 'ended', 'location_id', 'plan_id', 'location_name'), row)) for row in cursor.fetchall()]

    def export(self, session_id):
        with self.lock:
            if not self.db.execute('SELECT 1 FROM sessions WHERE id=?', (session_id,)).fetchone():
                raise KeyError(session_id)
            cursor = self.db.execute('SELECT timestamp,simulated,latitude,longitude,temperature_c,ph,dissolved_oxygen_mg_l,turbidity_ntu,profile FROM samples WHERE session_id=? ORDER BY id', (session_id,))
            return [column[0] for column in cursor.description], cursor.fetchall()

    def summary(self, session_id):
        with self.lock:
            session = self.db.execute('SELECT started,ended,location_id,plan_id FROM sessions WHERE id=?', (session_id,)).fetchone()
            if session is None:
                raise KeyError(session_id)
            count, first, last = self.db.execute('SELECT COUNT(*),MIN(timestamp),MAX(timestamp) FROM samples WHERE session_id=?', (session_id,)).fetchone()
            metrics = {}
            aggregates = self.db.execute('''SELECT
                MIN(temperature_c),MAX(temperature_c),AVG(temperature_c),
                MIN(ph),MAX(ph),AVG(ph),
                MIN(dissolved_oxygen_mg_l),MAX(dissolved_oxygen_mg_l),AVG(dissolved_oxygen_mg_l),
                MIN(turbidity_ntu),MAX(turbidity_ntu),AVG(turbidity_ntu)
                FROM samples WHERE session_id=?''', (session_id,)).fetchone()
            for index, field in enumerate(SENSOR_FIELDS):
                minimum, maximum, mean = aggregates[index * 3:index * 3 + 3]
                metrics[field] = {'min': minimum, 'max': maximum, 'mean': round(mean, 3) if mean is not None else None}
            profiles = [row[0] for row in self.db.execute('SELECT DISTINCT profile FROM samples WHERE session_id=? ORDER BY profile', (session_id,))]
            return {'session_id': session_id, 'started': session[0], 'ended': session[1],
                    'simulated': True, 'sample_count': count, 'first_sample': first,
                    'last_sample': last, 'profiles': profiles, 'metrics': metrics,
                    'location_id': session[2], 'plan_id': session[3]}

    def create_location(self, name, latitude, longitude, notes=''):
        name = text(name, 'name', 80)
        notes = text(notes, 'notes', 500, required=False)
        latitude = coordinate(latitude, 'latitude', -90, 90)
        longitude = coordinate(longitude, 'longitude', -180, 180)
        with self.lock, self.db:
            try:
                return self.db.execute('INSERT INTO locations(name,latitude,longitude,notes) VALUES (?,?,?,?)', (name, latitude, longitude, notes)).lastrowid
            except sqlite3.IntegrityError as error:
                raise ValueError('A location with that name already exists') from error

    def locations(self):
        with self.lock:
            rows = self.db.execute('SELECT id,name,latitude,longitude,notes FROM locations ORDER BY name,id').fetchall()
            return [dict(zip(('id', 'name', 'latitude', 'longitude', 'notes'), row)) for row in rows]

    def create_plan(self, location_id, scheduled_for, notes=''):
        identifier(location_id, 'location_id')
        date = scheduled_time(scheduled_for)
        notes = text(notes, 'notes', 500, required=False)
        with self.lock, self.db:
            if not self.db.execute('SELECT 1 FROM locations WHERE id=?', (location_id,)).fetchone():
                raise KeyError('Location not found')
            return self.db.execute('INSERT INTO observation_plans(location_id,scheduled_for,notes) VALUES (?,?,?)', (location_id, date, notes)).lastrowid

    def plans(self):
        with self.lock:
            rows = self.db.execute('''SELECT p.id,p.location_id,l.name,p.scheduled_for,p.notes,p.status
                FROM observation_plans p JOIN locations l ON l.id=p.location_id ORDER BY p.scheduled_for,p.id''').fetchall()
            return [dict(zip(('id', 'location_id', 'location_name', 'scheduled_for', 'notes', 'status'), row)) for row in rows]

    def cancel_plan(self, plan_id):
        identifier(plan_id, 'plan_id')
        with self.lock, self.db:
            plan = self.db.execute('SELECT status FROM observation_plans WHERE id=?', (plan_id,)).fetchone()
            if plan is None:
                raise KeyError('Plan not found')
            if plan[0] not in ('planned', 'interrupted'):
                raise ValueError('Only planned or interrupted observations can be cancelled')
            self.db.execute("UPDATE observation_plans SET status='cancelled' WHERE id=?", (plan_id,))

    def comparison(self):
        with self.lock:
            rows = self.db.execute('''SELECT l.id,l.name,COUNT(DISTINCT s.id),COUNT(v.id),
                AVG(v.temperature_c),AVG(v.ph),AVG(v.dissolved_oxygen_mg_l),AVG(v.turbidity_ntu)
                FROM locations l LEFT JOIN sessions s ON s.location_id=l.id
                LEFT JOIN samples v ON v.session_id=s.id GROUP BY l.id,l.name ORDER BY l.name,l.id''').fetchall()
            return [{'location_id': row[0], 'location_name': row[1], 'session_count': row[2],
                     'sample_count': row[3], 'simulated': True,
                     'means': {field: round(row[index + 4], 3) if row[index + 4] is not None else None
                               for index, field in enumerate(SENSOR_FIELDS)}} for row in rows]

    def series(self, session_id, limit=120):
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
            raise ValueError('limit must be an integer between 1 and 500')
        with self.lock:
            if not self.db.execute('SELECT 1 FROM sessions WHERE id=?', (session_id,)).fetchone():
                raise KeyError(session_id)
            rows = self.db.execute('''SELECT timestamp,simulated,latitude,longitude,
                temperature_c,ph,dissolved_oxygen_mg_l,turbidity_ntu,profile
                FROM samples WHERE session_id=? ORDER BY id DESC LIMIT ?''',
                (session_id, limit)).fetchall()
            samples = [dict(zip(SAMPLE_FIELDS, row)) for row in reversed(rows)]
            for sample in samples:
                sample['simulated'] = bool(sample['simulated'])
            return {'session_id': session_id, 'simulated': True, 'limit': limit, 'samples': samples}

    def close(self):
        with self.lock:
            try:
                if self.active is not None:
                    with self.db:
                        self.db.execute('UPDATE sessions SET ended=? WHERE id=?', (self.now(), self.active))
                        self.db.execute("UPDATE observation_plans SET status='interrupted' WHERE id=(SELECT plan_id FROM sessions WHERE id=?)", (self.active,))
                    self.active = None
            finally:
                self.db.close()
