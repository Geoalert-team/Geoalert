# Sitio Areas and Address Linking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A sitio becomes an outline around its puroks, and more history records link to an area: through the sitio of an unplaced purok, a landmark, a street, or the one barangay that has the named place. The research from 2026-10-28 goes into the purok data.

**Architecture:**
- **Data:** `backend/apps/barangays/data/puroks/` gets the new pins, variants and Barangay Hall list.
- **Build:** `purok_estimate.py` gains a name tree and a nested split (sitio territory, then its puroks, reusing `split_named`), crowded starting points are spread, and `place_areas()` maps landmarks and streets to areas. `build_purok_estimates` writes the containers and `place_areas.csv`.
- **Linker:** `bfp_link.py` gains splitting fixes, one merged name index (`load_link_index`) and `explain_link()`. The BFP and flood/landslide commands load the index.
- **API:** the puroks API and the zone-overlap lookup learn which puroks are containers (`members`).
- **Map:** sitio lines are thicker, sitio fills sit under purok fills, and the smallest area wins under the pointer.

**Tech Stack:** Django 4.2 + GeoDjango (PostGIS) + DRF, numpy/scipy (the estimate grid), React 18 + react-leaflet 4, Jest (react-scripts).

**Spec:** `docs/superpowers/specs/2026-10-28-sitio-areas-and-address-linking-design.md`

## Global Constraints

