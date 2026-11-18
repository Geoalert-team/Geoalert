# Deploying GeoAlert for free (Vercel and Render)

Vercel serves the website and passes every `/api/` request to the backend on
Render, so the browser only ever sees one address. Sign-in depends on that. The
database and photos stay on Supabase.

This is enough for a demo and your defense. Free services can restart at any
time, so use a paid server before anyone relies on GeoAlert in a real emergency
(see [README.md](README.md)).

Screens on these sites change often, so a button may be named slightly
differently from what's written here.

## 1. The database and photo storage

The live site uses the team's current Supabase project. In step 3 you copy its
`DB_*` values from your `backend/.env`, except `DB_PORT`, which stays `6543`. On
that port Render borrows a connection only while it answers a request, which
leaves the 15 regular connections for the laptops.

### Photo storage

Render wipes its disk whenever the service restarts, so the live site keeps
photos in a Supabase Storage bucket. Until you add the `SUPABASE_S3_*` settings
below, each laptop saves photos in its own `backend/media` folder. In the
team's Supabase project:

1. **Storage > New bucket.** Name it `incident-photos`, leave **Public bucket**
   off, and create it. This name is `SUPABASE_S3_BUCKET`.
2. **Storage > Settings**, in the S3 connection section. Turn on the S3
   connection if it is off, then copy:
   - **Endpoint**, ending in `/storage/v1/s3`: `SUPABASE_S3_ENDPOINT`
   - **Region**, `ap-southeast-1` for Singapore: `SUPABASE_S3_REGION`
3. On the same page, under **S3 Access Keys**, create a new access key, then
   copy:
   - **Access key ID**: `SUPABASE_S3_KEY`
   - **Secret access key**: `SUPABASE_S3_SECRET`. It is shown only once.
4. Add the five lines to `backend/.env` on every laptop, so the laptops and the
   live site keep photos in the same place. If you already made
   `Downloads\geoalert-render.env`, delete it, then run
   `python deploy\make_render_env.py` again.
5. **Move the photos already saved.** Open the bucket and drag the
   `incident_reports` and `news` folders from `backend\media` into it, keeping
   their names. Every teammate who added photos on their own laptop does the
   same. The live site shows any photo missing from the bucket as broken.

The secret key opens every bucket in the project. Put it only in `.env` and on
Render, never in the frontend or a chat.

Because the laptops and the live site share one database:

- **Testing on a laptop changes the live site.** Test reports, alerts, imports
  and deletions show up for the public straight away.
- **Check before running `migrate` from another branch.** A change that removes
  or renames something breaks the live site, so ask whoever looks after the
  deployment first.
- **Give each teammate their own account**, and change the shared test
  passwords before going public (step 7).

### If the live site moves to its own project later

Create the new project in the Singapore region, with a storage bucket and S3
access keys. Put its details in `backend/.env` on one laptop for a moment and run:

```bash
cd backend
venv\Scripts\Activate.ps1
python manage.py migrate
python manage.py seed_data
python manage.py load_barangays
python manage.py load_puroks
python manage.py createsuperuser
```

Put your old `.env` values back afterwards. A new database has no past hazard
records: sign in as DRRMO once the site is live and import them.

## 2. Set up email

