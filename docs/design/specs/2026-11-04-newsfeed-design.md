# Newsfeed — design

Date: 2026-11-04
Status: draft for review
Branch: merge-scout

## Why

Our adviser suggested a newsfeed. Today a resident who opens GeoAlert sees the map and the
safety guides, but nothing tells them in one place what is happening now or what the office
has said: a typhoon advisory, a drill, a fire station notice. The feed puts the office's
announcements and the hazards that went on the map side by side, newest first, with no login.

Success: a resident opens the home page or the News page and sees, in one list, the alerts
that went out and what DRRMO or BFP announced, and can tell a live hazard from an old one.

## Decisions (agreed 2026-11-04)

1. **Two kinds of post in one feed:** announcements people write, and a post for each hazard
   alert that went out (a hazard went on the map).
2. **Public:** the 3 newest posts on the home page, and the full feed on a News page in the
   top menu. No login to read.
3. **Who writes announcements:** DRRMO, admins and BFP. A post shows the office it is from
   (DRRMO or BFP; admins post as DRRMO), never a staff member's name.
4. **Automatic posts are new alerts only:** no separate posts for a raise to Extreme, an
   all-clear or a withdrawal.
5. An alert post **stays after the hazard ends and shows its status** (Active or Resolved),
   so an old fire never reads as a live one. A **withdrawn** alert (published in error)
   drops out of the feed. **Sample** hazards never appear.
