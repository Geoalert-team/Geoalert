"""
Turning a BFP address into a barangay and a purok.

The address is typed by hand, roughly "<place>[, <place>], <barangay>,
Talisay City, Cebu". The barangay is the last barangay-like part, since a
sitio can share a barangay's name ("Purk Ilang-Ilang, San Roque, Linao" is
in Linao). Streets, block and lot numbers are not places and are dropped.
"""
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.history.bfp_link import find_purok, link_address, load_variants, split_address

# The 22 barangays as the shared database spells them
B = ['Biasong', 'Bulacao', 'Cadulawan', 'Camp IV', 'Cansojong', 'Dumlog', 'Jaclupan', 'Lagtang', 'Lawaan I',
     'Lawaan II', 'Lawaan III', 'Linao', 'Maghaway', 'Manipis', 'Mohon', 'Poblacion', 'Pooc', 'San Isidro',
     'San Roque', 'Tabunok', 'Tangke', 'Tapul']


class FakeBarangay:
    def __init__(self, id, name, boundary=None):
        self.id, self.name, self.boundary = id, name, boundary


class SplitAddressTests(SimpleTestCase):
    def test_split(self):
        cases = [
            ('PUROK SAMBAG, LARAY, BRGY SAN ROQUE', ('San Roque', [('purok', 'SAMBAG'), ('', 'LARAY')])),
            ('Purk Ilang-Ilang, San Roque, Linao, Talisay City Cebu',
             ('Linao', [('purok', 'Ilang-Ilang'), ('', 'San Roque')])),
            ('Rizal St., Zone 3, Dumlog, Talisay City, Cebu', ('Dumlog', [('', 'Zone 3')])),
            ('Block 6, Lot 9, Azienda Firenze, Camilla Homes Subd., Maghaway, Talisay City, Cebu',
             ('Maghaway', [('', 'Azienda Firenze'), ('', 'Camilla Homes Subd.')])),
            ('SRP, Lawaan 1, Talisay City, Cebu', ('Lawaan I', [])),
            ('Canizares St. Dumlog, Talisay City Cebu', ('Dumlog', [])),  # barangay at the end of a part
            ('Purok Mangga, Lower Candulawan, Talisay City, Cebu', ('Cadulawan', [('purok', 'Mangga')])),
            ('Bontory, Upper Mohon, Talisay City, Cebu', ('Mohon', [('', 'Bontory')])),
            ('Cebu Southroad, Linao, Talisay Cebu', ('Linao', [])),
            ('Zone 2, Brgy. Biasong, Talisay City', ('Biasong', [('', 'Zone 2')])),
            ('LAWA-AN 1, TALISAY CITY, CEBU', ('Lawaan I', [])),
            ('BRGY DUMLOG', ('Dumlog', [])),
            ('Sitio Napo, Talisay City Cebu', (None, [('sitio', 'Napo')])),
        ]
        for text, expected in cases:
            self.assertEqual(split_address(text, B), expected, text)

    def test_the_last_barangay_wins_even_when_written_upper_or_lower(self):
        # San Roque is also a sitio of Linao; "Upper Linao" is the barangay here
        self.assertEqual(split_address('Purk Ilang-Ilang, San Roque, Upper Linao, Talisay City Cebu', B),
                         ('Linao', [('purok', 'Ilang-Ilang'), ('', 'San Roque')]))

    def test_misspelled_barangays(self):
        self.assertEqual(split_address('Purok Kamunggay, Poblacio, Talisay City, Cebu', B)[0], 'Poblacion')
        self.assertEqual(split_address('Cassare, Casojong, Talisay City Cebu', B)[0], 'Cansojong')


class FindPurokTests(SimpleTestCase):
    def test_find_purok(self):
        self.assertEqual(find_purok([('sitio', 'Libra'), ('purok', 'Kamungay')],
                                    ['Sitio Libra', 'Purok Kamunggay'], {}), 'Purok Kamunggay')
        self.assertEqual(find_purok([('', 'LARAY'), ('purok', 'SAMBAG')], ['Sitio Laray', 'Purok Sambag'], {}),
                         'Purok Sambag')
        self.assertEqual(find_purok([('', 'Paglaum')], ['Sitio Paglaom'], {'paglaum': 'Sitio Paglaom'}),
                         'Sitio Paglaom')
        self.assertIsNone(find_purok([('', 'Zone 3')], ['Purok 3'], {}))
        self.assertIsNone(find_purok([], ['Purok Sambag'], {}))

    def test_load_variants(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'name_variants.csv'
            path.write_text('barangay,variant,name\nDumlog,Paglaum,Sitio Paglaom\n', encoding='utf-8')
            self.assertEqual(load_variants(path), {'dumlog': {'paglaum': 'Sitio Paglaom'}})

    def test_link_address(self):
        roque = FakeBarangay(19, 'San Roque', boundary=object())
        brgy, purok = link_address('PUROK SAMBAG, LARAY, BRGY SAN ROQUE', [roque], {19: ['Purok Sambag']}, {})
        self.assertEqual((brgy, purok), (roque, 'Purok Sambag'))
