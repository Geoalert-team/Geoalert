"""
PostGIS backend that retries a failed connect once.

The Supabase pooler occasionally drops a connection during the SSL
handshake ("SSL SYSCALL error: EOF detected"). The next attempt almost
always succeeds, so without a retry one dropped handshake becomes a 500
for whichever request happened to open the connection.

Retrying here is safe: the failure happens before any query is sent, so
nothing can run twice. Only the connect is retried, never a query.

It also drops the test database WITH (FORCE). The pooler keeps idle server
connections to a database after its client disconnects, so the plain DROP
DATABASE Django runs after the tests failed with "being accessed by other
users" and left test_postgres on Supabase. FORCE (PostgreSQL 13+) closes
those connections first. It would also end another developer's test run
on the same test database, but two runs sharing one already break each
other: the second deletes the first's database when it starts.
"""

import logging
import time

from django.contrib.gis.db.backends.postgis.base import (
    DatabaseWrapper as PostGISDatabaseWrapper,
)
from django.db.backends.postgresql.creation import (
    DatabaseCreation as PostgreSQLDatabaseCreation,
)

logger = logging.getLogger(__name__)

CONNECT_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 0.5


class DatabaseCreation(PostgreSQLDatabaseCreation):
    def _destroy_test_db(self, test_database_name, verbosity):
        # Same as Django's, plus FORCE: see the module docstring
        with self._nodb_cursor() as cursor:
            cursor.execute(
                'DROP DATABASE %s WITH (FORCE)' % self.connection.ops.quote_name(test_database_name)
            )


class DatabaseWrapper(PostGISDatabaseWrapper):
    creation_class = DatabaseCreation

    def get_new_connection(self, conn_params):
        for attempt in range(1, CONNECT_ATTEMPTS + 1):
            try:
                return super().get_new_connection(conn_params)
            except self.Database.OperationalError as exc:
                if attempt == CONNECT_ATTEMPTS:
                    raise
                logger.warning(
                    'Database connect failed (attempt %d of %d), retrying: %s',
                    attempt, CONNECT_ATTEMPTS, str(exc).strip(),
                )
                time.sleep(RETRY_DELAY_SECONDS)
