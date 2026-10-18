from django.apps import AppConfig

class HazardsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.hazards'
    label = 'hazards'

    def ready(self):
        # Anything the map shows changing moves its version, so the zone
        # endpoints stop answering 304 Not Modified. See utils/map_version.py.
        from django.db.models.signals import post_delete, post_save

        from apps.barangays.models import Barangay
        from apps.hazards.models import HazardType, HazardVerification, HazardZone
        from utils.map_version import bump

        for model in (HazardZone, HazardVerification, HazardType, Barangay):
            post_save.connect(bump, sender=model, dispatch_uid=f'map-version-save-{model.__name__}')
            post_delete.connect(bump, sender=model, dispatch_uid=f'map-version-delete-{model.__name__}')
