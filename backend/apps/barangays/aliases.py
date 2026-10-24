"""
Other spellings of Talisay's barangay names.

The PSA boundary file, the seed data, the fire log and the Barangay Hall all
spell some names differently (Tabunoc/Tabunok, Cadulawan/Candulawan,
Camp IV/Camp 4). Both boundary loaders resolve names through this table.
"""

# Name in the PSA boundary file -> other spellings the team may already have
ALIASES = {
    'Tabunoc': ['Tabunok'],
    'Cadulawan': ['Candulawan'],
    'Camp IV': ['Camp 4', 'Camp Four'],
    'Lawaan I': ['Lawaan 1'],
    'Lawaan II': ['Lawaan 2'],
    'Lawaan III': ['Lawaan 3'],
    'Poblacion': ['Poblacion (Talisay)'],
    'Tangke': ['Tanke'],
}

_GROUP = {}
for _name, _others in ALIASES.items():
    for _n in [_name, *_others]:
        _GROUP[_n.lower()] = _name.lower()


def canonical(name):
    """One key per barangay, whatever the spelling."""
    key = ' '.join(name.split()).lower()
    return _GROUP.get(key, key)


def match_barangay(name, barangays):
    """
    The barangay called `name` under any spelling. When two rows match (the
    shared database has an outline-less "Candulawan" next to the real
    "Cadulawan"), the one with an outline wins.
    """
    key = canonical(name)
    hits = [b for b in barangays if canonical(b.name) == key]
    hits.sort(key=lambda b: b.boundary is None)
    return hits[0] if hits else None
