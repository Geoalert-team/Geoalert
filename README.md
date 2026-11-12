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

--------------------------------------------------------------------------------
Flood and landslide chances (rain and terrain models)

The flood and landslide forecast needs three files in backend/apps/history/data/. Make
them in this order, from the backend folder:

python manage.py fetch_rain
python manage.py build_hazard_features
python manage.py test_hazard_models

fetch_rain downloads daily rain from Open-Meteo into rain_daily.csv (throttled, takes a
few minutes). build_hazard_features measures terrain per barangay into
barangay_terrain.csv. test_hazard_models runs the held-out test and writes
hazard_model_report.json; it takes a few minutes. The last two read the database only.
The forecast refits the chosen model itself and caches the result for 6 hours. If the
report or a data file is missing, flood and landslide show "unavailable" with the reason;
they are never estimated by counting past events, and they are left out of the All
hazards chance.

Each year (say every January): run fetch_rain so the newest full year joins the rain
scenarios, then run test_hazard_models.

After adding flood or landslide records for a finished year: set STUDY_END in
apps/history/hazard_data.py to the end of that year, then rerun test_hazard_models.
Until it is rerun, the accuracy card shows "stale" whenever study-period records have
changed. Records left out of the main run, with the reason for each, are listed in
data/hazard_model_exclusions.csv.

test_hazard_models always tests 2023, 2024 and 2025 (FOLDS in
apps/history/hazard_models.py); a newly added year is tested only after a fold for it is
added there.

Before go-live: email info@open-meteo.com and get written confirmation that GeoAlert's
use is free (non-commercial), and keep their reply with the project's records. If they
say no, take their paid API plan, or switch the rain source to ERA5 (Copernicus).
Training and live rain must come from the same source, and ERA5 is coarser (about 25 km
against 9 km), so switching means downloading the rain again from ERA5, rerunning
test_hazard_models and checking the accuracy card before use.
Keep the credit line "Rain data by Open-Meteo.com (CC BY 4.0), processed into hazard
chances by GeoAlert".

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


