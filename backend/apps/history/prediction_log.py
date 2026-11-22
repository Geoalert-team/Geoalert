"""
The prediction log: the chances the public site showed, kept so they can be
scored later against what happened.

Until 2026-11-22 it held flood's, landslide's and fire's barangay chances in
hazard_prediction_log (migration 0008). Those models were removed
(docs/design/specs/2026-11-22-fire-purok-model-design.md, Part A). The old
rows stay, unchanged; the table's trigger forbids changing or removing them,
and nothing writes to it any more.

The fire model's purok log (plan docs/design/plans/2026-11-22-fire-purok-model.md,
Task B6) will be written from here. Until it is built, nothing is logged.
"""


def write_month_rows(today) -> int:
    """This month's logged figures, written once a day. Nothing is logged until the fire purok log exists: 0."""
    return 0
