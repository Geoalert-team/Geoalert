# Purok History Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The public map colours each purok by how many past hazards it had, active hazards become pins only, tapping a barangay shows its whole history and picking a purok narrows it to that purok, and the History page gets the same Purok filter.

**Architecture:**
- **Backend:** the counting stays in `apps/history/purok_levels.py`. A new `apps/history/area.py` builds a barangay's or a purok's history. Two thin public views serve them, the history list learns the barangay rule and a `purok` filter, and resolving a flood or landslide links its record to the puroks it overlaps.
- **Frontend:** pure helpers in `components/Map/purokLevels.js` (levels, styles, copy) and a shared hover hook `usePurokHover`. `PurokHistoryLayer` draws the fills, and `AreaHistory` is the panel section. `PublicMap.jsx` loses the live shading, the outlines, the cordon layer and the heat, and wires the new pieces in.

**Tech Stack:** Django 4.2 + GeoDjango (PostGIS) + DRF, React 18 + react-leaflet 4, Jest (react-scripts).

**Spec:** `docs/superpowers/specs/2026-10-26-purok-history-map-design.md`, which builds on
`2026-10-25-history-based-hazard-levels-design.md` §1 and §6 and
`2026-10-25-report-driven-fire-hazards-design.md` §6.

## Global Constraints

