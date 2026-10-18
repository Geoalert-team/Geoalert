from django.test import SimpleTestCase

from apps.hazards.views import parse_bbox


class ParseBboxTests(SimpleTestCase):
    def test_valid_box(self):
        box = parse_bbox('123.80,10.20,123.90,10.30')
        self.assertEqual(box.srid, 4326)
        self.assertEqual(box.extent, (123.80, 10.20, 123.90, 10.30))

    def test_not_four_numbers(self):
        for bad in ('1,2,3', 'a,b,c,d', '1,2,3,4,5', ''):
            with self.assertRaises(ValueError):
                parse_bbox(bad)

    def test_corners_the_wrong_way_round(self):
        with self.assertRaises(ValueError):
            parse_bbox('123.90,10.20,123.80,10.30')

    def test_not_degrees(self):
        with self.assertRaises(ValueError):
            parse_bbox('500000,1100000,510000,1110000')
