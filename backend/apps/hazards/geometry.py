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
    return MultiPolygon(clipped, srid=geom.srid)


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
