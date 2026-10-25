import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.barangays import purok_load
from apps.barangays.aliases import match_barangay
from apps.barangays.models import Barangay, Purok

DATA_DIR = Path(__file__).resolve().parents[2] / 'data' / 'puroks'
ESTIMATES = DATA_DIR / 'talisay_puroks_estimated.geojson'


FIELDS = ['name', 'kind', 'parent', 'boundary', 'source', 'confidence']


class DatabaseStore:
    """Applies a purok_load.plan_replace plan in one transaction."""

    def existing(self, barangay_ids):
        return list(Purok.objects.filter(barangay_id__in=barangay_ids).values_list('id', 'barangay_id', 'name'))

    def apply(self, plan):
        with transaction.atomic():
            # Deletes first, so a kept purok can take over a deleted one's name
            Purok.objects.filter(id__in=plan['delete']).delete()
            for pk, r in plan['update']:
                Purok.objects.filter(id=pk).update(**{f: r[f] for f in FIELDS})
            Purok.objects.bulk_create(Purok(barangay_id=r['barangay_id'], **{f: r[f] for f in FIELDS})
                                      for r in plan['create'])


class Command(BaseCommand):
    help = ('Load purok outlines from GeoJSON (features need barangay, name and kind). '
            'Replaces the puroks of every barangay in the file and leaves the others alone, '
            'so official lines can go in one barangay at a time.')

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(ESTIMATES),
                            help='GeoJSON to load (default: the generated estimates).')
        parser.add_argument('--source', choices=Purok.SOURCES, default='estimated',
                            help='Source for features that do not say (default: estimated).')
        parser.add_argument('--dry-run', action='store_true', help='Check and report without saving.')

    def handle(self, *args, **options):
        path = Path(options['file'])
        if not path.exists():
            raise CommandError(f'File not found: {path}')
        rows, problems = purok_load.read_features(json.loads(path.read_text(encoding='utf-8')), options['source'])

        barangays = list(Barangay.objects.all())
        for r in rows:
            brgy = match_barangay(r['barangay'], barangays)
            if brgy is None:
                problems.append(f'{r["name"]}: no barangay called "{r["barangay"]}"')
                continue
            if brgy.boundary is None:
                problems.append(f'{r["name"]}: barangay {brgy.name} has no outline to check against')
                continue
            fitted, share = purok_load.fit_to_barangay(r['boundary'], brgy.boundary)
            if fitted is None:
                problems.append(f'{r["name"]}: only {share:.0%} of it lies inside {brgy.name}')
                continue
            r['boundary'], r['barangay_id'], r['barangay_obj'] = fitted, brgy.id, brgy

        seen = set()
        for r in rows:
            key = (r.get('barangay_id'), r['name'].lower())
            if key in seen:
                problems.append(f'{r["name"]}: listed twice in {r["barangay"]}')
            seen.add(key)

        if problems:
            for p in problems:
                self.stderr.write(f'  {p}')
            raise CommandError(f'{len(problems)} problem(s); nothing was changed.')

        self.report(rows)
        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(f'Dry run: {len(rows)} puroks checked, nothing saved.'))
            return
        plan = purok_load.replace(rows, DatabaseStore())
        self.stdout.write(self.style.SUCCESS(
            f'Loaded {len(rows)} puroks for {len({r["barangay_id"] for r in rows})} barangays '
            f'({len(plan["update"])} updated, {len(plan["create"])} added, {len(plan["delete"])} removed).'))
        if plan['create'] or plan['delete']:
            self.stdout.write('Puroks were added or removed: run "manage.py import_bfp_fires --relink" '
                              'so fire history follows them.')

    def report(self, rows):
        """Per barangay, how the new outlines line up with the ones they replace."""
        by_brgy = {}
        for r in rows:
            by_brgy.setdefault(r['barangay_obj'], {})[r['name']] = r['boundary']
        for brgy, new in sorted(by_brgy.items(), key=lambda kv: kv[0].name):
            old = {p.name: p.boundary for p in Purok.objects.filter(barangay=brgy)}
            line = f'  {brgy.name}: {len(new)} puroks'
            if old:
                result = purok_load.compare(old, new)
                if result['matched']:
                    avg = sum(s for _, s in result['matched']) / len(result['matched'])
                    line += f', average overlap with the outlines replaced {avg:.0%}'
                self.stdout.write(line)
                for name, score in result['matched']:
                    self.stdout.write(f'      {score:4.0%}  {name}')
                if result['only_estimated']:
                    self.stdout.write(f'      only before: {", ".join(result["only_estimated"])}')
                if result['only_new']:
                    self.stdout.write(f'      new: {", ".join(result["only_new"])}')
            else:
                self.stdout.write(line)
