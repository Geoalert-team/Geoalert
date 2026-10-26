"""
A purok's level from how often fire has hit it: few past events is green,
more is orange, many is red. The period and the two thresholds are System
Admin settings.
"""
from unittest import mock

from django.test import SimpleTestCase

from apps.history.purok_levels import highest, level_for, thresholds

T = {'years': 5, 'moderate': 3, 'extreme': 5}


class PurokLevelTests(SimpleTestCase):
    def test_level_for_each_boundary(self):
        self.assertEqual([level_for(n, T) for n in range(7)],
                         [None, 'Green', 'Green', 'Orange', 'Orange', 'Red', 'Red'])

    def test_contradicting_settings_fall_back_to_the_defaults(self):
        values = {'history.period_years': 2, 'history.moderate_at': 6, 'history.extreme_at': 4}
        with mock.patch('apps.history.purok_levels.get_setting', side_effect=values.get):
            self.assertEqual(thresholds(), {'years': 5, 'moderate': 3, 'extreme': 5})

    def test_settings_are_used_when_they_agree(self):
        values = {'history.period_years': 3, 'history.moderate_at': 2, 'history.extreme_at': 4}
        with mock.patch('apps.history.purok_levels.get_setting', side_effect=values.get):
            self.assertEqual(thresholds(), {'years': 3, 'moderate': 2, 'extreme': 4})

    def test_highest(self):
        self.assertEqual(highest(['Green', 'Red', 'Orange']), 'Red')
        self.assertEqual(highest([None, 'Orange']), 'Orange')
        self.assertEqual(highest([]), 'Green')
