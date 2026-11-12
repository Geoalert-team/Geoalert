"""
history_places.csv: the map point of a past event whose source names the
spot, the pin of a purok or sitio it names or a landmark it names. A record
whose source names only a barangay gets no point; its barangay's outline is
all that is known. place_history_records writes the points, and a ref it
can't find stops the run before anything is written.
"""
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.gis.geos import MultiPolygon, Point
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.barangays.models import Barangay
from apps.hazards.models import HazardType
from apps.history.management.commands.place_history_records import PLACES_FILE
from apps.history.models import HistoricalRecord
from apps.history.places import read_places
from apps.history.serializers import STAFF_ONLY_FIELDS, HistoricalRecordDetailSerializer
from tests.fire_setup import LAT, LNG, M, box

HEADER = 'source_ref,lat,lng,precision,basis\n'
LOCATION_FIELDS = ['location_lat', 'location_lng', 'location_precision', 'location_basis']


class ReadPlacesTests(SimpleTestCase):
    def test_a_row_gives_the_ref_the_point_the_precision_and_the_basis(self):
        [place] = read_places(HEADER + 'flood-landslide:a,10.245646,123.834572,place,map pin of Sitio Paglaom\n')
        self.assertEqual(place.ref, 'flood-landslide:a')
        self.assertEqual((place.point.y, place.point.x), (10.245646, 123.834572))
        self.assertEqual(place.point.srid, 4326)
        self.assertEqual(place.precision, 'place')
        self.assertEqual(place.basis, 'map pin of Sitio Paglaom')

    def test_columns_kept_for_people_are_ignored(self):
        [place] = read_places('sheet_row,source_ref,lat,lng,precision,basis,note\n'
                              '18,flood-landslide:a,10.2,123.8,landmark,the viewing deck,checked by hand\n')
        self.assertEqual((place.ref, place.precision), ('flood-landslide:a', 'landmark'))

    def test_a_precision_outside_the_list_names_its_line(self):
        with self.assertRaisesRegex(ValueError, r'line 3.*barangay'):
            read_places(HEADER + 'a,10.2,123.8,place,x\nb,10.2,123.8,barangay,x\n')

    def test_a_coordinate_that_is_not_a_latitude_and_longitude_names_its_line(self):
        for lat, lng in (('123.8', '10.2'), ('', '123.8'), ('ten', '123.8')):
            with self.subTest(lat=lat, lng=lng), self.assertRaisesRegex(ValueError, 'line 2'):
                read_places(HEADER + f'a,{lat},{lng},place,x\n')

    def test_a_ref_given_twice_names_its_line(self):
        with self.assertRaisesRegex(ValueError, r'line 3.*twice'):
            read_places(HEADER + 'a,10.2,123.8,place,x\na,10.3,123.8,place,y\n')

    def test_a_row_without_a_ref_names_its_line(self):
        with self.assertRaisesRegex(ValueError, 'line 2'):
            read_places(HEADER + ',10.2,123.8,place,x\n')

    def test_the_shipped_file_reads_and_sits_in_talisay(self):
        places = read_places(PLACES_FILE.read_text(encoding='utf-8-sig'))
        self.assertTrue(places)
        for place in places:
            self.assertTrue(place.ref.startswith('flood-landslide:'), place.ref)
            self.assertTrue(10.2 < place.point.y < 10.4 and 123.7 < place.point.x < 123.9, place.ref)
            self.assertTrue(place.basis, place.ref)


