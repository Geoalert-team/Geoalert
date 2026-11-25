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

The Rain watch ("Next 3 days") was removed on 2026-11-22 and will be rebuilt later;
landslide prediction came back as susceptibility by purok (the section below). Past hazards, the History
page and every history record are unchanged. Nothing was dropped from the database (the
rainwatch tables and hazard_prediction_log are still there, unused).

Design: docs/design/specs/2026-11-22-fire-purok-model-design.md. Plan:
docs/design/plans/2026-11-22-fire-purok-model.md. Background and the data checks behind
it: docs/research/2026-11-22-fire-purok-prediction-audit.md. Data credits:
backend/apps/history/data/ATTRIBUTION.md.

--------------------------------------------------------------------------------
Hazard prediction: flood susceptibility by purok

With Flood ticked, "Likely by month" fills each purok by its flood susceptibility: Red
(high), Orange (moderate), Green (low, within the assessed floodplain) or grey ("Not
assessed yet", with the reason). It shows how flood-prone an area is, not whether a flood
is coming, and it is the same in every month. A machine-learning model learns it from
where floods reached in the 2017 UP Mananga flood survey (169 reports, typhoons of
1990-2014), with UP NOAH flood depths and terrain as inputs; it is tested on GeoAlert's
own flood points and the Tino satellite map, and it is used only if it beats UP NOAH's map
on its own (otherwise the NOAH-based classes are shown, labelled as such). No person can
set or change a flood level. History, including the level an approved flood report
takes from its puroks' past floods, is unchanged.

The model is trained on a developer machine, never on the server (pypdf and xgboost are in
requirements/development.txt only):

python manage.py build_flood_features  (open map data and UP NOAH maps, to backend/.hazard_cache)
python manage.py train_flood_model     (reads flood records read-only; writes the model and report)

Both write to backend/apps/history/data/ (commit those files so a deploy carries them).
The survey points and the satellite map stay in the git-ignored backend/.hazard_cache and
are never shown or redistributed. Rerun both after a purok reload, after new located
floods, or when UP NOAH publishes new maps. Design:
docs/design/specs/2026-11-24-flood-susceptibility-model-design.md. Evidence:
docs/research/2026-11-24-flood-prediction-assessment.md.

--------------------------------------------------------------------------------
Landslide predictive analytics

With Landslide ticked, "Likely by month" fills each purok by its landslide susceptibility:
Red (high), Orange (moderate), Green (low) or grey ("Not assessed yet", with the reason).
It shows how prone the ground is to sliding, not whether a landslide is coming, and it is
the same in every month. A machine-learning model learns it from where landslides started
after Philippine typhoons (NASA's COOLR "new events" inventories, mapped from satellite
images after recent typhoons, and the Mangkhut inventory at Itogon) and is applied to
Talisay's terrain, land cover and roads; if it fails its tests, UP NOAH's landslide hazard
map is shown instead, labelled as such. NASA's Global Landslide Catalog is a test only: its
points in Talisay are shown on the report and never trained on. History is unchanged.

Run on a developer machine, never on the server:

python manage.py build_landslide_training  (the typhoon landslides and their "no landslide" ground)
python manage.py build_landslide_features  (Talisay's terrain, land cover and roads)
python manage.py train_landslide_model     (writes the model and report to backend/apps/history/data/)

The shipped table was built with `build_landslide_training --philippines-only` (Egay, Paeng,
Agaton and Mangkhut; the 19 world events left out to finish sooner, so the world test did not
run). The tiles already built stay in the git-ignored backend/.hazard_cache on the machine that
built them, so a full rebuild there without the option resumes from them; then rerun
train_landslide_model.

train_landslide_model needs NASA's Global Landslide Catalog export as
backend/.hazard_cache/nasa_global_landslide_catalog.csv. Its licence is unstated, so it stays
private in the git-ignored cache and is never committed; without it the command stops
before training.

Sources: NASA COOLR (CC BY 4.0), Abanco and Jones 2023 (Open Government Licence), UP NOAH
(ODbL), Esri / Impact Observatory land cover (CC BY 4.0), Copernicus DEM, OpenStreetMap
and Microsoft building footprints (ODbL). Design:
docs/design/specs/2026-11-24-landslide-susceptibility-model-design.md.

--------------------------------------------------------------------------------
Automatic retraining

GitHub retrains the models by itself (.github/workflows/model-retrain.yml): fire at
03:17 Manila on the 2nd of each month, flood at 03:17 Manila on 5 January and landslide at
03:17 Manila on 6 January (not on the hour: GitHub may delay or drop runs scheduled at
:00). The job runs
on GitHub's throw-away runner with a database of its own, never the shared one. It reads
its training data from the backend with a token, trains, and posts the attempt back. The
backend keeps every attempt (Predictive models tab, "Model updates") and puts a new model
live only when it does at least as well as the one in use. It needs the model_fit table
(migration history 0012) on the server. Scheduled runs happen only from main. In a public
repository, GitHub turns scheduled workflows off after 60 days without repository
activity; if the runs stop, turn the workflow back on in the Actions tab.

The landslide run only adds GeoAlert's own located landslides to the outside training
data; the outside-trained model never changes. It tries once there are at least 30
located spots in at least 3 barangays; below that it saves "Not tried" and the map stays
as it is. Its job may take up to 360 minutes (fire and flood: 120), and it stops itself
after 330 minutes with a "Failed" attempt, so a run that is too slow is still recorded.
It needs migrations history 0013 (the landslide log) and 0014 (model_fit accepts
landslide) on the server.

Set up once, with one long random token (never write it in a file):

python -c "import secrets; print(secrets.token_urlsafe(32))"

- Render > Environment:  MODEL_JOB_TOKEN = the token. Without it the job's two
  endpoints refuse everything.
- GitHub > Settings > Secrets and variables > Actions, two repository secrets:
  MODEL_JOB_API_URL = the backend's address, no trailing slash
                      (https://geoalert-rvqc.onrender.com)
  MODEL_JOB_TOKEN   = the same token

To run it by hand: Actions > Model retraining > Run workflow, then pick fire, flood or
landslide.
Tick "Dry run" to train and print the result without posting anything. A dry run on a
laptop (set MODEL_JOB_API_URL and MODEL_JOB_TOKEN in the terminal first):

python manage.py run_model_job --hazard fire --dry-run

The flood and landslide runs load the purok outlines only into an empty database with
MODEL_JOB_SCRATCH_DB=true, which only the workflow sets. On a laptop, once there are
enough spots to try, it stops with an error before training rather than write to the
shared database. A run that fails posts a "Failed"
attempt with its reason and turns the workflow red; the next scheduled run tries again.

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


