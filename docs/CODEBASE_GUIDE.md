# GeoAlert code guide

Where everything lives, and how the parts connect. Use it to find the code behind
any feature, or to answer "where is that done?" during the defense.

- Live website: https://geoalert-talisay.vercel.app
- Live backend: https://geoalert-rvqc.onrender.com
- Setup on a laptop: [README.md](../README.md). Hosting: [deploy/FREE_HOSTING.md](../deploy/FREE_HOSTING.md).

## The project at a glance

```
backend/            Django REST API (Python 3.11, Django 4.2, PostGIS)
  config/           settings, the list of API addresses (urls.py)
  apps/             one folder per feature (see "Modules" below)
  utils/            shared pieces: permissions, sessions, audit log, errors
  tests/            the backend's automated tests
  requirements/     the Python packages (base, development, production)
frontend/           React website (React 18, Leaflet.js, Chart.js)
  src/pages/        one file per screen; staff dashboards in pages/Dashboard/
  src/components/   the parts the screens are built from, grouped by feature
  src/api/          every call to the backend, one file per backend app
  public/hazard-index/  the susceptibility maps shown on the public map
deploy/             hosting guides and settings templates
docs/               this guide, design notes, research and data reviews
.github/workflows/  the automated tests that run on every push
```

Each backend app has the same parts, so once you know one you can find your way in
the others:

| File | What it holds |
|---|---|
| `models.py` | The database tables |
| `serializers.py` | How a record becomes JSON for the website, and checks on what comes in |
| `views.py` | What each API address does |
| `urls.py` | The API addresses of the app |
| `management/commands/` | Commands run with `python manage.py <name>` |

All API addresses start with `/api/`, and [backend/config/urls.py](../backend/config/urls.py)
sends each prefix to its app: `/api/auth/` to `accounts`, `/api/hazards/` to `hazards`,
and so on.

## How one request travels through the system

Example: a barangay officer reports a flood, and the DRRMO turns it into an alert.

1. **The screen.** The barangay dashboard
   ([BarangayDashboard.jsx](../frontend/src/pages/Dashboard/BarangayDashboard.jsx))
   checks the form with [fireReport.js](../frontend/src/pages/Dashboard/fireReport.js)
   and sends it through [reportApi.js](../frontend/src/api/reportApi.js).
2. **The request.** [axiosClient.js](../frontend/src/api/axiosClient.js) sends
   `POST /api/reports/incidents/` with the sign-in cookie. On the live site, Vercel
   passes every `/api/` request on to the backend on Render
   ([vercel.json](../frontend/vercel.json)).
3. **The backend.** Django finds the address in
   [config/urls.py](../backend/config/urls.py) and
   [reports/urls.py](../backend/apps/reports/urls.py). It checks the session and role
   ([utils/permissions.py](../backend/utils/permissions.py)), then
   `IncidentReportListCreateView` in [reports/views.py](../backend/apps/reports/views.py)
   validates and saves the report.
4. **The DRRMO's decision.** The DRRMO dashboard
   ([DRRMODashboard.jsx](../frontend/src/pages/Dashboard/DRRMODashboard.jsx)) calls
   `POST /api/reports/incidents/<id>/decide/`
   ([decide_views.py](../backend/apps/reports/decide_views.py)). Approving creates the
   hazard zone at the level its puroks' history gives
   ([history/purok_levels.py](../backend/apps/history/purok_levels.py)).
5. **The alert.** `issue_alert` in [hazards/alerts.py](../backend/apps/hazards/alerts.py)
   finds the affected barangays with a PostGIS query, picks the recipients
   (`alert_recipients`) and creates their notifications. An Extreme alert waits for a
   second officer first (`needs_second_approval`).
6. **Back on the screens.** The notification bell
   ([useNotifications.js](../frontend/src/hooks/useNotifications.js)) checks for new
   alerts every 30 seconds, and the public map
   ([PublicMap.jsx](../frontend/src/pages/PublicMap.jsx)) shows the hazard at its next
   refresh.

## Roles and where they are checked

There are four staff roles. Residents use the public pages without an account.

| Role (in the database) | Dashboard screen |
|---|---|
| `System_Admin` | [AdminDashboard.jsx](../frontend/src/pages/Dashboard/AdminDashboard.jsx) |
| `DRRMO_Officer` | [DRRMODashboard.jsx](../frontend/src/pages/Dashboard/DRRMODashboard.jsx) |
| `Barangay_Personnel` | [BarangayDashboard.jsx](../frontend/src/pages/Dashboard/BarangayDashboard.jsx) |
| `BFP_Personnel` | [BFPDashboard.jsx](../frontend/src/pages/Dashboard/BFPDashboard.jsx) |

