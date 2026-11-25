from pathlib import Path

import numpy as np
from django.conf import settings
from django.test import SimpleTestCase

from apps.history import landslide_training
from apps.history.landslide_features import FEATURE_COLUMNS
from apps.history.landslide_training import design_matrix
from utils.system_settings import SETTINGS


class LandslideGuardTests(SimpleTestCase):
    def test_no_setting_or_view_can_change_a_landslide_prediction(self):
        self.assertFalse([k for k in SETTINGS if 'landslide' in k.lower()])
        for path in Path(settings.BASE_DIR, 'apps').rglob('views*.py'):
            self.assertNotIn('landslide_purok_model', path.read_text(encoding='utf-8'))

    def test_model_inputs_are_the_allowlist(self):
        self.assertEqual(FEATURE_COLUMNS, ('slope_deg', 'relief_m', 'profile_curv', 'plan_curv', 'hand_m', 'twi',
            'dist_stream_m', 'dist_road_m', 'lc_trees', 'lc_rangeland', 'lc_crops', 'lc_built', 'lc_bare'))
        table = {c: np.ones(4) for c in (*FEATURE_COLUMNS, 'noah_class', 'label')}  # noah_class sits in every table
        _, cols = design_matrix(table, FEATURE_COLUMNS, medians={'dist_road_m': 1.0})
        self.assertEqual(set(cols) - set(FEATURE_COLUMNS), {'road_unknown'})  # noah_class never reaches a model
        self.assertNotIn('HistoricalRecord', Path(landslide_training.__file__).read_text(encoding='utf-8'))
