"""
What a report must say before DRRMO sees it.

Every report is when and where: the BFP fire log's columns A-F, asked of
floods and landslides as well as fires. When it started, and the puroks it
is in, picked by the reporter from the barangay's list. A fire's reporter
doesn't place a pin: the map shows one at each purok's centre, and the
report's location is set from the first. A flood or landslide may still
carry a pin of its own, which wins; without one it is placed the same way.
Property type, casualties, damage, structures and alarm level are DRRMO's,
entered when the fire is closed.

Plain functions so they test without the database; the create serializer
does the lookups.
"""
from datetime import timedelta

# A phone clock a few minutes fast is not a start time in the future
CLOCK_SKEW = timedelta(minutes=5)
MAX_PUROKS = 10


def report_errors(attrs, barangay, has_puroks, now, noun='hazard'):
    """
    {field: message} for what is missing or wrong, or {} when the report is
    fine. noun names the hazard in the messages ("Say when the flood started.").
    """
    errors = {}

    started = attrs.get('started_at')
    if started is None:
        errors['started_at'] = f'Say when the {noun} started.'
    elif started > now + CLOCK_SKEW:
        errors['started_at'] = "The start time can't be in the future."

    puroks = attrs.get('puroks') or []
    if any(p.barangay_id != barangay.id for p in puroks):
        errors['puroks'] = f'That purok is not in Barangay {barangay.name}.'
    elif len(puroks) > MAX_PUROKS:
        errors['puroks'] = f'Choose at most {MAX_PUROKS} puroks.'
    elif not puroks and has_puroks:
        errors['puroks'] = f'Choose the purok or sitio where the {noun} is.'

    return errors


def _centre(geometry):
    """A point inside the shape, or None. Not the centroid, which can fall outside."""
    return geometry.point_on_surface if geometry is not None else None


def prepare_report(attrs, now, has_puroks):
    """
    (attrs, errors) for a report about to be saved. has_puroks(barangay)
    says whether the barangay has any puroks to choose from.

    No hazard type: there is nothing to ask when or where of, so those
    fields are dropped. Otherwise the puroks are de-duplicated and checked,
    and the location is set from the first purok, or the barangay when it
    has none - always for a fire, and for other hazards when no pin was sent.
    """
    hazard = attrs.get('hazard_type')
    if hazard is None:
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

    noun = hazard.name.lower()
    errors = report_errors(attrs, barangay, has_puroks(barangay), now, noun)
    if not errors and (noun == 'fire' or attrs.get('location') is None):
        attrs['location'] = _centre(puroks[0].boundary) if puroks else _centre(barangay.boundary)
    return attrs, errors
