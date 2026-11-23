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
python manage.py runserver

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

Fire purok prediction log (once the fire_purok_prediction_log table exists, migration
history 0010): once a day the server writes down each purok's fire chance and level for
the month, so the fire model can be scored on fires that come after. The hazard list
(the map's busiest request) starts it in the background once a Manila day. Its rows can
never be changed or removed, so exactly ONE machine writes it: the deployed server. Put
this line in that server's backend/.env, and nowhere else:

HAZARD_LOG_WRITER=true

Teammates who run runserver against the shared database leave it out (it is off by
default): their warm-up then writes nothing, and log_hazard_predictions stops with a
message saying logging is off on that machine.

Windows Task Scheduler (one line; change both paths):

schtasks /Create /TN "GeoAlert prediction log" /SC DAILY /ST 06:00 /TR "\"C:\path\to\Geoalert\backend\venv\Scripts\python.exe\" \"C:\path\to\Geoalert\backend\manage.py\" log_hazard_predictions"

On Linux, cron:   0 6 * * *  cd /path/to/backend && venv/bin/python manage.py log_hazard_predictions

Running it twice on the same day adds no rows, and it writes nothing until the fire model
has been trained. The rows of the older hazard_prediction_log (the flood, landslide and
barangay fire models removed on 2026-11-22) stay, unchanged; nothing writes to it.

--------------------------------------------------------------------------------
Hazard prediction: the fire risk model by purok

"Likely by month" shows each purok's chance of a fire and its level (Red, Orange or
Green) for a chosen month, and each barangay's chance on hover. The model is adapted from
the City of Pittsburgh Bureau of Fire / Carnegie Mellon Metro21 fire risk model
(github.com/CityofPittsburgh/fire_risk_analysis, MIT License, (c) 2017 mmadaio) and
trained on the BFP fire log. Its inputs describe each purok from open map data
(buildings, roads, road distance to a fire station, land cover, population); no past fire
count is an input. Approving a fire report puts it on the map at the model's level for its
puroks (Moderate, with the reason, when the model has none).

The model is trained on a developer machine, never on the server (xgboost is in
requirements/development.txt only):

python manage.py build_fire_features   (downloads open map data once, to backend/.hazard_cache)
python manage.py train_fire_model      (reads the fires, read-only; writes the model and report)

Both write to backend/apps/history/data/; commit those files so a deploy carries them.
Rerun both after a BFP import or a purok reload: if the purok map changed since training,
fire shows "unavailable" with the reason until they are rerun. Until the first training
run, fire shows "The fire model has not been trained yet."

Flood and landslide prediction and the Rain watch ("Next 3 days") were removed on
2026-11-22 and will be rebuilt later; asking the forecast for them is a 400. Past hazards,
the History page and every history record are unchanged. Nothing was dropped from the
database (the rainwatch tables and hazard_prediction_log are still there, unused).

Design: docs/design/specs/2026-11-22-fire-purok-model-design.md. Plan:
docs/design/plans/2026-11-22-fire-purok-model.md. Background and the data checks behind
it: docs/research/2026-11-22-fire-purok-prediction-audit.md. Data credits:
backend/apps/history/data/ATTRIBUTION.md.

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


