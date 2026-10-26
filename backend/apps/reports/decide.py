"""
Deciding a fire report: approve it as a new fire, attach it to one nearby,
or reject it.

A fire report names its puroks; its pins are their centres (a point inside
each). An approved fire is a HazardZone whose geometry is a small circle
round each pin, used only to find the barangays to alert - the public map
shows the pins, not the circles. Its level is the highest level among the
puroks' fire history (apps/history/purok_levels.py); the officer doesn't
choose one.

Plain functions so they test without the database; the decide view does the
lookups, the alerts and the one transaction.
"""
from django.contrib.gis.geos import MultiPolygon
from django.utils import timezone


PIN_RADIUS_M = 25     # a burning block plus a little; only decides who is alerted
NEARBY_M = 500        # an active fire this close may be the same fire
METRIC_SRID = 32651   # UTM 51N, metres, covers Talisay


def report_pins(report):
    """Where a report's pins go: each purok's centre, else the report's own location."""
    puroks = list(report.puroks.all())
    if puroks:
        return [p.boundary.point_on_surface for p in puroks]
    return [report.location] if report.location is not None else []


def fire_geometry(points, radius_m=PIN_RADIUS_M):
    """A circle of radius_m metres round each point, as one MultiPolygon in SRID 4326."""
    circles = []
    for point in points:
        metric = point.transform(METRIC_SRID, clone=True)
        circles.append(metric.buffer(radius_m, 16))
    union = circles[0]
    for circle in circles[1:]:
        union = union.union(circle)
    union.srid = METRIC_SRID
    union.transform(4326)
    return union if isinstance(union, MultiPolygon) else MultiPolygon(union, srid=4326)


def is_nearby(geometry, points, metres=NEARBY_M):
    """Whether any of the points is within this many metres of the geometry."""
    shape = geometry.transform(METRIC_SRID, clone=True)
    return any(shape.distance(p.transform(METRIC_SRID, clone=True)) <= metres for p in points)


def decision_error(report):
    """Why this report can't be decided now, or None when it can."""
    if (getattr(report.hazard_type, 'name', '') or '').lower() != 'fire':
        return 'Only fire reports are decided here.'
    decided = report.status == 'Rejected' or (report.status == 'Validated' and report.hazard_zone_id)
    if not decided:
        return None  # Pending, or validated before this flow and never put on the map
    who = getattr(report.reviewed_by, 'full_name', None) or 'another officer'
    when = timezone.localtime(report.reviewed_at).strftime('%H:%M') if report.reviewed_at else ''
    return f'Already decided by {who} at {when}.' if when else f'Already decided by {who}.'
