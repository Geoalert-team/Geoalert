# Deploying GeoAlert

One Ubuntu server runs everything: Nginx serves the website and passes the API
to Gunicorn, and a second service runs the alert jobs. The database and photo
storage stay on Supabase.

## What you need first

- A server running **Ubuntu 24.04** with about 2 GB of memory.
- A **domain name**, with an `A` record pointing at the server's IP address.
  HTTPS can't be turned on until the domain reaches the server.
- The values from a working `backend/.env`: database, email and Supabase storage.

The live site uses whatever database `backend/.env` names. If that is the same
database your laptops use, testing on a laptop changes live data. Use a
separate Supabase project before anyone relies on the site.

## First deployment

Sign in to the server as root, then:

```bash
apt-get update && apt-get install -y git
git clone -b merge-scout https://github.com/Geoalert-team/Geoalert.git /opt/geoalert
bash /opt/geoalert/deploy/setup.sh your-domain.com
```

If the repository is private, `git clone` asks for a GitHub username and a
personal access token.

The script stops after creating `/opt/geoalert/backend/.env`. Replace every
`__FILL_IN__` in that file, then run the same `setup.sh` line again. It installs
everything and starts GeoAlert.

Supabase's `db.*.supabase.co` address only works over IPv6. If the database step
fails with "Network is unreachable" or "could not translate host name", the
server has no IPv6: use the **Session pooler** host and user from the Supabase
dashboard (Connect button) for `DB_HOST` and `DB_USER`, then run `setup.sh` again.

Then turn on HTTPS:

```bash
certbot --nginx -d your-domain.com
```

Open `https://your-domain.com`. If this is a new, empty database, also run:

```bash
cd /opt/geoalert/backend
sudo -u geoalert -H env DJANGO_SETTINGS_MODULE=config.settings.production venv/bin/python manage.py seed_data
sudo -u geoalert -H env DJANGO_SETTINGS_MODULE=config.settings.production venv/bin/python manage.py load_barangays
sudo -u geoalert -H env DJANGO_SETTINGS_MODULE=config.settings.production venv/bin/python manage.py load_puroks
sudo -u geoalert -H env DJANGO_SETTINGS_MODULE=config.settings.production venv/bin/python manage.py createsuperuser
```

A new database has no past hazard records. Sign in as DRRMO and import them
from the import page.

## Before real people use it

Reset the password of every account used during testing, and delete the test
accounts you no longer need.

## Releasing new code

Push to the branch, then on the server:

```bash
bash /opt/geoalert/deploy/update.sh
```

This also applies any database migrations.

## When something goes wrong

```bash
systemctl status geoalert geoalert-alerts nginx
journalctl -u geoalert -n 50
journalctl -u geoalert-alerts -n 50
tail -n 50 /var/log/nginx/error.log
```