- **The backend decides.** Each view names who may call it with a permission class
  from [utils/permissions.py](../backend/utils/permissions.py) (`IsSystemAdmin`,
  `IsDRRMOOfficer`, `IsBarangayPersonnel`, `IsBFPPersonnel`).
- **The website only follows.** [pages/Dashboard/index.jsx](../frontend/src/pages/Dashboard/index.jsx)
  picks the dashboard by role, and [Gate.jsx](../frontend/src/components/Gate.jsx) keeps
  signed-out visitors off staff pages. Hiding a button is never the protection; the
  backend check is.

## Modules: where each one lives

### F1 User Authentication and Access Control

| | Where |
|---|---|
| Backend | [accounts/](../backend/apps/accounts/): the `User` and `Role` tables, sign-in, two-factor codes, password change and reset ([password_reset.py](../backend/apps/accounts/password_reset.py)) |
| Security rules | [login_throttle.py](../backend/utils/login_throttle.py) (too many failures from one network), [session_limits.py](../backend/utils/session_limits.py) (30 minutes idle, 12 hours total), [password_change.py](../backend/utils/password_change.py), [reset_throttle.py](../backend/utils/reset_throttle.py); bcrypt hashing in `PASSWORD_HASHERS` in [settings/base.py](../backend/config/settings/base.py) |
| API | `/api/auth/` |
| Screens | [Login.jsx](../frontend/src/pages/Login.jsx), [ForgotPassword.jsx](../frontend/src/pages/ForgotPassword.jsx), [ResetPassword.jsx](../frontend/src/pages/ResetPassword.jsx), [Security.jsx](../frontend/src/pages/Security.jsx); who is signed in: [AuthContext.js](../frontend/src/context/AuthContext.js) |

### F2 Real-Time Hazard Alerts

| | Where |
|---|---|
| Reports from barangays | [reports/](../backend/apps/reports/): `IncidentReport` table, filing ([views.py](../backend/apps/reports/views.py), [fire_report.py](../backend/apps/reports/fire_report.py)) and the DRRMO's decision ([decide.py](../backend/apps/reports/decide.py), [decide_views.py](../backend/apps/reports/decide_views.py)) |
| Alerts | [hazards/alerts.py](../backend/apps/hazards/alerts.py): recipients, sending, the second-officer approval, reminders; the timed jobs in [release_pending_alerts.py](../backend/apps/hazards/management/commands/release_pending_alerts.py) |
| Notifications | [notifications/](../backend/apps/notifications/), API `/api/notifications/` |
| Screens | the bells ([NotificationBell.jsx](../frontend/src/components/Navbar/NotificationBell.jsx), [ResidentAlertBell.jsx](../frontend/src/components/Navbar/ResidentAlertBell.jsx)), waiting alerts ([AwaitingApprovalCard.jsx](../frontend/src/components/Resolve/AwaitingApprovalCard.jsx)), closing a hazard ([components/Resolve/](../frontend/src/components/Resolve/)) |

### F3 Interactive GIS Mapping

| | Where |
|---|---|
| Backend | [hazards/](../backend/apps/hazards/): `HazardZone` and `HazardType` tables, the zone list and detail ([views.py](../backend/apps/hazards/views.py)), cleaning a drawn shape ([geometry.py](../backend/apps/hazards/geometry.py)); [barangays/](../backend/apps/barangays/): `Barangay` and `Purok` tables and their outlines |
| Estimated purok outlines | [purok_estimate.py](../backend/apps/barangays/purok_estimate.py) and its data in [barangays/data/puroks/](../backend/apps/barangays/data/puroks/) |
| API | `/api/hazards/`, `/api/barangays/` |
| Screens | [PublicMap.jsx](../frontend/src/pages/PublicMap.jsx) and the map parts in [components/Map/](../frontend/src/components/Map/) (the hazard panel, barangay panel, purok layers) |

### F4 Guidance and Safety Instructions

| | Where |
|---|---|
| Backend | [guidance/](../backend/apps/guidance/), API `/api/guidance/` |
| Screens | [WhatToDo.jsx](../frontend/src/pages/WhatToDo.jsx), the editor [GuidanceEditor.jsx](../frontend/src/components/Guidance/GuidanceEditor.jsx), the map's What to do tab [GuidanceSteps.jsx](../frontend/src/components/Map/GuidanceSteps.jsx) |

### F5 Historical Data and Trend Analysis

| | Where |
|---|---|
| Backend | [history/](../backend/apps/history/): the `HistoricalRecord` table and its list, detail and export ([views.py](../backend/apps/history/views.py), [export.py](../backend/apps/history/export.py)), a place's past hazards ([area.py](../backend/apps/history/area.py)) |
| Importing the official logs | BFP fire log ([bfp.py](../backend/apps/history/bfp.py), [bfp_import.py](../backend/apps/history/bfp_import.py), [bfp_link.py](../backend/apps/history/bfp_link.py)), flood and landslide log ([flood_landslide.py](../backend/apps/history/flood_landslide.py)), both from the page ([import_views.py](../backend/apps/history/import_views.py), [importing.py](../backend/apps/history/importing.py)) |
| Predictive | see "The predictive feature" below |
| API | `/api/history/` |
| Screens | [HistoricalData.jsx](../frontend/src/pages/HistoricalData.jsx), [components/History/](../frontend/src/components/History/), [components/Forecast/](../frontend/src/components/Forecast/) |

