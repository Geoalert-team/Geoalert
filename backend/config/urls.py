
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
    path('api/auth/',            include('apps.accounts.urls')),
    path('api/hazards/',         include('apps.hazards.urls')),
    path('api/notifications/',   include('apps.notifications.urls')),
    path('api/guidance/',        include('apps.guidance.urls')),
    path('api/history/',         include('apps.history.urls')),
    path('api/reports/',         include('apps.reports.urls')),
    path('api/barangays/',       include('apps.barangays.urls')),
    path('api/admin-dashboard/', include('apps.admin_dashboard.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)