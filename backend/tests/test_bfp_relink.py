"""
fire_places.csv: fires placed by hand, because the address alone can't reach
an area. It is the only place these links live, so a re-link or a re-import
has to keep them, and a name it can't find must stop the run, not lose a link.
"""
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.barangays.models import Barangay, Purok
from apps.hazards.models import HazardType
from apps.history import bfp
from apps.history.importing import import_fires
from apps.history.management.commands.import_bfp_fires import Command
from apps.history.models import HistoricalRecord
from tests.fire_setup import MultiPolygon, box

COMMAND = 'apps.history.management.commands.import_bfp_fires.PUROK_DATA'
HEADER = 'barangay,address,areas,why\n'


def area(barangay, name):
    return Purok.objects.create(barangay=barangay, name=name, kind='purok', source='estimated',
                                boundary=MultiPolygon(box(-100, -100, 100, 100), srid=4326))


class PlacedFireMixin:
    def setUp(self):
        self.fire = HazardType.objects.create(name='Fire')
        outline = MultiPolygon(box(-500, -500, 500, 500), srid=4326)
        self.home = Barangay.objects.create(name='Home', municipality='Talisay', boundary=outline)
        self.next = Barangay.objects.create(name='Next door', municipality='Talisay', boundary=outline)
        self.rose, self.lower = area(self.home, 'Purok Rose'), area(self.home, 'Sitio Lower')
        self.subd = area(self.next, 'Mansueto Subdivision')
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data = Path(folder.name)

    def places(self, *rows):
        (self.data / 'fire_places.csv').write_text(HEADER + ''.join(f'{r}\n' for r in rows), encoding='utf-8')

    def record(self, text, barangay=None):
        return HistoricalRecord.objects.create(
            hazard_type=self.fire, barangay=barangay or self.home, severity_level='Red', occurred_at=timezone.now(),
            location_text=text, source_ref=f'bfp:{abs(hash(text)) % 10_000_000}')

    def relink(self, **options):
        out = StringIO()
        with mock.patch(COMMAND, self.data):
            call_command('import_bfp_fires', relink=True, stdout=out, **options)
        return out.getvalue()


class RelinkPlacedFiresTests(PlacedFireMixin, TestCase):
    def test_a_placed_fire_links_to_every_area_listed(self):
        self.places('Home,"Fidel Bas St., Home",Purok Rose + Sitio Lower,street crosses two areas')
        fire = self.record('Fidel Bas St., Home')
        self.relink()
        self.assertEqual(set(fire.puroks.all()), {self.rose, self.lower})

    def test_the_address_matches_whatever_its_case_and_spacing(self):
        self.places('Home,"FIDEL BAS ST.,  HOME",Purok Rose,typed differently')
        fire = self.record('Fidel Bas St., Home')
        self.relink()
        self.assertEqual(set(fire.puroks.all()), {self.rose})

    def test_a_placement_can_cross_a_barangay_line_and_the_record_keeps_its_barangay(self):
        self.places('Next door,"South Town Centre, Home",Mansueto Subdivision,the mall stands over the line')
        fire = self.record('South Town Centre, Home')
        self.relink()
        fire.refresh_from_db()
        self.assertEqual(set(fire.puroks.all()), {self.subd})
        self.assertEqual(fire.barangay, self.home)

    def test_a_fire_with_no_placement_still_links_from_its_address(self):
        self.places('Home,"Fidel Bas St., Home",Purok Rose,other fire')
        fire = self.record('Purok Rose, Home')
        self.relink()
        self.assertEqual(set(fire.puroks.all()), {self.rose})

    def test_a_dry_run_saves_nothing(self):
        self.places('Home,"Fidel Bas St., Home",Purok Rose,street')
        fire = self.record('Fidel Bas St., Home')
        self.assertIn('Dry run', self.relink(dry_run=True))
        self.assertEqual(fire.puroks.count(), 0)

    def test_an_area_that_is_not_loaded_stops_the_run_and_changes_nothing(self):
        self.places('Home,"Fidel Bas St., Home",Purok Gone,typo')
        kept = self.record('Purok Rose, Home')
        fire = self.record('Fidel Bas St., Home')
        with self.assertRaisesRegex(CommandError, 'Purok Gone'):
            self.relink()
        self.assertEqual((kept.puroks.count(), fire.puroks.count()), (0, 0))


class ImportPlacedFiresTests(PlacedFireMixin, TestCase):
    ROW = {'row': 5, 'date': 44963, 'time': 2242, 'city': 'Talisay_City_c', 'location': 'Fidel Bas St., Home',
           'category': 'RESIDENTIAL', 'subcategory': 'SINGLE AND TWO FAMILY DWELLING', 'total_hurt': 0,
           'damage_cost': Decimal('1000'), 'structures_affected': 1, 'alarm': '1ST ALARM',
           **{k: 0 for k in bfp.CASUALTY_FIELDS}}

    def test_a_reimported_fire_gets_its_placed_areas(self):
        self.places('Home,"Fidel Bas St., Home",Purok Rose + Sitio Lower,street crosses two areas')
        with (mock.patch('apps.history.importing.PUROK_DATA', self.data),
              mock.patch('apps.history.importing.check_layout'),
              mock.patch('apps.history.importing.bfp.read_sheet', return_value=[dict(self.ROW)])):
            import_fires('fires.xlsx', save=True)
        self.assertEqual(set(HistoricalRecord.objects.get().puroks.all()), {self.rose, self.lower})


class ReportTests(SimpleTestCase):
    def test_placed_links_are_counted_in_the_report(self):
        out = StringIO()
        report = {k: 0 for k in ('read', 'imported', 'skipped_existing', 'linked', 'barangay_only')}
        report.update({'linked_by': {'placed': 2}, 'outside_city': [], 'duplicates': [], 'bad_date': [],
                       'no_barangay': [], 'unknown_alarms': {}, 'unlinked': {}})
        Command(stdout=out).print_report(report)
        self.assertIn('placed 2', out.getvalue())
