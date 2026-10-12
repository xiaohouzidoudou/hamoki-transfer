import io
import os
import sqlite3
import tempfile
import time
import unittest

os.environ.setdefault('UPLOAD_SECRET', 'x' * 32)
os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='hamoki-import-'))

from app import create_app


class HamokiTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.key = 'test-' + 'Z' * 27
        self.app = create_app({'TESTING': True, 'DATA_DIR': self.dir.name, 'UPLOAD_SECRET': self.key, 'TOTAL_BYTES': 10000})
        self.client = self.app.test_client()

    def tearDown(self):
        self.dir.cleanup()

    def send_text(self, content='https://example.net'):
        return self.client.post('/api/send', data={'text': content, 'ttl': '1h'}, headers={'X-Upload-Key': self.key})

    def test_text_and_pickup_limit(self):
        result = self.send_text()
        self.assertEqual(result.status_code, 201)
        code = result.json['code']
        self.assertEqual(len(code), 12)
        self.assertEqual(self.client.get('/api/item/' + code).json['remaining'], 5)
        svg = self.client.get('/api/qr/' + code)
        self.assertEqual(svg.status_code, 200)
        self.assertTrue(svg.data.startswith(b'<?xml') or b'<svg' in svg.data)
        for i in range(5):
            self.assertEqual(self.client.post('/api/text/' + code).json['text'], 'https://example.net')
        self.assertEqual(self.client.post('/api/text/' + code).status_code, 404)

    def test_file_upload_and_download(self):
        result = self.client.post('/api/send', data={'file': (io.BytesIO(b'bytes here'), 'hello.txt'), 'ttl': '24h'}, headers={'X-Upload-Key': self.key})
        self.assertEqual(result.status_code, 201)
        code = result.json['code']
        downloaded = self.client.get('/d/' + code)
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.data, b'bytes here')
        self.assertIn('attachment', downloaded.headers['Content-Disposition'])
        self.assertEqual(self.client.get('/api/item/' + code).json['remaining'], 4)

    def test_denied_unauthorized_upload(self):
        res = self.client.post('/api/send', data={'text': 'secret'})
        self.assertEqual(res.status_code, 403)

    def test_expiry(self):
        code = self.send_text('temporary').json['code']
        with sqlite3.connect(os.path.join(self.dir.name, 'index.sqlite3')) as con:
            con.execute('UPDATE shares SET expires=? WHERE code=?', (int(time.time()) - 1, code))
        self.assertEqual(self.client.get('/api/item/' + code).status_code, 404)

    def test_quota(self):
        res = self.client.post('/api/send', data={'file': (io.BytesIO(b'x' * 10001), 'big.txt')}, headers={'X-Upload-Key': self.key})
        self.assertEqual(res.status_code, 507)


if __name__ == '__main__':
    unittest.main()
