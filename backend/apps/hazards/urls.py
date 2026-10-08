from django.urls import path
from apps.hazards.views import (
    HazardZoneListView,
    HazardZoneCreateView,
    HazardZoneDetailView,
    HazardZoneResolvedListView,
    HazardZoneVerifyView,
    HazardTypeListView,
    HazardUnifiedView,
    HazardLayerListView,
)

urlpatterns = [
    path('',                  HazardZoneListView.as_view(),         name='hazard-list'),
    path('create/',           HazardZoneCreateView.as_view(),       name='hazard-create'),
    path('types/',            HazardTypeListView.as_view(),         name='hazard-types'),
    path('unified/',          HazardUnifiedView.as_view(),          name='hazard-unified'),
    path('layers/',           HazardLayerListView.as_view(),        name='hazard-layers'),
    path('resolved/',         HazardZoneResolvedListView.as_view(), name='hazard-resolved'),
    path('<uuid:pk>/',        HazardZoneDetailView.as_view(),       name='hazard-detail'),
    path('<uuid:pk>/verify/', HazardZoneVerifyView.as_view(),       name='hazard-verify'),
]