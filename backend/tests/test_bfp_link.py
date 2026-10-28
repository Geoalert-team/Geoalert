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

from apps.barangays.purok_estimate import norm_name
from apps.history.bfp_link import (explain_link, find_purok, link_address, load_link_index, load_variants,
                                   split_address, street_key, street_parts)

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
            ('Purok Mangga, Lower Candulawan, Talisay City, Cebu',
             ('Cadulawan', [('purok', 'Mangga'), ('', 'Lower Candulawan')])),
            ('Bontory, Upper Mohon, Talisay City, Cebu', ('Mohon', [('', 'Bontory'), ('', 'Upper Mohon')])),
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
                         ('Linao', [('purok', 'Ilang-Ilang'), ('', 'San Roque'), ('', 'Upper Linao')]))

    def test_misspelled_barangays(self):
        self.assertEqual(split_address('Purok Kamunggay, Poblacio, Talisay City, Cebu', B)[0], 'Poblacion')
        self.assertEqual(split_address('Cassare, Casojong, Talisay City Cebu', B)[0], 'Cansojong')

    def test_semicolons_separate_places(self):
        self.assertEqual(split_address('PUROK BAMBOO; PUROK KAIMITO, BRGY MANIPIS', B),
                         ('Manipis', [('purok', 'BAMBOO'), ('purok', 'KAIMITO')]))

    def test_a_leading_house_number_is_dropped(self):
        self.assertEqual(split_address('100 Art Ville, San Isidro, Talisay City Cebu', B),
                         ('San Isidro', [('', 'Art Ville')]))

    def test_upper_or_lower_barangay_is_also_a_place(self):
        # Upper Mohon is a sitio of Mohon; the part still says which barangay it is
        self.assertEqual(split_address('Bontory, Upper Mohon, Talisay City, Cebu', B),
                         ('Mohon', [('', 'Bontory'), ('', 'Upper Mohon')]))
        self.assertEqual(split_address('Purok Mangga, Lower Candulawan, Talisay City, Cebu', B),
                         ('Cadulawan', [('purok', 'Mangga'), ('', 'Lower Candulawan')]))

    def test_barangay_hall_stays_a_place(self):
        self.assertEqual(split_address('Barangay Hall, Mohon, Talisay City, Cebu', B),
                         ('Mohon', [('', 'Barangay Hall')]))


class StreetTests(SimpleTestCase):
    def test_street_parts(self):
        self.assertEqual(street_parts('Nacario St., Tabunok, Talisay City Cebu', B), ['Nacario St.'])
        self.assertEqual(street_parts('609 Burgos St., Dumlog, Talisay City Cebu', B), ['Burgos St.'])
        self.assertEqual(street_parts('Purok Alisto, Tabunok, Talisay City Cebu', B), [])

    def test_street_key(self):
        self.assertEqual(street_key('Nacario St.'), street_key('Nacario Street'))
        self.assertEqual(street_key('Mansueto Rd.'), street_key('Mansueto Road'))
        self.assertEqual(street_key('N. Bacalso Ave.'), street_key('N. Bacalso Avenue'))
        self.assertNotEqual(street_key('Burgos Street'), street_key('Burgos Road'))


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


POINTS = '''barangay,name,kind,parent,lat,lng,placed_by,confidence,sources,note
San Roque,Sitio Laray,sitio,,10.26,123.85,Wikimapia outline,high,,
San Roque,Purok Macopa,purok,Sitio Laray,,,,,,
San Roque,Purok Deep,purok,Purok Macopa,,,,,,
San Roque,Sitio Kimba,sitio,,10.25,123.85,notices,low,,
Lawaan II,Sitio Iba,sitio,,10.25,123.83,notices,low,,
Lawaan II,Purok Rambutan,purok,Sitio Iba,,,,,,
Lagtang,Sitio Iba,sitio,,10.26,123.83,notices,low,,
'''
PLACES = '''barangay,place,kind,area,share
Mohon,Barangay Hall,landmark,Valley View Village,1.0
San Roque,Cebu Evergreen Memorial Park,landmark,Sitio Kimba,1.0
Lawaan I,Lawaan National High School,landmark,Near Lawaan Elementary School,1.0
Tabunok,Nacario Street,street,Purok Mabini,0.8
Tabunok,Victoria Street,street,Purok Mabini,0.74
Tabunok,Colis Street,street,Purok Mabini,0.75
'''


def index_from(points=POINTS, variants='barangay,variant,name\n', places=PLACES):
    with tempfile.TemporaryDirectory() as d:
        for name, text in (('purok_points.csv', points), ('name_variants.csv', variants),
                           ('place_areas.csv', places)):
            (Path(d) / name).write_text(text, encoding='utf-8')
        return load_link_index(Path(d))


