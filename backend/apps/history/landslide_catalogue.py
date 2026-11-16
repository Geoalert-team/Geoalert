"""
NASA's Global Landslide Catalog (2007-2017), used only for extra landslide days near Talisay.

The catalogue states no licence. Its raw rows stay in the git-ignored .hazard_cache/ folder and are never
committed, shown or served; only numbers fitted from them reach the app.
"""
import calendar
import csv
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Mapping

import requests

from apps.barangays.aliases import spellings
from apps.history.hazard_data import DATA_DIR
from apps.history.rain import USER_AGENT
from apps.history.storms import haversine_km

CATALOGUE_URL = 'https://data.nasa.gov/docs/legacy/Global_Landslide_Catalog_Export/Global_Landslide_Catalog_Export_rows.csv'
CACHE_NAME = 'nasa_global_landslide_catalog.csv'
CATALOGUE_RADIUS_KM = 20.0
EXCLUSIONS_FILE = DATA_DIR / 'landslide_catalogue_exclusions.csv'


@dataclass(frozen=True)
class CatalogueRecord:
    event_id: str
    day: date
    lat: float
    lon: float
    accuracy: str
    text: str
    place_text: str


def get(url) -> bytes:
    resp = requests.get(url, timeout=120, allow_redirects=True, headers={'User-Agent': USER_AGENT})
    resp.raise_for_status()
    return resp.content


def ensure_catalogue(cache_dir: Path, get=None) -> Path:
    """The cached catalogue file; downloaded (redirects followed) only when it is missing."""
    path = Path(cache_dir) / CACHE_NAME
    if not path.exists():
        data = (get or globals()['get'])(CATALOGUE_URL)
        first = data.split(chr(10).encode(), 1)[0]
        if b'event_date' not in first or b'latitude' not in first:
            raise ValueError('The download is not the landslide catalogue (header line lacks event_date/latitude).')
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix('.part')
        part.write_bytes(data)
        os.replace(part, path)
    return path


def read_catalogue(path) -> list[CatalogueRecord]:
    out = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            try:
                day = datetime.strptime((row.get('event_date') or '').split()[0], '%m/%d/%Y').date()
                lat, lon = float(row['latitude']), float(row['longitude'])
            except (ValueError, IndexError, KeyError, TypeError):
                continue
            text = ' | '.join(row.get(k) or '' for k in
                              ('event_title', 'location_description', 'admin_division_name', 'gazeteer_closest_point'))
            place = f"{row.get('event_title') or ''} {row.get('location_description') or ''}"
            out.append(CatalogueRecord((row.get('event_id') or '').strip(), day, lat, lon,
                                       (row.get('location_accuracy') or '').strip(), text, place))
    return out


def load_exclusions(path=EXCLUSIONS_FILE) -> dict[str, str]:
    with open(path, newline='', encoding='utf-8') as f:
        return {row['event_id'].strip(): row['reason'].strip() for row in csv.DictReader(f)}


def near(records, centre, excluded: Mapping[str, str], radius_km=CATALOGUE_RADIUS_KM) -> list[CatalogueRecord]:
    """Records within the radius, minus listed ids and anything mentioning Negros."""
    return [r for r in records
            if r.event_id not in excluded and 'negros' not in r.text.lower()
            and haversine_km(centre[0], centre[1], r.lat, r.lon) <= radius_km]


def era_end(records) -> date:
    last = max(r.day for r in records)
    return date(last.year, last.month, calendar.monthrange(last.year, last.month)[1])


def named_barangay(record, names: Mapping[int, str]) -> int | None:
    """The one barangay named in the human-written place text (title and location), only when that text
    also says Talisay. Gazetteer and admin fields come from the coordinates, so they never decide."""
    place = ' '.join(record.place_text.split()).lower()
    if 'talisay' not in place:
        return None
    hits = set()
    for bid, name in names.items():
        for spelling in spellings(name):
            if re.search(r'(?<!\w)' + re.escape(spelling) + r'(?!\w)', place):
                hits.add(bid)
                break
    return next(iter(hits)) if len(hits) == 1 else None
