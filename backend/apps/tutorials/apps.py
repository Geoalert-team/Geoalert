from django.apps import AppConfig


class TutorialsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.tutorials'
    verbose_name = 'Tutorial videos'

    def ready(self):
        # Any saved or deleted video or category refreshes the cached public
        # lists, including the videos deleted with a category. See list_cache.py.
        from django.db.models.signals import post_delete, post_save

        from apps.tutorials.list_cache import bump
        from apps.tutorials.models import TutorialVideo, VideoCategory

        for model in (TutorialVideo, VideoCategory):
            post_save.connect(bump, sender=model, dispatch_uid=f'tutorial-lists-save-{model.__name__}')
            post_delete.connect(bump, sender=model, dispatch_uid=f'tutorial-lists-delete-{model.__name__}')
