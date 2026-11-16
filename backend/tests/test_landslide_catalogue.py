import tempfile
from datetime import date
from pathlib import Path

from django.test import SimpleTestCase

from apps.history.landslide_catalogue import (
    CACHE_NAME, CatalogueRecord, ensure_catalogue, era_end, load_exclusions, named_barangay, near,
    read_catalogue)

CENTRE = (10.2447, 123.8494)
HEADER = ('source_name,source_link,event_id,event_date,event_time,event_title,event_description,'
          'location_description,location_accuracy,landslide_category,landslide_trigger,landslide_size,'
          'landslide_setting,fatality_count,injury_count,storm_name,photo_link,notes,event_import_source,'
          'event_import_id,country_name,country_code,admin_division_name,admin_division_population,'
          'gazeteer_closest_point,gazeteer_distance,submitted_date,created_date,last_edited_date,'
          'longitude,latitude')
PAYLOAD = (HEADER + chr(10)).encode()
KM_PER_DEG = 6371.0088 * 3.141592653589793 / 180


def line(eid, when, title, loc, admin, lat, lon, place='Talisay'):
    return (f'src,http://x,{eid},{when},,"{title}","desc, with comma","{loc}",5km,landslide,rain,small,'
            f'natural,0,0,,,,imp,1,Philippines,PH,{admin},100,{place},1.0,,,,{lon},{lat}')


def north(km):
    return CENTRE[0] + km / KM_PER_DEG


FIXTURE = '\n'.join([
    HEADER,
    line(1, '08/01/2008 12:00:00 AM', 'Slide, Talisay', 'Manipis, Talisay', 'Cebu', north(5), CENTRE[1]),
    line(2, '09/12/2017 12:00:00 AM', 'Far', 'Elsewhere', 'Cebu', north(25), CENTRE[1]),
    line(3, '03/03/2010 12:00:00 AM', 'Negros slide', 'Somewhere', 'Negros Occidental', north(3), CENTRE[1]),
    line(4, '04/04/2012 12:00:00 AM', 'Listed', 'Tabunok', 'Cebu', north(4), CENTRE[1]),
    line(5, '', 'No date', 'x', 'Cebu', north(1), CENTRE[1]),
    line(6, '05/05/2015 12:00:00 AM', 'No coords', 'x', 'Cebu', '', ''),
]) + '\n'

NAMES = {1: 'Manipis', 2: 'Camp IV', 3: 'Tabunok'}


def rec(location, eid='r'):
    return CatalogueRecord(eid, date(2010, 1, 1), 10.2, 123.8, '5km', location, location)


class CatalogueTests(SimpleTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / 'cat.csv'
        self.path.write_text(FIXTURE, encoding='utf-8')

    def test_dates_coordinates_and_text_are_read(self):
        got = read_catalogue(self.path)
        self.assertEqual([r.event_id for r in got], ['1', '2', '3', '4'])
        first = got[0]
        self.assertEqual(first.day, date(2008, 8, 1))
        self.assertAlmostEqual(first.lat, north(5), places=6)
        self.assertAlmostEqual(first.lon, CENTRE[1])
        self.assertEqual(first.accuracy, '5km')
        self.assertIn('Slide, Talisay', first.text)
        self.assertIn('Manipis, Talisay', first.text)

    def test_near_keeps_20_km_and_drops_negros_and_listed_ids(self):
        got = near(read_catalogue(self.path), CENTRE, {'4': 'duplicate'})
        self.assertEqual([r.event_id for r in got], ['1'])

    def test_era_end_is_the_month_end_of_the_latest_record(self):
        self.assertEqual(era_end(read_catalogue(self.path)), date(2017, 9, 30))

    def test_named_barangay_needs_talisay_and_one_name(self):
        self.assertEqual(named_barangay(rec('Sitio X, Manipis, Talisay City'), NAMES), 1)
        self.assertEqual(named_barangay(rec('Camp 4, Talisay, Cebu'), NAMES), 2)
        self.assertEqual(named_barangay(rec('Camp IV, Talisay'), NAMES), 2)
        self.assertIsNone(named_barangay(rec('Manipis Road, Toledo'), NAMES))
        self.assertIsNone(named_barangay(rec('Manipis and Tabunok, Talisay'), NAMES))

    def test_coordinate_derived_fields_never_decide_a_barangay(self):
        rows = FIXTURE.splitlines()[0:1] + [
            line(7, '01/01/2010 12:00:00 AM', 'Slide', 'Sitio Y, Toledo City', 'Cebu', north(5), CENTRE[1], place='Manipis'),
            line(8, '01/01/2010 12:00:00 AM', 'Slide', 'Manipis', 'Cebu', north(5), CENTRE[1], place='Talisay'),
        ]
        self.path.write_text(chr(10).join(rows) + chr(10), encoding='utf-8')
        got = read_catalogue(self.path)
        self.assertEqual(len(got), 2)
        self.assertIn('Manipis', got[0].text)
        for r in got:
            self.assertIsNone(named_barangay(r, NAMES))

    def test_ensure_downloads_only_when_missing(self):
        calls = []

        def fake(url):
            calls.append(url)
            return PAYLOAD
        cache_dir = Path(self.dir.name) / 'cache'
        path = ensure_catalogue(cache_dir, get=fake)
        self.assertEqual(path, cache_dir / CACHE_NAME)
        self.assertEqual(path.read_bytes(), PAYLOAD)
        ensure_catalogue(cache_dir, get=fake)
        self.assertEqual(len(calls), 1)
        self.assertEqual([p.name for p in cache_dir.iterdir()], [CACHE_NAME])

    def test_a_failed_or_wrong_download_leaves_nothing(self):
        cache_dir = Path(self.dir.name) / 'cache'

        def boom(url):
            raise OSError('down')
        with self.assertRaises(OSError):
            ensure_catalogue(cache_dir, get=boom)
        with self.assertRaises(ValueError):
            ensure_catalogue(cache_dir, get=lambda url: b'<html>Error</html>')
        self.assertEqual(list(cache_dir.iterdir()) if cache_dir.exists() else [], [])

    def test_exclusion_ids_are_stripped(self):
        p = Path(self.dir.name) / 'ex.csv'
        p.write_text('event_id,reason' + chr(10) + ' 4 , dup ' + chr(10), encoding='utf-8')
        self.assertEqual(load_exclusions(p), {'4': 'dup'})
        self.assertEqual([r.event_id for r in near(read_catalogue(self.path), CENTRE, load_exclusions(p))], ['1'])

    def test_a_longer_word_is_not_the_barangay(self):
        self.assertIsNone(named_barangay(rec('Manipisan, Talisay'), NAMES))

    def test_load_exclusions_reads_the_shipped_file(self):
        self.assertEqual(load_exclusions(), {})
