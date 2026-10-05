import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import test_monitor
from water_monitor.model import Store, reading
from water_monitor.planning import InvalidInput


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(':memory:')
        self.location = self.store.create_location('Lake edge', 22.6, 88.4, 'Observe water appearance')
    def tearDown(self):
        self.store.close()

    def test_validation_and_unique_names(self):
        for value in [91, -91, float('nan'), float('inf'), True, '22', 10**300]:
            with self.subTest(value=value), self.assertRaises(InvalidInput):
                self.store.create_location('Other', value, 88)
        with self.assertRaises(ValueError): self.store.create_location('LAKE EDGE', 0, 0)
        with self.assertRaises(InvalidInput): self.store.create_location('', 0, 0)
        with self.assertRaises(InvalidInput): self.store.create_location('Other', 0, 181)
        with self.assertRaises(InvalidInput): self.store.create_location('Other', 0, 0, notes='x'*501)
        with self.assertRaises(InvalidInput): self.store.create_plan(self.location, '2026-10-10T12:00:00')
        with self.assertRaises(InvalidInput): self.store.create_plan(True, '2026-10-10T12:00:00Z')
        with self.assertRaises(KeyError): self.store.create_plan(999, '2026-10-10T12:00:00Z')

    def test_schedule_timezone_and_lifecycle(self):
        plan = self.store.create_plan(self.location, '2026-10-10T12:00:00+05:30', 'Scheduled observation')
        self.assertEqual(self.store.plans()[0]['scheduled_for'], '2026-10-10T06:30:00+00:00')
        self.assertEqual(self.store.plans()[0]['status'], 'planned')
        session = self.store.start(plan_id=plan)
        self.assertEqual(self.store.sessions()[0]['location_id'], self.location)
        self.assertEqual(self.store.plans()[0]['status'], 'recording')
        with self.assertRaises(ValueError): self.store.cancel_plan(plan)
        self.store.append(reading(0))
        self.store.stop()
        self.assertEqual(self.store.plans()[0]['status'], 'completed')
        self.assertEqual(self.store.summary(session)['plan_id'], plan)
        with self.assertRaises(ValueError): self.store.start(plan_id=plan)
        other = self.store.create_plan(self.location, '2026-10-11T12:00:00Z')
        self.store.cancel_plan(other)
        with self.assertRaises(ValueError): self.store.start(plan_id=other)
        with self.assertRaises(ValueError): self.store.cancel_plan(other)

    def test_assignment_validation_and_atomicity(self):
        plan = self.store.create_plan(self.location, '2026-10-10T12:00:00Z')
        other = self.store.create_location('Other lake', 0, 0)
        for kwargs, error in [({'location_id': 999}, KeyError), ({'plan_id': 999}, KeyError),
                              ({'location_id': other, 'plan_id': plan}, InvalidInput)]:
            with self.assertRaises(error): self.store.start(**kwargs)
        self.assertIsNone(self.store.active)
        self.assertEqual(self.store.sessions(), [])
        self.assertEqual(self.store.plans()[0]['status'], 'planned')

    def test_comparison_weighted_by_samples_and_coordinates_unchanged(self):
        self.store.start(location_id=self.location)
        sample = reading(0); sample['ph'] = 6
        self.store.append(sample); self.store.stop()
        session = self.store.start(location_id=self.location)
        for index in range(3):
            value = reading(index, 'turbid'); value['ph'] = 8
            self.store.append(value)
        self.store.stop()
        result = self.store.comparison()[0]
        self.assertEqual(result['sample_count'], 4)
        self.assertEqual(result['session_count'], 2)
        self.assertEqual(result['means']['ph'], 7.5)
        self.assertEqual(self.store.series(session)['samples'][0]['latitude'], 22.5726)
        other = self.store.create_location('Unused', 0, 0)
        empty = next(row for row in self.store.comparison() if row['location_id'] == other)
        self.assertEqual(empty['sample_count'], 0)
        self.assertIsNone(empty['means']['ph'])

    def test_shutdown_preserves_interrupted_plan_for_manual_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'planning.sqlite3'
            store = Store(path)
            site = store.create_location('Station', 0, 0)
            plan = store.create_plan(site, '2026-10-10T12:00:00Z')
            store.start(plan_id=plan); store.append(reading(0)); store.close()
            reopened = Store(path)
            try:
                self.assertEqual(reopened.plans()[0]['status'], 'interrupted')
                self.assertEqual(reopened.comparison()[0]['sample_count'], 1)
                reopened.start(plan_id=plan); reopened.stop()
                self.assertEqual(reopened.plans()[0]['status'], 'completed')
            finally: reopened.close()

    def test_existing_recordings_migrate_without_assignment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'old.sqlite3'
            with closing(sqlite3.connect(path)) as db:
                db.executescript('''CREATE TABLE sessions(id INTEGER PRIMARY KEY,started TEXT NOT NULL,ended TEXT);
                    INSERT INTO sessions VALUES(1,'2026-01-01T00:00:00+00:00','2026-01-01T00:00:01+00:00');''')
            store = Store(path)
            try:
                self.assertEqual(len(store.sessions()), 1)
                self.assertIsNone(store.sessions()[0]['location_id'])
                self.assertEqual(store.plans(), [])
            finally: store.close()


