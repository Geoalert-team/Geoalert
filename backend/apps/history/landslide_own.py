"""
The landslide model's own data (the January job's floor, held-back season,
results and training rows), as flood_own has them for flood.

- The floor to try: at least OWN_MIN_SPOTS located spots in
  OWN_MIN_BARANGAYS barangays.
- The test: the newest wet season (1 June to 31 December of last year, as
  flood_own.season_split splits it), at least HELD_MIN spots, is held back.
  With no spot before it to train on, nothing is trained: a fit without
  GeoAlert's rows must never carry the GeoAlert basis.
- own_rows: the spots before that season as slides, each with three "no"
  points by the outside table's rule, in the Talisay fold with weight
  OWN_WEIGHT, for landslide_run.run(mode='own').

The job (model_job.landslide_attempt) decides whether the fit goes live; the
sentences it saves are here. A spot is {'id', 'when' (ISO, Manila), 'lon',
'lat', 'purok_id', 'barangay'}. Plain functions, no database; the rows never
carry a coordinate.
"""
import numpy as np

from apps.history import flood_own

# landslide_training_table and landslide_features are imported in own_rows only: the readiness panel, a public
# request, imports this module

OWN_MIN_SPOTS = 30       # located landslide spots (with a map point) to try own data
OWN_MIN_BARANGAYS = 3    # in at least this many barangays
HELD_MIN = 5             # new spots in the held-back season needed to test
OWN_WEIGHT = 10          # an own slide, and each of its "no" points, counts this many times in the fit and the cut-offs
OWN_FOLD = 'talisay'     # landslide_run.OWN_FOLD: the own rows' event, fold and region

LANDSLIDE_FLOOR = '{n} of 30 located landslide spots, {b} of 3 barangays'
LANDSLIDE_HELD = 'Too few new spots to test ({n} of 5); tries again next January'
LANDSLIDE_NO_TRAINING = 'No located spots before the newest season to train on; tries again next January'  # R43
LANDSLIDE_WORSE = ("Fewer of the {season} wet season's spots in Red or Orange than the map in use "
                   '({new} vs {live})')
LANDSLIDE_SWITCHED = 'Passed all four checks; {hits} of {n} held-back spots in Red or Orange'


def floor(spots: list) -> dict:
    """{n, barangays, enough}: whether there are enough spots, in enough barangays, to try."""
    return flood_own.floor(spots, OWN_MIN_SPOTS, OWN_MIN_BARANGAYS)


def own_rows(spots: list, features_at, seed: int = 0, *, on_ground) -> dict:
    """
    GeoAlert's own training rows, a table like landslide_training_table's
    (TABLE_COLUMNS) plus 'weight': each spot a slide (label 1), with three
    "no" points (label 0) drawn uniformly within 2 km of the spots and at
    least 60 m from every spot (event_no_points, the outside table's
    sample_no_points in local metres; all the spots are one event, seed
    `seed`). `features_at(points) -> {column: values}` reads every model
    input and the NOAH class at (lon, lat) points (Talisay's saved clue
    grids; NaN off them). As in the outside table, a row with a missing
    terrain clue (ruling R20: a point off the clue grids among them) or one
    not on ground (`on_ground(points) -> bool array`, required: the sea,
    ruling R21) is left out. A spot left out takes no share of the "no"
    points: they are drawn again around the kept spots only (final review
    m1), so the rows are those the kept spots give alone. Every row is in the
    Talisay fold with weight OWN_WEIGHT: the "no" points too, so the own rows
    keep the outside rows' 1-to-3 balance. No coordinate is kept.
    """
    from apps.history.landslide_features import FEATURE_COLUMNS, TERRAIN_COLUMNS
    from apps.history.landslide_training_table import event_no_points

    def read(points):
        values = {c: np.asarray(v, float) for c, v in features_at(points).items()}
        keep = np.ones(len(points), bool)
        for c in TERRAIN_COLUMNS:
            keep &= np.isfinite(values[c])
        if len(points):
            keep &= np.asarray(on_ground(points), bool)
        return values, keep

    slides = np.array([[float(s['lon']), float(s['lat'])] for s in spots], float).reshape(-1, 2)
    no = event_no_points(slides, seed=seed)
    values, keep = read(np.concatenate([slides, no]))
    gone = ~keep[:len(slides)]
    if gone.any():  # the clues are read once when every spot is kept
        slides = slides[~gone]
        no = event_no_points(slides, seed=seed)
        no_values, no_keep = read(no)
        values = {c: np.r_[values[c][:len(gone)][~gone], no_values[c]] for c in values}
        keep = np.r_[np.ones(len(slides), bool), no_keep]
    label = np.r_[np.ones(len(slides), int), np.zeros(len(no), int)]
    n = int(keep.sum())
    rows = {c: np.full(n, OWN_FOLD) for c in ('event', 'fold', 'region')}  # text, as read_table gives it
    rows['label'] = label[keep]
    rows.update({c: values[c][keep] for c in FEATURE_COLUMNS + ('noah_class',)})
    rows['weight'] = np.full(n, float(OWN_WEIGHT))
    return rows
