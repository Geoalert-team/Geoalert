"""
Importing the flood and landslide log: the Flood and Landslide sheets hold one
row per event, the By Barangay sheet splits each event one row per barangay.
Each (event, barangay) becomes one history record, linked to a purok where the
sheet names one that is on the purok list.
"""
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase
from openpyxl import Workbook

from apps.history import flood_landslide as fl
from apps.history.flood_landslide import plan_import

MNL = ZoneInfo('Asia/Manila')


class FakeBarangay:
    def __init__(self, id, name, boundary=None):
        self.id, self.name, self.boundary = id, name, boundary


MANIPIS = FakeBarangay(1, 'Manipis', boundary=object())
DUMLOG = FakeBarangay(2, 'Dumlog', boundary=object())
SAN_ISIDRO = FakeBarangay(3, 'San Isidro', boundary=object())
TABUNOK = FakeBarangay(4, 'Tabunok', boundary=object())
BARANGAYS = [MANIPIS, DUMLOG, SAN_ISIDRO, TABUNOK]


def event(**kw):
    e = {'sheet': 'Flood', 'row': 4, 'date': datetime(2021, 6, 12), 'time': 1855, 'city': 'Talisay_City_c',
         'location': 'MANANGA RIVER COMMUNITIES', 'hazard': 'FLOOD', 'subcategory': 'RIVER OVERFLOW',
         'cause': 'Heavy downpour', 'injured': None, 'fatalities': None, 'families': None, 'persons': None,
         'impact': 'Water neck-deep.', 'remarks': '', 'source': 'https://a.example/1\nhttps://a.example/2'}
    e.update(kw)
    return e


def split(barangay, place=None, **kw):
    s = {'row': 2, 'date': datetime(2021, 6, 12), 'hazard': 'FLOOD', 'barangay': barangay, 'place': place,
         'families': None}
    s.update(kw)
    return s


def plan(events, splits, existing=frozenset(), puroks=None, **kw):
    return plan_import(events, splits, set(existing), BARANGAYS, puroks or {}, {}, **kw)


