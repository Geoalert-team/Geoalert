"""
Employee IDs are given by the system: the role's prefix and the next number
for it (DRRMO-0001, BRGY-0001, ...). They can't be typed or edited through
the admin API, survive a role change, and are unique in the database.
Position is free text.
"""
import importlib
from datetime import timedelta
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.gis.geos import MultiPolygon
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Role, User, next_employee_id
from apps.admin_dashboard.views import UserDetailView, UserListCreateView
from apps.barangays.models import Barangay
from tests.fire_setup import box


class EmployeeIdTests(TestCase):
    def setUp(self):
        self.roles = {name: Role.objects.get_or_create(name=name)[0] for name in
                      ('System_Admin', 'DRRMO_Officer', 'Barangay_Personnel', 'BFP_Personnel')}
        self.admin = User.objects.create_user(
            email='admin@test.ph', password='x', full_name='Admin', role=self.roles['System_Admin'])
        self.barangay = Barangay.objects.create(name='Home', municipality='Talisay',
                                                boundary=MultiPolygon(box(0, 0, 1, 1), srid=4326))

    def call(self, view, method, body=None, **kwargs):
        factory = APIRequestFactory()
        request = getattr(factory, method)('/', body or {}, format='json')
        force_authenticate(request, user=self.admin)
        return view.as_view()(request, **kwargs)

    def create(self, email, role, **extra):
        body = {'first_name': 'Juan', 'last_name': 'Dela Cruz', 'email': email,
                'phone': '09171234567', 'position': 'Office Staff',
                'role_id': self.roles[role].id, **extra}
        if role == 'Barangay_Personnel':
            body['assigned_barangay_id'] = self.barangay.id
        response = self.call(UserListCreateView, 'post', body)
        self.assertEqual(response.status_code, 201, response.data)
        return response.data['user']

    # ---------- Assigned on create ----------

    def test_each_role_counts_on_its_own(self):
        self.assertEqual(self.admin.employee_id, 'ADMIN-0001')
        self.assertEqual(self.create('a@test.ph', 'DRRMO_Officer')['employee_id'], 'DRRMO-0001')
        self.assertEqual(self.create('b@test.ph', 'DRRMO_Officer')['employee_id'], 'DRRMO-0002')
        self.assertEqual(self.create('c@test.ph', 'BFP_Personnel')['employee_id'], 'BFP-0001')
        self.assertEqual(self.create('d@test.ph', 'System_Admin')['employee_id'], 'ADMIN-0002')

    def test_barangay_personnel_get_brgy(self):
        self.assertEqual(self.create('e@test.ph', 'Barangay_Personnel')['employee_id'], 'BRGY-0001')

    def test_numbering_continues_past_the_highest(self):
        User.objects.create_user(email='old@test.ph', password='x', full_name='Old',
                                 role=self.roles['DRRMO_Officer'], employee_id='DRRMO-0041')
        self.assertEqual(next_employee_id('DRRMO_Officer'), 'DRRMO-0042')
        self.assertEqual(self.create('f@test.ph', 'DRRMO_Officer')['employee_id'], 'DRRMO-0042')

    def test_a_typed_id_is_ignored(self):
        user = self.create('g@test.ph', 'DRRMO_Officer', employee_id='TC-2026-0142')
        self.assertEqual(user['employee_id'], 'DRRMO-0001')

    def test_position_is_free_text(self):
        user = self.create('h@test.ph', 'BFP_Personnel', position='Fire Truck Driver (Volunteer)')
        self.assertEqual(user['position'], 'Fire Truck Driver (Volunteer)')

    # ---------- Kept after create ----------

    def test_editing_cannot_change_it(self):
        user = self.create('i@test.ph', 'DRRMO_Officer')
        response = self.call(UserDetailView, 'put', {'employee_id': 'MINE-1'}, pk=user['id'])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(User.objects.get(pk=user['id']).employee_id, 'DRRMO-0001')

    def test_a_role_change_keeps_it(self):
        user = self.create('j@test.ph', 'DRRMO_Officer')
        response = self.call(UserDetailView, 'put', {'role_id': self.roles['BFP_Personnel'].id}, pk=user['id'])
        self.assertEqual(response.status_code, 200, response.data)
        moved = User.objects.get(pk=user['id'])
        self.assertEqual((moved.role.name, moved.employee_id), ('BFP_Personnel', 'DRRMO-0001'))

    def test_no_role_waits_until_one_is_given(self):
        user = User.objects.create_user(email='k@test.ph', password='x', full_name='No Role')
        self.assertIsNone(user.employee_id)
        user.role = self.roles['BFP_Personnel']
        user.save(update_fields=['role'])
        self.assertEqual(User.objects.get(pk=user.pk).employee_id, 'BFP-0001')

    # ---------- Unique ----------

    def test_the_database_refuses_a_duplicate(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(email='l@test.ph', password='x', full_name='Copy',
                                     role=self.roles['DRRMO_Officer'], employee_id='ADMIN-0001')

    def test_a_clash_takes_the_next_number(self):
        # Another account takes DRRMO-0001 after this one picked it but before it was stored
        real = next_employee_id
        picks = []

        def stale(role_name):
            picks.append(role_name)
            if len(picks) == 1:
                User.objects.filter(pk=self.admin.pk).update(employee_id='DRRMO-0001')
                return 'DRRMO-0001'
            return real(role_name)

        with mock.patch('apps.accounts.models.next_employee_id', side_effect=stale):
            user = User.objects.create_user(email='m@test.ph', password='x', full_name='Racer',
                                            role=self.roles['DRRMO_Officer'])
        self.assertEqual(user.employee_id, 'DRRMO-0002')
        self.assertEqual(len(picks), 2)


class NumberExistingAccountsTests(TestCase):
    """Migration 0005: every older account is numbered per role, oldest first."""

    def test_numbers_by_role_in_creation_order(self):
        roles = {name: Role.objects.get_or_create(name=name)[0] for name in
                 ('System_Admin', 'DRRMO_Officer', 'BFP_Personnel')}
        start = timezone.now() - timedelta(days=30)
        made = []
        for i, (email, role, typed) in enumerate([
            ('d1@test.ph', 'DRRMO_Officer', None),
            ('a1@test.ph', 'System_Admin', None),
            ('d2@test.ph', 'DRRMO_Officer', None),
            ('a2@test.ph', 'System_Admin', '3241'),
            ('f1@test.ph', 'BFP_Personnel', None),
            ('none@test.ph', None, None),
        ]):
            user = User.objects.create_user(email=email, password='x', full_name=email,
                                            role=roles.get(role))
            # As they were before: typed by hand or blank, made on different days
            User.objects.filter(pk=user.pk).update(employee_id=typed, created_at=start + timedelta(days=i))
            made.append(email)

        migration = importlib.import_module('apps.accounts.migrations.0005_number_employee_ids')
        migration.number_accounts(django_apps, None)

        ids = dict(User.objects.filter(email__in=made).values_list('email', 'employee_id'))
        self.assertEqual(ids, {
            'd1@test.ph': 'DRRMO-0001',
            'a1@test.ph': 'ADMIN-0001',
            'd2@test.ph': 'DRRMO-0002',
            'a2@test.ph': 'ADMIN-0002',
            'f1@test.ph': 'BFP-0001',
            'none@test.ph': None,
        })
