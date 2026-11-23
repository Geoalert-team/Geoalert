"""
A fire model file for tests: the shape train_fire_model writes, for chosen
puroks and chances, put where apps.history.fire_purok reads it.
"""
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from apps.barangays.models import Purok
from apps.history import fire_purok

CUTOFFS = {'orange': 0.02, 'red': 0.05, 'red_reason': None}
REPORT = {'version': 'xgboost@0123456789ab', 'credit': 'Adapted from the City of Pittsburgh Bureau of Fire / '
          'Carnegie Mellon Metro21 fire risk model (github.com/CityofPittsburgh/fire_risk_analysis, MIT License, '
          '© 2017 mmadaio)', 'candidates': [], 'verdict': {'adopted': True, 'reasons': ['test']},
          'caveat': 'test caveat'}


def level_of(p):
    return 'Red' if p >= CUTOFFS['red'] else 'Orange' if p >= CUTOFFS['orange'] else 'Green'


def model_document(chances, limited=(), outlines_version=None):
    """
    chances: {purok: p for every month, or a list of 12 p}. limited: puroks
    flagged "Limited data". Trained 2023-01 to 2026-10.
    """
    areas = {}
    for purok, p in chances.items():
        months = p if isinstance(p, list) else [p] * 12
        areas[str(purok.id)] = {'barangay_id': purok.barangay_id, 'limited_data': purok in limited,
                                'months': [{'p': v, 'level': level_of(v), 'low': v / 2, 'high': min(v * 1.5, 0.99)}
                                           for v in months]}
    return {'version': REPORT['version'], 'credit': REPORT['credit'],
            'model': {'family': 'xgboost', 'settings': {'label': 'pittsburgh'}}, 'calibration': {'a': 0, 'b': 1},
            'cutoffs': CUTOFFS, 'trained': {'start': '2023-01', 'end': '2026-10', 'fires': 200, 'unplaced': []},
            'outlines_version': outlines_version or Purok.outlines_version(), 'areas': areas}


@contextmanager
def model_files(chances=None, limited=(), report=True, outlines_version=None):
    """
    The fire model files in a temporary folder, read by fire_purok while the
    block runs; chances=None means no model file at all (not trained yet).
    """
    with tempfile.TemporaryDirectory() as d:
        model_path, report_path = Path(d) / 'fire_purok_model.json', Path(d) / 'fire_purok_report.json'
        if chances is not None:
            model_path.write_text(json.dumps(model_document(chances, limited, outlines_version)), encoding='utf-8')
            if report:
                report_path.write_text(json.dumps(REPORT), encoding='utf-8')
        with mock.patch.object(fire_purok, 'MODEL_FILE', model_path), \
                mock.patch.object(fire_purok, 'REPORT_FILE', report_path):
            fire_purok.clear_cache()
            try:
                yield model_path
            finally:
                fire_purok.clear_cache()
