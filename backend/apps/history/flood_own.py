"""
Flood's own-data mode (automatic retraining, spec 6.3): once GeoAlert has
enough located flood spots of its own, the yearly job trains the flood
susceptibility recipe on them instead of the 2017 Mananga survey.

- The floor to try: at least OWN_MIN_SPOTS spots in OWN_MIN_BARANGAYS
  barangays.
- The test: the newest wet season (1 June to 31 December of last year) is held
  back; the model trains on the spots before it.
- The folds: the training spots' barangays, spread over at most MAX_FOLDS
  folds, the largest first, each to the fold with the fewest spots so far.
- train_own runs flood_run.run in mode 'own'. The job (model_job) decides
  whether the fit goes live; the sentences it saves are here.

A spot is {'id', 'when' (ISO, Manila), 'lon', 'lat', 'purok_id', 'barangay'};
a training spot also carries 'positive': True and 'inputs'. Plain functions,
no database.
"""
from datetime import date, datetime, timedelta, timezone

import numpy as np

# flood_run (scikit-learn) is imported in train_own only: the readiness panel, a public request, imports this module

OWN_MIN_SPOTS = 100
OWN_MIN_BARANGAYS = 5
HELD_MIN = 10
MAX_FOLDS = 5

FLOOD_FLOOR = '{n} of 100 located flood spots, {b} of 5 barangays'
FLOOD_HELD = 'Too few new spots to test ({n} of 10); tries again next January'
FLOOD_FOLDS = 'Too few barangays before the {season} wet season to test the model'
FLOOD_WORSE = "Fewer of the {season} wet season's spots in Red or Orange than the map in use ({new} vs {live})"
FLOOD_SWITCHED = 'Passed all four checks; {hits} of {n} held-back spots in Red or Orange'

FLAGGED = ('Red', 'Orange')
MANILA = timezone(timedelta(hours=8))  # Manila keeps UTC+8 all year


def _barangay_counts(spots: list) -> dict:
    counts = {}
    for s in spots:
        name = s.get('barangay')
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts


def floor(spots: list, min_spots: int | None = None, min_barangays: int | None = None) -> dict:
    """{n, barangays, enough}: whether there are enough spots, in enough barangays, to try (the floor defaults to flood's; landslide passes its own)."""
    min_spots = OWN_MIN_SPOTS if min_spots is None else min_spots
    min_barangays = OWN_MIN_BARANGAYS if min_barangays is None else min_barangays
    n, barangays = len(spots), len(_barangay_counts(spots))
    return {'n': n, 'barangays': barangays, 'enough': n >= min_spots and barangays >= min_barangays}


def local_day(when: str) -> date:
    """A spot's date in Manila; a time with no offset is already Manila time."""
    moment = datetime.fromisoformat(when)
    return moment.date() if moment.tzinfo is None else moment.astimezone(MANILA).date()


def season_split(spots: list, today: date) -> tuple:
    """
    (train, held, season): season is last year; train is every spot before
    1 June of it, held is 1 June to 31 December of it. Later spots are in
    neither (they wait for next January).
    """
    season = today.year - 1
    start, end = date(season, 6, 1), date(season, 12, 31)
    train, held = [], []
    for s in spots:
        day = local_day(s['when'])
        if day < start:
            train.append(s)
        elif day <= end:
            held.append(s)
    return train, held, season


def own_folds(spots: list) -> dict:
    """
    {barangay: fold}: k = min(MAX_FOLDS, barangays) folds; the barangays by
    spot count (most first, then by name), each to the fold with the fewest
    spots so far, the lowest index on a tie. The same for any order of spots.
    """
    counts = _barangay_counts(spots)
    k = min(MAX_FOLDS, len(counts))
    sizes = [0] * k
    folds = {}
    for name in sorted(counts, key=lambda name: (-counts[name], name)):
        fold = min(range(k), key=lambda i: (sizes[i], i))
        folds[name] = fold
        sizes[fold] += counts[name]
    return folds


def compare(new_levels: list, live_levels: list) -> tuple:
    """(hits of the new map, hits of the live map): held-back spots in Red or Orange on each."""
    return (sum(1 for lv in new_levels if lv in FLAGGED), sum(1 for lv in live_levels if lv in FLAGGED))


def train_own(features, train_spots: list, held_spots: list, city, outside: dict, season: int, fingerprint: str,
              eosrs_flagged=None, reps: int = 1000, stability_reps: int = 200, log=print,
              outside_source: str | None = None) -> tuple:
    """
    (model JSON, report JSON) of the recipe trained on GeoAlert's own spots.
    `outside` is the live map's rows by purok id ({} when no flood model was
    live) and `outside_source` its source ('noah', 'model', 'geoalert'); the
    held-back spots reach the run only after its choice and cut-offs are
    fixed, as the survey's test points do.
    """
    from apps.history.flood_run import run

    flags = np.zeros(len(features.buildings['lon']), bool) if eosrs_flagged is None else eosrs_flagged

    def load_tests():
        held = [{**s, 'day': local_day(s['when']).isoformat()} for s in held_spots]
        return {'geoalert_points': held, 'eosrs_flagged': flags}

    model, report = run(features, train_spots, city, load_tests, log=log, fingerprint=fingerprint, reps=reps,
                        stability_reps=stability_reps, mode='own', folds=own_folds(train_spots), outside=outside,
                        outside_source=outside_source)
    report['temporal_test'] = {'season': season, **report['temporal_test']}
    return model, report
