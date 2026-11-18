from django.contrib import admin

from apps.rainwatch.models import PagasaAlert, RainForecastRun, RainWatchOverride, RainWatchRules


@admin.register(RainWatchRules)
class RainWatchRulesAdmin(admin.ModelAdmin):
    """Add a row to change the rules; the newest row is in force. Never edited or deleted."""

    list_display = ('created_at', 'note', 'created_by')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        current = RainWatchRules.current()
        if current is not None:
            for name in ('flood_dry', 'flood_wet', 'slide_dry', 'slide_wet', 'wet_14day_mm',
                         'flood_exposure_min', 'steep_share_min', 'stale_hours'):
                value = getattr(current, name)
                initial[name] = ','.join(str(v) for v in value) if isinstance(value, list) else value
        return initial

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        super().save_model(request, obj, form, change)


class ViewOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RainForecastRun)
class RainForecastRunAdmin(ViewOnlyAdmin):
    list_display = ('source', 'init_time', 'hours', 'received_at', 'job_version')


@admin.register(PagasaAlert)
class PagasaAlertAdmin(ViewOnlyAdmin):
    list_display = ('event', 'severity', 'covers_talisay', 'effective', 'expires', 'fetched_at')


@admin.register(RainWatchOverride)
class RainWatchOverrideAdmin(ViewOnlyAdmin):
    list_display = ('hazard', 'level', 'starts_at', 'ends_at', 'note', 'cancelled_at')
