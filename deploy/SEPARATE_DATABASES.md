# Separating the live database from development

Until now every laptop connected to the live database as `postgres`, its owner,
and the live server did too. One lost or infected laptop, or one mistaken
command, could read or change everything, including password hashes and 2FA
secrets, and none of GeoAlert's own permission checks or audit log apply to a
direct database login (security audit GA-04).

After these steps:

| Who | Connects to | As |
|---|---|---|
| Laptops | a separate development project, with a scrubbed copy of the data | that project's `postgres` |
| The live server (Render) | the live project | `geoalert_app`: reads and writes rows, can't change the database's structure |
| Whoever runs migrations | the live project | `postgres`, from `backend/.env.production` on one machine |

Do the three parts in order. Parts A and B change nothing for anyone else; part
C is the one that takes the live password away from the laptops.

Never paste a password or key into a chat, an issue or a screenshot.

## Part A: the development database (about 20 minutes)

1. In Supabase, **New project**: name `geoalert-dev`, region Southeast Asia
   (Singapore), a long generated database password (keep it in a password
   manager). The free plan allows two projects.
2. In the new project, **Connect** > **Session pooler**. Note the host, the
   user (`postgres.` followed by the new project's id) and port `5432`.
3. Copy `backend/.env` to `backend/.env.devdb` (git ignores it) and change
   `DB_USER`, `DB_PASSWORD` and `DB_HOST` to the new project's values.
4. For photos: in the new project, **Storage** > new private bucket
   `incident-photos`, then **Storage settings** > S3 access keys > new key. Put
   its endpoint, region, key and secret in the `SUPABASE_S3_*` lines of
   `.env.devdb`. (Or blank those five lines: photos are then saved on the
   laptop.)
5. Build the copy, from the `backend` folder with the venv active (after
   `pip install -r requirements\development.txt`):

   ```powershell
   python ..\deploy\make_dev_database.py --target-env .env.devdb
   ```

   It reads the live database (read-only), creates the tables in the new one,
   and copies everything with names, emails, passwords, 2FA, report text,
   photos, sessions, notifications and the audit log scrubbed or left out. It
   lists the made-up accounts with their roles at the end.
6. Give yourself a sign-in on the copy:

   ```powershell
   $env:GEOALERT_ENV_FILE=".env.devdb"; python manage.py changepassword user1@dev.geoalert.local
   Remove-Item Env:GEOALERT_ENV_FILE
   ```

   (use an address the script listed with the role you want).
7. Send `.env.devdb` to each teammate privately (not in git or a group chat).
   Each saves it as `backend/.env`, replacing the old one. From then on their
   `runserver`, tests and experiments use the copy.

## Part B: the live server's own login (about 10 minutes)

1. Make a password on your own machine:
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`
2. In the **live** project's **SQL Editor**, paste `deploy/sql/geoalert_app_role.sql`,
   replace `REPLACE_WITH_A_LONG_RANDOM_PASSWORD` with that password (in the
   editor only), and **Run**. The last line should show `geoalert_app` with
   `rolbypassrls = true`.
3. On Render, **Environment**:
   - `DB_USER` = `geoalert_app.` followed by the live project's id (the part
     after `postgres.` in the current `DB_USER`)
   - `DB_PASSWORD` = the new password

   Keep `DB_PORT=6543`. Save; Render restarts.
4. Check the live site: sign in, open the map, open the admin dashboard
   (Database and Database schema checks ok).
   If sign-in fails with a database error, put the old `DB_USER` and
   `DB_PASSWORD` back on Render (they still work until part C) and tell
   whoever looks after the deployment.

## Part C: take the owner password off the laptops

Only once every teammate uses the development copy (part A) and the live site
runs as `geoalert_app` (part B).

1. Live project, **Project Settings** > **Database** > **Reset database
   password**. Keep the new one in a password manager.
2. The one person who runs migrations makes `backend/.env.production`: a copy
   of their old `.env` (the live values) with the new password. Git ignores it.
3. Live project, **Storage settings** > S3 access keys: create a new key, put it
   in Render's `SUPABASE_S3_KEY` and `SUPABASE_S3_SECRET`, check that a report
   photo still opens, then **delete the old key**. Every laptop's copy of it
   stops working.
4. Delete leftover copies of the old values: old `.env` backups,
   `Downloads\geoalert-render.env`.

## Releasing a change that has a migration, from now on

```powershell
cd backend
$env:GEOALERT_ENV_FILE=".env.production"; python manage.py migrate; Remove-Item Env:GEOALERT_ENV_FILE
```

Then push to `main`; Render deploys once CI passes (FREE_HOSTING.md, "Releasing
new code"), so always migrate first. New tables are readable and writable by
`geoalert_app` automatically. In the live project's SQL Editor, turn row-level
security on for them, as for every other table:

```sql
DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT relname FROM pg_class
           WHERE relnamespace = 'public'::regnamespace AND relkind IN ('r','p') AND NOT relrowsecurity
  LOOP EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.relname); END LOOP;
END $$;
```

To refresh the development copy later: run part A step 5 again with `--replace`.