class PlanningHTTPTests(unittest.TestCase):
    setUp = test_monitor.HTTPTests.setUp
    tearDown = test_monitor.HTTPTests.tearDown
    fetch = test_monitor.HTTPTests.fetch
    def post(self, path, data):
        return urlopen(Request(self.base+path, method='POST', data=json.dumps(data).encode(), headers={'X-Monitor-Request':'1', 'Content-Type':'application/json'}), timeout=3)

    def test_location_plan_assigned_recording_and_export(self):
        with self.post('/api/locations', {'name':'Lake edge','latitude':22.6,'longitude':88.4}) as response:
            self.assertEqual(response.status, 201); location = json.load(response)['location_id']
        with self.post('/api/plans', {'location_id':location,'scheduled_for':'2026-10-10T12:00:00+05:30'}) as response:
            plan = json.load(response)['plan_id']
        with self.post('/api/sessions/start', {'plan_id':plan}) as response: session = json.load(response)['session_id']
        self.store.append(reading(0))
        with self.post('/api/sessions/stop', {}) as response: self.assertEqual(response.status, 200)
        with self.fetch('/api/comparison') as response: self.assertEqual(json.load(response)[0]['sample_count'], 1)
        with self.fetch(f'/api/export/{session}?format=json') as response:
            exported = json.load(response)
            self.assertEqual(exported['planning']['location_id'], location)
            self.assertTrue(exported['planning']['association_only'])
        with self.fetch('/api/planning/export') as response:
            data = json.load(response)
            self.assertEqual(data['plans'][0]['status'], 'completed')
            self.assertEqual(data['locations'][0]['name'], 'Lake edge')

    def test_invalid_payloads_return_400_and_missing_references_404(self):
        cases = [('/api/locations', [], 400), ('/api/locations', {}, 400),
                 ('/api/locations', {'name':'x','latitude':999,'longitude':0}, 400),
                 ('/api/locations', {'name':'x','latitude':0,'longitude':0,'unsupported':1}, 400),
                 ('/api/plans', {'location_id':999,'scheduled_for':'2026-10-10T12:00:00Z'}, 404),
                 ('/api/sessions/start', {'location_id':999}, 404),
                 ('/api/plans/cancel', {'plan_id':999}, 404)]
        for path, data, status in cases:
            with self.subTest(path=path,data=data):
                with self.assertRaises(HTTPError) as error: self.post(path,data)
                self.assertEqual(error.exception.code, status); error.exception.close()
        bad = Request(self.base+'/api/locations', method='POST', data=b'{bad', headers={'X-Monitor-Request':'1','Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as error: urlopen(bad,timeout=3)
        self.assertEqual(error.exception.code,400); error.exception.close()
