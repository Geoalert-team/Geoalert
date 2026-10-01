
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse


def root_view(request):
    return JsonResponse({"status": "ok", "message": "GeoAlert API is running"})


urlpatterns = [
    path('', root_view),
    path('django-admin/', admin.site.urls),
    path('api/auth/',            include('apps.accounts.accounts_urls')),
    path('api/hazards/',         include('apps.hazards.hazards_urls')),
    path('api/notifications/',   include('apps.notifications.notifications_urls')),
    path('api/guidance/',        include('apps.guidance.guidance_urls')),
    path('api/history/',         include('apps.history.history_urls')),
    path('api/reports/',         include('apps.reports.reports_urls')),
    path('api/barangays/',       include('apps.barangays.barangays_urls')),
    path('api/admin-dashboard/', include('apps.admin_dashboard.admin_urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)