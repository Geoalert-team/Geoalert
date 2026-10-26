"""
Cleaning up a hazard zone drawn by hand on the map.

An officer outlines the affected area by tapping corners. Two things can go
wrong with a shape made that way, and both are fixed here rather than
rejected, because a publish that fails during an emergency is worse than one
that is slightly adjusted:

  * The outline can cross itself (a figure eight). PostGIS treats that as
    invalid, and intersects-queries on it give wrong answers, so it is
    repaired into the area the officer evidently meant.
  * The outline can spill past the city. Talisay only notifies its own
    barangays, so the part outside the city is cut off. A shape entirely
    outside is refused.
"""

from django.contrib.gis.db.models import Union
from django.contrib.gis.geos import GeometryCollection, MultiPolygon, Polygon

from apps.barangays.models import Barangay


# Less than this share of the drawn outline inside the city is refused.
# Tracing loosely along the coast or the city line keeps far more than this;
# only an outline that mostly missed the city falls below it.
MIN_INSIDE_SHARE = 0.05


class OutsideCity(ValueError):
    """The zone does not overlap the city at all."""


def city_outline():
    """Union of every barangay boundary, or None when none are loaded."""
    return Barangay.objects.filter(boundary__isnull=False).aggregate(
        outline=Union('boundary'),
    )['outline']


def _polygons_only(geom):
    """Keep the area parts of a geometry, dropping stray lines and points."""
    if isinstance(geom, Polygon):
        parts = [geom]
    elif isinstance(geom, (MultiPolygon, GeometryCollection)):
        parts = [p for g in geom for p in _polygons_only(g)]
    else:
        parts = []
    return [p for p in parts if not p.empty and p.area > 0]


def repair(geom):
    """Fix a self-crossing outline. Returns a MultiPolygon."""
    if not geom.valid:
        try:
            geom = geom.make_valid()
        except Exception:
            # Older GEOS without make_valid; buffer(0) is the classic repair.
            geom = geom.buffer(0)
    parts = _polygons_only(geom)
    if not parts:
        raise ValueError('The outline has no area. Add at least three separate corners.')
    return MultiPolygon(parts, srid=geom.srid)


def clip_to_city(geom, city):
    """
    The part of geom inside city, as a MultiPolygon.

    city None means the boundaries aren't loaded. Then nothing is clipped,
    matching the map, which also stops checking when it has no outlines.
    """
    geom = repair(geom)
    if city is None:
        return geom
    if not city.valid:
        city = repair(city)

    clipped = _polygons_only(geom.intersection(city))
    if not clipped:
        raise OutsideCity('The outlined area is entirely outside Talisay City.')
    result = MultiPolygon(clipped, srid=geom.srid)

    # A sliver left over from an outline drawn almost entirely over the sea
    # or a neighbouring city is a mis-tap, not a hazard zone. Publishing it
    # would notify a barangay about an area too small to see on the map.
    if result.area < geom.area * MIN_INSIDE_SHARE:
        raise OutsideCity(
            'Almost all of the outlined area is outside Talisay City. '
            'Draw it over the affected barangays.'
        )
    return result


def main_barangay(geom, barangays):
    """The barangay that holds the largest share of the zone, or None."""
    best, best_area = None, 0.0
    for b in barangays:
        if b.boundary is None:
            continue
        try:
            area = geom.intersection(b.boundary).area
        except Exception:
            continue  # a malformed boundary shouldn't block the publish
        if area > best_area:
            best, best_area = b, area
    return best


def overlap_shares(geometry, zone_ids):
    """
    For each saved zone in zone_ids, the share (0-1) of `geometry` it
    covers, measured on the spheroid by PostGIS. {zone_id: share}.

    Used to tell a second alert for the same event (most of the new drawing
    is already covered) from a neighbouring zone that just touches it.
    """
    from django.db import connection, transaction

    if not zone_ids:
        return {}
    try:
        # Savepoint: a failed query here must not break the caller's transaction
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                """
                WITH g AS (SELECT ST_MakeValid(ST_GeomFromEWKB(%s)) AS geom)
                SELECT z.hzzn_id,
                       ST_Area(ST_Intersection(ST_MakeValid(z.hzzn_polygon), g.geom)::geography)
                       / NULLIF(ST_Area(g.geom::geography), 0)
                FROM hazard_zone z, g
                WHERE z.hzzn_id = ANY(%s::uuid[])
                """,
                [bytes(geometry.ewkb), [str(i) for i in zone_ids]],
            )
            return {row[0]: min(float(row[1] or 0), 1.0) for row in cursor.fetchall()}
    except Exception:
        # Can't measure: treat every overlap as a full one, so the officer
        # is still asked rather than silently double-alerting.
        return {i: 1.0 for i in zone_ids}


