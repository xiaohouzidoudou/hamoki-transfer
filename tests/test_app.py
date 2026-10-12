import io
import os
import sqlite3
import tempfile
import time
import unittest

os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='hamoki-import-'))

from app import RATE, create_app


class HamokiTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        RATE.clear()
        self.app = create_app({'TESTING': True, 'DATA_DIR': self.dir.name, 'TOTAL_BYTES': 10000})
        self.client = self.app.test_client()

    def tearDown(self):
        self.dir.cleanup()

    def send_text(self, content='https://example.net'):
        return self.client.post('/api/send', data={'text': content, 'ttl': '1h'})

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
        result = self.client.post('/api/send', data={'file': (io.BytesIO(b'bytes here'), 'hello.txt'), 'ttl': '24h'})
        self.assertEqual(result.status_code, 201)
        code = result.json['code']
        downloaded = self.client.get('/d/' + code)
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.data, b'bytes here')
        self.assertIn('attachment', downloaded.headers['Content-Disposition'])
        self.assertEqual(self.client.get('/api/item/' + code).json['remaining'], 4)

    def test_combined_picture_and_text_one_code(self):
        payload = b'\\x89PNG\\r\\n\\x1a\\nhello'
        result = self.client.post('/api/send', data={
            'file': (io.BytesIO(payload), 'photo.png'),
            'text': '这张图片请一起收取',
            'ttl': '1h',
        })
        self.assertEqual(result.status_code, 201)
        code = result.json['code']
        self.assertTrue(result.json['has_file'])
        self.assertTrue(result.json['has_text'])
        self.assertEqual(len(code), 12)
        lookup = self.client.get('/api/item/' + code)
        self.assertEqual(lookup.status_code, 200)
        self.assertTrue(lookup.json['has_text'])
        self.assertTrue(lookup.json['has_file'])
        self.assertEqual(lookup.json['remaining'], 5)
        self.assertEqual(self.client.post('/api/text/' + code).json['text'], '这张图片请一起收取')
        self.assertEqual(self.client.get('/api/item/' + code).json['remaining'], 5)
        with self.client.get('/d/' + code) as downloaded:
            self.assertEqual(downloaded.status_code, 200)
            self.assertEqual(downloaded.data, payload)
        self.assertEqual(self.client.get('/api/item/' + code).json['remaining'], 4)
        self.assertEqual(self.client.post('/api/text/' + code).json['text'], '这张图片请一起收取')

    def test_text_limit_still_applies_when_image_present(self):
        result = self.client.post('/api/send', data={
            'file': (io.BytesIO(b'picture'), 'photo.jpg'),
            'text': '字' * 30000,
        })
        self.assertEqual(result.status_code, 400)

    def test_legacy_file_only_and_text_only_still_compatible(self):
        text = self.send_text('old sharing flow').json['code']
        self.assertTrue(self.client.get('/api/item/' + text).json['has_text'])
        self.assertFalse(self.client.get('/api/item/' + text).json['has_file'])
        self.assertEqual(self.client.post('/api/text/' + text).json['text'], 'old sharing flow')
        file_result = self.client.post('/api/send', data={'file': (io.BytesIO(b'old file'), 'legacy.txt')})
        filecode = file_result.json['code']
        self.assertFalse(self.client.get('/api/item/' + filecode).json['has_text'])
        self.assertTrue(self.client.get('/api/item/' + filecode).json['has_file'])
        with self.client.get('/d/' + filecode) as response:
            self.assertEqual(response.data, b'old file')

    def test_public_upload_without_key(self):
        res = self.client.post('/api/send', data={'text': 'hello, public upload'})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(len(res.json['code']), 12)

    def test_public_upload_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.send_text('rate test').status_code, 201)
        self.assertEqual(self.send_text('rate exceeded').status_code, 429)


    def test_expiry(self):
        code = self.send_text('temporary').json['code']
        with sqlite3.connect(os.path.join(self.dir.name, 'index.sqlite3')) as con:
            con.execute('UPDATE shares SET expires=? WHERE code=?', (int(time.time()) - 1, code))
        self.assertEqual(self.client.get('/api/item/' + code).status_code, 404)

    def test_quota(self):
        res = self.client.post('/api/send', data={'file': (io.BytesIO(b'x' * 10001), 'big.txt')})
        self.assertEqual(res.status_code, 507)


if __name__ == '__main__':
    unittest.main()
