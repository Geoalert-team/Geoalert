"""ModelFit: every automatic retraining attempt, and which fit is live."""
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase

from apps.barangays.models import Purok
from apps.history import model_fits
from apps.history.model_fits import LANDSLIDE_SEASON_LOCK, record_attempt
from apps.history.models import ModelFit


def payload(result='switched', hazard='fire', outlines='v1', built_at='2027-02-02T03:00:00+08:00'):
    return {
        'hazard': hazard, 'result': result, 'reason': 'r',
        'model': {'version': 'x@1', 'outlines_version': outlines, 'built_at': built_at},
        'report': {'version': 'x@1'},
    }


def second_payload(hazard='fire'):
    p = payload(hazard=hazard)
    p['model']['version'] = p['report']['version'] = 'x@2'
    return p


MANILA = ZoneInfo('Asia/Manila')


def in_month(month):
    """Run as on the 5th of `month` 2027 in Manila (the server's clock for the flood season lock)."""
    return mock.patch('django.utils.timezone.localtime', return_value=datetime(2027, month, 5, 3, 17, tzinfo=MANILA))


def freeze_manila(year, month, day):
    """Run as on that day in Manila (the server's clock for the season locks)."""
    return mock.patch('django.utils.timezone.localtime', return_value=datetime(year, month, day, 3, 17, tzinfo=MANILA))


