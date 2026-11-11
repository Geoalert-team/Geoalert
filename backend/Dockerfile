# The backend as Render runs it. GDAL 3.6 is the newest Django 4.2 supports.
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
RUN pip install --no-cache-dir -r requirements/production.txt
COPY . .

RUN useradd --create-home app && chown -R app /app
USER app

# One process with a few threads: the free plan has about 512 MB and a tenth of a CPU
CMD exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 120 --access-logfile -