### F6 Unified Hazard Display

| | Where |
|---|---|
| Backend | the hazard layers list (`HazardLayerListView` in [hazards/views.py](../backend/apps/hazards/views.py), `/api/hazards/layers/`), the susceptibility maps ([susceptibility.py](../backend/apps/hazards/susceptibility.py), built by `manage.py build_hazard_index` into [frontend/public/hazard-index/](../frontend/public/hazard-index/)) |
| Screens | the layer checkboxes [LayerControl.jsx](../frontend/src/components/Map/LayerControl.jsx), past hazards per purok [PurokHistoryLayer.jsx](../frontend/src/components/Map/PurokHistoryLayer.jsx), reading the susceptibility maps [hazardLevels.js](../frontend/src/components/Map/hazardLevels.js) |

### F7 Reporting and Analytics

| | Where |
|---|---|
| Backend | [reports/views.py](../backend/apps/reports/views.py) (Hazard Summary, Response Status, printing), [reports/analytics.py](../backend/apps/reports/analytics.py) |
| API | `/api/reports/hazard-summary/`, `/api/reports/response-status/`, `/api/reports/analytics/` |
| Screens | [ReportingAnalytics.jsx](../frontend/src/pages/ReportingAnalytics.jsx) with its two tabs [Reports.jsx](../frontend/src/pages/Reports.jsx) and [Analytics.jsx](../frontend/src/pages/Analytics.jsx); charts in [components/Charts/](../frontend/src/components/Charts/) and [components/Analytics/](../frontend/src/components/Analytics/); CSV files from [utils/csv.js](../frontend/src/utils/csv.js) |

### F8 Administrative Dashboard

| | Where |
|---|---|
| Backend | [admin_dashboard/](../backend/apps/admin_dashboard/): users, settings, activity log, alerts, status; the `AuditLog` and `SystemConfig` tables |
| Supporting | the settings an administrator can change ([system_settings.py](../backend/utils/system_settings.py)), what "Operational" means ([health.py](../backend/utils/health.py)), audit logging ([audit.py](../backend/utils/audit.py)) |
| API | `/api/admin-dashboard/` |
| Screens | [AdminDashboard.jsx](../frontend/src/pages/Dashboard/AdminDashboard.jsx) and its tabs in [pages/Dashboard/admin/](../frontend/src/pages/Dashboard/admin/) |

### News and tutorial videos

| | Where |
|---|---|
| News and advisories | [news/](../backend/apps/news/) (`/api/news/`): announcements from DRRMO and BFP ([feed.py](../backend/apps/news/feed.py)); hazard alerts are not posted here, they show on the map and in the bell; screens [News.jsx](../frontend/src/pages/News.jsx), [components/News/](../frontend/src/components/News/) |
| Tutorial videos | [tutorials/](../backend/apps/tutorials/) (`/api/tutorials/`), YouTube links ([youtube.py](../backend/apps/tutorials/youtube.py)); on the What to do page via [components/Tutorials/](../frontend/src/components/Tutorials/) |

## The predictive feature

**Rebuild in progress (2026-11-22).** Flood and landslide prediction, the old barangay fire
model and the Rain watch were removed. Fire is being rebuilt as a per-purok model adapted
from the City of Pittsburgh Bureau of Fire's fire risk model; until it is trained, fire
shows "unavailable" with the reason. Design:
[2026-11-22-fire-purok-model-design.md](design/specs/2026-11-22-fire-purok-model-design.md);
plan: [2026-11-22-fire-purok-model.md](design/plans/2026-11-22-fire-purok-model.md);
research: [2026-11-22-fire-purok-prediction-audit.md](research/2026-11-22-fire-purok-prediction-audit.md).
Everything is in [backend/apps/history/](../backend/apps/history/).

| File | Role |
|---|---|
| [views.py](../backend/apps/history/views.py) | The API: `HistoricalForecastView` (`/api/history/forecast/`, fire only; any other hazard is a 400) and `ForecastAccuracyView` (`/api/history/forecast/accuracy/`) |
| [forecast_rows.py](../backend/apps/history/forecast_rows.py) | The forecast's barangay rows, and marking a hazard unavailable with its reason |
| [prediction_log.py](../backend/apps/history/prediction_log.py) | Will keep the fire model's purok figures (plan Task B6); writes nothing until then. The old `hazard_prediction_log` rows stay, unchanged |
| [forecast.py](../backend/apps/history/forecast.py) | Counting (the share of past years with an event): the rows' history columns and a comparison baseline only, never shown as a forecast |

