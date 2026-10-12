#!/usr/bin/env bash
set -euo pipefail
umask 077
ACTION="${1:-status}"
CTRL=/opt/hamoki-dev/dev-control
CONF=/opt/1panel/www/conf.d/dev.2858888.xyz.conf
PROJECTS=/opt/1panel/www/sites/dev.2858888.xyz/projects
NGINX=1Panel-openresty-oeUO
LOCK="$CTRL/.switch.lock"

exec 9>"$LOCK"
flock -x 9

mode() {
  if cmp -s "$CONF" "$CTRL/online.conf"; then echo online
  elif cmp -s "$CONF" "$CTRL/offline.conf"; then echo offline
  else echo modified
  fi
}
count_projects() { find "$PROJECTS" -maxdepth 1 -type f -name '*.conf' | wc -l; }
CURRENT="$(mode)"
if [ "$ACTION" = sync ]; then
  if [ "$(count_projects)" -gt 0 ]; then ACTION=on; else ACTION=off; fi
fi
case "$ACTION" in
  status)
    echo "site=$CURRENT projects=$(count_projects)"
    ;;
  on|off)
    if [ "$CURRENT" = modified ]; then
      echo "ERROR: current vhost was modified outside of dev-site; inspect before changing" >&2
      exit 3
    fi
    if [ "$ACTION" = off ] && [ "$(count_projects)" != 0 ]; then
      echo "ERROR: active project routes still registered. Unregister and finish those projects first." >&2
      exit 4
    fi
    TARGET="$ACTION"
    if [ "$CURRENT" = online ] && [ "$ACTION" = on ]; then
      echo 'Already online';exit 0
    fi
    if [ "$CURRENT" = offline ] && [ "$ACTION" = off ]; then
      echo 'Already offline';exit 0
    fi
    BACKUP="$CTRL/backups/dev-site-$(date -u +%Y%m%dT%H%M%SZ).conf"
    cp -p "$CONF" "$BACKUP"
    cp "$CTRL/$TARGET.conf" "$CONF"
    if ! docker exec "$NGINX" /usr/local/openresty/bin/openresty -t >/tmp/hamoki-dev-site-nginx-test.log 2>&1; then
      cp "$BACKUP" "$CONF"
      echo 'ERROR: nginx config test failed; prior config restored' >&2
      tail -12 /tmp/hamoki-dev-site-nginx-test.log >&2
      exit 5
    fi
    if ! docker exec "$NGINX" /usr/local/openresty/bin/openresty -s reload; then
      cp "$BACKUP" "$CONF"
      docker exec "$NGINX" /usr/local/openresty/bin/openresty -s reload || true
      echo 'ERROR: nginx reload failed; prior config restored' >&2
      exit 6
    fi
    echo "Site switched $CURRENT -> $TARGET (backup stored)"
    ;;
  *)
    echo 'Usage: dev-site.sh [status|on|off|sync]' >&2
    exit 2
    ;;
esac