class PlaceHistoryRecordsTests(TestCase):
    def setUp(self):
        flood = HazardType.objects.create(name='Flood')
        self.home = Barangay.objects.create(name='Home', municipality='Talisay',
                                            boundary=MultiPolygon(box(-500, -500, 500, 500), srid=4326))
        self.a, self.b = (
            HistoricalRecord.objects.create(hazard_type=flood, barangay=self.home, severity_level='Orange',
                                            occurred_at=timezone.now(), source_ref=ref)
            for ref in ('flood-landslide:a', 'flood-landslide:b'))
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.file = Path(folder.name) / 'history_places.csv'

    def places(self, *rows):
        self.file.write_text(HEADER + ''.join(f'{r}\n' for r in rows), encoding='utf-8')

    def run_command(self, **options):
        out = StringIO()
        call_command('place_history_records', file=str(self.file), stdout=out, **options)
        return out.getvalue()

    def test_each_named_record_gets_its_point_precision_and_basis(self):
        self.places(f'flood-landslide:a,{LAT},{LNG},place,map pin of Sitio Bahala')
        out = self.run_command()
        self.a.refresh_from_db()
        self.assertAlmostEqual(self.a.location.x, LNG)
        self.assertAlmostEqual(self.a.location.y, LAT)
        self.assertEqual(self.a.location_precision, 'place')
        self.assertEqual(self.a.location_basis, 'map pin of Sitio Bahala')
        self.assertIn('Placed 1', out)

    def test_a_record_not_in_the_file_keeps_no_point(self):
        self.places(f'flood-landslide:a,{LAT},{LNG},place,x')
        self.run_command()
        self.b.refresh_from_db()
        self.assertIsNone(self.b.location)
        self.assertEqual((self.b.location_precision, self.b.location_basis), ('', ''))

    def test_a_dry_run_writes_nothing(self):
        self.places(f'flood-landslide:a,{LAT},{LNG},place,x')
        out = self.run_command(dry_run=True)
        self.a.refresh_from_db()
        self.assertIsNone(self.a.location)
        self.assertIn('Dry run', out)
        self.assertIn('Placed 1', out)

    def test_a_ref_with_no_record_stops_the_run_before_anything_is_written(self):
        self.places(f'flood-landslide:a,{LAT},{LNG},place,x', f'flood-landslide:gone,{LAT},{LNG},place,y')
        with self.assertRaisesRegex(CommandError, 'flood-landslide:gone'):
            self.run_command()
        self.a.refresh_from_db()
        self.assertIsNone(self.a.location)

    def test_a_bad_file_stops_the_run_with_its_line(self):
        self.places(f'flood-landslide:a,{LAT},{LNG},guess,x')
        with self.assertRaisesRegex(CommandError, 'line 2'):
            self.run_command()

    def test_running_it_again_changes_nothing(self):
        self.places(f'flood-landslide:a,{LAT},{LNG},place,x')
        self.run_command()
        out = self.run_command()
        self.assertIn('Placed 0', out)
        self.assertIn('unchanged 1', out)

    def test_a_point_outside_its_records_barangay_is_reported(self):
        far = LNG + 5000 * M
        self.places(f'flood-landslide:a,{LAT},{far},landmark,x')
        out = self.run_command()
        self.assertRegex(out, r'outside .*Home.*flood-landslide:a')
        self.a.refresh_from_db()
        self.assertAlmostEqual(self.a.location.x, far)


class LocationInTheDetailTests(SimpleTestCase):
    def test_the_detail_carries_the_point_its_precision_and_its_basis(self):
        for name in LOCATION_FIELDS:
            self.assertIn(name, HistoricalRecordDetailSerializer.Meta.fields)

    def test_only_staff_see_them_like_the_location_text(self):
        for name in LOCATION_FIELDS:
            self.assertIn(name, STAFF_ONLY_FIELDS)

    def test_latitude_and_longitude_come_from_the_point(self):
        serializer = HistoricalRecordDetailSerializer()
        placed = HistoricalRecord(location=Point(123.834572, 10.245646, srid=4326))
        self.assertEqual(serializer.get_location_lat(placed), 10.245646)
        self.assertEqual(serializer.get_location_lng(placed), 123.834572)

    def test_a_record_with_no_point_sends_none(self):
        serializer = HistoricalRecordDetailSerializer()
        self.assertIsNone(serializer.get_location_lat(HistoricalRecord()))
        self.assertIsNone(serializer.get_location_lng(HistoricalRecord()))
