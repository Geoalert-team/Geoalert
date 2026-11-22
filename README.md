# GeoAlert

A Community Geospatial Hazard Guidance and Risk Awareness System for the Talisay City
DRRMO: a public hazard map with safety guidance, and dashboards for the DRRMO, barangay
personnel, the BFP and the system administrator.

- Live website: https://geoalert-talisay.vercel.app
- **Where everything is in the code: [docs/CODEBASE_GUIDE.md](docs/CODEBASE_GUIDE.md)**
- Hosting it: [deploy/FREE_HOSTING.md](deploy/FREE_HOSTING.md)
- Design notes and research: [docs/design/](docs/design/), [docs/research/](docs/research/)

The rest of this file sets the project up on a laptop.

--------------------------------------------------------------------------------
Clones the Repository

Each team member runs this on their own machine:

git clone https://github.com/Madmanstn/GeoAlert.git
cd GeoAlert

Then set up the backend:

cd backend
python -m venv venv

venv\Scripts\Activate.ps1
pip install -r requirements/development.txt    
copy .env.example .env

Then open .env and fill in their own database credentials.

DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your-supabase-password
DB_HOST=db.dxncngkzfgoxlocaomnv.supabase.co
DB_PORT=5432

Then run migrations:

python manage.py migrate
python manage.py seed_data
python manage.py seed_fake_hazards     (optional: sample hazards on the map and 5 years of historical records)
python manage.py runserver

Sample hazards are generated with Faker and flagged as sample data on the map and the
historical page. They are placed where the susceptibility maps say each hazard is likely
(floods on the low coastal plain, landslides on upland slopes, fires in built-up blocks)
and dated by season (typhoon floods Sep-Dec, fires Mar-May). Running it again replaces
the old samples; real hazards are never touched.

python manage.py seed_fake_hazards --clear          removes all sample data
python manage.py seed_fake_hazards --active 12 --years 8 --seed 7

Real flood and landslide history (2021-2026, from news reports) comes from the
Flood_Landslide_data .xlsx: one record per event per barangay it hit. It is already in
the shared database; running it again adds only new rows.

python manage.py import_flood_landslide path\to\Flood_Landslide_data.xlsx --dry-run
python manage.py import_flood_landslide path\to\Flood_Landslide_data.xlsx --replace     swaps in a corrected sheet



Then set up the frontend in a new terminal:

cd frontend
npm install
copy .env.example .env
npm start

--------------------------------------------------------------------------------
Alert jobs (held Extreme alerts, unread-alert reminders, stale-zone nudges)

The map and the notification bell run these while someone has them open. So that
they also happen on time at 2 AM with nobody signed in, the server that runs GeoAlert
should run them every minute. Either keep a worker running:

python manage.py release_pending_alerts --loop

or have Windows Task Scheduler run it once a minute (one line; change both paths, and
add /RU SYSTEM to keep it running with nobody signed in to Windows):

schtasks /Create /TN "GeoAlert alert jobs" /SC MINUTE /MO 1 /TR "\"C:\path\to\Geoalert\backend\venv\Scripts\python.exe\" \"C:\path\to\Geoalert\backend\manage.py\" release_pending_alerts"

On Linux, cron:   * * * * *  cd /path/to/backend && venv/bin/python manage.py release_pending_alerts

Running it on more than one machine is safe: nothing is sent twice. On your own laptop
while developing you don't need it.

Prediction log (once the hazard_prediction_log table exists, migration 0008): once a day
the server should also write down the chances it gave, so they can be checked against
what happened. Its rows can never be changed or removed, so exactly ONE machine writes
it: the deployed server. Put this line in that server's backend/.env, and nowhere else:

HAZARD_LOG_WRITER=true

Teammates who run runserver against the shared database leave it out (it is off by
default): their warm-up then writes nothing, and log_hazard_predictions stops with a
message saying logging is off on that machine.

Windows Task Scheduler (one line; change both paths):

schtasks /Create /TN "GeoAlert prediction log" /SC DAILY /ST 06:00 /TR "\"C:\path\to\Geoalert\backend\venv\Scripts\python.exe\" \"C:\path\to\Geoalert\backend\manage.py\" log_hazard_predictions"

On Linux, cron:   0 6 * * *  cd /path/to/backend && venv/bin/python manage.py log_hazard_predictions

Running it twice on the same day adds no rows. Since 2026-11-22 it writes nothing: the
flood, landslide and old fire models it logged were removed, and the fire purok log that
replaces them is not built yet (plan docs/design/plans/2026-11-22-fire-purok-model.md,
Task B6). The rows already in hazard_prediction_log stay, unchanged.

--------------------------------------------------------------------------------
Hazard prediction (rebuild in progress, 2026-11-22)

Flood and landslide prediction, the old barangay fire model and the Rain watch ("Next 3
days") were removed on 2026-11-22: flood and landslide will be rebuilt later, and fire is
being rebuilt as a per-purok model adapted from the City of Pittsburgh Bureau of Fire's
fire risk model. Design: docs/design/specs/2026-11-22-fire-purok-model-design.md. Plan:
docs/design/plans/2026-11-22-fire-purok-model.md. Background and the data checks behind
it: docs/research/2026-11-22-fire-purok-prediction-audit.md.

Until the new fire model is built and trained, the "Likely by month" map view and the
forecast cards show fire as "unavailable" with the reason, never a counted figure; asking
the forecast for flood or landslide is a 400. The commands fetch_rain, fetch_storms,
build_hazard_features and test_hazard_models are gone, with their data files. Past
hazards, the History page and every history record are unchanged. Nothing was dropped
from the database (the rainwatch tables and hazard_prediction_log are still there,
unused).

--------------------------------------------------------------------------------
Deploying

See deploy/README.md.

--------------------------------------------------------------------------------
Tests

GitHub runs them on every push and pull request (the Actions tab): the backend tests on
a fresh PostGIS database of their own, then the frontend tests and the production build.
A build warning fails the run, so keep it warning-free. To run them yourself:

python manage.py test tests apps        (backend, uses a test_ copy of your database)
npm test                                (frontend)

--------------------------------------------------------------------------------


To make the first administrator account, run this and type a password when asked
(never write a real password in this file):

python manage.py createsuperuser




install POSTMAN Thunder Client in vscode
to test the login endpoint 

or on browser


