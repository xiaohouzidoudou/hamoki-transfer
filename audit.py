"""Privacy-conscious, bounded application access audit for Hamoki Transfer.

No request bodies, credentials, share codes, query strings or full URLs are stored.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

from flask import abort, jsonify, make_response, render_template, request
from itsdangerous import TimestampSigner, BadSignature, SignatureExpired


AUDIT_COOKIE = "hamoki_audit_admin"
MAX_RECORDS = 25000
RETENTION = 30 * 86400
EXCLUDED = {"/health", "/favicon.ico", "/api/upload/quota",
            "/api/private/latest", "/api/private/me", "/api/private/invite",
            "/api/private/devices", "/api/admin/summary", "/api/admin/events"}


def _secret_file(root: Path, name: str, size: int = 32) -> bytes:
    path = root / name
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "wb") as out:
            out.write(secrets.token_bytes(size))
            out.flush()
            os.fsync(out.fileno())
    value = path.read_bytes()
    if len(value) != size:
        raise RuntimeError("invalid audit secret")
    return value


def setup_audit(app, db, root, limit):
    signing_key = _secret_file(root, ".audit-session-secret")
    signer = TimestampSigner(signing_key, salt="hamoki-audit-login-v1")
    # Reuse the owner's existing upload-unlock password; no new accounts.
    # If that password is not configured, viewing audit logs stays disabled.
    configured = app.config.get("UPLOAD_UNLOCK_PASSWORD", "")

    # A password rotation invalidates pre-existing signed sessions.
    admin_proof = hashlib.sha256(configured.encode("utf-8")).hexdigest().encode("ascii")

    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created INTEGER NOT NULL,
            ip TEXT NOT NULL,
            device TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL,
            route TEXT NOT NULL,
            method TEXT NOT NULL,
            status INTEGER NOT NULL,
            bytes INTEGER NOT NULL DEFAULT 0,
            agent TEXT NOT NULL DEFAULT ''
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_audit_ip_created ON audit_events(ip,created)")

    def signed_in():
        try:
            proof = signer.unsign(request.cookies.get(AUDIT_COOKIE, ""), max_age=12 * 3600)
            return bool(configured) and hmac.compare_digest(proof, admin_proof)
        except (BadSignature, SignatureExpired, ValueError, TypeError):
            return False

    def require_admin():
        if not signed_in():
            abort(401, description="请先登录管理日志")

    def csrf():
        if request.headers.get("X-Hamoki-Client") != "1":
            abort(403, description="无效请求来源")
        origin = request.headers.get("Origin")
        if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
            abort(403, description="无效请求来源")

    def route_label():
        path = request.path
        route = request.url_rule.rule if request.url_rule else ""
        if not route:
            # Only a constrained path is logged for scanning detection;
            # no parameters, user-controlled queries or secret paths.
            return "可疑路径", (re.sub(r"[^a-zA-Z0-9/_.-]", "?", path)[:100] or "/")
        mapping = {
            "/": "访问首页",
            "/admin/logs": "访问日志页",
            "/api/send": "公开上传",
            "/api/upload/unlock": "上传口令验证",
            "/api/private/create": "创建私人空间",
            "/api/private/join": "设备配对",
            "/api/private/send": "私人发送",
            "/api/private/file": "私人文件下载",
            "/api/private/rename": "设备改名",
            "/api/private/revoke": "设备解绑",
            "/api/private/invite/reissue": "更新配对码",
            "/api/item/<code>": "查询取件码",
            "/api/text/<code>": "领取文字",
            "/d/<code>": "公开文件下载",
            "/f/<token>": "公开分享访问",
            "/api/qr/<code>": "查看二维码",
            "/api/preview/<code>": "预览图片",
            "/api/admin/login": "管理员登录",
            "/api/admin/logout": "管理员退出",
        }
        return mapping.get(route, "其他请求"), route

    def paired_device(con):
        token = request.cookies.get("hamoki_private_device", "")
        if len(token) != 64 or not re.fullmatch("[0-9a-f]{64}", token):
            return ""
        hashed = hashlib.sha256(token.encode("ascii")).hexdigest()
        row = con.execute(
            "SELECT label FROM private_devices WHERE token_hash=?", (hashed,)
        ).fetchone()
        if row is None:
            return ""
        return str(row["label"])[:24]

    @app.after_request
    def audit_response(response):
        try:
            path = request.path
            if path.startswith("/static/") or path in EXCLUDED:
                return response
            action, route = route_label()
            # Admin data browsing is not useful to track and can be noisy.
            if path.startswith("/api/admin/") and action not in ("管理员登录", "管理员退出"):
                return response
            now = int(time.time())
            ip = str(request.remote_addr or "unknown")[:48]
            user_agent = request.headers.get("User-Agent", "")[:120]
            byte_count = max(0, min(int(request.content_length or 0), 6 * 1024 ** 3))
            with db() as con:
                device = paired_device(con)
                con.execute(
                    """INSERT INTO audit_events
                       (created,ip,device,action,route,method,status,bytes,agent)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (now, ip, device, action, route, request.method[:8],
                     int(response.status_code), byte_count, user_agent)
                )
                # Bound the log even under aggressive HTTP scans.
                if now % 137 == 0:
                    con.execute("DELETE FROM audit_events WHERE created<?", (now - RETENTION,))
                    current = con.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
                    if current > MAX_RECORDS:
                        con.execute(
                            "DELETE FROM audit_events WHERE id IN "
                            "(SELECT id FROM audit_events ORDER BY id LIMIT ?)",
                            (current - MAX_RECORDS,)
                        )
        except Exception:
            # Logging must not interrupt uploads, downloads or ordinary pages.
            app.logger.exception("audit event write failed")
        return response

    @app.get("/admin/logs")
    def audit_page():
        return render_template("audit.html")

    @app.get("/api/admin/session")
    def audit_session():
        return jsonify(authenticated=signed_in())

    @app.post("/api/admin/login")
    def audit_login():
        csrf()
        limit("audit-admin-login", 5, 3600)
        raw = (request.get_json(silent=True) or {}).get("password")
        if not configured or not isinstance(raw, str) or len(raw) > 256 or not hmac.compare_digest(
            raw.encode("utf-8"), configured.encode("utf-8")
        ):
            abort(403, description="管理密码不正确")
        resp = jsonify(ok=True)
        resp.set_cookie(AUDIT_COOKIE, signer.sign(admin_proof).decode("ascii"),
                        max_age=12 * 3600, httponly=True,
                        secure=not app.config["TESTING"],
                        samesite="Strict", path="/")
        return resp

    @app.post("/api/admin/logout")
    def audit_logout():
        csrf()
        resp = jsonify(ok=True)
        resp.delete_cookie(AUDIT_COOKIE, path="/")
        return resp

    def bounds():
        try:
            start = int(request.args.get("from", "0"))
            end = int(request.args.get("to", "0"))
        except ValueError:
            abort(400, description="时间范围不正确")
        now = int(time.time())
        if start <= 0 or end <= start or end - start > 86401 or start > now + 86400:
            abort(400, description="请选择单日时间范围")
        return start, end

    @app.get("/api/admin/summary")
    def audit_summary():
        require_admin()
        start, end = bounds()
        with db() as con:
            q = " FROM audit_events WHERE created>=? AND created<?"
            args = (start, end)
            totals = con.execute(
                "SELECT COUNT(*) requests, COUNT(DISTINCT ip) ips,"
                "SUM(CASE WHEN status>=400 THEN 1 ELSE 0 END) failures,"
                "SUM(CASE WHEN action IN ('公开上传','私人发送') AND status<400 THEN 1 ELSE 0 END) uploads,"
                "SUM(CASE WHEN action IN ('公开文件下载','私人文件下载') AND status<400 THEN 1 ELSE 0 END) downloads,"
                "COALESCE(SUM(CASE WHEN action IN ('公开上传','私人发送') AND status<400 THEN bytes ELSE 0 END),0) upload_bytes"
                + q, args
            ).fetchone()
            top_ips = con.execute(
                "SELECT ip, COUNT(*) requests, SUM(CASE WHEN status>=400 THEN 1 ELSE 0 END) failures"
                + q + " GROUP BY ip ORDER BY requests DESC LIMIT 8", args
            ).fetchall()
            suspicious = con.execute(
                "SELECT COUNT(*) FROM audit_events WHERE created>=? AND created<?"
                " AND (status IN (401,403,429) OR action='可疑路径')", args
            ).fetchone()[0]
        return jsonify(
            totals=dict(totals), suspicious=suspicious,
            top_ips=[dict(row) for row in top_ips],
            notice="可疑请求仅是启发式提示，不等于已确认受到攻击"
        )

    @app.get("/api/admin/events")
    def audit_events():
        require_admin()
        start, end = bounds()
        action = request.args.get("action", "")
        if action and (len(action) > 32 or any(ord(ch) < 32 for ch in action)):
            abort(400, description="筛选条件不正确")
        try:
            offset = int(request.args.get("offset", "0"))
        except ValueError:
            abort(400, description="翻页参数不正确")
        if offset < 0 or offset > MAX_RECORDS:
            abort(400, description="翻页参数不正确")
        where = "WHERE created>=? AND created<?"
        args = [start, end]
        if action:
            where += " AND action=?"
            args.append(action)
        with db() as con:
            total = con.execute("SELECT COUNT(*) FROM audit_events " + where, args).fetchone()[0]
            rows = con.execute(
                "SELECT id,created,ip,device,action,route,method,status,bytes,agent"
                " FROM audit_events " + where +
                " ORDER BY id DESC LIMIT 120 OFFSET ?", args + [offset]
            ).fetchall()
        return jsonify(total=total, events=[dict(row) for row in rows])

    return None
