"""Private paired-device clipboard beside the existing public transfer service."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import secrets
import sqlite3
import time
import zipfile

from flask import abort, jsonify, make_response, request, send_file

COOKIE = "hamoki_private_device"
CHARS = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
COOKIE_AGE = 400 * 86400


def digest(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def setup_private(app, db, files, lock, limit):
    storage = files.parent / "private-files"
    storage.mkdir(exist_ok=True)
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS private_rooms (
            id TEXT PRIMARY KEY,
            invite_hash TEXT UNIQUE NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            filename TEXT NOT NULL DEFAULT '',
            filekey TEXT NOT NULL DEFAULT '',
            size INTEGER NOT NULL DEFAULT 0,
            revision TEXT NOT NULL DEFAULT '',
            updated INTEGER NOT NULL DEFAULT 0,
            sender TEXT NOT NULL DEFAULT ''
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS private_devices (
            id TEXT PRIMARY KEY,
            room_id TEXT NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL,
            created INTEGER NOT NULL,
            seen INTEGER NOT NULL
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_private_devices_room ON private_devices(room_id)")

    def guard():
        # Non-simple custom header rejects cross-site HTML form CSRF; no CORS is enabled.
        if request.headers.get("X-Hamoki-Client") != "1":
            abort(403, description="请求来源不正确")
        origin = request.headers.get("Origin")
        if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
            abort(403, description="请求来源不正确")

    def auth():
        token = request.cookies.get(COOKIE, "")
        if len(token) != 64 or any(ch not in "0123456789abcdef" for ch in token):
            abort(401, description="设备未配对")
        with db() as con:
            device = con.execute("SELECT * FROM private_devices WHERE token_hash=?", (digest(token),)).fetchone()
        if device is None:
            abort(401, description="设备未配对")
        return device

    def set_cookie(response, token):
        response.set_cookie(
            COOKIE, token, max_age=COOKIE_AGE, httponly=True,
            secure=not app.config["TESTING"], samesite="Lax", path="/"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    def enroll(con, room_id, label):
        count = con.execute("SELECT COUNT(*) FROM private_devices WHERE room_id=?", (room_id,)).fetchone()[0]
        if count >= 8:
            abort(409, description="此配对空间最多绑定 8 台设备")
        token = secrets.token_hex(32)
        device_id = secrets.token_hex(12)
        now = int(time.time())
        con.execute("INSERT INTO private_devices VALUES (?,?,?,?,?,?)",
                    (device_id, room_id, digest(token), label, now, now))
        return token, device_id

    @app.post("/api/private/create")
    def private_create():
        guard()
        limit("private-room-create", 3, 86400)
        label = (request.get_json(silent=True) or {}).get("label", "我的设备")
        if not isinstance(label, str) or len(label) > 24:
            abort(400, description="设备名称不正确")
        label = label.strip() or "我的设备"
        with lock, db() as con:
            for _ in range(4):
                invite = "HK-" + "-".join("".join(secrets.choice(CHARS) for _ in range(6)) for _ in range(4))
                if not con.execute("SELECT 1 FROM private_rooms WHERE invite_hash=?", (digest(invite),)).fetchone():
                    break
            else:
                abort(503)
            room_id = secrets.token_hex(16)
            con.execute("INSERT INTO private_rooms (id,invite_hash) VALUES (?,?)", (room_id, digest(invite)))
            token, device_id = enroll(con, room_id, label)
        return set_cookie(make_response(jsonify(paired=True, invite=invite, device_id=device_id), 201), token)

    @app.post("/api/private/join")
    def private_join():
        guard()
        limit("private-room-join", 8, 3600)
        payload = request.get_json(silent=True) or {}
        invite = payload.get("invite", "")
        label = payload.get("label", "我的设备")
        if not isinstance(invite, str) or not isinstance(label, str) or len(label) > 24:
            abort(400, description="配对码不正确")
        invite = invite.strip().upper()
        if not invite.startswith("HK-") or len(invite) != 30:
            abort(400, description="配对码不正确")
        with lock, db() as con:
            room = con.execute("SELECT id FROM private_rooms WHERE invite_hash=?", (digest(invite),)).fetchone()
            if room is None:
                abort(403, description="配对码无效")
            token, device_id = enroll(con, room["id"], label.strip() or "我的设备")
        return set_cookie(make_response(jsonify(paired=True, device_id=device_id)), token)

    @app.get("/api/private/me")
    def private_me():
        try:
            device = auth()
        except Exception as err:
            if getattr(err, "code", None) == 401:
                return jsonify(paired=False)
            raise
        with db() as con:
            members = con.execute("SELECT COUNT(*) FROM private_devices WHERE room_id=?", (device["room_id"],)).fetchone()[0]
        # Refresh the per-browser cookie lifetime on a normal visit.
        response = make_response(jsonify(paired=True, device_id=device["id"], label=device["label"], devices=members))
        return set_cookie(response, request.cookies[COOKIE])

    @app.get("/api/private/latest")
    def private_latest():
        device = auth()
        with db() as con:
            room = con.execute("SELECT body,filename,filekey,size,revision,updated,sender FROM private_rooms WHERE id=?",
                               (device["room_id"],)).fetchone()
            sender = con.execute("SELECT label FROM private_devices WHERE id=?", (room["sender"],)).fetchone() if room else None
        if room is None:
            abort(404)
        return jsonify(
            has_text=bool(room["body"]), text=room["body"],
            has_file=bool(room["filekey"]), filename=room["filename"], size=room["size"],
            revision=room["revision"], updated=room["updated"],
            sender=sender["label"] if sender else "其他设备",
            self_sent=room["sender"] == device["id"]
        )

    @app.post("/api/private/send")
    def private_send():
        guard()
        device = auth()
        limit("private-send-" + device["id"], 20, 60)
        body = request.form.get("text", "").strip()
        uploads = [item for item in request.files.getlist("file") if item.filename]
        if not body and not uploads:
            abort(400, description="请粘贴文字或选择文件")
        if len(body.encode("utf-8")) > 65536:
            abort(400, description="文字不能超过 64 KB")
        if len(uploads) > 500:
            abort(400, description="一次最多选择 500 个文件")
        pending = None
        name = ""
        size = 0
        new_key = ""
        try:
            if uploads:
                new_key = secrets.token_hex(24)
                pending = storage / ("." + new_key + ".upload")
                if len(uploads) > 1:
                    with zipfile.ZipFile(pending, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                        total = 0
                        seen = set()
                        for item in uploads:
                            name_part = item.filename.replace("\\", "/").split("/")[-1]
                            if not name_part or name_part in (".", "..") or len(name_part) > 200 or name_part in seen or any(ord(c) < 32 for c in name_part):
                                abort(400, description="文件名不安全或文件重名")
                            seen.add(name_part)
                            with archive.open(name_part, "w", force_zip64=True) as target:
                                while True:
                                    chunk = item.stream.read(1024 * 1024)
                                    if not chunk:
                                        break
                                    total += len(chunk)
                                    if total > app.config["MAX_FILE_BYTES"] - 1024 * 1024:
                                        abort(413, description="文件过大")
                                    target.write(chunk)
                    name = str(len(uploads)) + "个文件.zip"
                else:
                    name = uploads[0].filename.replace("\\", "/").split("/")[-1].strip()[:200]
                    if not name or name in (".", "..") or any(ord(c) < 32 for c in name):
                        abort(400, description="文件名不正确")
                    uploads[0].save(pending)
                size = pending.stat().st_size
                if size < 1 or size > app.config["MAX_FILE_BYTES"]:
                    abort(413, description="文件大小不正确或超过限制")
            now = int(time.time())
            old_key = ""
            with lock, db() as con:
                room = con.execute("SELECT * FROM private_rooms WHERE id=?", (device["room_id"],)).fetchone()
                if room is None:
                    abort(401, description="配对空间不存在")
                public_bytes = con.execute("SELECT COALESCE(SUM(size),0) FROM shares WHERE kind='file' AND expires>?", (now,)).fetchone()[0]
                private_bytes = con.execute("SELECT COALESCE(SUM(size),0) FROM private_rooms WHERE filekey!=''").fetchone()[0]
                if public_bytes + private_bytes - room["size"] + size > app.config["TOTAL_BYTES"]:
                    abort(507, description="服务器剩余存储空间不足")
                old_key = room["filekey"]
                if pending:
                    os.replace(pending, storage / new_key)
                con.execute("""UPDATE private_rooms SET body=?,filename=?,filekey=?,size=?,revision=?,updated=?,sender=?
                               WHERE id=?""",
                            (body, name, new_key, size, secrets.token_hex(12), now, device["id"], device["room_id"]))
            if old_key:
                (storage / old_key).unlink(missing_ok=True)
            return jsonify(ok=True), 201
        finally:
            if pending:
                pending.unlink(missing_ok=True)

    @app.get("/api/private/file")
    def private_file():
        device = auth()
        with db() as con:
            room = con.execute("SELECT filename,filekey FROM private_rooms WHERE id=?", (device["room_id"],)).fetchone()
        if not room or not room["filekey"]:
            abort(404)
        file_path = storage / room["filekey"]
        if not file_path.is_file():
            abort(404)
        # Never serve uploaded files as active HTML or inline SVG.
        return send_file(file_path, as_attachment=True, mimetype="application/octet-stream",
                         download_name=room["filename"], max_age=0)

    @app.get("/api/private/devices")
    def private_devices():
        device = auth()
        with db() as con:
            rows = con.execute("SELECT id,label,seen FROM private_devices WHERE room_id=? ORDER BY created",
                               (device["room_id"],)).fetchall()
        return jsonify(devices=[dict(id=r["id"], label=r["label"], seen=r["seen"], me=r["id"] == device["id"]) for r in rows])

    @app.post("/api/private/revoke")
    def private_revoke():
        guard()
        device = auth()
        wanted = (request.get_json(silent=True) or {}).get("device_id", "")
        if not isinstance(wanted, str) or len(wanted) != 24:
            abort(400, description="设备标识不正确")
        with lock, db() as con:
            con.execute("DELETE FROM private_devices WHERE room_id=? AND id=?", (device["room_id"], wanted))
        response = make_response(jsonify(ok=True))
        if wanted == device["id"]:
            response.delete_cookie(COOKIE, path="/")
        return response

    return None