- **No commits** (the user's standing instruction, repeated 2026-10-28). Every "Leave uncommitted" step means the change stays in the working tree.
- **Nothing touches the shared database.**
  - Tests run on Django's throwaway test database (`manage.py test`).
  - `build_purok_estimates` only reads barangay outlines.
  - Never run `load_puroks`, `import_bfp_fires` without `--dry-run`, `import_bfp_fires --relink` without `--dry-run`, or `import_flood_landslide` without `--dry-run`.
- **Commands:**
  - Backend: from `backend/`, `venv/Scripts/python.exe manage.py test tests.<module>`.
  - Frontend: from `frontend/`, `CI=true npx react-scripts test --watchAll=false <path>`.
- **BFP spellings win** where sources differ. The confidence words are `high` / `medium` / `low`, as defined in `SOURCES.md`.
- **Container:** a purok whose exact `name` is the `parent` of another purok in the same barangay. `members` = how many puroks name it as `parent`.
- **Street share:** a street links to an area only when that area holds at least `STREET_SHARE = 0.75` of the street's length in the barangay.
- **Rule names** (import report and dry run): `purok`, `sitio`, `landmark`, `street`.
- **The teammate's flood/landslide code:** only the one `variants = …` line in `import_flood_landslide.py` changes. `flood_landslide.py` and its tests stay untouched and must pass.

## Review Focus

1. **An address naming a placed sitio and an unplaced purok of another sitio:** "Purok Macopa, Kimba" must link to Kimba, which is written, not to Macopa's sitio Laray. Direct matches on every part come before any fallback. *Test in Task 3.*
2. **A no-barangay address whose only name is in two barangays:** "Sitio Iba, Talisay City" stays unplaced. It is never guessed. *Test in Task 3.*
3. **A landmark word that matches two landmarks in one barangay:** "Elementary School" alone links to nothing. *Test in Task 4.*
4. **A medium purok far outside its sitio:**
   - The sitio's outline still takes it in, even as a MultiPolygon. *Test in Task 5.*
   - The pointer over the purok picks the purok, not the sitio. *Test in Task 8.*
5. **Names stay unique per barangay after the build:** the container uses the sitio's name, and nothing else (the leftover, an unnamed area) uses it. *Test in Task 5.*

---

### Task 1: Research data

**Files:**
- Modify: `backend/apps/barangays/data/puroks/purok_points.csv`, `name_variants.csv`, `needs_barangay_check.csv`, `SOURCES.md`
- Test: `backend/tests/test_research_data.py` (new)

**Interfaces:**
- Produces: CSV rows that later tasks read. The columns are unchanged.

- [ ] **Step 1: Write the failing test** `ResearchDataTests` (`SimpleTestCase`, reads the real files):
  - `test_every_parent_is_a_row_in_the_same_barangay`
  - `test_no_two_rows_share_a_name_in_a_barangay`: under `norm_name`
  - `test_placed_rows_have_a_confidence_and_how`: `lat`, `lng`, `placed_by` and `confidence` are all set or all blank
  - `test_variants_point_at_rows`: every `name_variants.csv` `name` is a `purok_points.csv` row of that barangay
  - `test_the_2026_10_28_research_is_in`:
    - `('Cadulawan','Purok Boongon')` is placed `medium`
    - `('Manipis','Camp 6')` is `high`
    - `('Camp IV','Purok Sambag')` has parent `Sitio Proper`
    - `('Bulacao','Upper Kabanayan')` has parent `Sitio Kabanayan`
    - `('Dumlog','Sitio Bahala')` is `low`
- [ ] **Step 2: Run it.** `manage.py test tests.test_research_data` fails on the last test only. If an earlier test fails on today's data, fix that data row in Step 3.
- [ ] **Step 3: Edit the CSVs** exactly as spec §1 lists:
  - **`purok_points.csv`:**
    - Placed rows, with these coordinates:
      - Cadulawan:
        - Purok Boongon 10.278797,123.843461
        - Sitio Mahayahay 10.279288,123.842392
        - Lower Mahayahay 10.276298,123.843254
      - Bulacao:
        - Sitio Kabanayan 10.273698,123.843391
        - Lower Kabanayan 10.272346,123.843987
      - Camp IV:
        - Cambawog Upper 10.309506,123.816231
        - Sitio Proper 10.320908,123.820364
      - Manipis Camp 6: 10.320982,123.786523
      - Dumlog:
        - Sitio Paglaom 10.245646,123.834572
        - Sitio Bahala 10.252728,123.835667
      - San Roque Sitio Ughay, moved to 10.255580,123.858710
    - Parents:
      - Upper/Lower Mahayahay → Sitio Mahayahay
      - Upper/Lower Kabanayan → Sitio Kabanayan
      - Purok Sambag (Camp IV) → Sitio Proper
    - New unplaced rows:
      - Manipis Sitio Langoyon
      - Camp IV Sitio Curba
      - Camp IV Purok Saging
      - Cadulawan Purok Nangka
    - Each row's `sources` and `note` say where it came from, in the file's existing style (e.g. `CDN 2024` and `"barangay hall at Purok Boongon"`).
  - **`name_variants.csv`:** the six variants, plus Cadulawan `Lower Candulawan` → `Zone II (Lower)`.
  - **`needs_barangay_check.csv`:** drop the rows now placed. Add the four new unplaced names with their searches.
  - **`SOURCES.md`:** in the sources table, add:
    - CDN 2024 (Candulawan)
    - camp4talisay.com
    - Philstar 2025 (Gatchalian visit)
    - RPN 2026
    - Bombo Radyo 2026
    - ABS-CBN 2022
    - CDN 2021 (Manipis closures)
    
    And one line under Files for `place_areas.csv` (generated by the build).
- [ ] **Step 4: Run it.** The same command gives OK.
- [ ] **Step 5: Leave uncommitted**

### Task 2: Splitting fixes

**Files:**
- Modify: `backend/apps/history/bfp_link.py`
- Test: `backend/tests/test_bfp_link.py`

**Interfaces:**
- Produces:
  - `split_address(text, barangay_names) -> (str | None, [(label, place)])`: same signature, new behaviour below
  - `street_parts(text, barangay_names) -> [str]`
  - `street_key(name) -> str`

- [ ] **Step 1: Write the failing tests** in `SplitAddressTests`:
  - `test_semicolons_separate_places`: `'PUROK BAMBOO; PUROK KAIMITO, BRGY MANIPIS'` → `('Manipis', [('purok','BAMBOO'), ('purok','KAIMITO')])`
  - `test_a_leading_house_number_is_dropped`: `'100 Art Ville, San Isidro, Talisay City Cebu'` → `('San Isidro', [('', 'Art Ville')])`
  - `test_upper_or_lower_barangay_is_also_a_place`:
    - `'Bontory, Upper Mohon, Talisay City, Cebu'` → `('Mohon', [('', 'Bontory'), ('', 'Upper Mohon')])`
    - `'Purok Mangga, Lower Candulawan, …'` → `('Cadulawan', [('purok','Mangga'), ('', 'Lower Candulawan')])`
    
    Update the two existing `test_split` cases to match.
  - `test_barangay_hall_stays_a_place`: `'Barangay Hall, Mohon, Talisay City, Cebu'` → `('Mohon', [('', 'Barangay Hall')])`
  - `test_street_parts`:
    - `'Nacario St., Tabunok, Talisay City Cebu'` → `['Nacario St.']`
    - `'609 Burgos St., Dumlog, …'` → `['Burgos St.']`
    - `'Purok Alisto, Tabunok, …'` → `[]`
  - `test_street_key`:
    - `street_key('Nacario St.') == street_key('Nacario Street')`
    - `street_key('Mansueto Rd.') == street_key('Mansueto Road')`
    - `street_key('N. Bacalso Ave.') == street_key('N. Bacalso Avenue')`
- [ ] **Step 2: Run it.** `manage.py test tests.test_bfp_link` fails on the new cases.
- [ ] **Step 3: Implement.**
  - In `split_address`: `;` acts as `,`. A leading all-digit word is dropped before `_candidate` runs. `_strip_barangay_word` leaves `"Barangay Hall"` alone. When `_barangay_in` matched through the Upper/Lower rule, that whole part is also a candidate.
  - `street_parts` returns the parts before the barangay that `_candidate` rejects as streets (`STREET_LAST`, or ends in `ROAD`), house number dropped.
  - `street_key` maps the last word `st`/`st.`/`str` → `street`, `rd`/`rd.` → `road` and `ave`/`ave.`/`av` → `avenue`, then applies `norm_name`.
- [ ] **Step 4: Run it.** `manage.py test tests.test_bfp_link tests.test_bfp_import tests.test_flood_landslide_import` gives OK.
- [ ] **Step 5: Leave uncommitted**

### Task 3: One name index, sitio fallback, no-barangay addresses

**Files:**
- Modify: `backend/apps/history/bfp_link.py`, `backend/apps/history/bfp_import.py`, `backend/apps/history/management/commands/import_bfp_fires.py`, `backend/apps/history/management/commands/import_flood_landslide.py` (one line)
- Test: `backend/tests/test_bfp_link.py`, `backend/tests/test_bfp_import.py`

**Interfaces:**
- Consumes: Task 2's `street_parts`, `street_key`.
- Produces:
  - `class LinkIndex(dict)`: `{canonical barangay: {key: area name}}`, the same shape `load_variants` returns, so `find_purok` takes it unchanged. It has a method `rule(barangay_name, key) -> str`.
  - `load_link_index(data_dir: Path) -> LinkIndex`. It reads, each file only if present and in this order (an earlier source wins a key):
    1. `name_variants.csv` (rule `purok`)
    2. the unplaced rows of `purok_points.csv`, each mapped to its nearest placed ancestor (rule `sitio`)
    3. `place_areas.csv`: kind `landmark` keyed by `norm_name` (rule `landmark`), and kind `street` with `share >= STREET_SHARE`, keyed by `street_key` (rule `street`)
  - `explain_link(text, barangays, puroks_by_barangay, index) -> (barangay | None, purok name | None, rule | '')`
  - `link_address(...)` keeps its signature and returns `explain_link(...)[:2]`.
  - `STREET_SHARE = 0.75`, added to `apps/barangays/purok_estimate.py` here and imported by `bfp_link`. Task 4 uses it too.

- [ ] **Step 1: Write the failing tests** (`LinkIndexTests`, `ExplainLinkTests`; write small CSVs to a temp dir, as `test_load_variants` does):
  - `test_an_unplaced_purok_maps_to_its_nearest_placed_sitio`: Macopa (unplaced, parent Sitio Laray, placed) → `'Sitio Laray'`, rule `sitio`. A chain of unplaced → unplaced → placed walks up to the placed one.
  - `test_a_variant_beats_a_sitio_fallback_for_the_same_key`
  - `test_streets_below_the_share_are_left_out`: share 0.74 is absent, 0.75 present
  - `test_explain_link_rules`, each with its `(barangay, purok, rule)`:
    - `'PUROK MACOPA, LARAY, BRGY SAN ROQUE'` → `Sitio Laray` / `purok` (Laray is written)
    - `'Purok Macopa, San Roque, …'` → `Sitio Laray` / `sitio`
    - `'Barangay Hall, Mohon, …'` → the hall's area / `landmark`
    - `'Nacario St., Tabunok, …'` → its area / `street`
    - `'Tabunok, Talisay City Cebu'` → `(Tabunok, None, '')`
  - `test_written_names_beat_fallbacks` (Review Focus 1): with Kimba placed and Macopa → Laray in the index, `'Purok Macopa, Kimba, San Roque'` → `Kimba`
  - `test_no_barangay_takes_the_one_barangay_with_the_name`:
    - `'Sitio Napo, Talisay City Cebu'` → Tapul
    - `'Sitio Iba, Purok Rambutan, Talisay City, Cebu'` with Iba in Lagtang and Lawaan II, and Rambutan only in Lawaan II's index → Lawaan II, rule `sitio`
  - `test_no_barangay_and_two_candidates_stays_unplaced` (Review Focus 2): `'Sitio Iba, Talisay City'` → `(None, None, '')`
  - In `test_bfp_import`: `test_report_counts_links_by_rule`, so `report['linked_by']` equals e.g. `{'purok': 1, 'sitio': 1}` for two fixture rows.
- [ ] **Step 2: Run it.** `manage.py test tests.test_bfp_link tests.test_bfp_import` fails with ImportError on `load_link_index`.
- [ ] **Step 3: Implement** in `bfp_link.py`.
  - `explain_link`:
    1. Try a direct match (purok name or `purok`-rule key) on every candidate, Purok-labelled first.
    2. Then `sitio` and `landmark` keys.
    3. Then `street_parts` through `street_key`.
  - When `split_address` finds no barangay, run steps 1–2 against each barangay. Exactly one barangay matching → that barangay and its rule.
  - `plan_import` calls `explain_link`, and the report gains `linked_by` (a dict of rule → count).
  - `import_bfp_fires` (both the import and `--relink`) and `import_flood_landslide` call `load_link_index(PUROK_DATA)` where they called `load_variants(VARIANTS_FILE)`. `print_report` prints `linked by: purok N, sitio N, landmark N, street N`.
- [ ] **Step 4: Run it.** `manage.py test tests.test_bfp_link tests.test_bfp_import tests.test_flood_landslide_import tests.test_bfp_reader` gives OK.
- [ ] **Step 5: Leave uncommitted**

### Task 4: Landmarks and streets to areas (`place_areas`)

**Files:**
- Modify: `backend/apps/barangays/purok_estimate.py`, `backend/apps/barangays/management/commands/build_purok_estimates.py`
- Test: `backend/tests/test_purok_estimate.py`

**Interfaces:**
- Produces:
  - `LINK_PLACES`: `('bridge', 'bridge', ('yes',))` and `('mall', 'shop', ('mall', 'department_store', 'supermarket'))`. `landmark_query` asks for them too. `landmarks_from_osm` returns them with those kinds, keeping a bridge only when its name contains "bridge". `area_names` ignores those kinds, so unnamed area names don't change.
  - `place_areas(leaves, containers, points, lines) -> [{'place', 'kind', 'area', 'share'}]`:
    - `leaves` and `containers` are `[(name, geometry)]` in lng/lat; `points` and `lines` are as from `landmarks_from_osm`.
    - A landmark goes to the first leaf that contains it, else a container, with share 1.0. A `hall` whose name matches `BARANGAY_HALL = re.compile(r'barangay hall|bulwagang|bahay pamahalaan', re.I)` also gives a row with place `Barangay Hall`.
    - A street's segments are summed by name. The street goes to the leaf holding the largest share; when that share is under `STREET_SHARE`, the container holding the largest share is used if it reaches `STREET_SHARE`. Names matching `NAMES_A_PUROK` are skipped.
    - When two landmarks match one place name in a barangay, the place is written to neither.
  - `STREET_SHARE` comes from Task 3.
  - The build writes `place_areas.csv` (`barangay,place,kind,area,share`) next to `--out`. With `--barangay`, rows for other barangays already in that file are kept. The landmark cache becomes `osm_landmarks_v2.json`.

- [ ] **Step 1: Write the failing tests** (`PlaceAreasTests`, on 2×1 boxes like the existing area tests):
  - `test_a_landmark_goes_to_the_leaf_it_stands_in`
  - `test_a_point_in_a_sitio_leftover_goes_to_the_sitio`
  - `test_the_barangay_hall_gets_its_alias`
  - `test_a_street_mostly_in_one_area_gets_its_share`: share 0.8, area named
  - `test_a_street_across_two_puroks_of_one_sitio_goes_to_the_sitio`
  - `test_two_landmarks_with_one_name_give_no_row` (Review Focus 3)
  - `test_bridges_are_kept_only_when_named_as_bridges`
- [ ] **Step 2: Run it.** `manage.py test tests.test_purok_estimate` fails with AttributeError on `place_areas`.
- [ ] **Step 3: Implement** `place_areas`, `LINK_PLACES` and `BARANGAY_HALL`. In `split_one`, return the place rows with the features; `handle` writes the CSV.
- [ ] **Step 4: Run it.** `manage.py test tests.test_purok_estimate` gives OK.
- [ ] **Step 5: Leave uncommitted**

### Task 5: Sitio first, then its puroks (nested split)

**Files:**
- Modify: `backend/apps/barangays/purok_estimate.py`, `backend/apps/barangays/management/commands/build_purok_estimates.py`
- Test: `backend/tests/test_purok_estimate.py`

**Interfaces:**
- Consumes: `split_named`, `tidy`, `outline_areas` (unchanged signatures).
- Produces:
  - `Node = namedtuple('Node', 'row children')`
  - `name_tree(rows) -> (top: [Node], leaves: int)`. It replaces `area_points`; delete `area_points` and its tests.
    - Only placed rows make nodes.
    - A placed row whose parent row is unplaced, or missing, is a top node.
    - `leaves` counts every row that is nobody's parent, as before.
  - `pull_inside(lng, lat, outline) -> (lng, lat)`: the point unchanged if `outline` contains it; otherwise the nearest point of `outline.buffer(-0.00005)` (about 5 m in), falling back to `outline.point_on_surface`.
  - `split_nested(inside, houses, step, n, top, to_cell, preset_for, barrier=None, dem=None, loose_reach=math.inf, min_cells=0) -> (named: [(row, mask, members)], unnamed: [mask])`:
    - `to_cell(row) -> (r, c)`; `preset_for(row) -> bool mask | None` (the row's own outline cells).
    - **Level 1:** one `split_named` over every placed row in the barangay. Each row is a seed with share 1, its preset is its own outline, and `loose` means confidence `low`. Then each seed is relabelled to its top node, and the level is tidied.
    - **Inside a node with children:** `split_named` on the node's territory, with `n` = number of seeds. The seeds are the node's own pin (no preset), plus each child subtree's rows relabelled to that child. Recurse.
    - A node with children gets `members` = number of direct children, and its mask is its whole territory.
  - **Build `split_one`:**
    1. A `low` child whose parent has an outline in `community_outlines.geojson` goes through `pull_inside` before `to_cell`.
    2. `split_nested` runs.
    3. Features are written for every named mask (containers included) and for the unnamed areas.
    4. The log adds `N sitios`.

- [ ] **Step 1: Write the failing tests** (`NestedSplitTests`, on the small grids the `SplitNamedTests` use):
  - `test_name_tree_nests_placed_rows_under_placed_parents`: a child of an unplaced parent is top
  - `test_leaves_count_every_name_that_is_nobodys_parent`, kept from today's tests
  - `test_a_sitios_territory_holds_its_puroks`: every child mask lies inside the parent mask
  - `test_the_sitio_keeps_a_leftover_of_its_own`: parent mask minus the child masks is not empty
  - `test_a_sitio_takes_in_a_medium_purok_far_away` (Review Focus 4): the parent mask covers the child's seed cell, even in two pieces
  - `test_pull_inside_moves_a_rough_point_into_the_outline_and_leaves_one_inside_alone`
  - `test_shares_count_the_whole_subtree`: on an even grid, a sitio with 2 puroks holds about 3/4 of the houses next to a lone purok
  - `test_names_are_unique_after_the_split` (Review Focus 5): build-level helper over `split_one`'s output on a fixture
- [ ] **Step 2: Run it.** `manage.py test tests.test_purok_estimate` fails with ImportError on `name_tree`.
- [ ] **Step 3: Implement** `Node`, `name_tree`, `pull_inside` and `split_nested`, then switch `split_one` over to them.
- [ ] **Step 4: Run it.** `manage.py test tests.test_purok_estimate tests.test_load_puroks` gives OK.
- [ ] **Step 5: Leave uncommitted**

### Task 6: No pinned name is lost

**Files:**
- Modify: `backend/apps/barangays/purok_estimate.py`
- Test: `backend/tests/test_purok_estimate.py`

**Interfaces:**
- Produces: `MIN_GAP_CELLS = 3`. `split_named` spreads its starting points: after the loose moves, a start closer than `MIN_GAP_CELLS` to an earlier start moves to the nearest house cell inside at least `MIN_GAP_CELLS` from every start. The `low` one moves first, else the later one. `tidy`'s majority filter never flips a label's last remaining cells.

- [ ] **Step 1: Write the failing tests:**
  - `test_four_names_on_one_spot_each_keep_an_area`: four seeds on one cell of a 30×30 house grid; after `split_named` + `tidy`, all four labels own at least `min_cells` cells
  - `test_a_lone_seed_is_not_moved`
- [ ] **Step 2: Run it.** `manage.py test tests.test_purok_estimate` fails on the first new test.
- [ ] **Step 3: Implement** the spreading in `split_named` and the guard in `tidy`.
- [ ] **Step 4: Run it, then check Lagtang.**
  - `manage.py test tests.test_purok_estimate` gives OK.
  - Then run `manage.py build_purok_estimates --barangay Lagtang --out <scratchpad>/lagtang.geojson`. Expected: no `no area left for` line. Before this change it named Molave, Sitio Diego Silang and Purok Jacinto Zamora.
- [ ] **Step 5: Leave uncommitted**

### Task 7: Containers in the API and zone overlaps

**Files:**
- Modify: `backend/apps/barangays/models.py`, `backend/apps/barangays/serializers.py`, `backend/apps/barangays/views.py`, `backend/apps/hazards/geometry.py`
- Test: `backend/tests/test_load_puroks.py` (`PurokSerializerTests`), `backend/tests/test_resolve_links_puroks.py`

**Interfaces:**
- Produces:
  - `Purok.member_counts() -> {(barangay_id, name): n}`: a classmethod with one query over non-blank `parent`
  - Each feature from `GET /api/barangays/puroks/` carries `members` (int), read from `context['members']` and defaulting to 0
  - `overlapping_puroks(geometry)` leaves out containers

- [ ] **Step 1: Write the failing tests:**
  - `test_feature_carries_its_member_count`: a serializer with `context={'members': {(1, 'Sitio Laray'): 2}}` gives `members == 2`, and `0` for another purok
  - `test_a_flood_never_counts_in_a_sitio_around_its_puroks`: a container covering `self.near` plus a child; the resolved zone's record lists only the child puroks
- [ ] **Step 2: Run it.** `manage.py test tests.test_load_puroks tests.test_resolve_links_puroks` fails on the two tests.
- [ ] **Step 3: Implement.** `PurokListView` passes `context={'members': Purok.member_counts()}`. `overlapping_puroks` excludes ids whose `(barangay_id, name)` is in `member_counts()`.
- [ ] **Step 4: Run it.** `manage.py test tests` gives OK (the whole backend suite).
- [ ] **Step 5: Leave uncommitted**

### Task 8: The map

**Files:**
- Modify: `frontend/src/components/Map/purokStyle.js`, `frontend/src/components/Map/PurokHistoryLayer.jsx`, `frontend/src/components/Map/purokLevels.js`
- Test: `frontend/src/components/Map/purokStyle.test.js`, `frontend/src/components/Map/purokLevels.test.js`

**Interfaces:**
- Produces:
  - `isContainer(feature) -> bool`: `members > 0`
  - `purokStyle(feature)`: weight `3` for a container, `1.5` otherwise, never filled
  - `purokAt(geo, lng, lat)`: of the features containing the point, a non-container wins; between two of the same sort, the smaller ring area wins
  - `purokTooltip(feature)`: a container's tooltip adds `{members} puroks inside` (1 → `1 purok inside`)
  - `splitFills(filled) -> {sitios, puroks}`: two FeatureCollections or nulls. `PurokHistoryLayer` draws `sitios` in pane `sitio-fills` (zIndex 355) and `puroks` in `purok-fills` (360).

- [ ] **Step 1: Write the failing tests:**
  - `purokAt` returns the purok, not its sitio, inside both, and the sitio on its leftover (Review Focus 4)
  - `purokStyle` gives weight 3 for `members: 2`
  - `purokTooltip` for `members: 3` contains `3 puroks inside`
  - `splitFills` puts a `members: 2` feature in `sitios`
- [ ] **Step 2: Run it.** `CI=true npx react-scripts test --watchAll=false src/components/Map` fails on the new tests.
- [ ] **Step 3: Implement** the four helpers and the second pane.
- [ ] **Step 4: Run it.** `CI=true npx react-scripts test --watchAll=false` gives all pass.
- [ ] **Step 5: Leave uncommitted**

### Task 9: Build the whole city locally and dry-run the links

**Files:**
- Modify (generated): `backend/apps/barangays/data/puroks/talisay_puroks_estimated.geojson`, `backend/apps/barangays/data/puroks/place_areas.csv`
- Create (scratchpad only, not the repo): `dryrun_links.py`

- [ ] **Step 1: Build.** `manage.py build_purok_estimates`. Expected: no `no area left for` line, and each barangay's line shows its sitio count.
- [ ] **Step 2: Write the dry-run script.** It loads purok names per barangay from the new GeoJSON's `(barangay, name)` and the index from `load_link_index(PUROK_DATA)`. It reads every `HistoricalRecord` (read-only), runs `explain_link` on `location_text`, and prints three things:
  - how many link by each rule, against today's links
  - the records that change purok
  - the ones still unlinked, grouped as street / landmark / name / barangay only
- [ ] **Step 3: Run the script** with `manage.py shell -c "exec(open(r'<scratchpad>/dryrun_links.py').read())"`. Expected: more than the 4 + 17 + 3 records named in the spec's table now link, and nothing that linked before is lost.
- [ ] **Step 4: Run every test.** `manage.py test tests` and `CI=true npx react-scripts test --watchAll=false` both pass.
- [ ] **Step 5: Leave uncommitted.** Report `git status --short` and the dry-run numbers. Don't load, relink or re-import until the user says so.
