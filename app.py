"""Hamoki Transfer: small original browser-only temporary file handoff service."""
from __future__ import annotations

from contextlib import contextmanager
import io
import mimetypes
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from urllib.parse import quote

import qrcode
from qrcode.image.svg import SvgPathImage
from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

# Minimal container images may lack system MIME mappings for WebP avatars.
mimetypes.add_type('image/webp', '.webp')

ALPHABET = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'
DIGITS = '23456789'
LETTERS = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
TTL = {'1h': 3600, '24h': 86400, '7d': 7 * 86400}
LOCK = threading.RLock()
RATE_LOCK = threading.Lock()
RATE = {}


class InsufficientStorage(HTTPException):
    code = 507
    description = '服务器临时存储空间不足'


def make_code():
    # Always include both a digit and a letter; omit easy-to-confuse I/O/0/1.
    chars = [
        secrets.choice(DIGITS),
        secrets.choice(LETTERS),
        secrets.choice(ALPHABET),
        secrets.choice(ALPHABET),
    ]
    secrets.SystemRandom().shuffle(chars)
    return ''.join(chars)


def valid_code(code):
    # Older four-digit numerical and original twelve-character codes remain valid.
    return (len(code) == 4 and all(ch in ALPHABET + '01' for ch in code)) or (
        len(code) == 12 and all(ch in ALPHABET for ch in code)
    )


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        DATA_DIR=os.environ.get('DATA_DIR', '/data'),
        PUBLIC_URL=os.environ.get('PUBLIC_URL', ''),
        MAX_UPLOAD_MB=int(os.environ.get('MAX_UPLOAD_MB', '5120')),
        TOTAL_BYTES=int(os.environ.get('TOTAL_LIMIT_MB', '10240')) * 1024 * 1024,
        TESTING=False,
    )
    if test_config:
        app.config.update(test_config)
    # Allow multipart framing overhead while enforcing the exact file-byte limit.
    app.config['MAX_FILE_BYTES'] = int(app.config['MAX_UPLOAD_MB']) * 1024 * 1024
    app.config['MAX_CONTENT_LENGTH'] = app.config['MAX_FILE_BYTES'] + 1024 * 1024
    # Only our loopback-bound reverse proxy is trusted to append the client IP.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

    root = Path(app.config['DATA_DIR']).resolve()
    files = root / 'files'
    files.mkdir(parents=True, exist_ok=True)
    db_path = root / 'index.sqlite3'

    @contextmanager
    def db():
        con = sqlite3.connect(db_path, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    with db() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS shares (
            code TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK(kind IN ('file','text')),
            name TEXT NOT NULL,
            size INTEGER NOT NULL,
            body TEXT,
            expires INTEGER NOT NULL,
            remaining INTEGER NOT NULL DEFAULT 10,
            created INTEGER NOT NULL
        )''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_shares_expires ON shares(expires)')
        # Separate capability URLs: short manual codes and long direct links.
        # Keeps the existing shares schema and old pickup codes untouched.
        con.execute('''CREATE TABLE IF NOT EXISTS public_links (
            token TEXT PRIMARY KEY,
            code TEXT NOT NULL UNIQUE
        )''')

    def cleanup():
        now = int(time.time())
        with LOCK, db() as con:
            expired = con.execute('SELECT code, kind FROM shares WHERE expires <= ?', (now,)).fetchall()
            for row in expired:
                if row['kind'] == 'file':
                    (files / row['code']).unlink(missing_ok=True)
            con.execute('DELETE FROM shares WHERE expires <= ?', (now,))
            con.execute('DELETE FROM public_links WHERE code NOT IN (SELECT code FROM shares)')

    def clean_loop():
        while True:
            time.sleep(300)
            try:
                cleanup()
            except Exception:
                app.logger.exception('cleanup error')

    if not app.config['TESTING']:
        threading.Thread(target=clean_loop, daemon=True, name='hamoki-cleaner').start()

    def limit(action, count, window=60):
        address = request.remote_addr or 'unknown'
        k = (action, address)
        now = time.monotonic()
        with RATE_LOCK:
            # bounded housekeeping for the in-process limiter
            if len(RATE) > 10000:
                RATE.clear()
            entries = [t for t in RATE.get(k, ()) if now - t < window]
            if len(entries) >= count:
                abort(429, description='操作过于频繁，请稍后重试')
            entries.append(now)
            RATE[k] = entries

    @app.after_request
    def set_headers(resp):
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['Referrer-Policy'] = 'no-referrer'
        resp.headers['X-Frame-Options'] = 'DENY'
        resp.headers['Content-Security-Policy'] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'"
        )
        if request.path.startswith(('/api/', '/d/', '/f/')):
            resp.headers['Cache-Control'] = 'no-store'
        return resp

    @app.errorhandler(HTTPException)
    def http_error(err):
        if request.path.startswith('/api/'):
            return jsonify(error=err.description), err.code
        return err

    @app.route('/')
    def home():
        return render_template('index.html')

    @app.route('/health')
    def health():
        return jsonify(ok=True)

    @app.post('/api/send')
    def upload():
        limit('upload', 10)
        ttl = request.form.get('ttl', '24h')
        if ttl not in TTL:
            abort(400, description='保存时间不正确')
        uploaded = request.files.get('file')
        body = request.form.get('text', '')
        body = body.strip()
        has_file = bool(uploaded and uploaded.filename)
        if not has_file and not body:
            abort(400, description='请选择文件或输入文字，可以同时发送')
        text_bytes = len(body.encode('utf-8'))
        if text_bytes > 65536:
            abort(400, description='文字长度不能超过 65536 字节')
        now = int(time.time())
        code = make_code()
        kind = 'file' if has_file else 'text'
        pending = None
        if kind == 'file':
            name = uploaded.filename.replace('\\', '/').split('/')[-1].strip()[:200]
            if not name:
                abort(400, description='文件名不正确')
            pending = files / ('.' + secrets.token_hex(16) + '.upload')
            try:
                uploaded.save(pending)
                size = pending.stat().st_size
                if size == 0:
                    abort(400, description='不能上传空文件')
                if size > app.config['MAX_FILE_BYTES']:
                    abort(413, description='单个文件不能超过 5 GB')
            except Exception:
                pending.unlink(missing_ok=True)
                raise
        else:
            name = '临时文字.txt'
            size = text_bytes
        try:
            with LOCK, db() as con:
                used = con.execute("SELECT COALESCE(SUM(size),0) FROM shares WHERE kind='file' AND expires > ?", (now,)).fetchone()[0]
                if kind == 'file' and used + size > app.config['TOTAL_BYTES']:
                    raise InsufficientStorage()
                for _ in range(150):
                    if not con.execute('SELECT 1 FROM shares WHERE code=?', (code,)).fetchone():
                        break
                    code = make_code()
                else:
                    abort(503, description='当前可用取件码不足，请稍后再试')
                if pending:
                    os.replace(pending, files / code)
                con.execute('INSERT INTO shares VALUES (?,?,?,?,?,?,?,?)', (code, kind, name, size, body, now + TTL[ttl], 10, now))
                token = secrets.token_urlsafe(15)
                for _ in range(5):
                    if not con.execute('SELECT 1 FROM public_links WHERE token=?', (token,)).fetchone():
                        break
                    token = secrets.token_urlsafe(15)
                else:
                    abort(503, description='生成分享链接失败，请重试')
                con.execute('INSERT INTO public_links (token, code) VALUES (?, ?)', (token, code))
        finally:
            if pending:
                pending.unlink(missing_ok=True)
        return jsonify(
            code=code, ttl=ttl, size=size, name=name,
            has_text=bool(body), has_file=has_file, created=now, expires=now + TTL[ttl],
            public_path='/f/' + token
        ), 201

    def lookup_share(code):
        if not valid_code(code):
            abort(404, description='取件码不存在')
        with db() as con:
            row = con.execute('SELECT * FROM shares WHERE code=? AND expires > ? AND remaining > 0', (code, int(time.time()))).fetchone()
        if row is None:
            abort(404, description='取件码不存在或已过期')
        return row

    def limit_short_code_access(code):
        if len(code) == 4:
            # Short codes can be guessed: throttle ALL lookup and pickup
            # paths together per client IP, including direct download URLs.
            limit('short-code-access-minute', 12)
            limit('short-code-access-hour', 60, 3600)

    @app.get('/api/item/<code>')
    def lookup(code):
        limit('lookup', 40)
        limit_short_code_access(code)
        row = lookup_share(code.upper())
        return jsonify(
            code=row['code'], name=row['name'], kind=row['kind'],
            size=row['size'], expires=row['expires'], remaining=row['remaining'],
            has_text=bool(row['body']), has_file=row['kind'] == 'file'
        )

    def consume(code, expected_kind):
        with LOCK, db() as con:
            if expected_kind == 'text':
                row = con.execute(
                    "SELECT * FROM shares WHERE code=? AND body IS NOT NULL AND body != '' AND expires > ? AND remaining > 0",
                    (code, int(time.time()))
                ).fetchone()
            else:
                row = con.execute(
                    "SELECT * FROM shares WHERE code=? AND kind=? AND expires > ? AND remaining > 0",
                    (code, expected_kind, int(time.time()))
                ).fetchone()
            if row is None:
                abort(404, description='取件码不存在或已过期')
            # For a combined share, only downloading the file counts toward
            # its ten downloads; revealing the accompanying text does not.
            if expected_kind != 'text' or row['kind'] == 'text':
                con.execute('UPDATE shares SET remaining=remaining-1 WHERE code=?', (code,))
            return row

    @app.post('/api/text/<code>')
    def get_text(code):
        limit('pickup', 30)
        limit_short_code_access(code)
        row = consume(code.upper(), 'text')
        return jsonify(text=row['body'])

    @app.get('/d/<code>')
    def download(code):
        limit('pickup', 30)
        limit_short_code_access(code)
        row = consume(code.upper(), 'file')
        path = files / row['code']
        if not path.is_file():
            abort(404, description='文件不存在或已被删除')
        return send_file(path, mimetype='application/octet-stream', as_attachment=True, download_name=row['name'], max_age=0)

    @app.get('/f/<token>')
    def public_link(token):
        # A long random token allows direct delivery without entering a short code.
        if not 16 <= len(token) <= 64 or any(ch not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for ch in token):
            abort(404)
        limit('public-link', 40)
        with db() as con:
            row = con.execute(
                '''SELECT s.* FROM public_links p JOIN shares s ON s.code=p.code
                   WHERE p.token=? AND s.expires>? AND s.remaining>0''',
                (token, int(time.time()))
            ).fetchone()
        if row is None:
            abort(404, description='分享链接不存在或已经过期')
        if row['kind'] == 'text':
            # Text-only links still use one of the ten available text pickups.
            item = consume(row['code'], 'text')
            return render_template('public_share.html', has_file=False,
                                   name=row['name'], text=item['body'], expires=row['expires'])
        if request.args.get('download') != '1':
            # Show the waiting screen immediately; the browser starts one
            # download in the background after the landing page is visible.
            return render_template('public_share.html', has_file=True,
                                   name=row['name'], text=row['body'], expires=row['expires'])
        path = files / row['code']
        if not path.is_file():
            abort(404, description='文件不存在或已经删除')
        item = consume(row['code'], 'file')
        return send_file(path, mimetype='application/octet-stream',
                         as_attachment=True, download_name=item['name'], max_age=0)

    @app.get('/api/qr/<code>')
    def qr(code):
        limit_short_code_access(code)
        lookup_share(code.upper())
        base = app.config['PUBLIC_URL'].rstrip('/') or request.url_root.rstrip('/')
        url = base + '/?code=' + quote(code.upper(), safe='')
        svg = qrcode.make(url, image_factory=SvgPathImage)
        data = io.BytesIO()
        svg.save(data)
        data.seek(0)
        return send_file(data, mimetype='image/svg+xml', max_age=0)

    return app


app = create_app()
