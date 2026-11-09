#!/usr/bin/env bash
# First-time setup of a fresh Ubuntu 24.04 server. Run as root, from the clone
# in /opt/geoalert:   bash /opt/geoalert/deploy/setup.sh your-domain.com
# Stops once for you to fill in backend/.env; run it again after that.
set -euo pipefail

DOMAIN="${1:?Usage: bash deploy/setup.sh your-domain.com}"
APP=/opt/geoalert
ENV_FILE="$APP/backend/.env"

[ "$(id -u)" -eq 0 ] || { echo "Run this as root."; exit 1; }
[ -d "$APP/.git" ] || { echo "Clone the repository into $APP first."; exit 1; }

echo "== Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y nginx git curl gdal-bin libgdal-dev libgeos-dev certbot python3-certbot-nginx ufw
# Node 22 and Python 3.11, the versions the GitHub Actions tests run on
command -v node >/dev/null || { curl -fsSL https://deb.nodesource.com/setup_22.x | bash -; apt-get install -y nodejs; }
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh

echo "== Swap (building the website needs more memory than a small server has)"
if [ -z "$(swapon --show)" ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== Account"
id geoalert >/dev/null 2>&1 || useradd --create-home --shell /bin/bash geoalert
chown -R geoalert:geoalert "$APP"

echo "== Settings"
if [ ! -f "$ENV_FILE" ]; then
  key="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
  sed -e "s|__DOMAIN__|$DOMAIN|g" -e "s|__SECRET_KEY__|$key|" -e "s|__LIBDIR__|/usr/lib/$(uname -m)-linux-gnu|g" \
    "$APP/deploy/production.env.example" > "$ENV_FILE"
  chown geoalert:geoalert "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo
  echo "Now replace every __FILL_IN__ in $ENV_FILE, then run this script again."
  exit 0
fi
if grep -q '__FILL_IN__' "$ENV_FILE"; then
  echo "$ENV_FILE still has __FILL_IN__ values. Fill them in, then run this script again."
  exit 1
fi

echo "== Services"
install -m 644 "$APP"/deploy/systemd/*.service /etc/systemd/system/
# Only the first time: Certbot adds the HTTPS settings to this file afterwards
if [ ! -f /etc/nginx/sites-available/geoalert ]; then
  sed "s/__DOMAIN__/$DOMAIN/g" "$APP/deploy/nginx/geoalert.conf" > /etc/nginx/sites-available/geoalert
fi
ln -sf /etc/nginx/sites-available/geoalert /etc/nginx/sites-enabled/geoalert
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl daemon-reload
systemctl enable geoalert geoalert-alerts nginx

echo "== Firewall"
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

bash "$APP/deploy/update.sh" --no-pull

echo
echo "Done. Turn on HTTPS with:   certbot --nginx -d $DOMAIN"
