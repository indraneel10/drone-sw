"""Deterministic synthetic readings and durable survey storage."""
import math
import sqlite3
import threading
from datetime import datetime, timezone


def reading(sample):
    if not isinstance(sample, int) or sample < 0:
        raise ValueError('sample must be a nonnegative integer')
    phase = sample / 12
    return {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'simulated': True,
        'latitude': 22.5726,
        'longitude': 88.3639,
        'temperature_c': round(25 + math.sin(phase), 2),
        'ph': round(7.2 + 0.2 * math.sin(phase / 2), 2),
        'dissolved_oxygen_mg_l': round(7 + 0.5 * math.cos(phase), 2),
        'turbidity_ntu': round(5 + 2 * math.sin(phase / 3), 2),
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
                    longitude,temperature_c,ph,dissolved_oxygen_mg_l,turbidity_ntu)
                    VALUES (?,?,?,?,?,?,?,?,?)''', (self.active, *value.values()))
                self.db.commit()

    def sessions(self):
        with self.lock:
            cursor = self.db.execute('SELECT id,started,ended FROM sessions ORDER BY id DESC')
            return [dict(zip(('id', 'started', 'ended'), row)) for row in cursor.fetchall()]

    def export(self, session_id):
        with self.lock:
            if not self.db.execute('SELECT 1 FROM sessions WHERE id=?', (session_id,)).fetchone():
                raise KeyError(session_id)
            cursor = self.db.execute('SELECT timestamp,simulated,latitude,longitude,temperature_c,ph,dissolved_oxygen_mg_l,turbidity_ntu FROM samples WHERE session_id=? ORDER BY id', (session_id,))
            return [column[0] for column in cursor.description], cursor.fetchall()

    def close(self):
        with self.lock:
            self.db.close()
