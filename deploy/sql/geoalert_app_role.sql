-- The live server's own database login (security audit GA-04).
--
-- Render used to sign in as `postgres`, the owner, which can change or drop
-- anything. geoalert_app can read and write rows and nothing else: no new
-- tables, no schema changes, no other logins. Migrations still run as
-- postgres, by whoever keeps that password (deploy/SEPARATE_DATABASES.md).
--
-- Run ONCE in the live project's Supabase SQL Editor. First replace the
-- password below with a long random one (make it on your own machine:
--   python -c "import secrets; print(secrets.token_urlsafe(32))"
-- ) and don't save this file with it.

CREATE ROLE geoalert_app LOGIN PASSWORD 'REPLACE_WITH_A_LONG_RANDOM_PASSWORD'
  -- Row-level security is on for every table with no policies, so it hides
  -- every row from an account without this. Like postgres, the app sees all.
  BYPASSRLS;

-- PostGIS lives in the `extensions` schema on Supabase, as for postgres
ALTER ROLE geoalert_app SET search_path = "$user", public, extensions;

GRANT USAGE ON SCHEMA public, extensions TO geoalert_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO geoalert_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO geoalert_app;

-- Tables later migrations create (as postgres) get the same rights
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO geoalert_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO geoalert_app;

-- Check: should list the role with rolbypassrls = true
SELECT rolname, rolcanlogin, rolbypassrls, rolcreaterole, rolcreatedb
FROM pg_roles WHERE rolname = 'geoalert_app';
