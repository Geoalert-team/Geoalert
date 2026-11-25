"""
A landslide model file for tests: the shape train_landslide_model writes, for
chosen puroks and levels, put where apps.history.landslide_purok reads it.
"""
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from apps.barangays.models import Purok
from apps.history import landslide_purok

VERSION = 'neural_network@0123456789ab'
REPORT = {'version': VERSION, 'source': 'model', 'candidates': [], 'acceptance': {'adopted': True, 'gates': {},
          'reasons': []}, 'limits': ['test limit'], 'credits': ['test credit'],
          'built_at': '2026-11-01T00:00:00+08:00'}


def model_document(levels, uncertain=(), estimated=(), outlines_version=None, source='model'):
    """levels: {purok: 'Red' | 'Orange' | 'Green' | None (not assessed)}."""
    areas = {}
    for purok, level in levels.items():
        areas[str(purok.id)] = {'barangay_id': purok.barangay_id, 'level': level,
                                'score': {'Red': .9, 'Orange': .6, 'Green': .2}.get(level),
                                'uncertain': purok in uncertain,
                                'not_assessed_reason': None if level else 'No buildings or roads in this area',
                                'estimated_outline': purok in estimated, 'points': 10}
    version = VERSION if source == 'model' else 'noah_fallback@0123456789ab'
    return {'version': version, 'source': source, 'chosen': 'neural_network', 'training_set': 'ph',
            'built_at': '2026-11-01T00:00:00+08:00', 'outlines_version': outlines_version or Purok.outlines_version(),
            'cutoffs': {'red': .8, 'orange': .5}, 'clip_ranges': {}, 'inputs': {'columns': []}, 'areas': areas}


@contextmanager
def landslide_model_files(levels=None, report=True, outlines_version=None, source='model', **kw):
    """The landslide model files in a temporary folder while the block runs; levels=None means no model file."""
    with tempfile.TemporaryDirectory() as d:
        model_path, report_path = Path(d) / 'landslide_purok_model.json', Path(d) / 'landslide_purok_report.json'
        if levels is not None:
            doc = model_document(levels, outlines_version=outlines_version, source=source, **kw)
            model_path.write_text(json.dumps(doc), encoding='utf-8')
            if report:
                report_path.write_text(json.dumps({**REPORT, 'version': doc['version'], 'source': source}),
                                       encoding='utf-8')
        with mock.patch.object(landslide_purok, 'MODEL_FILE', model_path), \
                mock.patch.object(landslide_purok, 'REPORT_FILE', report_path):
            landslide_purok.clear_cache()
            try:
                yield model_path
            finally:
                landslide_purok.clear_cache()
