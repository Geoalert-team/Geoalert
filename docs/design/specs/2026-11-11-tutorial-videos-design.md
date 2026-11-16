# Tutorial videos — design

Date: 2026-11-11
Status: draft for review (revised: managed on the What To Do page, not the dashboards)
Branch: merge-scout

## Why

The What To Do page shows 10 first aid videos, but they are hardcoded in
`frontend/src/data/safetyGuides.js` (`VIDEOS`). Adding, fixing or removing a video means
changing code, so DRRMO can't do it themselves. Before a typhoon or a drill, staff want to put
up a batch of videos quickly: some from YouTube, some recorded by the office as MP4 files.

Success: a signed-in DRRMO officer opens the What To Do page, adds several videos in one go
(pasting YouTube links, dropping MP4 files, or both), and residents see them on the same page,
grouped by category, with no code change.

## Decisions (agreed 2026-11-11)

1. **Who manages:** DRRMO officers and admins add, edit and delete videos and categories (the
   existing `IsDRRMOOfficer` permission on the server, `canPublish` on the page: the same
   people who edit the What To Do guides).
   BFP and barangay personnel can watch but not change anything.
2. **Who watches:** everyone. The videos are public on the What To Do page with no login, and
   there is no per-video visibility setting. They replace the hardcoded list; the 10 current
   videos move into the database under a "First Aid" category.
3. **Two kinds of video, mixed freely:** a YouTube link or an uploaded MP4 file. One batch can
   hold both, and an edit can switch a video from one kind to the other.
4. **MP4 size:** at most 50 MB per file, the most the Supabase free plan allows per file. The
   free plan's 1 GB is shared with report and news photos, so the form shows how much the
   uploaded videos use. Longer videos go on YouTube.
5. **Flow:** one batch form, not a 4-step wizard. The category is picked once for the batch,
   media comes before details so titles fill themselves in, and every row is reviewed on the
   same screen before Publish.
6. **Where:** on the What To Do page itself, in its videos section, the way guides are edited
   there now. Staff see **Add videos**, and **Edit** and **Delete** for the video playing; residents
   see none of it. Nothing is added to the dashboards.

## Non-goals

- A video manager on the DRRMO or admin dashboard (decision 6).
- Searching videos. The page's search stays for guides only.
- Drag-to-reorder. Videos show in the order they were added.
- Drafts, scheduled publishing, staff-only videos (decision 2).
- View counts, likes, comments.
- Custom thumbnails, or generated thumbnails for MP4s (they show a play-icon tile).
- Converting or compressing uploads (no ffmpeg on the server).
- Uploads over 50 MB, or uploads straight from the browser to storage.
- Linking categories to hazard types. A category is free text.

## Design

### 1. Data: `apps/tutorials`, two tables

`VideoCategory` (table `video_category`, columns prefixed `vdct_`):

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | primary key |
| `name` | text, up to 60 | required after trimming; unique ignoring case (a `Lower(name)` unique constraint), so "First aid" and "First Aid" can't both exist |
| `created_at` | timestamp | |

Categories are listed A–Z. A category that still has videos can't be deleted (`PROTECT`).

`TutorialVideo` (table `tutorial_video`, columns prefixed `tvid_`):

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | primary key |
| `category` | category | required; `PROTECT` |
| `title` | text, up to 120 | required after trimming |
| `description` | text, up to 500 | optional; shown as plain text |
| `source_type` | `youtube` or `upload` | |
| `youtube_id` | text, 11 | only the video ID (e.g. `2v8vlXgGXwE`), never the pasted link; blank for uploads |
| `file` | file, optional | key `tutorials/YYYY/MM/<uuid>.mp4` in the Supabase bucket, or under `MEDIA_ROOT` when storage falls back to local disk (as news photos are); blank for YouTube videos |
| `file_size` | bytes, nullable | set from the upload; used for "MP4 · 34 MB" and the total |
| `created_by` | user, nullable | `SET_NULL` |
| `created_at`, `updated_at` | timestamps | |

A database check keeps the two kinds apart: a `youtube` row has a `youtube_id` and no file;
an `upload` row has a file and no `youtube_id`. Videos are ordered by category name, then
`created_at` (oldest first, so a series stays in the order it was added).

Deleting a video, or replacing its file or switching it to YouTube, deletes the stored file
too, as news photos are.

