"""
Linking a BFP address to a barangay and a purok.

The fire log places a fire by a typed address, roughly "<place>[, <place>],
<barangay>, Talisay City, Cebu". The barangay is the last part that names
one under any spelling (apps/barangays/aliases.py): in "Purk Ilang-Ilang,
San Roque, Linao" the fire is in Linao and San Roque is a sitio there. The
parts before it are the candidate places; a purok is the first that names
one of that barangay's puroks, preferring parts the log labels "Purok".

Plain functions so they test without the database; the import command does
the lookups.
"""
import csv
import re
import unicodedata
from pathlib import Path

from apps.barangays.aliases import ALIASES, canonical, match_barangay
from apps.barangays.purok_estimate import ROMAN, STREET_SHARE, norm_name

LABELS = {'PUROK': 'purok', 'PRK': 'purok', 'PURK': 'purok', 'SITIO': 'sitio'}
BARANGAY_WORDS = {'BRGY', 'BRGY.', 'BARANGAY'}
CITY_WORDS = {'TALISAY', 'CITY', 'CEBU'}
NOT_AREA_FIRST = {'BLK', 'BLOCK', 'LOT', 'PHASE', 'CLUSTER'}
STREET_LAST = {'ST', 'ST.', 'AVE', 'AVE.', 'RD', 'RD.', 'DRIVE', 'HIGHWAY'}
UPPER_LOWER = {'UPPER', 'LOWER'}
# The short forms a street's last word is typed in, and the word they stand for
STREET_WORDS = {'st': 'street', 'st.': 'street', 'str': 'street', 'str.': 'street', 'rd': 'road', 'rd.': 'road',
                'ave': 'avenue', 'ave.': 'avenue', 'av': 'avenue', 'av.': 'avenue'}


def _words(part):
    return part.split()


def _drop_number(part):
    """ "100 Art Ville" is house 100 in Art Ville."""
    words = _words(part)
    if len(words) > 1 and words[0].isdigit():
        return ' '.join(words[1:])
    return part


def _strip_barangay_word(part):
    words = _words(part)
    # "Barangay Hall" is a place, not the barangay
    if len(words) > 1 and words[0].upper() in BARANGAY_WORDS and ' '.join(words[1:]).upper() != 'HALL':
        return ' '.join(words[1:])
    return part


def _is_city(part):
    return set(w.upper() for w in _words(part)) <= CITY_WORDS


def _spellings(barangay_names):
    """Every spelling we know of each barangay, longest first, for matching the end of a part."""
    names = set(barangay_names)
    for name, others in ALIASES.items():
        names.update([name, *others])
    return sorted(names, key=len, reverse=True)


def _barangay_in(part, by_key, spellings):
    """
    (barangay name, leftover text, place) when this part names a barangay,
    else None. "Upper Mohon" names Mohon and is also a sitio there, so it
    comes back as the place too.
    """
    if canonical(part) in by_key:
        return by_key[canonical(part)], '', ''
    words = _words(part)
    if len(words) > 1 and words[0].upper() in UPPER_LOWER and canonical(' '.join(words[1:])) in by_key:
        return by_key[canonical(' '.join(words[1:]))], '', part
    for spelling in spellings:
        if part.lower().endswith(' ' + spelling.lower()) and canonical(spelling) in by_key:
            return by_key[canonical(spelling)], part[:-len(spelling)].strip(), ''
    return None


def _find_barangay(parts, by_key, spellings):
    """
    (index of the barangay part, barangay name, leftover text of that part,
    place) or None. Part by part from the end, so "San Roque, Upper Linao" is
    in Linao: the last part naming a barangay in any form wins.
    """
    for i in range(len(parts) - 1, -1, -1):
        found = _barangay_in(parts[i], by_key, spellings)
        if found:
            return (i, *found)
    return None


def _is_street(part):
    words = _words(part)
    return bool(words) and (words[-1].upper() in STREET_LAST or words[-1].upper().endswith('ROAD'))


def _candidate(part):
    """(label, place) for a part that may be an area, or None for streets, lots and the like."""
    words = _words(part)
    if not words:
        return None
    first = words[0].upper().rstrip('.')
    if part.upper() == 'SRP' or first in NOT_AREA_FIRST or first.isdigit() or _is_street(part):
        return None
    label = LABELS.get(first, '')
    place = ' '.join(words[1:]) if label else part
    return (label, place) if place else None


