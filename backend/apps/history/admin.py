from django.contrib import admin, messages

from apps.barangays.models import Purok
from apps.history.model_fits import make_live, site_check
from apps.history.models import ModelFit


@admin.register(ModelFit)
class ModelFitAdmin(admin.ModelAdmin):
    """Read-only list of retraining attempts, with an undo to an earlier switched fit."""
    list_display = ('hazard', 'created_at', 'result', 'is_live', 'version')
    list_filter = ('hazard', 'result', 'is_live')
    actions = ['make_live_action']

    def get_queryset(self, request):
        # The list never reads the bodies: a fire fit's model and report are megabytes, on a 512 MB server
        return super().get_queryset(request).defer('model', 'report')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_make_live_permission(self, request):
        return request.user.is_superuser

    @admin.action(description='Make the selected fit the one in use', permissions=['make_live'])
    def make_live_action(self, request, queryset):
        outlines = Purok.outlines_version()
        for fit in queryset.defer(None):  # the selected fits in full: the check reads their model and report
            try:
                make_live(fit, outlines, check=site_check)
            except ValueError as exc:
                self.message_user(request, f'{fit}: {exc}', level=messages.ERROR)
            else:
                self.message_user(request, f'{fit} is now in use.')
