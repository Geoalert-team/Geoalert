from datetime import datetime, timezone as dt_tz

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.rainwatch.models import RainForecastRun, RainForecastSeries, RainWatchRules

INIT = datetime(2026, 11, 18, 0, 0, tzinfo=dt_tz.utc)


class RainWatchModelsTest(TestCase):
    def test_migration_seeds_balanced_rules(self):
        r = RainWatchRules.current()
        self.assertEqual(list(r.flood_dry), [30, 60, 120])
        self.assertEqual(list(r.flood_wet), [20, 40, 80])
        self.assertEqual(list(r.slide_dry), [50, 80, 120])
        self.assertEqual(list(r.slide_wet), [25, 40, 60])
        self.assertEqual((r.wet_14day_mm, r.flood_exposure_min, r.steep_share_min, r.stale_hours),
                         (156.5, 190, 0.40, 12))
        self.assertEqual(r.note, 'Balanced (backtest 2026-11-18)')

    def test_newest_rules_row_wins(self):
        old = RainWatchRules.current()
        new = RainWatchRules.objects.create(
            flood_dry=[40, 80, 160], flood_wet=old.flood_wet, slide_dry=old.slide_dry,
            slide_wet=old.slide_wet, wet_14day_mm=old.wet_14day_mm,
            flood_exposure_min=old.flood_exposure_min, steep_share_min=old.steep_share_min,
            stale_hours=old.stale_hours, note='test')
        self.assertEqual(RainWatchRules.current().pk, new.pk)
        self.assertEqual(list(RainWatchRules.current().flood_dry), [40, 80, 160])

    def test_run_unique_per_source_and_init(self):
        RainForecastRun.objects.create(source='gfs-nomads', init_time=INIT, hours=96)
        with self.assertRaises(IntegrityError), transaction.atomic():
            RainForecastRun.objects.create(source='gfs-nomads', init_time=INIT, hours=96)
        RainForecastRun.objects.create(source='gfs-dynamical', init_time=INIT, hours=96)

    def test_runs_series_and_rules_are_insert_only(self):
        run = RainForecastRun.objects.create(source='gfs-nomads', init_time=INIT, hours=2)
        with self.assertRaises(ValueError):
            run.save()
        s = RainForecastSeries.objects.create(run=run, lat='10.25', lon='123.75',
                                              first_hour_start=INIT, mm_per_hour=[0.0, 1.5])
        with self.assertRaises(ValueError):
            s.save()
        with self.assertRaises(ValueError):
            RainWatchRules.current().save()