def _parts_before(text, barangay_names):
    """(barangay or None, the parts before it): ',' and ';' both separate parts."""
    parts = [_drop_number(_strip_barangay_word(p.strip())) for p in text.replace(';', ',').split(',')]
    parts = [p for p in parts if p and not _is_city(p)]
    by_key = {}
    for name in barangay_names:
        by_key.setdefault(canonical(name), name)

    found = _find_barangay(parts, by_key, _spellings(barangay_names))
    if not found:
        return None, parts
    index, barangay, leftover, place = found
    return barangay, parts[:index] + [p for p in (leftover, place) if p]


def split_address(text, barangay_names):
    """
    (barangay, [(label, place)]): the barangay as spelled in barangay_names,
    or None, and the candidate places before it in address order.
    """
    barangay, before = _parts_before(text, barangay_names)
    return barangay, [c for c in (_candidate(p) for p in before) if c]


def street_parts(text, barangay_names):
    """The streets an address names before its barangay ("Nacario St."), house numbers dropped."""
    _, before = _parts_before(text, barangay_names)
    return [p for p in before if _is_street(p)]


def street_key(name):
    """A key for matching a street however its last word is typed: "Nacario St." and "Nacario Street" match."""
    words = _words(_drop_number(name))
    if words:
        words[-1] = STREET_WORDS.get(words[-1].lower(), words[-1])
    return norm_name(' '.join(words))