A data migration creates "First Aid" and the 10 videos now in `VIDEOS`, with their current
titles and no description. `VIDEOS` is then removed from `safetyGuides.js`.

### 2. Reading YouTube links: `apps/tutorials/youtube.py`

`parse_youtube_id(text)` returns the 11-character ID, or `None`. It accepts:
`youtube.com/watch?v=ID` (with or without `www.` or `m.`, and with extra parameters such as
`&t=42s` or `&list=…`), `youtu.be/ID`, `youtube.com/shorts/ID`, `youtube.com/embed/ID`,
`youtube-nocookie.com/embed/ID`, and a bare ID. The ID must match `[A-Za-z0-9_-]{11}`.
Anything else (another site, a channel or playlist link with no video) is `None`.

`lookup(youtube_id)` asks YouTube's public oEmbed endpoint
(`https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=<id>&format=json`,
no API key, 5-second timeout, using `requests`) and returns one of:
- `{"status": "ok", "title": "…"}`
- `{"status": "not_found"}`: YouTube answers 400, 401, 403 or 404 (deleted, private, or
  can't be embedded)
- `{"status": "unchecked"}`: YouTube didn't answer (timeout or network error)

`frontend/src/utils/youtube.js` has the same `parseYouTubeId`, so a row shows its thumbnail
the moment a link is pasted. The server's copy is the one that decides what is saved.

### 3. The API: `/api/tutorials/`

Reading is public; everything else is DRRMO officers and admins (`IsDRRMOOfficer`). Anyone
else gets 401 (signed out) or 403.

| Method and path | Who | What |
|---|---|---|
| `GET /api/tutorials/` | anyone | every video, in the order above |
| `POST /api/tutorials/` | DRRMO, admins | add **one** video (multipart) |
| `PATCH /api/tutorials/<id>/` | DRRMO, admins | edit title, description, category, or the media |
| `DELETE /api/tutorials/<id>/` | DRRMO, admins | delete it and its file |
| `GET /api/tutorials/categories/` | anyone | `[{id, name, video_count}]`, A–Z |
| `POST /api/tutorials/categories/` | DRRMO, admins | `{name}` → the new category |
| `PATCH /api/tutorials/categories/<id>/` | DRRMO, admins | rename |
| `DELETE /api/tutorials/categories/<id>/` | DRRMO, admins | delete; 409 with a message if it still has videos |
| `GET /api/tutorials/youtube-check/?url=…` | DRRMO, admins | `{youtube_id, status, title, duplicate}` |

One video per `POST` is what lets the form show progress per row, and a failed row be retried
without resending the others.

**A video, as sent:**
`{id, title, description, category: {id, name}, source_type, youtube_id, file_url,
file_size, created_at}`. `file_url` is absolute (signed, valid one hour, on Supabase), built
the way report photos' URLs are (`photo_url`); null for YouTube videos. `youtube_id` is null
for uploads.

**Writing** (multipart): `category` (an id), `title`, `description`, `source_type`, and either
`youtube_url` (a pasted link; the server stores only the ID) or `file`.
- `youtube_url` must parse (`parse_youtube_id`), else 400 "That isn't a YouTube video link."
  The server does **not** call YouTube when saving; the form already checked it (below), and a
  slow YouTube must not block a save.
- `file` must end in `.mp4`, be at most 50 MB ("That video is 63.2 MB. Please use one under
  50 MB, or put it on YouTube."), and really be an MP4: bytes 4–7 are `ftyp`, so a renamed
  file is refused ("That file isn't an MP4 video."). Stored with content type `video/mp4` so
  browsers play it.
- Switching `source_type` on an edit needs the new media in the same request.
- A failed check answers 400 with `{field: message}`.

**`youtube-check`** parses the link, then calls `lookup`. `duplicate` is the category name of
a video already using that ID, else null. A link that doesn't parse answers 400.

**Audit log:** `ADD_VIDEO`, `EDIT_VIDEO`, `DELETE_VIDEO` (with the title) and
`ADD_VIDEO_CATEGORY`, `RENAME_VIDEO_CATEGORY`, `DELETE_VIDEO_CATEGORY` (with the name), shown
in the admin activity log with their own labels.

### 4. The What To Do page

The videos section moves out of `WhatToDo.jsx` into its own component,
`components/Tutorials/TutorialVideos.jsx`, which `WhatToDo.jsx` renders where the section is
now. It reads from `GET /api/tutorials/`.

**What everyone sees:**
- The heading becomes "Tutorial videos".
- Category chips above the player: **All**, then each category that has videos. The first
  video of the chosen category plays.
- The player (`VideoPlayer.jsx`) plays YouTube videos in the `youtube-nocookie.com` frame used
  now, and MP4s in a `<video controls preload="metadata">`. Under it: the category, the title,
  the description, and "Watch on YouTube" for YouTube videos only.
- The playlist beside it: a thumbnail (YouTube's, or a play-icon tile for an MP4), the title,
  and the category.
- Choosing a hazard higher up the page no longer changes the video (categories aren't tied to
  hazards).
- An MP4's link lasts an hour. If it fails to play, the section fetches the list again once
  and retries with the fresh link.
- If the list can't be loaded: "Couldn't load the videos. Try again." with a retry button.
  If there are no videos, residents don't see the section.

**What DRRMO officers and admins see as well** (`canPublish`, as for guides):
- **Add videos** beside the heading.
- **Edit** and **Delete** for the chosen (playing) video only, just under its card in the
  playlist (changed 2026-11-11 at the user's word: not on every playlist item). Clicking
  another video moves them to it.
- When there are no videos, the section still shows for them: "No videos yet." and
  **Add videos**.
- Like the guide editor, one form is open at a time: while the form is open, Add videos and
  the Edit and Delete buttons are hidden. The tools are hidden too while the list is loading
  or failed to load.

```
TUTORIAL VIDEOS                                          [Add videos]  ← staff only
Short lessons. Watch and share them with your family.
[All] [First Aid] [Flood Preparedness]
┌──────────────────────────────────┐  ┌──────────────────────────────────┐
│                                  │  │ ▶ How to treat a fracture        │
│             player               │  │   First Aid                      │
│                                  │  │                  [Edit] [Delete] │ ← staff only, chosen video
├──────────────────────────────────┤  │ ▶ Recovery position              │
│ FIRST AID                        │  │   First Aid                      │
│ How to treat a fracture          │  │ ▶ Barangay flood drill 2026      │
│ Keep the limb still, pad it…     │  │   Flood · MP4                    │
│                 Watch on YouTube │  └──────────────────────────────────┘
└──────────────────────────────────┘
```

**Adding videos** (`AddVideosForm.jsx`). Pressing Add videos opens the form in place, at the
top of the section, and scrolls to it, as the guide editor opens in place. The four steps sit
on one screen:

1. **Category:** a picker (`CategoryPicker.jsx`) with the categories A–Z. Beside it:
   **+ New category**, which creates one in place; **Rename**, for the chosen category; and
   **Delete**, shown only when the chosen category has no videos. The category applies to
   every row; a row can change its own.
2. **Media:** a box for YouTube links and a drop zone for MP4 files, side by side, both
   always there. Rows from either sit in the same batch.
   - Links: one or more, one per line. Each link becomes a row. Each row asks
     `youtube-check`; on `ok` the title fills in from YouTube.
   - Files: dropped, or picked with a file button, several at a time. Each file becomes a row,
     its title filled in from the file name (`flood-drill_2026.mp4` → "flood drill 2026").
     The row plays the file in the browser (`URL.createObjectURL`), so a video the browser
     can't play (for example a phone recording in HEVC) shows up before it is uploaded.
   - Under the drop zone: "Up to 50 MB each. Uploaded videos use 212 MB of the 1 GB shared
     with report photos." (the sum of `file_size`).
3. **Details:** each row has its title and a short description.
4. **Review:** each row shows its state:
   - **Ready**
   - **Needs a title**
   - **Not a YouTube link** / **Video not found or private** (`not_found`)
   - **Couldn't check with YouTube**: allowed; the title must be typed
   - **Too big (63.2 MB, limit 50 MB)** / **Not an MP4**
   - **Already in First Aid**: a warning, allowed

   Every row has a remove button. **Publish N videos** turns on when no row has a blocking
   state.

**Publishing:** rows are sent one at a time, in order. A YouTube row saves at once. An MP4 row
shows a progress bar for the upload (axios `onUploadProgress`), then "Saving…" while the
server passes it to storage. A saved row is marked done and stays saved even if a later row
fails. A failed row keeps what was typed, shows the server's message, and offers **Retry**.
When all are done: "4 videos published", **Add more videos** (an empty form, same category)
and **Done**, which closes the form and shows the new videos in the playlist. Leaving while
rows are still sending (Cancel, or leaving the page) asks "2 videos are still uploading.
Leave anyway?"

```
┌ Add videos ───────────────────────────────────────────────────────┐
│ Category [First Aid ▾]  + New category   Rename                   │
│                                                                   │
│ ┌ YouTube links ──────────────┐  ┌ MP4 files ───────────────────┐ │
│ │ Paste one or more links,    │  │  Drop MP4 files here         │ │
│ │ one per line                │  │  or [Choose files]           │ │
│ └─────────────────────────────┘  └──────────────────────────────┘ │
│   Up to 50 MB each. Uploaded videos use 212 MB of the 1 GB…       │
│                                                                   │
│ 1 ┌thumb┐ Title [How to treat a fracture     ]  YouTube · Ready 🗑 │
│   └─────┘ About [Keep the limb still…        ]                    │
│ 2 ┌ ▶   ┐ Title [flood drill 2026            ]  MP4 · 31 MB    🗑 │
│   └─────┘ About [                             ]  ████████░░ 62%   │
│ 3 ┌ ✕   ┐ youtu.be/abc123  ⚠ Video not found or private        🗑 │
│                                                                   │
│        [Cancel]  [Publish 3 videos] (off until row 3 is fixed)    │
└───────────────────────────────────────────────────────────────────┘
```

**Editing** opens the same form in place with one row, filled in. The row shows its current
media; pasting a new link or choosing a new file replaces it on save, from either kind
(decision 3). **Save** instead of Publish.

**Deleting** asks first, with the browser's confirm box as deleting guidance does: "Delete
'How to treat a fracture'? Residents will stop seeing it." For an MP4: "…The uploaded file is
deleted too." Deleting a category asks first too.

Text is rendered as text, never as HTML.

### 5. Errors

- The section shows "Couldn't load the videos. Try again." with a retry button when the list
  fails.
- The form shows the server's messages on the row they belong to; a failed save keeps what
  was typed.
- A failed delete shows its message above the playlist, as a failed guidance delete does.
- A category name already in use answers 400 "There is already a category called First Aid."
- Two staff editing the same video: the last save wins. Accepted.

### 6. Tests

Backend (`backend/tests/test_tutorial_videos.py`, against the database like the other view
tests; YouTube's oEmbed is mocked, never called):
- `parse_youtube_id` reads every accepted link form and refuses other sites, channel and
  playlist-only links, and IDs of the wrong length or characters.
- `lookup` maps YouTube's answers to `ok` (with title), `not_found` (400/401/403/404) and
  `unchecked` (timeout, connection error).
- Reading is public; DRRMO and admins can add, edit and delete; BFP, barangay personnel and
  signed-out users get 403 / 401 on every write.
- Adding a YouTube video stores only the ID; a bad link answers 400.
- Adding an MP4 stores the file and its size; a file over 50 MB, a non-`.mp4` name and a
  renamed non-MP4 each answer 400.
- An edit can switch a video from YouTube to MP4 and back; switching without the new media
  answers 400.
- The database check refuses a row with both a file and a YouTube ID, or neither.
- Replacing a file, switching to YouTube and deleting a video each delete the old file.
- A category name is unique ignoring case; a category with videos can't be deleted (409).
- `youtube-check` reports `duplicate` for an ID already saved.
- Each change is in the audit log.
- The data migration creates "First Aid" with the 10 videos.

Frontend:
- `parseYouTubeId` matches the backend's cases.
- The section: residents see no Add, Edit or Delete; staff do; it plays YouTube and MP4
  videos, filters by category chip, hides from residents when there are no videos but shows
  "No videos yet." to staff, and shows the retry message when loading fails.
- The form: pasting three links and dropping two files makes five rows in one batch, the
  files' titles taken from their names; a file over 50 MB shows Too big without uploading;
  Publish is off while a row is blocking; publishing sends one request per row in order; a
  failed row shows Retry while the others stay done; Add more videos keeps the category;
  editing a YouTube video with a new file switches it to MP4.
- Deleting asks first.

Checked by hand, once, on the real Supabase storage: a 50 MB MP4 uploads, plays, and can be
skipped forward. The bucket's own file size limit (Supabase → Storage → bucket settings) must
be at least 50 MB.

## Going live

The migrations add two tables to the **shared** database and copy the 10 videos into it.
Applying them is a separate step, done only with the user's go-ahead and after a backup, as
with the employee ID change.

## Files

New: `backend/apps/tutorials/` (app, models, `youtube.py`, migrations including the seed,
serializers, views, urls), `backend/tests/test_tutorial_videos.py`,
`frontend/src/api/tutorialsApi.js`, `frontend/src/utils/youtube.js` (and its test),
`frontend/src/components/Tutorials/` (`TutorialVideos.jsx`, `AddVideosForm.jsx`,
`VideoEntryRow.jsx`, `CategoryPicker.jsx`, `VideoPlayer.jsx`, their CSS and tests).

Changed: `backend/config/settings/base.py` (install the app), `backend/config/urls.py`
(`api/tutorials/`), `frontend/src/pages/WhatToDo.jsx` (the videos section replaced by
`TutorialVideos`), `frontend/src/pages/css/WhatToDo.css` (video styles move with it),
`frontend/src/pages/Dashboard/admin/adminShared.jsx` (audit labels),
`frontend/src/data/safetyGuides.js` (`VIDEOS` removed).

Not changed: the DRRMO and admin dashboards.

## Revision 2 (agreed 2026-11-11): category header, descriptions, deleting categories

Asked for after the first version went live. Where this section and the sections above
disagree, this section wins.

### Decisions

1. **The header is the chosen category.** The big "Tutorial videos" title and its line are
   replaced by the chosen category's name and description. A small "Tutorial videos" label stays
   above it, so "First Aid" isn't confused with the guides' First aid tab higher up the page.
2. **No "All" view.** The section always shows one category. It opens on the first category
   A–Z. **‹** and **›** arrows beside the name go to the previous and next category, wrapping
   around at the ends. Hovering (or focusing) an arrow shows "Previous: <name>" or
   "Next: <name>". With one category the arrows are hidden. The chips stay, as quick links to
   each category. If the chosen category disappears, the first one is shown.
3. **Which categories show.** Residents see only categories that have videos. Staff also see
   empty ones (so they can fill or delete them), with "No videos in this category yet."
4. **Categories get an optional description**, up to 300 characters, shown under the name in
   the header. One new column, `vdct_description` (blank by default; migration
   `tutorials/0003`). The picker's **+ New category** and **Edit category** (was Rename) take a
   name and a description.
5. **A category can be deleted at any time, with its videos.** Staff get **Delete category**
   next to the header and in the form's category picker. It first shows, word for word:
   "Are you sure you want to delete '<Category Name>'? This action is permanent and will
   automatically delete all videos contained within this category." The server deletes the
   category's videos, their uploaded files, then the category. The 409 for a category with
   videos is gone.
6. **In-app confirmations.** Deleting a video or a category asks in an in-app dialog (the admin
   dashboard's `ConfirmDialog`), not the browser's confirm box. The video wording is unchanged:
   "Delete '<title>'? Residents will stop seeing it." plus " The uploaded file is deleted too."
   for an MP4. Edit and Delete for a video stay under the chosen playlist card only.

### Data and API

- `VideoCategory.description`: text up to 300, blank allowed, trimmed. Sent with the category:
  `GET /api/tutorials/categories/` gives `[{id, name, description, video_count}]`.
- `POST /api/tutorials/categories/` and `PATCH .../<id>/` take `name` and `description`.
- `DELETE /api/tutorials/categories/<id>/` deletes the category's videos and the category in one
  database transaction; the uploaded files are deleted once it commits, so a failed delete never
  loses a file whose row survived. Answers 204. Audit: `DELETE_VIDEO_CATEGORY` with
  `"<name>" and <n> videos`.
- `RENAME_VIDEO_CATEGORY` stays the action name for edits, with `"<old>" → "<new>"` when the name
  changed, else `"<name>" (description)`.

### Tests

- Backend: the description is saved, trimmed, limited to 300 and listed; deleting a category with
  an uploaded video deletes the videos, their files and the category, and is logged with the
  count.
- Frontend:
  - the header shows the category's name and description;
  - the arrows move and wrap, and their tooltips name the neighbour;
  - one category hides the arrows;
  - residents never see empty categories, and staff do, with the empty message;
  - both dialogs confirm and cancel;
  - Delete category is offered for a category with videos and shows the warning word for word;
  - the picker sends the description.
