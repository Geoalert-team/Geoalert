# Forgot password — design

Date: 2026-10-21
Status: draft for review
Branch: merge-scout

## Why

Staff who forget their password today have one way back in: a System Admin
uses Admin › Users › Reset password and passes on a temporary password. There
is no self-service reset, and nothing in the system sends email yet (Django is
configured for Gmail SMTP, but `.env` still holds the placeholder
`EMAIL_HOST_USER=your-email@gmail.com` and no code calls `send_mail`).

Only staff have accounts (System Admin, DRRMO Officer, Barangay Personnel);
residents never sign in.

## Decisions (agreed 2026-10-21)

| Question | Choice |
|---|---|
| How they get back in | An emailed one-time reset link |
| Link lifetime | 1 hour |
| Who can use it | All staff, System Admins included |
| A locked account | A successful reset unlocks it |
| Token mechanism | Django's built-in `default_token_generator` (no new table, no migration) |

## Goals

- "Forgot password?" on the login page leads to a reset that needs no admin.
- The page never reveals whether an email has an account.
- A link works once, for 1 hour, and stops working when the password changes.
- The new password follows the same rules as Change password.
- Every request, reset and failure is in the audit log.
- It can be tested today without real email; real sending starts once Gmail
  details are in `.env`.

## Non-goals

- Resetting by SMS or a typed code.
- An admin screen listing pending reset requests.
- Changing the admin Reset password, 2FA, the login lockout or session limits.
- Signing the person in automatically after the reset.

## Design

### 1. What staff see

- **Login** (`pages/Login.jsx`): a "Forgot password?" link under the password
  field goes to `/forgot-password`.
- **Forgot password** (`/forgot-password`, `pages/ForgotPassword.jsx`): an
  email field and "Send reset link". Whatever happens, it then shows:
  *"If an account with that email exists, we've sent a link to reset its
  password. It works for 1 hour."* and a "Back to log in" link. Too many
  requests from one address: *"Too many reset requests. Try again in a little
  while."*
- **The email**, subject *"Reset your GeoAlert password"*:
  > Hello {full name},
  > Someone asked to reset the password for your GeoAlert account. To choose a
  > new password, open this link within 1 hour:
  > {link}
  > If you didn't ask for this, ignore this email; your password stays the same.
