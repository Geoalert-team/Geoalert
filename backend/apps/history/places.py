"""
history_places.csv: the map point of a past event whose source names the
spot, read for manage.py place_history_records.

One row per record, keyed by its source_ref: lat and lng, the precision
(place: the map pin of the purok or sitio the source names; landmark: a
landmark it names) and the basis, the words saying where the point comes
from. Other columns are for people and are ignored. A record whose source
names only a barangay has no row and so no point.

A plain function so it tests without the database; the command does the
lookups and the one transaction.
"""
import csv
import io
from collections import namedtuple

from django.contrib.gis.geos import Point

from apps.history.models import HistoricalRecord

Place = namedtuple('Place', 'ref point precision basis')
PRECISIONS = [value for value, _ in HistoricalRecord.LOCATION_PRECISIONS]
BASIS_MAX = HistoricalRecord._meta.get_field('location_basis').max_length


def _number(text, low, high):
    value = float(text)
    if not low <= value <= high:
        raise ValueError
    return value


def read_places(text):
    """[Place] from the file's text; ValueError naming the line of a bad row."""
    places, seen = [], set()
    # Line 1 is the header, so the first row is line 2
    for line, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        ref = (row.get('source_ref') or '').strip()
        if not ref:
            raise ValueError(f'line {line}: no source_ref')
        if ref in seen:
            raise ValueError(f'line {line}: {ref} is given twice')
        try:
            lat = _number(row.get('lat') or '', -90, 90)
            lng = _number(row.get('lng') or '', -180, 180)
        except ValueError:
            raise ValueError(f'line {line}: {ref} needs a latitude and a longitude') from None
        precision = (row.get('precision') or '').strip()
        if precision not in PRECISIONS:
            raise ValueError(f'line {line}: {ref} precision {precision!r} is not one of {", ".join(PRECISIONS)}')
        basis = ' '.join((row.get('basis') or '').split())
        if len(basis) > BASIS_MAX:
            raise ValueError(f'line {line}: {ref} basis is over {BASIS_MAX} characters')
        seen.add(ref)
        places.append(Place(ref, Point(lng, lat, srid=4326), precision, basis))
    return places
