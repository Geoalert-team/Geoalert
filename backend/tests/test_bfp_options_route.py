"""
The fire close form reads its lists (property types by category, alarm
levels) from /api/history/bfp-options/, DRRMO only. No database.
"""
from django.test import SimpleTestCase
from django.urls import resolve
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.hazards.fire_close_views import BfpOptionsView
from apps.history.bfp import ALARM_LEVELS, PROPERTY_TYPES


class Role:
    def __init__(self, name):
        self.name = name


class User:
    is_authenticated = True
    is_active = True

    def __init__(self, role):
        self.role = Role(role)


def get(role):
    request = APIRequestFactory().get('/api/history/bfp-options/')
    force_authenticate(request, user=User(role))
    return BfpOptionsView.as_view()(request)


class BfpOptionsRouteTests(SimpleTestCase):
    def test_the_url_serves_the_options(self):
        self.assertIs(resolve('/api/history/bfp-options/').func.view_class, BfpOptionsView)

    def test_an_officer_gets_the_bfp_lists(self):
        response = get('DRRMO_Officer')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'property_types': PROPERTY_TYPES, 'alarm_levels': ALARM_LEVELS})

    def test_barangay_personnel_do_not(self):
        self.assertEqual(get('Barangay_Personnel').status_code, 403)