class PlanImportTests(SimpleTestCase):
    def test_one_record_per_barangay_the_event_hit(self):
        records, report = plan([event()], [split('SAN ISIDRO', families=357), split('DUMLOG', 'SITIO BAHALA')])
        self.assertEqual([r['barangay'] for r in records], [SAN_ISIDRO, DUMLOG])
        self.assertTrue(all(r['hazard'] == 'Flood' for r in records))
        self.assertEqual(records[0]['occurred_at'], datetime(2021, 6, 12, 18, 55, tzinfo=MNL))
        self.assertEqual(len({r['source_ref'] for r in records}), 2)
        self.assertTrue(records[0]['source_ref'].startswith('flood-landslide:'))
        self.assertIn('Families evacuated in this barangay: 357.', records[0]['description'])
        self.assertEqual(report['imported'], 2)

    def test_a_named_place_on_the_purok_list_is_linked(self):
        [rec], report = plan([event()], [split('DUMLOG', 'SITIO LITMON (COASTAL)')],
                             puroks={DUMLOG.id: ['Sitio Litmon', 'Sitio Kamalig']})
        self.assertEqual(rec['purok_names'], ['Sitio Litmon'])
        self.assertEqual(rec['location_text'], 'SITIO LITMON (COASTAL), BRGY DUMLOG')
        self.assertEqual((report['linked'], report['barangay_only']), (1, 0))

    def test_a_place_not_on_the_list_files_the_record_under_the_barangay(self):
        [rec], report = plan([event()], [split('DUMLOG', 'SITIO BAHALA')], puroks={DUMLOG.id: ['Sitio Bahalang']})
        self.assertEqual(rec['purok_names'], [])
        self.assertEqual(report['barangay_only'], 1)
        self.assertEqual(report['unlinked'], {'Dumlog': {'SITIO BAHALA': ['Sitio Bahalang']}})

    def test_two_places_in_one_barangay_are_one_record(self):
        [rec], _ = plan([event()], [split('MANIPIS', 'PUROK BAMBOO'), split('MANIPIS', 'SITIO SANTOL, CAMP 5')],
                        puroks={MANIPIS.id: ['Sitio Camp 5']})
        self.assertEqual(rec['purok_names'], ['Sitio Camp 5'])
        self.assertEqual(rec['location_text'], 'PUROK BAMBOO; SITIO SANTOL, CAMP 5, BRGY MANIPIS')

    def test_another_spelling_of_the_barangay_matches(self):
        [rec], _ = plan([event()], [split('TABUNOC')])
        self.assertEqual(rec['barangay'], TABUNOK)

    def test_the_logs_columns_fill_the_record(self):
        [rec], _ = plan([event(cause='Typhoon Tino', injured=1, fatalities=0, families=48, persons=119)],
                        [split('DUMLOG')])
        self.assertEqual((rec['hazard_subcategory'], rec['cause']), ('RIVER OVERFLOW', 'Typhoon Tino'))
        self.assertEqual((rec['injured'], rec['fatalities'], rec['families_affected'], rec['persons_affected']),
                         (1, 0, 48, 119))
        self.assertEqual(rec['description'], 'Water neck-deep. Sources: https://a.example/1 https://a.example/2')

    def test_figures_are_kept_once_per_event(self):
        records, _ = plan([event(injured=6, fatalities=7, families=10)], [split('SAN ISIDRO'), split('DUMLOG')])
        self.assertEqual([r['total_casualties'] for r in records], [13, None])
        self.assertEqual([(r['injured'], r['families_affected']) for r in records], [(6, 10), (None, None)])
        self.assertIn('Whole event (2 barangays): 6 injured, 7 dead, 10 families affected.',
                      records[1]['description'])

    def test_zero_is_kept_apart_from_not_reported(self):
        [zero], _ = plan([event(injured=0, fatalities=0)], [split('MANIPIS')])
        [blank], _ = plan([event()], [split('MANIPIS')])
        self.assertEqual((zero['total_casualties'], blank['total_casualties']), (0, None))

    def test_an_event_naming_no_barangay_is_one_record_without_one(self):
        [rec], report = plan([event(location='TALISAY CITY (BARANGAYS NOT STATED)')], [])
        self.assertIsNone(rec['barangay'])
        self.assertEqual(rec['location_text'], 'TALISAY CITY (BARANGAYS NOT STATED)')
        self.assertEqual(report['no_barangay'], ['Flood row 4'])

    def test_warnings_are_left_out_unless_asked_for(self):
        warning = event(subcategory='RISK ADVISORY (NO CONFIRMED SLIDE)', hazard='LANDSLIDE')
        records, report = plan([warning], [split('MANIPIS', hazard='LANDSLIDE')])
        self.assertEqual((records, report['warnings_skipped']), ([], ['Flood row 4']))
        records, _ = plan([warning], [split('MANIPIS', hazard='LANDSLIDE')], include_warnings=True)
        self.assertEqual(len(records), 1)

    def test_existing_refs_are_skipped(self):
        [rec], _ = plan([event()], [split('DUMLOG')])
        records, report = plan([event()], [split('DUMLOG')], existing={rec['source_ref']})
        self.assertEqual((records, report['skipped_existing']), ([], 1))

    def test_a_split_row_with_no_event_is_reported(self):
        _, report = plan([event()], [split('DUMLOG', date=datetime(2021, 6, 13))])
        self.assertEqual(report['splits_without_event'], ['By Barangay row 2'])

    def test_an_unknown_barangay_is_reported_and_filed_without_one(self):
        [rec], report = plan([event()], [split('ATLANTIS')])
        self.assertIsNone(rec['barangay'])
        self.assertEqual(report['unknown_barangays'], ['ATLANTIS'])

    def test_rows_outside_talisay_or_without_a_date_are_left_out(self):
        records, report = plan([event(city='Minglanilla'), event(row=5, date=None)], [])
        self.assertEqual(records, [])
        self.assertEqual((report['outside_city'], report['bad_date']), (['Flood row 4'], ['Flood row 5']))