- **Reset password** (`/reset-password/:uid/:token`, `pages/ResetPassword.jsx`):
  - On load it asks the backend whether the link is still good. If not:
    *"This link has expired or was already used."* and a "Send a new link"
    link to `/forgot-password`.
  - Otherwise: "New password" and "Confirm new password" with show/hide, and
    "Save new password". The passwords must match (*"The passwords don't
    match."*) before anything is sent. The server's rule messages show as
    they do on Change password.
  - On success: *"Password changed. Log in with your new password."* and a
    "Log in" link. Accounts with 2FA are asked for their code at that sign-in
    as usual.
- Both pages use the login page's look (`Login.css`, `lg-*` classes).

### 2. Backend

All three endpoints follow `LoginView`'s pattern: `AllowAny`, no
authentication classes, CSRF-exempt. They sit under `/api/auth/`, which the
must-change-password middleware already lets through.

| Endpoint | Body | Answer |
|---|---|---|
| `POST /api/auth/password-reset/` | `{email}` | 200 `{message}` (the generic text) always, except 429 `{error}` when the address is over its limit |
| `POST /api/auth/password-reset/check/` | `{uid, token}` | 200 `{valid: true\|false}` |
| `POST /api/auth/password-reset/confirm/` | `{uid, token, new_password}` | 200 `{message}`; 400 `{error}` for a bad link or a rejected password; 429 `{error}` when the address is over its failed-attempt limit |

- **request**: finds an *active* account by email (case-insensitive). If there
  is one and its per-account limit isn't reached, it sends the email. Unknown,
  deactivated and over-limit accounts get the same 200 answer and no email.
- **check**: decodes `uid`, loads the active account, and returns
  `default_token_generator.check_token(user, token)`.
- **confirm**: the same check (failure: *"This link has expired or was already
  used."*), then `validate_password(new_password, user)` (failure: the
  validator messages joined, as Change password does), then
  `set_password`, `must_change_password = False`, `failed_login_count = 0`,
  `locked_until = None`, `save()`. It does not sign anyone in. Changing the
  password hash ends every other session for the account (Django checks the
  session's password hash), and makes the token unusable, so a link works
  once.

New code:

- `apps/accounts/password_reset.py`: `find_active_user(email)`,
  `user_from_uid(uid)`, `reset_link(user) -> str`
  (`{FRONTEND_URL}/reset-password/{uid}/{token}`),
  `reset_email(user, link) -> (subject, body)`, `send_reset_email(user)`.
  Database access lives in the two lookup helpers, so the views can be
  tested without a database.
- `utils/reset_throttle.py`: `allow(key, limit, window) -> bool`, counting in
  the Django cache like `utils/login_throttle.py`. A cache outage allows the
  request (a reset must not be blocked by a cache fault).
- Limits: 10 requests per address per 15 minutes (over: 429); 3 emails per
  account per hour (over: generic answer, no email); 20 failed `confirm`
  attempts per address per 15 minutes (over: 429).

Settings:

- `base.py`: `PASSWORD_RESET_TIMEOUT = 3600`;
  `FRONTEND_URL = env('FRONTEND_URL', default='http://localhost:3000')`;
  `DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='GeoAlert <no-reply@geoalert.local>')`.
- `development.py`: `EMAIL_BACKEND = env('EMAIL_BACKEND',
  default='django.core.mail.backends.console.EmailBackend')`, so in
  development the email prints in the backend terminal. Setting
  `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` plus real
  `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` (a Gmail app password) sends real
  mail. Production keeps SMTP from `base.py`.
- `.env.example` gains `FRONTEND_URL`, `DEFAULT_FROM_EMAIL`, `EMAIL_BACKEND`
  and a line on Gmail app passwords.

### 3. Safety and errors

- The request page's answer never depends on whether the account exists.
- Deactivated accounts can't request or complete a reset.
- Audit log (`log_event`, with the account as `user` where one is known):
  `PASSWORD_RESET_REQUESTED` (email sent), `PASSWORD_RESET_EMAIL_FAILED`
  (sending raised; the person still sees the generic answer),
  `PASSWORD_RESET_DONE`, `PASSWORD_RESET_FAILED` (a bad or expired link for a
  known account, or a rejected password). Requests for unknown emails are not
  logged, so the log can't be filled with made-up addresses.
- The admin Logs tab gets labels for the four new actions
  (`ACTION_META` in `pages/Dashboard/admin/adminShared.jsx`).
- The token and the link never appear in the audit details; the account's
  email address does, as it does for other account events.

### 4. Frontend wiring

- `api/authApi.js`: `requestPasswordReset(email)`,
  `checkResetLink(uid, token)`, `confirmPasswordReset(uid, token, newPassword)`.
- `App.jsx`: public routes `/forgot-password` and `/reset-password/:uid/:token`.

## Testing

- **Backend** (`tests/test_password_reset.py`, `SimpleTestCase` only, since the
  database is the team's shared Supabase server):
  - `reset_link` builds `FRONTEND_URL/reset-password/<uid>/<token>`, and the
    token verifies for that (unsaved) user.
  - `reset_email` contains the name, the link, "1 hour" and the ignore line.
  - `allow` stops at the limit, and allows on a cache error.
  - The views, through `APIRequestFactory`, with `find_active_user`,
    `user_from_uid`, `send_reset_email`, `log_event` and `User.save` patched:
    unknown email → generic 200, no email; known → generic 200, email sent;
    per-account limit → generic 200, no email; per-address limit → 429;
    `check` with a bad token → `valid: false`; `confirm` with a bad token →
    400 and the expired message; a weak password → 400 with the rule
    messages; success → password set, flags and lockout cleared, saved.
- **Frontend** (Jest): the login page links to `/forgot-password`; Forgot
  password shows the generic message after sending, and the limit message on
  429; Reset password shows the expired message for a bad link, refuses
  mismatched passwords without calling the API, and shows success.
- **Live**, with the terminal email: request a reset for
  `editor.test@geoalert.local`, open the link printed in the backend output,
  set a new password, sign in with it, and confirm the old one is refused.
  This changes only the test account's password and adds normal audit rows.

## Files touched

Backend: `apps/accounts/password_reset.py` (new), `apps/accounts/views.py`,
`apps/accounts/urls.py`, `utils/reset_throttle.py` (new),
`config/settings/base.py`, `config/settings/development.py`, `.env.example`,
`tests/test_password_reset.py` (new).

Frontend: `pages/ForgotPassword.jsx` (new), `pages/ResetPassword.jsx` (new),
`pages/Login.jsx`, `App.jsx`, `api/authApi.js`,
`pages/Dashboard/admin/adminShared.jsx`, and their tests.

## Noticed, separate

- Real email needs a sending account: a Gmail address with 2-step
  verification and an app password in `.env`. That is the team's to set up;
  until then development prints the email in the backend terminal.
