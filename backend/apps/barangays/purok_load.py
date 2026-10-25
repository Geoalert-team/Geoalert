"""
Checks and bookkeeping for manage.py load_puroks.

Plain functions so they test without the database; the command does the
lookups and the one transaction.
"""
import json

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon

from apps.barangays.models import Purok
from apps.barangays.purok_estimate import norm_name

KEEP_INSIDE = 0.9  # a shape at least this much inside its barangay is trimmed, anything less refused


def read_features(collection, default_source):
    """
    (rows, problems) from a GeoJSON FeatureCollection. Every problem is
    listed, not just the first, so a traced file is fixed in one pass.
    """
    rows, problems = [], []
    for n, f in enumerate(collection.get('features', []), 1):
        p = f.get('properties') or {}
        label = p.get('name') or f'feature {n}'
        missing = [k for k in ('barangay', 'name', 'kind') if not str(p.get(k) or '').strip()]
        if missing:
            problems.append(f'{label}: missing {", ".join(missing)}')
            continue
        if p['kind'] not in Purok.KINDS:
            problems.append(f'{label}: kind "{p["kind"]}" is not one of {", ".join(Purok.KINDS)}')
            continue
        source = p.get('source') or default_source
        if source not in Purok.SOURCES:
            problems.append(f'{label}: source "{source}" is not one of {", ".join(Purok.SOURCES)}')
            continue
        try:
            geom = GEOSGeometry(json.dumps(f['geometry']), srid=4326)
        except Exception as exc:
            problems.append(f'{label}: unreadable shape ({exc})')
            continue
        if geom.geom_type == 'Polygon':
            geom = MultiPolygon(geom, srid=4326)
        if geom.geom_type != 'MultiPolygon':
            problems.append(f'{label}: shape is a {geom.geom_type}, not an area')
            continue
        rows.append({
            'barangay': p['barangay'].strip(),
            'name': p['name'].strip(),
            'kind': p['kind'],
            'parent': (p.get('parent') or '').strip(),
            'source': source,
            # Only researched points have a confidence; official lines just are
            'confidence': '' if source == 'official' else (p.get('confidence') or ''),
            'boundary': geom,
        })
    return rows, problems


def fit_to_barangay(shape, boundary):
    """
    (shape cut to the barangay, share that was inside). A small overhang is
    a tracing slip and is trimmed; a shape mostly outside is the wrong
    barangay, so it comes back as None.
    """
    shape = shape if shape.valid else shape.buffer(0)
    share = shape.intersection(boundary).area / shape.area if shape.area else 0.0
    if share < KEEP_INSIDE:
        return None, share
    inside = shape.intersection(boundary)
    if inside.geom_type == 'Polygon':
        inside = MultiPolygon(inside, srid=4326)
    elif inside.geom_type == 'GeometryCollection':
        inside = MultiPolygon(*[g for g in inside if g.geom_type == 'Polygon'], srid=4326)
    return inside, share


def overlap(a, b):
    """Shared area / combined area: 1 is the same shape, 0 no overlap."""
    union = a.union(b).area
    return a.intersection(b).area / union if union else 0.0


def compare(old_by_name, new_by_name):
    """How the outlines being replaced line up with the new ones, matched by name."""
    old = {norm_name(n): (n, g) for n, g in old_by_name.items()}
    matched, only_new, used = [], [], set()
    for name, geom in sorted(new_by_name.items()):
        key = norm_name(name)
        if key in old:
            matched.append((name, overlap(old[key][1], geom)))
            used.add(key)
        else:
            only_new.append(name)
    only_old = sorted(n for k, (n, _) in old.items() if k not in used)
    return {'matched': matched, 'only_estimated': only_old, 'only_new': only_new}


def plan_replace(existing, rows):
    """
    What loading `rows` does to the puroks already there, given as
    (id, barangay_id, name): a purok whose name matches one in the file
    (under norm_name, so a re-spelling still matches) is updated and keeps
    its id; the rest of the file is created; the rest of what was there is
    deleted. Keeping ids is what keeps fire history linked to its purok.
    """
    by_key = {}
    for pk, barangay_id, name in existing:
        by_key.setdefault((barangay_id, norm_name(name)), pk)
    plan = {'update': [], 'create': [], 'delete': []}
    kept = set()
    for row in rows:
        pk = by_key.get((row['barangay_id'], norm_name(row['name'])))
        if pk is None or pk in kept:
            plan['create'].append(row)
        else:
            kept.add(pk)
            plan['update'].append((pk, row))
    plan['delete'] = [pk for pk, _, _ in existing if pk not in kept]
    return plan


def replace(rows, store):
    """Replace the puroks of exactly the barangays that appear in the rows, keeping ids where names match."""
    plan = plan_replace(store.existing({r['barangay_id'] for r in rows}), rows)
    store.apply(plan)
    return plan
