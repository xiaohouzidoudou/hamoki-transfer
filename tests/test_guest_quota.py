import io
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app import RATE, RATE_LOCK, create_app


class GuestUploadQuotaTests(unittest.TestCase):
    def setUp(self):
        with RATE_LOCK:
            RATE.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.conf = {'TESTING': True, 'DATA_DIR': self.temp.name,
                     'GUEST_DAILY_BYTES': 10, 'TOTAL_BYTES': 100,
                     'UPLOAD_UNLOCK_PASSWORD': 'example-testing-secret'}
        self.app = create_app(self.conf)
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def test_rolling_guest_daily_limit_and_persistence(self):
        self.assertEqual(self.client.post('/api/send', data={'text':'1234567'}).status_code, 201)
        quota = self.client.get('/api/upload/quota').json
        self.assertEqual(quota['used_bytes'], 7)
        self.assertEqual(quota['remaining_bytes'], 3)
        self.assertFalse(quota['unlocked'])
        self.assertEqual(self.client.post('/api/send',data={'text':'ABCD'}).status_code,429)
        self.assertEqual(self.client.get('/api/upload/quota').json['used_bytes'],7)
        self.assertEqual(self.client.post('/api/send',data={'text':'ABC'}).status_code,201)
        self.assertEqual(self.client.post('/api/send',data={'text':'A'}).json['code'],'guest_quota_exceeded')
        restarted = create_app(self.conf)
        self.assertEqual(restarted.test_client().get('/api/upload/quota').json['used_bytes'],10)

    def test_guest_ip_separation(self):
        self.assertEqual(self.client.post('/api/send',data={'text':'1234567890'}).status_code,201)
        other = self.app.test_client()
        self.assertEqual(other.post('/api/send',data={'text':'x'},environ_overrides={'REMOTE_ADDR':'198.51.100.20'}).status_code,201)

    def test_unlock_cookie_and_guest_bypass(self):
        self.assertEqual(self.client.post('/api/send',data={'text':'1234567890'}).status_code,201)
        self.assertEqual(self.client.post('/api/upload/unlock',json={'password':'wrong'},
                headers={'X-Hamoki-Client':'1'}).status_code,403)
        self.assertEqual(self.client.post('/api/upload/unlock',json={'password':'example-testing-secret'}).status_code,403)
        ok = self.client.post('/api/upload/unlock',json={'password':'example-testing-secret'},
                headers={'X-Hamoki-Client':'1'})
        self.assertEqual(ok.status_code,200)
        self.assertTrue(self.client.get('/api/upload/quota').json['unlocked'])
        self.assertEqual(self.client.post('/api/send',data={'text':'bypassed'}).status_code,201)
        self.assertEqual(self.client.get('/api/upload/quota').json['used_bytes'],10)
        other = self.app.test_client()
        self.assertFalse(other.get('/api/upload/quota').json['unlocked'])

    def test_file_counting_and_global_capacity(self):
        # File bytes are charged to the daily quota; storage limit is shared.
        self.assertEqual(self.client.post('/api/send',data={'file':(io.BytesIO(b'12345678'),'a.txt')}).status_code,201)
        self.assertEqual(self.client.get('/api/upload/quota').json['used_bytes'],8)
        self.assertEqual(self.client.post('/api/send',data={'file':(io.BytesIO(b'abc'),'b.txt')}).status_code,429)
        self.assertEqual(self.client.post('/api/upload/unlock',json={'password':'example-testing-secret'},
            headers={'X-Hamoki-Client':'1'}).status_code,200)
        self.app.config['TOTAL_BYTES'] = 9
        self.assertEqual(self.client.post('/api/send',data={'file':(io.BytesIO(b'abc'),'c.txt')}).status_code,507)

    def test_old_events_expire_after_24h(self):
        self.assertEqual(self.client.post('/api/send',data={'text':'1234567890'}).status_code,201)
        path = Path(self.temp.name) / 'index.sqlite3'
        with sqlite3.connect(path) as con:
            con.execute('UPDATE guest_uploads SET created=?', (int(time.time())-86402,))
        self.assertEqual(self.client.get('/api/upload/quota').json['remaining_bytes'],10)
        self.assertEqual(self.client.post('/api/send',data={'text':'1234567890'}).status_code,201)

    def test_unconfigured_password_fails_closed(self):
        app=create_app({**self.conf, 'UPLOAD_UNLOCK_PASSWORD':''})
        client=app.test_client()
        self.assertEqual(client.post('/api/upload/unlock',json={'password':'anything'},headers={'X-Hamoki-Client':'1'}).status_code,403)

if __name__=='__main__':
    unittest.main()
