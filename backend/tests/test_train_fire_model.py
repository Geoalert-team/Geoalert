"""
manage.py train_fire_model (plan Task B4): 6 puroks in 2 barangays with fires
across 2023-2026 and a features file matched to the purok map. The command
runs once for the class with a small candidate grid and few resamples.
"""
import json
import re
import shutil
import tempfile
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

import numpy as np
from django.contrib.gis.geos import MultiPolygon
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.barangays.models import Barangay, Purok
from apps.hazards.models import HazardType
from apps.history import fire_features as ff
from apps.history import fire_training as ft
from apps.history.management.commands import train_fire_model as tfm
from apps.history.models import HistoricalRecord
from tests.fire_setup import box
from tests.test_fire_training import SMALL

TODAY = '2026-11-23'


def make_world(cls):
    """Two barangays, six puroks (two of them named from the fire log), fires each month somewhere."""
    fire = HazardType.objects.create(name='Fire', logo_class='fire', is_active=True)
    cls.barangays = [Barangay.objects.create(name=n, municipality='Talisay',
                                             boundary=MultiPolygon(box(i * 1000, 0, i * 1000 + 900, 900), srid=4326))
                     for i, n in enumerate(('Alpha', 'Beta'))]
    cls.puroks = []
    for i in range(6):
        b = cls.barangays[i // 3]
        x = (i // 3) * 1000 + (i % 3) * 300
        cls.puroks.append(Purok.objects.create(barangay=b, name=f'Purok {i}', kind='purok', source='estimated',
                                               confidence='low' if i == 5 else 'medium',
                                               boundary=MultiPolygon(box(x, 0, x + 250, 250), srid=4326)))
    tz = timezone.get_current_timezone()
    rng = np.random.default_rng(4)
    hot = {0, 3}  # dense areas burn more often
    cls.placed = 0
    for year, month in [(y, m) for y in (2023, 2024, 2025, 2026) for m in range(1, 13) if (y, m) <= (2026, 10)]:
        for i, purok in enumerate(cls.puroks):
            if rng.random() < (0.35 if i in hot else 0.06):
                when = datetime(year, month, 10, 14, 0, tzinfo=tz)
                rec = HistoricalRecord.objects.create(barangay=purok.barangay, hazard_type=fire,
                                                      severity_level='Orange', occurred_at=when)
                rec.puroks.add(purok)
                cls.placed += 1
    # A fire BFP logged with only its barangay: listed, never guessed into a purok
    cls.unplaced = HistoricalRecord.objects.create(barangay=cls.barangays[1], hazard_type=fire, severity_level='Orange',
                                                   occurred_at=datetime(2025, 3, 2, 9, 0, tzinfo=tz))


def write_table(folder, version):
    rows = []
    for i, p in enumerate(Purok.objects.order_by('id')):
        row = {'purok_id': p.id, 'barangay_id': p.barangay_id, 'barangay': p.barangay.name, 'name': p.name,
               'confidence': p.confidence, 'from_fire_log': i in (0, 4)}
        row.update({c: float((i * 5 + j * 2) % 9 + 1) for j, c in enumerate(ff.FEATURE_COLUMNS)})
        row['buildings_in_area'] = 400.0 if i in (0, 3) else 30.0
        row['building_density_per_ha'] = row['buildings_in_area'] / 6
        rows.append(row)
    table = ff.FeatureTable(rows=rows, outlines_version=version, built_at='2026-11-23T08:00:00+08:00',
                            sources={'buildings': {'name': 'test'}})
    ff.write_features(table, Path(folder) / ff.FEATURES_FILE.name, Path(folder) / ff.FEATURES_META.name)


def run(folder, **kw):
    out = StringIO()
    with mock.patch.object(ft, 'CANDIDATES', SMALL):
        call_command('train_fire_model', output_dir=str(folder), today=TODAY, interval_reps=5, boot_reps=50,
                     stdout=out, **kw)
    return out.getvalue()


class TrainFireModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_world(cls)
        cls.folder = Path(tempfile.mkdtemp())
        write_table(cls.folder, Purok.outlines_version())
        cls.output = run(cls.folder)
        cls.model = json.loads((cls.folder / ff.MODEL_FILE.name).read_text(encoding='utf-8'))
        cls.report = json.loads((cls.folder / ff.REPORT_FILE.name).read_text(encoding='utf-8'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)
        super().tearDownClass()

    def test_writes_model_and_report(self):
        self.assertEqual(set(self.model['areas']), {str(p.id) for p in self.puroks})
        for area in self.model['areas'].values():
            self.assertEqual(len(area['months']), 12)
            for m in area['months']:
                self.assertIn(m['level'], ('Red', 'Orange', 'Green'))
                self.assertTrue(0 < m['p'] < 1)
                self.assertTrue(0 < m['low'] <= m['high'] < 1)
        self.assertEqual(self.model['outlines_version'], Purok.outlines_version())
        self.assertIn(self.model['model']['family'], SMALL)
        self.assertRegex(self.model['version'], r'^[a-z_]+@[0-9a-f]{12}$')
        self.assertTrue(self.model['version'].startswith(self.model['model']['family'] + '@'))
        self.assertEqual(self.report['version'], self.model['version'])

    def test_training_span(self):
        trained = self.model['trained']
        self.assertEqual((trained['start'], trained['end']), ('2023-01', '2026-10'))
        self.assertEqual(trained['fires'], self.placed)
        self.assertEqual(self.report['test']['window'], {'start': '2026-01', 'end': '2026-10'})

    def test_unplaced_listed_not_trained(self):
        self.assertEqual(self.model['trained']['unplaced'], [{'date': '2025-03-02', 'barangay': 'Beta'}])
        self.assertEqual(self.report['unplaced'], self.model['trained']['unplaced'])

    def test_limited_data_for_a_low_confidence_point(self):
        self.assertTrue(self.model['areas'][str(self.puroks[5].id)]['limited_data'])

    def test_report_names_comparisons_and_caveat(self):
        for section in (self.report['test']['comparison'], self.report['barangay_check']['comparison']):
            self.assertEqual(set(section), {'comparison_same_everywhere', 'comparison_buildings',
                                            'comparison_historical_frequency'})
        self.assertEqual(self.report['caveat'], tfm.CAVEAT.format(named=2, total=6))
        self.assertEqual((self.report['sensitivity']['named_areas'], self.report['sensitivity']['other_areas']), (2, 4))
        self.assertIn('log_loss', self.report['test']['scores'])
        self.assertIn('log_loss', self.report['leave_one_barangay_out'])
        self.assertIn('log_loss', self.report['barangay_check']['scores'])
        self.assertEqual([r['level'] for r in self.report['test']['levels']], ['Red', 'Orange', 'Green'])
        self.assertEqual(self.report['test']['green_fires'], self.report['test']['levels'][2]['fires'])
        self.assertEqual(len(self.report['test']['reliability']), 10)
        self.assertEqual({r['family'] for r in self.report['candidates']}, set(SMALL))
        self.assertIn('adopted', self.report['verdict'])

    def test_credit_present(self):
        for doc in (self.model, self.report):
            self.assertIn('City of Pittsburgh', doc['credit'])
            self.assertIn('MIT', doc['credit'])

    def test_cutoffs_and_levels_agree(self):
        c = self.model['cutoffs']
        for area in self.model['areas'].values():
            for m in area['months']:
                expect = 'Red' if c['red'] is not None and m['p'] >= c['red'] else (
                    'Orange' if m['p'] >= c['orange'] else 'Green')
                self.assertEqual(m['level'], expect)

    def test_prints_the_outcome(self):
        self.assertIn(self.model['model']['family'], self.output)
        self.assertRegex(self.output, r'test log loss')

    def test_same_data_same_version(self):
        with tempfile.TemporaryDirectory() as d:
            for name in (ff.FEATURES_FILE.name, ff.FEATURES_META.name):
                shutil.copy(self.folder / name, Path(d) / name)
            run(d)
            again = json.loads((Path(d) / ff.MODEL_FILE.name).read_text(encoding='utf-8'))
        self.assertEqual(again['version'], self.model['version'])

    def test_interrupted_write_keeps_the_old_files(self):
        # The site reads both files while training runs; a write that dies halfway
        # must leave the previous pair whole, not a truncated or mismatched file.
        real_write = Path.write_text
        calls = []

        def dies_on_second_write(path, data, *args, **kwargs):
            calls.append(path)
            if len(calls) == 2:
                real_write(path, data[:len(data) // 2], *args, **kwargs)
                raise OSError('disk full')
            return real_write(path, data, *args, **kwargs)

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for name in (ff.FEATURES_FILE.name, ff.FEATURES_META.name):
                shutil.copy(self.folder / name, d / name)
            (d / ff.MODEL_FILE.name).write_text('{"old": "model"}\n', encoding='utf-8')
            (d / ff.REPORT_FILE.name).write_text('{"old": "report"}\n', encoding='utf-8')
            with mock.patch.object(Path, 'write_text', dies_on_second_write):
                with self.assertRaisesRegex(OSError, 'disk full'):
                    run(d)
            self.assertEqual((d / ff.MODEL_FILE.name).read_text(encoding='utf-8'), '{"old": "model"}\n')
            self.assertEqual((d / ff.REPORT_FILE.name).read_text(encoding='utf-8'), '{"old": "report"}\n')
            self.assertEqual(sorted(p.name for p in d.iterdir() if p.name.endswith('.tmp')), [])

    def test_stops_on_stale_outlines(self):
        with tempfile.TemporaryDirectory() as d:
            write_table(d, 'an-older-map')
            with self.assertRaisesRegex(CommandError, 'build_fire_features'):
                run(d)
            self.assertFalse((Path(d) / ff.MODEL_FILE.name).exists())

    def test_missing_features_file(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(CommandError, 'build_fire_features'):
                run(d)
