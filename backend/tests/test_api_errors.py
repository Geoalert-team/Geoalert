import json

from django.db import IntegrityError, OperationalError
from django.test import RequestFactory, SimpleTestCase

from utils.errors import ApiErrorMiddleware


class ApiErrorMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.mw = ApiErrorMiddleware(lambda request: None)
        self.rf = RequestFactory()

    def run_error(self, exc, path='/api/hazards/types/'):
        with self.assertLogs('geoalert.api', level='ERROR'):
            return self.mw.process_exception(self.rf.get(path), exc)

    def test_database_unreachable_is_503_and_says_nothing_saved(self):
        r = self.run_error(OperationalError('max clients reached'))
        body = json.loads(r.content)
        self.assertEqual(r.status_code, 503)
        self.assertIn('Nothing was saved', body['error'])

    def test_constraint_violation_quotes_a_reference(self):
        r = self.run_error(IntegrityError('violates check constraint'))
        body = json.loads(r.content)
        self.assertEqual(r.status_code, 500)
        self.assertIn(body['reference'], body['error'])

    def test_unexpected_error_hides_internals(self):
        r = self.run_error(ValueError('secret internal detail'))
        body = json.loads(r.content)
        self.assertEqual(r.status_code, 500)
        self.assertNotIn('secret', body['error'])

    def test_non_api_paths_keep_django_handling(self):
        self.assertIsNone(self.mw.process_exception(self.rf.get('/admin/'), ValueError('x')))
