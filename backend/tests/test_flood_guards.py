"""
No person or setting can touch a flood prediction (plan Task 8, spec 7): no
system setting names flood, no view writes the flood model files, and the
feature builder reads no flood observation. History's own settings stay.
"""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.history import flood_features
from utils.system_settings import SETTINGS


class FloodGuardTests(SimpleTestCase):
    def test_no_setting_or_view_can_change_a_flood_prediction(self):
        self.assertFalse([k for k in SETTINGS if 'flood' in k.lower()])
        for path in Path(settings.BASE_DIR, 'apps').rglob('views*.py'):
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('flood_purok_model', text, path)
            self.assertNotIn('flood_features.MODEL_FILE', text, path)
        self.assertNotIn('HistoricalRecord', Path(flood_features.__file__).read_text(encoding='utf-8'))

    def test_history_settings_are_still_there(self):
        self.assertTrue({'history.period_years', 'history.moderate_at', 'history.extreme_at'} <= set(SETTINGS))
