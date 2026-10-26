"""
What a fire report must say before DRRMO sees it.

A fire report is when and where: the BFP fire log's columns A-F. When it
started, and the puroks it is in, picked by the reporter from the
barangay's list. The reporter doesn't place a pin: the map shows one at
each purok's centre, and the report's location is set from the first.
Property type, casualties, damage, structures and alarm level are DRRMO's,
entered when the fire is closed.

Plain functions so they test without the database; the create serializer
does the lookups.
"""
from datetime import timedelta

# A phone clock a few minutes fast is not a start time in the future
CLOCK_SKEW = timedelta(minutes=5)
MAX_PUROKS = 10


def fire_report_errors(attrs, barangay, has_puroks, now):
    """{field: message} for what is missing or wrong, or {} when the report is fine."""
    errors = {}

    started = attrs.get('started_at')
    if started is None:
        errors['started_at'] = 'Say when the fire started.'
    elif started > now + CLOCK_SKEW:
        errors['started_at'] = "The start time can't be in the future."

    puroks = attrs.get('puroks') or []
    if any(p.barangay_id != barangay.id for p in puroks):
        errors['puroks'] = f'That purok is not in Barangay {barangay.name}.'
    elif len(puroks) > MAX_PUROKS:
        errors['puroks'] = f'Choose at most {MAX_PUROKS} puroks.'
    elif not puroks and has_puroks:
        errors['puroks'] = 'Choose the purok or sitio where the fire is.'

    return errors


def _centre(geometry):
    """A point inside the shape, or None. Not the centroid, which can fall outside."""
    return geometry.point_on_surface if geometry is not None else None


def prepare_report(attrs, now, has_puroks):
    """
    (attrs, errors) for a report about to be saved. has_puroks(barangay)
    says whether the barangay has any puroks to choose from.

    Not a fire: the fire fields are dropped, whatever the client sent. A
    fire: the puroks are de-duplicated, checked, and the location is set
    from the first purok, or the barangay when it has none.
    """
    hazard = attrs.get('hazard_type')
    if hazard is None or hazard.name.lower() != 'fire':
        attrs.pop('started_at', None)
        attrs.pop('puroks', None)
        return attrs, {}

    barangay = attrs.get('barangay')
    if barangay is None:
        return attrs, {'barangay': 'Choose the barangay where this is happening.'}

    seen, puroks = set(), []
    for purok in attrs.get('puroks') or []:
        if purok.id not in seen:
            seen.add(purok.id)
            puroks.append(purok)
    attrs['puroks'] = puroks

    errors = fire_report_errors(attrs, barangay, has_puroks(barangay), now)
    if not errors:
        attrs['location'] = _centre(puroks[0].boundary) if puroks else _centre(barangay.boundary)
    return attrs, errors
