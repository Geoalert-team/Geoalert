# Tutorial Videos Revision 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The What To Do tutorial videos section shows one category at a time, with its name and description as the header and ‹ › arrows between categories. Categories get an optional description. A category can be deleted with its videos, after an in-app warning.

**Architecture:** Changes the existing `apps/tutorials` app (one new column, cascade delete in the view) and `components/Tutorials/` (header and arrows in `TutorialVideos.jsx`, description fields in `CategoryPicker.jsx`, the admin dashboard's `ConfirmDialog` for confirmations).

**Tech Stack:** as the first plan (`docs/superpowers/plans/2026-11-11-tutorial-videos.md`).

**Spec:** `docs/superpowers/specs/2026-11-11-tutorial-videos-design.md`, section "Revision 2".

## Global Constraints

The first plan's Global Constraints all apply: no commits; no `migrate` on the shared database without the user's go-ahead and a backup; backend tests via `.superpowers/sdd/2026-11-11-tutorial-videos/run-backend.sh`; frontend via `run-frontend.sh`; `CI=true npm run build` must be clean. Also:
- **Category warning, verbatim:** `Are you sure you want to delete '<Category Name>'? This action is permanent and will automatically delete all videos contained within this category.`
- **Description:** at most 300 characters, blank allowed, trimmed.

## Review Focus

1. **Deleting the category being shown**, or the last category: the section falls back to the first category left. For residents with nothing left, the section disappears.
2. **A category deleted while its files fail to delete from storage:** the rows are gone (one transaction) and file deletion is best-effort after commit; the delete never 500s on a missing file.
3. **Arrows with two categories:** Previous and Next both name the other one; with one category there are no arrows.
4. **An old client** still sending only `name` to create or rename a category keeps working, with the description defaulting to blank.
5. **The edit form open on a video whose category is deleted:** the form closes, since the video is gone.

---

### Task 1: Backend: description and cascade delete

**Files:** Modify `backend/apps/tutorials/models.py`, `serializers.py`, `views.py`; Create `backend/apps/tutorials/migrations/0003_category_description.py` (generated); Test `backend/tests/test_tutorial_videos.py`.

**Interfaces:**
- Produces:
  - `VideoCategory.description = CharField(max_length=300, blank=True, default='', db_column='vdct_description')`.
  - `VideoCategorySerializer` fields `['id', 'name', 'description', 'video_count']`, with `description = CharField(max_length=300, required=False, allow_blank=True)`.
  - Category `DELETE` → 204 always (404 if unknown).
  - Audit `DELETE_VIDEO_CATEGORY` details `"<name>" and <n> videos`. Edit details `"<old>" → "<new>"`, or `"<name>" (description)` when only the description changed.

- [ ] **Step 1:** Replace `test_only_an_empty_category_can_be_deleted` with `test_a_category_is_deleted_with_its_videos_and_files`. Upload an MP4 into Drills, delete Drills: 204; no Drills videos or category; the file is gone from storage; audit `"Drills" and 1 videos`. Add `test_a_description_is_saved_trimmed_and_listed`: `'  Bandaging and bleeding '` → `'Bandaging and bleeding'`; 301 characters → 400; the GET list includes `description`; a create without `description` gives `''`. Update `test_anyone_can_list_categories_a_to_z_with_counts` to expect `description` too.
- [ ] **Step 2:** Run backend `CategoryApiTests`. Expected: the new tests fail (409; no `description` field).
- [ ] **Step 3:** Implement the model field, run `makemigrations tutorials --name category_description`, then update the serializer and views. Delete uses `transaction.atomic()`: collect the file names, delete the videos and the category, then `transaction.on_commit` deletes each file, ignoring storage errors.
- [ ] **Step 4:** Run backend `tests.test_tutorial_videos`. Expected: OK. Then `makemigrations --check --dry-run`. Expected: `No changes detected`.

### Task 2: Picker: description and Delete with the warning

**Files:** Modify `frontend/src/api/tutorialsApi.js`, `frontend/src/components/Tutorials/CategoryPicker.jsx`, `CategoryPicker.test.js`, `css/TutorialVideos.css`.

**Interfaces:**
- `tutorialsApi.createCategory({ name, description })` and `tutorialsApi.updateCategory(id, { name, description })`. `renameCategory` is removed.
- `CategoryPicker`: **+ New category** and **Edit category** open the name input (`aria-label` `New category name` or `Category name`) and a description input (`aria-label="Category description"`, max 300), with `Create` or `Save`.
- **Delete** shows for any chosen category. It opens `ConfirmDialog` (from `pages/Dashboard/admin/adminShared`) titled `Delete category`, with the verbatim warning and confirm label `Delete`. On confirm it calls `removeCategory`, then `onChange(null)` and `onChanged()`.

- [ ] **Step 1:** Update the picker tests:
  - create sends `{ name: 'Typhoon Response', description: 'Before, during and after' }`;
  - Edit category is prefilled and sends both fields;
  - Delete is offered for First Aid (10 videos) and the dialog shows the warning verbatim;
  - Cancel doesn't delete; Delete in the dialog calls `removeCategory('c1')`.
- [ ] **Step 2:** Run frontend `CategoryPicker`. Expected: fail.
- [ ] **Step 3:** Implement. Import `../../pages/css/AdminDashboard.css` so the dialog is styled.
- [ ] **Step 4:** Run frontend `CategoryPicker AddVideosForm`. Expected: pass.

### Task 3: The category header, arrows and the video delete dialog

**Files:** Modify `frontend/src/components/Tutorials/TutorialVideos.jsx`, `TutorialVideos.test.js`, `css/TutorialVideos.css`.

**Interfaces:**
- Consumes: `tutorialsApi.list()` and `tutorialsApi.categories()`, loaded together; `ConfirmDialog`.
- Produces:
  - **Categories shown:** those from `categories()`. Residents get only `video_count > 0`; staff get all.
  - **Header:** a small label `Tutorial videos`, `<h2>` = category name, `<p class="tv-category-description">` when there is a description.
  - **Arrows:** `aria-label`s `Previous: <name>` and `Next: <name>`, with the same text as a hover/focus tooltip (`data-tip`). Hidden when only one category.
  - **Chips:** one per shown category (no All).
  - **Staff tools:** **Add videos** and **Delete category** (the picker's warning dialog) beside the chips.
  - **Video delete:** through `ConfirmDialog` titled `Delete video` with the existing wording.
  - **Empty category, staff:** `No videos in this category yet.`

- [ ] **Step 1:** Update the section tests:
  - **Header and arrows:** the header shows First Aid's name and description; ‹ › wrap from the last category to the first; tooltips name the neighbours; one category hides the arrows.
  - **Who sees what:** residents don't get an empty category; staff do, with the message.
  - **Deleting:** video delete goes through the dialog (Cancel keeps the video, Delete removes it). Delete category shows the warning and calls `removeCategory`, then the section reloads onto the first remaining category.
  - **Existing tests:** chip tests no longer expect All.
- [ ] **Step 2:** Run frontend `TutorialVideos`. Expected: fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run every frontend test and `CI=true npm run build`. Expected: all pass, `Compiled successfully.`

### Task 4: Whole check

- [ ] Backend `tests apps` on the test database: OK. Frontend: all pass. Build clean.
- [ ] Fresh reviewer on the change.
- [ ] Ask the user before backing up and running `migrate tutorials` (0003) on the shared database.
