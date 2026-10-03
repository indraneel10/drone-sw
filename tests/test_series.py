import json
import unittest
from urllib.error import HTTPError

import test_monitor
from water_monitor.model import Store, reading


class SeriesTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(':memory:')
    def tearDown(self):
        self.store.close()
    def test_empty_order_limit_and_isolation(self):
        session = self.store.start()
        self.assertEqual(self.store.series(session)['samples'], [])
        for index in range(6):
            sample = reading(index, 'turbid')
            sample['timestamp'] = f'2026-01-01T00:00:0{index}+00:00'
            self.store.append(sample)
        series = self.store.series(session, 3)
        self.assertEqual(len(series['samples']), 3)
        self.assertEqual([row['timestamp'][-14:-6] for row in series['samples']], ['00:00:03', '00:00:04', '00:00:05'])
        self.assertTrue(all(row['simulated'] is True for row in series['samples']))
        self.store.stop()
        other = self.store.start()
        self.store.append(reading(10, 'low-oxygen'))
        self.assertEqual(len(self.store.series(other)['samples']), 1)
        self.assertEqual(len(self.store.series(session)['samples']), 6)
    def test_invalid_limits_and_unknown_session(self):
        for limit in [0, -1, 501, '10', True]:
            with self.assertRaises(ValueError): self.store.series(1, limit)
        with self.assertRaises(KeyError): self.store.series(999)


class SeriesHTTPTests(unittest.TestCase):
    setUp = test_monitor.HTTPTests.setUp
    tearDown = test_monitor.HTTPTests.tearDown
    fetch = test_monitor.HTTPTests.fetch
    def test_json_csv_and_series(self):
        session = self.store.start()
        for index in range(4): self.store.append(reading(index, 'turbid'))
        with self.fetch(f'/api/series/{session}?limit=2') as response:
            self.assertEqual(len(json.load(response)['samples']), 2)
        with self.fetch(f'/api/export/{session}?format=json') as response:
            self.assertIn('.json', response.headers['Content-Disposition'])
            result = json.load(response)
            self.assertEqual(result['session_id'], session)
            self.assertEqual(len(result['samples']), 4)
            self.assertTrue(result['samples'][0]['simulated'] is True)
        with self.fetch(f'/api/export/{session}') as response:
            self.assertIn('.csv', response.headers['Content-Disposition'])
            self.assertEqual(len(response.read().decode().splitlines()), 5)
    def test_error_responses(self):
        session = self.store.start()
        cases = [(f'/api/series/{session}?limit=0', 400),
                 (f'/api/series/{session}?limit=501', 400),
                 (f'/api/series/{session}?limit=abc', 400),
                 (f'/api/series/{session}?limit=1&limit=2', 400),
                 (f'/api/series/{session}?unexpected=1', 400),
                 ('/api/series/999', 404),
                 (f'/api/export/{session}?format=xml', 400),
                 (f'/api/export/{session}?format=json&format=csv', 400)]
        for path, expected in cases:
            with self.subTest(path=path):
                with self.assertRaises(HTTPError) as error: self.fetch(path)
                self.assertEqual(error.exception.code, expected)
