"""
Closing a fire: the BFP log's columns G onward, entered by DRRMO once the
fire is out. Alarm level and property type are required; a count left blank
means not counted yet, which is not zero.
"""
from decimal import Decimal

from django.test import SimpleTestCase

from apps.history.bfp import close_fields, exact_location

OK = {'alarm_level': '1ST ALARM', 'property_category': 'RESIDENTIAL',
      'property_subcategory': 'SINGLE AND TWO FAMILY DWELLING'}


class CloseFieldsTests(SimpleTestCase):
    def test_a_complete_close(self):
        fields, errors = close_fields({**OK, 'injured_civ_male': '2', 'fatal_ff_female': 0, 'damage_cost': '75000',
                                       'structures_affected': '1', 'summary': ' Out by 11:00 '})
        self.assertEqual(errors, {})
        self.assertEqual((fields['injured_civ_male'], fields['fatal_ff_female'], fields['damage_cost'],
                          fields['structures_affected']), (2, 0, Decimal('75000'), 1))
        self.assertEqual(fields['total_casualties'], 2)
        self.assertEqual(fields['summary'], 'Out by 11:00')

    def test_blank_counts_stay_blank(self):
        fields, errors = close_fields({**OK, 'injured_civ_male': '', 'damage_cost': None})
        self.assertEqual(errors, {})
        self.assertIsNone(fields['injured_civ_male'])
        self.assertIsNone(fields['damage_cost'])
        self.assertIsNone(fields['total_casualties'])

    def test_required_and_valid(self):
        self.assertEqual(close_fields({})[1]['alarm_level'], 'Choose the alarm level.')
        self.assertEqual(close_fields({**OK, 'alarm_level': '9TH ALARM'})[1]['alarm_level'], 'Choose the alarm level.')
        self.assertEqual(close_fields({**OK, 'property_subcategory': 'GRASS'})[1]['property_subcategory'],
                         'Choose the property type.')
        self.assertEqual(close_fields({**OK, 'injured_ff_male': '-1'})[1]['injured_ff_male'],
                         'Enter a whole number, 0 or more.')
        self.assertEqual(close_fields({**OK, 'injured_ff_male': '1.5'})[1]['injured_ff_male'],
                         'Enter a whole number, 0 or more.')
        self.assertEqual(close_fields({**OK, 'damage_cost': 'abc'})[1]['damage_cost'],
                         'Enter an amount in pesos, 0 or more.')

    def test_exact_location(self):
        self.assertEqual(exact_location(['Purok Sambag', 'Purok Agoho'], 'Jaclupan'),
                         'PUROK SAMBAG, PUROK AGOHO, BRGY JACLUPAN')
        self.assertEqual(exact_location([], 'Jaclupan'), 'BRGY JACLUPAN')
        self.assertEqual(exact_location([], None), '')
