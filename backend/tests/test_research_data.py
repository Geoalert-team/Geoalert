"""
The hand-edited purok research files hold together.

purok_points.csv, name_variants.csv and the rest are edited by hand
(SOURCES.md), so these tests read the real files: a parent that names no
row, two rows for one place, or a half-filled point would quietly break
the build or the fire linking.
"""
import csv
from pathlib import Path

from django.test import SimpleTestCase

from apps.barangays.aliases import canonical
from apps.barangays.purok_estimate import norm_name

DATA = Path(__file__).resolve().parents[1] / 'apps' / 'barangays' / 'data' / 'puroks'
POINT_FIELDS = ('lat', 'lng', 'placed_by', 'confidence')


def _rows(name):
    with open(DATA / name, encoding='utf-8', newline='') as fh:
        return list(csv.DictReader(fh))


class ResearchDataTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.points = _rows('purok_points.csv')
        cls.by_key = {(canonical(r['barangay']), r['name']): r for r in cls.points}

    def row(self, barangay, name):
        return self.by_key.get((canonical(barangay), name))

    def test_every_parent_is_a_row_in_the_same_barangay(self):
        missing = [(r['barangay'], r['name'], r['parent']) for r in self.points
                   if r['parent'] and (canonical(r['barangay']), r['parent']) not in self.by_key]
        self.assertEqual(missing, [])

    def test_no_two_rows_share_a_name_in_a_barangay(self):
        seen, twice = set(), []
        for r in self.points:
            key = (canonical(r['barangay']), norm_name(r['name']))
            if key in seen:
                twice.append((r['barangay'], r['name']))
            seen.add(key)
        self.assertEqual(twice, [])

    def test_placed_rows_have_a_confidence_and_how(self):
        half = [(r['barangay'], r['name']) for r in self.points
                if len({bool(r[f].strip()) for f in POINT_FIELDS}) > 1]
        self.assertEqual(half, [])

    def test_variants_point_at_rows(self):
        dangling = [(v['barangay'], v['variant'], v['name']) for v in _rows('name_variants.csv')
                    if (canonical(v['barangay']), v['name']) not in self.by_key]
        self.assertEqual(dangling, [])

    def test_the_2026_10_28_research_is_in(self):
        self.assertEqual(self.row('Cadulawan', 'Purok Boongon')['confidence'], 'medium')
        self.assertEqual(self.row('Manipis', 'Camp 6')['confidence'], 'high')
        self.assertEqual(self.row('Camp IV', 'Purok Sambag')['parent'], 'Sitio Proper')
        self.assertEqual(self.row('Bulacao', 'Upper Kabanayan')['parent'], 'Sitio Kabanayan')
        self.assertEqual(self.row('Dumlog', 'Sitio Bahala')['confidence'], 'low')
