from pathlib import Path

from django.test import SimpleTestCase

from apps.history import landslide_inventories
from apps.history.landslide_inventories import coolr_events, coolr_slides

ROWS = [{'ev_date': '2023/07/26 00:00:00+00', 'ctry_name': 'Philippines', 'storm_name': 'Typhoon Egay', 'latitude': 17.5, 'longitude': 120.9},
        {'ev_date': '2022/10/28 00:00:00+00', 'ctry_name': 'Philippines', 'storm_name': 'Tropical Storm', 'latitude': 6.9, 'longitude': 124.2},
        {'ev_date': '2022/04/10 00:00:00+00', 'ctry_name': 'Philippines', 'storm_name': 'Tropical Storm', 'latitude': 10.7, 'longitude': 124.85},
        {'ev_date': '2023/08/05 00:00:00+00', 'ctry_name': 'Vietnam', 'storm_name': '', 'latitude': 22.0, 'longitude': 103.0}]


class LandslideInventoriesTests(SimpleTestCase):
    def test_philippine_events_get_their_folds_and_the_rest_are_world(self):
        ev = coolr_events(ROWS)
        self.assertEqual((ev['egay'].fold, ev['egay'].landcover_year), ('egay', 2022))
        self.assertEqual((ev['paeng'].fold, ev['agaton'].fold), ('paeng', 'agaton'))
        self.assertEqual((ev['paeng'].landcover_year, ev['agaton'].landcover_year), (2021, 2021))
        self.assertEqual(ev['egay'].noah_provinces,
                         ('Abra', 'IlocosNorte', 'IlocosSur', 'Apayao', 'Kalinga', 'MountainProvince'))  # R26
        self.assertEqual(ev['paeng'].noah_provinces, ('Maguindanao', 'Cotabato', 'SultanKudarat'))
        world = [e for e in ev.values() if e.region == 'world']
        self.assertEqual(len(world), 1)
        self.assertEqual((world[0].fold, world[0].landcover_year), ('world', 2022))
        self.assertEqual(world[0].key, 'vietnam_20230805')

    def test_slides_keep_their_event_and_point(self):
        s = coolr_slides(ROWS)
        self.assertEqual(s[0], {'event': 'egay', 'lon': 120.9, 'lat': 17.5})
        self.assertEqual(len(s), 4)
        self.assertEqual(s[3]['event'], 'vietnam_20230805')

    def test_an_unknown_philippine_date_is_refused(self):
        with self.assertRaisesMessage(ValueError, 'Unknown Philippine COOLR event 2024-01-01'):
            coolr_events([{**ROWS[0], 'ev_date': '2024/01/01 00:00:00+00'}])

    def test_module_reads_no_geoalert_records(self):
        src = Path(landslide_inventories.__file__).read_text(encoding='utf-8')
        for name in ('HistoricalRecord', 'purok_levels', 'forecast'):
            self.assertNotIn(name, src)
