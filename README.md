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

Running it twice on the same day adds no rows. Flood and landslide days it missed are
filled in by the next run, up to 30 days back. (On the server with HAZARD_LOG_WRITER=true
the forecast's warm-up also runs it once a day, but only when someone opens the site.)

--------------------------------------------------------------------------------
Flood and landslide chances (rain, storm and exposure models)

The flood and landslide forecast needs these files in backend/apps/history/data/. Make
them in this order, from the backend folder:

python manage.py fetch_rain
python manage.py fetch_storms
python manage.py build_hazard_features
python manage.py test_hazard_models

None of the downloads needs an account or a key.
- fetch_rain downloads daily rain from NASA POWER, from 2006-12-18 to a few days ago, into
  rain_daily.csv (about a minute, one request per year).
- fetch_storms downloads the IBTrACS storm tracks (NOAA NCEI; the West Pacific file, about
  115 MB, read as it streams and never kept whole, plus the last-3-years file) and writes
  storm_days.csv and storm_days.meta.json: each day a storm centre came within 300 km of
  Talisay in the 72 hours to the end of the day. fetch_storms --recent reads only the
  last-3-years file (about 12 MB) and merges it in.
- build_hazard_features measures terrain per barangay into barangay_terrain.csv
  (elevation and OpenStreetMap, reused from .hazard_cache when saved), and flood exposure
  into barangay_exposure.csv: buildings (Microsoft building footprints) in the UP NOAH
  25-year and 100-year Medium/High flood areas (the Cebu maps, about 120 MB, from the
  bettergovph mirror on Hugging Face) and on ground under 2 m above drainage.
- test_hazard_models downloads the NASA Global Landslide Catalog (data.nasa.gov, no login)
  into .hazard_cache when it is not there, runs the held-out tests, applies the rule for
  replacing the current model, fits both models on the whole study period and writes
  hazard_model_report.json (version 2). It takes about a minute. It stops, and keeps the
  old report, when any input is missing; the message names the command to run.
All four read the database only. Raw downloads stay in backend/.hazard_cache, which is not
in git; the NASA catalogue's rows never leave it (it states no licence). The data files
above are in git; data/ATTRIBUTION.md gives their sources and licences (ODbL for
barangay_exposure.csv). NASA catalogue events left out by hand are listed, with the
reason, in data/landslide_catalogue_exclusions.csv.

The forecast scores every day from the fit saved in the report (it does not refit) and
caches the result for 6 hours; once a day the warm-up refreshes the recent storm tracks.
A day the storm file does not cover gets no flood chance. If the report or a data file is
missing, or the report is from an older version, flood and landslide show "unavailable"
with the reason; they are never estimated by counting past events, and they are left out
of the All hazards chance.

Fire's chance comes from its own Poisson regression (apps/history/model_forecast.py),
refitted from the records by the forecast itself and cached for 6 hours. Each refit also
tests a second model, a pooled Poisson regression that uses each barangay's building
count from barangay_exposure.csv (apps/history/fire_candidate.py), on the last 9 full
months; it takes over only if it scores clearly better there. Without that file today's
model is used. Fire is never estimated by counting either:
- With too few fire records to train and test (100 to train, 20 to test), fire shows
  "unavailable".
- For a past period with fewer than 100 fires before it (2023-2024 today), the model
  trained on every record is used, and the rows say it learned from that period.
- A period from before the first fire record shows "unavailable".

Each year (say every January): run fetch_rain so the newest full year joins the rain
scenarios, and fetch_storms, then run test_hazard_models.

After adding flood or landslide records for a finished year: set STUDY_END in
apps/history/hazard_data.py to the end of that year, then rerun test_hazard_models.
Until it is rerun, the accuracy card shows "stale" whenever study-period records have
changed. Records left out of the main run, with the reason for each, are listed in
data/hazard_model_exclusions.csv.

test_hazard_models always tests 2023, 2024 and 2025 (FOLDS in
apps/history/hazard_models.py); a newly added year is tested only after a fold for it is
added there.

Rain source: NASA POWER (https://power.larc.nasa.gov), daily corrected rain
(PRECTOTCORR) from NASA's MERRA-2 and GEOS-IT models, free with no restrictions on use,
commercial use included (CC BY 4.0). Its grid is about 55 km across, so the whole city
reads one cell, and it runs a few days behind today; the live "rain so far" uses the same
service. Training and live rain must come from the same source: changing the source means
downloading the rain again, rerunning test_hazard_models and checking the accuracy card.
Keep the credit line "Rain data from NASA POWER (CC BY 4.0), processed into hazard chances
by GeoAlert". In the thesis or any publication, use POWER's acknowledgment: "The data was
obtained from the National Aeronautics and Space Administration (NASA) Langley Research
Center's Prediction Of Worldwide Energy Resources (POWER) project funded through the NASA
Earth Science Division." Nothing else is required: no account, key or email. (Optional
courtesy: POWER likes to hear of published work that uses its data, at
larc-power-project@mail.nasa.gov.)

Open-Meteo is no longer used (its free API is non-commercial only). NASA IMERG satellite
rain was also tested and gave weaker results; the comparison is kept locally (not in git) in
.superpowers/sdd/2026-11-12-hazard-prediction-models/imerg-test/.

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


