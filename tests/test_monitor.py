import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from water_monitor.model import Store, reading
from water_monitor.server import Application, handler_for

class StoreTests(unittest.TestCase):
    def test_ranges(self):
        for index in range(500):
            value=reading(index)
            self.assertTrue(value['simulated'])
            self.assertTrue(7 <= value['ph'] <= 7.4)
            self.assertTrue(3 <= value['turbidity_ntu'] <= 7)
        with self.assertRaises(ValueError): reading(-1)

    def test_record_export_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.db'
            store=Store(path)
            store.append(reading(0))
            first=store.start()
            with self.assertRaises(ValueError): store.start()
            store.append(reading(1))
            self.assertEqual(store.stop(),first)
            store.append(reading(2))
            columns,rows=store.export(first)
            self.assertEqual(len(rows),1)
            self.assertEqual(dict(zip(columns,rows[0]))['simulated'],1)
            with self.assertRaises(ValueError): store.stop()
            with self.assertRaises(KeyError): store.export(999)
            store.start();store.close()
            recovered=Store(path)
            self.assertTrue(all(item['ended'] for item in recovered.sessions()))
            self.assertEqual(len(recovered.export(first)[1]),1)
            recovered.close()

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(':memory:');self.app=Application(self.store)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.app))
        self.thread=threading.Thread(target=self.server.serve_forever);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown();self.thread.join();self.server.server_close();self.store.close()
    def fetch(self,path,method='GET',headers=None):
        return urlopen(Request(self.base+path,method=method,headers=headers or {}),timeout=3)
    def test_endpoints(self):
        with self.fetch('/api/telemetry') as response:self.assertTrue(json.load(response)['simulated'])
        with self.assertRaises(HTTPError) as error:self.fetch('/api/sessions/start','POST')
        self.assertEqual(error.exception.code,403)
        with self.fetch('/api/sessions/start','POST',{'X-Monitor-Request':'1'}) as response:session=json.load(response)['session_id']
        self.store.append(reading(0))
        with self.fetch(f'/api/export/{session}') as response:self.assertIn('simulated',response.read().decode())
        with self.fetch('/api/sessions/stop','POST',{'X-Monitor-Request':'1'}) as response:self.assertEqual(response.status,200)
        for path in ['/api/export/bad','/api/export/999','/../model.py']:
            with self.assertRaises(HTTPError) as error:self.fetch(path)
            self.assertEqual(error.exception.code,404)
        with self.fetch('/') as response:self.assertIn('SIMULATED DATA',response.read().decode())
    def test_independent_sampling(self):
        self.store.start();self.app.worker.start();self.app.finished.wait(1.2)
        self.app.finished.set();self.app.worker.join()
        self.assertGreaterEqual(len(self.store.export(1)[1]),2)

if __name__=='__main__':unittest.main()
