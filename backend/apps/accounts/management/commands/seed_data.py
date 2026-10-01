from django.core.management.base import BaseCommand
from apps.accounts.accounts_models import Role
from apps.hazards.hazards_models import HazardType


class Command(BaseCommand):
    help = 'Seed initial roles and hazard types'

    def handle(self, *args, **kwargs):
        # Seed roles
        roles = ['System_Admin', 'DRRMO_Officer', 'Barangay_Personnel']
        for role_name in roles:
            Role.objects.get_or_create(name=role_name)
            self.stdout.write(f'  ✓ Role: {role_name}')

        # Seed hazard types — GeoAlert covers only 3
        hazard_types = [
            {'name': 'Flood',     'logo_class': 'flood-icon'},
            {'name': 'Fire',      'logo_class': 'fire-icon'},
            {'name': 'Landslide', 'logo_class': 'landslide-icon'},
        ]
        for h in hazard_types:
            HazardType.objects.get_or_create(
                name=h['name'],
                defaults={'logo_class': h['logo_class']}
            )
            self.stdout.write(f'  ✓ Hazard type: {h["name"]}')

        self.stdout.write(self.style.SUCCESS('Seed complete.'))