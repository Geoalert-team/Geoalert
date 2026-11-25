"""
manage.py run_model_job --hazard {fire,flood,landslide} [--dry-run] [--today YYYY-MM-DD] [--cache-dir DIR]
                         [--stability-reps N]

The automatic retraining job (apps/history/model_job.py), run by
.github/workflows/model-retrain.yml: it fetches the training data from
GeoAlert (MODEL_JOB_API_URL, with the MODEL_JOB_TOKEN bearer token), trains,
and posts the attempt back; GeoAlert makes the fit live only when it passed.

--dry-run trains and prints "result: reason" but posts nothing. Any error
posts a Failed attempt with its reason (not in a dry run) and exits non-zero.
It prints counts, results and reasons only, never a spot. The flood and
landslide runs load outlines only into an empty database with
MODEL_JOB_SCRATCH_DB=true (the runner's own), so on a laptop pointed at the
shared database they stop before writing anything there. --stability-reps
sets the flood or landslide stability refits (flood 200, landslide 20 by
default, ruling R60: one neural network fit takes minutes, so 100 refits would not
fit GitHub's 360 minutes; the workflow also sets LANDSLIDE_MLP_JOBS so the
network's seeds are fitted side by side on the runner's cores).

The landslide run also keeps a limit of its own, LANDSLIDE_LIMIT_MINUTES after
the command starts: GitHub stops the job at 360 minutes and then nothing is
posted, so past the limit the run's refit loops stop it and a Failed attempt
("Failed: the run passed its 330-minute limit") is posted. Fire and flood
have none.
"""
import logging
import tempfile
import time
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.history import fire_evaluation as fe
from apps.history import fire_features, model_job

FLOOD_REPS, FLOOD_STABILITY_REPS = 1000, 200  # train_flood_model's defaults
LANDSLIDE_REPS, LANDSLIDE_STABILITY_REPS = 1000, 20  # the job's 20 refits (R60; train_landslide_model's 200 offline)
LANDSLIDE_LIMIT_MINUTES = 330  # after the command starts; the workflow's 360 leaves room for setup and the post
GIS_LOGGER = 'django.contrib.gis'  # GEOS and GDAL log their notices and errors here


class MaskDecimals(logging.Filter):
    """
    A GEOS or GDAL line can say "... at or near point X Y", and the job's
    settings print every log line to the console: each decimal number
    becomes #, as in a failed attempt's reason (model_job.mask_decimals).
    """

    def filter(self, record):
        try:
            text = record.getMessage()
        except (TypeError, ValueError):  # a malformed record: mask it as written
            text = str(record.msg)
        record.msg, record.args = model_job.mask_decimals(text), None
        return True


GIS_MASK = MaskDecimals()


class Command(BaseCommand):
    help = ('Retrain the fire, flood or landslide model on GeoAlert\'s data and post the attempt back (the automatic '
            'job).')

    def add_arguments(self, parser):
        parser.add_argument('--hazard', choices=('fire', 'flood', 'landslide'), required=True)
        parser.add_argument('--dry-run', action='store_true', help='Train and print the result; post nothing.')
        parser.add_argument('--today', default=None, help='Run as on this date (YYYY-MM-DD); default today in Manila.')
        parser.add_argument('--cache-dir', default=None, help='The download cache (default backend/.hazard_cache).')
        parser.add_argument('--stability-reps', type=int, default=None,
                            help='Stability refits for flood or landslide (default flood 200, landslide 100).')

    def handle(self, *args, **options):
        started = time.monotonic()  # the landslide run's own limit counts from here
        logging.getLogger(GIS_LOGGER).addFilter(GIS_MASK)  # kept for the rest of the run; added once however often
        hazard, dry_run = options['hazard'], options['dry_run']
        log = self.stdout.write
        try:
            today = date.fromisoformat(options['today']) if options['today'] else timezone.localdate()
            attempt = self.attempt(hazard, today, options['cache_dir'], log, options['stability_reps'], started)
            log(f'{attempt["result"]}: {attempt["reason"]}')
            if dry_run:
                log('Dry run: nothing was posted.')
                return
            answer = model_job.post(attempt)
            log(self.style.SUCCESS(f'GeoAlert saved attempt {answer["id"]}: {answer["result"]}'
                                   + (', now the live model' if answer['is_live'] else '')))
        except Exception as exc:
            reason = model_job.failed_reason(exc)
            if not dry_run:
                try:
                    model_job.post({'hazard': hazard, 'result': 'failed', 'reason': reason})
                except Exception as post_exc:  # the original failure is the one to report
                    self.stderr.write(f'The failed attempt could not be posted either ({type(post_exc).__name__}).')
            raise CommandError(reason) from exc

    def attempt(self, hazard, today, cache_dir, log, stability_reps=None, started=None):
        data = model_job.fetch(hazard)
        if hazard == 'fire':
            log(f'GeoAlert sent {len(data["fires"])} fire records.')
            return model_job.fire_attempt(data, today, fire_features.DATA_DIR, fe.BOOT_REPS, fe.INTERVAL_REPS, log)
        floor = data.get('floor') or {}
        log(f'GeoAlert sent {len(data["spots"])} located {hazard} spots in {floor.get("barangays", "?")} barangays.')
        cache = Path(cache_dir or Path(settings.BASE_DIR) / '.hazard_cache')
        if hazard == 'flood':
            run, reps, stability, limit = model_job.flood_attempt, FLOOD_REPS, FLOOD_STABILITY_REPS, {}
        else:
            from apps.history.landslide_training import Deadline  # the job's own limit (GitHub's 360 posts nothing)

            started = time.monotonic() if started is None else started
            minutes = LANDSLIDE_LIMIT_MINUTES
            run, reps, stability = model_job.landslide_attempt, LANDSLIDE_REPS, LANDSLIDE_STABILITY_REPS
            limit = {'deadline': Deadline(at=started + minutes * 60, minutes=minutes)}
        stability = stability if stability_reps is None else stability_reps
        with tempfile.TemporaryDirectory() as workdir:
            # fetch named here, so the outlines are fetched the way the data was
            return run(data, today, cache, Path(workdir), reps, stability, log, fetch=model_job.fetch, **limit)
