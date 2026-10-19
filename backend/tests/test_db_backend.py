from unittest import mock

from django.db import connections
from django.test import SimpleTestCase

from utils.db_backend import base as db_backend

PARENT_CONNECT = (
    'django.contrib.gis.db.backends.postgis.base.DatabaseWrapper.get_new_connection'
)


@mock.patch.object(db_backend.time, 'sleep')
class ConnectRetryTests(SimpleTestCase):
    def setUp(self):
        self.wrapper = connections["default"]
        self.handshake_error = self.wrapper.Database.OperationalError(
            'SSL SYSCALL error: EOF detected'
        )

    def test_uses_retrying_backend(self, _sleep):
        self.assertIsInstance(self.wrapper, db_backend.DatabaseWrapper)

    def test_retries_once_after_a_dropped_handshake(self, sleep):
        with mock.patch(PARENT_CONNECT, side_effect=[self.handshake_error, 'conn']) as parent:
            self.assertEqual(self.wrapper.get_new_connection({}), 'conn')
        self.assertEqual(parent.call_count, 2)
        sleep.assert_called_once()

    def test_gives_up_after_the_second_failure(self, _sleep):
        with mock.patch(PARENT_CONNECT, side_effect=self.handshake_error) as parent:
            with self.assertRaises(self.wrapper.Database.OperationalError):
                self.wrapper.get_new_connection({})
        self.assertEqual(parent.call_count, db_backend.CONNECT_ATTEMPTS)

    def test_does_not_retry_other_errors(self, _sleep):
        with mock.patch(PARENT_CONNECT, side_effect=ValueError('bad params')) as parent:
            with self.assertRaises(ValueError):
                self.wrapper.get_new_connection({})
        self.assertEqual(parent.call_count, 1)


class TestDatabaseTeardownTests(SimpleTestCase):
    """
    The pooler keeps idle server connections to the test database after the
    test run disconnects, so a plain DROP DATABASE failed with "being
    accessed by other users" and left test_postgres behind on Supabase.
    """

    def test_uses_forcing_creation(self):
        self.assertIsInstance(connections['default'].creation, db_backend.DatabaseCreation)

    def test_drop_closes_lingering_connections(self):
        creation = connections['default'].creation
        cursor = mock.MagicMock()
        with mock.patch.object(type(creation), '_nodb_cursor') as nodb:
            nodb.return_value.__enter__.return_value = cursor
            creation._destroy_test_db('test_postgres', verbosity=0)
        cursor.execute.assert_called_once_with('DROP DATABASE "test_postgres" WITH (FORCE)')
