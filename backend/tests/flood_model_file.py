"""
A flood model file for tests: the shape train_flood_model writes, for chosen
puroks and levels, put where apps.history.flood_purok reads it.
"""
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from apps.barangays.models import Purok
from apps.history import flood_purok

VERSION = 'logistic_regression@0123456789ab'
REPORT = {'version': VERSION, 'source': 'model', 'candidates': [], 'acceptance': {'adopted': True, 'gates': [],
          'reasons': []}, 'limits': ['test limit'], 'credits': ['test credit'],
          'basis': 'From a machine-learning model (test).', 'built_at': '2026-11-01T00:00:00+08:00',
          'survey_spots': 105}


def model_document(levels, uncertain=(), estimated=(), outlines_version=None, source='model'):
    """levels: {purok: 'Red' | 'Orange' | 'Green' | None (not assessed)}."""
    areas = {}
    for purok, level in levels.items():
        areas[str(purok.id)] = {'barangay_id': purok.barangay_id, 'level': level,
                                'score': {'Red': .9, 'Orange': .6, 'Green': .2}.get(level),
                                'uncertain': purok in uncertain,
                                'not_assessed_reason': None if level else 'Outside the surveyed floodplain',
                                'estimated_outline': purok in estimated, 'buildings': 10}
    version = VERSION if source == 'model' else 'noah_fallback@0123456789ab'
    return {'version': version, 'source': source, 'chosen': 'logistic_regression',
            'built_at': '2026-11-01T00:00:00+08:00', 'outlines_version': outlines_version or Purok.outlines_version(),
            'cutoffs': {'red': .8, 'orange': .5, 'red_recall': .5, 'orange_recall': .9, 'target_reached': True},
            'domain': {'buffer_m': 300, 'rule': 'test'}, 'inputs': {'columns': []}, 'areas': areas}


@contextmanager
def flood_model_files(levels=None, report=True, outlines_version=None, source='model', **kw):
    """The flood model files in a temporary folder while the block runs; levels=None means no model file."""
    with tempfile.TemporaryDirectory() as d:
        model_path, report_path = Path(d) / 'flood_purok_model.json', Path(d) / 'flood_purok_report.json'
        if levels is not None:
            doc = model_document(levels, outlines_version=outlines_version, source=source, **kw)
            model_path.write_text(json.dumps(doc), encoding='utf-8')
            if report:
                report_path.write_text(json.dumps({**REPORT, 'version': doc['version'], 'source': source}),
                                       encoding='utf-8')
        with mock.patch.object(flood_purok, 'MODEL_FILE', model_path), \
                mock.patch.object(flood_purok, 'REPORT_FILE', report_path):
            flood_purok.clear_cache()
            try:
                yield model_path
            finally:
                flood_purok.clear_cache()
