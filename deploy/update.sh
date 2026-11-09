#!/usr/bin/env bash
# Brings the server up to the latest code. Run as root:
#   bash /opt/geoalert/deploy/update.sh
set -euo pipefail

APP=/opt/geoalert

as_app() { sudo -u geoalert -H env DJANGO_SETTINGS_MODULE=config.settings.production "$@"; }

[ "${1:-}" = "--no-pull" ] || as_app git -C "$APP" pull --ff-only

echo "== Backend"
cd "$APP/backend"
[ -x venv/bin/python ] || as_app uv venv --python 3.11 venv
as_app uv pip install --python venv/bin/python -r requirements/production.txt
as_app venv/bin/python manage.py migrate --noinput
as_app venv/bin/python manage.py collectstatic --noinput
as_app venv/bin/python manage.py check --deploy

echo "== Website"
SITE="$(sed -n 's/^FRONTEND_URL=//p' .env)"
cd "$APP/frontend"
as_app npm ci
as_app env REACT_APP_API_URL="$SITE" GENERATE_SOURCEMAP=false npm run build

echo "== Restarting"
systemctl restart geoalert geoalert-alerts
systemctl reload nginx

echo "== Checking"
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null -H "Host: ${SITE#https://}" -H "X-Forwarded-Proto: https" http://127.0.0.1:8000/api/auth/csrf/; then
    echo "GeoAlert is answering."
    exit 0
  fi
  sleep 1
done
echo "GeoAlert did not answer. See: journalctl -u geoalert -n 50"
exit 1
