"""Hamoki Transfer: small original browser-only temporary file handoff service."""
from __future__ import annotations

from contextlib import contextmanager
import io
import hashlib
import hmac
import mimetypes
import zipfile
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

import qrcode
from qrcode.image.svg import SvgPathImage
from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from itsdangerous import TimestampSigner, BadSignature, SignatureExpired
from private_channel import setup_private

# Minimal container images may lack system MIME mappings for WebP avatars.
mimetypes.add_type('image/webp', '.webp')

ALPHABET = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'
DIGITS = '23456789'
LETTERS = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
TTL = {'1d': 86400, '3d': 3 * 86400, '7d': 7 * 86400,
       '1h': 3600, '24h': 86400}  # Legacy API compatibility; new UI defaults to 3d.
LOCK = threading.RLock()
RATE_LOCK = threading.Lock()
RATE = {}


class InsufficientStorage(HTTPException):
    code = 507
    description = '网盘可用容量不足，请等候过期文件自动清理后重试'


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
        GUEST_DAILY_BYTES=int(os.environ.get('GUEST_DAILY_MB', '1024')) * 1024 * 1024,
        UPLOAD_UNLOCK_PASSWORD=os.environ.get('UPLOAD_UNLOCK_PASSWORD', ''),
        CLEANUP_INTERVAL_SECONDS=int(os.environ.get('CLEANUP_INTERVAL_SECONDS', '300')), 
        TESTING=False,
    )
    if test_config:
        app.config.update(test_config)
    # Allow multipart framing overhead while enforcing the exact file-byte limit.
    app.config['MAX_FILE_BYTES'] = int(app.config['MAX_UPLOAD_MB']) * 1024 * 1024
    app.config['MAX_CONTENT_LENGTH'] = app.config['MAX_FILE_BYTES'] + 2 * 1024 * 1024
    # Only our loopback-bound reverse proxy is trusted to append the client IP.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

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
        con.execute('''CREATE TABLE IF NOT EXISTS guest_uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_hash TEXT NOT NULL,
            created INTEGER NOT NULL,
            bytes INTEGER NOT NULL CHECK(bytes >= 0)
        )''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_guest_uploads_ip_time ON guest_uploads(ip_hash, created)')

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
            con.execute('DELETE FROM guest_uploads WHERE created <= ?', (now - 86400,))

    def clean_loop():
        interval = max(1, app.config['CLEANUP_INTERVAL_SECONDS'])
        while True:
            time.sleep(interval)
            try:
                cleanup()
            except Exception:
                app.logger.exception('cleanup error')

    # Reclaim expired disk files and share tokens immediately after a restart.
    # The background worker then repeats deletion every 5 minutes by default.
    cleanup()
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

    # Upload unlock uses a signed, expiring browser cookie. The password itself
    # lives ONLY in the instance environment, never in source code or cookies.
    unlock_secret_path = root / '.upload-access-secret'
    try:
        upload_key = unlock_secret_path.read_bytes()
    except FileNotFoundError:
        try:
            fd = os.open(unlock_secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as output:
                output.write(secrets.token_bytes(32))
        except FileExistsError:
            pass
        upload_key = unlock_secret_path.read_bytes()
    if len(upload_key) != 32:
        raise RuntimeError('invalid upload-access secret')
    upload_signer = TimestampSigner(upload_key, salt='hamoki-public-upload-v1')
    unlock_cookie = 'hamoki_upload_unlocked'

    def upload_unlocked():
        if not app.config['UPLOAD_UNLOCK_PASSWORD']:
            return False
        token = request.cookies.get(unlock_cookie, '')
        try:
            return upload_signer.unsign(token, max_age=86400) == b'unlocked'
        except (BadSignature, SignatureExpired):
            return False

    def guest_ip_hash():
        # Hash the visitor IP so the SQLite ledger does not store raw addresses.
        ip = request.remote_addr or 'unknown'
        return hmac.new(upload_key, ip.encode('utf-8'), hashlib.sha256).hexdigest()

    def guest_used(con, now, ip_hash):
        return con.execute(
            'SELECT COALESCE(SUM(bytes),0) FROM guest_uploads WHERE ip_hash=? AND created>?',
            (ip_hash, now - 86400)
        ).fetchone()[0]

    def guest_quota_error(used):
        return jsonify(
            error='今日访客上传额度已用完，请输入上传口令继续上传',
            code='guest_quota_exceeded',
            limit_bytes=app.config['GUEST_DAILY_BYTES'],
            used_bytes=used
        ), 429

    @app.get('/api/upload/quota')
    def public_upload_quota():
        now = int(time.time())
        with db() as con:
            used = guest_used(con, now, guest_ip_hash())
        return jsonify(unlocked=upload_unlocked(),
                       used_bytes=used,
                       limit_bytes=app.config['GUEST_DAILY_BYTES'],
                       remaining_bytes=max(0, app.config['GUEST_DAILY_BYTES'] - used))

    @app.post('/api/upload/unlock')
    def public_upload_unlock():
        limit('upload-unlock', 5, 3600)
        if request.headers.get('X-Hamoki-Client') != '1':
            abort(403, description='无效的请求来源')
        origin = request.headers.get('Origin')
        if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
            abort(403, description='无效的请求来源')
        provided = (request.get_json(silent=True) or {}).get('password', '')
        configured = app.config['UPLOAD_UNLOCK_PASSWORD']
        if not isinstance(provided, str) or len(provided) > 128 or not configured or not hmac.compare_digest(provided, configured):
            abort(403, description='上传口令不正确')
        resp = jsonify(ok=True)
        resp.set_cookie(unlock_cookie, upload_signer.sign(b'unlocked').decode('ascii'),
                        max_age=86400, httponly=True, secure=not app.config['TESTING'],
                        samesite='Strict', path='/')
        return resp

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

    setup_private(app, db, files, LOCK, limit)

    @app.route('/')
    def home():
        return render_template('index.html')

    @app.route('/health')
    def health():
        return jsonify(ok=True)

    @app.post('/api/send')
    def upload():
        limit('upload', 10)
        ttl = request.form.get('ttl', '3d')
        if ttl not in TTL:
            abort(400, description='保存时间不正确')
        uploads = [item for item in request.files.getlist('file') if item.filename]
        if len(uploads) > 500:
            abort(400, description='一次最多选择 500 个文件')
        mode = request.form.get('selection', 'single')
        if mode not in ('single', 'multiple', 'folder'):
            abort(400, description='文件选择方式不正确')
        body = request.form.get('text', '').strip()
        has_file = bool(uploads)
        if not has_file and not body:
            abort(400, description='请选择文件或输入文字，可以同时发送')
        text_bytes = len(body.encode('utf-8'))
        if text_bytes > 65536:
            abort(400, description='文字长度不能超过 65536 字节')
        now = int(time.time())
        guest_bypass = upload_unlocked()
        visitor_hash = guest_ip_hash() if not guest_bypass else ''
        if not guest_bypass and request.content_length is not None:
            # Fast reject clearly oversized guest requests before buffering files.
            with db() as con:
                already_used = guest_used(con, now, visitor_hash)
            remaining = max(0, app.config['GUEST_DAILY_BYTES'] - already_used)
            if request.content_length > remaining + 2 * 1024 * 1024:
                return guest_quota_error(already_used)
        code = make_code()
        kind = 'file' if has_file else 'text'
        pending = None
        if kind == 'file':
            as_zip = len(uploads) > 1 or mode == 'folder'
            pending = files / ('.' + secrets.token_hex(16) + '.upload')
            try:
                if as_zip:
                    total = 0
                    names = set()
                    with zipfile.ZipFile(pending, 'w', compression=zipfile.ZIP_STORED,
                                         allowZip64=True) as archive:
                        for uploaded in uploads:
                            # Retain folder structure inside ZIP but never trust client paths.
                            raw = uploaded.filename.replace('\\', '/')
                            components = raw.split('/')
                            if (len(components) > 16 or any(
                                not part or part in ('.', '..') or ':' in part or
                                len(part) > 200 or any(ord(ch) < 32 for ch in part)
                                for part in components
                            )):
                                abort(400, description='文件夹中存在不安全的文件名')
                            entry = '/'.join(components if mode == 'folder' else components[-1:])
                            if entry in names:
                                abort(400, description='包含重名文件，请重命名后重试')
                            names.add(entry)
                            with archive.open(entry, 'w', force_zip64=True) as target:
                                while True:
                                    chunk = uploaded.stream.read(1024 * 1024)
                                    if not chunk:
                                        break
                                    total += len(chunk)
                                    if total > app.config['MAX_FILE_BYTES'] - 1024 * 1024:
                                        abort(413, description='文件总大小不能超过 5 GB')
                                    target.write(chunk)
                    size = pending.stat().st_size
                    if size > app.config['MAX_FILE_BYTES']:
                        abort(413, description='文件总大小不能超过 5 GB')
                    if mode == 'folder':
                        folder = uploads[0].filename.replace('\\', '/').split('/')[0].strip()
                        name = (folder[:150] or '文件夹') + '.zip'
                    else:
                        name = f'{len(uploads)}个文件.zip'
                else:
                    uploaded = uploads[0]
                    name = uploaded.filename.replace('\\', '/').split('/')[-1].strip()[:200]
                    if not name:
                        abort(400, description='文件名不正确')
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
                private_used = con.execute("SELECT COALESCE(SUM(size),0) FROM private_rooms WHERE filekey != ''").fetchone()[0]
                if kind == 'file' and used + private_used + size > app.config['TOTAL_BYTES']:
                    raise InsufficientStorage()
                if not guest_bypass:
                    already_used = guest_used(con, now, visitor_hash)
                    if already_used + size > app.config['GUEST_DAILY_BYTES']:
                        return guest_quota_error(already_used)
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
                if not guest_bypass:
                    con.execute('INSERT INTO guest_uploads (ip_hash, created, bytes) VALUES (?,?,?)', (visitor_hash, now, size))
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
        if request.args.get('preview') == '1':
            if row['kind'] != 'file':
                abort(404)
            path = files / row['code']
            return send_file(path, mimetype=safe_image_type(path, row['name']),
                             as_attachment=False, max_age=0)
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

    def safe_image_type(path, name):
        extension = Path(name).suffix.lower()
        types = {
            '.png': ('image/png', lambda v: v.startswith(b'\x89PNG\r\n\x1a\n')),
            '.jpg': ('image/jpeg', lambda v: v.startswith(b'\xff\xd8\xff')),
            '.jpeg': ('image/jpeg', lambda v: v.startswith(b'\xff\xd8\xff')),
            '.gif': ('image/gif', lambda v: v.startswith((b'GIF87a', b'GIF89a'))),
            '.webp': ('image/webp', lambda v: v.startswith(b'RIFF') and v[8:12] == b'WEBP'),
        }
        if extension not in types or not path.is_file():
            abort(404, description='该文件不支持在线图片预览')
        with path.open('rb') as stream:
            signature = stream.read(16)
        mimetype, check = types[extension]
        if not check(signature):
            abort(404, description='该文件不支持在线图片预览')
        return mimetype

    @app.get('/api/preview/<code>')
    def preview(code):
        limit('preview', 30)
        limit_short_code_access(code)
        row = lookup_share(code.upper())
        if row['kind'] != 'file':
            abort(404, description='不是图片')
        path = files / row['code']
        mimetype = safe_image_type(path, row['name'])
        # Viewing an image does not spend a pickup/download.
        return send_file(path, mimetype=mimetype, as_attachment=False, max_age=0)

    @app.get('/api/qr/<code>')
    def qr(code):
        limit_short_code_access(code)
        lookup_share(code.upper())
        # Keep the original configured preview base for that hostname, but
        # generate links from the current trusted proxy hostname on a new domain.
        # This avoids leaking the preview subpath into dedicated deployments.
        configured = app.config['PUBLIC_URL'].rstrip('/')
        base = (configured if configured and
                urlsplit(configured).netloc.lower() == request.host.lower()
                else request.url_root.rstrip('/'))
        url = base + '/?code=' + quote(code.upper(), safe='')
        svg = qrcode.make(url, image_factory=SvgPathImage)
        data = io.BytesIO()
        svg.save(data)
        data.seek(0)
        return send_file(data, mimetype='image/svg+xml', max_age=0)

    return app


app = create_app()
