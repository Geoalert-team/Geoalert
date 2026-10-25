# Purok and sitio data: sources

No purok or sitio boundaries are published for Talisay City. Official lines have been
requested from the Barangay Hall. Until they arrive, `manage.py build_purok_estimates`
draws estimated outlines from the files here, and `manage.py load_puroks` loads them.

## Files

| File | What it holds |
|---|---|
| `purok_points.csv` | One row per purok, sitio, zone or subdivision name: where it was found (`lat`, `lng`), how (`placed_by`), how sure (`confidence`), its sitio (`parent`) and its sources. Rows with no `lat`/`lng` are the names still to pin. Hand-editable: fix a point, then rebuild. |
| `community_outlines.geojson` | Outlines drawn for some of the names on Wikimapia and OpenStreetMap. A name with an outline starts its area from all of it. |
| `barangay_counts.csv` | How many puroks each barangay has: the official sitio count where the city's 2010 profile gives one, and 2015 households (÷ 175 gives the count elsewhere). |
| `notices.json` | The Visayan Electric outage notices that place names along roads (evidence for the `low` rows). |
| `talisay_puroks_estimated.geojson` | The built outlines. Generated; don't edit by hand. |
| `name_variants.csv` | Other spellings of a purok's name (`barangay,variant,name`), so a BFP address like "Ilan-ilang, San Roque" still finds Purok Ilang-Ilang. Read by `manage.py import_bfp_fires`. Hand-editable. |
| `needs_barangay_check.csv` | Names from the BFP fire log that no source could place, with their fire count, one example address and what was searched. For the Barangay Hall: a location for any of them names one of the unnamed areas. |

## Confidence

- **high**: the name has its own place or outline on Wikimapia or OpenStreetMap, or a
  chapel, court or school named after it.
- **medium**: a street named after it, a listing named after it ("Sitio Romahan, Dumlog"),
  or two or more Overture listings addressed there.
- **low**: an outage notice that names its road, or a single business address. On the
  map these start from the nearest free house cluster within 500 m, and hovering one
  says the location is approximate.

Areas called "Unnamed area k" stand for puroks the research couldn't place. The
barangay's purok count says they exist, but not where.

## Sources

| Source | Used for | Licence / terms | Accessed |
|---|---|---|---|
| BFP Talisay fire incident log, Jan 2023 – Sep 2026 (supplied by the team) | Names, and the spelling of a name where sources differ (the log wins); its fires are imported as history by `manage.py import_bfp_fires` | Internal | 2026-10-23, 2026-10-25 |
| City of Talisay 2010 Barangay Profiles, via the Wayback Machine (talisaycitycebu.gov.ph) | Official sitio counts, a few names | Public record | 2026-10-23 |
| Visayan Electric service interruption notices, 2024–2026 (visayanelectric.com) | Names with barangay and roads | Public notices | 2026-10-23 |
| Wikipedia, 2017 revisions of the barangay articles | Sitio lists for Cansojong and Lawaan II | CC BY-SA 4.0 | 2026-10-23 |
| DSWD DROMIC fire reports for Talisay (dromic.dswd.gov.ph) | Names | Public record | 2026-10-23 |
| Wikimapia (wikimapia.org, public API) | Places and outlines | CC BY-SA 3.0 | 2026-10-23 |
| OpenStreetMap (Overpass API, Nominatim search) | Places, landmarks, named areas, streets | ODbL 1.0 | 2026-10-23, 2026-10-25 |
| Overture Maps places, release 2026-10-21.0 | Places and addresses naming a sitio or purok | CDLA Permissive 2.0 | 2026-10-25 |
| SunStar, "3,000 families in disaster-prone areas in Talisay" (2014) | Landslide-prone sitio names | News report | 2026-10-25 |
| Philstar/The Freeman, SunStar and GMA reports, 2025–2026 (Typhoon Tino, fires) | Names (Sitio Nangka, Camp IV, and others) | News reports | 2026-10-25 |
| PhilAtlas (PSA 2015 census) | Households per barangay | PSA open data | 2026-10-23 |
| Microsoft Global ML Building Footprints | Where the houses are (sizes the areas) | ODbL 1.0 | 2026-10-23 |

Overture listings were checked by hand. A listing was kept only when its own name or
address names the sitio *and* the barangay it lies in, or when two or more listings
agree. Listings whose address names a different barangay were dropped.

## When the official boundaries arrive

    python manage.py load_puroks --file official_<barangay>.geojson --source official --dry-run

Read the overlap report, then run the command again without `--dry-run`. That replaces the
estimates for those barangays only.
