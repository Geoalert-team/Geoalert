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


user = User.objects.create_superuser(email='admin@geoalert.gov.ph', password='Admin2026!', full_name='GeoAlert Administrator')




install POSTMAN Thunder Client in vscode
to test the login endpoint 

or on browser


