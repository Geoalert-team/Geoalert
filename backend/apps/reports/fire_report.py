"""
What a fire report must say before DRRMO sees it.

A fire report is when and where: the BFP fire log's columns A-F. When it
started, a pin inside the barangay, and the purok, or the name the reporter
typed when theirs is not on the list. Property type, casualties, damage,
structures and alarm level are DRRMO's, entered when the fire is closed.

A plain function so it tests without the database; the create serializer
does the lookups.
"""
from datetime import timedelta

# A phone clock a few minutes fast is not a start time in the future
CLOCK_SKEW = timedelta(minutes=5)
# The PSA barangay lines are approximate; a pin about 110 m over still counts
PIN_TOLERANCE_DEG = 0.001


def fire_report_errors(attrs, barangay, has_puroks, now):
    """{field: message} for what is missing or wrong, or {} when the report is fine."""
    errors = {}

    started = attrs.get('started_at')
    if started is None:
        errors['started_at'] = 'Say when the fire started.'
    elif started > now + CLOCK_SKEW:
        errors['started_at'] = "The start time can't be in the future."

    location = attrs.get('location')
    if location is None:
        errors['location'] = 'Drop a pin where the fire is.'
    elif barangay.boundary is not None and not barangay.boundary.buffer(PIN_TOLERANCE_DEG).contains(location):
        errors['location'] = f'The pin is outside Barangay {barangay.name}.'

    purok, other = attrs.get('purok'), (attrs.get('purok_other') or '').strip()
    if purok is not None and purok.barangay_id != barangay.id:
        errors['purok'] = f'That purok is not in Barangay {barangay.name}.'
    elif purok is not None and other:
        errors['purok'] = 'Choose a purok from the list or type one, not both.'
    elif purok is None and not other and has_puroks:
        errors['purok'] = "Choose the purok or sitio, or pick 'Not on the list' and type its name."

    return errors