class CloseFieldsTests(SimpleTestCase):
    def test_a_flood_needs_a_sub_category_from_its_list(self):
        fields, errors = fl.close_fields({'hazard_subcategory': ' river overflow '}, 'Flood')
        self.assertEqual((fields['hazard_subcategory'], errors), ('RIVER OVERFLOW', {}))
        _, errors = fl.close_fields({}, 'Flood')
        self.assertEqual(errors, {'hazard_subcategory': 'Choose the sub category.'})
        _, errors = fl.close_fields({'hazard_subcategory': 'ROAD LANDSLIDE'}, 'Flood')
        self.assertIn('hazard_subcategory', errors)

    def test_a_type_without_a_list_is_not_asked_for_one(self):
        fields, errors = fl.close_fields({'hazard_subcategory': 'ANYTHING'}, 'Earthquake')
        self.assertEqual((fields['hazard_subcategory'], errors), ('', {}))

    def test_counts_are_whole_numbers_and_blank_is_not_counted(self):
        fields, errors = fl.close_fields({'hazard_subcategory': 'LANDSLIDE', 'injured': 2, 'fatalities': '0',
                                          'families_affected': '', 'persons_affected': None}, 'Landslide')
        self.assertEqual(errors, {})
        self.assertEqual((fields['injured'], fields['fatalities'], fields['families_affected'],
                          fields['persons_affected'], fields['total_casualties']), (2, 0, None, None, 2))
        _, errors = fl.close_fields({'hazard_subcategory': 'LANDSLIDE', 'injured': '-1', 'persons_affected': '2.5'},
                                    'Landslide')
        self.assertEqual(errors, {'injured': 'Enter a whole number, 0 or more.',
                                  'persons_affected': 'Enter a whole number, 0 or more.'})

    def test_nobody_counted_is_no_casualty_total(self):
        fields, _ = fl.close_fields({'hazard_subcategory': 'LANDSLIDE'}, 'Landslide')
        self.assertIsNone(fields['total_casualties'])

    def test_cause_and_summary_are_kept_and_the_cause_has_a_limit(self):
        fields, errors = fl.close_fields({'hazard_subcategory': 'FLASH FLOOD', 'cause': '  Heavy   rain ',
                                          'summary': ' Knee-deep. '}, 'Flood')
        self.assertEqual((fields['cause'], fields['summary'], errors), ('Heavy rain', 'Knee-deep.', {}))
        _, errors = fl.close_fields({'hazard_subcategory': 'FLASH FLOOD', 'cause': 'x' * 201}, 'Flood')
        self.assertEqual(errors, {'cause': 'Keep the cause under 200 characters.'})


class SeverityTests(SimpleTestCase):
    def test_deaths_or_a_large_evacuation_is_extreme(self):
        self.assertEqual(fl.severity(event(fatalities=1)), 'Red')
        self.assertEqual(fl.severity(event(families=100)), 'Red')
        self.assertEqual(fl.severity(event(persons=500)), 'Red')

    def test_injuries_or_any_families_affected_is_moderate(self):
        self.assertEqual(fl.severity(event(injured=1, fatalities=0)), 'Orange')
        self.assertEqual(fl.severity(event(families=48, persons=119)), 'Orange')

    def test_no_figures_is_low(self):
        self.assertEqual(fl.severity(event(injured=0, fatalities=0)), 'Green')
        self.assertEqual(fl.severity(event()), 'Green')


class ReadWorkbookTests(SimpleTestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)

    def test_reads_events_below_three_header_rows_and_splits_below_one(self):
        wb = Workbook()
        flood = wb.active
        flood.title = 'Flood'
        flood['A1'], flood['G2'] = 'Date of Event', 'General Category'
        for col, value in zip('ABEFGHIJKLMNOP', [datetime(2024, 10, 23), None, 'Talisay_City_c', 'SITIO LITMON',
                                                 'FLOOD', 'COASTAL WAVES', 'Kristine', None, None, 48, 119,
                                                 'Waves.', 'NEW.', 'https://x.example']):
            flood[f'{col}4'] = value
        wb.create_sheet('Landslide')['A1'] = 'Date of Event'
        by = wb.create_sheet('By Barangay')
        by['A1'] = 'Date of Event'
        for col, value in zip('ABFGI', [datetime(2024, 10, 23), 'FLOOD', 'DUMLOG', 'SITIO LITMON', 48]):
            by[f'{col}2'] = value
        path = Path(self._dir.name) / 'log.xlsx'
        wb.save(path)

        events, splits = fl.read_workbook(path)
        [e] = events
        self.assertEqual((e['sheet'], e['row'], e['hazard'], e['subcategory']), ('Flood', 4, 'FLOOD', 'COASTAL WAVES'))
        self.assertEqual((e['injured'], e['families'], e['persons']), (None, 48, 119))
        self.assertEqual(splits, [{'row': 2, 'date': datetime(2024, 10, 23), 'hazard': 'FLOOD',
                                   'barangay': 'DUMLOG', 'place': 'SITIO LITMON', 'families': 48}])