- **No commits** (the user's standing instruction, repeated 2026-10-26). Each commit step means: leave the change in the working tree.
- **The shared database:** this plan has no migrations. Nothing writes to it. Tests run on Django's throwaway test database (`manage.py test`), as in the earlier plans.
- **One rule:** the period and thresholds come only from `apps.history.purok_levels.thresholds()` on the backend and the `thresholds` the API returns on the frontend. Never write 5 / 3 / 5 outside tests.
- **Level codes:** `Green` / `Orange` / `Red`. Labels are `Low` / `Moderate` / `Extreme` (`LABEL` in `purok_levels.py`). Colours are `SEVERITY[code].color` from `components/Map/hazardInfo.js`, the same as the pins.
- **Each hazard type is counted on its own.** A purok's level over several types is the highest of the per-type levels, never a level from the summed count.
- **A barangay's history** = records with `barangay` = it, plus records with a purok in it, each counted once.
- **Type nouns:** Flood → flood / floods, Landslide → landslide / landslides, Fire → fire / fires. Several types → past hazard / past hazards.
- **Copy (exact):**
  - Views: `Past hazards`, `Likely by month`
  - Legend: `Past hazards: {layerName}`, `{thresholdText}`, `Pins: active hazards, coloured by alert level`
  - `thresholdText` for 3 / 5 over 5 years: `1–2 · 3–4 · 5+ past events in the last 5 years`
  - Panel summary: `21 fires in the last 5 years`, `No fires in the last 5 years`
  - Panel rows and buttons: `Purok not recorded`, `‹ San Roque`, `Show more`, `Try again`
  - Hover line: `2 fires (Low)`; several types joined with `, `; none: `No past hazards in the last 5 years`
  - No types ticked: `Tick a hazard type in Layers to see its history.`
  - Errors: `Past-hazard colours couldn't load.`, `Past records couldn't be loaded. Try again.`
  - Backend 400s: `barangay must be an id.`, `purok must be an id or "none".`, `purok needs a barangay.`, `That purok is not in Barangay {name}.`
  - History page: `Purok`, `All puroks (21)`, `Purok Sambag (2)`, `Purok not recorded (16)`
  - Tiles-down pill: `Map tiles temporarily unavailable. Hazard pins and barangay lines are still shown.`

## Review Focus

1. **One record linked to two puroks of the same barangay.** It must count once in the barangay's total and once in each purok. Pinned in Task 2 (`test_a_record_in_two_puroks_counts_once_for_the_barangay`).
2. **A record filed under barangay A but linked to a purok in barangay B** (a BFP link across a border). It must appear once in each barangay's history and never twice in either. Pinned in Task 2 (`test_a_record_linked_across_a_border_shows_in_both_barangays`) and Task 3 (`test_barangay_rule_counts_each_record_once`).
3. **Every hazard type unticked in Layers.** No fills, and the panel says `Tick a hazard type in Layers to see its history.` instead of fetching all types. Pinned in Task 5 (`asks for a ticked type when none is`).
4. **Switching barangay while a purok is open.** The panel must return to the new barangay's whole history, not ask for the old purok under the new barangay. Pinned in Task 5 (`a new barangay starts on its whole history`).
5. **A purok parameter that isn't a number** (`?purok=abc`). The answer must be a 400 with the message, never a 500. Pinned in Task 2 (`test_bad_purok_is_a_400`) and Task 3 (`test_purok_filter_needs_a_barangay_and_an_id`).

---

### Task 1: Purok counts and `GET /api/history/purok-levels/`

**Files:**
- Modify: `backend/apps/history/purok_levels.py`
- Modify: `backend/apps/history/views.py` (add `PurokLevelsView`)
- Modify: `backend/apps/history/urls.py`
- Test: `backend/tests/test_area_history.py` (new; Tasks 2 and 3 add to it)

**Interfaces:**
- Produces: `purok_counts(since, types=None) -> dict[tuple[int, str], int]`, which maps (purok id, type name) to a count. It covers records with `occurred_at >= since` (all time when `since` is None), skips records with no hazard type, and counts each (record, purok) pair once.
- Produces: `GET /api/history/purok-levels/?types=Flood,Fire` → `{"thresholds": {...}, "results": [{"purok": int, "type": str, "count": int, "level": code}]}`, route name `history-purok-levels`.

- [ ] **Step 1: Write the failing tests**

```python
"""
Past hazards per purok and per area, for the map's purok colours, its
barangay panel and the History page's Purok filter. Real database: the
counting goes through historical_record_purok.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.history.models import HistoricalRecord
from apps.history.purok_levels import purok_counts
from apps.history.views import PurokLevelsView
from tests.fire_setup import FireSetupMixin


def get(view, **params):
    return view.as_view()(APIRequestFactory().get('/', params))


class PurokCountTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.history(self.near, 3)
        self.history(self.far, 1)
        flood = HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.flood, severity_level='Green',
                                                occurred_at=timezone.now() - timedelta(days=10))
        flood.puroks.add(self.near)
        untyped = HistoricalRecord.objects.create(barangay=self.home, hazard_type=None, severity_level='Green',
                                                  occurred_at=timezone.now())
        untyped.puroks.add(self.near)
        old = HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.fire, severity_level='Green',
                                              occurred_at=timezone.now() - timedelta(days=365 * 6))
        old.puroks.add(self.near)

    def test_counts_per_purok_and_type_in_the_period(self):
        since = timezone.now() - timedelta(days=365 * 5)
        self.assertEqual(purok_counts(since), {(self.near.id, 'Fire'): 3, (self.near.id, 'Flood'): 1,
                                               (self.far.id, 'Fire'): 1})
        self.assertEqual(purok_counts(since, ['Flood']), {(self.near.id, 'Flood'): 1})
        self.assertEqual(purok_counts(None)[(self.near.id, 'Fire')], 4)

    def test_the_endpoint_gives_levels_and_leaves_out_zeros(self):
        data = get(PurokLevelsView, types='Fire').data
        self.assertEqual(data['thresholds'], {'years': 5, 'moderate': 3, 'extreme': 5})
        self.assertCountEqual(data['results'], [
            {'purok': self.near.id, 'type': 'Fire', 'count': 3, 'level': 'Orange'},
            {'purok': self.far.id, 'type': 'Fire', 'count': 1, 'level': 'Green'},
        ])
        self.assertEqual(get(PurokLevelsView, types='Volcano').data['results'], [])
        self.assertEqual(len(get(PurokLevelsView).data['results']), 3)
```

- [ ] **Step 2: Run them to see them fail**

Run (from `backend/`): `venv/Scripts/python.exe manage.py test tests.test_area_history`
Expected: ImportError for `purok_counts` / `PurokLevelsView`.

- [ ] **Step 3: Implement `purok_counts(since, types=None)` in `purok_levels.py`**

Query `HistoricalRecord` filtered by `puroks__isnull=False` and `hazard_type__isnull=False`, plus `occurred_at__gte=since` when given and `hazard_type__name__in=types` when given. Take `values_list('puroks', 'hazard_type__name')` with `annotate(n=Count('id', distinct=True))`. Import the model inside the function, as `purok_levels()` does.

- [ ] **Step 4: Add `PurokLevelsView` (public) to `views.py` and the route `purok-levels/` to `urls.py`**

`types` is split on commas and blanks are dropped; an empty list means every type. `since = timezone.now() - timedelta(days=365 * t['years'])`. Each row's level is `level_for(count, t)`.

- [ ] **Step 5: Run the tests to see them pass**

Run: the command from Step 2. Expected: OK.

- [ ] **Step 6: Leave uncommitted**

---

### Task 2: A barangay's or purok's history and `GET /api/history/area/`

**Files:**
- Create: `backend/apps/history/area.py`
- Modify: `backend/apps/history/views.py` (add `AreaHistoryView`)
- Modify: `backend/apps/history/urls.py`
- Test: `backend/tests/test_area_history.py`

**Interfaces:**
- Consumes: `purok_counts`, `thresholds`, `level_for`, `highest`, `LABEL` (Task 1 and the existing module).
- Produces: `barangay_records(barangay) -> QuerySet[HistoricalRecord]`, holding the ids of records with `barangay=barangay` or a purok in it. Used through `id__in` so callers never see join duplicates.
- Produces: `area_history(barangay, purok, types, since, staff) -> dict`. `purok` is a `Purok`, the string `'none'`, or `None`. `types` is a list of names (empty = all). `since` is a datetime or None (all time). The result follows the spec's shape:

  `{count, level, thresholds, purok, puroks, unplaced, events}`

  - `purok` is `{id, name, parent}`, or `{'id': 'none', 'name': 'Purok not recorded', 'parent': ''}`, or `None`.
  - `puroks` and `unplaced` are filled in only for a barangay view; otherwise they are `[]` and `0`.
  - `events` are newest first: `{id, date, type, property_category, property_subcategory, alarm_level, structures_affected, puroks: [names]}`, plus `location_text` and `damage_cost` (as a string or null) when `staff`.
- Produces: `GET /api/history/area/?barangay=<id>[&purok=<id>|none][&types=Fire][&period=all]`, route name `history-area`.

- [ ] **Step 1: Write the failing tests** (append to `test_area_history.py`; the new imports go at the top of the file)

```python
from apps.barangays.models import Purok
from apps.history.views import AreaHistoryView
from django.contrib.gis.geos import MultiPolygon
from rest_framework.test import force_authenticate
from tests.fire_setup import box


class RecordMixin(FireSetupMixin):
    def record(self, barangay, *puroks, hazard=None, **kw):
        r = HistoricalRecord.objects.create(barangay=barangay, hazard_type=hazard or self.fire, severity_level='Green',
                                            occurred_at=timezone.now() - timedelta(days=20), **kw)
        r.puroks.set(puroks)
        return r


class AreaHistoryTests(RecordMixin, TestCase):
    def area(self, user=None, **params):
        request = APIRequestFactory().get('/', params)
        if user:
            force_authenticate(request, user=user)
        return AreaHistoryView.as_view()(request)

    def test_barangay_view_lists_puroks_unplaced_and_events(self):
        self.history(self.near, 3)
        self.record(self.home)                                   # no purok
        self.record(self.home, self.near, hazard=self.flood)     # another type
        data = self.area(barangay=self.home.id, types='Fire').data
        self.assertEqual((data['count'], data['unplaced'], data['level'], data['purok']), (4, 1, 'Orange', None))
        self.assertEqual(data['puroks'], [{'id': self.near.id, 'name': 'Purok Near', 'parent': '',
                                           'count': 3, 'level': 'Orange'}])
        self.assertEqual(len(data['events']), 4)
        self.assertNotIn('location_text', data['events'][0])

    def test_types_are_counted_on_their_own(self):
        self.history(self.near, 2)
        self.record(self.home, self.near, hazard=self.flood)
        self.record(self.home, self.near, hazard=self.flood)
        data = self.area(barangay=self.home.id, types='Fire,Flood').data
        self.assertEqual((data['count'], data['puroks'][0]['level']), (4, 'Green'))

    def test_purok_view_and_none_view(self):
        self.history(self.near, 2)
        self.record(self.home)
        purok = self.area(barangay=self.home.id, purok=self.near.id).data
        self.assertEqual((purok['count'], purok['level'], purok['puroks'], purok['unplaced']), (2, 'Green', [], 0))
        self.assertEqual(purok['purok'], {'id': self.near.id, 'name': 'Purok Near', 'parent': ''})
        none = self.area(barangay=self.home.id, purok='none').data
        self.assertEqual((none['count'], none['level'], none['purok']['name']), (1, None, 'Purok not recorded'))

    def test_a_record_in_two_puroks_counts_once_for_the_barangay(self):
        other = Purok.objects.create(barangay=self.home, name='Purok Other', kind='purok', source='estimated',
                                     boundary=MultiPolygon(box(200, 200, 300, 300), srid=4326))
        self.record(self.home, self.near, other)
        data = self.area(barangay=self.home.id).data
        self.assertEqual(data['count'], 1)
        self.assertEqual(sorted(p['count'] for p in data['puroks']), [1, 1])

    def test_a_record_linked_across_a_border_shows_in_both_barangays(self):
        self.record(self.home, self.far)
        self.assertEqual(self.area(barangay=self.home.id).data['count'], 1)
        self.assertEqual(self.area(barangay=self.next.id).data['count'], 1)
        self.assertEqual(self.area(barangay=self.next.id).data['puroks'][0]['count'], 1)

    def test_period_all_reaches_past_the_period(self):
        self.record(self.home, self.near, occurred_at=timezone.now() - timedelta(days=365 * 7))
        self.assertEqual(self.area(barangay=self.home.id).data['count'], 0)
        self.assertEqual(self.area(barangay=self.home.id, period='all').data['count'], 1)

    def test_staff_see_where_and_damage(self):
        self.record(self.home, self.near, location_text='SAMBAG, BRGY HOME', damage_cost='1500.00')
        event = self.area(self.officer, barangay=self.home.id).data['events'][0]
        self.assertEqual((event['location_text'], event['damage_cost']), ('SAMBAG, BRGY HOME', '1500.00'))

    def test_bad_purok_is_a_400(self):
        self.assertEqual(self.area(barangay=self.home.id, purok='abc').data,
                         {'error': 'purok must be an id or "none".'})
        response = self.area(barangay=self.home.id, purok=self.far.id)
        self.assertEqual((response.status_code, response.data['error']), (400, 'That purok is not in Barangay Home.'))
        self.assertEqual(self.area(barangay='x').status_code, 400)
        self.assertEqual(self.area(barangay=99999).status_code, 404)
```

- [ ] **Step 2: Run them to see them fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_area_history`. Expected: ImportError for `AreaHistoryView`.

- [ ] **Step 3: Implement `barangay_records` and `area_history` in `apps/history/area.py`**

The approach:
- **The record set:** a barangay view uses `HistoricalRecord.objects.filter(id__in=barangay_records(b))`, a purok view filters `puroks=purok`, and `'none'` filters `barangay=b, puroks__isnull=True`. Then apply `since` and `types` to that set.
- **`puroks` rows:** call `purok_counts(since, types)`, restrict it to the barangay's purok ids, and sum each purok's counts across its types. The row's level is `highest(level_for(c, t) for each type)`, and the list is sorted by count descending, then name.
- **`level`:** in a purok view, the highest per-type level of that purok; in a barangay view, `highest` over its rows, or `None` when there are no rows; for `'none'`, always `None`.
- **Events:** prefetch `puroks` and `select_related('hazard_type')`, ordered `-occurred_at`, `id`.

- [ ] **Step 4: Add `AreaHistoryView` (public) and the route `area/`**

Parse the parameters using the Global Constraints copy:
- `barangay`: not a number → 400; not found → 404 `{'error': 'Barangay not found'}`.
- `purok`: `'none'`, a number, or a 400. A purok id outside this barangay (or unknown) gets the 400 that names the barangay.
- `period=all` → `since=None`.
- `staff = IsDRRMOOfficer().has_permission(request, self)` (`utils.permissions`).

- [ ] **Step 5: Run the tests to see them pass**

Run: the command from Step 2. Expected: OK.

- [ ] **Step 6: Leave uncommitted**

---

### Task 3: The history list's barangay rule and `purok` filter

**Files:**
- Modify: `backend/apps/history/views.py` (`HistoricalRecordListView.get`)
- Test: `backend/tests/test_area_history.py`

**Interfaces:**
- Consumes: `barangay_records` (Task 2).
- Produces: `GET /api/history/?barangay=<id>` now includes records linked to a purok in it. New `&purok=<id>` and `&purok=none` (both need `barangay`).

- [ ] **Step 1: Write the failing tests**

```python
from apps.history.views import HistoricalRecordListView


class HistoryListPurokTests(RecordMixin, TestCase):
    def listed(self, **params):
        return get(HistoricalRecordListView, **params)

    def test_barangay_rule_counts_each_record_once(self):
        other = Purok.objects.create(barangay=self.home, name='Purok Other', kind='purok', source='estimated',
                                     boundary=MultiPolygon(box(200, 200, 300, 300), srid=4326))
        self.record(self.home, self.near, other)
        self.record(self.next, self.near)        # filed next door, linked to a Home purok
        self.assertEqual(len(self.listed(barangay=self.home.id).data), 2)
        page = self.listed(barangay=self.home.id, limit=5).data
        self.assertEqual((page['count'], page['type_counts']), (2, [{'name': 'Fire', 'count': 2}]))

    def test_purok_filter(self):
        self.history(self.near, 2)
        self.record(self.home)
        self.assertEqual(len(self.listed(barangay=self.home.id, purok=self.near.id).data), 2)
        self.assertEqual(len(self.listed(barangay=self.home.id, purok='none').data), 1)

    def test_purok_filter_needs_a_barangay_and_an_id(self):
        self.assertEqual(self.listed(purok='none').data, {'error': 'purok needs a barangay.'})
        self.assertEqual(self.listed(barangay=self.home.id, purok='abc').status_code, 400)
```

- [ ] **Step 2: Run them to see them fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_area_history`. Expected: the three new tests fail. The count is 1 where 2 is expected, and the `purok` parameter is ignored.

- [ ] **Step 3: Implement in `HistoricalRecordListView.get`**

Use `records.filter(id__in=barangay_records(barangay))`. `purok=<id>` → `filter(puroks__id=id)`; `purok=none` → `filter(barangay_id=b, puroks__isnull=True)`. The 400s use the Global Constraints copy. Update the docstring's filter list.

- [ ] **Step 4: Run the whole backend suite**

Run: `venv/Scripts/python.exe manage.py test tests`. Expected: OK (this includes `test_history_detail` and `test_analytics`).

- [ ] **Step 5: Leave uncommitted**

---

### Task 4: Resolving a flood or landslide links its puroks

**Files:**
- Modify: `backend/apps/hazards/views.py` (`HazardZoneDetailView.patch`, where it creates the `HistoricalRecord`, ~line 551)
- Test: `backend/tests/test_resolve_links_puroks.py` (new)

**Interfaces:**
- Produces: `overlapping_puroks(geometry) -> QuerySet[Purok]` in `apps/hazards/geometry.py`: `Purok.objects.filter(boundary__intersects=g).exclude(boundary__touches=g)`.

- [ ] **Step 1: Write the failing test**

```python
"""
Resolving a flood or landslide files its history record under every purok
its area overlaps, so it colours those puroks. Sharing only a border doesn't count.
"""
from django.contrib.gis.geos import MultiPolygon
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.hazards.views import HazardZoneDetailView
from apps.history.models import HistoricalRecord
from tests.fire_setup import FireSetupMixin, box


class ResolveLinksPuroksTests(FireSetupMixin, TestCase):
    def resolve(self, zone):
        request = APIRequestFactory().patch('/', {'status': 'Resolved'}, format='json')
        force_authenticate(request, user=self.officer)
        return HazardZoneDetailView.as_view()(request, pk=zone.pk)

    def test_a_flood_counts_in_the_puroks_it_overlaps_not_one_it_touches(self):
        inside = self.zone(self.near, hazard_type=self.flood,
                           geometry=MultiPolygon(box(-50, -50, 50, 50), srid=4326))
        touching = self.zone(self.near, hazard_type=self.flood,
                             geometry=MultiPolygon(box(100, -50, 200, 50), srid=4326))
        self.assertEqual(self.resolve(inside).status_code, 200)
        self.assertEqual(self.resolve(touching).status_code, 200)
        self.assertEqual(list(HistoricalRecord.objects.get(hazard_zone=inside).puroks.all()), [self.near])
        self.assertEqual(list(HistoricalRecord.objects.get(hazard_zone=touching).puroks.all()), [])
```

- [ ] **Step 2: Run it to see it fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_resolve_links_puroks`. Expected: FAIL; the first record's purok list is `[]`.

- [ ] **Step 3: Implement**

Add `overlapping_puroks` to `apps/hazards/geometry.py`. In the resolve branch, keep the created record as `record`, then `if zone.geometry: record.puroks.set(overlapping_puroks(zone.geometry))`.

- [ ] **Step 4: Run it and the fire-close tests**

Run: `venv/Scripts/python.exe manage.py test tests.test_resolve_links_puroks tests.test_fire_close_views`. Expected: OK.

- [ ] **Step 5: Leave uncommitted**

---

### Task 5: Frontend helpers, API calls and the panel's history section

**Files:**
- Create: `frontend/src/components/Map/purokLevels.js`
- Create: `frontend/src/components/Map/AreaHistory.jsx`
- Modify: `frontend/src/api/historyApi.js` (add `purokLevels`, `area`; `heat` is removed in Task 7)
- Modify: `frontend/src/components/Map/BarangayPanel.jsx`
- Modify: `frontend/src/pages/css/PublicMap.css` (classes for the new section, under the existing `pm-history-*` rules)
- Test: `frontend/src/components/Map/purokLevels.test.js`, `frontend/src/components/Map/AreaHistory.test.js`

**Interfaces:**
- Produces in `historyApi`: `purokLevels(types?) -> Promise<{thresholds, results}>` (GET `/api/history/purok-levels/`, `types` joined by commas when given), and `area(params) -> Promise<AreaHistory>` (GET `/api/history/area/`).
- Produces in `purokLevels.js`:
  - `PUROK_LEVELS`: `[{code: 'Red', label: 'Extreme'}, {code: 'Orange', label: 'Moderate'}, {code: 'Green', label: 'Low'}]`, each with `color` from `SEVERITY`
  - `byPurok(results) -> Map<string, {[type]: {count, level}}>`
  - `purokLevel(entry, types) -> code | null`: the highest per-type level among `types`
  - `filledPuroks(geo, levels, types) -> FeatureCollection | null`: features with a level, each with `properties.level`
  - `purokFillStyle(feature) -> Leaflet path options`: `{ stroke: true, color, weight: 1, opacity: 0.9, fillColor: color, fillOpacity: 0.45 }`
  - `typeNoun(types, n) -> string`
  - `historyLine(entry, types, years) -> string`
  - `thresholdText(t) -> string`
  - `areaTitle(count, types, years) -> string`
- Produces: `AreaHistory({ barangay, purokId, types, onPickPurok })`, where `purokId` is an id, `'none'` or `null`, and `onPickPurok` takes the same.
- Produces: `BarangayPanel` gains `purokId = null`, `onPickPurok = () => {}` and `historyTypes = []`. It renders `<AreaHistory>` under the active hazards.

- [ ] **Step 1: Write the failing helper tests** (`purokLevels.test.js`)

```js
import { byPurok, filledPuroks, historyLine, purokLevel, thresholdText, typeNoun, areaTitle } from './purokLevels';

const T = { years: 5, moderate: 3, extreme: 5 };
const RESULTS = [
  { purok: 7, type: 'Fire', count: 2, level: 'Green' },
  { purok: 7, type: 'Flood', count: 4, level: 'Orange' },
  { purok: 9, type: 'Fire', count: 6, level: 'Red' },
];
const feature = (id) => ({ type: 'Feature', id, properties: { id, name: `P${id}` }, geometry: null });

test('a purok takes the highest level among the ticked types', () => {
  const levels = byPurok(RESULTS);
  expect(purokLevel(levels.get('7'), ['Fire', 'Flood'])).toBe('Orange');
  expect(purokLevel(levels.get('7'), ['Fire'])).toBe('Green');
  expect(purokLevel(levels.get('7'), ['Landslide'])).toBeNull();
  expect(purokLevel(undefined, ['Fire'])).toBeNull();
});

test('only puroks with a level are filled', () => {
  const geo = { type: 'FeatureCollection', features: [feature(7), feature(8), feature(9)] };
  const filled = filledPuroks(geo, byPurok(RESULTS), ['Fire']);
  expect(filled.features.map((f) => [f.id, f.properties.level])).toEqual([[7, 'Green'], [9, 'Red']]);
  expect(filledPuroks(geo, byPurok(RESULTS), [])).toBeNull();
});

test('the hover line and the copy', () => {
  const levels = byPurok(RESULTS);
  expect(historyLine(levels.get('7'), ['Fire', 'Flood'], 5)).toBe('2 fires (Low), 4 floods (Moderate)');
  expect(historyLine(levels.get('7'), ['Landslide'], 5)).toBe('No past hazards in the last 5 years');
  expect(thresholdText(T)).toBe('1–2 · 3–4 · 5+ past events in the last 5 years');
  expect(thresholdText({ years: 3, moderate: 2, extreme: 3 })).toBe('1 · 2 · 3+ past events in the last 3 years');
  expect(typeNoun(['Fire'], 1)).toBe('fire');
  expect(typeNoun(['Fire', 'Flood'], 2)).toBe('past hazards');
  expect(areaTitle(21, ['Fire'], 5)).toBe('21 fires in the last 5 years');
  expect(areaTitle(0, ['Fire'], 5)).toBe('No fires in the last 5 years');
});
```

- [ ] **Step 2: Write the failing panel tests** (`AreaHistory.test.js`, rendered with `createRoot` and `act` as in `components/History/RecordDetail.test.js`, with `historyApi.area` mocked)

```js
const BARANGAY = { id: 19, name: 'San Roque' };
const AREA = {
  count: 21, level: 'Green', thresholds: { years: 5, moderate: 3, extreme: 5 }, purok: null, unplaced: 16,
  puroks: [{ id: 7, name: 'Purok Sambag', parent: 'Sitio Laray', count: 2, level: 'Green' }],
  events: Array.from({ length: 7 }, (_, i) => ({ id: `e${i}`, date: '2026-03-0' + (i + 1), type: 'Fire',
    alarm_level: '1ST ALARM', property_category: 'RESIDENTIAL', property_subcategory: '', structures_affected: 1,
    puroks: ['Purok Sambag'] })),
};

test('the barangay view lists its puroks, the unplaced and five events', async () => { /* render with purokId null:
  text includes '21 fires in the last 5 years', 'Purok Sambag', 'Purok not recorded', '16'; 5 event items;
  clicking 'Show more' shows 7; historyApi.area called with { barangay: 19, types: 'Fire' } */ });
test('picking a row calls onPickPurok with its id, and the unplaced row with "none"', async () => { /* 7, then 'none' */ });
test('the purok view has a way back', async () => { /* purokId 7, answer with purok {id:7,name:'Purok Sambag'}:
  button '‹ San Roque' calls onPickPurok(null); area called with { barangay: 19, purok: 7, types: 'Fire' } */ });
test('a new barangay starts on its whole history', async () => { /* rerender with barangay {id: 5} and purokId null
  after purokId 7: last area call is { barangay: 5, types: 'Fire' } */ });
test('asks for a ticked type when none is', async () => { /* types []: text 'Tick a hazard type in Layers to see
  its history.'; area not called */ });
test('a failed load says so and retries', async () => { /* area rejects: text 'Past records couldn't be loaded.
  Try again.'; clicking 'Try again' calls area again */ });
```

Each comment lists the assertions the test makes; write them out the way `RecordDetail.test.js` does.

- [ ] **Step 3: Run them to see them fail**

Run (from `frontend/`): `CI=true npx react-scripts test --watchAll=false src/components/Map/purokLevels.test.js src/components/Map/AreaHistory.test.js`
Expected: "Cannot find module './purokLevels'" / "'./AreaHistory'".

- [ ] **Step 4: Implement `purokLevels.js`, the two `historyApi` calls and `AreaHistory.jsx`**

How `AreaHistory` behaves:
- It refetches when `barangay.id`, `purokId` or `types.join(',')` changes, and ignores stale answers (the `live` flag pattern in `BarangayPanel`).
- It sends `purok` only when `purokId` isn't null.
- Events show five at a time, held in local state that resets on every new answer.
- Each event shows the date (`en-PH`, as `HazardPanel`'s `formatDate` does), the type, and `alarm_level · property_subcategory || property_category`. In a barangay view, the event's purok names follow.
- Purok rows are buttons with a swatch in `SEVERITY[level].color`.

- [ ] **Step 5: Wire `AreaHistory` into `BarangayPanel`**

It goes after the active-hazards `pm-tabpanel`, as its own `pm-tabpanel` with the `<h3>Past hazards</h3>` heading. Document the three new props in the component comment.

- [ ] **Step 6: Run the tests to see them pass, then the whole frontend suite**

Run: the command from Step 3, then `CI=true npx react-scripts test --watchAll=false`. Expected: all pass.

- [ ] **Step 7: Leave uncommitted**

---

### Task 6: The purok fill layer and the shared hover

**Files:**
- Create: `frontend/src/components/Map/usePurokHover.js`
- Create: `frontend/src/components/Map/PurokHistoryLayer.jsx`
- Modify: `frontend/src/components/Map/PurokLayer.jsx`
- Modify: `frontend/src/components/Map/purokStyle.js` (add `PUROK_SELECTED`)
- Test: `frontend/src/components/Map/purokStyle.test.js`

**Interfaces:**
- Consumes: `filledPuroks`, `purokFillStyle` (Task 5); `purokAt`, `purokTooltip`, `PUROK_HOVER` (existing).
- Produces:
  - `usePurokHover(geo, tooltipFor) -> feature | null`: the body of `PurokLayer`'s current effect, moved as is, with `tooltipFor(feature)` in place of `purokTooltip`.
  - `PurokLayer({ geo, selectedId = null, tooltipFor = purokTooltip })`: outlines and hover as now, plus `selectedId`'s outline drawn with `{ ...purokStyle(f), ...PUROK_SELECTED }`.
  - `PUROK_SELECTED = { weight: 3.5, dashArray: null }`.
  - `PurokHistoryLayer({ geo, levels, types, tooltipFor, skipBarangay = null })`: the fills from `filledPuroks(geo, levels, types)` in their own pane `purok-fills` (zIndex 360, `pointerEvents: 'none'`, `interactive={false}`), keyed so they remount when the set or the levels change. It hovers over the filled puroks outside `skipBarangay`, so a selected barangay's puroks are hovered by `PurokLayer` only, with one tooltip.

- [ ] **Step 1: Write the failing test** (add to `purokStyle.test.js`)

```js
test('the selected purok is drawn bold and solid', () => {
  const s = { ...purokStyle(feature({ source: 'estimated' })), ...PUROK_SELECTED };
  expect(s.weight).toBeGreaterThan(PUROK_HOVER.weight);
  expect(s.dashArray).toBeNull();
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `CI=true npx react-scripts test --watchAll=false src/components/Map/purokStyle.test.js`. Expected: `PUROK_SELECTED` is undefined.

- [ ] **Step 3: Implement the hook, `PUROK_SELECTED`, the `PurokLayer` change and `PurokHistoryLayer`**

- [ ] **Step 4: Run the whole frontend suite and the build**

Run: `CI=true npx react-scripts test --watchAll=false`, then `npx react-scripts build`. Expected: tests pass; the build compiles (lint warnings that were already there are fine).

- [ ] **Step 5: Leave uncommitted**

---

### Task 7: The map: Past hazards, pins only, barangay → purok

**Files:**
- Modify: `frontend/src/pages/PublicMap.jsx`
- Modify: `frontend/src/components/Map/hazardLevels.js`
- Modify: `frontend/src/api/historyApi.js` (remove `heat`)
- Modify: `backend/apps/history/views.py`, `backend/apps/history/urls.py` (remove `HistoricalHeatView`, its route, and the imports only it used: `math`, and `timedelta` if Task 1 doesn't use it)

**Interfaces:**
- Consumes: `historyApi.purokLevels`, `byPurok`, `historyLine`, `thresholdText`, `PUROK_LEVELS` (Task 5); `PurokHistoryLayer`, `PurokLayer({ selectedId, tooltipFor })` (Task 6); `BarangayPanel({ purokId, onPickPurok, historyTypes })` (Task 5).
- Produces: `selection` for a barangay is `{ kind: 'barangay', id, spot, purokId }`, and `selectBarangay(barangay, spot = null, purokId = null)`.

- [ ] **Step 1: Replace the views**

`HEAT_MODES` becomes `VIEWS`:
- `{ key: 'past', label: 'Past hazards', note }`, where the note is built from `thresholdText(thresholds)` + `' Pins: active hazards, coloured by alert level.'`
- the existing `likely` entry

`heatMode` becomes `view`, defaulting to `'past'`.

- [ ] **Step 2: Load the purok levels**

- `const [purokLevels, setPurokLevels] = useState(null)` holds `{ thresholds, levels: byPurok(results) }`, or `{ error: true }`.
- `loadPurokLevels()` replaces `loadHeat` in the first-load effect and in `refreshMap`.
- On failure, the status area shows the pill `Past-hazard colours couldn't load.`.

- [ ] **Step 3: Remove the live shading, the outlines, the cordon layer and the heat**

**In `PublicMap.jsx`, delete:**
- `historySpots`, `loadHeat`, `NO_HISTORY`
- `showOutlines` / `toggleOutlines` / `zoneOutlines` / `zoneOutlinesKey`, and the zone-outline `<GeoJSON>`
- the `hazard-levels` `<Pane>` / `<ImageOverlay>`, `shadedHazards`, `levelUrl`
- `<CordonLayer hazards={visibleHazards} />`
- the cordon legend row (`hasCordon`)
- the `showOutlines` / `onToggleOutlines` props passed to `LayerControl`, which hides that toggle without them; `LayerControl` itself is unchanged
- the imports these leave unused (`ImageOverlay`, `HAZARD_LEVELS`, `useHazardLevelLayer`, `CordonLayer`, `hasCordon`, `drawsShading`)

**Keep:**
- `CordonPatterns`, `DRAFT_COLOR` and `cordonRingStyle`, for the draft preview
- `markerSpots`

**In `hazardLevels.js`,** keep only `loadClassGrid` and what it needs (`hexToRgb`, `loadImage`, `BASE`), and rewrite the file comment to say that's all it now holds. `SpotReading.jsx` and `utils/zoneCheck.js` still import it.

**In `historyApi.js`,** remove `heat`.

**On the backend,** remove `HistoricalHeatView`.

**Copy,** change the tiles-down pill to the Global Constraints text.

- [ ] **Step 4: Draw the fills and hand the hover text to both layers**

- In the `past` view, render `<PurokHistoryLayer geo={purokGeo} levels={purokLevels.levels} types={visibleTypeList} tooltipFor={purokTip} skipBarangay={selectedPuroks ? selectedBarangayId : null} />`.
- `purokTip(f)` = `purokTooltip(f)` + `<br>` + `historyLine(levels.get(String(f.id ?? f.properties.id)), visibleTypeList, thresholds.years)`. In the `likely` view, or before the levels load, it is plain `purokTooltip`.
- Pass `selectedId={selection?.purokId ?? null}` and `tooltipFor={purokTip}` to `PurokLayer`.

- [ ] **Step 5: The legend**

In the `past` view, show:
- the title `Past hazards: {layerName}`
- one swatch per `PUROK_LEVELS` entry (`label`, `color`)
- `thresholdText` as a note, and `Pins: active hazards, coloured by alert level`

The `likely` legend is unchanged. The rest of the legend (pin colours, symbols, overlap) stays.

- [ ] **Step 6: Tapping a purok**

In the barangay layer's click handler:
- If this barangay's panel is already open, find the purok under the tap with `purokAt(puroksOf(purokGeo, id), lng, lat)`. Pass its id as `purokId`. A tap on no purok passes `null` (back to the whole barangay).
- Otherwise call `selectBarangay(b, spot)`, which starts with `purokId: null`.

`pickPurok(id)` sets `selection.purokId`. Pass `purokId`, `onPickPurok={pickPurok}` and `historyTypes={visibleTypeList}` to `BarangayPanel`.

- [ ] **Step 7: Run the whole frontend suite, the build and the backend suite**

Run: `CI=true npx react-scripts test --watchAll=false`, `npx react-scripts build` (from `frontend/`), and `venv/Scripts/python.exe manage.py test tests` (from `backend/`).
Expected: all pass and the build compiles. `grep -rn "heat\|useHazardLevelLayer\|HAZARD_LEVELS" frontend/src backend/apps` finds nothing except unrelated words.

- [ ] **Step 8: Leave uncommitted**

---

### Task 8: The History page's Purok filter

**Files:**
- Modify: `frontend/src/pages/HistoricalData.jsx`
- Test: `frontend/src/pages/historyPurokFilter.test.js` (new)

**Interfaces:**
- Consumes: `historyApi.area` (Task 5), and the list's `purok` parameter (Task 3).

- [ ] **Step 1: Write the failing tests** (`createRoot` / `act`; mock `historyApi.list`, `historyApi.area`, `barangaysApi.list`, `hazardsApi.types`; wrap the page in `MemoryRouter`, and mock `PublicNavbar` to render nothing)

```js
test('the Purok dropdown appears once a barangay is picked, with counts', async () => { /* pick barangay 19:
  area called with { barangay: 19, period: 'all' }; options text equals
  ['All puroks (21)', 'Purok Sambag (2)', 'Purok not recorded (16)'] */ });
test('picking a purok filters the list, and a new barangay resets it', async () => { /* pick Purok Sambag: last
  list call params include { barangay: '19', purok: '7' }; pick barangay 5: purok select value '' and the
  last list call has no purok */ });
test('no dropdown when the counts fail to load', async () => { /* area rejects: no select labelled Purok */ });
```

- [ ] **Step 2: Run them to see them fail**

Run: `CI=true npx react-scripts test --watchAll=false src/pages/historyPurokFilter.test.js`. Expected: there is no Purok select.

- [ ] **Step 3: Implement**

- Add `purokId` state (`''` = All puroks; `'none'`; or an id) and `purokCounts` state (the `area` answer, or `null`).
- When `barangayId` changes, reset `purokId` and fetch `historyApi.area({ barangay: barangayId, period: 'all' })`.
- Render a `db-field` labelled `Purok` after the Barangay select, only when `barangayId && purokCounts`. The `Purok not recorded` option appears only when `unplaced > 0`.
- Add `purok` to the list params and to the effect's dependencies.

- [ ] **Step 4: Run the tests to see them pass, then the whole frontend suite**

Run: the Step 2 command, then `CI=true npx react-scripts test --watchAll=false`. Expected: all pass.

- [ ] **Step 5: Leave uncommitted**

---

### Task 9: Check it in the real app

**Files:** none changed. The checks below are recorded in the final report.

- [ ] **Step 1: Work out the expected numbers from the shared database (read only)**

Run (from `backend/`), as a script under the session scratchpad run through `manage.py shell -c "exec(open(r'<path>').read())"`:
- San Roque (id 19)'s count under the barangay rule
- its unplaced count
- `purok_counts(since)` for its puroks
- the number of puroks with any count in the period

The 2026-10-26 figures to compare against are: 21, 16, Purok Sambag 2, and 82 puroks.

- [ ] **Step 2: Call the running backend**

Run:
- `curl -s "http://localhost:8000/api/history/area/?barangay=19&types=Fire"`
- `curl -s "http://localhost:8000/api/history/purok-levels/?types=Fire"`
- `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/history/heat/`

Expected: the area and purok-level numbers equal Step 1's, and `heat/` answers 404.

- [ ] **Step 3: Look at the map and the History page**

Use a browser tool if the session has one; otherwise ask the user to look, with the checklist. Signed out, at http://localhost:3000:
1. The map opens on **Past hazards**: puroks are filled in green, orange and red along their own lines, with no round spots and no zone shading.
2. Tapping San Roque opens the panel with `21 fires in the last 5 years`, Purok Sambag 2, and `Purok not recorded` 16.
3. Tapping inside Purok Sambag narrows the panel, and `‹ San Roque` goes back.
4. The History page with San Roque → Purok Sambag lists 2 records.

- [ ] **Step 4: Report**

List what was checked and how, any check that couldn't be done, and the files changed (`git status --short`). Nothing is committed.