Render's free plan blocks the ports Gmail uses, so password-reset emails go
through [Brevo](https://www.brevo.com), which is free for up to 300 emails a day.

1. Create a Brevo account and verify the address you'll send from.
2. Under **SMTP & API**, create an SMTP key.
3. Note your SMTP login and that key for the next step.

## 3. Put the backend on Render

1. From the Geoalert folder, run `python deploy\make_render_env.py`. It writes
   `Downloads\geoalert-render.env` with a new `SECRET_KEY` and the `DB_*` and
   `SUPABASE_S3_*` values from your `backend/.env`. Open that file and replace
   the `__FILL_IN__` lines it lists: your Brevo login and SMTP key go in
   `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD`, and the sender address you
   verified goes in `DEFAULT_FROM_EMAIL`.
2. On [Render](https://render.com), sign in with GitHub and choose
   **New > Web Service**, then pick this repository. If Render opens a page
   titled "Create a new Postgres", choose **New Web Service** on it.
3. Fill in:

   | Field | Value |
   |---|---|
   | Name | `Geoalert` |
   | Branch | `feature/geoalert-updates` |
   | Language | Docker |
   | Root Directory | `backend` |
   | Region | Singapore |
   | Instance Type | Free |

4. Under **Environment Variables**, choose **Add from .env** and paste your copy.
5. Create the service and wait for it to say it's live. The first build takes
   several minutes.
6. Open `https://geoalert-rvqc.onrender.com/api/auth/csrf/`. You should see a
   short line of text, not an error page.

Render adds a few letters to the name to make the address, here
`geoalert-rvqc.onrender.com`. If you create the service again and get a
different address, change it in `frontend/vercel.json`, in `ALLOWED_HOSTS` and in
the cron job (step 5), then push.

## 4. Put the website on Vercel

1. On [Vercel](https://vercel.com), sign in with GitHub and add a new project
   from this repository. If it won't let you use the team's repository, fork it
   to your own GitHub account and import the fork.
2. Fill in:

   | Field | Value |
   |---|---|
   | Project Name | `geoalert-talisay` |
   | Framework | Create React App |
   | Root Directory | `frontend` |

   Add no environment variables. The built website calls its own address, and
   `vercel.json` forwards `/api/` to Render.
3. Deploy. This first build comes from `main` and may fail; that's expected.
4. In **Settings > Environments > Production**, set **Branch Tracking** to
   `feature/geoalert-updates`. Push to that branch to build it. Don't press
   **Redeploy** on a `main` deployment: Redeploy rebuilds the same branch.
5. Under **Domains**, add `geoalert-talisay.vercel.app` if the project got a
   different address, and always open the site there. Sign-in works only on the
   address listed in Render's `CSRF_TRUSTED_ORIGINS`, not on the long
   per-deployment addresses.

To use a different address, put it in Render's `ALLOWED_HOSTS`,
`CSRF_TRUSTED_ORIGINS`, `CORS_ORIGIN` and `FRONTEND_URL`.

## 5. Keep the backend awake

Render puts a free service to sleep after 15 idle minutes, and waking takes about
a minute. Render also has no free background worker for the timed alert jobs.
One scheduled request solves both, because the map's data request runs those jobs.

On [cron-job.org](https://cron-job.org), create a job that calls
`https://geoalert-rvqc.onrender.com/api/hazards/` **every minute**.

Render's 750 free hours cover one service running all month, so keep it as the
only free web service in that Render account.

## Rain watch: GitHub job

The map's "Next 3 days" view needs a rain forecast. A small GitHub job fetches it
from NOAA every 6 hours and sends it to Render. Render itself stays light: it
only stores the forecast and works out the colours. Do these in order.

1. **Back up, then migrate.** This changes the team's shared Supabase database,
   so do it only after a backup. From a laptop pointed at the live database, run
   `python manage.py showmigrations rainwatch` to check that `0001` is not yet
   applied, then `python manage.py migrate rainwatch`. Name the app: a plain
   `migrate` would apply every pending migration in the project, not only
   `rainwatch 0001`.
2. **Put the code on the deploy branch.** The new code has to be live before
   the first run: the site deploys from `feature/geoalert-updates`. You commit
   and push it yourself (the assistant never does). Then wait until both
   deploys have finished: **Render** (the backend, Dashboard > your service >
   **Events**) and **Vercel** (the website, Project > **Deployments**). Only go
   on when both say they are live.
3. **Render settings** (Environment):
   - `RAIN_WATCH_INGEST_TOKEN`: a long random value. Make one with
     `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
   - `PAGASA_FEED_WRITER=true`: only this server reads PAGASA's alert feed.
   - `HAZARD_LOG_WRITER=true`: check it is set too.

   `deploy\make_render_env.py` already writes all three; only the token needs
   filling in.
4. **GitHub secrets** (repository **Settings > Secrets and variables >
   Actions**):
   - `RAIN_WATCH_INGEST_TOKEN`: the same value as on Render.
   - `RAIN_WATCH_API_URL`: `https://geoalert-rvqc.onrender.com`
5. **Spending limit.** In GitHub **Billing > Budgets and alerts** (or Spending
   limits), set the Actions limit to $0, so the job can never be charged.
6. **Public or private?** Check the repository's visibility. Each run installs
   the forecast libraries (eccodes, xarray, pandas, zarr, icechunk) and then
   fetches the forecast, which takes roughly 4 to 6 minutes. At 4 runs a day
   that is about 500 to 700 minutes a month. It is free on a public repository.
   On a private one it counts against the 2,000 free minutes a month.
7. **Put the job on `main`.** GitHub runs timers only from the default branch, so
   `.github/workflows/rain-forecast.yml` and `tools/rain_forecast/` must be on
   `main`.
8. **Run it once by hand.** Actions tab > **Rain forecast** > **Run workflow**.
   Tick **dry run** first: it fetches the forecast and checks it without sending
   anything. Then run it again with dry run off. Open the map and the DRRMO
   dashboard. A correct result: the line says "Updated ... ago" and does not
   say "Out of date". On a dry day residents see no colours on the map, because
   the public map shows only Orange and Red; that is right. Staff see Green
   (and Yellow when it applies) on the DRRMO dashboard card.

If the job fails, GitHub emails the person who last changed the workflow's
schedule (the `cron` line) or who last re-enabled the workflow. That email is
the only alarm, so make sure that person reads it.

**"Out of date" on the map.** The newest full forecast is more than 12 hours old
(two missed runs in a row), or none has arrived yet. The forecast colours go
grey; PAGASA and DRRMO raises still show. Look at the latest run in the Actions
tab for the reason, fix it, and run it by hand.

**A paused timer.** On a public repository, GitHub pauses timers after 60 days
with no activity. Open Actions > **Rain forecast** > **Enable workflow**.

## 6. Check that it works

Three things can only be proven on the live site:

- [ ] **Sign in, then reload the page.** You should still be signed in.
- [ ] **Submit a report with a photo of about 5 MB.** It should upload.
- [ ] **Use Forgot password.** The email should arrive.

Also confirm that the map shows the purok outlines. The first load after a
restart is slow while the server rebuilds them.

## 7. Before real people use it

Reset the password of every account used during testing, and delete the test
accounts you no longer need.

## Releasing new code

If the release changes the database, run `python manage.py migrate` from a laptop
pointed at the live database **first**. Render doesn't run migrations by itself.

Then push to `feature/geoalert-updates`. Vercel and Render both redeploy on their
own.

## When something goes wrong

- **Backend errors:** Render > your service > **Logs**.
- **Website build errors:** Vercel > your project > **Deployments**.
- **Sign-in fails with a 403:** check `CSRF_TRUSTED_ORIGINS` matches the Vercel
  address exactly, starting with `https://`.
- **Bad Request (400) from the backend:** the address is missing from
  `ALLOWED_HOSTS`.
- **"Too many clients" or "max clients" in Render's logs:** check that Render's
  `DB_PORT` is `6543`.
- **The first forecast after a restart is slow:** that's normal. Loading the
  forecast's model takes about half a minute on the free plan, and it's quick
  after that.
- **Everything stopped mid-month:** you may have used up Render's 5 GB of data or
  750 hours. It resets at the start of the next month.