6. An announcement is a title, text and an optional photo, published when saved. Its author
   can edit or delete it; DRRMO and admins can edit or delete any (BFP's included).

## Non-goals

- Drafts, scheduled posts, pinning, expiry.
- Comments, reactions, sharing.
- Sending announcements as notifications, SMS or email (the bell stays as it is).
- Rich text or HTML in posts; links typed in the text are plain text.
- Pulling news from outside sources (PAGASA, PHIVOLCS, the city's page).
- Posts for raises, all-clears or withdrawals (decision 4).

## Design

### 1. Data: `apps/news`, one table

`Announcement` (table `announcement`, columns prefixed `anno_` like the other tables):

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | primary key |
| `title` | text, up to 150 | required |
| `body` | text, up to 5,000 | required; shown as plain text with its line breaks |
| `photo` | image, optional | stored like report photos: key `news/YYYY/MM/<uuid><ext>` in the Supabase bucket, or under `MEDIA_ROOT` when storage falls back to local disk |
| `source` | `DRRMO` or `BFP` | set when the post is created from the author's role; admins post as DRRMO. Kept on the row so a post keeps its office if the author's role changes |
| `created_by` | user, nullable | `SET_NULL`: the post outlives a deleted account |
| `created_at`, `updated_at` | timestamps | `updated_at` shows as "edited" when it is more than a minute after `created_at` |

Deleting a post, or replacing or removing its photo, deletes the stored photo file too.

Alert posts are **not stored**. They are read from hazard zones when the feed is asked for, so
an alert post always shows the zone's current state and nothing can drift out of step with the
map. The alert-sending code is not touched.

### 2. The feed: `GET /api/news/` (public)

Query: `limit` (default 10, at most 30) and `before` (an ISO timestamp; only posts older than it).
Answer: `{"results": [...], "next_before": "<timestamp>" | null}`, newest first. The client
asks again with `before=next_before` for the next page ("Load more"); `null` means the end.

How a page is built: the newest `limit` announcements older than `before`, and the newest
`limit` alert posts older than `before`, merged by time and cut to `limit`. `next_before` is the
time of the last post returned when more remain in either list.

**Announcement post:**
`{kind: "announcement", id, title, body, photo_url, source, published_at, edited_at, can_edit}`.
`photo_url` is the absolute URL (signed and short-lived for Supabase, as report photos are).
`edited_at` is `updated_at` when the post was edited, else null. `can_edit` is true when the
person asking may edit or delete it (section 3); false for anyone signed out.

**Alert post**, one per hazard zone that went out:
`{kind: "alert", id: <zone id>, hazard_type, severity, published_at, barangay, puroks, status, map_link}`.
- `published_at` is when the zone's **first alert** went out (its earliest `HazardAlert`).
  A zone with no alert never went public, so it has no post: this leaves out an Extreme alert
  still waiting for a second officer.
- `severity` is the zone's current level (`Red`, `Orange`, `Green`); the card shows
  Extreme, Moderate or Low.
- `barangay` is the zone's barangay name; `puroks` are the purok names its reports named,
  in the order the map's pins show them.
- `status` is `active` for a zone that is Active (or Resolving, left by the old two-step fire
  close) and `resolved` for Resolved or Archived.
- `map_link` is `/map?zone=<id>` while active, null once resolved (it is off the map).
- Left out: sample zones, and Retracted (withdrawn) zones.

Ties: two posts with the same timestamp to the microsecond could straddle a page boundary
and one be skipped. Timestamps are stored to the microsecond, so this is accepted.

### 3. Writing: `POST /api/news/`, `PATCH /api/news/<id>/`, `DELETE /api/news/<id>/`

- **Post** (multipart: `title`, `body`, optional `photo`): DRRMO, admins and BFP
  (the existing `IsBFPPersonnel` permission, which lets in BFP, DRRMO and admins).
  Barangay personnel and anyone signed out get 403 / 401.
- **Edit** (`title`, `body`, a new `photo`, or `remove_photo=true`) and **delete**: the
  post's author, or any DRRMO officer or admin. BFP personnel can change only their own posts.
  Anyone else gets 403.
- **Checks:** title and text required after trimming, at most 150 and 5,000 characters; a photo
  must be a real image (Pillow checks it, as for report photos), JPEG, PNG or WebP, at most
  5 MB. A failed check answers 400 with `{field: message}`.
- **Audit log:** `POST_NEWS`, `EDIT_NEWS`, `DELETE_NEWS`, with the post's title, so the admin's
  activity log shows who changed what.

### 4. Screens

- **News page** (`/news`, public, "News" in the top menu between Map and About): the feed,
  newest first, with "Load more" until `next_before` is null.
  - Announcement card: the office badge (DRRMO or BFP), title, date (and "edited"),
    photo, and the text with its line breaks.
  - Alert card: the hazard's icon and colour, "Fire alert (Moderate) for Mohon · Purok
    Santol", the date, an Active or Resolved status, and "View on map" while active.
  - Signed-in DRRMO, admins and BFP see **New announcement** at the top, and **Edit** and
    **Delete** on the posts whose `can_edit` is true. Posting and editing use one form in a
    window: title, text, photo (with a preview, and Remove photo when editing).
- **Home page:** a "Latest updates" section with the 3 newest posts in the same cards and a
  "See all news" link, after the hero. If the feed can't be loaded or is empty, the section
  is not shown.
- **Admin activity log:** labels for the three new audit actions.

Text is rendered as text, never as HTML, so a post can't inject markup.

### 5. Errors

- The News page shows "Couldn't load the news. Try again." with a retry button when the feed
  fails; a failed "Load more" keeps the posts already shown and offers to try again.
- The form shows the server's messages under each field; a failed save keeps what was typed.
- Deleting asks for confirmation first.

### 6. Tests

Backend (against the database, like the other view tests):
- The feed is public and newest first, merging announcements and alert posts; `before` and
  `limit` page through it; `next_before` is null at the end.
- Alert posts: a zone that went out appears with its first alert's time and its status; one
  resolved shows `resolved` with no map link; sample, retracted and never-alerted (held) zones
  don't appear.
- Writing: DRRMO, admin and BFP can post, and the post's `source` follows the role; barangay
  personnel get 403; BFP can edit their own post but not DRRMO's; DRRMO can delete a BFP post;
  `can_edit` matches; bad title, text or photo answer 400; each change is in the audit log.

Frontend:
- The feed renders both kinds of card, plain text with line breaks, Active/Resolved and the
  map link only while active; Load more appends the next page.
- New announcement and Edit/Delete show only for those allowed; the form sends title, text and
  photo and shows field errors.
- The home section shows 3 posts and hides when the feed fails or is empty.

## Files

New: `backend/apps/news/` (app, model, migration, serializers, views, urls, feed builder),
`backend/tests/test_news.py`, `frontend/src/api/newsApi.js`,
`frontend/src/components/News/` (feed, cards, form and their tests),
`frontend/src/pages/News.jsx`, `frontend/src/pages/css/News.css`.

Changed: `backend/config/settings/base.py` (install the app), `backend/config/urls.py`
(`api/news/`), `frontend/src/App.jsx` (route), `frontend/src/components/Navbar/PublicNavbar.jsx`
(menu link), `frontend/src/pages/PublicHome.jsx` (Latest updates),
`frontend/src/pages/Dashboard/admin/adminShared.jsx` (audit labels).
