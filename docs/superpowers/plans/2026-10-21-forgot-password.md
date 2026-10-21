# Forgot Password Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Staff reset a forgotten password themselves through a one-time, 1-hour link emailed to them.

**Architecture:** Django's `default_token_generator` signs a token tied to the account's password hash and time; three CSRF-exempt `AllowAny` endpoints under `/api/auth/password-reset/` request, check and confirm a reset. Database access sits in two lookup helpers so the views test without a database. The React side adds a "Forgot password?" link, a request page and a reset page in the login page's style.

**Tech Stack:** Django 4.2 + DRF (Python 3.11.9 venv); React 18, react-router 6, Jest via react-scripts 5.0.1.

**Spec:** `docs/superpowers/specs/2026-10-21-forgot-password-design.md`

## Global Constraints

- No new dependencies. No model or migration changes.
- Backend tests: from `backend/`, `venv/Scripts/python.exe manage.py test tests.test_password_reset`. `SimpleTestCase` only (the database is the team's shared Supabase server). Cache-touching tests use `@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})`.
- Frontend tests: from `frontend/`, `CI=true npx react-scripts test --watchAll=false <file>`; component tests use `createRoot` + `act`, `global.IS_REACT_ACT_ENVIRONMENT = true`, and `MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}`.
- `PASSWORD_RESET_TIMEOUT = 3600`.
- Copy, verbatim:
  - Generic request reply: `If an account with that email exists, we've sent a link to reset its password. It works for 1 hour.`
  - Request limit: `Too many reset requests. Try again in a little while.`
  - Bad link: `This link has expired or was already used.`
  - Mismatch: `The passwords don't match.`
  - Success: `Password changed. Log in with your new password.`
  - Email subject: `Reset your GeoAlert password`
  - Email body: `Hello {full name},\n\nSomeone asked to reset the password for your GeoAlert account. To choose a new password, open this link within 1 hour:\n\n{link}\n\nIf you didn't ask for this, ignore this email; your password stays the same.\n`
- Limits: 10 requests per address per 15 min (over → 429); 3 emails per account per hour (over → generic 200, no email); 20 failed confirms per address per 15 min (over → 429).
- Audit actions: `PASSWORD_RESET_REQUESTED`, `PASSWORD_RESET_EMAIL_FAILED`, `PASSWORD_RESET_DONE`, `PASSWORD_RESET_FAILED`. No log row for unknown emails. Token and link never in audit details.
- Commits: ask the user at handoff whether to commit per task or leave everything uncommitted (they chose uncommitted last time).

## Review Focus

1. An email typed with spaces or different capitals (` Juan@Example.com `) still finds the account. Pinned in Task 3 (`request` strips before lookup) and Task 2 (`find_active_user` matches case-insensitively).
2. A missing or non-string `email` (absent, `""`, `123`, a list) gets the generic 200, never a 500. Pinned in Task 3.
3. A malformed `uid` or `token` (not base64, not a UUID, empty, a number) gives `valid: false` or the bad-link 400, never a 500. Pinned in Task 2 (`user_from_uid` returns `None`) and Task 3.
4. Sending fails (SMTP down, the placeholder Gmail details): the person still sees the generic reply, and `PASSWORD_RESET_EMAIL_FAILED` is logged. Pinned in Task 3.
5. A link used once cannot be used again: after the password changes, the same token is refused. Pinned in Task 2.

---

### Task 1: Reset rate limiter

**Files:**
- Create: `backend/utils/reset_throttle.py`
- Test: `backend/tests/test_password_reset.py` (new file; later tasks append to it)

**Interfaces:**
- Produces: `allow(key: str, limit: int, window: int) -> bool` — counts one hit for `key` in the default cache, returns False once `limit` hits fall within `window` seconds; any cache exception returns True.
- Produces: `blocked(key: str, limit: int) -> bool` — True when `key` already has `limit` or more hits, without counting one; any cache exception returns False.

- [ ] **Step 1: Write the failing tests**

```python
from unittest import mock
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from utils import reset_throttle

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

@override_settings(CACHES=LOCMEM)
class AllowTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_allows_up_to_the_limit_then_refuses(self):
        self.assertEqual([reset_throttle.allow('k', 3, 60) for _ in range(4)], [True, True, True, False])

    def test_keys_are_counted_separately(self):
        for _ in range(3):
            reset_throttle.allow('a', 3, 60)
        self.assertTrue(reset_throttle.allow('b', 3, 60))

    def test_a_cache_fault_never_blocks_a_reset(self):
        with mock.patch.object(reset_throttle.cache, 'add', side_effect=RuntimeError):
            self.assertTrue(reset_throttle.allow('k', 1, 60))
        with mock.patch.object(reset_throttle.cache, 'get', side_effect=RuntimeError):
            self.assertFalse(reset_throttle.blocked('k', 1))

    def test_blocked_looks_without_counting(self):
        reset_throttle.allow('k', 2, 60)
        self.assertFalse(reset_throttle.blocked('k', 2))
        self.assertFalse(reset_throttle.blocked('k', 2))  # still one hit
        reset_throttle.allow('k', 2, 60)
        self.assertTrue(reset_throttle.blocked('k', 2))
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_password_reset`
Expected: ImportError for `utils.reset_throttle`.

- [ ] **Step 3: Implement `allow`** — `cache.add(key, 0, window)` then `cache.incr(key)`; refuse when the count exceeds `limit`. Prefix keys with `'pwreset:'`.

- [ ] **Step 4: Run to verify they pass**

Run: same. Expected: OK.

---

### Task 2: Reset link, email and lookups

**Files:**
- Create: `backend/apps/accounts/password_reset.py`
- Modify: `backend/config/settings/base.py` (after the `EMAIL_*` block), `backend/config/settings/development.py`, `backend/.env.example`
- Test: `backend/tests/test_password_reset.py` (append)

**Interfaces:**
- Produces (all in `apps/accounts/password_reset.py`):
  - `GENERIC_REPLY`, `BAD_LINK`, `SUBJECT` string constants (Global Constraints copy).
  - `find_active_user(email: str) -> User | None` — `User.objects.filter(email__iexact=email, is_active=True).first()`.
  - `user_from_uid(uid) -> User | None` — `None` for any value that isn't a string decoding (`urlsafe_base64_decode`) to a valid UUID; otherwise the active user with that pk or `None`. Never raises.
  - `uid_for(user) -> str` — `urlsafe_base64_encode(force_bytes(user.pk))`.
  - `reset_link(user) -> str` — `f'{settings.FRONTEND_URL.rstrip("/")}/reset-password/{uid_for(user)}/{default_token_generator.make_token(user)}'`.
  - `reset_email(user, link: str) -> tuple[str, str]` — `(SUBJECT, body)` with the verbatim body; the name is `user.full_name or user.email`.
  - `send_reset_email(user) -> None` — `send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])`; lets exceptions propagate.
- Settings: `PASSWORD_RESET_TIMEOUT = 3600`, `FRONTEND_URL = env('FRONTEND_URL', default='http://localhost:3000')`, `DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='GeoAlert <no-reply@geoalert.local>')`; `development.py`: `EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')`.

- [ ] **Step 1: Write the failing tests** (an unsaved `User(email='juan@example.com', full_name='Juan Dela Cruz')` with `set_password('Old-pass-2026')` needs no database)

```python
@override_settings(FRONTEND_URL='https://geoalert.example/')
class ResetLinkTests(SimpleTestCase):
    def setUp(self):
        self.user = User(email='juan@example.com', full_name='Juan Dela Cruz')
        self.user.set_password('Old-pass-2026')

    def test_link_points_at_the_reset_page_and_its_token_verifies(self):
        link = password_reset.reset_link(self.user)
        prefix = f'https://geoalert.example/reset-password/{password_reset.uid_for(self.user)}/'
        self.assertTrue(link.startswith(prefix))
        self.assertTrue(default_token_generator.check_token(self.user, link[len(prefix):]))

    def test_a_token_stops_working_once_the_password_changes(self):
        token = password_reset.reset_link(self.user).rsplit('/', 1)[1]
        self.user.set_password('New-pass-2026')
        self.assertFalse(default_token_generator.check_token(self.user, token))

    def test_the_email_names_the_person_the_link_and_the_hour(self):
        subject, body = password_reset.reset_email(self.user, 'https://x/reset-password/u/t')
        self.assertEqual(subject, 'Reset your GeoAlert password')
        self.assertIn('Hello Juan Dela Cruz,', body)
        self.assertIn('https://x/reset-password/u/t', body)
        self.assertIn('within 1 hour', body)
        self.assertIn("If you didn't ask for this, ignore this email; your password stays the same.", body)

class UidTests(SimpleTestCase):
    def test_garbage_uids_are_none_without_a_query(self):
        with mock.patch.object(User.objects, 'filter') as q:
            for bad in (None, '', 'abc', '!!!', 123, urlsafe_base64_encode(b'not-a-uuid')):
                self.assertIsNone(password_reset.user_from_uid(bad), bad)
            q.assert_not_called()

    def test_reset_timeout_is_one_hour(self):
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 3600)
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_password_reset`
Expected: ImportError for `apps.accounts.password_reset`.

- [ ] **Step 3: Implement the module and the settings**; add to `.env.example` under the email block: `FRONTEND_URL=http://localhost:3000`, `DEFAULT_FROM_EMAIL=GeoAlert <no-reply@geoalert.local>`, and a comment: development prints emails in the backend terminal; to send real mail set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` with a Gmail address and an app password (Google account › Security › App passwords).

- [ ] **Step 4: Run to verify they pass**

Run: same. Expected: OK.

---

### Task 3: The three endpoints

**Files:**
- Modify: `backend/apps/accounts/views.py` (new views after `ChangePasswordView`), `backend/apps/accounts/urls.py`
- Test: `backend/tests/test_password_reset.py` (append)

**Interfaces:**
- Consumes: Task 1 `allow`; Task 2 helpers and constants.
- Produces: `PasswordResetRequestView`, `PasswordResetCheckView`, `PasswordResetConfirmView` — each `@method_decorator(csrf_exempt, name='dispatch')`, `permission_classes = [AllowAny]`, `authentication_classes = []`, routed at `password-reset/`, `password-reset/check/`, `password-reset/confirm/`. The address comes from `utils.login_throttle.throttle_ip(request)`.

Behaviour:
- **request**: `email = request.data.get('email')`; anything not a non-empty string after `.strip()` → generic 200. Over `allow(f'ip:{ip}', 10, 900)` → 429 `{'error': <limit copy>}`. Else `find_active_user(email)`; none, or `allow(f'acct:{user.pk}', 3, 3600)` refused → generic 200. Else `send_reset_email(user)`: success → `log_event(request, 'PASSWORD_RESET_REQUESTED', 'app_user', user.id, user.email, user=user)`; exception → `log_event(..., 'PASSWORD_RESET_EMAIL_FAILED', ..., f'{user.email}: {type(exc).__name__}', user=user)`. Always 200 `{'message': GENERIC_REPLY}`.
- **check**: `user = user_from_uid(uid)`; 200 `{'valid': bool(user and isinstance(token, str) and default_token_generator.check_token(user, token))}`.
- **confirm**: first, `blocked(f'confirm:{ip}', 20)` → 429 `{'error': <limit copy>}` without checking the token, so a blocked address can't keep guessing. Every failure below then calls `allow(f'confirm:{ip}', 20, 900)` to count itself; success never counts. Bad link → `PASSWORD_RESET_FAILED` (when `user` is known) and 400 `{'error': BAD_LINK}`. `validate_password(new_password, user)` failure (or missing/non-string password) → `PASSWORD_RESET_FAILED` and 400 `{'error': ' '.join(messages)}`. Success → `set_password`, `must_change_password = False`, `failed_login_count = 0`, `locked_until = None`, `save()`, `PASSWORD_RESET_DONE`, 200 `{'message': <success copy>}`.

- [ ] **Step 1: Write the failing tests** (patch targets: `apps.accounts.views.find_active_user`, `.user_from_uid`, `.send_reset_email`, `.log_event`, and `User.save`; `LOCMEM` cache)

```python
@override_settings(CACHES=LOCMEM)
class RequestViewTests(SimpleTestCase):
    # post(body) -> response via APIRequestFactory().post('/api/auth/password-reset/', body, format='json')
    def test_unknown_email_gets_the_generic_reply_and_no_email(self): ...      # find -> None; 200, message == GENERIC_REPLY; send not called; log not called
    def test_known_email_gets_the_same_reply_and_an_email(self): ...          # 200 generic; send called with the user; log action PASSWORD_RESET_REQUESTED
    def test_the_email_is_trimmed_before_the_lookup(self): ...                # {'email': ' Juan@Example.com '} -> find called with 'Juan@Example.com'
    def test_missing_or_odd_email_values_never_fail(self): ...                # for body in ({}, {'email': ''}, {'email': 123}, {'email': ['a']}): 200 generic, find not called
    def test_a_failed_send_still_answers_generically_and_is_logged(self): ... # send raises SMTPException -> 200 generic; log action PASSWORD_RESET_EMAIL_FAILED
    def test_three_emails_per_account_per_hour(self): ...                     # 4 posts -> send called 3 times; all 200 generic
    def test_ten_requests_per_address_then_429(self): ...                     # 11th post -> 429, error == limit copy

@override_settings(CACHES=LOCMEM)
class CheckViewTests(SimpleTestCase):
    def test_a_good_link_is_valid(self): ...                                  # user_from_uid -> user; real token -> {'valid': True}
    def test_bad_or_odd_links_are_invalid(self): ...                          # (None user), (user, 'wrong'), (user, 123) -> {'valid': False}, status 200

@override_settings(CACHES=LOCMEM)
class ConfirmViewTests(SimpleTestCase):
    def test_a_bad_link_is_refused(self): ...                                 # 400, error == BAD_LINK; log PASSWORD_RESET_FAILED when user known
    def test_a_weak_password_is_refused_with_the_rules(self): ...            # new_password '12345678' -> 400; error contains 'entirely numeric'
    def test_success_sets_the_password_and_clears_flags_and_lockout(self):   # user.must_change_password=True, failed_login_count=5, locked_until=now
        ...                                                                   # 200 success copy; user.check_password(new); flags cleared; save called; log PASSWORD_RESET_DONE
    def test_twenty_failures_per_address_then_429(self): ...                  # 21st bad confirm -> 429
```

Each `...` is filled with exactly the assertions in its trailing comment.

- [ ] **Step 2: Run to verify they fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_password_reset`
Expected: ImportError / AttributeError for the new views.

- [ ] **Step 3: Implement the three views and the URL entries.**

- [ ] **Step 4: Run to verify they pass, then the existing auth-adjacent suites**

Run: `venv/Scripts/python.exe manage.py test tests.test_password_reset tests.test_login_throttle tests.test_session_limits tests.test_password_hashing`
Expected: OK.

- [ ] **Step 5: Smoke without auth** (the endpoint is public and read-only for an unknown email)

Run: `curl -s -X POST -H "Content-Type: application/json" -d '{"email":"nobody@example.com"}' http://127.0.0.1:8000/api/auth/password-reset/`
Expected: `{"message": "If an account with that email exists, …"}`, and nothing printed as an email in the backend log.

---

### Task 4: Forgot password page, login link, API calls, log labels

**Files:**
- Create: `frontend/src/pages/ForgotPassword.jsx`, `frontend/src/pages/forgotPassword.test.js`
- Modify: `frontend/src/api/authApi.js`, `frontend/src/App.jsx` (public routes, next to `/login`), `frontend/src/pages/Login.jsx` (link after the password field), `frontend/src/pages/css/Login.css`, `frontend/src/pages/Dashboard/admin/adminShared.jsx` (`ACTION_META`)

**Interfaces:**
- Produces in `authApi`: `requestPasswordReset(email) -> Promise<{message}>`, `checkResetLink(uid, token) -> Promise<{valid}>`, `confirmPasswordReset(uid, token, newPassword) -> Promise<{message}>` (POST bodies `{email}`, `{uid, token}`, `{uid, token, new_password}`).
- Routes: `/forgot-password` → `ForgotPassword`, `/reset-password/:uid/:token` → `ResetPassword` (Task 5).
- `ACTION_META` entries: `PASSWORD_RESET_REQUESTED: { label: 'Requested password reset', tone: 'info', icon: 'key' }`, `PASSWORD_RESET_EMAIL_FAILED: { label: 'Reset email failed', tone: 'bad', icon: 'alert' }`, `PASSWORD_RESET_DONE: { label: 'Reset own password', tone: 'warn', icon: 'key' }`, `PASSWORD_RESET_FAILED: { label: 'Password reset failed', tone: 'bad', icon: 'key' }`.

- [ ] **Step 1: Write the failing tests** (`authApi` and `AuthContext` mocked; `Login` rendered for the link test)

```js
test('the login page links to Forgot password', ...);          // <a href="/forgot-password">Forgot password?</a> present
test('sending shows the same reply whatever the email', ...);   // type email, submit -> requestPasswordReset('juan@example.com'); text contains the generic reply; a 'Back to log in' link to /login
test('too many requests says so', ...);                          // requestPasswordReset rejects {status: 429} -> text contains the limit copy
test('the button waits while sending', ...);                    // pending promise -> submit button disabled and reads 'Sending…'
```

- [ ] **Step 2: Run to verify they fail**

Run: `CI=true npx react-scripts test --watchAll=false src/pages/forgotPassword.test.js`
Expected: FAIL, cannot find `./ForgotPassword`.

- [ ] **Step 3: Implement** — the page reuses the login card (`lg-card`, `lg-brand`, `lg-head`, `lg-field`, `lg-submit`, `lg-error`, `lg-note`); heading `Forgot your password?`, sub line `Enter your account's email and we'll send you a link to choose a new one.`; button `Send reset link` / `Sending…`. Any error other than 429 shows the generic reply too (nothing about the account leaks). The login link sits under the password field: `<Link to="/forgot-password" className="lg-forgot">Forgot password?</Link>`, right-aligned, `.84rem`.

- [ ] **Step 4: Run to verify they pass**

Run: same. Expected: PASS.

---

### Task 5: Reset password page

**Files:**
- Create: `frontend/src/pages/ResetPassword.jsx`, `frontend/src/pages/resetPassword.test.js`

**Interfaces:**
- Consumes: Task 4 `checkResetLink`, `confirmPasswordReset`; route params `uid`, `token`.

- [ ] **Step 1: Write the failing tests** (render inside `MemoryRouter initialEntries={['/reset-password/u1/t1']}` with a `<Routes><Route path="/reset-password/:uid/:token" element={<ResetPassword />} /></Routes>`)

```js
test('a bad link says so and offers a new one', ...);            // checkResetLink -> {valid:false}: text contains BAD_LINK copy; link to /forgot-password 'Send a new link'; no password fields
test('mismatched passwords are refused before anything is sent', ...); // valid link; type 'Abc-12345678' / 'Abc-12345679'; submit -> mismatch copy; confirmPasswordReset not called
test('the server rules show as they come back', ...);            // confirm rejects {status:400, message:'This password is too common.'} -> that text shown
test('success says so and links to log in', ...);                // confirm resolves -> called with ('u1','t1','Abc-12345678'); success copy; link to /login; fields gone
test('an expired link found on save says so', ...);              // confirm rejects {status:400, message: BAD_LINK copy} -> BAD_LINK copy and the 'Send a new link' link
```

- [ ] **Step 2: Run to verify they fail**

Run: `CI=true npx react-scripts test --watchAll=false src/pages/resetPassword.test.js`
Expected: FAIL, cannot find `./ResetPassword`.

- [ ] **Step 3: Implement** — check the link on mount (`cancelled` guard; show `Checking your link…` meanwhile; a failed check request counts as a bad link); heading `Choose a new password`; fields `New password` / `Confirm new password` with one Show/Hide toggle (`lg-show`); button `Save new password` / `Saving…`; error messages read `err.message` (axiosClient puts the server's `error` there, as Change password relies on). Login card styles, as Task 4.

- [ ] **Step 4: Run to verify they pass, then the whole frontend suite**

Run: `CI=true npx react-scripts test --watchAll=false`
Expected: all pass.

---

### Task 6: Whole flow in the running app

**Files:** scratchpad only (no repo changes).

- [ ] **Step 1:** With both dev servers running and the console email backend, open `/login`, follow "Forgot password?", request a reset for `editor.test@geoalert.local`. Expected: the generic reply on screen; the email (subject, body, link) printed in the backend server's output; `PASSWORD_RESET_REQUESTED` written.
- [ ] **Step 2:** Before resetting, sign in as `editor.test` in a second browser context and keep it. Open the printed link, try mismatched passwords (refused), then set a new valid password. Expected: success copy; signing in with the new password works (the forced-change screen does not appear); the previous password is refused; opening the same link again shows the bad-link copy; the second context's next request (`/api/auth/me/`) is refused, so it was signed out.
- [ ] **Step 3:** Screenshots of the login link, the request page, the reset page and the success state at 1366 and 390 px; no sideways scroll; look at each.
- [ ] **Step 4:** Report to the user, with the new `editor.test` password, the screenshot paths, and what is needed for real email (Gmail address + app password in `.env`, `EMAIL_BACKEND` set to SMTP).
