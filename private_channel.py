"""Private paired-device clipboard beside the existing public transfer service."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
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

    def room_invite(room_id, nonce):
        """Derive a stable high-entropy code without storing the plaintext in SQLite."""
        key_file = files.parent / ".private-invite-secret"
        try:
            key = key_file.read_bytes()
        except FileNotFoundError:
            try:
                fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as output:
                    output.write(secrets.token_bytes(32))
                    output.flush()
                    os.fsync(output.fileno())
            except FileExistsError:
                pass
            key = key_file.read_bytes()
        if len(key) != 32:
            raise RuntimeError("private invite secret is missing or invalid")
        bits = hmac.new(key, (room_id + ":" + nonce).encode("ascii"), hashlib.sha256).digest()
        letters = "".join(CHARS[n & 31] for n in bits[:24])
        return "HK-" + "-".join(letters[i:i + 6] for i in range(0, 24, 6))

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
        con.execute("""CREATE TABLE IF NOT EXISTS private_history (
            id TEXT PRIMARY KEY,
            room_id TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            filename TEXT NOT NULL DEFAULT '',
            filekey TEXT NOT NULL DEFAULT '',
            size INTEGER NOT NULL DEFAULT 0,
            updated INTEGER NOT NULL DEFAULT 0,
            sender TEXT NOT NULL DEFAULT ''
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_private_history_room ON private_history(room_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_private_devices_room ON private_devices(room_id)")
        con.execute("""CREATE TABLE IF NOT EXISTS private_agents (
            id TEXT PRIMARY KEY,
            room_id TEXT NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL,
            created INTEGER NOT NULL,
            seen INTEGER NOT NULL
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_private_agents_room ON private_agents(room_id)")
        # Existing rooms stored ONLY a one-way invite hash; never pretend to
        # recover the original code. Re-issue one only on an explicit request.
        room_cols = {row["name"] for row in con.execute("PRAGMA table_info(private_rooms)")}
        if "invite_nonce" not in room_cols:
            con.execute("ALTER TABLE private_rooms ADD COLUMN invite_nonce TEXT NOT NULL DEFAULT ''")

    def guard():
        # Non-simple custom header rejects cross-site HTML form CSRF; no CORS is enabled.
        if request.headers.get("X-Hamoki-Client") != "1":
            abort(403, description="请求来源不正确")
        origin = request.headers.get("Origin")
        if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
            abort(403, description="请求来源不正确")

    def auth(allow_agent=False):
        authorization = request.headers.get("Authorization", "")
        if authorization:
            if not allow_agent or not authorization.startswith("Bearer hka_"):
                abort(401, description="此令牌无权管理配对设备")
            token = authorization[11:]  # remove 'Bearer hka_' prefix
            if len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
                abort(401, description="AI 访问令牌无效")
            with db() as con:
                agent = con.execute("SELECT * FROM private_agents WHERE token_hash=?",
                                    (digest("hka_" + token),)).fetchone()
                if agent:
                    con.execute("UPDATE private_agents SET seen=? WHERE id=?",
                                (int(time.time()), agent["id"]))
            if agent is None:
                abort(401, description="AI 访问令牌已失效或被撤销")
            return agent
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
            room_id = secrets.token_hex(16)
            nonce = secrets.token_hex(16)
            invite = room_invite(room_id, nonce)
            con.execute("INSERT INTO private_rooms (id,invite_hash,invite_nonce) VALUES (?,?,?)",
                        (room_id, digest(invite), nonce))
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

    @app.get("/api/private/invite")
    def private_invite():
        device = auth()
        with db() as con:
            room = con.execute("SELECT id,invite_hash,invite_nonce FROM private_rooms WHERE id=?",
                               (device["room_id"],)).fetchone()
        if room is None:
            abort(404)
        if not room["invite_nonce"]:
            return jsonify(available=False, needs_reissue=True)
        invite = room_invite(room["id"], room["invite_nonce"])
        if digest(invite) != room["invite_hash"]:
            # Missing/rotated server key: do not falsely display an invalid invite.
            return jsonify(available=False, needs_reissue=True)
        return jsonify(available=True, invite=invite)

    @app.post("/api/private/invite/reissue")
    def private_invite_reissue():
        guard()
        device = auth()
        limit("private-invite-reissue-" + device["id"], 5, 3600)
        with lock, db() as con:
            room = con.execute("SELECT id FROM private_rooms WHERE id=?", (device["room_id"],)).fetchone()
            if room is None:
                abort(404)
            nonce = secrets.token_hex(16)
            invite = room_invite(room["id"], nonce)
            con.execute("UPDATE private_rooms SET invite_hash=?,invite_nonce=? WHERE id=?",
                        (digest(invite), nonce, room["id"]))
        return jsonify(available=True, invite=invite)

    @app.get("/api/private/latest")
    def private_latest():
        device = auth(allow_agent=True)
        with db() as con:
            room = con.execute("SELECT body,filename,filekey,size,revision,updated,sender FROM private_rooms WHERE id=?",
                               (device["room_id"],)).fetchone()
            sender = None
            if room:
                sender = con.execute("SELECT label FROM private_devices WHERE id=?", (room["sender"],)).fetchone()
                if sender is None:
                    sender = con.execute("SELECT label FROM private_agents WHERE id=?", (room["sender"],)).fetchone()
        if room is None:
            abort(404)
        return jsonify(
            has_text=bool(room["body"]), text=room["body"],
            has_file=bool(room["filekey"]), filename=room["filename"], size=room["size"],
            revision=room["revision"], updated=room["updated"],
            sender=sender["label"] if sender else "其他设备",
            self_sent=room["sender"] == device["id"]
        )

    @app.get("/api/private/history")
    def private_history():
        device = auth(allow_agent=True)
        with db() as con:
            rows = con.execute(
                """SELECT h.id,h.body,h.filename,h.filekey,h.size,h.updated,
                          COALESCE(d.label,a.label,'其他设备') AS sender
                   FROM private_history h
                   LEFT JOIN private_devices d ON d.id=h.sender
                   LEFT JOIN private_agents a ON a.id=h.sender
                   WHERE h.room_id=? ORDER BY h.rowid DESC LIMIT 2""",
                (device["room_id"],)
            ).fetchall()
        return jsonify(items=[
            {"id": row["id"], "text": row["body"], "has_text": bool(row["body"]),
             "filename": row["filename"], "has_file": bool(row["filekey"]),
             "size": row["size"], "updated": row["updated"], "sender": row["sender"]}
            for row in rows
        ])

    @app.get("/api/private/history/file/<entry_id>")
    def private_history_file(entry_id):
        device = auth(allow_agent=True)
        if not re.fullmatch(r"[0-9a-f]{24}", entry_id):
            abort(404)
        with db() as con:
            row = con.execute(
                "SELECT filename,filekey FROM private_history WHERE id=? AND room_id=?",
                (entry_id, device["room_id"])
            ).fetchone()
        if not row or not row["filekey"]:
            abort(404)
        file_path = storage / row["filekey"]
        if not file_path.is_file():
            abort(404)
        return send_file(file_path, as_attachment=True, mimetype="application/octet-stream",
                         download_name=row["filename"], max_age=0)

    @app.post("/api/private/send")
    def private_send():
        guard()
        device = auth(allow_agent=True)
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
            # Preserve the old latest as history, keeping at most two prior items.
            # History file bytes count against the same 10 GiB shared capacity.
            stale_keys = []
            with lock, db() as con:
                room = con.execute("SELECT * FROM private_rooms WHERE id=?", (device["room_id"],)).fetchone()
                if room is None:
                    abort(401, description="配对空间不存在")
                existing = con.execute(
                    "SELECT id,filekey,size FROM private_history WHERE room_id=? ORDER BY rowid DESC",
                    (device["room_id"],)
                ).fetchall()
                keep_old = 1 if room["revision"] else 2
                stale = existing[keep_old:]
                stale_keys = [row["filekey"] for row in stale if row["filekey"]]
                removed_bytes = sum(row["size"] for row in stale)
                public_bytes = con.execute(
                    "SELECT COALESCE(SUM(size),0) FROM shares WHERE kind='file' AND expires>?",
                    (now,)
                ).fetchone()[0]
                private_bytes = con.execute(
                    "SELECT COALESCE(SUM(size),0) FROM private_rooms WHERE filekey!=''"
                ).fetchone()[0]
                history_bytes = con.execute(
                    "SELECT COALESCE(SUM(size),0) FROM private_history WHERE filekey!=''"
                ).fetchone()[0]
                if public_bytes + private_bytes + history_bytes - removed_bytes + size > app.config["TOTAL_BYTES"]:
                    abort(507, description="服务器剩余存储空间不足")
                if pending:
                    os.replace(pending, storage / new_key)
                if room["revision"]:
                    con.execute(
                        """INSERT INTO private_history
                           (id,room_id,body,filename,filekey,size,updated,sender)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (room["revision"], room["id"], room["body"], room["filename"],
                         room["filekey"], room["size"], room["updated"], room["sender"])
                    )
                for item in stale:
                    con.execute("DELETE FROM private_history WHERE id=?", (item["id"],))
                con.execute(
                    """UPDATE private_rooms SET body=?,filename=?,filekey=?,size=?,revision=?,updated=?,sender=?
                       WHERE id=?""",
                    (body, name, new_key, size, secrets.token_hex(12), now, device["id"], device["room_id"])
                )
            for old_key in stale_keys:
                (storage / old_key).unlink(missing_ok=True)
            return jsonify(ok=True), 201
        finally:
            if pending:
                pending.unlink(missing_ok=True)

    @app.get("/api/private/file")
    def private_file():
        device = auth(allow_agent=True)
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

    @app.get("/api/private/agent/list")
    def private_agent_list():
        device = auth()
        with db() as con:
            agents = con.execute(
                "SELECT id,label,created,seen FROM private_agents WHERE room_id=? ORDER BY created",
                (device["room_id"],)
            ).fetchall()
        return jsonify(agents=[dict(agent) for agent in agents])

    @app.post("/api/private/agent/create")
    def private_agent_create():
        guard()
        device = auth()  # Browser pairing required; a bearer token may not create more tokens.
        limit("agent-token-create-" + device["id"], 5, 3600)
        payload = request.get_json(silent=True) or {}
        label = payload.get("label", "AI 工具")
        if (not isinstance(label, str) or not 1 <= len(label.strip()) <= 24
                or any(ord(c) < 32 or ord(c) == 127 for c in label)):
            abort(400, description="AI 工具名称需为1到24个字符")
        label = label.strip()
        with lock, db() as con:
            count = con.execute("SELECT COUNT(*) FROM private_agents WHERE room_id=?",
                                (device["room_id"],)).fetchone()[0]
            if count >= 5:
                abort(409, description="最多创建5个 AI 工具令牌，请先撤销旧令牌")
            new_id = secrets.token_hex(12)
            token = "hka_" + secrets.token_hex(32)
            now = int(time.time())
            con.execute(
                "INSERT INTO private_agents VALUES (?,?,?,?,?,?)",
                (new_id, device["room_id"], digest(token), label, now, now)
            )
        # One-time display: never expose plaintext token again in list or logs.
        return jsonify(ok=True, id=new_id, label=label, token=token), 201

    @app.post("/api/private/agent/revoke")
    def private_agent_revoke():
        guard()
        device = auth()
        wanted = (request.get_json(silent=True) or {}).get("id", "")
        if not isinstance(wanted, str) or len(wanted) != 24 or any(
                c not in "0123456789abcdef" for c in wanted):
            abort(400, description="AI 令牌标识不正确")
        with lock, db() as con:
            cur = con.execute(
                "DELETE FROM private_agents WHERE id=? AND room_id=?",
                (wanted, device["room_id"])
            )
        if cur.rowcount != 1:
            abort(404, description="AI 工具令牌不存在")
        return jsonify(ok=True)

    @app.get("/api/private/devices")
    def private_devices():
        device = auth()
        with db() as con:
            rows = con.execute("SELECT id,label,seen FROM private_devices WHERE room_id=? ORDER BY created",
                               (device["room_id"],)).fetchall()
        return jsonify(devices=[dict(id=r["id"], label=r["label"], seen=r["seen"], me=r["id"] == device["id"]) for r in rows])

    @app.post("/api/private/rename")
    def private_rename():
        guard()
        device = auth()
        payload = request.get_json(silent=True) or {}
        target = payload.get("device_id", "")
        new_name = payload.get("name", "")
        if not isinstance(target, str) or len(target) != 24 or any(c not in "0123456789abcdef" for c in target):
            abort(400, description="设备标识不正确")
        if not isinstance(new_name, str):
            abort(400, description="设备名称不正确")
        new_name = new_name.strip()
        if not new_name or len(new_name) > 24 or any(ord(c) < 32 or ord(c) == 127 for c in new_name):
            abort(400, description="设备名称需为1至24个有效字符")
        with lock, db() as con:
            updated = con.execute(
                "UPDATE private_devices SET label=? WHERE id=? AND room_id=?",
                (new_name, target, device["room_id"])
            )
            if updated.rowcount != 1:
                abort(404, description="设备不存在或不属于当前空间")
        return jsonify(ok=True, name=new_name)

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
