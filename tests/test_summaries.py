import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import test_monitor
from water_monitor.model import Store, reading
from water_monitor.server import Application


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(':memory:')
    def tearDown(self):
        self.store.close()
    def test_empty_and_known_statistics(self):
        session = self.store.start()
        empty = self.store.summary(session)
        self.assertEqual(empty['sample_count'], 0)
        self.assertIsNone(empty['metrics']['ph']['mean'])
        for index, value in enumerate([6.0, 8.0]):
            sample = reading(index, 'turbid')
            sample['ph'] = value
            # Recording must not rely on dictionary insertion order.
            self.store.append(dict(reversed(list(sample.items()))))
        summary = self.store.summary(session)
        self.assertEqual(summary['sample_count'], 2)
        self.assertEqual(summary['profiles'], ['turbid'])
        self.assertEqual(summary['metrics']['ph'], {'min': 6.0, 'max': 8.0, 'mean': 7.0})
        with self.assertRaises(KeyError): self.store.summary(999)
    def test_profiles_and_validation(self):
        self.assertGreater(reading(0, 'turbid')['turbidity_ntu'], 25)
        self.assertLess(reading(0, 'low-oxygen')['dissolved_oxygen_mg_l'], 4)
        with self.assertRaises(ValueError): reading(0, 'unknown')
        for interval in [0, float('nan'), float('inf'), 61]:
            with self.assertRaises(ValueError): Application(self.store, interval=interval)
    def test_health_reports_dead_sampler(self):
        app = Application(self.store)
        self.assertEqual(app.health()['status'], 'degraded')
        app.worker.start()
        try: self.assertEqual(app.health()['status'], 'ok')
        finally: app.finished.set(); app.worker.join()
        self.assertEqual(app.health()['status'], 'degraded')

    def test_old_database_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'old.db'
            db = sqlite3.connect(path)
            db.executescript('''CREATE TABLE sessions(id INTEGER PRIMARY KEY,started TEXT NOT NULL,ended TEXT);
                CREATE TABLE samples(id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,simulated INTEGER NOT NULL,latitude REAL,longitude REAL,
                temperature_c REAL,ph REAL,dissolved_oxygen_mg_l REAL,turbidity_ntu REAL);
                INSERT INTO sessions VALUES(1,'2026-01-01',NULL);
                INSERT INTO samples VALUES(1,1,'2026-01-01T00:00:00+00:00',1,22,88,25,7,7,5);''')
            db.close()
            migrated = Store(path)
            try:
                self.assertEqual(migrated.summary(1)['profiles'], ['baseline'])
                self.assertEqual(migrated.summary(1)['sample_count'], 1)
            finally: migrated.close()


class SummaryHTTPTests(unittest.TestCase):
    setUp = test_monitor.HTTPTests.setUp
    tearDown = test_monitor.HTTPTests.tearDown
    fetch = test_monitor.HTTPTests.fetch
    def test_summary_api(self):
        session = self.store.start()
        self.store.append(reading(0, 'low-oxygen'))
        with self.fetch(f'/api/summary/{session}') as response:
            value = json.load(response)
            self.assertEqual(value['sample_count'], 1)
            self.assertEqual(value['profiles'], ['low-oxygen'])
