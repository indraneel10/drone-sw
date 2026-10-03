"""Deterministic synthetic readings and durable survey storage."""
import math
import sqlite3
import threading
from datetime import datetime, timezone

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
        ''')
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(samples)')}
        if 'profile' not in columns:
            self.db.execute("ALTER TABLE samples ADD COLUMN profile TEXT NOT NULL DEFAULT 'baseline'")
        self.db.execute('CREATE INDEX IF NOT EXISTS samples_session ON samples(session_id)')
        # A previous process cannot still own an active recording.
        self.db.execute('UPDATE sessions SET ended=? WHERE ended IS NULL', (self.now(),))
        self.db.commit()
        self.active = None

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    def start(self):
        with self.lock:
            if self.active is not None:
                raise ValueError('A session is already recording')
            self.active = self.db.execute('INSERT INTO sessions(started) VALUES (?)', (self.now(),)).lastrowid
            self.db.commit()
            return self.active

    def stop(self):
        with self.lock:
            if self.active is None:
                raise ValueError('No session is recording')
            session_id = self.active
            self.db.execute('UPDATE sessions SET ended=? WHERE id=?', (self.now(), session_id))
            self.db.commit()
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
            cursor = self.db.execute('SELECT id,started,ended FROM sessions ORDER BY id DESC')
            return [dict(zip(('id', 'started', 'ended'), row)) for row in cursor.fetchall()]

    def export(self, session_id):
        with self.lock:
            if not self.db.execute('SELECT 1 FROM sessions WHERE id=?', (session_id,)).fetchone():
                raise KeyError(session_id)
            cursor = self.db.execute('SELECT timestamp,simulated,latitude,longitude,temperature_c,ph,dissolved_oxygen_mg_l,turbidity_ntu,profile FROM samples WHERE session_id=? ORDER BY id', (session_id,))
            return [column[0] for column in cursor.description], cursor.fetchall()

    def summary(self, session_id):
        with self.lock:
            session = self.db.execute('SELECT started,ended FROM sessions WHERE id=?', (session_id,)).fetchone()
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
                    'last_sample': last, 'profiles': profiles, 'metrics': metrics}

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
            self.db.close()
