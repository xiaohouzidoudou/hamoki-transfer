import tempfile
import unittest
from pathlib import Path

from app import create_app, RATE, RATE_LOCK


class PairedTransferTests(unittest.TestCase):
    def setUp(self):
        with RATE_LOCK:
            RATE.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATA_DIR': self.tmp.name})
        self.pc = self.app.test_client()
        self.phone = self.app.test_client()
        self.headers = {'X-Hamoki-Client': '1'}

    def tearDown(self):
        self.tmp.cleanup()

    def test_pair_send_replace_and_revoke(self):
        response = self.pc.post('/api/private/create', json={'label': 'PC'}, headers=self.headers)
        self.assertEqual(response.status_code, 201)
        invite = response.json['invite']
        self.assertTrue(invite.startswith('HK-'))
        self.assertEqual(self.phone.post('/api/private/join', json={'invite': invite, 'label': 'Phone'}, headers=self.headers).status_code, 200)
        def send(client, text, **kwargs):
            return client.post('/api/private/send', data={'text': text, **kwargs}, headers=self.headers)
        self.assertEqual(send(self.pc, 'hello').status_code, 201)
        self.assertEqual(self.phone.get('/api/private/latest').json['text'], 'hello')
        self.assertEqual(send(self.phone, 'newest').status_code, 201)
        self.assertEqual(self.pc.get('/api/private/latest').json['text'], 'newest')
        file_response = self.pc.post('/api/private/send', data={'text': '', 'file': ( __import__('io').BytesIO(b'hello file'), 'sample.txt')},
                                   headers=self.headers, content_type='multipart/form-data')
        self.assertEqual(file_response.status_code, 201)
        latest = self.phone.get('/api/private/latest').json
        self.assertEqual(latest['text'], '')
        self.assertTrue(latest['has_file'])
        self.assertEqual(self.phone.get('/api/private/file').data, b'hello file')
        self.assertEqual(send(self.pc,'last').status_code, 201)
        self.assertFalse(self.phone.get('/api/private/latest').json['has_file'])
        self.assertEqual(list((Path(self.tmp.name) / 'private-files').iterdir()), [])
        devices = self.pc.get('/api/private/devices').json['devices']
        other = next(d['id'] for d in devices if not d['me'])
        self.assertEqual(self.pc.post('/api/private/revoke',json={'device_id':other},headers=self.headers).status_code,200)
        self.assertEqual(self.phone.get('/api/private/latest').status_code,401)

    def test_invite_view_and_reissue_preserve_devices(self):
        result = self.pc.post('/api/private/create', json={'label':'PC'}, headers=self.headers)
        original = result.json['invite']
        self.assertEqual(self.pc.get('/api/private/invite').json['invite'], original)
        self.assertEqual(self.phone.post('/api/private/join', json={'invite':original, 'label':'Phone'},headers=self.headers).status_code, 200)
        fresh = self.phone.post('/api/private/invite/reissue', json={},headers=self.headers).json['invite']
        self.assertNotEqual(original, fresh)
        self.assertEqual(self.pc.get('/api/private/invite').json['invite'], fresh)
        self.assertTrue(self.phone.get('/api/private/me').json['paired'])
        self.assertTrue(self.pc.get('/api/private/me').json['paired'])
        self.assertEqual(self.app.test_client().post('/api/private/join',json={'invite':original},headers=self.headers).status_code,403)
        self.assertEqual(self.app.test_client().post('/api/private/join',json={'invite':fresh},headers=self.headers).status_code,200)

    def test_legacy_room_can_reissue(self):
        result = self.pc.post('/api/private/create', json={'label':'PC'}, headers=self.headers)
        with self.app.app_context():
            import sqlite3
            con=sqlite3.connect(str(Path(self.tmp.name)/'index.sqlite3'))
            con.execute("UPDATE private_rooms SET invite_nonce=''")
            con.commit()
            con.close()
        self.assertTrue(self.pc.get('/api/private/invite').json['needs_reissue'])
        self.assertEqual(self.pc.post('/api/private/invite/reissue',json={},headers=self.headers).status_code,200)
        self.assertTrue(self.pc.get('/api/private/invite').json['available'])

    def test_rename_device_and_room_isolation(self):
        created = self.pc.post('/api/private/create', json={'label':'我的设备'},headers=self.headers).json
        joined = self.phone.post('/api/private/join',json={'invite':created['invite'],'label':'我的设备'},headers=self.headers).json
        device_id = joined['device_id']
        renamed = self.pc.post('/api/private/rename',json={'device_id':device_id,'name':'安卓手机'},headers=self.headers)
        self.assertEqual(renamed.status_code,200)
        rows = self.pc.get('/api/private/devices').json['devices']
        self.assertEqual(next(row['label'] for row in rows if row['id']==device_id),'安卓手机')
        self.assertEqual(self.pc.post('/api/private/rename',json={'device_id':device_id,'name':' '},headers=self.headers).status_code,400)
        self.assertEqual(self.pc.post('/api/private/rename',json={'device_id':'0'*24,'name':'别人设备'},headers=self.headers).status_code,404)
        self.assertTrue(self.phone.get('/api/private/me').json['paired'])

    def test_reject_unpaired_and_csrf(self):
        self.assertEqual(self.phone.get('/api/private/latest').status_code,401)
        self.assertEqual(self.pc.post('/api/private/create',json={'label':'PC'}).status_code,403)


if __name__=='__main__':
    unittest.main()