class ModelFitTests(TestCase):
    def test_switched_fit_becomes_live(self):
        model_fits.record_attempt(payload(), 'v1')
        fit = model_fits.live_fit('fire')
        self.assertEqual(fit.version, 'x@1')
        self.assertTrue(fit.is_live)

    def test_second_switch_replaces_the_first(self):
        a = model_fits.record_attempt(payload(), 'v1')
        b = model_fits.record_attempt(second_payload(), 'v1')
        a.refresh_from_db()
        self.assertFalse(a.is_live)
        self.assertTrue(b.is_live)
        self.assertEqual(model_fits.live_fit('fire').pk, b.pk)
        self.assertEqual(ModelFit.objects.filter(hazard='fire', is_live=True).count(), 1)

    def test_kept_fit_is_saved_not_live(self):
        fit = model_fits.record_attempt(payload(result='kept'), 'v1')
        self.assertIsNone(model_fits.live_fit('fire'))
        fit.refresh_from_db()
        self.assertEqual(fit.model['version'], 'x@1')

    def test_stale_switched_fit_is_skipped(self):
        fit = model_fits.record_attempt(payload(outlines='old'), 'v1')
        self.assertEqual(fit.result, 'skipped')
        self.assertEqual(fit.reason, model_fits.STALE_FIT)
        self.assertFalse(fit.is_live)
        self.assertIsNone(model_fits.live_fit('fire'))

    def test_not_tried_needs_no_model(self):
        fit = model_fits.record_attempt({'hazard': 'flood', 'result': 'not_tried', 'reason': '7 of 100 …'}, 'v1')
        fit.refresh_from_db()
        self.assertIsNone(fit.model)
        self.assertIsNone(fit.report)
        self.assertEqual(fit.result, 'not_tried')

    def test_bad_payloads_raise(self):
        def bad(**changes):
            p = payload()
            p.update(changes)
            return p
        cases = [
            bad(hazard='quake'),  # landslide is a hazard since history 0014
            bad(result='won'),
            bad(reason=''),
            bad(reason='x' * 501),
            {k: v for k, v in payload().items() if k != 'model'},
            bad(report={'version': 'x@2'}),
            payload(built_at='not a date'),
        ]
        for p in cases:
            with self.assertRaises(ValueError, msg=p):
                model_fits.record_attempt(p, 'v1')
        self.assertEqual(ModelFit.objects.count(), 0)

    def test_check_refusal_raises(self):
        with self.assertRaises(ValueError) as ctx:
            model_fits.record_attempt(payload(), 'v1', check=lambda *a: 'cannot read')
        self.assertEqual(str(ctx.exception), 'cannot read')
        self.assertEqual(ModelFit.objects.count(), 0)

    def test_check_runs_only_for_switched_on_current_map(self):
        seen = []

        def check(*args):
            seen.append(args)

        model_fits.record_attempt(payload(result='kept'), 'v1', check=check)
        model_fits.record_attempt(payload(outlines='old'), 'v1', check=check)
        self.assertEqual(seen, [])
        model_fits.record_attempt(payload(), 'v1', check=check)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], 'fire')
        self.assertEqual(seen[0][3], 'v1')

    def test_one_live_fit_per_hazard(self):
        ModelFit.objects.create(hazard='fire', result='switched', reason='r', is_live=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ModelFit.objects.create(hazard='fire', result='switched', reason='r', is_live=True)
        ModelFit.objects.create(hazard='flood', result='switched', reason='r', is_live=True)

    def test_newer_is_fit(self):
        fit = model_fits.record_attempt(payload(result='kept'), 'v1')

        def file_at(built):
            return {'built_at': built}

        self.assertFalse(model_fits.newer_is_fit({'built_at': 'x'}, None))
        self.assertTrue(model_fits.newer_is_fit(None, fit))
        self.assertTrue(model_fits.newer_is_fit({}, fit))
        self.assertFalse(model_fits.newer_is_fit(file_at('2027-03-01T00:00:00+08:00'), fit))
        self.assertTrue(model_fits.newer_is_fit(file_at('2027-01-01T00:00:00+08:00'), fit))
        self.assertTrue(model_fits.newer_is_fit(file_at('2027-02-02T03:00:00+08:00'), fit))

    # Final review I3: the flood map never changes in the middle of a wet season
    def test_a_flood_switch_in_the_wet_season_is_kept(self):
        with in_month(2):
            live = model_fits.record_attempt(payload(hazard='flood'), 'v1')
        with in_month(9):
            fit = model_fits.record_attempt(second_payload(hazard='flood'), 'v1')
        fit.refresh_from_db()
        self.assertEqual((fit.result, fit.reason, fit.is_live), ('kept', model_fits.FLOOD_SEASON_LOCK, False))
        self.assertEqual(fit.model['version'], 'x@2')
        self.assertEqual(model_fits.live_fit('flood').pk, live.pk)
        self.assertEqual(model_fits.FLOOD_SEASON_LOCK, 'Flood maps change only between January and May')

    def test_a_flood_switch_in_february_goes_live(self):
        with in_month(2):
            fit = model_fits.record_attempt(payload(hazard='flood'), 'v1')
        self.assertEqual((fit.result, fit.reason, fit.is_live), ('switched', 'r', True))
        self.assertEqual(model_fits.live_fit('flood').pk, fit.pk)

    def test_the_flood_lock_runs_june_to_december(self):
        for month in range(1, 13):
            ModelFit.objects.all().delete()
            with self.subTest(month=month), in_month(month):
                fit = model_fits.record_attempt(payload(hazard='flood'), 'v1')
                self.assertEqual(fit.is_live, month <= 5)
                self.assertEqual(fit.result, 'switched' if month <= 5 else 'kept')

    def test_switch_outside_january_to_may_is_kept(self):  # model_fits.record_attempt, Manila July
        self.switched_landslide_payload = payload(hazard='landslide', outlines='v')
        in_use = payload(hazard='landslide', outlines='v')
        in_use['model']['version'] = in_use['report']['version'] = 'x@0'
        with freeze_manila(2027, 2, 1):
            live = model_fits.record_attempt(in_use, 'v', check=None)
        with freeze_manila(2027, 7, 1):
            fit = record_attempt(self.switched_landslide_payload, 'v', check=None)
        self.assertEqual((fit.result, fit.reason, fit.is_live), ('kept', LANDSLIDE_SEASON_LOCK, False))
        fit.refresh_from_db()
        self.assertEqual(fit.model['version'], 'x@1')
        self.assertEqual(model_fits.live_fit('landslide').pk, live.pk)  # the live map unchanged
        self.assertEqual(LANDSLIDE_SEASON_LOCK, 'Landslide maps change only between January and May')

    def test_the_landslide_lock_runs_june_to_december(self):
        for month in range(1, 13):
            ModelFit.objects.all().delete()
            with self.subTest(month=month), in_month(month):
                fit = model_fits.record_attempt(payload(hazard='landslide'), 'v1')
                self.assertEqual(fit.is_live, month <= 5)
                self.assertEqual((fit.result, fit.reason), ('switched', 'r') if month <= 5
                                 else ('kept', LANDSLIDE_SEASON_LOCK))

    def test_a_landslide_switch_does_not_touch_the_flood_map(self):
        with in_month(3):
            flood = model_fits.record_attempt(payload(hazard='flood'), 'v1')
            landslide = model_fits.record_attempt(payload(hazard='landslide'), 'v1')
        self.assertEqual(model_fits.live_fit('flood').pk, flood.pk)
        self.assertEqual(model_fits.live_fit('landslide').pk, landslide.pk)

    def test_the_database_takes_landslide_and_refuses_another_hazard(self):
        ModelFit.objects.create(hazard='landslide', result='not_tried', reason='2 of 30 …')
        ModelFit.objects.create(hazard='landslide', result='switched', reason='r', is_live=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ModelFit.objects.create(hazard='landslide', result='switched', reason='r', is_live=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ModelFit.objects.create(hazard='quake', result='not_tried', reason='r')

    def test_site_check_reads_a_landslide_fit_as_the_site_does(self):
        from apps.history import landslide_purok

        with mock.patch.object(landslide_purok, 'parse', return_value='cannot read') as parse:
            self.assertEqual(model_fits.site_check('landslide', {'m': 1}, {'r': 1}, 'v1'), 'cannot read')
        parse.assert_called_once_with({'m': 1}, {'r': 1}, 'v1')
        with mock.patch.object(landslide_purok, 'parse', return_value=object()):
            self.assertIsNone(model_fits.site_check('landslide', {}, {}, 'v1'))

    def test_fire_switches_in_any_month(self):
        for month in range(1, 13):
            with self.subTest(month=month), in_month(month):
                fit = model_fits.record_attempt(payload(), 'v1')
                self.assertEqual((fit.result, fit.is_live), ('switched', True))
                self.assertEqual(model_fits.live_fit('fire').pk, fit.pk)

    def test_make_live_only_switched_on_current_map(self):
        a = model_fits.record_attempt(payload(), 'v1')
        b = model_fits.record_attempt(second_payload(), 'v1')
        model_fits.make_live(a, 'v1')
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertTrue(a.is_live)
        self.assertFalse(b.is_live)
        kept = model_fits.record_attempt(payload(result='kept'), 'v1')
        with self.assertRaises(ValueError):
            model_fits.make_live(kept, 'v1')
        old = ModelFit.objects.create(hazard='fire', result='switched', reason='r', outlines_version='old')
        with self.assertRaises(ValueError):
            model_fits.make_live(old, 'v1')
        a.refresh_from_db()
        self.assertTrue(a.is_live)

    def test_attempts_newest_first_without_bodies(self):
        for i in range(3):
            model_fits.record_attempt({'hazard': 'flood', 'result': 'not_tried', 'reason': f'n{i}'}, 'v1')
        rows = model_fits.attempts(limit=2)
        self.assertEqual([r['reason'] for r in rows], ['n2', 'n1'])
        self.assertEqual(set(rows[0]), {'hazard', 'result', 'reason', 'version', 'created_at', 'is_live'})

    def test_admin_action_undoes(self):
        a = model_fits.record_attempt(payload(), 'v1')
        model_fits.record_attempt(second_payload(), 'v1')
        model_admin = admin.site._registry[ModelFit]
        user = get_user_model().objects.create_superuser(email='r@example.com', password='x', full_name='Root')
        request = RequestFactory().post('/admin/')
        request.user = user
        request.session = {}
        request._messages = FallbackStorage(request)
        with mock.patch.object(Purok, 'outlines_version', return_value='v1'), \
                mock.patch('apps.history.admin.site_check', return_value=None):
            model_admin.make_live_action(request, ModelFit.objects.filter(pk=a.pk))
        a.refresh_from_db()
        self.assertTrue(a.is_live)
        self.assertEqual(model_fits.live_fit('fire').pk, a.pk)

    def test_admin_list_leaves_out_the_bodies(self):
        # Final review P1: the changelist never loads every row's model and report
        model_fits.record_attempt(payload(), 'v1')
        model_admin = admin.site._registry[ModelFit]
        request = RequestFactory().get('/admin/')
        request.user = get_user_model().objects.create_superuser(email='l@example.com', password='x', full_name='L')
        fit = model_admin.get_queryset(request).get()
        self.assertEqual(fit.get_deferred_fields(), {'model', 'report'})

    def test_admin_undo_from_the_list_reads_the_fit(self):
        a = model_fits.record_attempt(payload(), 'v1')
        model_fits.record_attempt(second_payload(), 'v1')
        model_admin = admin.site._registry[ModelFit]
        request = RequestFactory().post('/admin/')
        request.user = get_user_model().objects.create_superuser(email='u@example.com', password='x', full_name='U')
        request.session = {}
        request._messages = FallbackStorage(request)
        with mock.patch.object(Purok, 'outlines_version', return_value='v1'), \
                mock.patch('apps.history.admin.site_check', return_value=None) as check:
            model_admin.make_live_action(request, model_admin.get_queryset(request).filter(pk=a.pk))
        self.assertEqual(check.call_args[0][1], a.model)
        self.assertEqual(check.call_args[0][2], a.report)
        self.assertEqual(model_fits.live_fit('fire').pk, a.pk)

    def test_undo_action_is_superuser_only(self):
        from django.contrib.auth.models import Permission
        model_admin = admin.site._registry[ModelFit]
        User = get_user_model()
        staff = User.objects.create_user(email='s@example.com', password='x', full_name='Staff', is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename='view_modelfit'))
        root = User.objects.create_superuser(email='r2@example.com', password='x', full_name='Root')

        def request_for(user):
            request = RequestFactory().get('/admin/')
            request.user = user
            return request

        self.assertNotIn('make_live_action', model_admin.get_actions(request_for(User.objects.get(pk=staff.pk))))
        self.assertIn('make_live_action', model_admin.get_actions(request_for(root)))
