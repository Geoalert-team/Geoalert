"""
Where floods were seen, for training and testing the flood susceptibility
model (spec 3.1). Only `manage.py train_flood_model` reads this module; the
feature builder never does, so no flood observation can become an input.

- The 2017 UP Mananga flood survey: Annex 11 of E. C. Paringit and R. S.
  Otadoy (eds.) (2017), LiDAR Surveys and Flood Mapping of Mananga River,
  UP Training Center for Applied Geodesy and Photogrammetry / University of
  San Carlos (Phil-LiDAR 1): 169 flood depths residents reported at 107
  spots for six typhoons (1990-2014). Its terms allow research and
  educational use with acknowledgement.
- The EOS-RS flood proxy map of Typhoon Tino (Sentinel-1, 4 Nov 2025):
  Earth Observatory of Singapore - Remote Sensing Lab; contains modified
  Copernicus Sentinel data (2025). A test only.
- GeoAlert's own flood records that have a map point (a test only).

The PDF, the parsed points and the satellite map are private: they live only
in the git-ignored cache folder (backend/.hazard_cache), are never written to
apps/history/data, and only fitted numbers reach the website.
"""
import csv
import re
import zipfile
from pathlib import Path

from apps.history.downloads import fetch_verified

MANANGA_PDF_URL = ('https://dream.upd.edu.ph/assets/Publications/LiDAR-Technical-Reports/USC/'
                   'LiDAR-Surveys-and-Flood-Mapping-of-Mananga-River.pdf')
MANANGA_PDF_SHA256 = '616821337324a60f1ec24be47c3d292e001a2f942f482bd77df0ebba1e99be11'
MANANGA_PDF_FILE = 'mananga_lidar_flood_report_2017.pdf'
EOSRS_ZIP_URL = ('https://sentinel-asia.org/EO/2025/article20251104PH/EOS-RS_20251104_FPM_S1/'
                 'EOS-RS_20251104_FPM_S1_Central_Philippines_Typhoon_Kalmaegi_v0.9_shp.zip')
EOSRS_ZIP_SHA256 = '5855f2d05d645f84625ed2379ee85b2b643c8dc0a0713433f6554cb2963d730c'
EOSRS_ZIP_FILE = 'eosrs_tino_fpm_v0.9_shp.zip'
EOSRS_DIR = 'eosrs_tino_fpm'
ANNEX_FILE = 'mananga_annex11_points.csv'
ANNEX_ROWS = 169
ANNEX_COLUMNS = ('point', 'lat', 'lon', 'modelled_m', 'reported_m', 'event')

# "n lat lon modelled reported squared-error event 100-Year", one row of Table A-11.1
ROW = re.compile(r'^(\d+) (10\.\d+) (123\.\d+) ([\d.]+) ([\d.]+) ([\d.]+) (.+?) 100-Year$')


def parse_annex11(text: str, expected: int = ANNEX_ROWS) -> list:
    """Annex 11's rows from the report's text; anything but `expected` rows is an error, never a partial set."""
    rows = []
    for line in text.splitlines():
        m = ROW.match(' '.join(line.split()))
        if m:
            rows.append({'point': int(m.group(1)), 'lat': float(m.group(2)), 'lon': float(m.group(3)),
                         'modelled_m': float(m.group(4)), 'reported_m': float(m.group(5)),
                         'event': m.group(7).strip()})
    if len(rows) != expected:
        raise ValueError(f'Annex 11 must have {expected} rows, found {len(rows)}.')
    return rows


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    return '\n'.join(page.extract_text() or '' for page in PdfReader(str(path)).pages)


def annex_points(cache_dir: Path, refresh: bool = False) -> list:
    """The 169 survey points, from the cached CSV, else parsed from the (downloaded) report."""
    cache_dir = Path(cache_dir)
    csv_path = cache_dir / ANNEX_FILE
    if csv_path.exists() and not refresh:
        with open(csv_path, newline='', encoding='utf-8') as f:
            rows = [{'point': int(r['point']), 'lat': float(r['lat']), 'lon': float(r['lon']),
                     'modelled_m': float(r['modelled_m']), 'reported_m': float(r['reported_m']),
                     'event': r['event']} for r in csv.DictReader(f)]
        if len(rows) == ANNEX_ROWS:
            return rows
    pdf = fetch_verified(MANANGA_PDF_URL, MANANGA_PDF_SHA256, cache_dir / MANANGA_PDF_FILE)
    rows = parse_annex11(_pdf_text(pdf))
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=ANNEX_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def spots(points: list) -> list:
    """
    One entry per distinct place: {lat, lon, events, max_depth, positive}.
    A spot is positive when any event's reported depth there is above zero;
    the same place reported for several typhoons is still one place.
    """
    by_place = {}
    for p in points:
        entry = by_place.setdefault((p['lat'], p['lon']), {'lat': p['lat'], 'lon': p['lon'], 'events': [],
                                                           'max_depth': 0.0})
        if p['event'] not in entry['events']:
            entry['events'].append(p['event'])
        entry['max_depth'] = max(entry['max_depth'], p['reported_m'])
    for entry in by_place.values():
        entry['positive'] = entry['max_depth'] > 0
    return list(by_place.values())


def _safe_extract(archive: Path, target: Path):
    """Extract a zip, refusing any member that would land outside `target`."""
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    with zipfile.ZipFile(archive) as z:
        for member in z.namelist():
            if not (root / member).resolve().is_relative_to(root):
                raise RuntimeError(f'{archive} has an unsafe member name: {member}')
        z.extractall(target)


def eosrs_polygons(cache_dir: Path) -> list:
    """The Tino flood proxy map's polygons (SRID 4326), from the verified, cached shapefile."""
    from django.contrib.gis.gdal import DataSource
    from django.contrib.gis.geos import GEOSGeometry

    cache_dir = Path(cache_dir)
    archive = fetch_verified(EOSRS_ZIP_URL, EOSRS_ZIP_SHA256, cache_dir / EOSRS_ZIP_FILE)
    folder = cache_dir / EOSRS_DIR
    shapes = list(folder.glob('*.shp'))
    if not shapes:
        _safe_extract(archive, folder)
        shapes = list(folder.glob('*.shp'))
    if len(shapes) != 1:
        raise RuntimeError(f'{archive} should hold one shapefile; found {len(shapes)}.')
    return [GEOSGeometry(feature.geom.wkt, srid=4326) for feature in DataSource(str(shapes[0]))[0]]


def geoalert_flood_points() -> list:
    """GeoAlert's flood records that have a map point (read-only): {source_ref, day, barangay, lat, lon, precision}."""
    from django.utils import timezone

    from apps.history.models import HistoricalRecord

    records = (HistoricalRecord.objects.filter(hazard_type__name='Flood', location__isnull=False)
               .select_related('barangay').order_by('occurred_at'))
    return [{'source_ref': r.source_ref, 'day': timezone.localtime(r.occurred_at).date().isoformat(),
             'barangay': r.barangay.name if r.barangay else None, 'lat': r.location.y, 'lon': r.location.x,
             'precision': r.location_precision} for r in records]
