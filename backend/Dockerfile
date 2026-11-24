# The backend as Render runs it: Debian 12's GDAL 3.6, which Django 5.2
# supports. Python 3.11, since Django 6 (which needs 3.12) isn't used yet.
FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgdal32 libgeos-c1v5 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s "$(ls /usr/lib/*-linux-gnu/libgdal.so.* | head -n 1)" /usr/local/lib/libgdal.so \
    && ln -s "$(ls /usr/lib/*-linux-gnu/libgeos_c.so.* | head -n 1)" /usr/local/lib/libgeos_c.so

ENV PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    GDAL_LIBRARY_PATH=/usr/local/lib/libgdal.so \
    GEOS_LIBRARY_PATH=/usr/local/lib/libgeos_c.so

WORKDIR /app
COPY requirements/ requirements/
# A PyPI download can stall for a while on the CI and Render builders, and
# pip's default 15 s read timeout then fails the whole build (CI run #50,
# Pillow). Wait up to 120 s, retry each request, and run the install up to
# three times: a second run skips whatever the first one installed.
RUN for attempt in 1 2 3; do \
        pip install --no-cache-dir --timeout 120 --retries 10 -r requirements/production.txt && exit 0; \
        echo "pip install failed (attempt $attempt of 3), retrying in 15 s"; \
        sleep 15; \
    done; \
    exit 1
COPY . .

RUN useradd --create-home app && chown -R app /app
USER app

# One process with a few threads: the free plan has about 512 MB and a tenth of a CPU
CMD exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 120 --access-logfile -
