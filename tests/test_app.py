import io
import os
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='hamoki-import-'))

from app import RATE, create_app, valid_code, make_code, DIGITS, LETTERS


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
        self.assertEqual(len(code), 4)
        self.assertTrue(any(c in DIGITS for c in code))
        self.assertTrue(any(c in LETTERS for c in code))
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
        self.assertEqual(len(code), 4)
        self.assertTrue(any(c in DIGITS for c in code))
        self.assertTrue(any(c in LETTERS for c in code))
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
        self.assertEqual(len(res.json['code']), 4)

    def test_four_character_alphanumeric_collision(self):
        with patch('app.make_code', side_effect=['A2C3', 'A2C3', 'B4D5']):
            first = self.send_text('first').json['code']
            second = self.send_text('second').json['code']
        self.assertEqual(first, 'A2C3')
        self.assertEqual(second, 'B4D5')
        self.assertEqual(self.client.post('/api/text/A2C3').json['text'], 'first')
        self.assertEqual(self.client.post('/api/text/B4D5').json['text'], 'second')

    def test_legacy_four_digit_numeric_still_supported(self):
        legacy = '0007'
        with sqlite3.connect(os.path.join(self.dir.name, 'index.sqlite3')) as con:
            con.execute('INSERT INTO shares VALUES (?,?,?,?,?,?,?,?)',
                        (legacy, 'text', '临时文字.txt', 10, 'old four digits',
                         int(time.time()) + 3600, 5, int(time.time())))
        self.assertTrue(valid_code(legacy))
        self.assertEqual(self.client.post('/api/text/0007').json['text'], 'old four digits')

    def test_old_twelve_character_code_remains_redeemable(self):
        legacy = 'ABCDEFGHJKLM'
        with sqlite3.connect(os.path.join(self.dir.name, 'index.sqlite3')) as con:
            con.execute('INSERT INTO shares VALUES (?,?,?,?,?,?,?,?)',
                        (legacy, 'text', '临时文字.txt', 10, 'old-content',
                         int(time.time()) + 3600, 5, int(time.time())))
        self.assertTrue(valid_code(legacy))
        self.assertEqual(self.client.get('/api/item/' + legacy).status_code, 200)
        self.assertEqual(self.client.post('/api/text/' + legacy).json['text'], 'old-content')
        self.assertEqual(self.client.get('/api/qr/' + legacy).status_code, 200)

    def test_invalid_codes_are_rejected(self):
        for code in ('001', '01234', '12?A', 'I123', '123456789012'):
            self.assertFalse(valid_code(code))

    def test_public_direct_file_link_and_download_limit(self):
        response = self.client.post('/api/send', data={
            'file': (io.BytesIO(b'direct-link'), 'hello.txt'),
            'ttl': '1h',
        })
        self.assertEqual(response.status_code, 201)
        direct_path = response.json['public_path']
        self.assertTrue(direct_path.startswith('/f/'))
        self.assertNotIn(response.json['code'], direct_path)
        for i in range(5):
            with self.client.get(direct_path) as result:
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.data, b'direct-link')
                self.assertIn('attachment', result.headers['Content-Disposition'])
        self.assertEqual(self.client.get(direct_path).status_code, 404)

    def test_public_direct_text_link(self):
        response = self.send_text('Direct plain text')
        url = response.json['public_path']
        result = self.client.get(url)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data.decode('utf8'), 'Direct plain text')
        self.assertIn('text/plain', result.headers['Content-Type'])

    def test_public_combined_link_shows_text_and_download(self):
        response = self.client.post('/api/send', data={
            'file': (io.BytesIO(b'test-image'), 'a.png'),
            'text': 'private note',
        })
        direct_path = response.json['public_path']
        webpage = self.client.get(direct_path)
        self.assertEqual(webpage.status_code, 200)
        self.assertIn(b'private note', webpage.data)
        self.assertIn(b'?download=1', webpage.data)
        self.assertEqual(self.client.get('/api/item/' + response.json['code']).json['remaining'], 5)
        with self.client.get(direct_path + '?download=1') as file:
            self.assertEqual(file.status_code, 200)
            self.assertEqual(file.data, b'test-image')

    def test_public_link_rejects_missing_or_invalid_token(self):
        self.assertEqual(self.client.get('/f/short').status_code, 404)
        self.assertEqual(self.client.get('/f/' + 'A' * 22).status_code, 404)

    def test_four_digit_access_has_per_ip_rate_limit(self):
        code = self.send_text('safe').json['code']
        for _ in range(12):
            self.assertEqual(self.client.get('/api/item/' + code).status_code, 200)
        self.assertEqual(self.client.get('/api/item/' + code).status_code, 429)
        self.assertEqual(self.client.post('/api/text/' + code).status_code, 429)
        self.assertEqual(self.client.get('/api/qr/' + code).status_code, 429)

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
