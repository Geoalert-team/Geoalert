"""
Open landslide inventories for the landslide susceptibility model: NASA COOLR
(new events, a File GDB of points) and the Typhoon Mangkhut scars at Itogon
(polygons). Training data only: they are kept in `.hazard_cache` and are never
served, stored in the database or shown to users.
"""
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from apps.history.downloads import fetch_verified, sha256_of

COOLR_URL = 'https://ndownloader.figshare.com/files/54363830'
COOLR_SHA256 = '2a019c6a955a4e9ae8da9b8740c1f64c3cd9a162e90972bb03509a5f119dfd38'
COOLR_ZIP = 'nasa_coolr_new_events.zip'
COOLR_GDB = 'nasa_coolr_new_events/nasa_coolr_new_events.gdb'
COOLR_LAYER = 'nasa_coolr_events_new_point'

MANGKHUT_URL = 'https://data-package.ceh.ac.uk/data/32765a61-8510-4dfc-b7c7-58bad12f8497.zip'
MANGKHUT_ZIP = 'eidc_mangkhut_itogon.zip'
MANGKHUT_SHAPE = 'data/itogon_inventory_v11_wgs84utm51.shp'
# The package wrapper may be regenerated, so the three inner files are pinned.
MANGKHUT_FILES = {
    'data/itogon_inventory_v11_wgs84utm51.shp': 'fd28551e09f95c87c9db234d9c0dbcc2e8e381d76d657277c230bec5c8ad8099',
    'data/itogon_inventory_v11_wgs84utm51.dbf': '89beefb3f3f3c998300b0e12fbff95d6df6b4fac71974f90c7bb6197d600ca84',
    'data/itogon_inventory_v11_wgs84utm51.shx': 'd4d8563a08834cd1ea928d1b8252a30394025c8e6cfc100be3d90a0e69e9b79a',
}
MANGKHUT_SRID = 32651

# R26: Egay's slides reach Apayao, Kalinga and Mountain Province, and Paeng's Sultan Kudarat (an exact
# point-in-polygon check put 71% of Egay's slides outside the first three provinces' maps).
EVENT_NOAH = {
    'egay': ('Abra', 'IlocosNorte', 'IlocosSur', 'Apayao', 'Kalinga', 'MountainProvince'),
    'mangkhut': ('Benguet',),
    'paeng': ('Maguindanao', 'Cotabato', 'SultanKudarat'),
    'agaton': ('Leyte', 'SouthernLeyte'),
}


@dataclass(frozen=True)
class Event:
    key: str
    date: date
    fold: str
    region: str
    landcover_year: int
    noah_provinces: tuple


# Philippine COOLR events by date: key and the land cover year (the year before).
PH_COOLR = {
    date(2023, 7, 26): ('egay', 2022),
    date(2022, 10, 28): ('paeng', 2021),
    date(2022, 4, 10): ('agaton', 2021),
}

MANGKHUT_EVENT = Event('mangkhut', date(2018, 9, 14), 'mangkhut', 'ph', 2017, EVENT_NOAH['mangkhut'])


def _row_date(row: dict) -> date:
    text = str(row['ev_date'])[:10].replace('/', '-')  # '2023/07/26 ...' or GDAL's '2023-07-26'
    return datetime.strptime(text, '%Y-%m-%d').date()


def _row_event(row: dict) -> Event:
    when = _row_date(row)
    country = str(row['ctry_name'])
    if country == 'Philippines':
        if when not in PH_COOLR:
            raise ValueError(f'Unknown Philippine COOLR event {when.isoformat()}')
        key, year = PH_COOLR[when]
        return Event(key, when, key, 'ph', year, EVENT_NOAH[key])
    key = f"{country.lower().replace(' ', '_')}_{when:%Y%m%d}"
    return Event(key, when, 'world', 'world', when.year - 1, ())


def coolr_events(rows: list) -> dict:
    """{key: Event} for every event in the COOLR rows."""
    events = {}
    for row in rows:
        event = _row_event(row)
        events[event.key] = event
    return events


def coolr_slides(rows: list) -> list:
    """One {'event', 'lon', 'lat'} per COOLR row."""
    return [{'event': _row_event(r).key, 'lon': float(r['longitude']), 'lat': float(r['latitude'])} for r in rows]


def _extract(zip_path: Path, folder: Path, members=None) -> None:
    with zipfile.ZipFile(zip_path) as z:
        root = folder.resolve()
        names = members if members is not None else z.namelist()
        for member in names:
            if not (root / member).resolve().is_relative_to(root):
                raise RuntimeError(f'{zip_path} has an unsafe member name: {member}')
        z.extractall(folder, names)


def read_coolr(cache_dir: Path) -> list:
    """The COOLR new-events points as dicts keyed by the GDB field names."""
    from django.contrib.gis.gdal import DataSource

    cache_dir = Path(cache_dir)
    zip_path = fetch_verified(COOLR_URL, COOLR_SHA256, cache_dir / COOLR_ZIP)
    folder = cache_dir / zip_path.stem
    gdb = folder / COOLR_GDB
    if not gdb.exists():
        _extract(zip_path, folder)
    fields = ('ev_date', 'ctry_name', 'storm_name', 'latitude', 'longitude', 'ev_id')
    layer = DataSource(str(gdb))[COOLR_LAYER]
    return [{name: feature.get(name) for name in fields} for feature in layer]


def read_mangkhut(cache_dir: Path) -> list:
    """The Mangkhut scar polygons (GEOS, SRID 32651); each inner file's checksum is checked first."""
    from django.contrib.gis.gdal import DataSource, GDALException
    from django.contrib.gis.geos import GEOSGeometry

    cache_dir = Path(cache_dir)
    zip_path = fetch_unverified_zip(MANGKHUT_URL, cache_dir / MANGKHUT_ZIP)
    folder = cache_dir / zip_path.stem
    if not all((folder / name).exists() for name in MANGKHUT_FILES):
        _extract(zip_path, folder, list(MANGKHUT_FILES))
    for name, sha in MANGKHUT_FILES.items():
        if sha256_of(folder / name) != sha:
            raise RuntimeError(f'{folder / name} does not match its pinned checksum; delete it to extract it again.')
    layer = DataSource(str(folder / MANGKHUT_SHAPE))[0]
    polygons = []
    for feature in layer:
        try:
            wkt = feature.geom.wkt
        except GDALException:  # a feature with no geometry (one in the package) has no scar to read
            continue
        polygons.append(GEOSGeometry(wkt, srid=MANGKHUT_SRID))
    return polygons


def fetch_unverified_zip(url: str, dest: Path) -> Path:
    """The package zip, downloaded when missing. Its wrapper may change, so only the inner files are checked."""
    import requests

    from apps.history.downloads import CHUNK, USER_AGENT

    dest = Path(dest)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix('.part')
    try:
        response = requests.get(url, stream=True, timeout=300, headers={'User-Agent': USER_AGENT})
        response.raise_for_status()
        with open(part, 'wb') as f:
            for block in response.iter_content(chunk_size=CHUNK):
                if block:
                    f.write(block)
        part.replace(dest)
    finally:
        if part.exists():
            part.unlink()
    return dest
