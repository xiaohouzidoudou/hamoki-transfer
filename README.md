# Hamoki Transfer

A tiny, original, self-hosted file handoff tool: browser upload -> 12-character pickup code + QR -> browser download. No account, Telegram, client software, npm, or external JavaScript. Built from scratch with Flask + SQLite and a little vanilla JS.

## Features

- File upload and short text transfer
- 1 hour / 24 hours / 7 days auto-expiration
- 5 pickups per code; cryptographically random 12-character codes
- QR codes rendered server-side as SVG
- Local SQLite and files, no third-party storage
- Private sender link instead of an account; public receiver uses code
- Per-IP request rate limits, per-file size limit, total storage limit
- All user files force `Content-Disposition: attachment`

## Start with Docker

```sh
cp .env.example .env
# Edit .env with: UPLOAD_SECRET, PUBLIC_URL
mkdir -p data && sudo chown 10001:10001 data
docker compose up -d --build
```

Run behind an HTTPS reverse proxy (1Panel, nginx, etc.) forwarding to `127.0.0.1:8018`. Set `PUBLIC_URL` to your HTTPS origin such as `https://send.example.com`. Direct inbound port 8018 is loopback-only on the VPS.

**Private sender URL** (keep secret):

`https://send.example.com/#key=YOUR_UPLOAD_SECRET`

The browser receives the private key from the URL fragment, removes it from the address bar, keeps it only in session storage, and sends it in an HTTP header for uploads. The recipient only sees `https://send.example.com/?code=THE_CODE`. Do not publish sender URLs or paste private URLs in screenshots or chats. Use an unshared browser profile on shared work computers; if someone can inspect browser storage while it is open, they can access the key. Change `UPLOAD_SECRET` to revoke upload access.

## Security notes

- The service requires `UPLOAD_SECRET` to be at least 24 characters; use `openssl rand -hex 32`. Do **not** commit the `.env` file.
- Do not expose the storage directory on the web or mount private host paths.
- This is not end-to-end encrypted; stored content is accessible to server administrators. Share only files you are authorized to transfer.
- Configure HTTPS, backups, disk quotas, and the reverse proxy's body-size limit before publishing.
- Rate limiting is in-process and best suited to a single small-instance deployment. Production at scale should use reverse-proxy rate limiting too.
- QR URLs are derived from `PUBLIC_URL`. File and text downloads count as pickups.
- This implementation is independent code under the MIT license, *not* a fork or a derivative copy of FileCodeBox.

## Development

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt pytest
export UPLOAD_SECRET="$(openssl rand -hex 32)"
export DATA_DIR=./data
flask --app app run --port 8000
pytest -q
```

## Roadmap

The MVP intentionally avoids login accounts, complex storage engines, frontend frameworks, browser pairing, and server-to-server sync. Add extra features only when actually needed.
