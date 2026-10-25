"""
Deciding what the BFP import writes: one history record per fire, linked to
its purok where the address names one, and a report of everything it could
not place so the purok list can be fixed and the import re-run.
"""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from apps.history import bfp
from apps.history.bfp_import import plan_import

MNL = ZoneInfo('Asia/Manila')


class FakeBarangay:
    def __init__(self, id, name, boundary=None):
        self.id, self.name, self.boundary = id, name, boundary


ROQUE = FakeBarangay(19, 'San Roque', boundary=object())
MOHON = FakeBarangay(15, 'Mohon', boundary=object())
CANSOJONG = FakeBarangay(5, 'Cansojong', boundary=object())


def row(**kw):
    r = {'row': 5, 'date': 44963, 'time': 2242, 'city': 'Talisay_City_c',
         'location': 'PUROK SAMBAG, LARAY, BRGY SAN ROQUE',
         'category': 'RESIDENTIAL', 'subcategory': 'SINGLE AND TWO FAMILY DWELLING',
         'total_hurt': 0, 'damage_cost': Decimal('625000'), 'structures_affected': 76, 'alarm': '2ND ALARM'}
    r.update({k: 0 for k in bfp.CASUALTY_FIELDS})
    r.update(kw)
    return r


class PlanImportTests(SimpleTestCase):
    def test_a_new_row_becomes_one_record(self):
        [rec], report = plan_import([row(location='PUROK SAMBAG, LARAY, BRGY SAN ROQUE')], set(), [ROQUE],
                                    {ROQUE.id: ['Purok Sambag']}, {})
        self.assertEqual(rec['barangay'], ROQUE)
        self.assertEqual(rec['purok_name'], 'Purok Sambag')
        self.assertEqual(rec['severity_level'], 'Orange')
        self.assertEqual(rec['alarm_level'], '2ND ALARM')
        self.assertEqual(rec['description'], 'BFP: RESIDENTIAL – SINGLE AND TWO FAMILY DWELLING, 2ND ALARM')
        self.assertEqual(rec['location_text'], 'PUROK SAMBAG, LARAY, BRGY SAN ROQUE')
        self.assertEqual(rec['occurred_at'], datetime(2023, 2, 6, 22, 42, tzinfo=MNL))
        self.assertTrue(rec['source_ref'].startswith('bfp:'))
        self.assertEqual((report['imported'], report['linked']), (1, 1))

    def test_existing_refs_are_skipped(self):
        r = row()
        records, report = plan_import([r], {bfp.source_ref(bfp.parse_when(r['date'], r['time']), r['location'])},
                                      [ROQUE], {}, {})
        self.assertEqual((records, report['skipped_existing']), ([], 1))

    def test_an_exact_repeat_is_imported_once(self):
        records, report = plan_import([row(row=190), row(row=191)], set(), [ROQUE], {}, {})
        self.assertEqual(len(records), 1)
        self.assertEqual(report['duplicates'], [191])

    def test_same_time_and_place_but_a_different_fire_gets_its_own_ref(self):
        records, report = plan_import([row(row=7), row(row=8, subcategory='RUBBISH')], set(), [ROQUE], {}, {})
        self.assertEqual(len(records), 2)
        self.assertEqual(records[1]['source_ref'], records[0]['source_ref'] + ':2')
        self.assertEqual(report['duplicates'], [])

    def test_rows_outside_talisay_and_bad_dates_are_listed_not_imported(self):
        records, report = plan_import([row(row=9, city='Toledo_City'), row(row=10, date='sometime')], set(),
                                      [ROQUE], {}, {})
        self.assertEqual(records, [])
        self.assertEqual((report['outside_city'], report['bad_date']), ([9], [10]))

    def test_barangay_only_and_no_barangay(self):
        records, report = plan_import([row(row=4, location='Mohon, Talisay City Cebu'),
                                       row(row=5, location='Sitio Napo, Talisay City Cebu')], set(),
                                      [ROQUE, MOHON], {}, {})
        self.assertEqual([r['purok_name'] for r in records], [None, None])
        self.assertEqual(records[1]['barangay'], None)
        self.assertEqual((report['barangay_only'], report['no_barangay']), (1, [5]))

    def test_unlinked_names_are_listed_with_close_purok_names(self):
        _, report = plan_import([row(location='Sitio Ibacan, Cansojong, Talisay City Cebu')], set(),
                                [CANSOJONG], {CANSOJONG.id: ['Sitio Ebacan']}, {})
        self.assertEqual(report['unlinked']['Cansojong']['Sitio Ibacan'], {'fires': 1, 'close': ['Sitio Ebacan']})

    def test_unknown_alarm_is_low_and_listed(self):
        [rec], report = plan_import([row(alarm='ALARM X')], set(), [ROQUE], {}, {})
        self.assertEqual(rec['severity_level'], 'Green')
        self.assertEqual(report['unknown_alarms'], {'ALARM X': 1})
