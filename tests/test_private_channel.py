import tempfile
import unittest
from pathlib import Path

from app import create_app


class PairedTransferTests(unittest.TestCase):
    def setUp(self):
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

    def test_reject_unpaired_and_csrf(self):
        self.assertEqual(self.phone.get('/api/private/latest').status_code,401)
        self.assertEqual(self.pc.post('/api/private/create',json={'label':'PC'}).status_code,403)


if __name__=='__main__':
    unittest.main()