class PlaceKeys(dict):
    """
    {key: area name} for one barangay, and the rule each key came from:
    purok (another spelling), sitio (an unplaced purok's sitio), landmark or
    street. The first source to give a key keeps it.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rules = {}
        self.landmarks = []  # (words, area): for "Evergreen SRP" finding Cebu Evergreen Memorial Park

    def add(self, key, name, rule):
        if key and key not in self:
            self[key] = name
            self.rules[key] = rule


class LinkIndex(dict):
    """{canonical barangay: PlaceKeys}, the same shape load_variants gives, so find_purok reads either."""

    def keys_for(self, barangay_name):
        return self.setdefault(canonical(barangay_name), PlaceKeys())

    def add(self, barangay_name, key, name, rule):
        self.keys_for(barangay_name).add(key, name, rule)

    def rule(self, barangay_name, key):
        return self.get(canonical(barangay_name), PlaceKeys()).rules.get(key, 'purok')


# Words a typed landmark carries that the landmark's own name may not
LANDMARK_NOISE = {'srp', 'area', 'near', 'the', 'of'}


def _words_of(name):
    plain = ''.join(c for c in unicodedata.normalize('NFKD', name) if not unicodedata.combining(c))
    return {ROMAN.get(w, w) for w in re.findall(r'[a-z0-9]+', plain.lower())} - LANDMARK_NOISE


def _rule_of(keys, key):
    return getattr(keys, 'rules', {}).get(key, 'purok')


def match_place(candidates, purok_names, keys, own_words=frozenset()):
    """
    (area name, rule) for the first candidate that names one of purok_names,
    or (None, ''). Every candidate is tried as written (and under its other
    spellings) before any falls back to its sitio or a landmark, so "Purok
    Macopa, Kimba" is Kimba, which is written, not Macopa's sitio.

    own_words are the barangay's own name words, which a typed landmark may
    add and its map name leave out ("LAWAAN 1 NATIONAL HIGH SCHOOL" is
    Lawaan National High School).
    """
    by_key = {norm_name(n): n for n in purok_names}
    ordered = [c for c in candidates if c[0] == 'purok'] + [c for c in candidates if c[0] != 'purok']
    for _, place in ordered:
        key = norm_name(place)
        if key in by_key:
            return by_key[key], 'purok'
        if _rule_of(keys, key) == 'purok' and keys.get(key) in purok_names:
            return keys[key], 'purok'
    for _, place in ordered:
        key = norm_name(place)
        name = keys.get(key)
        if name is not None and name not in purok_names:
            # Another spelling of a purok nobody placed: that purok's sitio
            name = keys.get(norm_name(name))
        if name in purok_names and _rule_of(keys, key) in ('purok', 'sitio', 'landmark'):
            return name, (_rule_of(keys, key) if keys.get(key) == name else 'sitio')
        words = _words_of(place) - own_words
        hits = {area for landmark, area in getattr(keys, 'landmarks', []) if words and words <= landmark}
        if len(hits) == 1 and next(iter(hits)) in purok_names:
            return next(iter(hits)), 'landmark'
    return None, ''


def find_purok(candidates, purok_names, variants):
    """The purok one of the candidates names, Purok-labelled ones first, or None."""
    return match_place(candidates, purok_names, variants)[0]


def load_variants(path):
    """{canonical barangay: {normalised other spelling: purok name}} from name_variants.csv."""
    variants = {}
    with open(path, encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh):
            variants.setdefault(canonical(row['barangay']), {})[norm_name(row['variant'])] = row['name']
    return variants


def _read(path):
    if not path.exists():
        return []
    with open(path, encoding='utf-8', newline='') as fh:
        return list(csv.DictReader(fh))


def load_link_index(data_dir):
    """
    Every way an address can name an area, per barangay, from the purok data
    folder: other spellings (name_variants.csv), an unplaced purok's nearest
    placed sitio (purok_points.csv), and the landmarks and streets the build
    put in an area (place_areas.csv). A file that isn't there is skipped.
    """
    data_dir = Path(data_dir)
    index = LinkIndex()
    for row in _read(data_dir / 'name_variants.csv'):
        index.add(row['barangay'], norm_name(row['variant']), row['name'], 'purok')

    points = _read(data_dir / 'purok_points.csv')
    rows = {(canonical(r['barangay']), r['name']): r for r in points}
    for r in points:
        if str(r.get('lat') or '').strip():
            continue
        parent, seen = r['parent'], set()
        while parent and parent not in seen:
            seen.add(parent)
            up = rows.get((canonical(r['barangay']), parent))
            if up is None:
                break
            if str(up.get('lat') or '').strip():
                index.add(r['barangay'], norm_name(r['name']), parent, 'sitio')
                break
            parent = up['parent']

    for row in _read(data_dir / 'place_areas.csv'):
        if row['kind'] == 'landmark':
            index.add(row['barangay'], norm_name(row['place']), row['area'], 'landmark')
            index.keys_for(row['barangay']).landmarks.append((_words_of(row['place']), row['area']))
        elif row['kind'] == 'street' and float(row['share'] or 0) >= STREET_SHARE:
            index.add(row['barangay'], street_key(row['place']), row['area'], 'street')
    return index


def _in_barangay(text, barangay, candidates, puroks_by_barangay, index, names):
    purok_names = puroks_by_barangay.get(barangay.id, [])
    keys = index.get(canonical(barangay.name), {})
    purok, rule = match_place(candidates, purok_names, keys, own_words=_words_of(barangay.name))
    if purok is None:
        for street in street_parts(text, names):
            key = street_key(street)
            if _rule_of(keys, key) == 'street' and keys.get(key) in purok_names:
                return keys[key], 'street'
    return purok, rule


def _without_barangay(candidates, barangays, puroks_by_barangay, index):
    """The one barangay that has the most of the named places, with the area there; a tie places nothing."""
    scores = []
    for b in barangays:
        names, keys = puroks_by_barangay.get(b.id, []), index.get(canonical(b.name), {})
        hits = sum(1 for c in candidates if match_place([c], names, keys)[0])
        if hits:
            scores.append((hits, b))
    scores.sort(key=lambda s: -s[0])
    if not scores or (len(scores) > 1 and scores[0][0] == scores[1][0]):
        return None, None, ''
    barangay = scores[0][1]
    purok, rule = match_place(candidates, puroks_by_barangay.get(barangay.id, []),
                              index.get(canonical(barangay.name), {}))
    return barangay, purok, rule


def explain_link(text, barangays, puroks_by_barangay, index):
    """
    (barangay object or None, area name or None, rule) for one address. The
    rule says how it was found: purok (as written, or another spelling),
    sitio (a purok nobody placed, so its sitio), landmark or street; '' for
    no area.
    """
    names = [b.name for b in barangays]
    name, candidates = split_address(text, names)
    if name is None:
        return _without_barangay(candidates, barangays, puroks_by_barangay, index)
    barangay = match_barangay(name, barangays)
    purok, rule = _in_barangay(text, barangay, candidates, puroks_by_barangay, index, names)
    return barangay, purok, rule if purok else ''


def link_address(text, barangays, puroks_by_barangay, variants):
    """(barangay object or None, purok name or None) for one BFP address."""
    return explain_link(text, barangays, puroks_by_barangay, variants)[:2]