# ---------- Cordon ----------
#
# A cordon is the safety ring kept clear around a hazard, mostly a fire: the
# burning block is the hazard, the cordon is where people are told to leave.
# It is stored as a width in meters on the zone (HazardZone.cordon_m), never
# folded into the drawn polygon, so the map can show the block at the
# published severity and the ring one level below it.

CORDON_MIN_M = 10
CORDON_MAX_M = 100

# Meters in one degree of latitude. Only used when PostGIS can't buffer.
_M_PER_DEG = 111_320


def _buffer_in_db(geometry, meters):
    """The geometry grown by `meters`, measured on the spheroid by PostGIS."""
    from django.contrib.gis.geos import GEOSGeometry
    from django.db import connection, transaction

    # Savepoint: a failed query must not break the caller's transaction
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            'SELECT ST_AsEWKB(ST_Buffer(ST_MakeValid(ST_GeomFromEWKB(%s))::geography, %s)::geometry)',
            [bytes(geometry.ewkb), float(meters)],
        )
        grown = GEOSGeometry(memoryview(bytes(cursor.fetchone()[0])))
    grown.srid = geometry.srid or 4326
    return grown


def _buffer_planar(geometry, meters):
    """
    Fallback when the database can't answer. A degree of longitude is
    shorter than a degree of latitude away from the equator, so the buffer
    uses the longitude scale: that errs on the side of a slightly wider
    cordon in latitude, which over-alerts rather than missing anyone.
    """
    import math

    lat = geometry.centroid.y
    degrees = meters / (_M_PER_DEG * max(math.cos(math.radians(lat)), 0.1))
    return geometry.buffer(degrees)


def with_cordon(geometry, cordon_m, city=None):
    """
    The area a zone reaches once its cordon is included: `geometry` grown by
    `cordon_m` meters, cut at the city boundary, as a MultiPolygon.

    Returns `geometry` unchanged when there is no cordon. `city` is the
    union of barangay boundaries; pass it when it is already at hand, or
    leave it None to look it up. The block itself is always inside the
    result, so the cut can never leave nothing.
    """
    if not cordon_m or geometry is None:
        return geometry
    try:
        grown = _buffer_in_db(geometry, cordon_m)
    except Exception:
        grown = _buffer_planar(geometry, cordon_m)

    if city is None:
        city = city_outline()
    try:
        return clip_to_city(grown, city)
    except ValueError:
        # Can't cut it (a bad boundary): an uncut cordon still alerts
        # everyone it should, plus perhaps a neighbour, which is the safer
        # mistake.
        return repair(grown)


def cordon_ring(geometry, reach):
    """
    The cordon on its own: `reach` (from with_cordon) less the hazard, as a
    MultiPolygon, or None when the zone has no cordon.

    The map hatches this ring and leaves the hazard to its own shading, so
    the place where it is happening and the place people are told to keep
    clear of never look alike. Routing still uses the whole of `reach`;
    this shape is for drawing only.
    """
    if geometry is None or reach is None or reach is geometry:
        return None
    try:
        parts = _polygons_only(repair(reach).difference(repair(geometry)))
    except Exception:
        return None
    if not parts:
        return None
    return MultiPolygon(parts, srid=reach.srid or geometry.srid or 4326)


def overlapping_puroks(geometry):
    """
    The puroks a zone's area overlaps, for its history record when resolved:
    the zone counts once in each. A purok that only shares a border with it
    doesn't count.
    """
    from apps.barangays.models import Purok
    return Purok.objects.filter(boundary__intersects=geometry).exclude(boundary__touches=geometry)
