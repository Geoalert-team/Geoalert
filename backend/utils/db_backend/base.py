"""
PostGIS backend that retries a failed connect once.

The Supabase pooler occasionally drops a connection during the SSL
handshake ("SSL SYSCALL error: EOF detected"). The next attempt almost
always succeeds, so without a retry one dropped handshake becomes a 500
for whichever request happened to open the connection.

Retrying here is safe: the failure happens before any query is sent, so
nothing can run twice. Only the connect is retried, never a query.
"""

import logging
import time

from django.contrib.gis.db.backends.postgis.base import (
    DatabaseWrapper as PostGISDatabaseWrapper,
)

logger = logging.getLogger(__name__)

CONNECT_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 0.5


class DatabaseWrapper(PostGISDatabaseWrapper):
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