class LinkIndexTests(SimpleTestCase):
    def test_an_unplaced_purok_maps_to_its_nearest_placed_sitio(self):
        index = index_from()
        self.assertEqual(index['san roque']['macopa'], 'Sitio Laray')
        self.assertEqual(index.rule('San Roque', 'macopa'), 'sitio')
        # Unplaced under unplaced: up to the first placed one
        self.assertEqual(index['san roque'][norm_name('Purok Deep')], 'Sitio Laray')

    def test_a_variant_beats_a_sitio_fallback_for_the_same_key(self):
        index = index_from(variants='barangay,variant,name\nSan Roque,Macopa,Sitio Kimba\n')
        self.assertEqual(index['san roque']['macopa'], 'Sitio Kimba')
        self.assertEqual(index.rule('San Roque', 'macopa'), 'purok')

    def test_streets_below_the_share_are_left_out(self):
        tabunok = index_from().keys_for('Tabunok')
        self.assertNotIn(street_key('Victoria Street'), tabunok)
        self.assertEqual(tabunok[street_key('Colis Street')], 'Purok Mabini')

    def test_missing_files_are_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_link_index(Path(d)), {})


class ExplainLinkTests(SimpleTestCase):
    ROQUE, MOHON, TABUNOK = FakeBarangay(19, 'San Roque', 1), FakeBarangay(15, 'Mohon', 1), FakeBarangay(20, 'Tabunok', 1)
    TAPUL, LAGTANG, LAWAAN2 = FakeBarangay(22, 'Tapul', 1), FakeBarangay(8, 'Lagtang', 1), FakeBarangay(10, 'Lawaan II', 1)
    PUROKS = {19: ['Sitio Laray', 'Sitio Kimba', 'Purok Sambag'], 15: ['Valley View Village'], 20: ['Purok Mabini'],
              22: ['Sitio Napo'], 8: ['Sitio Iba'], 10: ['Sitio Iba']}

    def explain(self, text):
        barangays = [self.ROQUE, self.MOHON, self.TABUNOK, self.TAPUL, self.LAGTANG, self.LAWAAN2]
        return explain_link(text, barangays, self.PUROKS, index_from())

    def test_explain_link_rules(self):
        cases = [
            ('PUROK MACOPA, LARAY, BRGY SAN ROQUE', (self.ROQUE, 'Sitio Laray', 'purok')),
            ('Purok Macopa, San Roque, Talisay City Cebu', (self.ROQUE, 'Sitio Laray', 'sitio')),
            ('Barangay Hall, Mohon, Talisay City, Cebu', (self.MOHON, 'Valley View Village', 'landmark')),
            ('Evergreen SRP, Brgy San Roque, Talisay City, Cebu', (self.ROQUE, 'Sitio Kimba', 'landmark')),
            ('Nacario St., Tabunok, Talisay City Cebu', (self.TABUNOK, 'Purok Mabini', 'street')),
            ('Tabunok, Talisay City Cebu', (self.TABUNOK, None, '')),
        ]
        for text, expected in cases:
            self.assertEqual(self.explain(text), expected, text)

    def test_a_landmark_typed_with_its_barangay_name_still_matches(self):
        lawaan = FakeBarangay(11, 'Lawaan I', 1)
        found = explain_link('LAWAAN 1 NATIONAL HIGH SCHOOL, BRGY LAWAAN 1', [lawaan],
                             {11: ['Near Lawaan Elementary School']}, index_from())
        self.assertEqual(found, (lawaan, 'Near Lawaan Elementary School', 'landmark'))

    def test_written_names_beat_fallbacks(self):
        # Macopa's sitio is Laray, but the address says Kimba
        self.assertEqual(self.explain('Purok Macopa, Kimba, San Roque, Talisay City Cebu'),
                         (self.ROQUE, 'Sitio Kimba', 'purok'))

    def test_no_barangay_takes_the_one_barangay_with_the_name(self):
        self.assertEqual(self.explain('Sitio Napo, Talisay City Cebu'), (self.TAPUL, 'Sitio Napo', 'purok'))
        # Iba is in Lagtang and Lawaan II; only Lawaan II also has Purok Rambutan
        self.assertEqual(self.explain('Sitio Iba, Purok Rambutan, Talisay City, Cebu'),
                         (self.LAWAAN2, 'Sitio Iba', 'purok'))

    def test_no_barangay_and_two_candidates_stays_unplaced(self):
        self.assertEqual(self.explain('Sitio Iba, Talisay City'), (None, None, ''))