The screens are in [components/Forecast/](../frontend/src/components/Forecast/) and the
map's "Likely by month" view in [PublicMap.jsx](../frontend/src/pages/PublicMap.jsx).

## Shared building blocks

**Backend, [utils/](../backend/utils/):**

- [permissions.py](../backend/utils/permissions.py): who may call each API address.
- [errors.py](../backend/utils/errors.py): turns errors into readable API messages.
- [audit.py](../backend/utils/audit.py): the activity log.
- [sessions.py](../backend/utils/sessions.py), [session_limits.py](../backend/utils/session_limits.py): sign-in sessions and their time limits.
- [map_version.py](../backend/utils/map_version.py): lets the map skip downloading data that hasn't changed.
- [db_backend/](../backend/utils/db_backend/): the database connection, retried once if it fails.
- [sampling.py](../backend/utils/sampling.py): keeps sample data out of reports.

**Frontend:**

- [api/](../frontend/src/api/): every backend call. [errorMessage.js](../frontend/src/api/errorMessage.js) turns a failed call into one readable sentence.
- [context/AuthContext.js](../frontend/src/context/AuthContext.js): who is signed in.
- [hooks/](../frontend/src/hooks/): the notification and alert polling.
- [utils/](../frontend/src/utils/): small helpers (severity names, dates, CSV, terrain readings).

## Commands (`python manage.py …`)

| Command | What it does |
|---|---|
| `seed_data` | Creates the four roles and the hazard types |
| `load_barangays`, `load_puroks`, `build_purok_estimates` | Loads the 22 barangay outlines and the purok outlines |
| `import_bfp_fires`, `import_flood_landslide` | Imports the official fire log and the flood and landslide log |
| `release_pending_alerts` | The timed alert jobs (held Extreme alerts, reminders) |
| `build_hazard_index` | Builds the susceptibility maps for the public map |
| `log_hazard_predictions` | The daily prediction log (writes nothing until the fire purok log is built) |
| `seed_fake_hazards` | Adds or removes sample hazards for demos |

## Tests

| Part | Where | Run it |
|---|---|---|
| Backend | [backend/tests/](../backend/tests/), one file per feature (`test_<feature>.py`) | `python manage.py test tests apps` in `backend` |
| Frontend | next to the code they test, named `*.test.js` | `npm test` in `frontend` |
| Automatic | [.github/workflows/ci.yml](../.github/workflows/ci.yml) runs both on every push | |

## Where is…? (quick answers)

| Question | Answer |
|---|---|
| How passwords are stored | bcrypt, `PASSWORD_HASHERS` in [settings/base.py](../backend/config/settings/base.py) |
| The account lockout | `LoginView` (wrong passwords) and `TwoFactorVerifyView` (wrong codes) in [accounts/views.py](../backend/apps/accounts/views.py) set `locked_until`; per network: [login_throttle.py](../backend/utils/login_throttle.py) |
| Two-factor authentication | the `TwoFactor…View` classes in [accounts/views.py](../backend/apps/accounts/views.py) |
| Session timeout | [utils/session_limits.py](../backend/utils/session_limits.py) |
| Who receives an alert | `alert_recipients` in [hazards/alerts.py](../backend/apps/hazards/alerts.py) |
| The second-officer approval for Extreme | `needs_second_approval` and `release_overdue_approvals` in [hazards/alerts.py](../backend/apps/hazards/alerts.py) |
| How a purok's hazard level is set | [history/purok_levels.py](../backend/apps/history/purok_levels.py) |
| Finding the affected barangays (PostGIS) | `affected_barangays` in [hazards/alerts.py](../backend/apps/hazards/alerts.py) |
| The activity log | `AuditLog` in [admin_dashboard/models.py](../backend/apps/admin_dashboard/models.py) |
| Settings the administrator can change | [utils/system_settings.py](../backend/utils/system_settings.py) |
| All the database tables | the `models.py` of each app; the full list is the Data Dictionary in the manuscript |
| Where the live site's settings are | Render's Environment page (never in the code); template in [deploy/render.env.example](../deploy/render.env.example) |

## Other documents

- [docs/design/](design/): the design (`specs/`) and step-by-step plan (`plans/`) for
  each feature built since October, named by date.
- [docs/research/](research/): the research on hazard prediction models.
- [docs/data-reviews/](data-reviews/): PDF reviews of the hazard placements and the
  purok list per barangay.
- [deploy/](../deploy/): hosting on Vercel and Render ([FREE_HOSTING.md](../deploy/FREE_HOSTING.md))
  or on a paid server ([README.md](../deploy/README.md)).
