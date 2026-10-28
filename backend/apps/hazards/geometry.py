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


def overlapping_puroks(geometry):
    """
    The puroks a zone's area overlaps, for its history record when resolved:
    the zone counts once in each. A purok that only shares a border with it
    doesn't count, nor does a sitio drawn around puroks: the zone counts in
    those puroks instead, not twice.
    """
    from apps.barangays.models import Purok
    sitios = Purok.member_counts()
    found = Purok.objects.filter(boundary__intersects=geometry).exclude(boundary__touches=geometry)
    return found.exclude(pk__in=[p.pk for p in found if (p.barangay_id, p.name) in sitios])
