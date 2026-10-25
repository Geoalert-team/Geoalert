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

from apps.barangays.aliases import ALIASES, canonical, match_barangay
from apps.barangays.purok_estimate import norm_name

LABELS = {'PUROK': 'purok', 'PRK': 'purok', 'PURK': 'purok', 'SITIO': 'sitio'}
BARANGAY_WORDS = {'BRGY', 'BRGY.', 'BARANGAY'}
CITY_WORDS = {'TALISAY', 'CITY', 'CEBU'}
NOT_AREA_FIRST = {'BLK', 'BLOCK', 'LOT', 'PHASE', 'CLUSTER'}
STREET_LAST = {'ST', 'ST.', 'AVE', 'AVE.', 'RD', 'RD.', 'DRIVE', 'HIGHWAY'}
UPPER_LOWER = {'UPPER', 'LOWER'}


def _words(part):
    return part.split()


def _strip_barangay_word(part):
    words = _words(part)
    if len(words) > 1 and words[0].upper() in BARANGAY_WORDS:
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
    """(barangay name, leftover text) when this part names a barangay, else None."""
    if canonical(part) in by_key:
        return by_key[canonical(part)], ''
    words = _words(part)
    if len(words) > 1 and words[0].upper() in UPPER_LOWER and canonical(' '.join(words[1:])) in by_key:
        return by_key[canonical(' '.join(words[1:]))], ''
    for spelling in spellings:
        if part.lower().endswith(' ' + spelling.lower()) and canonical(spelling) in by_key:
            return by_key[canonical(spelling)], part[:-len(spelling)].strip()
    return None


def _find_barangay(parts, by_key, spellings):
    """
    (index of the barangay part, barangay name, leftover text of that part) or
    None. Part by part from the end, so "San Roque, Upper Linao" is in Linao:
    the last part naming a barangay in any form wins.
    """
    for i in range(len(parts) - 1, -1, -1):
        found = _barangay_in(parts[i], by_key, spellings)
        if found:
            return (i, *found)
    return None


def _candidate(part):
    """(label, place) for a part that may be an area, or None for streets, lots and the like."""
    words = _words(part)
    if not words:
        return None
    first, last = words[0].upper().rstrip('.'), words[-1].upper()
    if part.upper() == 'SRP' or first in NOT_AREA_FIRST or first.isdigit():
        return None
    if last in STREET_LAST or last.endswith('ROAD'):
        return None
    label = LABELS.get(first, '')
    place = ' '.join(words[1:]) if label else part
    return (label, place) if place else None


def split_address(text, barangay_names):
    """
    (barangay, [(label, place)]): the barangay as spelled in barangay_names,
    or None, and the candidate places before it in address order.
    """
    parts = [_strip_barangay_word(p.strip()) for p in text.split(',')]
    parts = [p for p in parts if p and not _is_city(p)]
    by_key = {}
    for name in barangay_names:
        by_key.setdefault(canonical(name), name)

    found = _find_barangay(parts, by_key, _spellings(barangay_names))
    if found:
        index, barangay, leftover = found
        before = parts[:index] + ([leftover] if leftover else [])
    else:
        barangay, before = None, parts
    return barangay, [c for c in (_candidate(p) for p in before) if c]


def find_purok(candidates, purok_names, variants):
    """The purok one of the candidates names, Purok-labelled ones first, or None."""
    by_key = {norm_name(n): n for n in purok_names}
    ordered = [c for c in candidates if c[0] == 'purok'] + [c for c in candidates if c[0] != 'purok']
    for _, place in ordered:
        key = norm_name(place)
        if key in by_key:
            return by_key[key]
        if variants.get(key) in purok_names:
            return variants[key]
    return None


def load_variants(path):
    """{canonical barangay: {normalised other spelling: purok name}} from name_variants.csv."""
    variants = {}
    with open(path, encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh):
            variants.setdefault(canonical(row['barangay']), {})[norm_name(row['variant'])] = row['name']
    return variants


def link_address(text, barangays, puroks_by_barangay, variants):
    """(barangay object or None, purok name or None) for one BFP address."""
    name, candidates = split_address(text, [b.name for b in barangays])
    if name is None:
        return None, None
    barangay = match_barangay(name, barangays)
    purok = find_purok(candidates, puroks_by_barangay.get(barangay.id, []),
                       variants.get(canonical(barangay.name), {}))
    return barangay, purok
